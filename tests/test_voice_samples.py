from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from tts_app.providers.base import AudioChunk, TTSOptions
from tts_app.voice_samples import VoiceSampleCache


class SlowSampleProvider:
    name = "slow"
    english_voices = ()
    chinese_voices = ()

    def __init__(self):
        self.calls = 0
        self.first_call_started = asyncio.Event()
        self.release_first_call = asyncio.Event()

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        self.calls += 1
        if self.calls == 1:
            self.first_call_started.set()
            await self.release_first_call.wait()
        yield AudioChunk(data=b"sample-audio", mime_type="audio/mpeg", extension="mp3")


@pytest.mark.asyncio
async def test_voice_sample_cache_serializes_concurrent_identical_misses(test_settings):
    provider = SlowSampleProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Jennifer", speed=1.25, language="English", audio_format="mp3")

    first = asyncio.create_task(cache.get_or_create(text="Sample text.", options=options, language="en"))
    await provider.first_call_started.wait()
    second = asyncio.create_task(cache.get_or_create(text="Sample text.", options=options, language="en"))
    await asyncio.sleep(0)
    provider.release_first_call.set()

    first_result, second_result = await asyncio.gather(first, second)

    assert first_result == (b"sample-audio", "audio/mpeg")
    assert second_result == (b"sample-audio", "audio/mpeg")
    assert provider.calls == 1
