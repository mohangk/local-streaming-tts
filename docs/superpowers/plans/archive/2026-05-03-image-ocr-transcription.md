# Image OCR Transcription Implementation Plan

> Historical implementation plan. For the current OCR behavior and data model, read `docs/superpowers/specs/2026-05-03-image-ocr-generation-design.md`.

## Summary

Implement image-to-text transcription as an Image mode in Generate, alongside Text and URL. The user can take or upload one or more images in a batch, run OCR for each image, review one draft-level combined text area, inspect source thumbnails, and then generate one normal streamed TTS audio item from that reviewed combined text.

Current UI behavior also includes a fourth Generate input mode, `Draft Images`, for unlinked OCR drafts. Active Image mode is for selecting images and reviewing the current draft only; saved draft sessions are listed separately in `Draft Images`.

This plan assumes the existing Generate-page voice tooling on `main`. Do not add or modify voice behavior as part of this OCR branch.

## Scope

- Add `image` as a generation source type.
- Store uploaded source images under `data/images/`.
- Treat one OCR draft as a document with ordered child images.
- Add OCR draft persistence, including draft status, language, OCR model, draft-level `combined_text`, optional linked generation ID, and per-image path/status/raw OCR text/error metadata.
- Add a small OCR provider interface with fake and Qwen implementations.
- Add API routes for multi-image OCR draft create/list/get/update/delete, image serving, individual image deletion, failed-image retry, and creating a generation from reviewed OCR draft text.
- Add Image mode to the lightweight frontend with multi-photo upload/camera input, one combined review textarea, thumbnail source-image strip with retry/remove actions, and generate-audio action.
- Add Draft Images mode to list unlinked OCR drafts by extraction session with preview text, thumbnails, Continue, and Delete.
- Add image preview overlay for active-review and draft-list thumbnails.
- Update local setup/docs for OCR environment variables and image storage.

Out of scope:

- Voice tooling changes that already live on `main`.
- Automatic language detection.
- Generating pinyin that is not visibly present in the source image.
- Appending more photos to an existing draft after initial batch upload.
- Drag/drop or manual image reordering.
- OCR/TTS cost tracking.

## Implementation Tasks

1. Add storage support:
   - Extend `SourceType` to include `image`.
   - Add `ocr_drafts` as the parent document table.
   - Add `ocr_drafts.combined_text` as the editable draft-level transcript.
   - Add `ocr_draft_images` as ordered child image rows with image path, original filename, MIME type, byte size, OCR status, raw extracted text, and error.
   - Add methods to create drafts with multiple images, list/get drafts with images, update draft-level combined text, rebuild combined text from child image OCR text after retry/delete, remove an image, link a draft to a generation, delete unlinked drafts, and force-delete linked drafts during generation deletion.
   - Ensure deleting an image generation removes the linked OCR draft, all child image rows, and the stored image directory.

2. Add OCR providers:
   - Create `ocr_providers/base.py` with `OCROptions`, `OCRProvider`, and `OCRProviderError`.
   - Add deterministic fake OCR for tests.
   - Add Qwen OCR provider using the shared Alibaba credential path.
   - Add provider registry driven by `OCR_PROVIDER`.

3. Add API routes:
   - `POST /api/ocr-drafts` accepts repeated multipart `image` files plus `language`, stores all images, runs OCR per image, and returns the draft with ordered images.
   - `GET /api/ocr-drafts` lists recent drafts with compact image metadata.
   - `GET /api/ocr-drafts/{draft_id}` returns one draft with its images.
   - `GET /api/ocr-drafts/{draft_id}/images/{image_id}` serves the stored image bytes for thumbnail display.
   - `PUT /api/ocr-drafts/{draft_id}` updates language and draft-level `combined_text`.
   - `DELETE /api/ocr-drafts/{draft_id}/images/{image_id}` deletes one image from an unlinked draft and removes its stored file directory.
   - `DELETE /api/ocr-drafts/{draft_id}` deletes only unlinked drafts and all their images.
   - `POST /api/ocr-drafts/{draft_id}/images/{image_id}/retry` retries OCR for a stored image, updates that image's raw `extracted_text`, then rebuilds draft `combined_text` from image text in order.
   - `POST /api/ocr-drafts/{draft_id}/generation` creates a normal streamed generation from draft `combined_text` and links the draft.

4. Add frontend Image mode:
   - Add an Image tab beside Text and URL.
   - Add file input with `accept="image/*"`, `capture="environment"`, and `multiple`.
   - Upload all selected images in one batch to create an OCR draft.
   - Render one full-width combined OCR textarea, followed by source-image thumbnails.
   - Show Retry OCR on failed active-draft thumbnails and Remove on unlinked active-draft thumbnails.
   - Enable Generate audio when the combined OCR textarea is non-empty.
   - Generate audio from reviewed `combined_text` using existing language, voice, speed, autoplay, playback, and history flows.
   - Add Draft Images mode with unlinked draft cards, preview text from `combined_text`, thumbnail strips, Continue, and Delete.
   - Open a larger source-image preview from thumbnails in both active review and Draft Images mode.

5. Update configuration and docs:
   - Add `OCR_PROVIDER`, `OCR_MODEL`, `TTS_IMAGE_DIR`, and `TTS_MAX_IMAGE_BYTES`.
   - Rename model env vars to `TTS_MODEL` and `OCR_MODEL`.
   - Document that stored images are local data and must not be committed.

## Test Plan

- Storage tests for multi-image OCR draft create/get/list/update, `combined_text` migration and persistence, individual image deletion with combined-text rebuild, linked deletion blocking, forced deletion, source type migration, and image generation cleanup.
- API tests for multi-image OCR draft upload, partial OCR failure state, image serving, draft-level review update, individual image removal, failed-image retry rebuilding `combined_text`, generation creation from `combined_text`, linked cleanup on generation delete, and language propagation to TTS.
- OCR provider tests for fake deterministic output, Qwen request shape, API key failures, empty/invalid responses, and provider errors.
- Frontend static tests for Image tab controls, Draft Images mode, multi-file multipart upload, one combined OCR textarea, active thumbnail retry/remove actions, image preview overlay, draft-list card actions, and generation from reviewed `combined_text`.
- Docs/config tests for OCR env vars and removal of legacy model env var names.
- Regression tests to keep single-image OCR working through the upgraded endpoint.

## Verification

Run:

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```
