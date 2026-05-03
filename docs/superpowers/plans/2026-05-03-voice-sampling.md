# Voice Sampling Implementation Plan

## Goal

Let a user preview the currently selected voice, language, and speed from the
Generate page before creating a full generation.

## Scope

- Add a `POST /api/voice-sample` endpoint that streams a short built-in sample
  script through the configured TTS provider.
- Use a language-specific sample script for English and Chinese.
- Do not persist sample requests to generation history and do not cache sample
  audio in the normal generation audio directory.
- Add a lightweight `Sample` button beside the voice controls.
- Stop any active generation playback before sample playback starts.
- Keep sample playback state isolated so the normal ended handler does not save
  generation progress or continue to the next segment.
- Revoke generated object URLs after sample playback or when playback is stopped.

## Tests

- API test: sample endpoint returns audio with requested voice, speed, and
  language without creating history.
- API test: Chinese samples use the Chinese sample script and provider language.
- Frontend static tests: Sample button and endpoint are wired.
- Frontend static tests: sample playback state revokes object URLs and bypasses
  generation progress on `ended`.
- Syntax check: `node --check src/tts_app/static/app.js`.
