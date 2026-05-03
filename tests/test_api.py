from __future__ import annotations

import io
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import anyio
import httpx
import starlette
import starlette.testclient
from fastapi.testclient import TestClient

from tts_app.api import create_app
from tts_app.extractor import ExtractedText
from tts_app.ocr_providers.base import OCROptions, OCRProviderError
from tts_app.providers.base import AudioChunk, TTSOptions


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


class CapturingTTSProvider:
    name = "capturing"
    voice_options = ()
    speed_options = ()

    def __init__(self):
        self.calls: list[tuple[str, TTSOptions]] = []

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        self.calls.append((text, options))
        yield AudioChunk(data=b"sample-", mime_type="audio/mpeg", extension="mp3")
        yield AudioChunk(data=b"audio", mime_type="audio/mpeg", extension="mp3")


class FailingOCRProvider:
    name = "failing-ocr"

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        raise OCRProviderError("ocr unavailable")


def test_submit_text_starts_generation_and_history_returns_item(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    response = client.post("/api/generations/text", json={"text": "Hello world. Another sentence.", "title": "Note"})

    assert response.status_code == 200
    generation_id = response.json()["generation_id"]

    history = client.get("/api/generations")
    assert history.status_code == 200
    assert history.json()[0]["id"] == generation_id
    assert history.json()[0]["title"] == "Note"


def test_submit_text_logs_generation_request(test_settings, caplog):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="tts_app.api"):
        response = client.post(
            "/api/generations/text",
            json={"text": "Hello world.", "title": "Note", "voice": "Jennifer", "speed": 1.25},
        )

    assert response.status_code == 200
    generation_id = response.json()["generation_id"]
    assert any(
        f"text_generation_submitted generation_id={generation_id} voice=Jennifer speed=1.25" in record.getMessage()
        for record in caplog.records
    )


def test_submit_text_defaults_to_configured_qwen_voice(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    generation_id = client.post(
        "/api/generations/text",
        json={"text": "Hello world.", "title": "Note"},
    ).json()["generation_id"]

    detail = client.get(f"/api/generations/{generation_id}").json()

    assert detail["generation"]["voice"] == test_settings.qwen_voice


def test_options_returns_voice_and_speed_choices(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    response = client.get("/api/options")

    assert response.status_code == 200
    body = response.json()
    assert body["default_language"] == "en"
    assert body["default_voices"]["en"] == test_settings.qwen_voice
    assert body["default_voices"]["zh"] == "Fake Chinese"
    assert body["default_voice"] == test_settings.qwen_voice
    fake_english = next(voice for voice in body["voices"] if voice["value"] == "Fake English")
    assert fake_english["language"] == "en"
    assert fake_english["preferred"] is False
    assert {"value": 1.25, "label": "1.25x"} in body["speeds"]


def test_options_keeps_duplicate_voice_preferences_language_scoped(test_settings):
    settings = replace(test_settings, provider_name="qwen", qwen_api_key="key")
    client = TestClient(create_app(settings, run_background_inline=True))
    client.put("/api/voices/Cherry/preference", json={"preferred": True, "language": "en"})

    response = client.get("/api/options")

    assert response.status_code == 200
    cherry_entries = [voice for voice in response.json()["voices"] if voice["value"] == "Cherry"]
    assert {voice["language"] for voice in cherry_entries} == {"en", "zh"}
    assert next(voice for voice in cherry_entries if voice["language"] == "en")["preferred"] is True
    assert next(voice for voice in cherry_entries if voice["language"] == "zh")["preferred"] is False


def test_options_lists_multilingual_qwen_voices_for_chinese(test_settings):
    settings = replace(test_settings, provider_name="qwen", qwen_api_key="key")
    client = TestClient(create_app(settings, run_background_inline=True))

    response = client.get("/api/options")

    assert response.status_code == 200
    voices = response.json()["voices"]
    assert any(voice["value"] == "Jennifer" and voice["language"] == "zh" for voice in voices)
    assert any(voice["value"] == "Aiden" and voice["language"] == "zh" for voice in voices)


def test_voice_preference_endpoint_updates_preference(test_settings):
    settings = replace(test_settings, provider_name="qwen", qwen_api_key="key")
    client = TestClient(create_app(settings, run_background_inline=True))

    response = client.put("/api/voices/Jennifer/preference", json={"preferred": True, "language": "en"})

    assert response.status_code == 200
    assert response.json() == {"voice": "Jennifer", "language": "en", "preferred": True}
    options = client.get("/api/options").json()
    assert next(
        voice for voice in options["voices"] if voice["value"] == "Jennifer" and voice["language"] == "en"
    )["preferred"] is True


def test_voice_sample_returns_audio_without_creating_history(test_settings, monkeypatch):
    provider = CapturingTTSProvider()
    monkeypatch.setattr("tts_app.api.get_provider", lambda settings: provider)
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post("/api/voice-sample", json={"voice": "Jennifer", "speed": 1.25, "language": "en"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert response.content == b"sample-audio"
    assert client.get("/api/generations").json() == []
    assert not test_settings.audio_dir.exists()
    text, options = provider.calls[0]
    assert text.startswith("This is a short Readvox voice sample.")
    assert options.voice == "Jennifer"
    assert options.speed == 1.25
    assert options.language == "English"
    assert options.audio_format == "mp3"


def test_voice_sample_uses_chinese_script(test_settings, monkeypatch):
    provider = CapturingTTSProvider()
    monkeypatch.setattr("tts_app.api.get_provider", lambda settings: provider)
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post("/api/voice-sample", json={"voice": "Cherry", "speed": 1.0, "language": "zh"})

    assert response.status_code == 200
    assert response.content == b"sample-audio"
    text, options = provider.calls[0]
    assert "这是一个简短的 Readvox 语音示例" in text
    assert options.voice == "Cherry"
    assert options.language == "Chinese"


def test_create_ocr_draft_stores_image_and_returns_text(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        data={"language": "zh"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "zh"
    assert "Fake OCR text" in body["extracted_text"]
    assert (test_settings.data_dir / body["image_path"]).exists()


def test_create_ocr_draft_rejects_non_image_upload(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 400


def test_create_ocr_draft_rejects_empty_upload(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"", "image/png")},
    )

    assert response.status_code == 400


def test_create_ocr_draft_rejects_too_large_upload(test_settings):
    settings = replace(test_settings, max_image_bytes=4)
    client = TestClient(create_app(settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"12345", "image/png")},
    )

    assert response.status_code == 413


def test_failed_ocr_draft_keeps_real_image_path(test_settings, monkeypatch):
    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: FailingOCRProvider())
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 502
    draft = client.get("/api/ocr-drafts").json()[0]
    assert draft["status"] == "failed"
    assert draft["error"] == "ocr unavailable"
    assert draft["image_path"] == f"images/{draft['id']}/source.png"
    assert (test_settings.data_dir / draft["image_path"]).exists()


def test_delete_unlinked_ocr_draft_removes_image_directory(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image_path = test_settings.data_dir / draft["image_path"]

    response = client.delete(f"/api/ocr-drafts/{draft['id']}")

    assert response.status_code == 204
    assert not image_path.exists()
    assert not (test_settings.image_dir / str(draft["id"])).exists()


def test_update_ocr_draft_and_create_generation(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "en"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()

    update = client.put(f"/api/ocr-drafts/{draft['id']}", json={"language": "en", "extracted_text": "Reviewed text."})
    assert update.status_code == 200

    generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Wrong text.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    assert generation.status_code == 200
    detail = client.get(f"/api/generations/{generation.json()['generation_id']}").json()
    assert detail["generation"]["source_type"] == "image"
    assert detail["generation"]["full_text"] == "Reviewed text."
    assert detail["generation"]["settings"]["ocr_draft_id"] == draft["id"]


def test_generation_from_already_linked_ocr_draft_is_rejected(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Ignored.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )
    generation_count = len(client.get("/api/generations").json())

    response = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Ignored again.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    assert response.status_code == 409
    assert len(client.get("/api/generations").json()) == generation_count


def test_failed_ocr_draft_generation_is_rejected_until_reviewed(test_settings, monkeypatch):
    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: FailingOCRProvider())
    client = TestClient(create_app(test_settings, run_background_inline=True))
    client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    )
    draft = client.get("/api/ocr-drafts").json()[0]

    failed_generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Ignored.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )
    update = client.put(f"/api/ocr-drafts/{draft['id']}", json={"language": "en", "extracted_text": "Reviewed text."})
    reviewed_generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Ignored.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    assert failed_generation.status_code == 409
    assert update.status_code == 200
    assert update.json()["status"] == "completed"
    assert update.json()["error"] is None
    assert reviewed_generation.status_code == 200


def test_delete_linked_ocr_draft_is_rejected_by_api(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "en"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Reviewed text.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    response = client.delete(f"/api/ocr-drafts/{draft['id']}")

    assert response.status_code == 409


def test_submit_text_preserves_explicit_voice(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    generation_id = client.post(
        "/api/generations/text",
        json={"text": "Hello world.", "title": "Note", "voice": "Custom"},
    ).json()["generation_id"]

    detail = client.get(f"/api/generations/{generation_id}").json()

    assert detail["generation"]["voice"] == "Custom"


def test_submit_text_persists_selected_speed(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    generation_id = client.post(
        "/api/generations/text",
        json={"text": "Hello world.", "title": "Note", "speed": 1.25},
    ).json()["generation_id"]

    detail = client.get(f"/api/generations/{generation_id}").json()

    assert detail["generation"]["settings"]["speed"] == 1.25


def test_submit_text_persists_selected_language(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    generation_id = client.post(
        "/api/generations/text",
        json={"text": "你好。", "title": "Note", "voice": "Cherry", "language": "zh"},
    ).json()["generation_id"]

    detail = client.get(f"/api/generations/{generation_id}").json()

    assert detail["generation"]["settings"]["language"] == "zh"


def test_submit_text_rejects_invalid_speed(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    response = client.post(
        "/api/generations/text",
        json={"text": "Hello world.", "title": "Note", "speed": 2.5},
    )

    assert response.status_code == 422


def test_submit_url_defaults_to_configured_qwen_voice(test_settings, monkeypatch):
    async def fake_fetch_and_extract(url: str) -> ExtractedText:
        return ExtractedText(title="Page", text="Hello world from a fetched page.", url=url)

    monkeypatch.setattr("tts_app.api.fetch_and_extract", fake_fetch_and_extract)
    app = create_app(settings=test_settings)
    client = TestClient(app)

    generation_id = client.post(
        "/api/generations/url",
        json={"url": "https://example.test/page"},
    ).json()["generation_id"]

    detail = client.get(f"/api/generations/{generation_id}").json()

    assert detail["generation"]["voice"] == test_settings.qwen_voice


def test_submit_url_preserves_explicit_voice(test_settings, monkeypatch):
    async def fake_fetch_and_extract(url: str) -> ExtractedText:
        return ExtractedText(title="Page", text="Hello world from a fetched page.", url=url)

    monkeypatch.setattr("tts_app.api.fetch_and_extract", fake_fetch_and_extract)
    app = create_app(settings=test_settings)
    client = TestClient(app)

    generation_id = client.post(
        "/api/generations/url",
        json={"url": "https://example.test/page", "voice": "Custom"},
    ).json()["generation_id"]

    detail = client.get(f"/api/generations/{generation_id}").json()

    assert detail["generation"]["voice"] == "Custom"


def test_generation_detail_contains_audio_after_background_task(test_settings):
    app = create_app(settings=test_settings, run_background_inline=True)
    client = TestClient(app)

    generation_id = client.post(
        "/api/generations/text",
        json={"text": "Hello world. Another sentence.", "title": "Note"},
    ).json()["generation_id"]

    detail = client.get(f"/api/generations/{generation_id}")

    assert detail.status_code == 200
    assert detail.json()["generation"]["id"] == generation_id
    assert len(detail.json()["audio_segments"]) >= 1


async def test_inline_generation_completes_before_response_body_is_sent(test_settings):
    app = create_app(settings=test_settings, run_background_inline=True)
    body = json.dumps({"text": "Hello world.", "title": "Note"}).encode("utf-8")
    request_complete = False

    async def receive() -> dict[str, Any]:
        nonlocal request_complete
        if request_complete:
            return {"type": "http.disconnect"}
        request_complete = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] != "http.response.body" or message.get("more_body", False):
            return
        generation_id = json.loads(message.get("body", b"{}"))["generation_id"]
        detail = app.state.storage.get_generation(generation_id)
        assert len(detail["audio_segments"]) >= 1

    await app(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/api/generations/text",
            "raw_path": b"/api/generations/text",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "extensions": {},
            "state": {},
        },
        receive,
        send,
    )


def test_audio_endpoint_serves_cached_segment(test_settings):
    app = create_app(settings=test_settings, run_background_inline=True)
    client = TestClient(app)

    generation_id = client.post("/api/generations/text", json={"text": "Hello world.", "title": "Note"}).json()[
        "generation_id"
    ]
    detail = client.get(f"/api/generations/{generation_id}").json()
    audio_id = detail["audio_segments"][0]["id"]

    audio = client.get(f"/api/audio/{generation_id}/{audio_id}")

    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/")
    assert b"FAKE-TTS" in audio.content


def test_delete_generation_removes_history_and_audio_files(test_settings):
    app = create_app(settings=test_settings, run_background_inline=True)
    client = TestClient(app)
    generation_id = client.post("/api/generations/text", json={"text": "Hello world.", "title": "Note"}).json()[
        "generation_id"
    ]
    detail = client.get(f"/api/generations/{generation_id}").json()
    audio_path = test_settings.data_dir / detail["audio_segments"][0]["file_path"]
    assert audio_path.exists()

    response = client.delete(f"/api/generations/{generation_id}")

    assert response.status_code == 204
    assert client.get(f"/api/generations/{generation_id}").status_code == 404
    assert all(item["id"] != generation_id for item in client.get("/api/generations").json())
    assert not audio_path.exists()


def test_delete_image_generation_removes_linked_ocr_draft_and_image(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "en"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image_path = test_settings.data_dir / draft["image_path"]
    generation_id = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"text": "Reviewed text.", "voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    ).json()["generation_id"]

    response = client.delete(f"/api/generations/{generation_id}")

    assert response.status_code == 204
    assert not image_path.exists()
    assert client.get(f"/api/ocr-drafts/{draft['id']}").status_code == 404


def test_delete_missing_generation_returns_404(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    response = client.delete("/api/generations/999")

    assert response.status_code == 404


def test_update_progress_persists_segment_percentage(test_settings):
    app = create_app(settings=replace(test_settings, segment_max_chars=20))
    client = TestClient(app)
    generation_id = client.post(
        "/api/generations/text",
        json={"text": "Alpha beta gamma. Delta epsilon zeta. Eta theta iota. Kappa lambda mu.", "title": "Note"},
    ).json()["generation_id"]

    response = client.put(f"/api/generations/{generation_id}/progress", json={"segment_index": 1})

    assert response.status_code == 200
    assert response.json()["progress_percent"] == 50
    detail = client.get(f"/api/generations/{generation_id}").json()
    assert detail["generation"]["last_segment_index"] == 1
    assert detail["generation"]["progress_percent"] == 50


def test_update_progress_completed_sets_100_percent(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)
    generation_id = client.post("/api/generations/text", json={"text": "One. Two.", "title": "Note"}).json()[
        "generation_id"
    ]

    response = client.put(f"/api/generations/{generation_id}/progress", json={"segment_index": 1, "completed": True})

    assert response.status_code == 200
    assert response.json()["progress_percent"] == 100


async def test_generation_events_replays_existing_events(test_settings):
    app = create_app(settings=test_settings, run_background_inline=True)
    generation_id = await app.state.service.create_from_text(text="Hello world.", title="Note", voice="Test")
    await app.state.service.run_generation(generation_id, "Test")
    first_chunk_sent = anyio.Event()
    request_complete = False
    chunks: list[bytes] = []

    async def receive() -> dict[str, Any]:
        nonlocal request_complete
        if request_complete:
            await first_chunk_sent.wait()
            return {"type": "http.disconnect"}
        request_complete = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] != "http.response.body":
            return
        body = message.get("body", b"")
        if body:
            chunks.append(body)
            first_chunk_sent.set()

    await app(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": f"/api/generations/{generation_id}/events",
            "raw_path": f"/api/generations/{generation_id}/events".encode(),
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "extensions": {},
            "state": {},
        },
        receive,
        send,
    )

    text = b"".join(chunks).decode("utf-8")
    assert "data: " in text
    assert '"type": "generation_created"' in text


def test_root_serves_frontend(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Readvox" in response.text
