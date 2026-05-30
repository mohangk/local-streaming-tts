# Playback Telemetry Frontend Testing

## Summary

Playback telemetry will add more client-side behavior around audio state, progress events, resumed playback, and user interaction timing. Before adding telemetry, the frontend needs a small executable JavaScript test layer and a bounded playback/progress extraction from `app.js`.

This spec intentionally separates the refactor/testing foundation from the later telemetry feature. The next implementation pass should not add new telemetry events. It should preserve existing playback behavior while making the behavior testable with Vitest.

## Telemetry Purpose

The telemetry feature exists to diagnose a specific mobile playback failure: when a long article is playing and the phone or browser puts Readvox into the background, playback sometimes stops before the generation is finished. The goal is not to guess at a fix first. The goal is to capture enough local evidence to explain where playback stopped and why, then use that evidence to choose better fixes.

Future telemetry should help answer questions such as:

- Was the page hidden, frozen, discarded, unloaded, or merely backgrounded?
- Was the audio element playing, paused, ended, stalled, waiting, suspended, or errored?
- Was playback in a generated segment or a voice sample?
- Which generation, segment index, and audio segment were active when playback stopped?
- Did the app still hold or lose a wake lock?
- Did an EventSource disconnect, network transition, or generation refresh happen near the stop?
- Did Readvox attempt to save progress, continue to the next segment, or mark completion?

Telemetry should be local-first and diagnostic. It should avoid collecting article text or source content unless a later design explicitly justifies that. Segment indexes, generation IDs, timestamps, browser lifecycle events, audio element event names, visibility state, and coarse user-agent/platform context are more useful and less sensitive than content.

## Current Step

Add Vitest with jsdom and extract existing playback/progress decision logic into a small module. This is the first architecture slice toward the frontend modularization direction in `docs/architecture.md`.

The current `app.js` is responsible for navigation, form submission, history rendering, voice controls, playback, progress saving, and event-source handling. Playback telemetry would make that coupling worse if added directly. The first slice should move the logic that can be tested without a real browser or audio stack.

## Goals

- Add `npm run test:js` using Vitest and jsdom.
- Keep `npm run check:js` and `npm run lint:js`.
- Create a focused playback module with existing behavior only.
- Preserve current browser behavior and static frontend entrypoints.
- Add Vitest tests for playback/progress decisions that are currently only covered by static string assertions.
- Keep static tests during the transition; do not remove broad static coverage in this pass.

## Non-Goals

- Do not add playback telemetry events in this pass.
- Do not add Playwright in this pass.
- Do not introduce a frontend framework.
- Do not split every `app.js` responsibility at once.
- Do not change backend progress APIs or storage schema.

## Frontend Refactor Shape

Create a small playback/progress module first, rather than a broad rewrite:

- `src/tts_app/static/playback.js`
  - Pure or low-DOM helper functions for existing playback behavior.
  - Candidate functions:
    - choose the saved resume segment within valid bounds;
    - decide whether an ended generation segment should save completed progress;
    - decide whether ended voice sample playback should skip generation progress;
    - build a progress request payload.

Keep `app.js` as the orchestrator for now. It should import helpers from `playback.js`, but it can continue owning DOM updates, audio element calls, EventSource wiring, navigation, and history rendering until later slices.

This bounded split starts the path toward the larger modular direction:

- `playback.js` for audio queue/progress decisions;
- later `history.js` for history rendering and actions;
- later `generation-form.js` for input modes and submit payloads;
- later `voice-controls.js` for language, voice, speed, preference, and sample playback;
- later `api-client.js` for fetch/error helpers.

## Vitest Layer

Use Vitest for module-level tests that do not start FastAPI and do not require a real browser:

- Test pure playback/progress helper functions directly.
- Use jsdom as the default test environment so later modules can exercise DOM behavior.
- Mock browser APIs only when a test needs them.
- Prefer executable behavior tests over static string assertions for new frontend logic.

Initial Vitest coverage should pin existing behavior:

- opening a generation resumes the saved segment, clamped to available text segments;
- missing or invalid saved progress resumes segment `0`;
- ending a voice sample clears sample state but does not save generation progress;
- ending the final generation segment asks to save completed progress once;
- intermediate ended segments continue playback without marking the generation complete;
- progress payloads include `segment_index` and only set `completed` when requested.

## Later Telemetry Feature

After this foundation lands, a separate telemetry feature can add new diagnostic behavior for mobile background playback stops. That future design should define:

- telemetry event names and payloads;
- the minimum event stream needed to reconstruct why long-article playback stopped;
- browser/page lifecycle events to capture, such as visibility, freeze/resume, pagehide/pageshow, and unload-adjacent events that are available on target mobile browsers;
- audio element events to capture, such as play, pause, ended, waiting, stalled, suspend, error, and timeupdate checkpoints if needed;
- wake lock state and failures around backgrounding;
- current generation ID, segment index, audio segment ID, and playback mode at each diagnostic event;
- which playback states are persisted locally vs sent to the backend;
- whether telemetry is stored in SQLite or only logged;
- privacy and local-only assumptions;
- how much telemetry is retained and how it is cleared;
- tests proving telemetry is emitted only for generation audio, not voice samples.

## Verification Direction

The frontend verification command should become:

```bash
npm run check:js
npm run lint:js
npm run test:js
```

Project completion still requires:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
```

Playwright should remain a separate future smoke command because it starts the app and is slower.
