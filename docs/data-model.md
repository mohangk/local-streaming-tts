# Data Model

Readvox stores metadata in SQLite and bytes on the filesystem. The exact schema is checked in at [schema.sql](schema.sql).

## Storage Layout

- `data/app.db`: SQLite database.
- `data/audio/<generation_id>/segment-0001.mp3`: per-segment TTS audio.
- `data/audio/<generation_id>/full.mp3`: stitched continuous playback artifact.
- `data/audio/voice-samples/<cache_key>.mp3`: derived voice sample cache files.
- `data/images/<ocr_draft_id>/<ocr_draft_image_id>/`: source images for OCR drafts.

## Core Relationships

```mermaid
erDiagram
    generations ||--o{ text_segments : has
    generations ||--o{ audio_segments : has
    generations ||--o| continuous_audio_artifacts : has
    generations ||--o{ playback_telemetry_events : has
    generations ||--o| ocr_drafts : linked_from
    text_segments ||--o| audio_segments : rendered_as
    ocr_drafts ||--o{ ocr_draft_images : contains
```

## Generations

`generations` is the durable History entry. It stores source type, title, optional URL, full source text, provider, voice, settings JSON, status, progress, and timestamps.

`text_segments` stores the ordered text chunks generated from a History entry.

`audio_segments` stores one row per completed segment audio file. Segment files remain the source of truth for generated audio bytes. `duration_ms` is populated when parseable and can be lazily backfilled for older cached MP3s.

`continuous_audio_artifacts` stores metadata for `full.mp3`, the stitched artifact used by the continuous playback endpoint.

## OCR Drafts

OCR image workflows are staged as drafts until the user creates audio:

- `ocr_drafts.combined_text` is the reviewed source of truth for audio generation.
- `ocr_draft_images.extracted_text` preserves raw per-image OCR output for retry, delete, and diagnostics.
- Linked drafts disappear from active draft-picking surfaces after audio generation and are recovered through History.
- Deleting an image History entry removes the generation, cached audio, linked OCR draft, and stored source images.

## Voice Preferences

`voice_preferences` stores the user's preferred voice per language.

Voice sample audio is cached under `data/audio/voice-samples/` by provider/model/language/voice/speed/sample-text hash. These files are derived app cache, not user-authored data and not generation History rows. They are not removed by generation deletion. A future cache-management flow can clear `data/audio/voice-samples/` if disk usage becomes a concern.

## Playback Telemetry

`playback_telemetry_events` stores content-free local diagnostics for playback debugging. It may reference a generation, segment index, and audio segment id, but it must not store article text, OCR text, URL content, generated audio bytes, provider raw responses, or raw browser identifiers.

## Cleanup Semantics

- Deleting a generation cascades text/audio segment metadata, continuous artifact metadata, and playback telemetry.
- Deleting a generation removes its cached audio directory.
- Deleting an unlinked OCR draft removes its stored source image directory.
- Deleting an image generation force-deletes its linked OCR draft and image directories.
