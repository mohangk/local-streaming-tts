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


def test_instruction_voice_sample_default_integrates_with_qwen(test_settings):
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        pytest.fail("DASHSCOPE_API_KEY or QWEN_API_KEY is required when RUN_QWEN_INTEGRATION=1")
    settings = replace(test_settings, provider_name="qwen", qwen_api_key=api_key)
    client = TestClient(create_app(settings, run_background_inline=True))

    sample_options = client.get("/api/voice-sample/options").json()
    sample_text = "Readvox checks the live provider with calm, clear narration."
    assert len(sample_text) <= settings.segment_max_chars
    response = client.post(
        "/api/voice-sample/instruction",
        json={
            "model": sample_options["default_model"],
            "voice": sample_options["default_voice"],
            "speed": sample_options["default_speed"],
            "language": sample_options["default_language"],
            "sample_text": sample_text,
            "instructions": "Read calmly and clearly.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("audio/")
    assert len(response.content) > 1_000
    assert client.get("/api/generations").json() == []
