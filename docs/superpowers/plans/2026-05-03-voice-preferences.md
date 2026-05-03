# Voice Preferences Implementation Plan

## Summary

Implement language-aware voice selection and language-scoped preferred voices. This plan is for the standalone voice preference work merged before the image OCR transcription branch.

## Scope

- Add language metadata to voice options.
- Add explicit provider voice lists: `english_voices` and `chinese_voices`.
- Keep Qwen voice lists owned by the Qwen provider path.
- Give the fake provider its own fake voice options.
- Persist voice preferences by `(voice, language)`.
- Expose language-scoped preference state through `/api/options`.
- Let the frontend filter voices by language and star only the selected language-specific voice.

Out of scope:

- Image OCR.
- OCR providers.
- Image upload or OCR draft storage.
- Voice sampling.
- Automatic voice selection based on source text.

## Implementation Steps

1. Extend provider options:
   - Add `language` to `SelectOption`.
   - Mark existing English Qwen voices with `language="en"`.
   - Add Chinese options from the same documented multilingual Qwen voice IDs with `language="zh"`.

2. Make provider voice metadata explicit:
   - Add `english_voices` and `chinese_voices` to the `TTSProvider` protocol.
   - Update Qwen provider to expose Qwen voice lists through those attributes.
   - Update fake provider to expose fake language-specific test voices.
   - Remove `voice_options` from providers.

3. Add language-scoped storage:
   - Create `voice_preferences` with primary key `(voice, language)`.
   - Add `set_voice_preference(voice, language, preferred)`.
   - Add `list_voice_preferences()` returning a `(voice, language)` keyed map.
   - Migrate old voice-only rows to `language='en'`.

4. Update API:
   - Build option lists from `provider.english_voices + provider.chinese_voices`.
   - Return language and preferred metadata for every voice option.
   - Sort preferred voices first within each language group.
   - Update `PUT /api/voices/{voice}/preference` to accept and return `language`.
   - Keep default voices language-specific.

5. Update frontend:
   - Add language selector.
   - Filter voice dropdown by active language.
   - Send `{ preferred, language }` when toggling a star.
   - Update only matching `voice.value` plus `voice.language` in local state.
   - Start with an empty fallback voice list so `/api/options` remains the source of truth.

## Tests

- Storage:
  - Preference round trip by language.
  - Same voice can have different English and Chinese preference state.
  - Legacy voice-only preference rows migrate to English.

- API:
  - `/api/options` includes language and preferred metadata.
  - Starring English `Cherry` does not star Chinese `Cherry`.
  - Chinese options include documented Qwen multilingual voice IDs.
  - Preference endpoint accepts and returns language.

- Providers:
  - Fake provider declares its own language voice options.
  - Qwen provider declares language voice options.
  - Providers no longer expose `voice_options`.

- Frontend:
  - Preference calls send current language.
  - Local state updates match both voice and language.
  - Initial frontend state does not seed hard-coded real voices.

## Verification

Run:

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```
