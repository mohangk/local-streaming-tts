from __future__ import annotations

from dataclasses import replace
from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from tts_app.api import create_app
from tts_app.ocr_providers.base import OCROptions, OCRProviderError
from tts_app.providers.base import AudioChunk, TTSOptions
from tts_app.providers.options import SelectOption

class CapturingTTSProvider:
    name = "capturing"
    english_voices = (SelectOption("Capture English", "Capture English", language="en"),)
    chinese_voices = (SelectOption("Capture Chinese", "Capture Chinese", language="zh"),)
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


class EmptyOCRProvider:
    name = "empty-ocr"

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        return " \n\t "


class FailsOnceOCRProvider:
    name = "fails-once-ocr"

    def __init__(self):
        self.calls: list[tuple[bytes, str, OCROptions]] = []

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        self.calls.append((image, mime_type, options))
        if len(self.calls) == 1:
            raise OCRProviderError("temporary ocr outage")
        return "Recovered OCR text"


def test_create_ocr_draft_stores_images_and_returns_ordered_text(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        data={"language": "zh"},
        files=[
            ("image", ("page-1.png", b"fake-image-one", "image/png")),
            ("image", ("page-2.jpg", b"fake-image-two", "image/jpeg")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "zh"
    assert body["status"] == "completed"
    assert [image["position"] for image in body["images"]] == [0, 1]
    assert all("Fake OCR text" in image["extracted_text"] for image in body["images"])
    assert "Fake OCR text" in body["combined_text"]
    assert all((test_settings.data_dir / image["image_path"]).exists() for image in body["images"])


def test_create_ocr_draft_still_accepts_single_image(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["images"]) == 1
    assert body["image_path"] == body["images"][0]["image_path"]


def test_append_ocr_draft_images_preserves_reviewed_combined_text(test_settings, monkeypatch):
    class CountingOCRProvider:
        name = "counting-ocr"

        def __init__(self):
            self.calls = 0

        async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
            self.calls += 1
            return f"Page {self.calls} text"

    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: CountingOCRProvider())
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page-1.png", b"fake-image-one", "image/png")},
    ).json()
    client.put(f"/api/ocr-drafts/{draft['id']}", json={"language": "en", "combined_text": "Reviewed existing text"})

    response = client.post(
        f"/api/ocr-drafts/{draft['id']}/images",
        files=[
            ("image", ("page-2.png", b"fake-image-two", "image/png")),
            ("image", ("page-3.png", b"fake-image-three", "image/png")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == draft["id"]
    assert [image["position"] for image in body["images"]] == [0, 1, 2]
    assert [image["extracted_text"] for image in body["images"]] == ["Page 1 text", "Page 2 text", "Page 3 text"]
    assert body["combined_text"] == "Reviewed existing text\n\nPage 2 text\n\nPage 3 text"
    assert len(client.get("/api/ocr-drafts").json()) == 1


def test_append_ocr_draft_images_can_use_current_unsaved_combined_text(test_settings, monkeypatch):
    class CountingOCRProvider:
        name = "counting-ocr"

        def __init__(self):
            self.calls = 0

        async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
            self.calls += 1
            return f"Page {self.calls} text"

    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: CountingOCRProvider())
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page-1.png", b"fake-image-one", "image/png")},
    ).json()

    response = client.post(
        f"/api/ocr-drafts/{draft['id']}/images",
        data={"combined_text": "Unsaved textarea edit"},
        files={"image": ("page-2.png", b"fake-image-two", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["combined_text"] == "Unsaved textarea edit\n\nPage 2 text"


def test_append_ocr_draft_images_rejects_linked_draft(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page-1.png", b"fake-image-one", "image/png")},
    ).json()
    generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )
    assert generation.status_code == 200

    response = client.post(
        f"/api/ocr-drafts/{draft['id']}/images",
        files={"image": ("page-2.png", b"fake-image-two", "image/png")},
    )

    assert response.status_code == 409


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


def test_partial_ocr_failure_keeps_successful_image_text(test_settings, monkeypatch):
    class PartiallyFailingOCRProvider:
        name = "partial-ocr"

        def __init__(self):
            self.calls = 0

        async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
            self.calls += 1
            if self.calls == 2:
                raise OCRProviderError("second page failed")
            return f"Page {self.calls} text"

    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: PartiallyFailingOCRProvider())
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        files=[
            ("image", ("page-1.png", b"fake-image-one", "image/png")),
            ("image", ("page-2.png", b"fake-image-two", "image/png")),
        ],
    )

    assert response.status_code == 200
    draft = response.json()
    assert draft["status"] == "partial_failed"
    assert [image["status"] for image in draft["images"]] == ["completed", "failed"]
    assert draft["images"][0]["extracted_text"] == "Page 1 text"
    assert draft["combined_text"] == "Page 1 text"
    assert draft["images"][1]["error"] == "second page failed"


def test_failed_ocr_draft_keeps_real_image_path(test_settings, monkeypatch):
    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: FailingOCRProvider())
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 200
    draft = client.get("/api/ocr-drafts").json()[0]
    assert draft["status"] == "failed"
    assert draft["images"][0]["error"] == "ocr unavailable"
    assert draft["images"][0]["image_path"] == f"images/{draft['id']}/{draft['images'][0]['id']}/source.png"
    assert (test_settings.data_dir / draft["images"][0]["image_path"]).exists()


def test_retry_failed_ocr_image_uses_stored_file_and_updates_draft(test_settings, monkeypatch):
    provider = FailsOnceOCRProvider()
    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: provider)
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "zh"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image = draft["images"][0]

    response = client.post(f"/api/ocr-drafts/{draft['id']}/images/{image['id']}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["error"] is None
    assert body["combined_text"] == "Recovered OCR text"
    assert body["images"][0]["status"] == "completed"
    assert body["images"][0]["error"] is None
    assert body["images"][0]["extracted_text"] == "Recovered OCR text"
    assert [call[0] for call in provider.calls] == [b"fake-image", b"fake-image"]
    assert provider.calls[1][1] == "image/png"
    assert provider.calls[1][2].language == "zh"
    assert provider.calls[1][2].model == test_settings.ocr_model


def test_retry_ocr_image_on_linked_draft_is_rejected(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    response = client.post(f"/api/ocr-drafts/{draft['id']}/images/{draft['images'][0]['id']}/retry")

    assert response.status_code == 409


def test_retry_missing_ocr_image_is_not_found(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post("/api/ocr-drafts/999/images/888/retry")

    assert response.status_code == 404


def test_empty_ocr_draft_is_failed_with_real_image_path(test_settings, monkeypatch):
    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: EmptyOCRProvider())
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 200
    draft = client.get("/api/ocr-drafts").json()[0]
    assert draft["status"] == "failed"
    assert draft["images"][0]["error"] == "OCR returned no visible text"
    assert draft["combined_text"] == ""
    assert (test_settings.data_dir / draft["images"][0]["image_path"]).exists()


def test_delete_unlinked_ocr_draft_removes_image_directory(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image_path = test_settings.data_dir / draft["images"][0]["image_path"]

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

    update = client.put(
        f"/api/ocr-drafts/{draft['id']}",
        json={"language": "en", "combined_text": "Reviewed text."},
    )
    assert update.status_code == 200
    assert update.json()["combined_text"] == "Reviewed text."
    assert update.json()["images"][0]["extracted_text"] != "Reviewed text."

    generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    assert generation.status_code == 200
    detail = client.get(f"/api/generations/{generation.json()['generation_id']}").json()
    assert detail["generation"]["source_type"] == "image"
    assert detail["generation"]["full_text"] == "Reviewed text."
    assert detail["generation"]["settings"]["ocr_draft_id"] == draft["id"]


def test_ocr_generation_uses_combined_text(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files=[
            ("image", ("page-1.png", b"fake-image-one", "image/png")),
            ("image", ("page-2.png", b"fake-image-two", "image/png")),
            ("image", ("page-3.png", b"fake-image-three", "image/png")),
        ],
    ).json()
    client.put(
        f"/api/ocr-drafts/{draft['id']}",
        json={
            "language": "en",
            "combined_text": "Edited combined text.",
        },
    )

    generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    assert generation.status_code == 200
    detail = client.get(f"/api/generations/{generation.json()['generation_id']}").json()
    assert detail["generation"]["full_text"] == "Edited combined text."


def test_ocr_generation_saves_reviewed_text_from_generation_request(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()

    generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={
            "voice": "Jennifer",
            "speed": 1.0,
            "language": "en",
            "autoplay": True,
            "combined_text": "Reviewed text sent with generate.",
        },
    )

    assert generation.status_code == 200
    detail = client.get(f"/api/generations/{generation.json()['generation_id']}").json()
    assert detail["generation"]["full_text"] == "Reviewed text sent with generate."
    updated = client.get(f"/api/ocr-drafts/{draft['id']}").json()
    assert updated["combined_text"] == "Reviewed text sent with generate."


def test_retry_ocr_image_rebuilds_combined_text_from_all_images(test_settings, monkeypatch):
    class RetryMiddleOCRProvider:
        name = "retry-middle-ocr"

        def __init__(self):
            self.calls = 0

        async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
            self.calls += 1
            if self.calls == 2:
                raise OCRProviderError("middle failed")
            if self.calls == 4:
                return "Recovered middle"
            return f"Page {self.calls} text"

    provider = RetryMiddleOCRProvider()
    monkeypatch.setattr("tts_app.api.get_ocr_provider", lambda settings: provider)
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files=[
            ("image", ("page-1.png", b"fake-image-one", "image/png")),
            ("image", ("page-2.png", b"fake-image-two", "image/png")),
            ("image", ("page-3.png", b"fake-image-three", "image/png")),
        ],
    ).json()
    client.put(f"/api/ocr-drafts/{draft['id']}", json={"language": "en", "combined_text": "User edit"})

    response = client.post(f"/api/ocr-drafts/{draft['id']}/images/{draft['images'][1]['id']}/retry")

    assert response.status_code == 200
    assert response.json()["combined_text"] == "Page 1 text\n\nRecovered middle\n\nPage 3 text"


def test_ocr_image_endpoint_serves_stored_image(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image = draft["images"][0]

    response = client.get(f"/api/ocr-drafts/{draft['id']}/images/{image['id']}")

    assert response.status_code == 200
    assert response.content == b"fake-image"
    assert response.headers["content-type"].startswith("image/")


def test_ocr_image_endpoint_uses_configured_image_dir(test_settings, tmp_path):
    settings = replace(test_settings, image_dir=tmp_path / "custom-images")
    client = TestClient(create_app(settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image = draft["images"][0]

    response = client.get(f"/api/ocr-drafts/{draft['id']}/images/{image['id']}")

    assert response.status_code == 200
    assert response.content == b"fake-image"
    assert (settings.image_dir / str(draft["id"]) / str(image["id"]) / "source.png").exists()


def test_delete_ocr_draft_image_removes_file(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files=[
            ("image", ("page-1.png", b"fake-image-one", "image/png")),
            ("image", ("page-2.png", b"fake-image-two", "image/png")),
        ],
    ).json()
    deleted_path = test_settings.data_dir / draft["images"][0]["image_path"]

    response = client.delete(f"/api/ocr-drafts/{draft['id']}/images/{draft['images'][0]['id']}")

    assert response.status_code == 204
    assert not deleted_path.exists()
    updated = client.get(f"/api/ocr-drafts/{draft['id']}").json()
    assert len(updated["images"]) == 1
    assert updated["images"][0]["position"] == 0
    assert updated["combined_text"] == updated["images"][0]["extracted_text"]


def test_image_generation_passes_selected_language_to_tts_provider(test_settings, monkeypatch):
    provider = CapturingTTSProvider()
    monkeypatch.setattr("tts_app.api.get_provider", lambda settings: provider)
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "zh"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()

    response = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Cherry", "speed": 1.0, "language": "zh", "autoplay": True},
    )

    assert response.status_code == 200
    assert provider.calls
    assert provider.calls[0][1].language == "Chinese"


def test_generation_from_already_linked_ocr_draft_is_rejected(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )
    generation_count = len(client.get("/api/generations").json())

    response = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
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
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )
    update = client.put(
        f"/api/ocr-drafts/{draft['id']}",
        json={"language": "en", "combined_text": "Reviewed text."},
    )
    reviewed_generation = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    assert failed_generation.status_code == 400
    assert update.status_code == 200
    assert update.json()["combined_text"] == "Reviewed text."
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
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    )

    response = client.delete(f"/api/ocr-drafts/{draft['id']}")

    assert response.status_code == 409


def test_delete_image_generation_removes_linked_ocr_draft_and_image(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    draft = client.post(
        "/api/ocr-drafts",
        data={"language": "en"},
        files={"image": ("page.png", b"fake-image", "image/png")},
    ).json()
    image_path = test_settings.data_dir / draft["images"][0]["image_path"]
    generation_id = client.post(
        f"/api/ocr-drafts/{draft['id']}/generation",
        json={"voice": "Jennifer", "speed": 1.0, "language": "en", "autoplay": True},
    ).json()["generation_id"]

    response = client.delete(f"/api/generations/{generation_id}")

    assert response.status_code == 204
    assert not image_path.exists()
    assert client.get(f"/api/ocr-drafts/{draft['id']}").status_code == 404
