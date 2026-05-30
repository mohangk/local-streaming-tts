from __future__ import annotations

import sqlite3

import pytest

from tts_app.storage import Storage


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

    with pytest.raises(ValueError, match="generation is already linked to an ocr draft"):
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
