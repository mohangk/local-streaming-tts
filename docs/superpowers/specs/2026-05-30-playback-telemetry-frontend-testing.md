# Playback Telemetry Frontend Testing

## Summary

Playback telemetry will add more client-side behavior around audio state, progress events, resumed playback, and user interaction timing. Before that work grows, the frontend test strategy should move beyond static string checks toward executable JavaScript tests.

## Current Step

Add ESLint as the first frontend quality gate. The immediate goal is to catch module-scope mistakes such as undefined identifiers, missing imports, and unused imports in the vanilla JavaScript modules.

## Future Testing Layers

### Vitest with jsdom

Use Vitest for module-level and interaction tests that can run without a browser:

- Import `app.js` and OCR/playback modules in a jsdom document.
- Mock `fetch`, `EventSource`, `URL.createObjectURL`, and `HTMLMediaElement` methods.
- Exercise click handlers instead of asserting only that handler text exists.
- Cover playback telemetry state transitions:
  - opening a generation resumes the saved segment;
  - segment-end progression records progress once;
  - sample playback does not write generation progress;
  - stale generation detail loads do not overwrite current playback state;
  - telemetry events are emitted only for generation audio, not voice samples.

### Playwright Smoke Tests

Use a tiny browser-level suite after Vitest is in place:

- Start the app with the fake provider.
- Load the Generate view and verify no console errors.
- Generate text audio and confirm Playback renders segments.
- Reopen from History and confirm saved progress is respected.
- For OCR, use fake OCR and verify Generate audio sends one generation request from reviewed text.

## Non-Goals

- Do not replace FastAPI/API pytest coverage.
- Do not introduce a frontend framework as part of testing.
- Do not build a large end-to-end suite; keep Playwright limited to high-value smoke paths.

## Verification Direction

The eventual frontend verification command should become:

```bash
npm run check:js
npm run lint:js
npm run test:js
```

Playwright should be a separate smoke command because it starts the app and is slower.
