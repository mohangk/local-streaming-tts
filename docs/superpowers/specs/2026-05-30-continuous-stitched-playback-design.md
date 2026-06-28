# Continuous Stitched Playback Design

## Problem

Playback telemetry from a mobile Chrome background test showed that the current segment finished while the page was hidden, but playback stalled when frontend JavaScript switched `audio.src` to the next segment and called `play()` in the background.

The fragile boundary is not segment audio generation. It is browser playback depending on hidden-page JavaScript at every segment transition.

## Goal

Make long-article playback look like one continuous audio resource to the browser, while preserving the current cost-saving model where TTS is generated segment-by-segment and only a few segments ahead.

## Non-Goals

- Do not generate the full article before playback can start.
- Do not replace the provider streaming/generation pipeline.
- Do not introduce HLS, MediaSource, or a frontend media framework in the first pass.
- Do not promise precise seeking or frame-perfect word highlighting in the first pass.
- Do not store article text or provider payloads in new diagnostics.

## Recommended Approach

Use a single continuous playback endpoint backed by a cached stitched MP3 artifact.

The browser should play one URL, for example:

```text
/api/generations/{generation_id}/continuous-audio?start_segment={segment_index}
```

That URL should remain stable for the playback session. The frontend should not switch `audio.src` between segment URLs during continuous playback.

The backend should keep the existing per-segment MP3 files as the source of truth during generation. As segments complete, a stitcher appends each completed segment in order to a generation-level artifact:

```text
data/audio/<generation_id>/full.mp3
```

The continuous endpoint reads from the stitched artifact. If the request reaches the current end of the file while generation is still running, it waits briefly for the next completed segment to be appended instead of closing the response. When the generation completes, `full.mp3` becomes the durable playback artifact for future sessions.

## Why Not A Half-Written Static File URL

Pointing `<audio>` directly at `/data/audio/<generation_id>/full.mp3` while it is still growing is not reliable enough. A normal static file response can set `Content-Length` to the file size at request time, hit EOF at the current size, or interact badly with browser caching and range requests.

The continuous endpoint can intentionally tail the growing artifact and decide when to wait and when to end. Serving completed artifacts with normal range semantics is intentionally deferred to a later compatibility change.

The distinction is:

- `full.mp3` is the cached byte artifact. It is useful storage, and after completion it becomes the durable audio file for future playback.
- `/api/generations/{generation_id}/continuous-audio` is the playback controller. During generation it streams bytes from `full.mp3`, waits when it reaches the current end of the file, and only closes when the generation is complete or the client disconnects.

This prevents the browser from treating a temporary artifact size as the final media length. The browser still gets one stable audio URL, but the backend controls whether current EOF means "wait for more generated audio" or "the generation is actually complete."

The response shape is different in the two cases:

```text
Static half-written full.mp3 response:
HTTP/1.1 200 OK
Content-Type: audio/mpeg
Content-Length: 443275
Accept-Ranges: bytes
```

In this case, `Content-Length` is the file size when the request starts. If more bytes are appended later, the browser may still consider `443275` bytes to be the complete media response. Range requests can also be based on that observed size.

```text
Continuous endpoint while generation is still running:
HTTP/1.1 200 OK
Content-Type: audio/mpeg
Transfer-Encoding: chunked
Cache-Control: no-store
```

In this case, there is no fixed `Content-Length` while the artifact is still growing. The server can yield available chunks, wait at the current artifact end, then yield more chunks after new segments are appended.

The first implementation should keep generated playback behind the continuous endpoint even after the artifact is complete. Returning a normal completed-file response with `Content-Length`, `Accept-Ranges`, and range support may be useful later for seeking, but it should be treated as a separate compatibility change because it changes browser media loading semantics.

## Data Model

Add SQLite metadata in a `continuous_audio_artifacts` table:

- `generation_id`: primary key and foreign key to `generations(id)` with `ON DELETE CASCADE`.
- `file_path`: relative path such as `audio/36/full.mp3`.
- `mime_type`: initially `audio/mpeg`.
- `status`: `building`, `completed`, or `failed`.
- `appended_through_segment_index`: last segment index durably appended to the artifact, or `-1` before any segment is appended.
- `byte_size`: current artifact byte size.
- `error`: nullable failure text.
- timestamps.

The existing `audio_segments.byte_size` values can be used to compute segment boundary byte offsets for first-pass playback because `full.mp3` is a byte-for-byte concatenation of segment files in segment order. If a later remux/finalization step rewrites the file, it must also replace or invalidate any offset assumptions.

The existing `audio_segments.duration_ms` field should be populated for generated MP3 segments when possible. Older rows may have null durations, so generation detail loading can lazily backfill missing durations from completed segment files and persist the result. Duration extraction belongs in generation/audio metadata code, not the provider interface or frontend.

Segment duration metadata is used for UI progress and highlighting only. It is not a new source of truth for generated audio bytes; segment MP3 files and stitched artifact metadata remain the durable playback sources.

## Backend Behavior

The stitcher owns artifact creation and repair:

- It appends only completed audio segments.
- It appends segments strictly in `segment_index` order.
- It is idempotent: calling it repeatedly should not duplicate bytes.
- It can repair missing or stale `full.mp3` by rebuilding from completed segment files.
- It updates SQLite after bytes are safely written.
- It never deletes segment MP3 files.

Generation should notify or invoke the stitcher after each segment completes. The continuous endpoint should also be allowed to invoke the stitcher lazily if a playback request arrives before the artifact is caught up.

The continuous endpoint should:

- Validate that the generation exists.
- Validate `start_segment` is within the generation's text segment range.
- Build or repair the artifact through `start_segment` if enough segment files exist.
- Return `409` immediately if the requested `start_segment` has not been appended yet.
- Start streaming from the byte offset for `start_segment`.
- Continue reading bytes as the artifact grows, waiting briefly at current EOF after the response has started while generation is still running.
- End only when the generation is complete and all completed bytes have been sent, or when the client disconnects.
- Return `404` for missing generations.

## Frontend Behavior

Continuous playback mode should become the default for generated article playback:

- `openGeneration` still loads generation detail for text rendering and progress.
- `playSegment(index)` should set `audio.src` once to the continuous endpoint when starting a continuous playback session.
- The frontend should not advance to the next segment by changing `audio.src` on `ended`.
- Text highlighting and progress remain segment-index based, but should advance during continuous playback:
  - On playback start, save progress to `start_segment`.
  - Track the segment where the current continuous stream started because `audio.currentTime` is relative to that start point.
  - During `timeupdate`, estimate the active segment from cumulative `duration_ms` for ready audio segments.
  - If all relevant segment durations are not available but the browser exposes a finite stream duration, use cumulative `byte_size` as a fallback because `full.mp3` is concatenated in segment order.
  - If neither duration nor a finite stream duration is available, keep the active segment at the chosen start segment instead of guessing.
  - Save progress only when the estimated segment changes, and serialize progress writes with the generation id captured when each save is queued so delayed requests cannot regress progress or write to a newly opened generation.
  - On `ended`, mark complete.

Segment click behavior can still restart the continuous URL at that segment. That is a user-initiated foreground action and does not recreate the hidden-page boundary problem.

## Telemetry

Keep the existing playback telemetry. Add or reuse content-free events to verify the fix:

- continuous playback URL selected
- continuous stream waiting for bytes
- continuous stream ended
- audio `playing` and `canplay` events if useful

Do not store article text, URL content, audio bytes, provider responses, or raw browser identifiers.

## Failure Modes

- If the stitched artifact fails, return an explicit API error and keep the frontend in continuous playback mode. Segment-playback fallback is future work, not part of the current contract.
- If the stream reaches current EOF after it has started and generation is still running, the endpoint should wait rather than end the audio response.
- If the requested `start_segment` has not been appended yet, return `409` immediately.
- If the client disconnects, the stream stops without failing the generation.
- If the artifact is missing but segment files exist, rebuild it from segment files.
- If a segment file is missing, return an explicit API error and keep existing generation deletion semantics.

## Testing Strategy

Storage tests should cover artifact metadata, deletion cascade, and rebuild state.

Stitcher tests should use small fake MP3-like byte files and assert:

- ordered append
- idempotent repeated append
- rebuild after missing artifact
- no append past missing segment gaps

API tests should assert:

- continuous endpoint returns bytes from multiple segments through one response
- `start_segment` starts at the expected segment boundary
- unknown generation returns `404`
- a not-yet-generated `start_segment` returns `409`
- generation deletion removes the stitched artifact with the existing audio directory cleanup

Frontend tests should assert:

- generated playback uses the continuous endpoint rather than per-segment audio URLs
- automatic segment transition no longer calls `playSegment(next)` in continuous mode
- user clicking a text segment restarts the continuous URL at that segment
- continuous playback estimates active segments from duration metadata, falls back to byte ratios only with finite stream duration, and clamps invalid metadata
- queued progress saves preserve the generation snapshot captured when each save was queued

Generation/audio metadata tests should assert:

- MP3 segment duration extraction works for parseable MP3 frames and ignores unparseable audio
- generation detail loading backfills missing `duration_ms` for completed segment files without regenerating audio

## Open Follow-Up

After the first pass, evaluate whether completed `full.mp3` files need an ffmpeg remux/finalization step for better duration and seek metadata. That should be a separate change unless testing proves the naive concatenated artifact is not playable enough for the background playback fix.

Also evaluate whether the continuous endpoint should serve completed artifacts with normal completed-file response semantics (`Content-Length`, `Accept-Ranges`, and range support). Keep this separate from the background playback fix because the current route intentionally behaves as a playback controller rather than a static file URL.
