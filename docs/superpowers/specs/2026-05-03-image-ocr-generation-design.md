# Image OCR Generation Design

## Summary

Add image OCR as a new way to create text for Readvox. A user can take or upload one or more photos, extract visible text from each image, manually review that text in a draft, and then create one normal streamed TTS generation from the combined reviewed result.

Generate-page voice controls are provided by the existing tooling on `main`. This design only covers image/OCR transcription and how it connects to the existing generation flow.

## Goals

- Support taking photos in the mobile browser or uploading one or more existing images in a batch.
- Preserve browser selection order as the document read order.
- Store the original images locally.
- Show numbered thumbnails next to each image's reviewed OCR text.
- Extract only visible text from each image through a lightweight OCR provider interface.
- Support visible Chinese characters and visible pinyin without generating missing pinyin.
- Require manual review before creating audio.
- Persist OCR drafts even when audio is never generated.
- Let users reopen drafts, remove individual draft images, and delete unused OCR drafts.
- Link image-based audio generations back to the OCR draft and images that produced them.
- Keep playback, history, cached audio, and progress behavior consistent with Text and URL generations.

## Non-Goals

- Do not auto-generate pinyin from Chinese characters in v1.
- Do not infer missing text that is not visible in the image.
- Do not automatically select voices based on OCR text content in v1.
- Do not add a separate OCR drafts navigation page in v1.
- Do not add drag/drop or manual reordering in v1.
- Do not append more photos to an existing draft in v1.
- Do not estimate or display OCR/TTS cost in this feature pass.

## User Flow

1. User opens Generate and selects Image mode.
2. User chooses the existing language, voice, speed, and autoplay settings.
3. User takes or uploads one or more images in one batch.
4. Frontend submits all selected images to the OCR draft endpoint.
5. Backend creates one OCR draft and ordered child image records.
6. Backend stores each original image, runs OCR for each image, and stores text or failure details per image.
7. Frontend shows a draft review view with numbered thumbnails and one editable text area per image.
8. User edits or confirms the text, and may remove incorrect images before generation.
9. User taps Generate audio.
10. Backend combines non-empty reviewed image texts in order, creates a normal generation, and links it to the OCR draft.
11. Existing streamed playback, history, audio caching, and progress tracking take over.

OCR drafts appear in Image mode as a compact recent-drafts list. A draft can be reopened for review or deleted if it is not linked to a generation.

## OCR Behavior

The OCR prompt asks for plain extracted text only:

- Preserve visible line breaks where useful.
- Preserve Chinese characters exactly as visible.
- Preserve visible pinyin exactly as visible.
- Preserve visible punctuation.
- Do not summarize.
- Do not translate.
- Do not transliterate Chinese characters into pinyin.
- Do not add text that is not visible.

Manual review is required before audio generation. Generation is allowed when at least one retained image has non-empty reviewed text. Images with empty reviewed text are skipped when building the combined transcript.

If OCR fails for one image, the draft remains available. Successful image results are kept, the failed image shows an error and editable empty text, and the user can either fill text manually, leave it empty so it is skipped, or remove that image.

## Storage

Add `image` to allowed generation `source_type` values.

Use `ocr_drafts` as the parent document:

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
ocr_model TEXT NOT NULL
language TEXT NOT NULL CHECK (language IN ('en', 'zh'))
status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'partial_failed', 'failed'))
error TEXT
linked_generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

Add ordered child images:

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
ocr_draft_id INTEGER NOT NULL REFERENCES ocr_drafts(id) ON DELETE CASCADE
position INTEGER NOT NULL
image_path TEXT NOT NULL
original_filename TEXT
mime_type TEXT NOT NULL
byte_size INTEGER NOT NULL
extracted_text TEXT NOT NULL DEFAULT ''
status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed'))
error TEXT
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
UNIQUE(ocr_draft_id, position)
```

Store images under:

```text
data/images/<draft_id>/<image_id>/source.<ext>
```

When creating audio from an OCR draft:

- The final generation uses `source_type = image`.
- `full_text` is all non-empty reviewed image text, ordered by `position`, separated by blank lines.
- Generation settings include `language`, `voice`, `speed`, and `ocr_draft_id`.
- The OCR draft `linked_generation_id` is set to the new generation ID.

Unused OCR draft deletion removes the draft row, child image rows, and stored image directory. Linked OCR draft deletion is blocked from the OCR draft list. Deleting a completed image generation from History removes audio, the linked OCR draft row, all child image rows, and the stored image directory.

## Provider Boundary

Add a separate OCR provider boundary instead of mixing OCR into the TTS provider:

```python
@dataclass(frozen=True)
class OCROptions:
    language: str
    model: str | None = None

class OCRProvider(Protocol):
    name: str
    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str: ...
```

The fake OCR provider is deterministic for tests. The Qwen OCR provider uses the existing Alibaba credential convention: `DASHSCOPE_API_KEY` or `QWEN_API_KEY`.

## API

- `POST /api/ocr-drafts`
  - Multipart upload with one or more repeated `image` files plus `language`.
  - Validates MIME type and size for every file.
  - Creates one draft, stores each image, runs OCR per image, and returns the draft with an `images` array in position order.

- `GET /api/ocr-drafts`
  - Returns recent drafts, newest first, including compact image metadata and preview text.

- `GET /api/ocr-drafts/{draft_id}`
  - Returns one draft with all child images.

- `GET /api/ocr-drafts/{draft_id}/images/{image_id}`
  - Returns the stored image bytes for thumbnail display.

- `PUT /api/ocr-drafts/{draft_id}`
  - Updates draft language and reviewed image texts.
  - Accepts image text updates keyed by child image ID.
  - Rejects unsupported languages.

- `DELETE /api/ocr-drafts/{draft_id}/images/{image_id}`
  - Deletes one unlinked draft image and its stored image directory.
  - Recompacts remaining positions.

- `DELETE /api/ocr-drafts/{draft_id}`
  - Deletes unlinked drafts and all child images.
  - Returns an error for drafts linked to a generation.

- `POST /api/ocr-drafts/{draft_id}/generation`
  - Accepts voice, speed, language, and autoplay.
  - Combines non-empty reviewed image texts in order.
  - Rejects generation only when all retained image texts are empty.
  - Creates an image generation, schedules TTS, and links the draft.

- `DELETE /api/generations/{generation_id}`
  - For image generations linked to OCR drafts, deletes the linked OCR draft and all stored images too.

## Frontend

- Add Image mode beside Text and URL.
- Add image input with:
  - `type="file"`
  - `accept="image/*"`
  - `capture="environment"` as a mobile camera hint.
  - `multiple` for batch upload.
- Show OCR status and partial failures.
- Show a draft review list with one numbered card per image.
- Each image card shows a CSS-sized thumbnail, OCR status/error, editable reviewed text, and a remove action.
- Keep Generate audio hidden or disabled until at least one retained image has reviewed text.
- Show recent OCR drafts inside Image mode with Open and Delete actions.
- Use existing language, voice, speed, autoplay, playback, history, and progress controls.

History list shows image generations as source type `Image`. Details include OCR model and language when available. Thumbnail preview in History can wait; thumbnails are required in the Image draft review flow.

## Configuration

Add:

- `OCR_PROVIDER`, default `fake`.
- `OCR_MODEL`, default `qwen-vl-ocr`.
- `TTS_IMAGE_DIR`, default `data/images`.
- `TTS_MAX_IMAGE_BYTES`, default 10 MB per image.

Use `TTS_MODEL` for the TTS model env var and `OCR_MODEL` for the OCR model env var. Remove old `QWEN_MODEL`, `QWEN_OCR_MODEL`, and `QWEN_VOICE` references from examples.

## Test Plan

- Storage:
  - OCR draft create/get/list/update round trip with multiple ordered images.
  - Language validation and migration.
  - Per-image text update and individual image removal.
  - Unused OCR draft deletion removes all child image rows.
  - Linked OCR draft deletion is blocked.
  - Deleting an image generation removes linked OCR metadata and image files.

- API:
  - `POST /api/ocr-drafts` stores multiple images, calls fake OCR for each, and returns ordered image results.
  - Upload validation rejects missing images, unsupported MIME types, empty files, and oversized images.
  - Partial OCR failure keeps successful image text and failed image errors on the same draft.
  - Image-serving route returns stored image bytes.
  - `PUT /api/ocr-drafts/{draft_id}` updates reviewed text per image.
  - Individual image deletion removes that stored image and preserves order for remaining images.
  - `POST /api/ocr-drafts/{draft_id}/generation` creates image generation from combined non-empty reviewed text.
  - Image generation passes selected language to TTS.
  - Deleting image generation removes stored audio and all image assets.

- Providers:
  - Fake OCR provider returns deterministic text.
  - Qwen OCR provider builds expected request with model, image, prompt, and credentials.
  - Qwen OCR provider maps provider failures into `OCRProviderError`.

- Frontend:
  - Generate page contains Image mode controls with multi-file input.
  - JavaScript posts multipart OCR draft upload with all selected images.
  - JavaScript renders numbered thumbnails and per-image review text areas.
  - JavaScript removes individual draft images.
  - JavaScript creates generation from reviewed draft image texts.
  - JavaScript lists and deletes OCR drafts.

- Regression:
  - Existing Text and URL generation tests continue to pass.
  - Existing single-image OCR upload still works through the same endpoint.
  - Existing History and playback tests continue to pass for image source generations.
