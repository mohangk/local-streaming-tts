# Playback Vitest Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Vitest/jsdom and extract existing playback/progress decision logic from `app.js` into a small tested module without adding telemetry behavior.

**Architecture:** Keep `app.js` as the browser orchestrator for now. Create `src/tts_app/static/playback.js` for pure playback/progress decisions that can be tested without a real audio element or FastAPI server. Preserve current playback behavior while establishing the first modular frontend testing slice described in `docs/architecture.md`.

**Tech Stack:** Vanilla ES modules, Vitest, jsdom, existing ESLint flat config, pytest docs/static tests.

---

## File Structure

- Modify `package.json`: add `test:js` script and Vitest/jsdom dev dependencies.
- Modify `eslint.config.js`: lint static JS and Vitest test files with appropriate browser/test globals.
- Create `src/tts_app/static/playback.js`: pure helpers for resume index, progress payloads, and ended-audio decisions.
- Modify `src/tts_app/static/app.js`: import playback helpers and replace inline decision logic while keeping DOM/audio orchestration in `app.js`.
- Create `tests/js/playback.test.js`: Vitest unit tests for playback helpers.
- Modify `tests/test_frontend_static.py`: ensure `playback.js` is included in static checks and app imports the helper module.
- Modify `tests/test_docs.py`: pin `npm run test:js` in architecture/docs verification guidance if needed.
- Modify `docs/architecture.md`: add `npm run test:js` to standard verification commands after Vitest lands.
- Modify `docs/superpowers/specs/2026-05-30-playback-telemetry-frontend-testing.md`: already updated to separate refactor from telemetry; only touch if implementation details change.

## Task 1: Add Vitest Script And Empty Harness

**Files:**
- Modify: `package.json`
- Modify: `eslint.config.js`
- Create: `tests/js/playback.test.js`

- [ ] **Step 1: Update `package.json` with Vitest**

Change `package.json` to include `test:js` and dev dependencies:

```json
{
  "name": "readvox-frontend-checks",
  "private": true,
  "type": "module",
  "scripts": {
    "lint:js": "eslint src/tts_app/static/**/*.js tests/js/**/*.js",
    "check:js": "node --check src/tts_app/static/app.js && node --check src/tts_app/static/ocr.js && node --check src/tts_app/static/utils.js && node --check src/tts_app/static/dom.js && node --check src/tts_app/static/state.js",
    "test:js": "vitest run --environment jsdom"
  },
  "devDependencies": {
    "@eslint/js": "^10.0.1",
    "eslint": "^10.4.1",
    "jsdom": "^27.2.0",
    "vitest": "^4.0.14"
  }
}
```

- [ ] **Step 2: Run install to refresh lockfile**

Run:

```bash
npm install
```

Expected: `package-lock.json` updates with `vitest` and `jsdom` dependencies.

- [ ] **Step 3: Update ESLint globals for tests**

In `eslint.config.js`, keep the existing browser config and add a second config block for `tests/js/**/*.js`:

```js
const testGlobals = {
  afterEach: "readonly",
  describe: "readonly",
  expect: "readonly",
  it: "readonly",
  vi: "readonly",
};

export default [
  {
    ignores: ["node_modules/**"],
  },
  {
    files: ["src/tts_app/static/**/*.js"],
    ...eslint.configs.recommended,
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: browserGlobals,
    },
    rules: {
      ...eslint.configs.recommended.rules,
      "no-undef": "error",
    },
  },
  {
    files: ["tests/js/**/*.js"],
    ...eslint.configs.recommended,
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...browserGlobals, ...testGlobals },
    },
    rules: {
      ...eslint.configs.recommended.rules,
      "no-undef": "error",
    },
  },
];
```

- [ ] **Step 4: Create a smoke Vitest file**

Create `tests/js/playback.test.js`:

```js
import { describe, expect, it } from "vitest";

describe("playback helpers", () => {
  it("runs in jsdom", () => {
    const marker = document.createElement("div");
    marker.textContent = "Readvox";
    document.body.append(marker);

    expect(document.body.textContent).toContain("Readvox");
  });
});
```

- [ ] **Step 5: Verify new JS test script passes**

Run:

```bash
npm run test:js
```

Expected: PASS with `1` test.

- [ ] **Step 6: Verify lint includes tests**

Run:

```bash
npm run lint:js
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add package.json package-lock.json eslint.config.js tests/js/playback.test.js
git commit -m "test: add Vitest frontend harness"
```

## Task 2: Add Playback Helper Tests First

**Files:**
- Modify: `package.json`
- Replace: `tests/js/playback.test.js`
- Create: `src/tts_app/static/playback.js`

- [ ] **Step 1: Replace smoke test with expected helper behavior**

Replace `tests/js/playback.test.js` with:

```js
import { describe, expect, it } from "vitest";
import {
  buildProgressPayload,
  chooseResumeSegmentIndex,
  endedPlaybackAction,
} from "../../src/tts_app/static/playback.js";

describe("chooseResumeSegmentIndex", () => {
  it("clamps saved progress into the available text segment range", () => {
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: 2, totalSegments: 5 })).toBe(2);
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: 99, totalSegments: 5 })).toBe(4);
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: -4, totalSegments: 5 })).toBe(0);
  });

  it("resumes at zero for missing, invalid, or empty generation progress", () => {
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: undefined, totalSegments: 5 })).toBe(0);
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: Number.NaN, totalSegments: 5 })).toBe(0);
    expect(chooseResumeSegmentIndex({ lastSegmentIndex: 2, totalSegments: 0 })).toBe(0);
  });
});

describe("buildProgressPayload", () => {
  it("includes segment index and defaults completed to false", () => {
    expect(buildProgressPayload(3)).toEqual({ segment_index: 3, completed: false });
  });

  it("sets completed only when requested", () => {
    expect(buildProgressPayload(3, { completed: true })).toEqual({ segment_index: 3, completed: true });
  });
});

describe("endedPlaybackAction", () => {
  it("clears sample playback without saving generation progress", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: true,
        continuousPlayback: true,
        currentSegmentIndex: 0,
        totalSegments: 3,
      }),
    ).toEqual({ type: "clear-sample" });
  });

  it("continues to the next segment during continuous generation playback", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: false,
        continuousPlayback: true,
        currentSegmentIndex: 0,
        totalSegments: 3,
      }),
    ).toEqual({ type: "play-next", segmentIndex: 1 });
  });

  it("marks progress completed only at the final generation segment", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: false,
        continuousPlayback: false,
        currentSegmentIndex: 2,
        totalSegments: 3,
      }),
    ).toEqual({ type: "complete", segmentIndex: 2 });
  });

  it("stops without completion for intermediate non-continuous segments", () => {
    expect(
      endedPlaybackAction({
        samplePlayback: false,
        continuousPlayback: false,
        currentSegmentIndex: 1,
        totalSegments: 3,
      }),
    ).toEqual({ type: "stop" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm run test:js
```

Expected: FAIL because `src/tts_app/static/playback.js` or named exports do not exist.

- [ ] **Step 3: Create minimal playback helper module**

Create `src/tts_app/static/playback.js`:

```js
export function chooseResumeSegmentIndex({ lastSegmentIndex, totalSegments }) {
  const total = Number(totalSegments || 0);
  if (!Number.isFinite(total) || total <= 0) {
    return 0;
  }
  const saved = Number(lastSegmentIndex || 0);
  if (!Number.isFinite(saved)) {
    return 0;
  }
  return Math.min(Math.max(saved, 0), total - 1);
}

export function buildProgressPayload(segmentIndex, options = {}) {
  return {
    segment_index: segmentIndex,
    completed: Boolean(options.completed),
  };
}

export function endedPlaybackAction({ samplePlayback, continuousPlayback, currentSegmentIndex, totalSegments }) {
  if (samplePlayback) {
    return { type: "clear-sample" };
  }

  const nextIndex = currentSegmentIndex + 1;
  if (continuousPlayback && nextIndex < totalSegments) {
    return { type: "play-next", segmentIndex: nextIndex };
  }

  if (totalSegments > 0 && currentSegmentIndex >= totalSegments - 1) {
    return { type: "complete", segmentIndex: currentSegmentIndex };
  }

  return { type: "stop" };
}
```

- [ ] **Step 4: Run Vitest**

Run:

```bash
npm run test:js
```

Expected: PASS.

- [ ] **Step 5: Add `playback.js` to `check:js` after the file exists**

Change `package.json` to include `src/tts_app/static/playback.js` in the parse check:

```json
"check:js": "node --check src/tts_app/static/app.js && node --check src/tts_app/static/ocr.js && node --check src/tts_app/static/playback.js && node --check src/tts_app/static/utils.js && node --check src/tts_app/static/dom.js && node --check src/tts_app/static/state.js"
```

- [ ] **Step 6: Run parse check**

Run:

```bash
npm run check:js
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add package.json src/tts_app/static/playback.js tests/js/playback.test.js
git commit -m "test: cover playback progress decisions"
```

## Task 3: Wire Playback Helpers Into `app.js`

**Files:**
- Modify: `src/tts_app/static/app.js`
- Modify: `src/tts_app/static/index.html`
- Modify: `src/tts_app/static/ocr.js`
- Modify: `tests/test_frontend_static.py`

- [ ] **Step 1: Add static tests for playback module import**

In `tests/test_frontend_static.py`, update `JS_FILES`:

```python
JS_FILES = ("app.js", "ocr.js", "playback.js", "state.js", "dom.js", "utils.js")
```

Add a test near the playback static tests:

```python
def test_frontend_imports_playback_helpers():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    playback_js = (STATIC_DIR / "playback.js").read_text(encoding="utf-8")

    assert 'from "./playback.js?v=' in app_js
    assert "chooseResumeSegmentIndex" in app_js
    assert "buildProgressPayload" in app_js
    assert "endedPlaybackAction" in app_js
    assert "export function chooseResumeSegmentIndex" in playback_js
    assert "export function buildProgressPayload" in playback_js
    assert "export function endedPlaybackAction" in playback_js
```

Add an asset-version test near the import test:

```python
def test_frontend_static_asset_version_bumped_for_playback_module():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    ocr_js = (STATIC_DIR / "ocr.js").read_text(encoding="utf-8")

    assert 'href="/static/styles.css?v=playback-vitest-1"' in html
    assert 'src="/static/app.js?v=playback-vitest-1"' in html
    assert "?v=playback-vitest-1" in app_js
    assert "?v=playback-vitest-1" in ocr_js
    assert "ocr-generate-fix-1" not in html
    assert "ocr-generate-fix-1" not in app_js
    assert "ocr-generate-fix-1" not in ocr_js
```

- [ ] **Step 2: Run static test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_imports_playback_helpers -q
```

Expected: FAIL because `app.js` does not import `playback.js` yet.

- [ ] **Step 3: Import helpers in `app.js`**

Add this import after the existing `ocr.js` import:

```js
import {
  buildProgressPayload,
  chooseResumeSegmentIndex,
  endedPlaybackAction,
} from "./playback.js?v=playback-vitest-1";
```

- [ ] **Step 4: Bump static asset version tokens**

Use `playback-vitest-1` for local static module imports and HTML asset references touched by this compatibility change:

- In `src/tts_app/static/index.html`, change `/static/styles.css?v=ocr-generate-fix-1` and `/static/app.js?v=ocr-generate-fix-1` to `?v=playback-vitest-1`.
- In `src/tts_app/static/app.js`, update local imports from `?v=ocr-generate-fix-1` to `?v=playback-vitest-1`.
- In `src/tts_app/static/ocr.js`, update local imports from `?v=ocr-generate-fix-1` to `?v=playback-vitest-1`.

- [ ] **Step 5: Replace resume-index logic**

In `loadGenerationDetail`, replace:

```js
if (detail.text_segments.length > 0) {
  const savedIndex = Number(detail.generation.last_segment_index || 0);
  state.currentSegmentIndex = Math.min(Math.max(savedIndex, 0), detail.text_segments.length - 1);
}
```

with:

```js
state.currentSegmentIndex = chooseResumeSegmentIndex({
  lastSegmentIndex: detail.generation.last_segment_index,
  totalSegments: detail.text_segments.length,
});
```

- [ ] **Step 6: Replace progress payload construction**

In `saveProgress`, replace:

```js
body: JSON.stringify({ segment_index: segmentIndex, completed: Boolean(options.completed) }),
```

with:

```js
body: JSON.stringify(buildProgressPayload(segmentIndex, options)),
```

- [ ] **Step 7: Replace ended-handler decision logic**

In the `audioPlayer.addEventListener("ended", ...)` handler, replace the decision branches with:

```js
const action = endedPlaybackAction({
  samplePlayback: state.samplePlayback,
  continuousPlayback: state.continuousPlayback,
  currentSegmentIndex: state.currentSegmentIndex,
  totalSegments: state.currentDetail?.text_segments.length || 0,
});

if (action.type === "clear-sample") {
  audioPlayer.pause();
  audioPlayer.removeAttribute("src");
  audioPlayer.load();
  clearSamplePlayback();
  releaseWakeLock();
  return;
}

if (action.type === "play-next") {
  playSegment(action.segmentIndex);
  return;
}

if (action.type === "complete") {
  saveProgress(action.segmentIndex, { completed: true });
}

state.continuousPlayback = false;
releaseWakeLock();
```

- [ ] **Step 8: Update existing ended-handler static tests**

Update `tests/test_frontend_static.py::test_frontend_ended_handler_skips_generation_progress_for_samples` so it verifies the new action-based branch and still proves sample playback does not save generation progress:

```python
def test_frontend_ended_handler_skips_generation_progress_for_samples():
    js = frontend_js()
    handler = js.split('audioPlayer.addEventListener("ended"', 1)[1].split("document.addEventListener", 1)[0]
    sample_branch = handler.split('if (action.type === "play-next")', 1)[0]

    assert "endedPlaybackAction({" in handler
    assert "samplePlayback: state.samplePlayback" in handler
    assert 'action.type === "clear-sample"' in sample_branch
    assert "clearSamplePlayback()" in sample_branch
    assert "return" in sample_branch
    assert "saveProgress" not in sample_branch
```

Update `tests/test_frontend_static.py::test_frontend_javascript_ended_handler_respects_continuous_playback` so it checks the helper result instead of old local `nextIndex` code:

```python
def test_frontend_javascript_ended_handler_respects_continuous_playback():
    js = frontend_js()
    handler = js.split('audioPlayer.addEventListener("ended"', 1)[1].split("loadHistory();", 1)[0]

    assert "continuousPlayback: state.continuousPlayback" in handler
    assert 'action.type === "play-next"' in handler
    assert "playSegment(action.segmentIndex)" in handler
```

- [ ] **Step 9: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_frontend_static.py::test_frontend_imports_playback_helpers tests/test_frontend_static.py::test_frontend_static_asset_version_bumped_for_playback_module tests/test_frontend_static.py::test_frontend_history_autoplay_resumes_saved_segment tests/test_frontend_static.py::test_frontend_ended_handler_skips_generation_progress_for_samples tests/test_frontend_static.py::test_frontend_javascript_ended_handler_respects_continuous_playback tests/test_frontend_static.py::test_frontend_playback_updates_progress -q
npm run test:js
```

Expected: PASS.

- [ ] **Step 10: Run JS checks**

Run:

```bash
npm run check:js
npm run lint:js
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add src/tts_app/static/app.js src/tts_app/static/index.html src/tts_app/static/ocr.js tests/test_frontend_static.py
git commit -m "refactor: extract playback progress decisions"
```

## Task 4: Update Verification Documentation

**Files:**
- Modify: `docs/architecture.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `tests/test_docs.py`

- [ ] **Step 1: Add docs tests for `npm run test:js`**

In `tests/test_docs.py`, add assertions in `test_handoff_docs_exist_and_cover_local_operations`:

```python
assert "npm run test:js" in readme
assert "npm run test:js" in agents
assert "npm run test:js" in architecture
```

- [ ] **Step 2: Run docs test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_docs.py::test_handoff_docs_exist_and_cover_local_operations -q
```

Expected: FAIL until docs mention the new command.

- [ ] **Step 3: Update `AGENTS.md` local commands**

Change the test command block to:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
```

- [ ] **Step 4: Update `README.md` verification blocks**

Where README lists frontend verification commands, include:

```bash
npm run test:js
```

Keep `check:js` and `lint:js`.

- [ ] **Step 5: Update `docs/architecture.md` testing commands**

Change the architecture verification command block to:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
```

- [ ] **Step 6: Run docs test**

Run:

```bash
.venv/bin/pytest tests/test_docs.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md README.md docs/architecture.md tests/test_docs.py
git commit -m "docs: add frontend unit test command"
```

## Task 5: Final Verification And Architecture Review

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
- `check:js`: all static modules parse, including `playback.js`.
- `lint:js`: source and Vitest tests lint cleanly.
- `test:js`: Vitest playback helper tests pass.
- `git diff --check`: no whitespace errors.

- [ ] **Step 2: Run architecture reviewer**

Spawn the project custom agent:

```text
Use the architecture_reviewer custom agent to review the current diff against docs/architecture.md, AGENTS.md, docs/architecture-review-subagent.md, .codex/agents/architecture-reviewer.toml, and relevant tests. Focus on frontend modularity, test-layer ownership, and whether this pass avoids adding telemetry behavior.
```

Expected: no high-risk findings. Fix any valid findings before continuing.

- [ ] **Step 3: Review commit history**

Run:

```bash
git log --oneline --max-count=6
```

Expected: recent commits tell this story:

- Vitest harness.
- Playback progress decision extraction.
- Verification docs.

- [ ] **Step 4: Push**

If working directly on `main` and the branch is up to date:

```bash
git push origin HEAD:main
```

If working on a feature branch, push the branch and open a PR.
