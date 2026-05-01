from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest

from tts_app.events import EventBroker
from tts_app.generation import GenerationService
from tts_app.providers.base import AudioChunk, ProviderError, TTSOptions
from tts_app.providers.fake import FakeTTSProvider
from tts_app.storage import Storage


class FailingProvider:
    name = "failing"

    def __init__(self, exc: Exception):
        self.exc = exc

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        raise self.exc
        yield AudioChunk(data=b"", mime_type="audio/mpeg", extension="mp3")


@pytest.mark.asyncio
async def test_generation_service_persists_segments_and_audio(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    service = GenerationService(
        storage=storage,
        provider=FakeTTSProvider(),
        broker=broker,
        audio_dir=test_settings.audio_dir,
        segment_max_chars=20,
    )

    generation_id = await service.create_from_text("Hello world. Second sentence.", title="Manual text")
    await service.run_generation(generation_id)

    detail = storage.get_generation(generation_id)

    assert detail["generation"]["status"] == "completed"
    assert len(detail["text_segments"]) == 2
    assert len(detail["audio_segments"]) == 2
    for audio in detail["audio_segments"]:
        assert test_settings.audio_dir in (test_settings.data_dir / audio["file_path"]).parents


@pytest.mark.asyncio
async def test_generation_service_writes_audio_under_custom_audio_dir(test_settings, tmp_path):
    audio_dir = tmp_path / "custom-audio"
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    service = GenerationService(
        storage=storage,
        provider=FakeTTSProvider(),
        broker=broker,
        audio_dir=audio_dir,
        segment_max_chars=20,
    )

    generation_id = await service.create_from_text("Hello world. Second sentence.", title="Manual text")
    await service.run_generation(generation_id)

    detail = storage.get_generation(generation_id)

    assert len(detail["audio_segments"]) == 2
    for audio in detail["audio_segments"]:
        audio_path = audio_dir.parent / audio["file_path"]
        assert audio_path.is_file()
        assert audio_dir in audio_path.parents


@pytest.mark.asyncio
async def test_generation_service_marks_active_segment_failed_on_provider_error(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    service = GenerationService(
        storage=storage,
        provider=FailingProvider(ProviderError("bad voice")),
        broker=broker,
        audio_dir=test_settings.audio_dir,
        segment_max_chars=20,
    )

    generation_id = await service.create_from_text("Hello world.", title="Manual text")
    await service.run_generation(generation_id)

    detail = storage.get_generation(generation_id)
    events = []
    async for event in broker.subscribe(generation_id):
        events.append(event)
        if event["type"] == "generation_failed":
            break

    assert detail["generation"]["status"] == "failed"
    assert detail["generation"]["error"] == "bad voice"
    assert detail["text_segments"][0]["status"] == "failed"
    assert events[-1] == {"type": "generation_failed", "generation_id": generation_id, "error": "bad voice"}


@pytest.mark.asyncio
async def test_generation_service_marks_active_segment_failed_on_non_provider_error(test_settings, tmp_path):
    audio_dir = tmp_path / "audio-file"
    audio_dir.write_text("not a directory", encoding="utf-8")
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    service = GenerationService(
        storage=storage,
        provider=FakeTTSProvider(),
        broker=broker,
        audio_dir=audio_dir,
        segment_max_chars=20,
    )

    generation_id = await service.create_from_text("Hello world.", title="Manual text")
    await service.run_generation(generation_id)

    detail = storage.get_generation(generation_id)

    assert detail["generation"]["status"] == "failed"
    assert "Not a directory" in detail["generation"]["error"]
    assert detail["text_segments"][0]["status"] == "failed"
    assert detail["audio_segments"] == []


@pytest.mark.asyncio
async def test_event_broker_replays_generation_events(test_settings):
    broker = EventBroker()
    await broker.publish(7, {"type": "segment_completed", "segment_index": 0})

    events = []
    async for event in broker.subscribe(7):
        events.append(event)
        break

    assert events == [{"type": "segment_completed", "segment_index": 0}]


@pytest.mark.asyncio
async def test_event_broker_does_not_duplicate_events_published_during_replay(test_settings):
    broker = EventBroker()
    old_event = {"type": "segment_completed", "segment_index": 0}
    new_event = {"type": "segment_completed", "segment_index": 1}
    await broker.publish(7, old_event)

    subscription = broker.subscribe(7)
    assert await anext(subscription) == old_event
    await broker.publish(7, new_event)

    assert await anext(subscription) == new_event
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(anext(subscription), timeout=0.01)
    await subscription.aclose()
