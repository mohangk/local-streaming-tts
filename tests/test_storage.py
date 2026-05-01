from __future__ import annotations

import sqlite3

import pytest

from tts_app.storage import Storage


def test_create_generation_persists_full_text_and_segments(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    generation_id = storage.create_generation(
        source_type="text",
        title="Manual text",
        url=None,
        full_text="First sentence. Second sentence.",
        provider="fake",
        voice="Test",
        settings={"format": "mp3"},
    )
    storage.create_text_segments(generation_id, ["First sentence.", "Second sentence."])

    detail = storage.get_generation(generation_id)

    assert detail["generation"]["id"] == generation_id
    assert detail["generation"]["full_text"] == "First sentence. Second sentence."
    assert [segment["text"] for segment in detail["text_segments"]] == [
        "First sentence.",
        "Second sentence.",
    ]


def test_audio_segment_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    generation_id = storage.create_generation(
        source_type="text",
        title="Manual text",
        url=None,
        full_text="Hello.",
        provider="fake",
        voice="Test",
        settings={},
    )
    text_segment_id = storage.create_text_segments(generation_id, ["Hello."])[0]
    storage.record_audio_segment(
        generation_id=generation_id,
        text_segment_id=text_segment_id,
        segment_index=0,
        file_path="data/audio/abc/segment-0001.mp3",
        mime_type="audio/mpeg",
        duration_ms=None,
        byte_size=12,
        status="completed",
        error=None,
    )

    detail = storage.get_generation(generation_id)

    assert detail["audio_segments"][0]["file_path"].endswith("segment-0001.mp3")
    assert detail["audio_segments"][0]["status"] == "completed"


def test_list_generations_orders_newest_first(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    first = storage.create_generation("text", "First", None, "A", "fake", "Test", {})
    second = storage.create_generation("text", "Second", None, "B", "fake", "Test", {})

    rows = storage.list_generations()

    assert [row["id"] for row in rows] == [second, first]


def test_invalid_source_type_is_rejected_by_sqlite(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    with pytest.raises(sqlite3.IntegrityError):
        storage.create_generation("file", "Invalid", None, "A", "fake", "Test", {})


def test_invalid_generation_status_is_rejected_by_sqlite(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})

    with pytest.raises(sqlite3.IntegrityError):
        storage.update_generation_status(generation_id, "paused")


def test_invalid_text_segment_status_is_rejected_by_sqlite(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})
    text_segment_id = storage.create_text_segments(generation_id, ["A"])[0]

    with pytest.raises(sqlite3.IntegrityError):
        storage.update_text_segment_status(text_segment_id, "paused")


def test_invalid_audio_segment_status_is_rejected_by_sqlite(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})
    text_segment_id = storage.create_text_segments(generation_id, ["A"])[0]

    with pytest.raises(sqlite3.IntegrityError):
        storage.record_audio_segment(
            generation_id=generation_id,
            text_segment_id=text_segment_id,
            segment_index=0,
            file_path="data/audio/abc/segment-0001.mp3",
            mime_type="audio/mpeg",
            duration_ms=None,
            byte_size=12,
            status="paused",
            error=None,
        )


def test_cross_generation_audio_segment_insertion_is_rejected(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    first_generation_id = storage.create_generation("text", "First", None, "A", "fake", "Test", {})
    second_generation_id = storage.create_generation("text", "Second", None, "B", "fake", "Test", {})
    first_text_segment_id = storage.create_text_segments(first_generation_id, ["A"])[0]

    with pytest.raises(sqlite3.IntegrityError):
        storage.record_audio_segment(
            generation_id=second_generation_id,
            text_segment_id=first_text_segment_id,
            segment_index=0,
            file_path="data/audio/abc/segment-0001.mp3",
            mime_type="audio/mpeg",
            duration_ms=None,
            byte_size=12,
            status="completed",
            error=None,
        )


def test_updating_missing_generation_raises_key_error(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    with pytest.raises(KeyError, match="generation 999 not found"):
        storage.update_generation_status(999, "completed")


def test_updating_missing_text_segment_raises_key_error(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    with pytest.raises(KeyError, match="text segment 999 not found"):
        storage.update_text_segment_status(999, "completed")
