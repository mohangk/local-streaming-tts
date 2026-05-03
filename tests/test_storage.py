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
