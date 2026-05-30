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


def test_list_completed_audio_segments_for_stitching(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A B C", "fake", "Test", {})
    segment_ids = storage.create_text_segments(generation_id, ["A", "B", "C"])
    first_audio_id = storage.record_audio_segment(
        generation_id,
        segment_ids[0],
        0,
        "audio/1/segment-0001.mp3",
        "audio/mpeg",
        None,
        3,
        "completed",
        None,
    )
    second_audio_id = storage.record_audio_segment(
        generation_id,
        segment_ids[1],
        1,
        "audio/1/segment-0002.mp3",
        "audio/mpeg",
        None,
        4,
        "completed",
        None,
    )
    running_audio_id = storage.record_audio_segment(
        generation_id,
        segment_ids[2],
        2,
        "audio/1/segment-0003.mp3",
        "audio/mpeg",
        None,
        5,
        "running",
        None,
    )

    rows = storage.list_completed_audio_segments_for_stitching(generation_id)

    assert [row["id"] for row in rows] == [first_audio_id, second_audio_id]
    assert [row["segment_index"] for row in rows] == [0, 1]
    assert running_audio_id not in [row["id"] for row in rows]


def test_continuous_audio_artifact_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})

    storage.upsert_continuous_audio_artifact(
        generation_id,
        file_path=f"audio/{generation_id}/full.mp3",
        mime_type="audio/mpeg",
        status="building",
        appended_through_segment_index=0,
        byte_size=123,
        error=None,
    )

    artifact = storage.get_continuous_audio_artifact(generation_id)

    assert artifact == {
        "generation_id": generation_id,
        "file_path": f"audio/{generation_id}/full.mp3",
        "mime_type": "audio/mpeg",
        "status": "building",
        "appended_through_segment_index": 0,
        "byte_size": 123,
        "error": None,
    }


def test_delete_generation_cascades_continuous_audio_artifact(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})
    storage.upsert_continuous_audio_artifact(
        generation_id,
        file_path=f"audio/{generation_id}/full.mp3",
        mime_type="audio/mpeg",
        status="completed",
        appended_through_segment_index=0,
        byte_size=123,
        error=None,
    )

    storage.delete_generation(generation_id)

    with pytest.raises(KeyError, match=f"continuous audio artifact for generation {generation_id} not found"):
        storage.get_continuous_audio_artifact(generation_id)


def test_generation_progress_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation(
        source_type="text",
        title="Manual text",
        url=None,
        full_text="One. Two. Three. Four.",
        provider="fake",
        voice="Test",
        settings={},
    )
    storage.create_text_segments(generation_id, ["One.", "Two.", "Three.", "Four."])

    storage.update_generation_progress(generation_id, segment_index=1)

    detail = storage.get_generation(generation_id)

    assert detail["generation"]["last_segment_index"] == 1
    assert detail["generation"]["progress_percent"] == 50

def test_generation_progress_completed_sets_100_percent(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "One. Two.", "fake", "Test", {})
    storage.create_text_segments(generation_id, ["One.", "Two."])

    storage.update_generation_progress(generation_id, segment_index=1, completed=True)

    assert storage.get_generation(generation_id)["generation"]["progress_percent"] == 100


def test_playback_telemetry_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A B", "fake", "Test", {})
    segment_ids = storage.create_text_segments(generation_id, ["A", "B"])
    audio_id = storage.record_audio_segment(
        generation_id,
        segment_ids[0],
        0,
        "audio/1/0.mp3",
        "audio/mpeg",
        10,
        123,
        "completed",
        None,
    )

    stored = storage.record_playback_telemetry(
        generation_id,
        "session-1710000000000-abc123",
        [
            {
                "event_name": "audio_waiting",
                "segment_index": 0,
                "audio_segment_id": audio_id,
                "payload": {"visibility_state": "hidden", "audio_paused": False},
            }
        ],
    )

    events = storage.list_playback_telemetry_events(generation_id)
    assert stored == 1
    assert len(events) == 1
    assert events[0]["generation_id"] == generation_id
    assert events[0]["session_id"] == "session-1710000000000-abc123"
    assert events[0]["event_name"] == "audio_waiting"
    assert events[0]["segment_index"] == 0
    assert events[0]["audio_segment_id"] == audio_id
    assert events[0]["payload"] == {"visibility_state": "hidden", "audio_paused": False}
    assert events[0]["created_at"]


def test_playback_telemetry_requires_existing_generation(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    with pytest.raises(KeyError):
        storage.record_playback_telemetry(
            999,
            "session-1710000000000-abc123",
            [{"event_name": "audio_play", "payload": {}}],
        )


def test_playback_telemetry_requires_audio_segment_from_same_generation(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    first_generation_id = storage.create_generation("text", "First", None, "A", "fake", "Test", {})
    second_generation_id = storage.create_generation("text", "Second", None, "B", "fake", "Test", {})
    segment_ids = storage.create_text_segments(second_generation_id, ["B"])
    audio_id = storage.record_audio_segment(
        second_generation_id,
        segment_ids[0],
        0,
        "audio/2/0.mp3",
        "audio/mpeg",
        10,
        123,
        "completed",
        None,
    )

    with pytest.raises(ValueError, match=f"audio segment does not belong to generation {first_generation_id}"):
        storage.record_playback_telemetry(
            first_generation_id,
            "session-1710000000000-abc123",
            [{"event_name": "audio_play", "audio_segment_id": audio_id, "payload": {}}],
        )


def test_playback_telemetry_requires_segment_from_same_generation(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})
    storage.create_text_segments(generation_id, ["A"])

    with pytest.raises(ValueError, match="playback telemetry segment index does not belong to generation"):
        storage.record_playback_telemetry(
            generation_id,
            "session-1710000000000-abc123",
            [{"event_name": "audio_play", "segment_index": 1, "payload": {}}],
        )


def test_playback_telemetry_requires_audio_segment_index_match(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A B", "fake", "Test", {})
    segment_ids = storage.create_text_segments(generation_id, ["A", "B"])
    audio_id = storage.record_audio_segment(
        generation_id,
        segment_ids[0],
        0,
        "audio/1/0.mp3",
        "audio/mpeg",
        10,
        123,
        "completed",
        None,
    )

    with pytest.raises(ValueError, match="playback telemetry audio segment does not match segment index"):
        storage.record_playback_telemetry(
            generation_id,
            "session-1710000000000-abc123",
            [{"event_name": "audio_play", "segment_index": 1, "audio_segment_id": audio_id, "payload": {}}],
        )


def test_playback_telemetry_drops_unknown_payload_keys(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "Secret article text", "fake", "Test", {})

    storage.record_playback_telemetry(
        generation_id,
        "session-1710000000000-abc123",
        [
            {
                "event_name": "audio_play",
                "payload": {
                    "audio_paused": False,
                    "article_text": "Secret article text",
                    "url": "https://example.test/private",
                    "provider_response": {"raw": "content"},
                    "unexpected": "value",
                },
            }
        ],
    )

    events = storage.list_playback_telemetry_events(generation_id)
    assert events[0]["payload"] == {"audio_paused": False}


def test_playback_telemetry_drops_invalid_allowed_payload_values(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "Secret article text", "fake", "Test", {})

    storage.record_playback_telemetry(
        generation_id,
        "session-1710000000000-abc123",
        [
            {
                "event_name": "audio_play",
                "payload": {
                    "audio_paused": "Secret article text",
                    "audio_current_time": "Secret article text",
                    "type": "Secret article text",
                    "visibility_state": "Secret article text",
                    "platform": "Secret article text",
                    "user_agent": "Secret article text",
                    "wake_lock_active": True,
                },
            }
        ],
    )

    events = storage.list_playback_telemetry_events(generation_id)
    assert events[0]["payload"] == {"wake_lock_active": True}


def test_playback_telemetry_rejects_unknown_event_names(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})

    with pytest.raises(ValueError, match="unsupported playback telemetry event"):
        storage.record_playback_telemetry(
            generation_id,
            "session-1710000000000-abc123",
            [{"event_name": "Secret article text", "payload": {}}],
        )


def test_playback_telemetry_rejects_free_form_session_id(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})

    with pytest.raises(ValueError, match="unsupported playback telemetry session id"):
        storage.record_playback_telemetry(
            generation_id,
            "Secret article text",
            [{"event_name": "audio_play", "payload": {}}],
        )


def test_playback_telemetry_retains_newest_events_per_generation(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})
    storage.create_text_segments(generation_id, [f"Segment {index}" for index in range(1005)])

    storage.record_playback_telemetry(
        generation_id,
        "session-1710000000000-abc123",
        [
            {"event_name": "audio_play", "segment_index": index, "payload": {"audio_current_time": index}}
            for index in range(1005)
        ],
    )

    events = storage.list_playback_telemetry_events(generation_id)
    assert len(events) == 1000
    assert events[0]["segment_index"] == 5
    assert events[-1]["segment_index"] == 1004


def test_delete_generation_cascades_playback_telemetry(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})
    storage.record_playback_telemetry(
        generation_id,
        "session-1710000000000-abc123",
        [{"event_name": "audio_play", "payload": {}}],
    )

    storage.delete_generation(generation_id)

    assert storage.list_playback_telemetry_events(generation_id) == []


def test_delete_generation_cascades_segments(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "Hello.", "fake", "Test", {})
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

    storage.delete_generation(generation_id)

    assert storage.list_generations() == []
    with pytest.raises(KeyError, match=f"generation {generation_id} not found"):
        storage.get_generation(generation_id)

def test_list_generations_orders_newest_first(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    first = storage.create_generation("text", "First", None, "A", "fake", "Test", {})
    second = storage.create_generation("text", "Second", None, "B", "fake", "Test", {})

    rows = storage.list_generations()

    assert [row["id"] for row in rows] == [second, first]

def test_list_generations_includes_settings_and_progress(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation(
        "url",
        "Page",
        "https://example.test/page",
        "Text",
        "fake",
        "Jennifer",
        {"speed": 1.25},
    )
    storage.create_text_segments(generation_id, ["Text"])
    storage.update_generation_progress(generation_id, segment_index=0)

    row = storage.list_generations()[0]

    assert row["url"] == "https://example.test/page"
    assert row["voice"] == "Jennifer"
    assert row["settings"]["speed"] == 1.25
    assert row["progress_percent"] == 100

def test_init_schema_migrates_existing_generation_progress_columns(test_settings):
    test_settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(test_settings.db_path)
    try:
        conn.execute(
            """
            CREATE TABLE generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                full_text TEXT NOT NULL,
                provider TEXT NOT NULL,
                voice TEXT NOT NULL,
                settings_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    Storage(test_settings.db_path).init_schema()

    conn = sqlite3.connect(test_settings.db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(generations)").fetchall()}
    finally:
        conn.close()

    assert "last_segment_index" in columns
    assert "progress_percent" in columns

def test_init_schema_migrates_existing_generation_source_type_check_for_image(test_settings):
    test_settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(test_settings.db_path)
    try:
        conn.execute(
            """
            CREATE TABLE generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL CHECK (source_type IN ('text', 'url')),
                title TEXT NOT NULL,
                url TEXT,
                full_text TEXT NOT NULL,
                provider TEXT NOT NULL,
                voice TEXT NOT NULL,
                settings_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                error TEXT,
                last_segment_index INTEGER NOT NULL DEFAULT 0 CHECK (last_segment_index >= 0),
                progress_percent INTEGER NOT NULL DEFAULT 0 CHECK (progress_percent >= 0 AND progress_percent <= 100),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    storage = Storage(test_settings.db_path)
    storage.init_schema()

    generation_id = storage.create_generation("image", "Image text", None, "OCR text", "fake", "Test", {})

    assert storage.get_generation(generation_id)["generation"]["source_type"] == "image"

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

def test_audio_segment_index_must_match_text_segment_index(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A B", "fake", "Test", {})
    first_text_segment_id = storage.create_text_segments(generation_id, ["A", "B"])[0]

    with pytest.raises(sqlite3.IntegrityError):
        storage.record_audio_segment(
            generation_id=generation_id,
            text_segment_id=first_text_segment_id,
            segment_index=1,
            file_path="data/audio/abc/segment-0002.mp3",
            mime_type="audio/mpeg",
            duration_ms=None,
            byte_size=12,
            status="completed",
            error=None,
        )

def test_negative_text_segment_index_is_rejected(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})

    with pytest.raises(sqlite3.IntegrityError):
        with storage.connection() as conn:
            conn.execute(
                """
                INSERT INTO text_segments (generation_id, segment_index, text, status)
                VALUES (?, -1, ?, 'queued')
                """,
                (generation_id, "A"),
            )

def test_negative_audio_segment_index_is_rejected(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})
    text_segment_id = storage.create_text_segments(generation_id, ["A"])[0]

    with pytest.raises(sqlite3.IntegrityError):
        storage.record_audio_segment(
            generation_id=generation_id,
            text_segment_id=text_segment_id,
            segment_index=-1,
            file_path="data/audio/abc/segment-0001.mp3",
            mime_type="audio/mpeg",
            duration_ms=None,
            byte_size=12,
            status="completed",
            error=None,
        )

def test_negative_audio_duration_is_rejected(test_settings):
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
            duration_ms=-1,
            byte_size=12,
            status="completed",
            error=None,
        )

def test_negative_audio_byte_size_is_rejected(test_settings):
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
            byte_size=-1,
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

def test_voice_preference_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    storage.set_voice_preference("Cherry", "en", True)
    assert storage.list_voice_preferences() == {("Cherry", "en"): True}

    storage.set_voice_preference("Cherry", "en", False)
    assert storage.list_voice_preferences() == {("Cherry", "en"): False}

def test_voice_preferences_are_language_scoped(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    storage.set_voice_preference("Cherry", "en", True)
    storage.set_voice_preference("Cherry", "zh", False)

    assert storage.list_voice_preferences() == {
        ("Cherry", "en"): True,
        ("Cherry", "zh"): False,
    }

def test_init_schema_migrates_voice_preferences_to_english(test_settings):
    test_settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(test_settings.db_path)
    conn.execute(
        """
        CREATE TABLE voice_preferences (
            voice TEXT PRIMARY KEY,
            preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("INSERT INTO voice_preferences (voice, preferred) VALUES (?, ?)", ("Cherry", 1))
    conn.commit()
    conn.close()

    storage = Storage(test_settings.db_path)
    storage.init_schema()

    assert storage.list_voice_preferences() == {("Cherry", "en"): True}
