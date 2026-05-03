from __future__ import annotations

from dataclasses import replace

import pytest

from tts_app.providers.base import TTSOptions
from tts_app.providers.fake import FakeTTSProvider
from tts_app.providers.qwen import QwenTTSProvider
from tts_app.providers.registry import get_provider


@pytest.mark.asyncio
async def test_fake_provider_streams_deterministic_chunks():
    provider = FakeTTSProvider()
    options = TTSOptions(voice="Test", audio_format="mp3")

    chunks = [
        chunk
        async for chunk in provider.stream_speech(
            "Hello world.",
            options,
        )
    ]
    repeated_chunks = [
        chunk
        async for chunk in provider.stream_speech(
            "Hello world.",
            options,
        )
    ]

    assert chunks[0].mime_type == "audio/mpeg"
    assert chunks[0].data == repeated_chunks[0].data
    assert b"FAKE-TTS" in chunks[0].data
    assert b"Hello world." in chunks[0].data


def test_fake_provider_declares_own_language_voice_options():
    provider = FakeTTSProvider()

    assert provider.english_voices
    assert provider.chinese_voices
    assert not hasattr(provider, "voice_options")
    assert all("Qwen" not in voice.label for voice in provider.english_voices + provider.chinese_voices)
    assert {voice.language for voice in provider.english_voices} == {"en"}
    assert {voice.language for voice in provider.chinese_voices} == {"zh"}


def test_qwen_provider_declares_language_voice_options():
    provider = QwenTTSProvider(api_key="key", model="model", realtime_url="wss://example.test")

    assert provider.english_voices
    assert provider.chinese_voices
    assert not hasattr(provider, "voice_options")
    assert {voice.language for voice in provider.english_voices} == {"en"}
    assert {voice.language for voice in provider.chinese_voices} == {"zh"}


def test_registry_returns_fake_provider(test_settings):
    provider = get_provider(test_settings)

    assert provider.name == "fake"


def test_registry_returns_qwen_provider(test_settings):
    settings = replace(test_settings, provider_name="qwen", qwen_api_key="key")

    provider = get_provider(settings)

    assert isinstance(provider, QwenTTSProvider)
    assert provider.api_key == "key"
    assert provider.model == settings.qwen_model
    assert provider.realtime_url == settings.qwen_realtime_url


def test_registry_rejects_unknown_provider(test_settings):
    settings = replace(test_settings, provider_name="unknown")

    with pytest.raises(ValueError, match="unknown TTS provider: unknown"):
        get_provider(settings)
