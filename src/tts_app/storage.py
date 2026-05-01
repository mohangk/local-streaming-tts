from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tts_app.models import SourceType, Status


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
                """
            )
            self._ensure_generation_progress_columns(conn)

    def _ensure_generation_progress_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(generations)").fetchall()}
        if "last_segment_index" not in columns:
            conn.execute("ALTER TABLE generations ADD COLUMN last_segment_index INTEGER NOT NULL DEFAULT 0")
        if "progress_percent" not in columns:
            conn.execute("ALTER TABLE generations ADD COLUMN progress_percent INTEGER NOT NULL DEFAULT 0")

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
