# Image OCR Generation Design

## Summary

Add image OCR as a new way to create text for Readvox. A user can take a photo or upload an image, extract visible text, manually review that text, and then create a normal streamed TTS generation from the reviewed result.

Generate-page voice controls are provided by the existing tooling on `main`. This design only covers image/OCR transcription and how it connects to the existing generation flow.

## Goals

- Support taking a photo in the mobile browser or uploading an existing image.
- Store the original image locally.
- Extract only visible text from the image through a lightweight OCR provider interface.
- Support visible Chinese characters and visible pinyin without generating missing pinyin.
- Require manual review before creating audio.
- Persist OCR drafts even when audio is never generated.
- Let users reopen and delete unused OCR drafts.
- Link image-based audio generations back to the OCR draft/image that produced them.
- Keep playback, history, cached audio, and progress behavior consistent with Text and URL generations.

## Non-Goals

- Do not auto-generate pinyin from Chinese characters in v1.
- Do not infer missing text that is not visible in the image.
- Do not automatically select voices based on OCR text content in v1.
- Do not add a separate OCR drafts navigation page in v1.
- Do not implement image thumbnails in History as part of the first pass.
- Do not support multi-image document OCR in v1.
- Do not estimate or display OCR/TTS cost in this feature pass.

## User Flow

1. User opens Generate and selects Image mode.
2. User chooses the existing language, voice, speed, and autoplay settings.
3. User takes a photo or uploads an image.
4. Frontend submits the image to the OCR draft endpoint.
5. Backend stores the original image and creates an OCR draft.
6. Backend runs OCR and stores extracted text or failure details on the draft.
7. Frontend shows the extracted text in an editable review box.
8. User edits or confirms the text.
9. User taps Generate audio.
10. Backend creates a normal generation from reviewed text and links it to the OCR draft.
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

Manual review is required before audio generation. Empty reviewed text cannot generate audio.

If OCR fails, the draft remains with `failed` status, an error message, and the stored image. The user can delete the draft or retry in a later iteration if retry support is added.

## Storage

Add `image` to allowed generation `source_type` values.

Add `ocr_drafts`:

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
image_path TEXT NOT NULL
original_filename TEXT
mime_type TEXT NOT NULL
byte_size INTEGER NOT NULL
ocr_model TEXT NOT NULL
language TEXT NOT NULL CHECK (language IN ('en', 'zh'))
extracted_text TEXT NOT NULL DEFAULT ''
status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed'))
error TEXT
linked_generation_id INTEGER REFERENCES generations(id) ON DELETE SET NULL
created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

Store images under:

```text
data/images/<draft_id>/source.<ext>
```

When creating audio from an OCR draft:

- The final generation uses `source_type = image`.
- `full_text` is the reviewed OCR text.
- Generation settings include `language`, `voice`, `speed`, and `ocr_draft_id`.
- The OCR draft `linked_generation_id` is set to the new generation ID.

Unused OCR draft deletion removes the draft row and stored image directory. Linked OCR draft deletion is blocked from the OCR draft list. Deleting a completed image generation from History removes audio, the linked OCR draft row, and the stored image directory.

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
  - Multipart upload with `image` and `language`.
  - Validates MIME type and size.
  - Stores image, runs OCR, and returns the draft.

- `GET /api/ocr-drafts`
  - Returns recent drafts, newest first.

- `GET /api/ocr-drafts/{draft_id}`
  - Returns a single draft.

- `PUT /api/ocr-drafts/{draft_id}`
  - Updates reviewed text and language.
  - Rejects unsupported languages.

- `DELETE /api/ocr-drafts/{draft_id}`
  - Deletes unlinked drafts.
  - Returns an error for drafts linked to a generation.

- `POST /api/ocr-drafts/{draft_id}/generation`
  - Accepts reviewed text, voice, speed, language, and autoplay.
  - Creates an image generation and schedules TTS.
  - Links the OCR draft to the generation.

- `DELETE /api/generations/{generation_id}`
  - For image generations linked to OCR drafts, deletes the linked OCR draft and stored image too.

## Frontend

- Add Image mode beside Text and URL.
- Add image input with:
  - `type="file"`
  - `accept="image/*"`
  - `capture="environment"` as a mobile camera hint.
- Show OCR status and failures.
- Show editable OCR review textarea after extraction.
- Keep Generate disabled for Image mode until reviewed text is present.
- Show recent OCR drafts inside Image mode with Open and Delete actions.
- Use existing language, voice, speed, autoplay, playback, history, and progress controls.

History list shows image generations as source type `Image`. Details include OCR model and language when available. Thumbnail preview can wait.

## Configuration

Add:

- `OCR_PROVIDER`, default `fake`.
- `OCR_MODEL`, default `qwen-vl-ocr`.
- `TTS_IMAGE_DIR`, default `data/images`.
- `TTS_MAX_IMAGE_BYTES`, default 10 MB.

Use `TTS_MODEL` for the TTS model env var and `OCR_MODEL` for the OCR model env var. Remove old `QWEN_MODEL`, `QWEN_OCR_MODEL`, and `QWEN_VOICE` references from examples.

## Test Plan

- Storage:
  - OCR draft create/get/list/update round trip.
  - Language validation and migration.
  - Unused OCR draft deletion succeeds.
  - Linked OCR draft deletion is blocked.
  - Deleting an image generation removes linked OCR metadata and image files.

- API:
  - `POST /api/ocr-drafts` stores image, calls fake OCR, and returns extracted text.
  - Upload validation rejects missing image, unsupported MIME type, and oversized image.
  - Failed OCR keeps a failed draft with error detail.
  - `PUT /api/ocr-drafts/{draft_id}` updates reviewed text.
  - `POST /api/ocr-drafts/{draft_id}/generation` creates image generation from reviewed text.
  - Image generation passes selected language to TTS.
  - Deleting image generation removes stored audio and image assets.

- Providers:
  - Fake OCR provider returns deterministic text.
  - Qwen OCR provider builds expected request with model, image, prompt, and credentials.
  - Qwen OCR provider maps provider failures into `OCRProviderError`.

- Frontend:
  - Generate page contains Image mode controls.
  - JavaScript posts multipart OCR draft upload.
  - JavaScript renders OCR review textarea.
  - JavaScript creates generation from OCR draft reviewed text.
  - JavaScript lists and deletes OCR drafts.

- Regression:
  - Existing Text and URL generation tests continue to pass.
  - Existing History and playback tests continue to pass for image source generations.
