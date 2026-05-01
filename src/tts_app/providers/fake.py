from __future__ import annotations

import asyncio
import hashlib
from typing import AsyncIterator

from tts_app.providers.base import AudioChunk, TTSOptions


class FakeTTSProvider:
    name = "fake"

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        await asyncio.sleep(0)
        digest = hashlib.sha256(f"{options.voice}:{text}".encode("utf-8")).hexdigest()[:16]
        data = f"FAKE-TTS\nvoice={options.voice}\ndigest={digest}\ntext={text}\n".encode("utf-8")
        yield AudioChunk(data=data, mime_type="audio/mpeg", extension="mp3")
