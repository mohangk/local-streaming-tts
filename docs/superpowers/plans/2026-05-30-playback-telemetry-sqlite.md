# Playback Telemetry SQLite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local SQLite-backed playback telemetry for diagnosing mobile/background long-article playback stops.

**Architecture:** Store content-free generation playback events in SQLite through a write-only API. Add a focused `telemetry.js` frontend module that queues and sends events, while `app.js` remains the playback orchestrator. Keep voice samples excluded and preserve existing playback behavior.

**Tech Stack:** FastAPI, Pydantic, SQLite, vanilla ES modules, Vitest/jsdom, pytest, existing frontend static tests.

---

## Review Hardening

The implementation must enforce the content-free telemetry boundary on the server side, not only in frontend helpers. Use these additional constraints while executing the tasks below:

- `session_id` must match an app-generated opaque token shape: either a browser UUID or `session-<timestamp>-<hex>`.
- `event_name` must be one of the documented telemetry event names.
- `payload` must be sanitized by key and value type before storage.
- Unknown payload keys, free-form string values for enum fields, and mismatched types for boolean/numeric fields must be dropped.
- Storage should enforce the same sanitization as the API so direct storage callers cannot bypass the content-free boundary.

## File Structure

- Modify `src/tts_app/storage.py`: create telemetry table/indexes and add behavior-level storage methods.
- Modify `tests/test_storage.py`: cover persistence, missing generation rejection, retention, and deletion cascade.
- Modify `src/tts_app/api.py`: add telemetry request models and `POST /api/generations/{generation_id}/playback-telemetry`.
- Modify `tests/test_api.py`: cover valid batches and validation failures.
- Create `src/tts_app/static/telemetry.js`: session, event building, queueing, flushing, content redaction boundaries.
- Create `tests/js/telemetry.test.js`: Vitest coverage for helper behavior.
- Modify `src/tts_app/static/app.js`: call telemetry helpers from generation playback lifecycle points.
- Modify `src/tts_app/static/index.html` and existing module imports: bump asset version.
- Modify `tests/test_frontend_static.py`: pin telemetry import/wiring and voice-sample exclusion.
- Modify `docs/architecture.md` and `tests/test_docs.py` only if implementation needs public architecture guidance beyond the committed spec.

## Constants

Use these names consistently unless implementation reveals a clear local convention conflict:

```python
PLAYBACK_TELEMETRY_RETENTION_LIMIT = 1000
PLAYBACK_TELEMETRY_BATCH_LIMIT = 50
```

Use asset version:

```text
playback-telemetry-1
```

## Task 1: Storage Schema And Methods

**Files:**
- Modify: `tests/test_storage.py`
- Modify: `src/tts_app/storage.py`

- [ ] **Step 1: Write failing storage tests**

Add these tests near the generation progress tests in `tests/test_storage.py`:

```python
def test_playback_telemetry_round_trip(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A B", "fake", "Test", {})
    segment_ids = storage.create_text_segments(generation_id, ["A", "B"])
    audio_id = storage.record_audio_segment(
        generation_id,
        segment_ids[0],
        0,
        Path("audio/1/0.mp3"),
        "audio/mpeg",
        10,
        123,
        Status.COMPLETED,
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
        Path("audio/2/0.mp3"),
        "audio/mpeg",
        10,
        123,
        Status.COMPLETED,
    )

    with pytest.raises(KeyError):
        storage.record_playback_telemetry(
            first_generation_id,
            "session-1710000000000-abc123",
            [{"event_name": "audio_play", "audio_segment_id": audio_id, "payload": {}}],
        )


def test_playback_telemetry_retains_newest_events_per_generation(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A", "fake", "Test", {})

    storage.record_playback_telemetry(
        generation_id,
        "session-1710000000000-abc123",
        [
            {"event_name": "audio_play", "segment_index": index, "payload": {"index": index}}
            for index in range(1005)
        ],
    )

    events = storage.list_playback_telemetry_events(generation_id)
    assert len(events) == 1000
    assert events[0]["payload"]["index"] == 5
    assert events[-1]["payload"]["index"] == 1004


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
```

- [ ] **Step 2: Run storage tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_storage.py::test_playback_telemetry_round_trip tests/test_storage.py::test_playback_telemetry_requires_existing_generation tests/test_storage.py::test_playback_telemetry_requires_audio_segment_from_same_generation tests/test_storage.py::test_playback_telemetry_retains_newest_events_per_generation tests/test_storage.py::test_delete_generation_cascades_playback_telemetry -q
```

Expected: FAIL because `Storage.record_playback_telemetry` does not exist.

- [ ] **Step 3: Add storage schema**

In `src/tts_app/storage.py`, add near imports:

```python
PLAYBACK_TELEMETRY_RETENTION_LIMIT = 1000
```

In `Storage.init_schema`, add the table and indexes inside the initial `executescript` after `audio_segments`:

```sql
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
```

- [ ] **Step 4: Add storage methods**

Add these methods near `update_generation_progress` in `src/tts_app/storage.py`:

```python
    def record_playback_telemetry(self, generation_id: int, session_id: str, events: list[dict[str, Any]]) -> int:
        with self.connection() as conn:
            generation = conn.execute("SELECT id FROM generations WHERE id = ?", (generation_id,)).fetchone()
            if generation is None:
                raise KeyError(f"generation {generation_id} not found")
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
                    json.dumps(event.get("payload", {})),
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
```

- [ ] **Step 5: Run storage tests**

Run:

```bash
.venv/bin/pytest tests/test_storage.py::test_playback_telemetry_round_trip tests/test_storage.py::test_playback_telemetry_requires_existing_generation tests/test_storage.py::test_playback_telemetry_requires_audio_segment_from_same_generation tests/test_storage.py::test_playback_telemetry_retains_newest_events_per_generation tests/test_storage.py::test_delete_generation_cascades_playback_telemetry -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tts_app/storage.py tests/test_storage.py
git commit -m "feat: store playback telemetry events"
```

## Task 2: Telemetry API Endpoint

**Files:**
- Modify: `tests/test_api.py`
- Modify: `src/tts_app/api.py`

- [ ] **Step 1: Write failing API tests**

Add tests near progress endpoint tests in `tests/test_api.py`:

```python
def test_record_playback_telemetry_batch(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    response = client.post(
        "/api/generations/text",
        json={"text": "One. Two.", "title": "Telemetry", "voice": "Test", "speed": 1.0, "language": "en"},
    )
    generation_id = response.json()["generation_id"]

    response = client.post(
        f"/api/generations/{generation_id}/playback-telemetry",
        json={
            "session_id": "session-1710000000000-abc123",
            "events": [
                {
                    "event_name": "audio_waiting",
                    "segment_index": 0,
                    "audio_segment_id": None,
                    "payload": {"visibility_state": "hidden"},
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"stored": 1}
    events = test_settings.storage.list_playback_telemetry_events(generation_id)
    assert events[0]["event_name"] == "audio_waiting"
    assert events[0]["payload"] == {"visibility_state": "hidden"}


def test_record_playback_telemetry_unknown_generation_returns_404(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.post(
        "/api/generations/999/playback-telemetry",
        json={"session_id": "session-1710000000000-abc123", "events": [{"event_name": "audio_play", "payload": {}}]},
    )

    assert response.status_code == 404


def test_record_playback_telemetry_validates_batch_size(test_settings):
    client = TestClient(create_app(test_settings, run_background_inline=True))
    generation = client.post(
        "/api/generations/text",
        json={"text": "One.", "title": "Telemetry", "voice": "Test", "speed": 1.0, "language": "en"},
    ).json()

    empty = client.post(
        f"/api/generations/{generation['generation_id']}/playback-telemetry",
        json={"session_id": "session-1710000000000-abc123", "events": []},
    )
    oversized = client.post(
        f"/api/generations/{generation['generation_id']}/playback-telemetry",
        json={
            "session_id": "session-1710000000000-abc123",
            "events": [{"event_name": "audio_play", "payload": {}} for _ in range(51)],
        },
    )

    assert empty.status_code == 422
    assert oversized.status_code == 422
```

If `test_settings.storage` is not available in the local fixture, replace that line with:

```python
events = Storage(test_settings.db_path).list_playback_telemetry_events(generation_id)
```

- [ ] **Step 2: Run API tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_record_playback_telemetry_batch tests/test_api.py::test_record_playback_telemetry_unknown_generation_returns_404 tests/test_api.py::test_record_playback_telemetry_validates_batch_size -q
```

Expected: FAIL with 404 because the route does not exist.

- [ ] **Step 3: Add API models**

In `src/tts_app/api.py`, change the typing and Pydantic imports:

```python
from typing import Any
from pydantic import BaseModel, Field, field_validator
```

Import telemetry validation constants from storage:

```python
from tts_app.storage import PLAYBACK_TELEMETRY_EVENT_NAMES, Storage, validate_playback_telemetry_session_id
```

Add near `ProgressRequest`:

```python
PLAYBACK_TELEMETRY_BATCH_LIMIT = 50


class PlaybackTelemetryEventRequest(BaseModel):
    event_name: str = Field(min_length=1, max_length=80)
    segment_index: int | None = Field(default=None, ge=0)
    audio_segment_id: int | None = Field(default=None, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        if value not in PLAYBACK_TELEMETRY_EVENT_NAMES:
            raise ValueError("unsupported playback telemetry event")
        return value


class PlaybackTelemetryRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    events: list[PlaybackTelemetryEventRequest] = Field(min_length=1, max_length=PLAYBACK_TELEMETRY_BATCH_LIMIT)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        return validate_playback_telemetry_session_id(value)
```

- [ ] **Step 4: Add API route**

Add this route after `update_progress`:

```python
    @app.post("/api/generations/{generation_id}/playback-telemetry")
    async def record_playback_telemetry(generation_id: int, payload: PlaybackTelemetryRequest):
        try:
            stored = storage.record_playback_telemetry(
                generation_id,
                payload.session_id,
                [event.model_dump() for event in payload.events],
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc
        logger.info(
            "playback_telemetry_recorded generation_id=%s session_id=%s events=%s",
            generation_id,
            payload.session_id,
            stored,
        )
        return {"stored": stored}
```

- [ ] **Step 5: Run API tests**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_record_playback_telemetry_batch tests/test_api.py::test_record_playback_telemetry_unknown_generation_returns_404 tests/test_api.py::test_record_playback_telemetry_validates_batch_size -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/tts_app/api.py tests/test_api.py
git commit -m "feat: add playback telemetry API"
```

## Task 3: Frontend Telemetry Module

**Files:**
- Create: `src/tts_app/static/telemetry.js`
- Create: `tests/js/telemetry.test.js`
- Modify: `package.json` only if `check:js` must include the new file.

- [ ] **Step 1: Write failing Vitest tests**

Create `tests/js/telemetry.test.js`:

```js
import { describe, expect, it, vi } from "vitest";
import {
  createPlaybackTelemetry,
  playbackTelemetryContext,
} from "../../src/tts_app/static/telemetry.js";

function generationState(overrides = {}) {
  return {
    currentGenerationId: 7,
    currentSegmentIndex: 2,
    currentDetail: {
      audio_segments: [{ id: 42, segment_index: 2 }],
    },
    samplePlayback: false,
    continuousPlayback: true,
    autoplay: true,
    wakeLock: {},
    eventSource: { readyState: 1 },
    ...overrides,
  };
}

function audio(overrides = {}) {
  return {
    paused: false,
    ended: false,
    currentTime: 12.5,
    duration: 30,
    readyState: 4,
    networkState: 1,
    ...overrides,
  };
}

describe("playbackTelemetryContext", () => {
  it("builds content-free playback context for a generation segment", () => {
    expect(playbackTelemetryContext(generationState(), audio())).toEqual({
      generationId: 7,
      segmentIndex: 2,
      audioSegmentId: 42,
      payload: {
        audio_current_time: 12.5,
        audio_duration: 30,
        audio_ended: false,
        audio_network_state: 1,
        audio_paused: false,
        audio_ready_state: 4,
        autoplay: true,
        continuous_playback: true,
        event_source_ready_state: 1,
        wake_lock_active: true,
      },
    });
  });

  it("returns null for voice sample playback", () => {
    expect(playbackTelemetryContext(generationState({ samplePlayback: true }), audio())).toBeNull();
  });
});

describe("createPlaybackTelemetry", () => {
  it("queues and flushes generation events", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: true }));
    const telemetry = createPlaybackTelemetry({ fetchImpl, sessionId: "session-1710000000000-abc123" });

    telemetry.record(generationState(), audio(), "audio_play", { visibility_state: "visible" });
    await telemetry.flush();

    expect(fetchImpl).toHaveBeenCalledWith("/api/generations/7/playback-telemetry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: "session-1710000000000-abc123",
        events: [
          {
            event_name: "audio_play",
            segment_index: 2,
            audio_segment_id: 42,
            payload: expect.objectContaining({ visibility_state: "visible", audio_paused: false }),
          },
        ],
      }),
    });
  });

  it("does not throw when telemetry delivery fails", async () => {
    const telemetry = createPlaybackTelemetry({
      fetchImpl: vi.fn(async () => {
        throw new Error("offline");
      }),
      sessionId: "session-1710000000000-abc123",
    });

    telemetry.record(generationState(), audio(), "audio_waiting");
    await expect(telemetry.flush()).resolves.toBe(false);
  });
});
```

- [ ] **Step 2: Run Vitest to verify failure**

Run:

```bash
npm run test:js
```

Expected: FAIL because `src/tts_app/static/telemetry.js` does not exist.

- [ ] **Step 3: Implement telemetry module**

Create `src/tts_app/static/telemetry.js`:

```js
const MAX_QUEUE_LENGTH = 100;

function sessionId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function audioSegmentForState(state) {
  return state.currentDetail?.audio_segments.find((segment) => segment.segment_index === state.currentSegmentIndex) || null;
}

export function playbackTelemetryContext(state, audioPlayer) {
  if (!state.currentGenerationId || state.samplePlayback) {
    return null;
  }
  const audioSegment = audioSegmentForState(state);
  return {
    generationId: state.currentGenerationId,
    segmentIndex: state.currentSegmentIndex,
    audioSegmentId: audioSegment?.id ?? null,
    payload: {
      audio_current_time: Number.isFinite(audioPlayer.currentTime) ? audioPlayer.currentTime : null,
      audio_duration: Number.isFinite(audioPlayer.duration) ? audioPlayer.duration : null,
      audio_ended: Boolean(audioPlayer.ended),
      audio_network_state: audioPlayer.networkState,
      audio_paused: Boolean(audioPlayer.paused),
      audio_ready_state: audioPlayer.readyState,
      autoplay: Boolean(state.autoplay),
      continuous_playback: Boolean(state.continuousPlayback),
      event_source_ready_state: state.eventSource?.readyState ?? null,
      wake_lock_active: Boolean(state.wakeLock),
    },
  };
}

export function createPlaybackTelemetry(options = {}) {
  const fetchImpl = options.fetchImpl || fetch;
  const telemetrySessionId = options.sessionId || sessionId();
  const queue = [];

  function record(state, audioPlayer, eventName, payload = {}) {
    const context = playbackTelemetryContext(state, audioPlayer);
    if (!context) {
      return false;
    }
    queue.push({
      generationId: context.generationId,
      event: {
        event_name: eventName,
        segment_index: context.segmentIndex,
        audio_segment_id: context.audioSegmentId,
        payload: { ...context.payload, ...payload },
      },
    });
    if (queue.length > MAX_QUEUE_LENGTH) {
      queue.splice(0, queue.length - MAX_QUEUE_LENGTH);
    }
    return true;
  }

  async function flush() {
    const first = queue[0];
    if (!first) {
      return true;
    }
    const generationId = first.generationId;
    const events = queue.filter((item) => item.generationId === generationId).slice(0, 50);
    try {
      const response = await fetchImpl(`/api/generations/${generationId}/playback-telemetry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: telemetrySessionId,
          events: events.map((item) => item.event),
        }),
      });
      if (!response.ok) {
        return false;
      }
      for (const item of events) {
        const index = queue.indexOf(item);
        if (index >= 0) {
          queue.splice(index, 1);
        }
      }
      return true;
    } catch {
      return false;
    }
  }

  return {
    record,
    flush,
    sessionId: telemetrySessionId,
  };
}
```

- [ ] **Step 4: Add `telemetry.js` to parser checks**

Update `package.json` `check:js` to include:

```text
node --check src/tts_app/static/telemetry.js
```

Place it next to `playback.js`.

- [ ] **Step 5: Run frontend module tests**

Run:

```bash
npm run test:js
npm run check:js
npm run lint:js
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add package.json src/tts_app/static/telemetry.js tests/js/telemetry.test.js
git commit -m "test: add playback telemetry helpers"
```

## Task 4: Wire Frontend Telemetry Into Playback

**Files:**
- Modify: `src/tts_app/static/app.js`
- Modify: `src/tts_app/static/ocr.js`
- Modify: `src/tts_app/static/index.html`
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Write failing static tests**

In `tests/test_frontend_static.py`, add `telemetry.js` to `JS_FILES`:

```python
JS_FILES = ("app.js", "ocr.js", "playback.js", "telemetry.js", "state.js", "dom.js", "utils.js")
```

Add tests near playback static tests:

```python
def test_frontend_imports_playback_telemetry_module():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    telemetry_js = (STATIC_DIR / "telemetry.js").read_text(encoding="utf-8")

    assert 'from "./telemetry.js?v=' in app_js
    assert "createPlaybackTelemetry" in app_js
    assert "playbackTelemetry.record" in app_js
    assert "playbackTelemetry.flush" in app_js
    assert "export function createPlaybackTelemetry" in telemetry_js


def test_frontend_voice_sample_path_does_not_record_playback_telemetry():
    js = frontend_js()
    sampler = js.split("async function playVoiceSample()", 1)[1].split("async function loadHistory()", 1)[0]

    assert "playbackTelemetry.record" not in sampler
    assert "state.samplePlayback = true" in sampler


def test_frontend_static_asset_version_bumped_for_playback_telemetry():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    ocr_js = (STATIC_DIR / "ocr.js").read_text(encoding="utf-8")

    assert 'href="/static/styles.css?v=playback-telemetry-1"' in html
    assert 'src="/static/app.js?v=playback-telemetry-1"' in html
    assert "?v=playback-telemetry-1" in app_js
    assert "?v=playback-telemetry-1" in ocr_js
    assert "playback-vitest-1" not in html
    assert "playback-vitest-1" not in app_js
    assert "playback-vitest-1" not in ocr_js
```

- [ ] **Step 2: Run static tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_imports_playback_telemetry_module tests/test_frontend_static.py::test_frontend_voice_sample_path_does_not_record_playback_telemetry tests/test_frontend_static.py::test_frontend_static_asset_version_bumped_for_playback_telemetry -q
```

Expected: FAIL because `app.js` does not import telemetry and asset versions are not bumped.

- [ ] **Step 3: Import telemetry in `app.js`**

Update local import query strings in `app.js`, `ocr.js`, and `index.html` from `playback-vitest-1` to `playback-telemetry-1`.

In `app.js`, add:

```js
import { createPlaybackTelemetry } from "./telemetry.js?v=playback-telemetry-1";
```

After imports, create the telemetry instance:

```js
const playbackTelemetry = createPlaybackTelemetry();
```

- [ ] **Step 4: Add a local record helper in `app.js`**

Add near playback helpers:

```js
function recordPlaybackTelemetry(eventName, payload = {}) {
  if (playbackTelemetry.record(state, audioPlayer, eventName, payload)) {
    playbackTelemetry.flush();
  }
}
```

- [ ] **Step 5: Record generation and segment events**

In `openGeneration`, after `state.currentGenerationId = generationId`, call:

```js
recordPlaybackTelemetry("generation_opened", {
  platform: telemetryPlatform(),
  user_agent: telemetryUserAgent(),
});
```

In `playSegment`, after `state.currentSegmentIndex = segmentIndex`, call:

```js
recordPlaybackTelemetry("segment_play_attempted");
```

- [ ] **Step 6: Record progress events**

In `saveProgress`, before `fetch`, call:

```js
recordPlaybackTelemetry("progress_save_attempted", buildProgressPayload(segmentIndex, options));
```

After a successful response, call:

```js
recordPlaybackTelemetry("progress_save_succeeded", {
  last_segment_index: progress.last_segment_index,
  progress_percent: progress.progress_percent,
});
```

In the `catch`, call:

```js
recordPlaybackTelemetry("progress_save_failed");
```

- [ ] **Step 7: Record audio and lifecycle events**

In audio event handlers:

```js
audioPlayer.addEventListener("play", () => {
  playPauseButton.textContent = "Pause";
  acquireWakeLock();
  recordPlaybackTelemetry("audio_play");
});

audioPlayer.addEventListener("pause", () => {
  playPauseButton.textContent = "Play";
  recordPlaybackTelemetry("audio_pause");
  releaseWakeLock();
});
```

Add handlers:

```js
audioPlayer.addEventListener("waiting", () => recordPlaybackTelemetry("audio_waiting"));
audioPlayer.addEventListener("stalled", () => recordPlaybackTelemetry("audio_stalled"));
audioPlayer.addEventListener("suspend", () => recordPlaybackTelemetry("audio_suspend"));
audioPlayer.addEventListener("error", () => recordPlaybackTelemetry("audio_error", { error_code: audioPlayer.error?.code ?? null }));
```

In the ended handler, after `const action = endedPlaybackAction(...)`, call:

```js
recordPlaybackTelemetry("audio_ended");
recordPlaybackTelemetry("playback_ended_action", action);
```

In `document.addEventListener("visibilitychange", ...)`, call:

```js
recordPlaybackTelemetry("visibility_changed", {
  visibility_state: document.visibilityState,
  document_hidden: document.hidden,
});
```

Add page lifecycle handlers:

```js
window.addEventListener("pagehide", () => recordPlaybackTelemetry("page_hidden"));
window.addEventListener("pageshow", () => recordPlaybackTelemetry("page_shown"));
document.addEventListener("freeze", () => recordPlaybackTelemetry("page_frozen"));
document.addEventListener("resume", () => recordPlaybackTelemetry("page_resumed"));
```

- [ ] **Step 8: Record wake-lock and EventSource events**

In `acquireWakeLock`, record:

```js
recordPlaybackTelemetry("wake_lock_acquired");
```

when request succeeds, and:

```js
recordPlaybackTelemetry("wake_lock_failed");
```

inside the `catch`.

In `releaseWakeLock`, record:

```js
recordPlaybackTelemetry("wake_lock_released");
```

before clearing `state.wakeLock`.

In `state.eventSource.onerror`, call:

```js
recordPlaybackTelemetry("event_source_error");
```

- [ ] **Step 9: Run focused frontend checks**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_imports_playback_telemetry_module tests/test_frontend_static.py::test_frontend_voice_sample_path_does_not_record_playback_telemetry tests/test_frontend_static.py::test_frontend_static_asset_version_bumped_for_playback_telemetry -q
npm run check:js
npm run lint:js
npm run test:js
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/tts_app/static/app.js src/tts_app/static/ocr.js src/tts_app/static/index.html tests/test_frontend_static.py
git commit -m "feat: record playback telemetry events"
```

## Task 5: Documentation And Architecture Review

**Files:**
- Modify: `docs/architecture.md`
- Modify: `tests/test_docs.py`

- [ ] **Step 1: Add docs test coverage**

In `tests/test_docs.py`, add:

```python
assert "SQLite-backed playback telemetry" in architecture
assert "content-free" in architecture
```

- [ ] **Step 2: Run docs test to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_docs.py::test_handoff_docs_exist_and_cover_local_operations -q
```

Expected: FAIL until architecture docs mention telemetry.

- [ ] **Step 3: Update architecture docs**

In `docs/architecture.md`, add under `Frontend state rules`:

```markdown
- Playback telemetry should stay local-first and content-free. Store diagnostic generation playback events in SQLite, delete them with the generation, and do not collect article text, OCR text, extracted URL content, generated audio bytes, or provider raw responses.
```

- [ ] **Step 4: Run docs tests**

Run:

```bash
.venv/bin/pytest tests/test_docs.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/architecture.md tests/test_docs.py
git commit -m "docs: document playback telemetry boundary"
```

## Task 6: Final Verification And PR

**Files:**
- No intended edits unless verification finds a defect.

- [ ] **Step 1: Run full verification**

Run:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
git diff --check
```

Expected:

- `pytest`: all tests pass.
- `check:js`: all static modules parse, including `telemetry.js`.
- `lint:js`: static modules and Vitest tests lint cleanly.
- `test:js`: playback and telemetry Vitest suites pass.
- `git diff --check`: no whitespace errors.

- [ ] **Step 2: Run architecture reviewer**

Use the `architecture_reviewer` custom agent against the full branch diff. Prompt:

```text
Review the current diff against docs/architecture.md, AGENTS.md, docs/architecture-review-subagent.md, .codex/agents/architecture-reviewer.toml, and relevant tests. Focus on local-first telemetry, SQLite retention/deletion semantics, content-free payload boundaries, frontend modularity, and whether voice samples are excluded.
```

Expected: no high-risk findings. Fix valid findings before continuing.

- [ ] **Step 3: Review commit history**

Run:

```bash
git log --oneline --max-count=8
```

Expected recent commits tell this story:

- design spec;
- storage;
- API;
- frontend telemetry helpers;
- frontend wiring;
- documentation boundary.

- [ ] **Step 4: Push and open PR**

Run:

```bash
git push -u origin feat/playback-telemetry
```

Open a PR against `main` with a summary and full verification results.
