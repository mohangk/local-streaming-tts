# Local Streaming TTS App Design

Date: 2026-05-01

## Summary

Build a local, mobile-first web app for generating text-to-speech audio from pasted text or a URL. The app will stream generation segment by segment, play audio as it becomes available by default, and persist all source text, generation metadata, and generated audio for later replay.

The app is intended for local hosting first, with optional private-network access. It is not designed as a public multi-user service in v1.

## Goals

- Provide a simple responsive web UI that works well on a mobile phone.
- Accept pasted text or a URL as input.
- Extract readable text from basic HTML pages.
- Generate speech segment by segment through a lightweight provider interface.
- Use Alibaba/Qwen real-time TTS as the first provider.
- Support auto-play as segments arrive and a manual queue mode.
- Persist generation history, full source text, segment text, settings, and audio files.
- Provide a good reading/listening playback view with synchronized text highlighting and tap-to-jump.
- Keep frontend JavaScript lightweight and framework-free.

## Non-Goals

- No JavaScript-heavy page extraction in v1. Pages that require browser rendering should return a clear unsupported-content error and be tracked as a future enhancement.
- No multi-user accounts, public authentication system, billing, or sharing features in v1.
- No full-audio-file export in v1. A later advanced option can concatenate segments into a single generated file.
- No voice cloning or voice design workflow in v1, even if the provider supports it.

## Architecture

Use FastAPI as the single Python backend process. FastAPI serves both the static frontend and the API. Local deployment should be one process, one port, and one data directory.

Core backend units:

- `App/API layer`: routes for submitting text, submitting URL jobs, streaming generation progress, fetching history, fetching generation details, and serving cached audio.
- `Text extraction layer`: handles direct pasted text and basic HTML page extraction.
- `Segmenter`: splits text into readable, provider-safe chunks while preferring paragraph and sentence boundaries.
- `TTS provider interface`: isolates provider-specific streaming TTS behavior behind a small Python contract.
- `Qwen provider`: first concrete provider, targeting Alibaba/Qwen real-time TTS streaming capabilities.
- `Generation service`: creates generation records, processes segments, persists audio and status, and emits progress events.
- `Storage layer`: SQLite metadata plus filesystem audio cache.
- `Frontend`: static HTML, CSS, and vanilla JavaScript served by FastAPI.

Recommended local data layout:

```text
data/
  app.db
  audio/
    <generation_id>/
      segment-0001.<ext>
      segment-0002.<ext>
```

## Provider Interface

The app should call an internal provider interface rather than calling Qwen directly from generation logic.

The interface should support:

- Provider name and available voices.
- Segment-level synthesis.
- Streaming or incremental audio output when the provider supports it.
- Provider options such as voice, language, format, sample rate, speed, pitch, volume, and bitrate where available.
- Clear provider errors that the generation service can persist.

Qwen/Alibaba is the first provider because current Alibaba Cloud Model Studio documentation describes Qwen real-time speech synthesis with streaming text input and incremental audio output.

Provider-specific limits, including max input characters, supported languages, and output formats, should be stored in provider configuration so the segmenter can stay within safe limits.

## User Workflow

The app has two primary mobile-first views:

- `Generate`: paste text or enter a URL, choose playback behavior, and start generation.
- `History`: browse previous generations, search or filter them, and reopen playback.

In `Generate`, the user chooses one of two input modes:

- `Text`: store the pasted or typed content directly.
- `URL`: fetch the URL server-side, extract readable text from basic HTML, then store the full extracted text.

When the user taps Generate:

1. The backend validates the input.
2. The backend creates a generation record with status `queued`.
3. URL input is fetched and extracted before segmentation.
4. The full source text is persisted.
5. The segmenter creates ordered text segments.
6. The generation service starts synthesizing segments.
7. Each completed audio segment is written to disk and recorded in SQLite.
8. The frontend receives progress events and updates playback.

Playback behavior:

- Auto-play is enabled by default.
- A toggle switches to manual queue mode.
- Segments appear in order as they are generated.
- Completed segments can be replayed immediately.
- Completed generations remain available through History across browser sessions.

## History

History is a first-class UI view, not a hidden admin page.

The history list should show:

- Source type: text or URL.
- Title when available.
- URL when applicable.
- Created time.
- Status.
- Text preview.
- Basic replay affordance.

Tapping a history entry opens its playback view with:

- Full stored text.
- Ordered text segments.
- Audio segment status.
- Replay controls.
- Generation settings used for that item.

Backend endpoints:

- `GET /api/generations`: list prior generations.
- `GET /api/generations/{generation_id}`: return generation metadata, full text, segments, and audio URLs.
- `GET /api/audio/{generation_id}/{segment_id}`: serve cached audio.

## Playback And Reading View

Each generation has a dedicated playback view optimized for reading while listening.

The view should include:

- A compact player with play/pause, current segment, progress, and playback mode.
- Readable text displayed as ordered segments.
- Highlighting for the currently playing text segment.
- Tap-to-jump from any text segment to its matching audio.
- Pending states for segments whose audio is not ready yet.
- Replay support for completed segments from current generation or History.
- Scroll-follow while audio plays.
- A way to disable scroll-follow if the user manually scrolls away.

The segmenter must persist each text segment separately so playback can map audio back to readable text. This means audio chunks are not just transient stream data; they are part of a durable segment model.

## URL Extraction

V1 supports basic HTML extraction only.

The extractor should:

- Fetch server-side with a reasonable timeout.
- Require an HTML content type or clearly handle missing content type.
- Remove scripts, styles, navigation-like boilerplate, and empty text.
- Prefer article-like content when available.
- Return a useful title when available.
- Persist the final extracted text.

Expected failures:

- Invalid URL.
- Network timeout or DNS failure.
- Unsupported content type.
- Empty extracted text.
- Content appears to require JavaScript rendering.

JavaScript-heavy extraction should be captured as a future enhancement, likely through a headless browser worker.

## Persistence

Use SQLite for durable metadata and the filesystem for audio bytes.

Suggested tables:

- `generations`: id, source type, title, URL, full text, provider, voice, settings JSON, status, error, created_at, updated_at.
- `text_segments`: id, generation_id, segment_index, text, status, created_at, updated_at.
- `audio_segments`: id, generation_id, text_segment_id, segment_index, file_path, mime_type, duration_ms, byte_size, status, error, created_at, updated_at.

The app stores full pasted or extracted text by design. This is acceptable because the app is a local personal tool.

## Error Handling

User-facing errors should be specific and actionable:

- URL validation errors should say the URL is invalid.
- Fetch failures should say the page could not be reached.
- Unsupported content types should identify the content type when known.
- Empty extraction should say no readable text was found.
- JavaScript-heavy pages should say browser-rendered pages are not supported yet.
- Provider failures should identify that speech generation failed and preserve any completed segments.

Generation failures should not discard prior successful work. If segment 5 fails after segments 1-4 succeeded, segments 1-4 remain playable and visible in History.

If mobile browser auto-play fails, the frontend should fall back to manual play and keep all generated segments.

## Testing

Use tests that do not require paid provider calls by default.

Test coverage should include:

- Text segmentation behavior.
- Basic HTML extraction.
- Storage creation and retrieval.
- Submit pasted text API.
- Submit URL API with mocked HTML fetches.
- History list and detail APIs.
- Audio file serving.
- Provider interface with a fake provider.
- Generation progress flow with fake audio output.
- Frontend smoke coverage for Generate, History, and Playback navigation.

The fake provider should produce deterministic small audio-like fixture bytes so local tests can verify streaming and caching behavior without using API credits.

## Future Enhancements

- JavaScript-heavy URL extraction through a headless browser.
- Single-file audio export by concatenating generated segments.
- Additional TTS providers.
- More voice controls in the UI.
- Optional cleanup policy for old generated audio.
- Optional private-proxy access guidance.
