from __future__ import annotations

import asyncio
import hashlib
from typing import AsyncIterator

from tts_app.providers.base import AudioChunk, TTSOptions
from tts_app.providers.options import SPEED_OPTIONS, SelectOption


FAKE_ENGLISH_VOICES: tuple[SelectOption, ...] = (
    SelectOption("Fake English", "Fake English voice", language="en"),
)

FAKE_CHINESE_VOICES: tuple[SelectOption, ...] = (
    SelectOption("Fake Chinese", "Fake Chinese voice", language="zh"),
)


class FakeTTSProvider:
    name = "fake"
    english_voices = FAKE_ENGLISH_VOICES
    chinese_voices = FAKE_CHINESE_VOICES
    speed_options = SPEED_OPTIONS

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        await asyncio.sleep(0)
        digest = hashlib.sha256(
            f"{options.model}:{options.voice}:{options.speed}:{options.instructions}:{text}".encode("utf-8")
        ).hexdigest()[:16]
        data = (
            f"FAKE-TTS\nmodel={options.model or ''}\nvoice={options.voice}\nspeed={options.speed}\n"
            f"instructions={options.instructions or ''}\ndigest={digest}\ntext={text}\n"
        ).encode("utf-8")
        yield AudioChunk(data=data, mime_type="audio/mpeg", extension="mp3")
