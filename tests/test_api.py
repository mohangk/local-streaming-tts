from __future__ import annotations

from fastapi.testclient import TestClient

from tts_app.api import create_app


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


def test_root_serves_frontend(test_settings):
    app = create_app(settings=test_settings)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Local TTS" in response.text
