from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tts_app.config import Settings, load_settings
from tts_app.events import EventBroker
from tts_app.extractor import ExtractionError, fetch_and_extract
from tts_app.generation import GenerationService
from tts_app.providers.options import SelectOption
from tts_app.providers.registry import get_provider
from tts_app.storage import Storage


class TextGenerationRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str = "Manual text"
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    autoplay: bool = True


class UrlGenerationRequest(BaseModel):
    url: str = Field(min_length=1)
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    autoplay: bool = True


class ProgressRequest(BaseModel):
    segment_index: int = Field(ge=0)
    completed: bool = False


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
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.state.settings = active_settings
    app.state.storage = storage
    app.state.broker = broker
    app.state.service = service

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

    @app.get("/api/options")
    async def options():
        voices = _option_dicts(getattr(provider, "voice_options", ()))
        if active_settings.qwen_voice not in {str(option["value"]) for option in voices}:
            voices.insert(0, {"value": active_settings.qwen_voice, "label": active_settings.qwen_voice})
        return {
            "default_voice": active_settings.qwen_voice,
            "default_speed": 1.0,
            "voices": voices,
            "speeds": _option_dicts(getattr(provider, "speed_options", ())),
        }

    @app.post("/api/generations/text")
    async def submit_text(payload: TextGenerationRequest, background_tasks: BackgroundTasks):
        voice = payload.voice or active_settings.qwen_voice
        generation_id = await service.create_from_text(
            text=payload.text,
            title=payload.title,
            voice=voice,
            settings={"autoplay": payload.autoplay, "speed": payload.speed},
        )
        await _schedule_generation(service, generation_id, voice, payload.speed, background_tasks, run_background_inline)
        return {"generation_id": generation_id}

    @app.post("/api/generations/url")
    async def submit_url(payload: UrlGenerationRequest, background_tasks: BackgroundTasks):
        voice = payload.voice or active_settings.qwen_voice
        try:
            extracted = await fetch_and_extract(payload.url)
        except ExtractionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        generation_id = await service.create_from_text(
            text=extracted.text,
            title=extracted.title,
            source_type="url",
            url=extracted.url,
            voice=voice,
            settings={"autoplay": payload.autoplay, "speed": payload.speed},
        )
        await _schedule_generation(service, generation_id, voice, payload.speed, background_tasks, run_background_inline)
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

    @app.put("/api/generations/{generation_id}/progress")
    async def update_progress(generation_id: int, payload: ProgressRequest):
        try:
            return storage.update_generation_progress(generation_id, payload.segment_index, payload.completed)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc

    @app.delete("/api/generations/{generation_id}", status_code=204)
    async def delete_generation(generation_id: int):
        try:
            storage.get_generation(generation_id)
            storage.delete_generation(generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc
        shutil.rmtree(active_settings.audio_dir / str(generation_id), ignore_errors=True)
        return Response(status_code=204)

    @app.get("/api/audio/{generation_id}/{audio_segment_id}")
    async def get_audio(generation_id: int, audio_segment_id: int):
        try:
            audio = storage.get_audio_segment(generation_id, audio_segment_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audio not found") from exc
        path = active_settings.data_dir / audio["file_path"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="audio file not found")
        return FileResponse(path, media_type=audio["mime_type"], stat_result=path.stat())

    @app.get("/api/generations/{generation_id}/events")
    async def generation_events(generation_id: int):
        async def stream():
            async for event in broker.subscribe(generation_id):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


async def _schedule_generation(
    service: GenerationService,
    generation_id: int,
    voice: str,
    speed: float,
    background_tasks: BackgroundTasks,
    run_background_inline: bool,
) -> None:
    if run_background_inline:
        await service.run_generation(generation_id, voice, speed)
        return
    background_tasks.add_task(service.run_generation, generation_id, voice, speed)


def _option_dicts(options: Iterable[SelectOption]) -> list[dict[str, str | float]]:
    return [{"value": option.value, "label": option.label} for option in options]
