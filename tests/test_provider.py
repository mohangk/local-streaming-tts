from __future__ import annotations

import pytest

from tts_app.providers.base import TTSOptions
from tts_app.providers.fake import FakeTTSProvider
from tts_app.providers.registry import get_provider


@pytest.mark.asyncio
async def test_fake_provider_streams_deterministic_chunks():
    provider = FakeTTSProvider()

    chunks = [
        chunk
        async for chunk in provider.stream_speech(
            "Hello world.",
            TTSOptions(voice="Test", audio_format="mp3"),
        )
    ]

    assert chunks[0].mime_type == "audio/mpeg"
    assert b"FAKE-TTS" in chunks[0].data
    assert b"Hello world." in chunks[0].data


def test_registry_returns_fake_provider(test_settings):
    provider = get_provider(test_settings)

    assert provider.name == "fake"
