# Continuous Stitched Playback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build continuous long-article playback so the browser plays one stable audio URL while the backend stitches completed segment MP3s into a cached generation-level artifact.

**Architecture:** Keep segment MP3s as the generation source of truth. Add SQLite artifact metadata plus a focused stitcher module that appends completed segment files in order to `data/audio/<generation_id>/full.mp3`. Add one continuous playback route and move frontend playback away from hidden-page per-segment `audio.src` swaps.

**Tech Stack:** FastAPI, SQLite, plain JavaScript modules, existing fake TTS provider, pytest, Vitest.

---

## File Structure

- Create `src/tts_app/continuous_audio.py`: stitched artifact builder and byte-range helpers.
- Modify `src/tts_app/storage.py`: schema migration and behavior-level artifact methods.
- Modify `src/tts_app/generation.py`: invoke the stitcher after each segment completes.
- Modify `src/tts_app/api.py`: add continuous audio route. If the route grows beyond this task, move it to `src/tts_app/routes/playback.py`.
- Modify `src/tts_app/static/playback.js`: add continuous playback URL/action helpers.
- Modify `src/tts_app/static/app.js`: use the continuous URL for generated playback.
- Modify `src/tts_app/static/telemetry.js` and storage constants only if adding new telemetry event names.
- Add tests in `tests/test_storage.py`, `tests/test_generation.py`, `tests/test_api.py`, `tests/js/playback.test.js`, and `tests/test_frontend_static.py`.

## Task 1: Store Stitched Audio Artifact Metadata

**Files:**
- Modify: `src/tts_app/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Add tests that create a generation, record/update an artifact, retrieve it, and verify generation deletion removes the row:

```python
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

    with pytest.raises(KeyError):
        storage.get_continuous_audio_artifact(generation_id)
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
.venv/bin/pytest tests/test_storage.py::test_continuous_audio_artifact_round_trip tests/test_storage.py::test_delete_generation_cascades_continuous_audio_artifact -q
```

Expected: fail because the storage methods/table do not exist.

- [ ] **Step 3: Add schema and methods**

Add table creation inside `Storage.init_schema()`:

```sql
CREATE TABLE IF NOT EXISTS continuous_audio_artifacts (
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
```

Add behavior-level methods:

```python
def upsert_continuous_audio_artifact(
    self,
    generation_id: int,
    file_path: str,
    mime_type: str,
    status: str,
    appended_through_segment_index: int,
    byte_size: int,
    error: str | None,
) -> None:
    with self.connection() as conn:
        generation = conn.execute("SELECT id FROM generations WHERE id = ?", (generation_id,)).fetchone()
        if generation is None:
            raise KeyError(f"generation {generation_id} not found")
        conn.execute(
            """
            INSERT INTO continuous_audio_artifacts
                (generation_id, file_path, mime_type, status, appended_through_segment_index, byte_size, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(generation_id) DO UPDATE SET
                file_path = excluded.file_path,
                mime_type = excluded.mime_type,
                status = excluded.status,
                appended_through_segment_index = excluded.appended_through_segment_index,
                byte_size = excluded.byte_size,
                error = excluded.error,
                updated_at = CURRENT_TIMESTAMP
            """,
            (generation_id, file_path, mime_type, status, appended_through_segment_index, byte_size, error),
        )


def get_continuous_audio_artifact(self, generation_id: int) -> dict[str, Any]:
    with self.connection() as conn:
        row = conn.execute(
            """
            SELECT generation_id, file_path, mime_type, status, appended_through_segment_index, byte_size, error
            FROM continuous_audio_artifacts
            WHERE generation_id = ?
            """,
            (generation_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"continuous audio artifact for generation {generation_id} not found")
    return dict(row)
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_storage.py::test_continuous_audio_artifact_round_trip tests/test_storage.py::test_delete_generation_cascades_continuous_audio_artifact -q
```

Expected: pass.

Commit:

```bash
git add src/tts_app/storage.py tests/test_storage.py
git commit -m "feat: store continuous audio artifacts"
```

## Task 2: Add The Continuous Audio Stitcher

**Files:**
- Create: `src/tts_app/continuous_audio.py`
- Modify: `src/tts_app/storage.py`
- Test: `tests/test_continuous_audio.py`

- [ ] **Step 1: Add storage helper for completed audio segments**

Write a failing test for a new storage method:

```python
def test_list_completed_audio_segments_for_stitching(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A B", "fake", "Test", {})
    segment_ids = storage.create_text_segments(generation_id, ["A", "B"])
    first_audio_id = storage.record_audio_segment(
        generation_id, segment_ids[0], 0, "audio/1/segment-0001.mp3", "audio/mpeg", None, 3, "completed", None
    )
    second_audio_id = storage.record_audio_segment(
        generation_id, segment_ids[1], 1, "audio/1/segment-0002.mp3", "audio/mpeg", None, 4, "completed", None
    )

    rows = storage.list_completed_audio_segments_for_stitching(generation_id)

    assert [row["id"] for row in rows] == [first_audio_id, second_audio_id]
    assert [row["segment_index"] for row in rows] == [0, 1]
```

Implement:

```python
def list_completed_audio_segments_for_stitching(self, generation_id: int) -> list[dict[str, Any]]:
    with self.connection() as conn:
        rows = conn.execute(
            """
            SELECT id, generation_id, segment_index, file_path, mime_type, byte_size, status
            FROM audio_segments
            WHERE generation_id = ? AND status = 'completed'
            ORDER BY segment_index
            """,
            (generation_id,),
        ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 2: Write failing stitcher tests**

Create `tests/test_continuous_audio.py`:

```python
from pathlib import Path

from tts_app.continuous_audio import ContinuousAudioStitcher
from tts_app.storage import Storage


def _generation_with_audio(storage: Storage, data_dir: Path, count: int = 3) -> int:
    generation_id = storage.create_generation("text", "Manual text", None, "A B C", "fake", "Test", {})
    segment_ids = storage.create_text_segments(generation_id, ["A", "B", "C"][:count])
    audio_dir = data_dir / "audio" / str(generation_id)
    audio_dir.mkdir(parents=True)
    for index, text_segment_id in enumerate(segment_ids):
        path = audio_dir / f"segment-{index + 1:04d}.mp3"
        path.write_bytes(f"SEG{index}".encode())
        storage.record_audio_segment(
            generation_id,
            text_segment_id,
            index,
            str(path.relative_to(data_dir)),
            "audio/mpeg",
            None,
            path.stat().st_size,
            "completed",
            None,
        )
    return generation_id


def test_stitcher_appends_completed_segments_in_order(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = _generation_with_audio(storage, test_settings.data_dir)
    stitcher = ContinuousAudioStitcher(storage, test_settings.data_dir)

    artifact = stitcher.ensure_appended(generation_id)

    full_path = test_settings.data_dir / artifact["file_path"]
    assert full_path.read_bytes() == b"SEG0SEG1SEG2"
    assert artifact["appended_through_segment_index"] == 2
    assert artifact["byte_size"] == len(b"SEG0SEG1SEG2")


def test_stitcher_is_idempotent(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = _generation_with_audio(storage, test_settings.data_dir)
    stitcher = ContinuousAudioStitcher(storage, test_settings.data_dir)

    stitcher.ensure_appended(generation_id)
    stitcher.ensure_appended(generation_id)

    artifact = storage.get_continuous_audio_artifact(generation_id)
    assert (test_settings.data_dir / artifact["file_path"]).read_bytes() == b"SEG0SEG1SEG2"
```

- [ ] **Step 3: Implement stitcher**

Create `src/tts_app/continuous_audio.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from tts_app.storage import Storage


class ContinuousAudioStitcher:
    def __init__(self, storage: Storage, data_dir: Path):
        self.storage = storage
        self.data_dir = Path(data_dir)

    def artifact_relative_path(self, generation_id: int) -> str:
        return f"audio/{generation_id}/full.mp3"

    def ensure_appended(self, generation_id: int) -> dict[str, Any]:
        self.storage.get_generation(generation_id)
        segments = self.storage.list_completed_audio_segments_for_stitching(generation_id)
        expected_next = 0
        try:
            artifact = self.storage.get_continuous_audio_artifact(generation_id)
            expected_next = int(artifact["appended_through_segment_index"]) + 1
        except KeyError:
            artifact = None

        relative_path = self.artifact_relative_path(generation_id)
        absolute_path = self.data_dir / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        if artifact is None:
            absolute_path.write_bytes(b"")

        appended = expected_next - 1
        with absolute_path.open("ab") as output:
            for segment in segments:
                index = int(segment["segment_index"])
                if index < expected_next:
                    continue
                if index != expected_next:
                    break
                output.write((self.data_dir / segment["file_path"]).read_bytes())
                appended = index
                expected_next += 1

        byte_size = absolute_path.stat().st_size
        detail = self.storage.get_generation(generation_id)
        status = "completed" if appended + 1 >= len(detail["text_segments"]) and detail["generation"]["status"] == "completed" else "building"
        self.storage.upsert_continuous_audio_artifact(
            generation_id,
            file_path=relative_path,
            mime_type="audio/mpeg",
            status=status,
            appended_through_segment_index=appended,
            byte_size=byte_size,
            error=None,
        )
        return self.storage.get_continuous_audio_artifact(generation_id)
```

- [ ] **Step 4: Run tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_continuous_audio.py tests/test_storage.py::test_list_completed_audio_segments_for_stitching -q
```

Expected: pass.

Commit:

```bash
git add src/tts_app/continuous_audio.py src/tts_app/storage.py tests/test_continuous_audio.py tests/test_storage.py
git commit -m "feat: stitch completed audio segments"
```

## Task 3: Build The Artifact During Generation

**Files:**
- Modify: `src/tts_app/generation.py`
- Test: `tests/test_generation.py`

- [ ] **Step 1: Write failing generation test**

Add:

```python
def test_generation_builds_continuous_audio_artifact(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    service = GenerationService(
        storage=storage,
        provider=FakeTTSProvider(),
        broker=broker,
        audio_dir=test_settings.audio_dir,
        segment_max_chars=8,
    )

    generation_id = anyio.run(service.create_from_text, "One. Two. Three.", "Note", "text", None, "Test", {})
    anyio.run(service.run_generation, generation_id, "Test")

    artifact = storage.get_continuous_audio_artifact(generation_id)
    assert artifact["status"] == "completed"
    assert (test_settings.data_dir / artifact["file_path"]).exists()
    assert artifact["appended_through_segment_index"] >= 0
```

- [ ] **Step 2: Inject and call the stitcher**

Modify `GenerationService.__init__` to create:

```python
from tts_app.continuous_audio import ContinuousAudioStitcher

self.continuous_audio = ContinuousAudioStitcher(storage, self.audio_dir.parent)
```

After `record_audio_segment(...)` in `_run_segment`, call:

```python
self.continuous_audio.ensure_appended(generation_id)
```

After marking a generation completed in `run_generation`, call it once more so the artifact status is finalized:

```python
self.continuous_audio.ensure_appended(generation_id)
```

- [ ] **Step 3: Run tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_generation.py::test_generation_builds_continuous_audio_artifact -q
```

Expected: pass.

Commit:

```bash
git add src/tts_app/generation.py tests/test_generation.py
git commit -m "feat: build continuous audio during generation"
```

## Task 4: Add Continuous Audio API Route

**Files:**
- Modify: `src/tts_app/api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Add:

```python
def test_continuous_audio_endpoint_streams_generation_audio(test_settings):
    app = create_app(settings=test_settings, run_background_inline=True)
    client = TestClient(app)
    generation_id = client.post("/api/generations/text", json={"text": "One. Two.", "title": "Note"}).json()[
        "generation_id"
    ]

    response = client.get(f"/api/generations/{generation_id}/continuous-audio?start_segment=0")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert b"FAKE-TTS" in response.content


def test_continuous_audio_endpoint_rejects_missing_generation(test_settings):
    client = TestClient(create_app(settings=test_settings, run_background_inline=True))

    response = client.get("/api/generations/999/continuous-audio?start_segment=0")

    assert response.status_code == 404
```

- [ ] **Step 2: Implement first-pass route**

Add a route that uses `ContinuousAudioStitcher.ensure_appended()` and `StreamingResponse`.

For the first pass, this route can stream a completed fake generation. Task 6 adds bounded waiting while generation is still running.

```python
@app.get("/api/generations/{generation_id}/continuous-audio")
async def get_continuous_audio(generation_id: int, start_segment: int = 0):
    try:
        detail = storage.get_generation(generation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="generation not found") from exc
    if start_segment < 0 or start_segment >= len(detail["text_segments"]):
        raise HTTPException(status_code=422, detail="start_segment out of range")

    artifact = app.state.service.continuous_audio.ensure_appended(generation_id)
    path = active_settings.data_dir / artifact["file_path"]
    start_offset = sum(
        int(segment["byte_size"])
        for segment in detail["audio_segments"]
        if int(segment["segment_index"]) < start_segment
    )

    def stream_file():
        with path.open("rb") as handle:
            handle.seek(start_offset)
            while True:
                chunk = handle.read(1024 * 256)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(stream_file(), media_type=artifact["mime_type"])
```

- [ ] **Step 3: Run tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_api.py::test_continuous_audio_endpoint_streams_generation_audio tests/test_api.py::test_continuous_audio_endpoint_rejects_missing_generation -q
```

Expected: pass.

Commit:

```bash
git add src/tts_app/api.py tests/test_api.py
git commit -m "feat: add continuous audio endpoint"
```

## Task 5: Switch Frontend Playback To Continuous Audio

**Files:**
- Modify: `src/tts_app/static/playback.js`
- Modify: `src/tts_app/static/app.js`
- Test: `tests/js/playback.test.js`
- Test: `tests/test_frontend_static.py`

- [ ] **Step 1: Add helper tests**

In `tests/js/playback.test.js`, add:

```js
describe("continuousAudioUrl", () => {
  it("builds a stable continuous playback URL from a generation and segment", () => {
    expect(continuousAudioUrl(36, 25)).toBe("/api/generations/36/continuous-audio?start_segment=25");
  });
});
```

- [ ] **Step 2: Implement helper**

In `src/tts_app/static/playback.js`, export:

```js
export function continuousAudioUrl(generationId, segmentIndex) {
  return `/api/generations/${generationId}/continuous-audio?start_segment=${segmentIndex}`;
}
```

- [ ] **Step 3: Update frontend static tests**

In `tests/test_frontend_static.py`, add assertions that generated playback references `continuousAudioUrl` and no longer assigns `/api/audio/${...}` in `playSegment`.

```python
def test_frontend_generated_playback_uses_continuous_audio_endpoint():
    app_js = Path("src/tts_app/static/app.js").read_text(encoding="utf-8")
    assert "continuousAudioUrl" in app_js
    assert "audioPlayer.src = continuousAudioUrl" in app_js
    assert "audioPlayer.src = `/api/audio/" not in app_js
```

- [ ] **Step 4: Update app playback**

Import the helper:

```js
import {
  buildProgressPayload,
  chooseResumeSegmentIndex,
  continuousAudioUrl,
  endedPlaybackAction,
} from "./playback.js?v=continuous-playback-1";
```

In `playSegment`, replace the per-segment URL with:

```js
audioPlayer.src = continuousAudioUrl(state.currentGenerationId, segmentIndex);
saveProgress(segmentIndex);
audioPlayer.play().catch(() => {
  playerStatus.textContent = "Tap Play to start audio";
});
```

In the `ended` handler, remove automatic `playSegment(action.segmentIndex)` for continuous mode. The continuous resource should only end when playback completes or fails.

- [ ] **Step 5: Bump asset versions**

Update JS/CSS query strings in `index.html`, `app.js`, and `ocr.js` to `continuous-playback-1`.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
npm run test:js
.venv/bin/pytest tests/test_frontend_static.py -q
```

Expected: pass.

Commit:

```bash
git add src/tts_app/static/playback.js src/tts_app/static/app.js src/tts_app/static/index.html src/tts_app/static/ocr.js tests/js/playback.test.js tests/test_frontend_static.py
git commit -m "feat: use continuous audio for playback"
```

## Task 6: Add Streaming Wait Behavior And Telemetry

**Files:**
- Modify: `src/tts_app/api.py`
- Modify: `src/tts_app/storage.py`
- Modify: `src/tts_app/static/app.js`
- Modify: `src/tts_app/static/telemetry.js`
- Test: `tests/test_api.py`
- Test: `tests/js/telemetry.test.js`

- [ ] **Step 1: Add backend waiting test**

Add an API test with a generation that has only the first segment completed and a request for the second segment:

```python
def test_continuous_audio_endpoint_returns_409_when_start_segment_not_ready(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "One. Two.", "fake", "Test", {})
    storage.create_text_segments(generation_id, ["One.", "Two."])
    client = TestClient(create_app(test_settings, run_background_inline=True))

    response = client.get(f"/api/generations/{generation_id}/continuous-audio?start_segment=1")

    assert response.status_code == 409
```

Add a second test with a completed generation and a route-level wait timeout set low enough for the test process. It should prove that the completed path still streams bytes:

```python
def test_continuous_audio_endpoint_streams_after_start_segment_exists(test_settings):
    client = TestClient(create_app(settings=test_settings, run_background_inline=True))
    generation_id = client.post("/api/generations/text", json={"text": "One. Two.", "title": "Note"}).json()[
        "generation_id"
    ]

    response = client.get(f"/api/generations/{generation_id}/continuous-audio?start_segment=1")

    assert response.status_code == 200
    assert b"FAKE-TTS" in response.content
```

- [ ] **Step 2: Add content-free telemetry events**

Add event names:

```python
"continuous_audio_selected",
"continuous_audio_waiting",
"continuous_audio_ended",
```

Record `continuous_audio_selected` when the frontend sets a continuous URL. Reuse existing `audio_waiting`, `audio_play`, `audio_error`, and `audio_ended` browser events.

- [ ] **Step 3: Implement bounded tailing in route**

Refactor route file streaming into a generator that:

- opens the artifact
- seeks to the start offset
- yields available bytes
- if EOF is reached and generation is not completed, sleeps briefly and calls `ensure_appended`
- exits when generation is complete and all artifact bytes have been yielded
- exits cleanly on client disconnect

- [ ] **Step 4: Run focused tests and commit**

Run:

```bash
.venv/bin/pytest tests/test_api.py tests/test_storage.py -q
npm run test:js -- tests/js/telemetry.test.js
```

Expected: pass.

Commit:

```bash
git add src/tts_app/api.py src/tts_app/storage.py src/tts_app/static/app.js src/tts_app/static/telemetry.js tests/test_api.py tests/js/telemetry.test.js
git commit -m "feat: tail continuous audio while generating"
```

## Task 7: Verify Mobile Background Playback

**Files:**
- Modify: docs only if observations update the design.

- [ ] **Step 1: Run full automated verification**

Run:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
git diff --check
```

Expected: all pass.

- [ ] **Step 2: Run local server with fake or existing cached generation**

Run:

```bash
TTS_PROVIDER=fake .venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001
```

- [ ] **Step 3: Manual mobile test**

Open a long article on mobile, start playback, background the browser, and confirm:

- the server logs show one continuous audio request instead of one request per segment
- playback crosses at least two segment boundaries while hidden
- telemetry does not show a stall at the first hidden segment boundary

- [ ] **Step 4: Architecture review**

Run the `.codex/agents/architecture-reviewer.toml` agent or simulate `docs/architecture-review-subagent.md`. Fix findings before merge.

- [ ] **Step 5: Final commit or PR update**

If any docs or small fixes were needed after manual verification:

```bash
git add <changed-files>
git commit -m "docs: record continuous playback verification"
```

Then push the branch and open/update the implementation PR.
