from __future__ import annotations

import asyncio
import hashlib
from typing import AsyncIterator

from tts_app.providers.base import AudioChunk, TTSOptions
from tts_app.providers.options import QWEN_ENGLISH_VOICES, SPEED_OPTIONS


class FakeTTSProvider:
    name = "fake"
    voice_options = QWEN_ENGLISH_VOICES
    speed_options = SPEED_OPTIONS

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        await asyncio.sleep(0)
        digest = hashlib.sha256(f"{options.voice}:{options.speed}:{text}".encode("utf-8")).hexdigest()[:16]
        data = f"FAKE-TTS\nvoice={options.voice}\nspeed={options.speed}\ndigest={digest}\ntext={text}\n".encode("utf-8")
        yield AudioChunk(data=data, mime_type="audio/mpeg", extension="mp3")
