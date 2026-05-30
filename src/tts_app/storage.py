from __future__ import annotations

import json
import math
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tts_app.models import SourceType, Status

PLAYBACK_TELEMETRY_RETENTION_LIMIT = 1000
PLAYBACK_TELEMETRY_SESSION_ID_RE = re.compile(
    r"^(?:"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
    r"|session-[0-9]{10,20}-[0-9a-f]{1,32}"
    r")$"
)
PLAYBACK_TELEMETRY_EVENT_NAMES = {
    "audio_ended",
    "audio_error",
    "audio_pause",
    "audio_play",
    "audio_stalled",
    "audio_suspend",
    "audio_waiting",
    "event_source_error",
    "generation_opened",
    "page_frozen",
    "page_hidden",
    "page_resumed",
    "page_shown",
    "playback_ended_action",
    "progress_save_attempted",
    "progress_save_failed",
    "progress_save_succeeded",
    "segment_play_attempted",
    "visibility_changed",
    "wake_lock_acquired",
    "wake_lock_failed",
    "wake_lock_released",
}
PLAYBACK_TELEMETRY_PAYLOAD_KEYS = {
    "audio_current_time",
    "audio_duration",
    "audio_ended",
    "audio_network_state",
    "audio_paused",
    "audio_ready_state",
    "autoplay",
    "completed",
    "continuous_playback",
    "document_hidden",
    "error_code",
    "event_source_ready_state",
    "last_segment_index",
    "platform",
    "progress_percent",
    "segmentIndex",
    "segment_index",
    "type",
    "user_agent",
    "visibility_state",
    "wake_lock_active",
}
PLAYBACK_TELEMETRY_BOOL_KEYS = {
    "audio_ended",
    "audio_paused",
    "autoplay",
    "completed",
    "continuous_playback",
    "document_hidden",
    "wake_lock_active",
}
PLAYBACK_TELEMETRY_FLOAT_KEYS = {
    "audio_current_time",
    "audio_duration",
}
PLAYBACK_TELEMETRY_INT_KEYS = {
    "audio_network_state",
    "audio_ready_state",
    "error_code",
    "event_source_ready_state",
    "last_segment_index",
    "progress_percent",
    "segmentIndex",
    "segment_index",
}
PLAYBACK_TELEMETRY_ENUM_VALUES = {
    "platform": {"android", "ios", "linux", "macos", "unknown", "windows"},
    "type": {"clear-sample", "complete", "play-next", "stop"},
    "user_agent": {"chrome", "edge", "firefox", "safari", "unknown"},
    "visibility_state": {"hidden", "prerender", "unknown", "visible"},
}


def validate_playback_telemetry_session_id(session_id: str) -> str:
    if not PLAYBACK_TELEMETRY_SESSION_ID_RE.fullmatch(session_id):
        raise ValueError("unsupported playback telemetry session id")
    return session_id


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS generations (
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

                CREATE TABLE IF NOT EXISTS text_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
                    text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(generation_id, id),
                    UNIQUE(generation_id, id, segment_index),
                    UNIQUE(generation_id, segment_index)
                );

                CREATE TABLE IF NOT EXISTS audio_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
                    text_segment_id INTEGER NOT NULL,
                    segment_index INTEGER NOT NULL CHECK (segment_index >= 0),
                    file_path TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
                    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
                    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (generation_id, text_segment_id, segment_index) REFERENCES text_segments(generation_id, id, segment_index) ON DELETE CASCADE,
                    UNIQUE(generation_id, segment_index)
                );

                CREATE TABLE IF NOT EXISTS playback_telemetry_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL,
                    event_name TEXT NOT NULL,
                    segment_index INTEGER CHECK (segment_index IS NULL OR segment_index >= 0),
                    audio_segment_id INTEGER REFERENCES audio_segments(id) ON DELETE SET NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_playback_telemetry_generation_id
                ON playback_telemetry_events(generation_id, id);

                CREATE INDEX IF NOT EXISTS idx_playback_telemetry_session_id
                ON playback_telemetry_events(session_id, id);

                CREATE TABLE IF NOT EXISTS voice_preferences (
                    voice TEXT NOT NULL,
                    language TEXT NOT NULL CHECK (language IN ('en', 'zh')),
                    preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (voice, language)
                );
                """
            )
            self._ensure_generation_source_type_allows_image(conn)
            self._ensure_generation_progress_columns(conn)
            self._drop_incompatible_ocr_tables(conn)
            self._create_ocr_tables(conn)
            self._ensure_ocr_draft_combined_text_column(conn)
            self._mark_empty_running_ocr_drafts_failed(conn)
            self._ensure_voice_preferences_language_key(conn)
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ocr_drafts_linked_generation_id
                ON ocr_drafts(linked_generation_id)
                WHERE linked_generation_id IS NOT NULL
                """
            )

    def _ensure_generation_source_type_allows_image(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'generations'
            """
        ).fetchone()
        if row is None or row["sql"] is None:
            return

        old_check = "source_type TEXT NOT NULL CHECK (source_type IN ('text', 'url'))"
        if old_check not in row["sql"]:
            return

        new_sql = row["sql"].replace(
            old_check,
            "source_type TEXT NOT NULL CHECK (source_type IN ('text', 'url', 'image'))",
        )
        schema_version = int(conn.execute("PRAGMA schema_version").fetchone()[0])
        try:
            conn.execute("PRAGMA writable_schema = ON")
            conn.execute(
                """
                UPDATE sqlite_master
                SET sql = ?
                WHERE type = 'table' AND name = 'generations'
                """,
                (new_sql,),
            )
            conn.execute(f"PRAGMA schema_version = {schema_version + 1}")
        finally:
            conn.execute("PRAGMA writable_schema = OFF")

    def _ensure_generation_progress_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(generations)").fetchall()}
        if "last_segment_index" not in columns:
            conn.execute("ALTER TABLE generations ADD COLUMN last_segment_index INTEGER NOT NULL DEFAULT 0")
        if "progress_percent" not in columns:
            conn.execute("ALTER TABLE generations ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0")

    def _create_ocr_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ocr_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ocr_model TEXT NOT NULL,
                language TEXT NOT NULL CHECK (language IN ('en', 'zh')),
                combined_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'partial_failed', 'failed')),
                error TEXT,
                linked_generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ocr_draft_images (
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

    def _ensure_ocr_draft_combined_text_column(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(ocr_drafts)").fetchall()}
        if "combined_text" in columns:
            return

        conn.execute("ALTER TABLE ocr_drafts ADD COLUMN combined_text TEXT NOT NULL DEFAULT ''")
        draft_ids = [
            int(row["id"])
            for row in conn.execute(
                """
                SELECT id FROM ocr_drafts
                ORDER BY id
                """
            ).fetchall()
        ]
        for draft_id in draft_ids:
            self._rebuild_ocr_draft_combined_text(conn, draft_id)

    def _drop_incompatible_ocr_tables(self, conn: sqlite3.Connection) -> None:
        if not self._ocr_tables_are_incompatible(conn):
            return

        conn.execute("DROP INDEX IF EXISTS idx_ocr_drafts_linked_generation_id")
        conn.execute("DROP TABLE IF EXISTS ocr_draft_images")
        conn.execute("DROP TABLE IF EXISTS ocr_drafts")

    def _ocr_tables_are_incompatible(self, conn: sqlite3.Connection) -> bool:
        draft_row = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'ocr_drafts'
            """
        ).fetchone()
        image_row = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'ocr_draft_images'
            """
        ).fetchone()
        if draft_row is None and image_row is None:
            return False
        if draft_row is None or image_row is None:
            return True

        draft_columns = {row["name"] for row in conn.execute("PRAGMA table_info(ocr_drafts)").fetchall()}
        image_columns = {row["name"] for row in conn.execute("PRAGMA table_info(ocr_draft_images)").fetchall()}
        required_draft_columns = {
            "id",
            "ocr_model",
            "language",
            "status",
            "error",
            "linked_generation_id",
            "created_at",
            "updated_at",
        }
        required_image_columns = {
            "id",
            "ocr_draft_id",
            "position",
            "image_path",
            "original_filename",
            "mime_type",
            "byte_size",
            "extracted_text",
            "status",
            "error",
            "created_at",
            "updated_at",
        }
        old_draft_columns = {"image_path", "original_filename", "mime_type", "byte_size", "extracted_text"}
        if not required_draft_columns.issubset(draft_columns):
            return True
        if draft_columns & old_draft_columns:
            return True
        if not required_image_columns.issubset(image_columns):
            return True

        fk_tables = {
            row["table"]
            for row in conn.execute("PRAGMA foreign_key_list(ocr_draft_images)").fetchall()
            if row["from"] == "ocr_draft_id"
        }
        return fk_tables != {"ocr_drafts"}

    def _validate_ocr_language(self, language: str) -> None:
        if language not in {"en", "zh"}:
            raise ValueError("ocr draft language must be en or zh")

    def _mark_empty_running_ocr_drafts_failed(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            UPDATE ocr_drafts
            SET status = 'failed',
                error = 'OCR draft has no images',
                updated_at = CURRENT_TIMESTAMP
            WHERE status IN ('queued', 'running')
              AND NOT EXISTS (
                  SELECT 1 FROM ocr_draft_images
                  WHERE ocr_draft_images.ocr_draft_id = ocr_drafts.id
              )
            """
        )

    def _validate_voice_language(self, language: str) -> None:
        if language not in {"en", "zh"}:
            raise ValueError("voice preference language must be en or zh")

    def _ensure_voice_preferences_language_key(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(voice_preferences)").fetchall()}
        if "language" in columns:
            return

        conn.execute("ALTER TABLE voice_preferences RENAME TO voice_preferences_old")
        conn.execute(
            """
            CREATE TABLE voice_preferences (
                voice TEXT NOT NULL,
                language TEXT NOT NULL CHECK (language IN ('en', 'zh')),
                preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (voice, language)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO voice_preferences (voice, language, preferred, updated_at)
            SELECT voice, 'en', preferred, updated_at
            FROM voice_preferences_old
            """
        )
        conn.execute("DROP TABLE voice_preferences_old")

    def create_generation(
        self,
        source_type: SourceType,
        title: str,
        url: str | None,
        full_text: str,
        provider: str,
        voice: str,
        settings: dict[str, Any],
    ) -> int:
        with self.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO generations
                    (source_type, title, url, full_text, provider, voice, settings_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
                """,
                (source_type, title, url, full_text, provider, voice, json.dumps(settings, sort_keys=True)),
            )
            return int(cur.lastrowid)

    def create_text_segments(self, generation_id: int, segments: list[str]) -> list[int]:
        ids: list[int] = []
        with self.connection() as conn:
            for index, text in enumerate(segments):
                cur = conn.execute(
                    """
                    INSERT INTO text_segments (generation_id, segment_index, text, status)
                    VALUES (?, ?, ?, 'queued')
                    """,
                    (generation_id, index, text),
                )
                ids.append(int(cur.lastrowid))
        return ids

    def update_generation_status(self, generation_id: int, status: Status, error: str | None = None) -> None:
        with self.connection() as conn:
            cur = conn.execute(
                """
                UPDATE generations
                SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error, generation_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"generation {generation_id} not found")

    def update_generation_progress(self, generation_id: int, segment_index: int, completed: bool = False) -> dict[str, int]:
        with self.connection() as conn:
            total_segments = conn.execute(
                "SELECT COUNT(*) FROM text_segments WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()[0]
            generation = conn.execute("SELECT id FROM generations WHERE id = ?", (generation_id,)).fetchone()
            if generation is None:
                raise KeyError(f"generation {generation_id} not found")

            if total_segments <= 0:
                last_segment_index = 0
                progress_percent = 0
            else:
                last_segment_index = min(max(int(segment_index), 0), total_segments - 1)
                progress_percent = 100 if completed else round(((last_segment_index + 1) / total_segments) * 100)
                progress_percent = min(max(progress_percent, 0), 100)

            conn.execute(
                """
                UPDATE generations
                SET last_segment_index = ?, progress_percent = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (last_segment_index, progress_percent, generation_id),
            )

        return {"last_segment_index": last_segment_index, "progress_percent": progress_percent}

    def record_playback_telemetry(self, generation_id: int, session_id: str, events: list[dict[str, Any]]) -> int:
        validate_playback_telemetry_session_id(session_id)
        with self.connection() as conn:
            generation = conn.execute("SELECT id FROM generations WHERE id = ?", (generation_id,)).fetchone()
            if generation is None:
                raise KeyError(f"generation {generation_id} not found")
            event_names = {str(event["event_name"]) for event in events}
            if not event_names.issubset(PLAYBACK_TELEMETRY_EVENT_NAMES):
                raise ValueError("unsupported playback telemetry event")

            audio_segment_ids = {
                int(event["audio_segment_id"])
                for event in events
                if event.get("audio_segment_id") is not None
            }
            if audio_segment_ids:
                placeholders = ",".join("?" for _ in audio_segment_ids)
                rows = conn.execute(
                    f"""
                    SELECT id
                    FROM audio_segments
                    WHERE generation_id = ? AND id IN ({placeholders})
                    """,
                    (generation_id, *audio_segment_ids),
                ).fetchall()
                found_ids = {int(row["id"]) for row in rows}
                if found_ids != audio_segment_ids:
                    raise KeyError(f"audio segment does not belong to generation {generation_id}")

            rows = [
                (
                    generation_id,
                    session_id,
                    str(event["event_name"]),
                    event.get("segment_index"),
                    event.get("audio_segment_id"),
                    json.dumps(self._playback_telemetry_payload(event.get("payload", {}))),
                )
                for event in events
            ]
            conn.executemany(
                """
                INSERT INTO playback_telemetry_events
                    (generation_id, session_id, event_name, segment_index, audio_segment_id, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
            conn.execute(
                """
                DELETE FROM playback_telemetry_events
                WHERE generation_id = ?
                  AND id NOT IN (
                    SELECT id
                    FROM playback_telemetry_events
                    WHERE generation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                  )
                """,
                (generation_id, generation_id, PLAYBACK_TELEMETRY_RETENTION_LIMIT),
            )
        return len(events)

    def _playback_telemetry_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in payload.items():
            if key not in PLAYBACK_TELEMETRY_PAYLOAD_KEYS:
                continue
            if key in PLAYBACK_TELEMETRY_BOOL_KEYS:
                if isinstance(value, bool):
                    sanitized[key] = value
                continue
            if key in PLAYBACK_TELEMETRY_INT_KEYS:
                if isinstance(value, int) and not isinstance(value, bool):
                    sanitized[key] = value
                continue
            if key in PLAYBACK_TELEMETRY_FLOAT_KEYS:
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                    sanitized[key] = value
                continue
            allowed_values = PLAYBACK_TELEMETRY_ENUM_VALUES.get(key)
            if allowed_values is not None and isinstance(value, str) and value in allowed_values:
                sanitized[key] = value
        return sanitized

    def list_playback_telemetry_events(self, generation_id: int) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, generation_id, session_id, event_name, segment_index, audio_segment_id, payload_json, created_at
                FROM playback_telemetry_events
                WHERE generation_id = ?
                ORDER BY id
                """,
                (generation_id,),
            ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["payload"] = json.loads(event.pop("payload_json"))
            events.append(event)
        return events

    def update_text_segment_status(self, text_segment_id: int, status: Status) -> None:
        with self.connection() as conn:
            cur = conn.execute(
                """
                UPDATE text_segments
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, text_segment_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"text segment {text_segment_id} not found")

    def record_audio_segment(
        self,
        generation_id: int,
        text_segment_id: int,
        segment_index: int,
        file_path: str,
        mime_type: str,
        duration_ms: int | None,
        byte_size: int,
        status: Status,
        error: str | None,
    ) -> int:
        with self.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO audio_segments
                    (generation_id, text_segment_id, segment_index, file_path, mime_type, duration_ms, byte_size, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (generation_id, text_segment_id, segment_index, file_path, mime_type, duration_ms, byte_size, status, error),
            )
            return int(cur.lastrowid)

    def list_generations(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, source_type, title, url, substr(full_text, 1, 180) AS text_preview,
                       provider, voice, settings_json, status, error, last_segment_index,
                       progress_percent, created_at, updated_at
                FROM generations
                ORDER BY datetime(created_at) DESC, id DESC
                """
            ).fetchall()
        generations = []
        for row in rows:
            generation = dict(row)
            generation["settings"] = json.loads(generation.pop("settings_json"))
            generations.append(generation)
        return generations

    def get_generation(self, generation_id: int) -> dict[str, Any]:
        with self.connection() as conn:
            generation = conn.execute(
                "SELECT * FROM generations WHERE id = ?",
                (generation_id,),
            ).fetchone()
            if generation is None:
                raise KeyError(f"generation {generation_id} not found")

            text_segments = conn.execute(
                "SELECT * FROM text_segments WHERE generation_id = ? ORDER BY segment_index",
                (generation_id,),
            ).fetchall()
            audio_segments = conn.execute(
                "SELECT * FROM audio_segments WHERE generation_id = ? ORDER BY segment_index",
                (generation_id,),
            ).fetchall()

        generation_dict = dict(generation)
        generation_dict["settings"] = json.loads(generation_dict.pop("settings_json"))
        return {
            "generation": generation_dict,
            "text_segments": [dict(row) for row in text_segments],
            "audio_segments": [dict(row) for row in audio_segments],
        }

    def delete_generation(self, generation_id: int) -> None:
        with self.connection() as conn:
            cur = conn.execute("DELETE FROM generations WHERE id = ?", (generation_id,))
            if cur.rowcount == 0:
                raise KeyError(f"generation {generation_id} not found")

    def get_audio_segment(self, generation_id: int, audio_segment_id: int) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM audio_segments
                WHERE generation_id = ? AND id = ?
                """,
                (generation_id, audio_segment_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"audio segment {audio_segment_id} not found")
        return dict(row)

    def create_ocr_draft(self, ocr_model: str, language: str, status: Status, error: str | None = None) -> int:
        self._validate_ocr_language(language)
        with self.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO ocr_drafts
                    (ocr_model, language, status, error)
                VALUES (?, ?, ?, ?)
                """,
                (ocr_model, language, status, error),
            )
            return int(cur.lastrowid)

    def create_ocr_draft_image(
        self,
        draft_id: int,
        position: int,
        image_path: str,
        original_filename: str | None,
        mime_type: str,
        byte_size: int,
        extracted_text: str,
        status: Status,
        error: str | None = None,
    ) -> int:
        with self.connection() as conn:
            self._ensure_ocr_draft_exists(conn, draft_id)
            cur = conn.execute(
                """
                INSERT INTO ocr_draft_images
                    (ocr_draft_id, position, image_path, original_filename, mime_type, byte_size, extracted_text, status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (draft_id, position, image_path, original_filename, mime_type, byte_size, extracted_text, status, error),
            )
            image_id = int(cur.lastrowid)
            self._refresh_ocr_draft_status(conn, draft_id)
            return image_id

    def get_ocr_draft(self, draft_id: int) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM ocr_drafts WHERE id = ?", (draft_id,)).fetchone()
            if row is None:
                raise KeyError(f"ocr draft {draft_id} not found")
            images = self._list_ocr_draft_images(conn, draft_id)
        return self._ocr_draft_dict(row, images)

    def list_ocr_drafts(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM ocr_drafts
                ORDER BY datetime(created_at) DESC, id DESC
                """
            ).fetchall()
            images_by_draft = {
                int(row["id"]): self._list_ocr_draft_images(conn, int(row["id"]))
                for row in rows
            }
        return [self._ocr_draft_dict(row, images_by_draft[int(row["id"])]) for row in rows]

    def update_ocr_draft(
        self,
        draft_id: int,
        *,
        language: str,
        combined_text: str | None,
        image_texts: dict[int, str],
    ) -> None:
        self._validate_ocr_language(language)
        with self.connection() as conn:
            cur = conn.execute(
                """
                UPDATE ocr_drafts
                SET language = ?,
                    combined_text = COALESCE(?, combined_text),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (language, combined_text, draft_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"ocr draft {draft_id} not found")

            for image_id, extracted_text in image_texts.items():
                image_cur = conn.execute(
                    """
                    UPDATE ocr_draft_images
                    SET extracted_text = ?, status = 'completed', error = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE ocr_draft_id = ? AND id = ?
                    """,
                    (extracted_text, draft_id, image_id),
                )
                if image_cur.rowcount == 0:
                    raise KeyError(f"ocr draft image {image_id} not found")
            if combined_text is None and image_texts:
                self._rebuild_ocr_draft_combined_text(conn, draft_id)
            self._refresh_ocr_draft_status(conn, draft_id)

    def rebuild_ocr_draft_combined_text(self, draft_id: int) -> None:
        with self.connection() as conn:
            self._ensure_ocr_draft_exists(conn, draft_id)
            self._rebuild_ocr_draft_combined_text(conn, draft_id)

    def update_ocr_draft_image_ocr_result(
        self,
        draft_id: int,
        image_id: int,
        *,
        image_path: str,
        extracted_text: str,
        status: Status,
        error: str | None,
    ) -> None:
        with self.connection() as conn:
            cur = conn.execute(
                """
                UPDATE ocr_draft_images
                SET image_path = ?, extracted_text = ?, status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE ocr_draft_id = ? AND id = ?
                """,
                (image_path, extracted_text, status, error, draft_id, image_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"ocr draft image {image_id} not found")
            self._refresh_ocr_draft_status(conn, draft_id)

    def update_ocr_draft_status(self, draft_id: int, status: Status, error: str | None = None) -> None:
        with self.connection() as conn:
            cur = conn.execute(
                """
                UPDATE ocr_drafts
                SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, error, draft_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"ocr draft {draft_id} not found")

    def get_ocr_draft_image(self, draft_id: int, image_id: int) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM ocr_draft_images
                WHERE ocr_draft_id = ? AND id = ?
                """,
                (draft_id, image_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"ocr draft image {image_id} not found")
        return dict(row)

    def delete_ocr_draft_image(self, draft_id: int, image_id: int) -> dict[str, Any]:
        with self.connection() as conn:
            draft = conn.execute("SELECT * FROM ocr_drafts WHERE id = ?", (draft_id,)).fetchone()
            if draft is None:
                raise KeyError(f"ocr draft {draft_id} not found")
            if draft["linked_generation_id"] is not None:
                raise ValueError("ocr draft is linked to generation")
            image = conn.execute(
                """
                SELECT * FROM ocr_draft_images
                WHERE ocr_draft_id = ? AND id = ?
                """,
                (draft_id, image_id),
            ).fetchone()
            if image is None:
                raise KeyError(f"ocr draft image {image_id} not found")
            deleted = dict(image)
            conn.execute("DELETE FROM ocr_draft_images WHERE id = ?", (image_id,))
            remaining = conn.execute(
                """
                SELECT id FROM ocr_draft_images
                WHERE ocr_draft_id = ?
                ORDER BY position, id
                """,
                (draft_id,),
            ).fetchall()
            for position, row in enumerate(remaining):
                conn.execute(
                    "UPDATE ocr_draft_images SET position = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (position, row["id"]),
                )
            self._rebuild_ocr_draft_combined_text(conn, draft_id)
            self._refresh_ocr_draft_status(conn, draft_id)
        return deleted

    def link_ocr_draft_generation(self, draft_id: int, generation_id: int) -> None:
        with self.connection() as conn:
            try:
                cur = conn.execute(
                    """
                    UPDATE ocr_drafts
                    SET linked_generation_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND linked_generation_id IS NULL
                    """,
                    (generation_id, draft_id),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("generation is already linked to an ocr draft") from exc
            if cur.rowcount == 0:
                exists = conn.execute("SELECT 1 FROM ocr_drafts WHERE id = ?", (draft_id,)).fetchone()
                if exists is None:
                    raise KeyError(f"ocr draft {draft_id} not found")
                raise ValueError("ocr draft is already linked to generation")

    def delete_ocr_draft(self, draft_id: int) -> dict[str, Any]:
        draft = self.get_ocr_draft(draft_id)
        if draft["linked_generation_id"] is not None:
            raise ValueError("ocr draft is linked to generation")
        with self.connection() as conn:
            conn.execute("DELETE FROM ocr_drafts WHERE id = ?", (draft_id,))
        return draft

    def force_delete_ocr_draft(self, draft_id: int) -> dict[str, Any]:
        draft = self.get_ocr_draft(draft_id)
        with self.connection() as conn:
            conn.execute("DELETE FROM ocr_drafts WHERE id = ?", (draft_id,))
        return draft

    def get_ocr_draft_for_generation(self, generation_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM ocr_drafts WHERE linked_generation_id = ?",
                (generation_id,),
            ).fetchone()
            if row is None:
                return None
            images = self._list_ocr_draft_images(conn, int(row["id"]))
        return self._ocr_draft_dict(row, images)

    def _ensure_ocr_draft_exists(self, conn: sqlite3.Connection, draft_id: int) -> None:
        exists = conn.execute("SELECT 1 FROM ocr_drafts WHERE id = ?", (draft_id,)).fetchone()
        if exists is None:
            raise KeyError(f"ocr draft {draft_id} not found")

    def _list_ocr_draft_images(self, conn: sqlite3.Connection, draft_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT * FROM ocr_draft_images
            WHERE ocr_draft_id = ?
            ORDER BY position, id
            """,
            (draft_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _ocr_draft_dict(self, row: sqlite3.Row, images: list[dict[str, Any]]) -> dict[str, Any]:
        draft = dict(row)
        draft["images"] = images
        draft["extracted_text"] = draft["combined_text"]
        first_image = images[0] if images else {}
        for key in ("image_path", "original_filename", "mime_type", "byte_size"):
            draft[key] = first_image.get(key)
        return draft

    def _combined_ocr_text(self, images: list[dict[str, Any]]) -> str:
        return "\n\n".join(str(image["extracted_text"]).strip() for image in images if str(image["extracted_text"]).strip())

    def _rebuild_ocr_draft_combined_text(self, conn: sqlite3.Connection, draft_id: int) -> None:
        images = self._list_ocr_draft_images(conn, draft_id)
        conn.execute(
            """
            UPDATE ocr_drafts
            SET combined_text = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (self._combined_ocr_text(images), draft_id),
        )

    def _refresh_ocr_draft_status(self, conn: sqlite3.Connection, draft_id: int) -> None:
        rows = conn.execute(
            "SELECT status, error FROM ocr_draft_images WHERE ocr_draft_id = ? ORDER BY position, id",
            (draft_id,),
        ).fetchall()
        if not rows:
            status = "failed"
            error = "OCR draft has no images"
        else:
            statuses = [row["status"] for row in rows]
            errors = [row["error"] for row in rows if row["error"]]
            if any(item in {"queued", "running"} for item in statuses):
                status = "running"
            elif all(item == "completed" for item in statuses):
                status = "completed"
            elif all(item == "failed" for item in statuses):
                status = "failed"
            else:
                status = "partial_failed"
            error = "; ".join(errors) if errors else None
        conn.execute(
            """
            UPDATE ocr_drafts
            SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, error, draft_id),
        )

    def set_voice_preference(self, voice: str, language: str, preferred: bool) -> None:
        self._validate_voice_language(language)
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO voice_preferences (voice, language, preferred, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(voice, language) DO UPDATE SET
                    preferred = excluded.preferred,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (voice, language, int(preferred)),
            )

    def list_voice_preferences(self) -> dict[tuple[str, str], bool]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT voice, language, preferred FROM voice_preferences ORDER BY language, voice"
            ).fetchall()
        return {(str(row["voice"]), str(row["language"])): bool(row["preferred"]) for row in rows}
