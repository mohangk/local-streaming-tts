# Configuration And Providers

Readvox runs with deterministic fake providers by default for development and tests. Real TTS/OCR calls are isolated behind provider adapters.

## Fake Providers

Use fake providers for local UI work and automated tests:

```bash
TTS_PROVIDER=fake
OCR_PROVIDER=fake
```

The fake TTS provider writes small deterministic audio-like files. The fake OCR provider returns deterministic text without calling external services.

## Qwen Providers

```bash
TTS_PROVIDER=qwen
OCR_PROVIDER=qwen
DASHSCOPE_API_KEY=...
TTS_MODEL=qwen3-tts-instruct-flash-realtime
OCR_MODEL=qwen-vl-ocr
QWEN_REALTIME_URL=wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
TTS_DEFAULT_ENGLISH_VOICE=Kai
TTS_DEFAULT_CHINESE_VOICE=Cherry
```

`DASHSCOPE_API_KEY` is preferred. `QWEN_API_KEY` is also supported where provider code accepts it.

Generate uses named voice profiles shared across devices in SQLite. Choose a profile for the current language and use **Edit** to create, change, duplicate, or delete profiles. Each profile stores its name, model, voice, language, speed, instructions, and editable preview text. English and Chinese audiobook defaults use the instruction model, Kai, and 1× speed. Profile names are trimmed and case-insensitively unique, including Unicode case folding.

The same editor is available at `/voice-sample`. **Preview** uses unsaved values; **Save and use** persists and selects the profile. **Cancel** keeps saved values unchanged and warns before discarding edits. In-app navigation preserves Text/URL input, Image review text, source images, and the originating Generate mode. OCR recognition language remains separate: image generation requires a profile matching its draft language.

The browser remembers the selected profile for each language. A deleted selection falls back to the first available profile for that language. If none remain, create a new profile. Legacy voice preferences and `readvox.voiceSelection.v1` are preserved; the editor offers importing a valid previous voice/speed into a new named profile. Voices unavailable on the instruction model, such as Jennifer, can be imported with the legacy flash model and empty instructions.

Voice samples use long preview text, up to 50,000 characters, uses the same `TTS_SEGMENT_MAX_CHARS` boundary as generation. Preview audio is cached by provider, model, voice, language, speed, instructions, text, and segment boundary; renaming a profile does not invalidate its audio. **Clear samples** clears only preview audio. Previewing never creates a History entry. Deleting a profile leaves all generated audio and History intact.

New Text, URL, and OCR UI requests send `profile_id`. The server resolves it once and snapshots profile ID/name, model, voice, language, speed, and instructions into the generation. Editing or deleting a profile cannot alter an existing job. API clients without a profile retain explicit voice/speed/language, use the configured `TTS_MODEL`, and have empty instructions. Supplying synthesis overrides with `profile_id` returns a validation error. Existing history is unchanged; missing historical model metadata remains unknown.

The profile API provides `GET/POST /api/voice-profiles` and `GET/PUT/DELETE /api/voice-profiles/{id}`. Creation and update accept `name`, `model`, `voice`, `language`, `speed`, `instructions`, and `preview_text`. Names are required, speed is 0.5–2.0, instructions have a 4,000-character limit, and preview text must be nonempty. Model/voice capabilities and language validation are shared with preview synthesis.

The instruction realtime models support these system voices: `Cherry`, `Serena`, `Ethan`, `Chelsie`, `Momo`, `Vivian`, `Moon`, `Maia`, `Kai`, `Nofish`, `Bella`, `Eldric Sage`, `Mia`, `Mochi`, `Bellona`, `Vincent`, `Bunny`, `Neil`, `Elias`, `Arthur`, `Nini`, `Seren`, `Pip`, and `Stella`. Readvox serves this model-specific list from `/api/voice-sample/options`; the normal generation voice list is not reused because some voices, including `Jennifer`, are unavailable on the instruction model. See Alibaba Cloud's current [Qwen-TTS voice list](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-voice-list) before changing the catalog.

The live provider integration canary verifies a saved instruction profile through the complete generation API-to-Qwen path using one supported voice and one short paid provider request in temporary storage. Deterministic tests cover multi-segment sample assembly without adding paid provider calls. Run the canary once before marking an implementation feature complete:

```bash
set -a
source .envrc.local
set +a
RUN_QWEN_INTEGRATION=1 .venv/bin/pytest -m live_provider -q
```

## Runtime Storage Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `TTS_DATA_DIR` | `data` | Root directory for local SQLite data and generated files. |
| `TTS_DB_PATH` | `$TTS_DATA_DIR/app.db` | SQLite database path. |
| `TTS_AUDIO_DIR` | `$TTS_DATA_DIR/audio` | Generated audio directory, including per-generation audio and voice sample cache files. |
| `TTS_IMAGE_DIR` | `$TTS_DATA_DIR/images` | Stored OCR source image directory. |
| `TTS_AUDIO_EXT` | `mp3` | Default generated audio file extension. |
| `TTS_SEGMENT_MAX_CHARS` | `550` | Maximum text characters per generated TTS segment. |
| `TTS_MAX_IMAGE_BYTES` | `10485760` | Maximum accepted OCR source image size. |

## OCR Image Mode

Image mode lets you upload or capture one or more photographed/scanned pages, review OCR text beside image thumbnails, choose an English or Chinese voice, and create a normal streamed generation from the combined reviewed text.

```bash
OCR_PROVIDER=fake
OCR_MODEL=qwen-vl-ocr
TTS_IMAGE_DIR=data/images
TTS_MAX_IMAGE_BYTES=10485760
```

Uploaded source images are stored under `data/images/` while their OCR draft exists. Deleting an unlinked OCR draft removes its stored image directory. Deleting a History entry created from an OCR draft removes the generation, cached audio, linked OCR draft, and stored source image directory.

For Chinese OCR, preserve only visible Chinese text and visible pinyin. Do not generate missing pinyin, transliterate Chinese characters into pinyin, translate, summarize, or infer text that is not visible in the image.

## Pricing Context

Alibaba Cloud Model Studio pricing is documented at <https://www.alibabacloud.com/help/en/model-studio/model-pricing>. The pricing page was last updated by Alibaba on Jun 22, 2026.

For the previously used realtime TTS model, `qwen3-tts-flash-realtime`, the relevant text-to-speech pricing captured on May 02, 2026 is:

| Deployment mode | Model | Billing unit | Input price | Output price | Free quota |
| --- | --- | --- | --- | --- | --- |
| International | `qwen3-tts-flash-realtime` | Input text characters | `$0.13 / 10K characters` | Not billed | 10,000 characters, valid 90 days after activating Model Studio |
| Chinese Mainland | `qwen3-tts-flash-realtime` | Input text characters | `$0.143353 / 10K characters` | Not charged | No free quota |

Future cost tracking should store the model, deployment mode, input character count, pricing source date, and calculated estimated cost per generation. Pricing can change, so keep this as a documented baseline rather than hard-coding it as permanent billing truth.

## Legacy Environment Cleanup

Existing deployments should use `TTS_MODEL`, `OCR_MODEL`, and `OCR_PROVIDER=qwen`. Remove old `QWEN_MODEL`, `QWEN_OCR_MODEL`, and `QWEN_VOICE` entries from `.envrc.local`.

The historical flash-model prices above do not establish instruction-model pricing. Re-check Alibaba Cloud pricing before implementing any billing-sensitive behavior.
