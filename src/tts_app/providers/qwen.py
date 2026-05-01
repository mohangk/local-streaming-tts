from __future__ import annotations

from typing import AsyncIterator

from tts_app.providers.base import AudioChunk, ProviderError, TTSOptions


class QwenTTSProvider:
    name = "qwen"

    def __init__(self, api_key: str | None, model: str, realtime_url: str):
        self.api_key = api_key
        self.model = model
        self.realtime_url = realtime_url

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        if not self.api_key:
            raise ProviderError("QWEN_API_KEY is required for qwen provider")
        raise ProviderError("qwen realtime provider is added in Task 9")
        yield AudioChunk(data=b"", mime_type="audio/mpeg", extension="mp3")
