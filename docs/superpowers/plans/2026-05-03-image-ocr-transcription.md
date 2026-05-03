# Image OCR Transcription Implementation Plan

## Summary

Implement image-to-text transcription as a third Generate input mode, alongside Text and URL. The user can take or upload an image, run OCR, manually review the extracted visible text, and then generate normal streamed TTS audio from the reviewed text.

This plan assumes the existing Generate-page voice tooling on `main`. Do not add or modify voice behavior as part of this OCR branch.

## Scope

- Add `image` as a generation source type.
- Store uploaded source images under `data/images/`.
- Add OCR draft persistence, including status, extracted text, language, OCR model, image path, and optional linked generation ID.
- Add a small OCR provider interface with fake and Qwen implementations.
- Add API routes for OCR draft create/list/get/update/delete and creating a generation from a reviewed OCR draft.
- Add Image mode to the lightweight frontend with upload/camera input, OCR review text, draft list, and generate-audio action.
- Update local setup/docs for OCR environment variables and image storage.

Out of scope:

- Voice tooling changes that already live on `main`.
- Automatic language detection.
- Generating pinyin that is not visibly present in the source image.
- Multi-image OCR.
- OCR/TTS cost tracking.

## Implementation Tasks

1. Add storage support:
   - Extend `SourceType` to include `image`.
   - Add `ocr_drafts` table and migrations.
   - Add methods to create, list, update, link, delete, and force-delete OCR drafts.
   - Ensure deleting an image generation removes the linked OCR draft and stored image directory.

2. Add OCR providers:
   - Create `ocr_providers/base.py` with `OCROptions`, `OCRProvider`, and `OCRProviderError`.
   - Add deterministic fake OCR for tests.
   - Add Qwen OCR provider using the shared Alibaba credential path.
   - Add provider registry driven by `OCR_PROVIDER`.

3. Add API routes:
   - `POST /api/ocr-drafts` accepts multipart `image` plus `language`, stores the image, runs OCR, and returns the draft.
   - `GET /api/ocr-drafts` lists recent drafts.
   - `GET /api/ocr-drafts/{draft_id}` returns one draft.
   - `PUT /api/ocr-drafts/{draft_id}` updates reviewed text and language.
   - `DELETE /api/ocr-drafts/{draft_id}` deletes only unlinked drafts.
   - `POST /api/ocr-drafts/{draft_id}/generation` creates a normal streamed generation from reviewed text and links the draft.

4. Add frontend Image mode:
   - Add an Image tab beside Text and URL.
   - Add file input with `accept="image/*"` and camera capture hint.
   - Upload image to create OCR draft.
   - Show editable OCR review text.
   - List recent OCR drafts with Open/Delete.
   - Generate audio from reviewed draft text using the existing language, voice, speed, autoplay, playback, and history flows.

5. Update configuration and docs:
   - Add `OCR_PROVIDER`, `OCR_MODEL`, `TTS_IMAGE_DIR`, and `TTS_MAX_IMAGE_BYTES`.
   - Rename model env vars to `TTS_MODEL` and `OCR_MODEL`.
   - Document that stored images are local data and must not be committed.

## Test Plan

- Storage tests for OCR draft create/get/list/update, linked deletion blocking, forced deletion, source type migration, and image generation cleanup.
- API tests for OCR draft upload, failed OCR draft state, review update, generation creation from reviewed text, linked cleanup on generation delete, and language propagation to TTS.
- OCR provider tests for fake deterministic output, Qwen request shape, API key failures, empty/invalid responses, and provider errors.
- Frontend static tests for Image tab controls, multipart upload, OCR review UI, draft list actions, and generation from reviewed draft text.
- Docs/config tests for OCR env vars and removal of legacy model env var names.

## Verification

Run:

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```
