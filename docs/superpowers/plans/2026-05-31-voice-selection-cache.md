# Voice Selection And Sample Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make voice controls compact by default, remember the user's last selected language/voice/speed, and cache repeated voice sample audio.

**Architecture:** Extract voice UI behavior into `voice-controls.js` and keep `app.js` as orchestration. Persist browser voice preferences in `localStorage`, validating stored values against API options before applying them. Add a backend sample-cache helper so `/api/voice-sample` can reuse local MP3 files without creating History rows.

**Tech Stack:** FastAPI, deterministic fake providers, plain JavaScript modules, localStorage, pytest, Vitest, static frontend tests.

---

## File Structure

- Create `src/tts_app/voice_samples.py`: backend cache key, cache path, temp-file write, provider streaming, and cached response bytes.
- Modify `src/tts_app/api.py`: delegate `/api/voice-sample` to `VoiceSampleCache`.
- Modify `src/tts_app/static/index.html`: wrap voice controls in collapsed/expanded containers and bump static asset version.
- Modify `src/tts_app/static/dom.js`: export voice panel, summary, edit, and done elements.
- Create `src/tts_app/static/voice-controls.js`: render language/voice/speed options, persist selections, toggle collapsed state, preference updates, and sample playback.
- Modify `src/tts_app/static/app.js`: import voice helpers and remove direct voice-control rendering/sample code.
- Modify `src/tts_app/static/ocr.js`: use voice helper payload values for OCR generation.
- Modify `src/tts_app/static/state.js`: add voice sample cache state only if needed by the frontend helper.
- Add tests in `tests/test_api.py`, `tests/test_frontend_static.py`, and `tests/js/voice-controls.test.js`.

## Task 1: Backend Voice Sample Cache

**Files:**
- Create: `src/tts_app/voice_samples.py`
- Modify: `src/tts_app/api.py`
- Test: `tests/test_api.py`

- [ ] Write failing API tests:
  - repeated identical `/api/voice-sample` requests call the provider once
  - different speed creates a second cache entry
  - provider failure returns an error and leaves no final cached file
- [ ] Run focused tests and confirm they fail:
  - `.venv/bin/pytest tests/test_api.py::test_voice_sample_reuses_cached_audio tests/test_api.py::test_voice_sample_cache_key_includes_speed tests/test_api.py::test_voice_sample_failure_does_not_cache_partial_file -q`
- [ ] Implement `VoiceSampleCache` with atomic temp-file replacement and content-free cache keys.
- [ ] Update `/api/voice-sample` to call the cache helper while preserving the existing response media type.
- [ ] Run focused API tests and commit:
  - `git commit -m "feat: cache voice sample audio"`

## Task 2: Voice Controls Module And Persistence

**Files:**
- Create: `src/tts_app/static/voice-controls.js`
- Modify: `src/tts_app/static/app.js`
- Modify: `src/tts_app/static/dom.js`
- Modify: `src/tts_app/static/ocr.js`
- Test: `tests/js/voice-controls.test.js`
- Test: `tests/test_frontend_static.py`

- [ ] Write failing Vitest tests for pure helpers:
  - stored language/voice/speed values are applied only when valid
  - stale stored values fall back to API defaults
  - selection persistence stores voices per language
- [ ] Run `npm run test:js -- tests/js/voice-controls.test.js` and confirm failure.
- [ ] Move voice option rendering, current language, selected voice lookup, preference toggling, sample playback, and sample clearing into `voice-controls.js`.
- [ ] Update `app.js` and `ocr.js` to use exported helpers for generation payload values and sample clearing.
- [ ] Run focused JS tests and commit:
  - `git commit -m "refactor: extract voice controls"`

## Task 3: Collapsed Voice UI

**Files:**
- Modify: `src/tts_app/static/index.html`
- Modify: `src/tts_app/static/styles.css`
- Modify: `src/tts_app/static/dom.js`
- Modify: `src/tts_app/static/voice-controls.js`
- Test: `tests/test_frontend_static.py`

- [ ] Write failing static tests that assert:
  - the compact voice summary exists and is visible by default
  - the expanded voice controls are hidden by default
  - Edit and Done controls are wired in `voice-controls.js`
  - the static asset version changed from `continuous-playback-1`
- [ ] Run focused static tests and confirm failure.
- [ ] Implement the collapsed/expanded markup and styles with a compact summary row showing selected voice and speed.
- [ ] Wire Edit/Done to toggle expanded state without changing current selections.
- [ ] Run focused static tests and commit:
  - `git commit -m "feat: collapse voice controls"`

## Task 4: Verification, Architecture Review, And PR

**Files:**
- Modify only if verification exposes issues.

- [ ] Run full verification:
  - `.venv/bin/pytest -q`
  - `npm run check:js`
  - `npm run lint:js`
  - `npm run test:js`
  - `git diff --check`
- [ ] Run the custom architecture reviewer from `.codex/agents/architecture-reviewer.toml`; if the agent cannot be spawned, simulate the same checklist from `docs/architecture-review-subagent.md`.
- [ ] Fix any blocking findings and rerun the relevant checks.
- [ ] Push `codex/voice-selection-cache`.
- [ ] Open a draft PR against `main` with the spec, plan, implementation summary, and verification results.
