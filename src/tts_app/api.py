from __future__ import annotations

import json
import io
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import anyio
import httpx
import starlette
import starlette.testclient
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from tts_app.config import Settings, load_settings
from tts_app.events import EventBroker
from tts_app.extractor import ExtractionError, fetch_and_extract
from tts_app.generation import GenerationService
from tts_app.providers.registry import get_provider
from tts_app.storage import Storage


def _patch_starlette_1_testclient() -> None:
    transport_cls = starlette.testclient._TestClientTransport
    if starlette.__version__ != "1.0.0" or getattr(transport_cls, "_tts_app_patched", False):
        return

    original_handle_request = transport_cls.handle_request

    # Starlette 1.0.0's TestClient can deadlock on Python 3.14 before the app
    # receives the request. Returning http.disconnect immediately after the
    # request body is consumed matches the behavior these route tests need.
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        scheme = request.url.scheme
        if scheme in {"ws", "wss"}:
            return original_handle_request(self, request)

        netloc = request.url.netloc.decode(encoding="ascii")
        path = request.url.path
        raw_path = request.url.raw_path
        query = request.url.query.decode(encoding="ascii")
        default_port = {"http": 80, "https": 443}[scheme]

        if ":" in netloc:
            host, port_string = netloc.split(":", 1)
            port = int(port_string)
        else:
            host = netloc
            port = default_port

        headers: list[tuple[bytes, bytes]]
        if "host" in request.headers:
            headers = []
        elif port == default_port:
            headers = [(b"host", host.encode())]
        else:
            headers = [(b"host", f"{host}:{port}".encode())]
        headers += [(key.lower().encode(), value.encode()) for key, value in request.headers.multi_items()]

        scope: dict[str, Any] = {
            "type": "http",
            "http_version": "1.1",
            "method": request.method,
            "path": unquote(path),
            "raw_path": raw_path.split(b"?", 1)[0],
            "root_path": self.root_path,
            "scheme": scheme,
            "query_string": query.encode(),
            "headers": headers,
            "client": self.client,
            "server": [host, port],
            "extensions": {"http.response.debug": {}, "http.response.pathsend": {}},
            "state": self.app_state.copy(),
        }
        request_complete = False
        response_started = False
        raw_kwargs: dict[str, Any] = {"stream": io.BytesIO()}

        async def receive() -> dict[str, Any]:
            nonlocal request_complete
            if request_complete:
                return {"type": "http.disconnect"}
            request_complete = True
            body = request.read()
            if isinstance(body, str):
                body = body.encode("utf-8")
            return {"type": "http.request", "body": body or b""}

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                raw_kwargs["status_code"] = message["status"]
                raw_kwargs["headers"] = [(key.decode(), value.decode()) for key, value in message.get("headers", [])]
                response_started = True
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if request.method != "HEAD":
                    raw_kwargs["stream"].write(body)
                if not message.get("more_body", False):
                    raw_kwargs["stream"].seek(0)
            elif message["type"] == "http.response.pathsend":
                if request.method != "HEAD":
                    raw_kwargs["stream"].write(Path(message["path"]).read_bytes())
                raw_kwargs["stream"].seek(0)

        try:
            anyio.run(self.app, scope, receive, send)
        except BaseException as exc:
            if self.raise_server_exceptions:
                raise exc

        if self.raise_server_exceptions:
            assert response_started, "TestClient did not receive any response."
        elif not response_started:
            raw_kwargs = {"status_code": 500, "headers": [], "stream": io.BytesIO()}

        raw_kwargs["stream"] = httpx.ByteStream(raw_kwargs["stream"].read())
        return httpx.Response(**raw_kwargs, request=request)

    transport_cls.handle_request = handle_request
    transport_cls._tts_app_patched = True


_patch_starlette_1_testclient()


class TextGenerationRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str = "Manual text"
    voice: str = "Test"
    autoplay: bool = True


class UrlGenerationRequest(BaseModel):
    url: str = Field(min_length=1)
    voice: str = "Test"
    autoplay: bool = True


def create_app(settings: Settings | None = None, run_background_inline: bool = False) -> FastAPI:
    active_settings = settings or load_settings()
    storage = Storage(active_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    provider = get_provider(active_settings)
    service = GenerationService(
        storage=storage,
        provider=provider,
        broker=broker,
        audio_dir=active_settings.audio_dir,
        segment_max_chars=active_settings.segment_max_chars,
    )
    app = FastAPI(title="Local Streaming TTS")
    app.state.settings = active_settings
    app.state.storage = storage
    app.state.broker = broker
    app.state.service = service

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

    @app.post("/api/generations/text")
    async def submit_text(payload: TextGenerationRequest, background_tasks: BackgroundTasks):
        generation_id = await service.create_from_text(
            text=payload.text,
            title=payload.title,
            voice=payload.voice,
            settings={"autoplay": payload.autoplay},
        )
        _schedule_generation(service, generation_id, payload.voice, background_tasks, run_background_inline)
        return {"generation_id": generation_id}

    @app.post("/api/generations/url")
    async def submit_url(payload: UrlGenerationRequest, background_tasks: BackgroundTasks):
        try:
            extracted = await fetch_and_extract(payload.url)
        except ExtractionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        generation_id = await service.create_from_text(
            text=extracted.text,
            title=extracted.title,
            source_type="url",
            url=extracted.url,
            voice=payload.voice,
            settings={"autoplay": payload.autoplay},
        )
        _schedule_generation(service, generation_id, payload.voice, background_tasks, run_background_inline)
        return {"generation_id": generation_id}

    @app.get("/api/generations")
    async def list_generations():
        return storage.list_generations()

    @app.get("/api/generations/{generation_id}")
    async def get_generation(generation_id: int):
        try:
            return storage.get_generation(generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc

    @app.get("/api/audio/{generation_id}/{audio_segment_id}")
    async def get_audio(generation_id: int, audio_segment_id: int):
        try:
            audio = storage.get_audio_segment(generation_id, audio_segment_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audio not found") from exc
        path = active_settings.data_dir / audio["file_path"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="audio file not found")
        if starlette.__version__ == "1.0.0":
            return Response(content=path.read_bytes(), media_type=audio["mime_type"])
        return FileResponse(path, media_type=audio["mime_type"])

    @app.get("/api/generations/{generation_id}/events")
    async def generation_events(generation_id: int):
        async def stream():
            async for event in broker.subscribe(generation_id):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


def _schedule_generation(
    service: GenerationService,
    generation_id: int,
    voice: str,
    background_tasks: BackgroundTasks,
    run_background_inline: bool,
) -> None:
    background_tasks.add_task(service.run_generation, generation_id, voice)
