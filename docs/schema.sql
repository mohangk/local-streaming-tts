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

CREATE TABLE text_segments (
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

CREATE TABLE audio_segments (
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

CREATE TABLE continuous_audio_artifacts (
    generation_id INTEGER PRIMARY KEY REFERENCES generations(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('building', 'completed', 'failed')),
    appended_through_segment_index INTEGER NOT NULL DEFAULT -1 CHECK (appended_through_segment_index >= -1),
    byte_size INTEGER NOT NULL DEFAULT 0 CHECK (byte_size >= 0),
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE playback_telemetry_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    segment_index INTEGER CHECK (segment_index IS NULL OR segment_index >= 0),
    audio_segment_id INTEGER REFERENCES audio_segments(id) ON DELETE SET NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_playback_telemetry_generation_id
ON playback_telemetry_events(generation_id, id);

CREATE INDEX idx_playback_telemetry_session_id
ON playback_telemetry_events(session_id, id);

CREATE TABLE voice_preferences (
    voice TEXT NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('en', 'zh')),
    preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (voice, language)
);

CREATE TABLE ocr_drafts (
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

CREATE UNIQUE INDEX idx_ocr_drafts_linked_generation_id
ON ocr_drafts(linked_generation_id)
WHERE linked_generation_id IS NOT NULL;

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

CREATE TABLE voice_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    name_key TEXT NOT NULL UNIQUE,
    model TEXT NOT NULL,
    voice TEXT NOT NULL,
    language TEXT NOT NULL CHECK(language IN ('en', 'zh')),
    speed REAL NOT NULL CHECK(speed BETWEEN 0.5 AND 2.0),
    instructions TEXT NOT NULL,
    preview_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE profile_migrations (version INTEGER PRIMARY KEY);
