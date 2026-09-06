"""Named voice persistence. Profiles never own generation or audio data."""
from __future__ import annotations

import sqlite3

PROFILE_FIELDS = ('name', 'model', 'voice', 'language', 'speed', 'instructions', 'preview_text')


def ensure_profile_schema(conn: sqlite3.Connection) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS voice_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK(length(trim(name)) > 0),
        model TEXT NOT NULL, voice TEXT NOT NULL,
        language TEXT NOT NULL CHECK(language IN ('en', 'zh')),
        speed REAL NOT NULL CHECK(speed BETWEEN 0.5 AND 2.0),
        instructions TEXT NOT NULL, preview_text TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )''')


class ProfileStorageMixin:
    def list_voice_profiles(self):
        with self.connection() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM voice_profiles ORDER BY id')]

    def get_voice_profile(self, profile_id):
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM voice_profiles WHERE id = ?', (profile_id,)).fetchone()
            if row is None:
                raise KeyError(profile_id)
            return dict(row)

    def save_voice_profile(self, values, profile_id=None):
        with self.connection() as conn:
            parameters = tuple(values[field] for field in PROFILE_FIELDS)
            if profile_id is None:
                profile_id = conn.execute(
                    'INSERT INTO voice_profiles (' + ','.join(PROFILE_FIELDS) + ') VALUES (?,?,?,?,?,?,?)',
                    parameters,
                ).lastrowid
            else:
                cursor = conn.execute(
                    'UPDATE voice_profiles SET ' + ','.join(field + '=?' for field in PROFILE_FIELDS)
                    + ',updated_at=CURRENT_TIMESTAMP WHERE id=?', parameters + (profile_id,),
                )
                if not cursor.rowcount:
                    raise KeyError(profile_id)
        return self.get_voice_profile(profile_id)

    def delete_voice_profile(self, profile_id):
        with self.connection() as conn:
            if not conn.execute('DELETE FROM voice_profiles WHERE id=?', (profile_id,)).rowcount:
                raise KeyError(profile_id)
