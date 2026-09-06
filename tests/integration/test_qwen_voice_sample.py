from __future__ import annotations

import os
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from tts_app.api import create_app


pytestmark = [
    pytest.mark.live_provider,
    pytest.mark.skipif(
        os.environ.get("RUN_QWEN_INTEGRATION") != "1",
        reason="set RUN_QWEN_INTEGRATION=1 to call the live Qwen provider",
    ),
]


def test_saved_instruction_profile_integrates_with_qwen_generation(test_settings):
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        pytest.fail("DASHSCOPE_API_KEY or QWEN_API_KEY is required when RUN_QWEN_INTEGRATION=1")
    settings = replace(test_settings, provider_name="qwen", qwen_api_key=api_key)
    client = TestClient(create_app(settings, run_background_inline=True))

    profile = client.get("/api/voice-profiles").json()[0]
    profile["instructions"] = "Read calmly and clearly."
    profile["preview_text"] = "Readvox checks the live provider with calm, clear narration."
    saved = client.put(f"/api/voice-profiles/{profile['id']}", json=profile)
    assert saved.status_code == 200
    assert client.get("/api/generations").json() == []
    assert len(profile["preview_text"]) <= settings.segment_max_chars
    response = client.post("/api/generations/text", json={
        "text": profile["preview_text"], "profile_id": profile["id"], "autoplay": False,
    })
    assert response.status_code == 200, response.text
    generation_id = response.json()["generation_id"]
    detail = client.app.state.storage.get_generation(generation_id)
    assert detail["generation"]["status"] == "completed", detail["generation"]["error"]
    assert detail["generation"]["settings"]["model"] == profile["model"]
    assert detail["generation"]["settings"]["instructions"] == profile["instructions"]
    assert len(detail["audio_segments"]) == 1
    assert detail["audio_segments"][0]["byte_size"] > 1_000
