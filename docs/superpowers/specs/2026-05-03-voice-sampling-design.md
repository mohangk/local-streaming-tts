# Voice Sampling Design

Date: 2026-05-03

## Summary

Add a lightweight `Sample` action on the Generate page so users can preview
the selected voice, language, and speed before creating a full generation.

## Flow

1. User chooses language, voice, and speed on the Generate page.
2. User taps `Sample`.
3. Frontend stops any active generation playback and clears the current audio
   buffer.
4. Frontend sends `{ voice, speed, language }` to `POST /api/voice-sample`.
5. Backend synthesizes a fixed short script through the active TTS provider.
6. Backend streams audio chunks back without creating history, text segments,
   cached generation audio, or playback progress.
7. Frontend plays the returned audio blob and revokes its object URL when
   playback ends or is stopped.

## Sample Text

Use language-specific scripts:

- English: a short Readvox voice sample that checks voice, pacing, clarity, and
  listening comfort.
- Chinese: a short Readvox voice sample in Chinese text for the same listening
  checks.

## API

`POST /api/voice-sample`

Request:

```json
{
  "voice": "Jennifer",
  "speed": 1.0,
  "language": "en"
}
```

Response:

- `200 OK`
- `Content-Type: audio/mpeg`
- streamed provider audio bytes

Validation:

- `voice` is required.
- `speed` uses the same accepted range as normal generation.
- unsupported languages fall back to the English sample text and automatic
  provider language label.

## Frontend

- Add a `Sample` button near the Generate page voice controls.
- Reuse the existing hidden audio element.
- Keep sample playback state separate from generation playback state.
- Do not save generation progress or advance to the next text segment when a
  sample ends.
- Stop sample playback before page navigation or normal generation playback.

## Tests

- API: sample endpoint returns audio with the requested voice, speed, and
  language.
- API: sample endpoint does not create history or cached generation audio.
- API: Chinese language uses the Chinese sample script.
- Frontend static: Sample button exists and calls `/api/voice-sample`.
- Frontend static: sample playback state revokes object URLs and bypasses
  generation progress updates.
