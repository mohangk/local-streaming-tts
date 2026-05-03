# Image OCR Generation Design

Date: 2026-05-03

## Summary

Add image-based text extraction as a third Generate input mode alongside Text and URL. The user can take a photo on mobile or upload an image, run OCR, review and edit the extracted visible text, then generate streamed text-to-speech audio using the existing generation, history, playback, progress, and audio-cache flow.

This plan also includes the earlier Generate-page voice improvements: sampling the selected voice and speed before generation, and marking preferred voices so they appear first in the selector.

The first OCR provider should use Alibaba Cloud Model Studio Qwen OCR, specifically `qwen-vl-ocr`, because Alibaba documents it as optimized for extracting text from documents, tables, receipts, exam papers, and handwritten content, with multilingual support. Their current vision guidance recommends `qwen3.6-plus` or `qwen3.6-flash` for general image understanding, but the v1 Readvox use case is OCR-first.

Sources checked:

- https://www.alibabacloud.com/help/en/model-studio/qwen-vl-ocr
- https://www.alibabacloud.com/help/en/model-studio/vision-understanding/

## Goals

- Add an `Image` input mode beside `Text` and `URL`.
- Support taking a photo in the mobile browser or uploading an existing image.
- Store the original image locally.
- Run OCR through a lightweight provider interface.
- Preserve only visible text from the image.
- Support visible Chinese characters and visible pinyin without generating missing pinyin.
- Require manual review before generating audio.
- Persist OCR drafts even when audio is never generated.
- Let users reopen and delete unused OCR drafts.
- Link image-based audio generations back to the OCR draft/image that produced them.
- Keep final audio playback behavior identical to text and URL generations.
- Let users sample a selected voice and speed before creating a generation.
- Let users mark preferred voices and list those voices first.

## Non-Goals

- Do not auto-generate pinyin from Chinese characters in v1.
- Do not infer missing text that is not visible in the image.
- Do not automatically select voices based on OCR text content in v1.
- Do not add a separate OCR drafts navigation page in v1.
- Do not implement image thumbnails in History as part of the first pass.
- Do not support multi-image document OCR in v1.
- Do not store voice samples in History.
- Do not estimate or display OCR/TTS cost in this feature pass.

## User Workflow

The Generate page gains a third input mode:

```text
Text | URL | Image
```

In Image mode:

1. User chooses a language, initially `English` or `Chinese`.
2. The voice selector filters to voices appropriate for the selected language.
3. User takes a photo or uploads an image.
4. User taps `Extract text`.
5. Backend stores the original image and creates an OCR draft.
6. Backend runs OCR and stores the extracted text.
7. Frontend shows the extracted text in an editable review textarea.
8. User corrects the text if needed.
9. User taps `Generate audio`.
10. Backend creates a normal generation from the reviewed text and links it to the OCR draft.
11. Existing segmented TTS generation, cached audio, History, playback, progress, and deletion flows apply.

OCR drafts should be shown in Image mode as a compact recent-drafts list. A draft can be opened for review or deleted if it is not linked to a generation.

## OCR Behavior

The OCR prompt should ask for plain extracted text only:

- Extract only visible text.
- Preserve Chinese characters exactly as visible.
- Preserve pinyin exactly as visible.
- Preserve useful line and paragraph breaks for reading.
- Do not transliterate Chinese characters into pinyin.
- Do not infer missing pinyin.
- Do not add summaries, explanations, labels, Markdown fences, or JSON unless a future endpoint explicitly asks for structured output.

If OCR fails, the draft remains with `failed` status, an error message, and the stored image. The user can delete the draft or retry in a later iteration if retry support is added.

## Data Model

Add `image` to the allowed generation `source_type` values.

Add an `ocr_drafts` table:

```text
id INTEGER PRIMARY KEY AUTOINCREMENT
image_path TEXT NOT NULL
original_filename TEXT
mime_type TEXT NOT NULL
byte_size INTEGER NOT NULL CHECK (byte_size >= 0)
ocr_model TEXT NOT NULL
language TEXT NOT NULL
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

The stored path should be relative to `data/`, matching the existing audio-cache style.

When creating an audio generation from an OCR draft:

- The final generation uses `source_type = image`.
- `full_text` is the reviewed OCR text, not necessarily the raw OCR output.
- Generation settings include `language`, `voice`, `speed`, and the OCR draft ID.
- The OCR draft `linked_generation_id` is set to the new generation ID.

Add a `voice_preferences` table:

```text
voice TEXT PRIMARY KEY
preferred INTEGER NOT NULL DEFAULT 0
updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
```

Voice preferences are global to the local app and not tied to a browser session.

## Delete Rules

Unused OCR draft deletion:

- Allowed.
- Deletes the draft row.
- Removes the stored image directory.

Linked OCR draft deletion:

- Blocked from Image mode.
- Return a clear error such as `Delete the generated history item first`.

Image generation deletion from History:

- Deletes the generation row and cached audio, as today.
- If the generation is linked to an OCR draft, also deletes the OCR draft row and stored image directory.

This keeps History as the owner of completed audio work while still allowing cleanup of unused OCR drafts.

## Provider Interface

Add a separate OCR provider boundary instead of mixing OCR into the TTS provider.

Suggested modules:

```text
src/tts_app/ocr_providers/base.py
src/tts_app/ocr_providers/fake.py
src/tts_app/ocr_providers/qwen.py
src/tts_app/ocr_providers/registry.py
```

The interface should accept image bytes plus OCR options and return extracted text:

```python
class OCROptions:
    language: str
    model: str | None = None

class OCRProvider:
    name: str
    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str: ...
```

The fake OCR provider should be deterministic and used by tests. The Qwen provider should use the existing Alibaba credential environment convention, accepting `DASHSCOPE_API_KEY` or `QWEN_API_KEY` through configuration.

## API

Add endpoints:

- `POST /api/ocr-drafts`
  - Multipart form upload with `image` and `language`.
  - Stores image, runs OCR, returns the draft.

- `GET /api/ocr-drafts`
  - Lists recent drafts for Image mode.

- `GET /api/ocr-drafts/{draft_id}`
  - Returns one draft.

- `PUT /api/ocr-drafts/{draft_id}`
  - Updates reviewed text and language.

- `DELETE /api/ocr-drafts/{draft_id}`
  - Deletes only if `linked_generation_id` is empty.

- `POST /api/ocr-drafts/{draft_id}/generation`
  - Accepts reviewed text, voice, speed, language, and autoplay.
  - Creates an image generation and schedules TTS.
  - Links the draft to the generation.

- `POST /api/voice-sample`
  - Accepts voice, speed, and language.
  - Synthesizes a fixed sample script for the selected language.
  - Returns audio without persisting a generation.

- `PUT /api/voices/{voice}/preference`
  - Accepts `{ preferred: true/false }`.
  - Updates local voice preference state.

Update:

- `DELETE /api/generations/{generation_id}`
  - For image generations linked to OCR drafts, delete the linked OCR draft and stored image too.

- `GET /api/options`
  - Include language metadata and preferred state for voice options.
  - Return preferred voices first within each language.

## Frontend

Generate page changes:

- Add `Image` mode tab.
- Add language selector above voice selector.
- Filter voice options by selected language.
- Add a star control for the selected voice.
- Add a `Sample` button for the selected language, voice, and speed.
- Add image input:
  - `type="file"`
  - `accept="image/*"`
  - use mobile camera support where browser allows it, likely with `capture="environment"`.
- Add `Extract text` button.
- Show OCR status and failures.
- Show editable OCR review textarea after extraction.
- Add `Generate audio` button for reviewed text.
- Show recent OCR drafts inside Image mode with Open and Delete actions.

The sample button should use a separate frontend playback path from normal generation playback, or explicitly stop and clear the main playback state before sample playback. It must not leave background audio playing when the user navigates or starts a normal generation.

Playback page should not need major changes. Image-based generations use the same text segment and audio segment model.

History list should show image generations as source type `Image`. Details should include OCR model and language when available. Thumbnail preview can wait.

## Language And Voice Selection

Add a user-facing language selector with at least:

- `English`
- `Chinese`

Voice options from `/api/options` should include language metadata. The frontend filters the voice dropdown by the selected language. If the selected voice is not valid for the selected language, choose the default voice for that language.

Future iteration: auto-detect language from OCR or source text and shortlist voices. Do not include this in v1.

## Voice Sampling

Add a `Sample` button beside the voice and speed controls. The sample feature should work for Text, URL, and Image modes because it samples voice settings, not the source input.

Sample flow:

1. User chooses language, voice, and speed.
2. User taps `Sample`.
3. Frontend stops any current app playback and sends the selected voice, speed, and language to `POST /api/voice-sample`.
4. Backend synthesizes a fixed short script through the active TTS provider.
5. Backend streams or returns audio without creating a generation.
6. Frontend plays the sample and restores the button state when playback ends or fails.

English sample script:

```text
This is a short Readvox voice sample. Use it to check the voice, pacing, clarity, and listening comfort before generating the full article.
```

Chinese sample script:

```text
这是一个简短的 Readvox 语音示例。请用它来检查声音、语速、清晰度和听感是否适合长时间收听。
```

The sample endpoint must not create a generation, text segments, History item, cached audio, OCR draft, or playback progress row.

## Preferred Voices

Persist preferred voices server-side in SQLite so preferences follow the local app across browser sessions and devices.

The `/api/options` response should include `preferred: true/false` and `language` metadata for each voice option. The backend should return preferred voices first within each language group. The frontend should still sort defensively so a stale client response cannot put starred voices below unstarred voices.

Frontend behavior:

- Add a star button next to the voice selector.
- The star reflects the currently selected voice.
- Tapping the star toggles preference for the selected voice.
- Preferred voices appear first in the voice dropdown for the active language.
- Preserve the currently selected voice when re-sorting options after a preference change.

## Error Handling

User-facing errors should distinguish:

- Missing image upload.
- Unsupported image MIME type.
- Image too large.
- OCR provider missing API key.
- OCR provider request failure.
- OCR returned no readable text.
- Draft not found.
- Draft deletion blocked because it is linked to a generation.
- Generation from draft blocked because reviewed text is empty.

OCR errors should be logged through application logging without including secret values.

## Configuration

Add configuration for:

- OCR provider name, defaulting to `fake` in tests and local development if appropriate.
- Qwen OCR model, defaulting to `qwen-vl-ocr`.
- Maximum uploaded image size.
- Stored image directory, defaulting to `data/images`.
- Default English voice.
- Default Chinese voice.

Use existing Alibaba credential environment variables:

- `DASHSCOPE_API_KEY`
- `QWEN_API_KEY`

## Testing

Add failing tests before implementation.

Storage tests:

- Schema creates OCR drafts table.
- Schema creates voice preferences table.
- OCR draft create/get/list/update round trip.
- Unused OCR draft deletion succeeds.
- Linked OCR draft deletion is blocked.
- Deleting an image generation removes the linked draft metadata.
- Preferred voice create/update/list round trip.

API tests:

- `POST /api/ocr-drafts` accepts an image, stores it, calls fake OCR, and returns extracted text.
- Unsupported MIME type is rejected.
- Empty OCR text returns a clear error or failed draft state.
- `PUT /api/ocr-drafts/{draft_id}` updates reviewed text.
- `DELETE /api/ocr-drafts/{draft_id}` blocks linked drafts.
- `POST /api/ocr-drafts/{draft_id}/generation` creates an image generation and links the draft.
- Deleting the image generation removes stored audio and image assets.
- `POST /api/voice-sample` returns audio for the selected language, voice, and speed without creating History.
- `PUT /api/voices/{voice}/preference` stores and unsets preferred voices.
- `GET /api/options` returns language-tagged voices with preferred voices first.

Provider tests:

- Fake OCR provider returns deterministic text.
- Qwen OCR provider builds the expected request with model, image, prompt, and credentials.
- Qwen OCR provider maps provider errors into `ProviderError`-style application errors.

Frontend static tests:

- Generate page contains Text, URL, and Image modes.
- Generate page contains language selector, star button, and Sample button.
- Image mode has file input with image accept/camera affordance.
- JavaScript posts multipart OCR draft upload.
- JavaScript renders OCR review textarea.
- JavaScript creates generation from OCR draft reviewed text.
- JavaScript lists and deletes OCR drafts.
- Language selection filters voice options.
- JavaScript calls `/api/voice-sample` and plays returned sample audio.
- JavaScript toggles voice preference and keeps preferred voices first.

Regression tests:

- Existing Text and URL generation tests continue to pass.
- Existing History and playback tests continue to pass for image source generations.
