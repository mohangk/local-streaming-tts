# Voice Preferences Design

## Summary

Add language-aware voice selection and language-scoped preferred voices to Readvox. The same provider voice ID can appear in multiple language lists, but preference state is stored independently per `(voice, language)` so starring a voice for English does not star it for Chinese.

This design covers the voice selector, provider voice metadata, and preference persistence. It does not cover image OCR transcription.

## Goals

- Let the user choose a language before choosing a voice.
- Show only voices that match the active language.
- Persist starred/preferred voices across browser sessions.
- Keep preferred voices first within each language list.
- Treat duplicate provider voice IDs in different languages as separate preference records.
- Make language-scoped voice lists an explicit TTS provider interface instead of letting provider-specific constants leak through fake providers.
- Keep frontend JavaScript lightweight and mobile-friendly.

## Provider Interface

TTS providers expose voice metadata by language:

```python
class TTSProvider(Protocol):
    name: str
    english_voices: tuple[SelectOption, ...]
    chinese_voices: tuple[SelectOption, ...]

    def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]: ...
```

Qwen owns Qwen-specific voice lists. The fake provider owns fake test voice lists and must not import Qwen voice constants.

Each voice option includes:

```python
@dataclass(frozen=True)
class SelectOption:
    value: str | float
    label: str
    language: str | None = None
```

## Storage

Voice preferences are keyed by both voice ID and language:

```sql
CREATE TABLE IF NOT EXISTS voice_preferences (
    voice TEXT NOT NULL,
    language TEXT NOT NULL CHECK (language IN ('en', 'zh')),
    preferred INTEGER NOT NULL DEFAULT 0 CHECK (preferred IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (voice, language)
);
```

Existing legacy `voice_preferences(voice, preferred)` rows migrate to English-only preferences. That preserves prior English usage and prevents accidental Chinese stars.

## API

`GET /api/options` returns:

- `default_language`
- `default_voices`
- `default_voice`
- `voices`, each with `value`, `label`, `language`, and `preferred`
- `speeds`

The backend sorts preferred voices before unpreferred voices within each language group.

`PUT /api/voices/{voice}/preference` accepts:

```json
{
  "language": "en",
  "preferred": true
}
```

The response includes `voice`, `language`, and `preferred`.

## Frontend

- The Generate page has a language selector before the voice selector.
- The voice dropdown filters by selected language.
- The star button reflects the selected `(voice, language)` preference.
- Tapping the star sends the current language with the preference update.
- Updating local frontend state only changes the matching `voice.value` and `voice.language`.
- Initial frontend state does not seed real voice options; `/api/options` is the source of truth.

## Test Coverage

- Storage round trips preference values by `(voice, language)`.
- Legacy voice-only preferences migrate to English.
- API options do not leak a preferred English voice into Chinese.
- API exposes Qwen multilingual voices under both language lists.
- Providers expose `english_voices` and `chinese_voices`.
- Fake provider does not import Qwen voice lists.
- Frontend sends language with preference updates and does not hard-code real voices in initial state.
