# Voice Selection And Sample Cache Design

## Problem

The Generate form spends too much vertical space on voice setup, especially on mobile. It also forgets the user's selected language, voice, and speed after options are re-rendered or the page reloads, so the form falls back to the first/default voice. Voice samples are generated every time the Sample button is pressed, even when the same voice, language, and speed were already sampled.

## Goal

Make voice setup compact by default, remember the last selected voice and speed, and avoid repeated provider calls for identical voice samples.

## Non-Goals

- Do not change provider voice lists or default provider configuration.
- Do not change generated article history semantics.
- Do not store user article text, OCR text, URL content, or provider raw responses in sample cache metadata.
- Do not introduce a frontend framework.
- Do not redesign the full Generate form beyond the voice controls touched here.

## Recommended Approach

Use a compact voice-control summary by default and extract voice behavior into the planned `voice-controls.js` frontend module.

The collapsed state should show only the selected voice label and speed, plus an Edit button. Pressing Edit reveals the full controls:

- language select
- voice select
- preferred voice star
- speed select
- sample button

The expanded state should have a Done button or equivalent control to return to the compact summary. The form should still submit with the selected language, voice, and speed in both states.

Persist the last selected settings in `localStorage` using a small browser-only preference object:

```json
{
  "language": "en",
  "speed": 1.25,
  "voices": {
    "en": "Jennifer",
    "zh": "Cherry"
  }
}
```

Selections are applied only if the API-provided options still contain that language, voice, or speed. If a stored value is stale, fall back to the API default.

Cache voice samples on the backend because that avoids paid provider calls across page reloads, browser sessions, and trusted devices using the same local service. The sample cache key should include:

- provider name
- provider model identity when available
- language
- voice
- speed
- sample text version

The sample text is fixed application text, not user content. Cached files can live under:

```text
data/audio/voice-samples/<cache_key>.mp3
```

The `/api/voice-sample` route should keep the same request and response shape. On cache hit it should return the cached audio file. On cache miss it should stream from the provider into a temporary file, atomically move the completed file into the cache path, and return the bytes. If generation fails, no partial cache file should remain.

## Frontend Behavior

The voice controls should be moved out of `app.js` into `src/tts_app/static/voice-controls.js` with a narrow API:

- render options from `state.options`
- expose current payload values for generation and OCR
- update the compact summary
- persist language, voice, and speed selections
- handle preference toggles
- handle sample playback with the existing global audio element
- clear sample playback without affecting generation playback

`app.js` and `ocr.js` should depend on exported helpers for language, voice, speed, sample playback, and sample cleanup. This is an incremental split, not a full frontend rewrite.

## Backend Behavior

Add a focused backend helper module for sample caching. It should:

- compute a stable cache key from content-free settings and a sample text version
- write cache misses to a temp file under the sample cache directory
- atomically replace the cache file after provider streaming succeeds
- return cached bytes with `audio/mpeg`
- leave no partial file after provider errors

The route can remain in `api.py` for this pass because the public voice API is still small, but the cache logic should not live inline in the route.

## Data And Cleanup

Voice sample cache files are derived app cache, not user-authored data. They do not need generation history rows and should not appear in History. They should not be removed by generation deletion. A future cache-management flow can clear `data/audio/voice-samples/` if disk usage becomes a concern.

## Testing Strategy

Backend tests should verify:

- first sample request calls the provider and writes a cache file
- repeated identical sample requests return the same audio without calling the provider again
- different speed, voice, or language uses a different cache entry
- provider failure does not leave a final cache file

Frontend tests should verify:

- voice controls are collapsible and default collapsed in HTML
- the new `voice-controls.js` module is imported with cache-busting query strings
- changing language/voice/speed saves a last-selection preference
- option rendering prefers stored selections when valid
- stale stored selections fall back to API defaults
- sample playback still marks `state.samplePlayback` and does not record generation playback telemetry

Run the full verification set before opening the PR:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
git diff --check
```
