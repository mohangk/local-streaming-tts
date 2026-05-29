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


def test_ocr_draft_round_trip_with_ordered_images(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()

    draft_id = storage.create_ocr_draft(
        ocr_model="qwen-vl-ocr",
        language="zh",
        status="completed",
    )
    first_image_id = storage.create_ocr_draft_image(
        draft_id,
        position=0,
        image_path="images/1/1/source.jpg",
        original_filename="page-1.jpg",
        mime_type="image/jpeg",
        byte_size=123,
        extracted_text="你好",
        status="completed",
    )
    second_image_id = storage.create_ocr_draft_image(
        draft_id,
        position=1,
        image_path="images/1/2/source.jpg",
        original_filename="page-2.jpg",
        mime_type="image/jpeg",
        byte_size=456,
        extracted_text="ni hao",
        status="completed",
    )

    draft = storage.get_ocr_draft(draft_id)
    assert draft["id"] == draft_id
    assert draft["language"] == "zh"
    assert [image["id"] for image in draft["images"]] == [first_image_id, second_image_id]
    assert [image["extracted_text"] for image in draft["images"]] == ["你好", "ni hao"]
    assert draft["combined_text"] == ""
    assert storage.list_ocr_drafts()[0]["id"] == draft_id


def test_ocr_draft_combined_text_is_persisted_separately_from_images(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")
    image_id = storage.create_ocr_draft_image(
        draft_id, 0, "images/1/1/source.png", None, "image/png", 10, "raw text", "completed"
    )

    storage.update_ocr_draft(draft_id, language="en", combined_text="Reviewed text.", image_texts={})

    draft = storage.get_ocr_draft(draft_id)
    assert draft["combined_text"] == "Reviewed text."
    assert draft["images"][0]["id"] == image_id
    assert draft["images"][0]["extracted_text"] == "raw text"


def test_rebuild_ocr_draft_combined_text_uses_image_text_in_order(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("fake-ocr", "en", "partial_failed")
    storage.create_ocr_draft_image(draft_id, 0, "images/1/1/source.png", None, "image/png", 10, "first", "completed")
    storage.create_ocr_draft_image(draft_id, 1, "images/1/2/source.png", None, "image/png", 10, "", "failed", "bad image")
    storage.create_ocr_draft_image(draft_id, 2, "images/1/3/source.png", None, "image/png", 10, "third", "completed")
    storage.update_ocr_draft(draft_id, language="en", combined_text="Edited text.", image_texts={})

    storage.rebuild_ocr_draft_combined_text(draft_id)

    assert storage.get_ocr_draft(draft_id)["combined_text"] == "first\n\nthird"


def test_init_schema_migrates_existing_ocr_drafts_to_combined_text(test_settings):
    test_settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(test_settings.db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE ocr_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ocr_model TEXT NOT NULL,
                language TEXT NOT NULL CHECK (language IN ('en', 'zh')),
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'partial_failed', 'failed')),
                error TEXT,
                linked_generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE ocr_draft_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ocr_draft_id INTEGER NOT NULL REFERENCES ocr_drafts(id) ON DELETE CASCADE,
                position INTEGER NOT NULL CHECK (position >= 0),
                image_path TEXT NOT NULL,
                original_filename TEXT,
                mime_type TEXT NOT NULL,
                byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                extracted_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ocr_draft_id, position)
            );
            """
        )
        conn.execute("INSERT INTO ocr_drafts (ocr_model, language, status) VALUES ('fake-ocr', 'en', 'completed')")
        draft_id = conn.execute("SELECT id FROM ocr_drafts").fetchone()[0]
        conn.execute(
            """
            INSERT INTO ocr_draft_images
                (ocr_draft_id, position, image_path, mime_type, byte_size, extracted_text, status)
            VALUES (?, 0, 'images/1/1/source.png', 'image/png', 10, 'old first', 'completed')
            """,
            (draft_id,),
        )
        conn.execute(
            """
            INSERT INTO ocr_draft_images
                (ocr_draft_id, position, image_path, mime_type, byte_size, extracted_text, status)
            VALUES (?, 1, 'images/1/2/source.png', 'image/png', 10, 'old second', 'completed')
            """,
            (draft_id,),
        )
        conn.commit()
    finally:
        conn.close()

    storage = Storage(test_settings.db_path)
    storage.init_schema()

    assert storage.get_ocr_draft(draft_id)["combined_text"] == "old first\n\nold second"


def test_update_ocr_draft_image_text_and_language(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")
    image_id = storage.create_ocr_draft_image(
        draft_id, 0, "images/1/1/source.png", None, "image/png", 10, "raw", "completed"
    )

    storage.update_ocr_draft(draft_id, language="zh", combined_text="reviewed text", image_texts={image_id: "raw update"})

    draft = storage.get_ocr_draft(draft_id)
    assert draft["combined_text"] == "reviewed text"
    assert draft["images"][0]["extracted_text"] == "raw update"
    assert draft["language"] == "zh"


def test_init_schema_resets_incompatible_ocr_tables(test_settings):
    test_settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(test_settings.db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL CHECK (source_type IN ('text', 'url', 'image')),
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
            );

            CREATE TABLE ocr_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_path TEXT NOT NULL,
                original_filename TEXT,
                mime_type TEXT NOT NULL,
                byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                ocr_model TEXT NOT NULL,
                language TEXT NOT NULL,
                extracted_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                error TEXT,
                linked_generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE ocr_draft_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ocr_draft_id INTEGER NOT NULL REFERENCES "ocr_drafts_old"(id) ON DELETE CASCADE,
                position INTEGER NOT NULL CHECK (position >= 0),
                image_path TEXT NOT NULL,
                original_filename TEXT,
                mime_type TEXT NOT NULL,
                byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                extracted_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ocr_draft_id, position)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO ocr_drafts
                (image_path, original_filename, mime_type, byte_size, ocr_model, language, extracted_text, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("images/1/source.png", "valid.png", "image/png", 10, "fake-ocr", "zh", "valid", "completed"),
        )
        conn.commit()
    finally:
        conn.close()

    storage = Storage(test_settings.db_path)
    storage.init_schema()

    assert storage.list_ocr_drafts() == []

    with storage.connection() as conn:
        table_sql = conn.execute(
            """
            SELECT group_concat(sql, '\n')
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('ocr_drafts', 'ocr_draft_images')
            """
        ).fetchone()[0]
        assert "ocr_drafts_old" not in table_sql

        image_foreign_keys = conn.execute("PRAGMA foreign_key_list(ocr_draft_images)").fetchall()
        assert {row["table"] for row in image_foreign_keys if row["from"] == "ocr_draft_id"} == {"ocr_drafts"}

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO ocr_drafts
                    (ocr_model, language, status)
                VALUES (?, ?, ?)
                """,
                ("fake-ocr", "fr", "completed"),
            )


def test_invalid_ocr_draft_language_is_rejected(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")

    with pytest.raises(ValueError, match="ocr draft language must be en or zh"):
        storage.create_ocr_draft("fake-ocr", "fr", "completed")

    with pytest.raises(ValueError, match="ocr draft language must be en or zh"):
        storage.update_ocr_draft(draft_id, language="fr", combined_text="", image_texts={})


def test_init_schema_marks_empty_running_ocr_drafts_failed(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    with storage.connection() as conn:
        conn.execute(
            """
            INSERT INTO ocr_drafts (ocr_model, language, status)
            VALUES ('fake-ocr', 'en', 'running')
            """
        )

    storage.init_schema()

    draft = storage.list_ocr_drafts()[0]
    assert draft["status"] == "failed"
    assert draft["error"] == "OCR draft has no images"


def test_delete_ocr_draft_image_reorders_remaining_images(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")
    first_id = storage.create_ocr_draft_image(draft_id, 0, "images/1/1/source.png", None, "image/png", 10, "one", "completed")
    second_id = storage.create_ocr_draft_image(draft_id, 1, "images/1/2/source.png", None, "image/png", 10, "two", "completed")

    deleted = storage.delete_ocr_draft_image(draft_id, first_id)

    draft = storage.get_ocr_draft(draft_id)
    assert deleted["id"] == first_id
    assert [(image["id"], image["position"]) for image in draft["images"]] == [(second_id, 0)]


def test_delete_unlinked_ocr_draft(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")
    storage.create_ocr_draft_image(draft_id, 0, "images/1/1/source.png", None, "image/png", 10, "text", "completed")

    storage.delete_ocr_draft(draft_id)

    with pytest.raises(KeyError, match=f"ocr draft {draft_id} not found"):
        storage.get_ocr_draft(draft_id)


def test_delete_linked_ocr_draft_is_blocked(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")
    generation_id = storage.create_generation("image", "Image text", None, "text", "fake", "Test", {"ocr_draft_id": draft_id})
    storage.link_ocr_draft_generation(draft_id, generation_id)

    with pytest.raises(ValueError, match="linked to generation"):
        storage.delete_ocr_draft(draft_id)


def test_one_ocr_draft_can_link_to_a_generation(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    first_draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")
    second_draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")
    generation_id = storage.create_generation("image", "Image text", None, "text", "fake", "Test", {"ocr_draft_id": first_draft_id})
    storage.link_ocr_draft_generation(first_draft_id, generation_id)

    with pytest.raises(sqlite3.IntegrityError):
        storage.link_ocr_draft_generation(second_draft_id, generation_id)


def test_link_ocr_draft_generation_rejects_second_link_without_overwriting(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    draft_id = storage.create_ocr_draft("fake-ocr", "en", "completed")
    first_generation_id = storage.create_generation(
        "image", "Image text", None, "text", "fake", "Test", {"ocr_draft_id": draft_id}
    )
    second_generation_id = storage.create_generation(
        "image", "Other image text", None, "other text", "fake", "Test", {"ocr_draft_id": draft_id}
    )
    storage.link_ocr_draft_generation(draft_id, first_generation_id)

    with pytest.raises(ValueError, match="ocr draft is already linked to generation"):
        storage.link_ocr_draft_generation(draft_id, second_generation_id)

    assert storage.get_ocr_draft(draft_id)["linked_generation_id"] == first_generation_id


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
