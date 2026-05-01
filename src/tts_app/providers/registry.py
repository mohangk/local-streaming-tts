from __future__ import annotations

from tts_app.config import Settings
from tts_app.providers.base import TTSProvider
from tts_app.providers.fake import FakeTTSProvider
from tts_app.providers.qwen import QwenTTSProvider


def get_provider(settings: Settings) -> TTSProvider:
    if settings.provider_name == "fake":
        return FakeTTSProvider()
    if settings.provider_name == "qwen":
        return QwenTTSProvider(
            api_key=settings.qwen_api_key,
            model=settings.qwen_model,
            realtime_url=settings.qwen_realtime_url,
        )
    raise ValueError(f"unknown TTS provider: {settings.provider_name}")
