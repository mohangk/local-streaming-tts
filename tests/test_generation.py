from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

import pytest

from tts_app.events import EventBroker
from tts_app.continuous_audio import ContinuousAudioError
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


class CapturingProvider:
    name = "capturing"

    def __init__(self):
        self.options: list[TTSOptions] = []

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        self.options.append(options)
        yield AudioChunk(data=b"audio", mime_type="audio/mpeg", extension="mp3")


class FailingContinuousAudio:
    def ensure_appended(self, generation_id: int) -> dict[str, object]:
        raise ContinuousAudioError("stitch failed")


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
async def test_generation_service_builds_continuous_audio_artifact(test_settings):
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

    generation_id = await service.create_from_text("One sentence. Two sentence. Three sentence.", title="Manual text")
    await service.run_generation(generation_id)

    artifact = storage.get_continuous_audio_artifact(generation_id)
    full_path = test_settings.data_dir / artifact["file_path"]

    assert artifact["status"] == "completed"
    assert artifact["appended_through_segment_index"] == len(storage.get_generation(generation_id)["text_segments"]) - 1
    assert full_path.exists()
    assert artifact["byte_size"] == full_path.stat().st_size


@pytest.mark.asyncio
async def test_generation_service_treats_continuous_audio_failure_as_nonfatal(test_settings, caplog):
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
    service.continuous_audio = FailingContinuousAudio()

    with caplog.at_level(logging.ERROR, logger="tts_app.generation"):
        generation_id = await service.create_from_text("One sentence.", title="Manual text")
        await service.run_generation(generation_id)

    detail = storage.get_generation(generation_id)
    assert detail["generation"]["status"] == "completed"
    assert detail["text_segments"][0]["status"] == "completed"
    assert detail["audio_segments"][0]["status"] == "completed"
    assert any("continuous_audio_append_failed generation_id=" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_generation_service_logs_generation_lifecycle(test_settings, caplog):
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

    with caplog.at_level(logging.INFO, logger="tts_app.generation"):
        generation_id = await service.create_from_text("Hello world.", title="Manual text", voice="Jennifer")
        await service.run_generation(generation_id, voice="Jennifer", speed=1.25)

    messages = [record.getMessage() for record in caplog.records]
    assert any(f"generation_created generation_id={generation_id}" in message for message in messages)
    assert any(f"generation_started generation_id={generation_id}" in message for message in messages)
    assert any(f"generation_completed generation_id={generation_id}" in message for message in messages)
    assert any(f"segment_completed generation_id={generation_id} segment_index=0" in message for message in messages)


@pytest.mark.asyncio
async def test_generation_service_passes_speed_to_provider(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    provider = CapturingProvider()
    service = GenerationService(
        storage=storage,
        provider=provider,
        broker=broker,
        audio_dir=test_settings.audio_dir,
        segment_max_chars=20,
    )

    generation_id = await service.create_from_text("Hello world.", title="Manual text", voice="Jennifer")
    await service.run_generation(generation_id, voice="Jennifer", speed=1.25)

    assert provider.options == [TTSOptions(voice="Jennifer", speed=1.25)]


@pytest.mark.asyncio
async def test_generation_service_passes_language_to_provider(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    provider = CapturingProvider()
    service = GenerationService(
        storage=storage,
        provider=provider,
        broker=broker,
        audio_dir=test_settings.audio_dir,
        segment_max_chars=20,
    )

    generation_id = await service.create_from_text("你好。", title="Image text", source_type="image", voice="Cherry")
    await service.run_generation(generation_id, voice="Cherry", speed=1.0, language="Chinese")

    assert provider.options == [TTSOptions(voice="Cherry", speed=1.0, language="Chinese")]


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
async def test_generation_service_marks_active_segment_failed_on_provider_error(test_settings, caplog):
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
    with caplog.at_level(logging.ERROR, logger="tts_app.generation"):
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
    assert any(f"generation_failed generation_id={generation_id}" in record.getMessage() for record in caplog.records)


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
