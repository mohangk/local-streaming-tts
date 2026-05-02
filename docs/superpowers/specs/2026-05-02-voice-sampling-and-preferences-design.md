# Voice Sampling And Preferences Design

Date: 2026-05-02

## Summary

Add two small Generate-page improvements after the current playback fixes are complete:

- A `Sample` button that plays a short predefined script using the selected voice and speed before creating a full generation.
- A preferred-voice toggle, shown as a star, that lets preferred voices appear first in the voice selector.

## Voice Sampling

Use a backend sample endpoint rather than creating a normal generation. This keeps sample playback out of History and avoids storing sample text, segments, or cached generation audio.

Proposed flow:

1. User chooses a voice and speed on the Generate page.
2. User taps `Sample`.
3. Frontend stops any current playback and sends `{ voice, speed }` to `POST /api/voice-sample`.
4. Backend uses the active TTS provider to synthesize a fixed short script.
5. Backend streams audio back as the provider emits chunks.
6. Frontend plays the sample audio and restores the button state when playback ends or fails.

Suggested sample script:

> This is a short Readvox voice sample. Use it to check the voice, pacing, clarity, and listening comfort before generating the full article.

The sample endpoint should not create a generation, text segments, History item, cached audio, or progress record.

## Preferred Voices

Persist preferred voices in SQLite so the preference follows the local app across browser sessions and devices.

Proposed storage:

- `voice_preferences`
  - `voice TEXT PRIMARY KEY`
  - `preferred INTEGER NOT NULL DEFAULT 0`
  - `updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`

Proposed API:

- `GET /api/options`: include `preferred: true/false` on each voice option and return preferred voices first.
- `PUT /api/voices/{voice}/preference`: accept `{ preferred: true/false }` and update the local preference.

Proposed frontend:

- Add a small star button next to the voice selector.
- Tapping the star toggles preference for the currently selected voice.
- Preferred voices render first in the dropdown, marked with a star in the label.
- The selected voice should remain selected when options are re-sorted.

## Testing

Add failing tests before implementation:

- API test for `POST /api/voice-sample` returning provider audio with the requested voice and speed.
- Storage/API tests for saving, unsetting, and returning preferred voice state.
- Frontend static tests for the Sample button, star control, sample fetch call, and preferred-first sorting.

