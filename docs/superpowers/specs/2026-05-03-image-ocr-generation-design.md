# Image OCR Generation Design

## Summary

Add image OCR as a new way to create text for Readvox. A user can upload one or more existing images, extract visible text from each image, manually review one combined draft transcript, inspect the source thumbnails, and then create one normal streamed TTS generation from the reviewed combined result.

Generate-page voice controls are provided by the existing tooling on `main`. This design only covers image/OCR transcription and how it connects to the existing generation flow.

## Goals

- Support uploading one or more existing images in a batch.
- Preserve browser selection order as the document read order.
- Store the original images locally.
- Show source thumbnails below the combined OCR review text.
- Extract only visible text from each image through a lightweight OCR provider interface.
- Support visible Chinese characters and visible pinyin without generating missing pinyin.
- Require manual review before creating audio.
- Persist OCR drafts and their editable `combined_text` even when audio is never generated.
- Let users reopen drafts, remove individual draft images, and delete unused OCR drafts.
- Keep saved draft sessions in a separate Generate mode named `Draft Images`.
- Let users open source image previews from thumbnails in both active review and Draft Images mode.
- Link image-based audio generations back to the OCR draft and images that produced them.
- Keep playback, history, cached audio, and progress behavior consistent with Text and URL generations.
- Next planned behavior: append newly uploaded images to the current unlinked OCR draft instead of creating a new draft when an active draft is open.
- Next planned behavior: provide an explicit warning-colored `Clear images` action for starting a fresh OCR draft.

## Non-Goals

- Do not auto-generate pinyin from Chinese characters in v1.
- Do not infer missing text that is not visible in the image.
- Do not automatically select voices based on OCR text content in v1.
- Do not add a separate bottom-navigation page for OCR drafts in v1; saved drafts live under Generate > Draft Images.
- Do not add drag/drop or manual reordering in v1.
- Do not estimate or display OCR/TTS cost in this feature pass.

## User Flow

1. User opens Generate and selects Image mode.
2. User chooses the existing language, voice, speed, and autoplay settings.
3. User uploads one or more images in one batch.
4. Frontend submits the selected images to create a new OCR draft.
5. Backend stores each original image, runs OCR for each image, and stores text or failure details per image.
6. Frontend shows a draft review view with one editable combined text area, followed by numbered source thumbnails.
7. User edits or confirms the combined text, and may retry failed image OCR or remove incorrect images before generation.
8. User taps Generate audio.
9. Backend creates a normal generation from the draft-level `combined_text` and links it to the OCR draft.
10. Existing streamed playback, history, audio caching, and progress tracking take over.

Unlinked OCR drafts appear in the separate Draft Images mode as one card per extraction session. A draft can be continued for review or deleted if it is not linked to a generation. Image mode itself is reserved for selecting images, reviewing the active draft, and generating audio from that active draft.

Planned next behavior changes steps 4 and 7: when an unlinked OCR draft is already active, newly selected images append to that draft instead of creating another draft; if the user wants a fresh draft, they use `Clear images` first.

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

Manual review is required before audio generation. The editable draft-level `combined_text` is the source of truth for audio generation. Generation is allowed when `combined_text` is non-empty after trimming.

If OCR fails for one image, the draft remains available. Successful image results are kept, the failed image shows an error and a `Retry OCR` action while the draft is unlinked. A retry updates that image row's raw `extracted_text`, then rebuilds draft `combined_text` from all image-level OCR text in image order. This intentionally overwrites any manual edits in the combined textarea after retry.

Planned next behavior: appending new images to an active unlinked draft preserves existing `combined_text`. Successful OCR text from the newly appended images is appended to the current `combined_text` in upload order, separated by blank lines. Failed appended images remain in the thumbnail list with errors and do not add text until retried successfully.

## Storage

Add `image` to allowed generation `source_type` values.

Use `ocr_drafts` as the parent document:

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
ocr_model TEXT NOT NULL
language TEXT NOT NULL CHECK (language IN ('en', 'zh'))
combined_text TEXT NOT NULL DEFAULT ''
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

`ocr_drafts.combined_text` stores the editable reviewed transcript. `ocr_draft_images.extracted_text` stores each image's raw OCR result and remains the source for retry/delete recombination and diagnostics.

When creating audio from an OCR draft:

- The final generation uses `source_type = image`.
- `full_text` is the trimmed draft-level `combined_text`.
- Generation settings include `language`, `voice`, `speed`, and `ocr_draft_id`.
- The OCR draft `linked_generation_id` is set to the new generation ID.

Planned next behavior: appending images to an unlinked draft inserts new child image rows after the current maximum `position`. The appended images keep the same storage layout under the existing draft directory.

Unused OCR draft deletion removes the draft row, child image rows, and stored image directory. Linked OCR draft deletion is blocked from Draft Images mode. Deleting a completed image generation from History removes audio, the linked OCR draft row, all child image rows, and the stored image directory. Deleting one source image from an unlinked draft removes that image directory, compacts remaining positions, and rebuilds `combined_text` from remaining image OCR text.

Planned next behavior: `Clear images` is the active-review affordance for starting over. If an unlinked OCR draft is active, it asks for confirmation, then deletes that draft through the same app deletion flow used by `DELETE /api/ocr-drafts/{draft_id}` and resets Image mode to no active draft. It must not remove linked drafts or generated audio.

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

- Planned: `POST /api/ocr-drafts/{draft_id}/images`
  - Multipart upload with one or more repeated `image` files plus `language`.
  - Validates MIME type and size for every file.
  - Appends images to one existing unlinked draft after the current last position.
  - Stores each image, runs OCR per image, and returns the updated draft.
  - Appends successful new OCR text to the existing draft `combined_text` without discarding manual edits already present.
  - Returns `409` for linked drafts and `404` for missing drafts.

- `GET /api/ocr-drafts`
  - Returns recent drafts, newest first, including compact image metadata and `combined_text`.

- `GET /api/ocr-drafts/{draft_id}`
  - Returns one draft with all child images.

- `GET /api/ocr-drafts/{draft_id}/images/{image_id}`
  - Returns the stored image bytes for thumbnail display.

- `PUT /api/ocr-drafts/{draft_id}`
  - Updates draft language and draft-level `combined_text`.
  - Keeps per-image `extracted_text` as raw OCR data.
  - Rejects unsupported languages.

- `DELETE /api/ocr-drafts/{draft_id}/images/{image_id}`
  - Deletes one unlinked draft image and its stored image directory.
  - Recompacts remaining positions.
  - Rebuilds draft `combined_text` from remaining image OCR text.

- `DELETE /api/ocr-drafts/{draft_id}`
  - Deletes unlinked drafts and all child images.
  - Returns an error for drafts linked to a generation.

- `POST /api/ocr-drafts/{draft_id}/generation`
  - Accepts voice, speed, language, and autoplay.
  - Uses draft `combined_text`.
  - Rejects generation when `combined_text` is empty after trimming.
  - Creates an image generation, schedules TTS, and links the draft.

- `POST /api/ocr-drafts/{draft_id}/images/{image_id}/retry`
  - Retries OCR for one stored source image in an unlinked draft.
  - Updates that image row's status/error/raw `extracted_text`.
  - Rebuilds draft `combined_text` from all image-level OCR text in image order.
  - Returns `409` for linked drafts and `404` for missing draft/image/file.

- `DELETE /api/generations/{generation_id}`
  - For image generations linked to OCR drafts, deletes the linked OCR draft and all stored images too.

## Frontend

- Add Image mode beside Text and URL.
- Add Draft Images mode beside Image for unlinked OCR drafts.
- Add image input with:
  - `type="file"`
  - `accept="image/*"`
  - `multiple` for batch upload.
- In Image mode, show one combined OCR textarea, then source thumbnails, then Generate audio.
- Current implementation creates a new OCR draft for each upload action.
- Planned next behavior appends more uploaded images to the active unlinked draft.
- Show OCR status and partial failures on source thumbnail cards.
- Active source thumbnails open the image preview overlay.
- Failed active thumbnails show `Retry OCR` while the draft is unlinked.
- Unlinked active thumbnails show `Remove`.
- Planned next behavior shows a warning-colored yellow `Clear images` button when an unlinked draft is active.
- Planned `Clear images` behavior confirms with the user, deletes the active unlinked draft and stored source images through the app deletion flow, clears active review state, and leaves Image mode ready for a fresh upload.
- Keep Generate audio hidden or disabled until the combined OCR textarea is non-empty.
- In Draft Images mode, show one card per unlinked OCR extraction session.
- Draft cards show a preview derived from `combined_text`, a compact thumbnail strip, `Continue`, and `Delete`.
- Draft-list thumbnail clicks open the preview overlay and do not continue the draft.
- Use existing language, voice, speed, autoplay, playback, history, and progress controls.

History list shows image generations as source type `Image`. Details include OCR model and language when available. Thumbnail preview in History can wait; thumbnails are required in active Image review and Draft Images mode.

Static assets use version query strings on `app.js` and `styles.css` for this UI revision so browsers and private proxies do not combine new HTML with stale JavaScript or CSS.

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
  - Planned: appending images to an existing unlinked OCR draft assigns positions after existing images.
  - Planned: appending successful OCR text preserves existing `combined_text` and adds new text at the end.
  - `combined_text` migration, persistence, and separation from per-image `extracted_text`.
  - Language validation and migration.
  - Individual image removal and combined-text rebuild.
  - Unused OCR draft deletion removes all child image rows.
  - Linked OCR draft deletion is blocked.
  - Deleting an image generation removes linked OCR metadata and image files.

- API:
  - `POST /api/ocr-drafts` stores multiple images, calls fake OCR for each, and returns ordered image results.
  - Planned: `POST /api/ocr-drafts/{draft_id}/images` appends uploaded images to an unlinked draft and updates `combined_text`.
  - Planned: Append endpoint rejects linked drafts.
  - Upload validation rejects missing images, unsupported MIME types, empty files, and oversized images.
  - Partial OCR failure keeps successful image text and failed image errors on the same draft.
  - Image-serving route returns stored image bytes.
  - `PUT /api/ocr-drafts/{draft_id}` updates draft-level `combined_text`.
  - Individual image deletion removes that stored image, preserves order for remaining images, and rebuilds `combined_text`.
  - OCR retry uses the stored image file, updates image-level `extracted_text`, and rebuilds `combined_text`.
  - `POST /api/ocr-drafts/{draft_id}/generation` creates image generation from `combined_text`.
  - Image generation passes selected language to TTS.
  - Deleting image generation removes stored audio and all image assets.

- Providers:
  - Fake OCR provider returns deterministic text.
  - Qwen OCR provider builds expected request with model, image, prompt, and credentials.
  - Qwen OCR provider maps provider failures into `OCRProviderError`.

- Frontend:
  - Generate page contains Image mode controls with multi-file upload input and no in-app `Take photo` button.
  - JavaScript posts multipart OCR draft upload with all selected images.
  - Current JavaScript creates a new OCR draft for each upload action.
  - Planned JavaScript appends uploads to the active unlinked OCR draft instead of creating a new draft.
  - JavaScript renders one combined OCR textarea and active source thumbnails.
  - Planned JavaScript exposes a yellow `Clear images` action for deleting the current unlinked draft and starting fresh.
  - JavaScript removes individual draft images and retries failed OCR images.
  - JavaScript creates generation from reviewed `combined_text`.
  - JavaScript lists and deletes OCR drafts in Draft Images mode.
  - JavaScript opens the image preview overlay from active and draft-list thumbnails.
  - CSS/HTML keep Draft Images hidden outside that mode, including after browser asset caching.

- Regression:
  - Existing Text and URL generation tests continue to pass.
  - Existing single-image OCR upload still works through the same endpoint.
  - Existing History and playback tests continue to pass for image source generations.
