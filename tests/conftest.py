from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import anyio
import httpx
import pytest
import starlette
import starlette.testclient

from tts_app.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        db_path=data_dir / "app.db",
        audio_dir=data_dir / "audio",
        image_dir=data_dir / "images",
        provider_name="fake",
        ocr_provider_name="fake",
        qwen_api_key=None,
        qwen_model="qwen3-tts-flash-realtime",
        ocr_model="qwen-vl-ocr",
        qwen_realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        default_audio_ext="mp3",
        segment_max_chars=80,
        max_image_bytes=10_485_760,
        default_english_voice="Jennifer",
        default_chinese_voice="Cherry",
    )


def _patch_starlette_1_testclient_for_tests() -> None:
    transport_cls = starlette.testclient._TestClientTransport
    if starlette.__version__ != "1.0.0" or getattr(transport_cls, "_tts_app_test_patched", False):
        return

    original_handle_request = transport_cls.handle_request

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
                await anyio.sleep(0)
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
                if request.method != "HEAD":
                    raw_kwargs["stream"].write(message.get("body", b""))
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
    transport_cls._tts_app_test_patched = True


_patch_starlette_1_testclient_for_tests()
