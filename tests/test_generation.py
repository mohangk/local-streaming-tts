from __future__ import annotations

import pytest

from tts_app.events import EventBroker
from tts_app.generation import GenerationService
from tts_app.providers.fake import FakeTTSProvider
from tts_app.storage import Storage


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
async def test_event_broker_replays_generation_events(test_settings):
    broker = EventBroker()
    await broker.publish(7, {"type": "segment_completed", "segment_index": 0})

    events = []
    async for event in broker.subscribe(7):
        events.append(event)
        break

    assert events == [{"type": "segment_completed", "segment_index": 0}]
