# Playback Telemetry SQLite Design

## Summary

Readvox needs local diagnostic telemetry for a specific playback failure: on mobile, long article playback sometimes stops after the phone or browser backgrounds the page. The goal is to capture enough evidence to explain where and why playback stopped, then use that evidence to choose a better fix. This feature should not guess at the fix first.

Telemetry will be stored in SQLite, scoped to generations, and deleted with the generation. The frontend will emit content-free playback diagnostics for generated audio only. Voice samples are excluded because they are short provider previews, not durable generated article playback.

## Goals

- Store playback diagnostic events in SQLite so failures can be inspected after page reloads or mobile backgrounding.
- Capture enough page, audio, wake-lock, progress, and segment-transition signals to reconstruct why long generation playback stopped.
- Keep telemetry local-first and content-free.
- Add a small frontend telemetry module instead of growing `app.js`.
- Preserve existing playback behavior while adding diagnostic event recording.
- Keep the first pass inspectable through storage/API tests rather than adding a user-facing telemetry UI.

## Non-Goals

- Do not send telemetry to an external service.
- Do not store article text, OCR text, extracted URL content, generated audio bytes, or provider raw responses.
- Do not add a telemetry dashboard in this pass.
- Do not introduce a frontend framework.
- Do not change TTS provider behavior or generation scheduling.
- Do not try to fix the mobile background playback stop in this pass. The feature exists to gather evidence for that fix.

## Data Model

Add a `playback_telemetry_events` table owned by `src/tts_app/storage.py`:

```sql
CREATE TABLE IF NOT EXISTS playback_telemetry_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id INTEGER NOT NULL REFERENCES generations(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    segment_index INTEGER,
    audio_segment_id INTEGER REFERENCES audio_segments(id) ON DELETE SET NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Add indexes for generation and session inspection:

```sql
CREATE INDEX IF NOT EXISTS idx_playback_telemetry_generation_id
ON playback_telemetry_events(generation_id, id);

CREATE INDEX IF NOT EXISTS idx_playback_telemetry_session_id
ON playback_telemetry_events(session_id, id);
```

`audio_segment_id` is intentionally nullable. Some events happen before an audio segment is selected, after playback has stopped, or during page lifecycle changes where the current audio segment is unknown. When an `audio_segment_id` is provided, storage should validate that it belongs to the same `generation_id` as the telemetry event.

## Retention

Telemetry is local data and should not grow without bound. The first pass should keep the newest `1000` events per generation. Storage should prune older events after inserting a batch for that generation.

Deleting a generation must delete its telemetry through the `ON DELETE CASCADE` relationship. There is no separate clear-telemetry UI in this pass.

## API Design

Add:

```http
POST /api/generations/{generation_id}/playback-telemetry
```

Request body:

```json
{
  "session_id": "session-1710000000000-abc123",
  "events": [
    {
      "event_name": "audio_waiting",
      "segment_index": 3,
      "audio_segment_id": 42,
      "payload": {
        "visibility_state": "hidden",
        "audio_paused": false,
        "audio_ended": false,
        "audio_current_time": 18.2
      }
    }
  ]
}
```

Response body:

```json
{
  "stored": 1
}
```

Validation rules:

- Unknown `generation_id` returns `404`.
- `session_id` is required and must match an app-generated opaque token shape: either a browser UUID or `session-<timestamp>-<hex>`.
- `events` must contain at least one event and no more than `50` events per request.
- `event_name` is required and must be no more than `80` characters.
- `payload` must be a JSON object.
- Backend storage serializes `payload` to JSON.

The API is intentionally write-only in this pass. Tests may inspect telemetry through `Storage` methods rather than adding a public read endpoint.

## Frontend Design

Add `src/tts_app/static/telemetry.js`.

Responsibilities:

- create a per-page playback `session_id`;
- build content-free telemetry events;
- enrich events with current playback context;
- queue and send small batches to the backend;
- skip all telemetry for voice samples;
- tolerate network failures without interrupting playback.

`app.js` remains the orchestrator. It should call telemetry helpers from existing playback lifecycle points, while `telemetry.js` owns event construction, redaction boundaries, queueing, and send behavior.

Candidate helper shape:

```js
createPlaybackTelemetrySession()
buildPlaybackTelemetryEvent(name, context, payload = {})
enqueuePlaybackTelemetryEvent(state, audioPlayer, name, payload = {})
flushPlaybackTelemetryEvents(fetchImpl = fetch)
```

The exact API can vary during implementation, but the boundary should remain: `app.js` says what happened; `telemetry.js` decides whether and how to record it.

## Event Coverage

Initial events should be enough to reconstruct long mobile playback stops without creating a high-volume stream:

- `generation_opened`
- `segment_play_attempted`
- `audio_play`
- `audio_pause`
- `audio_ended`
- `audio_waiting`
- `audio_stalled`
- `audio_suspend`
- `audio_error`
- `visibility_changed`
- `page_hidden`
- `page_shown`
- `page_frozen` when supported
- `page_resumed` when supported
- `wake_lock_acquired`
- `wake_lock_released`
- `wake_lock_failed`
- `event_source_error`
- `progress_save_attempted`
- `progress_save_succeeded`
- `progress_save_failed`
- `playback_ended_action`

Do not record high-frequency `timeupdate` events in the first pass. If later evidence needs finer timing, add throttled checkpoints explicitly.

## Event Context

Every event should include what is known at that moment:

- `generation_id`
- `session_id`
- `segment_index`
- `audio_segment_id`
- `event_name`
- current timestamp from the backend row

Payloads may include:

- `visibility_state`
- `document_hidden`
- `audio_paused`
- `audio_ended`
- `audio_current_time`
- `audio_duration`
- `audio_ready_state`
- `audio_network_state`
- `continuous_playback`
- `autoplay`
- `wake_lock_active`
- `event_source_ready_state`
- coarse `platform` and `user_agent` values when available
- action details such as `{ "type": "play-next", "segment_index": 4 }`

Payloads must not include:

- article text;
- OCR text;
- extracted URL or source content;
- generated audio bytes;
- provider responses;
- arbitrary DOM text.

## Failure Behavior

Telemetry must not disrupt playback:

- Failed telemetry requests should be swallowed after a bounded retry or dropped.
- Queue size should be bounded so backgrounded tabs cannot accumulate unbounded memory.
- `navigator.sendBeacon` may be used for `pagehide` if practical, but `fetch` is acceptable for the first pass.
- If a telemetry event cannot be built safely, skip it instead of throwing through playback handlers.

## Tests

Storage tests:

- create telemetry for a generation;
- reject telemetry for a missing generation;
- retain newest `1000` events per generation;
- delete telemetry when generation deletion runs.

API tests:

- valid batches return stored count;
- unknown generation returns `404`;
- empty and oversized batches fail validation;
- payloads are stored without article content fields.

Vitest tests:

- telemetry helpers build content-free events;
- voice sample state is ignored;
- queueing batches by generation/session works;
- flush failure does not throw to callers;
- page/audio context fields are included when provided.

Frontend static tests:

- `app.js` imports `telemetry.js`;
- generation playback paths emit telemetry calls;
- voice sample playback path does not emit telemetry calls;
- static asset version is bumped when the new module is wired.

Docs tests:

- architecture or docs mention SQLite-backed, local-first, content-free playback telemetry if the implementation updates public guidance.

## Implementation Sequence

Use the project architecture order:

1. Storage schema and methods with tests.
2. API request model and route with tests.
3. Frontend `telemetry.js` helpers with Vitest tests.
4. `app.js` wiring and static frontend tests.
5. Documentation updates if public commands or architecture guidance change.
6. Full verification and architecture review.

## First-Pass Decisions

- Do not add a public or private telemetry read endpoint in this pass. Inspect data through SQLite and storage tests.
- Use queued `fetch` for normal telemetry delivery. Add `sendBeacon` later only if browser behavior or tests justify it.
- Record coarse `user_agent` and `platform` once on `generation_opened`, not on every event.
