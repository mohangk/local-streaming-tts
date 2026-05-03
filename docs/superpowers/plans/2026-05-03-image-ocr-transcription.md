# Image OCR Transcription Implementation Plan

## Summary

Implement image-to-text transcription as a third Generate input mode, alongside Text and URL. The user can take or upload one or more images in a batch, run OCR for each image, review the extracted visible text beside thumbnails, and then generate one normal streamed TTS audio item from the combined reviewed text.

This plan assumes the existing Generate-page voice tooling on `main`. Do not add or modify voice behavior as part of this OCR branch.

## Scope

- Add `image` as a generation source type.
- Store uploaded source images under `data/images/`.
- Treat one OCR draft as a document with ordered child images.
- Add OCR draft persistence, including draft status, language, OCR model, optional linked generation ID, and per-image path/status/text/error metadata.
- Add a small OCR provider interface with fake and Qwen implementations.
- Add API routes for multi-image OCR draft create/list/get/update/delete, image serving, individual image deletion, and creating a generation from reviewed OCR draft text.
- Add Image mode to the lightweight frontend with multi-photo upload/camera input, thumbnail review cards, per-image OCR text editing, draft list, and generate-audio action.
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
   - Add `ocr_draft_images` as ordered child image rows with image path, original filename, MIME type, byte size, OCR status, reviewed text, and error.
   - Add methods to create drafts with multiple images, list/get drafts with images, update per-image reviewed text, remove an image, link a draft to a generation, delete unlinked drafts, and force-delete linked drafts during generation deletion.
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
   - `PUT /api/ocr-drafts/{draft_id}` updates language and reviewed text for child images by image ID.
   - `DELETE /api/ocr-drafts/{draft_id}/images/{image_id}` deletes one image from an unlinked draft and removes its stored file directory.
   - `DELETE /api/ocr-drafts/{draft_id}` deletes only unlinked drafts and all their images.
   - `POST /api/ocr-drafts/{draft_id}/generation` combines all non-empty reviewed image text in order, creates a normal streamed generation, and links the draft.

4. Add frontend Image mode:
   - Add an Image tab beside Text and URL.
   - Add file input with `accept="image/*"`, `capture="environment"`, and `multiple`.
   - Upload all selected images in one batch to create an OCR draft.
   - Render one numbered review card per draft image with a thumbnail, OCR status/error, editable reviewed text, and remove action.
   - Enable Generate audio when at least one retained image text area has non-empty reviewed text.
   - Generate audio from the reviewed draft image texts using existing language, voice, speed, autoplay, playback, and history flows.
   - List recent OCR drafts with Open/Delete.

5. Update configuration and docs:
   - Add `OCR_PROVIDER`, `OCR_MODEL`, `TTS_IMAGE_DIR`, and `TTS_MAX_IMAGE_BYTES`.
   - Rename model env vars to `TTS_MODEL` and `OCR_MODEL`.
   - Document that stored images are local data and must not be committed.

## Test Plan

- Storage tests for multi-image OCR draft create/get/list/update, individual image deletion, linked deletion blocking, forced deletion, source type migration, and image generation cleanup.
- API tests for multi-image OCR draft upload, partial OCR failure state, image serving, review update by image ID, individual image removal, generation creation from combined reviewed text, linked cleanup on generation delete, and language propagation to TTS.
- OCR provider tests for fake deterministic output, Qwen request shape, API key failures, empty/invalid responses, and provider errors.
- Frontend static tests for Image tab controls, multi-file multipart upload, thumbnail review cards, per-image text editing, image removal, draft list actions, and generation from reviewed draft text.
- Docs/config tests for OCR env vars and removal of legacy model env var names.
- Regression tests to keep single-image OCR working through the upgraded endpoint.

## Verification

Run:

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```
