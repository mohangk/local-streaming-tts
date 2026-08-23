from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import AsyncIterator

import pytest

from tts_app.providers.base import AudioChunk, ProviderError, TTSOptions
from tts_app.voice_samples import VoiceSampleCache, VoiceSampleCacheError


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


class FailingSecondSegmentProvider:
    name = "failing-second"
    english_voices = ()
    chinese_voices = ()

    def __init__(self):
        self.calls = 0

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        self.calls += 1
        if self.calls == 2:
            raise ProviderError("second segment failed")
        yield AudioChunk(data=b"first-segment", mime_type="audio/mpeg", extension="mp3")


class EmptySecondSegmentProvider:
    name = "empty-second"
    english_voices = ()
    chinese_voices = ()

    def __init__(self):
        self.calls = 0

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        self.calls += 1
        if self.calls == 1:
            yield AudioChunk(data=b"first-segment", mime_type="audio/mpeg", extension="mp3")
        if False:
            yield


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


@pytest.mark.asyncio
async def test_voice_sample_cache_releases_cancelled_waiter_reference(test_settings):
    provider = SlowSampleProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Jennifer", language="English", audio_format="mp3")
    path = cache.cache_path(text="Sample text.", options=options, language="en")

    owner = asyncio.create_task(cache.get_or_create(text="Sample text.", options=options, language="en"))
    await provider.first_call_started.wait()
    waiter = asyncio.create_task(cache.get_or_create(text="Sample text.", options=options, language="en"))
    while cache._locks[str(path)][1] < 2:
        await asyncio.sleep(0)
    waiter.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiter
    provider.release_first_call.set()
    await owner

    assert cache._locks == {}


@pytest.mark.asyncio
async def test_voice_sample_cache_key_can_use_request_model(test_settings):
    provider = SlowSampleProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Kai", speed=1.0, language="English", audio_format="mp3")
    instruct_options = TTSOptions(
        voice="Kai",
        model="qwen3-tts-instruct-flash-realtime",
        speed=1.0,
        language="English",
        audio_format="mp3",
    )

    default_model_path = cache.cache_path(text="Sample text.", options=options, language="en")
    instruct_model_path = cache.cache_path(text="Sample text.", options=instruct_options, language="en")

    assert default_model_path != instruct_model_path


def test_voice_sample_cache_rejects_model_key_that_differs_from_provider_options(test_settings):
    provider = SlowSampleProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Kai", model="model-used-by-provider")

    with pytest.raises(ValueError, match="cache model must match provider options model"):
        cache.cache_path(text="Sample text.", options=options, language="en", model="different-cache-model")


def test_voice_sample_cache_key_includes_segment_boundary(test_settings):
    provider = SlowSampleProvider()
    default_cache = VoiceSampleCache(test_settings, provider)
    smaller_segments_cache = VoiceSampleCache(replace(test_settings, segment_max_chars=40), provider)
    options = TTSOptions(voice="Kai", model="qwen3-tts-instruct-flash-realtime")

    default_path = default_cache.cache_path(text="A long sample text.", options=options, language="en")
    smaller_segments_path = smaller_segments_cache.cache_path(
        text="A long sample text.", options=options, language="en"
    )

    assert default_path != smaller_segments_path


@pytest.mark.asyncio
async def test_voice_sample_cache_clear_during_generation_does_not_restore_cleared_sample(test_settings):
    provider = SlowSampleProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Kai", speed=1.0, language="English", audio_format="mp3")

    generation = asyncio.create_task(cache.get_or_create(text="Sample text.", options=options, language="en"))
    await provider.first_call_started.wait()
    cache.clear()
    provider.release_first_call.set()

    result = await generation

    assert result == (b"sample-audio", "audio/mpeg")
    assert not cache.cache_dir.exists()


@pytest.mark.asyncio
async def test_voice_sample_cache_retries_when_cached_file_disappears_before_read(test_settings, monkeypatch):
    provider = FailingSecondSegmentProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Kai", speed=1.0, language="English", audio_format="mp3")
    path = cache.cache_path(text="Sample text.", options=options, language="en")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"stale-cache")
    original_read_bytes = Path.read_bytes
    removed = False

    def disappear_before_read(candidate):
        nonlocal removed
        if candidate == path and not removed:
            removed = True
            candidate.unlink()
            raise FileNotFoundError(candidate)
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", disappear_before_read)

    result = await cache.get_or_create(text="Sample text.", options=options, language="en")

    assert result == (b"first-segment", "audio/mpeg")
    assert provider.calls == 1


def test_voice_sample_cache_coordinates_clear_with_temporary_file_open(test_settings, monkeypatch):
    provider = FailingSecondSegmentProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Kai", speed=1.0, language="English", audio_format="mp3")
    open_started = threading.Event()
    allow_open = threading.Event()
    original_open = Path.open
    generation_result = {}
    clear_result = {}

    def blocking_open(path, *args, **kwargs):
        if ".tmp." in path.name:
            open_started.set()
            if not allow_open.wait(timeout=2):
                raise TimeoutError("temporary file open was not released")
        return original_open(path, *args, **kwargs)

    def generate():
        try:
            generation_result["value"] = asyncio.run(
                cache.get_or_create(text="Sample text.", options=options, language="en")
            )
        except BaseException as exc:
            generation_result["error"] = exc

    def clear():
        try:
            cache.clear()
        except BaseException as exc:
            clear_result["error"] = exc

    monkeypatch.setattr(Path, "open", blocking_open)
    generation_thread = threading.Thread(target=generate)
    generation_thread.start()
    assert open_started.wait(timeout=2)
    clear_thread = threading.Thread(target=clear)
    clear_thread.start()
    time.sleep(0.05)
    allow_open.set()
    generation_thread.join(timeout=2)
    clear_thread.join(timeout=2)

    assert not generation_thread.is_alive()
    assert not clear_thread.is_alive()
    assert "error" not in generation_result
    assert "error" not in clear_result
    assert generation_result["value"] == (b"first-segment", "audio/mpeg")
    assert not cache.cache_dir.exists()


@pytest.mark.asyncio
async def test_voice_sample_cache_removes_partial_audio_when_later_text_segment_fails(test_settings):
    provider = FailingSecondSegmentProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Kai", speed=1.0, language="English", audio_format="mp3")
    text = "First sentence is long enough. Second sentence is also long enough. Third sentence continues."

    with pytest.raises(VoiceSampleCacheError, match="second segment failed"):
        await cache.get_or_create(text=text, options=options, language="en")

    assert provider.calls == 2
    assert not list(cache.cache_dir.glob("*.mp3"))
    assert not list(cache.cache_dir.glob("*.tmp.*"))


@pytest.mark.asyncio
async def test_voice_sample_cache_removes_partial_audio_when_request_is_cancelled(test_settings):
    provider = SlowSampleProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Kai", speed=1.0, language="English", audio_format="mp3")

    generation = asyncio.create_task(cache.get_or_create(text="Sample text.", options=options, language="en"))
    await provider.first_call_started.wait()
    generation.cancel()

    with pytest.raises(asyncio.CancelledError):
        await generation

    assert not list(cache.cache_dir.glob("*.mp3"))
    assert not list(cache.cache_dir.glob("*.tmp.*"))


@pytest.mark.asyncio
async def test_voice_sample_cache_rejects_empty_later_text_segment(test_settings):
    provider = EmptySecondSegmentProvider()
    cache = VoiceSampleCache(test_settings, provider)
    options = TTSOptions(voice="Kai", speed=1.0, language="English", audio_format="mp3")
    text = "First sentence is long enough. Second sentence is also long enough. Third sentence continues."

    with pytest.raises(VoiceSampleCacheError, match="no audio for sample segment"):
        await cache.get_or_create(text=text, options=options, language="en")

    assert provider.calls == 2
    assert not list(cache.cache_dir.glob("*.mp3"))
    assert not list(cache.cache_dir.glob("*.tmp.*"))


def test_voice_sample_cache_surfaces_clear_failure(test_settings, monkeypatch):
    cache = VoiceSampleCache(test_settings, SlowSampleProvider())
    cache.cache_dir.mkdir(parents=True)
    (cache.cache_dir / "first.mp3").write_bytes(b"first")
    (cache.cache_dir / "second.mp3").write_bytes(b"second")

    def fail_clear(path, **_kwargs):
        (path / "first.mp3").unlink()
        raise PermissionError("cache directory is read-only")

    monkeypatch.setattr("tts_app.voice_samples.shutil.rmtree", fail_clear)

    with pytest.raises(VoiceSampleCacheError, match="Unable to clear voice sample cache"):
        cache.clear()

    assert not cache.cache_dir.exists()
    tombstones = list(cache.cache_dir.parent.glob("voice-samples.clear.*"))
    assert len(tombstones) == 1
    assert (tombstones[0] / "second.mp3").read_bytes() == b"second"


def test_voice_sample_cache_surfaces_atomic_detach_failure(test_settings, monkeypatch):
    cache = VoiceSampleCache(test_settings, SlowSampleProvider())
    cache.cache_dir.mkdir(parents=True)
    cached_file = cache.cache_dir / "sample.mp3"
    cached_file.write_bytes(b"sample")

    def fail_detach(_source, _destination):
        raise PermissionError("cache parent is read-only")

    monkeypatch.setattr("tts_app.voice_samples.os.replace", fail_detach)

    with pytest.raises(VoiceSampleCacheError, match="Unable to clear voice sample cache"):
        cache.clear()

    assert cached_file.read_bytes() == b"sample"
