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
TTS_MODEL=qwen3-tts-flash-realtime
OCR_MODEL=qwen-vl-ocr
QWEN_REALTIME_URL=wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
TTS_DEFAULT_ENGLISH_VOICE=Jennifer
TTS_DEFAULT_CHINESE_VOICE=Cherry
```

`DASHSCOPE_API_KEY` is preferred. `QWEN_API_KEY` is also supported where provider code accepts it.

The Generate page loads language-aware voice choices and speed presets from `/api/options`. Selected voice and speed are stored with each generation. Voice samples are streamed directly from the provider, cached for reuse, and do not create History entries or cached generation audio.

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

For the app's current default realtime TTS model, `qwen3-tts-flash-realtime`, the relevant text-to-speech pricing captured on May 02, 2026 is:

| Deployment mode | Model | Billing unit | Input price | Output price | Free quota |
| --- | --- | --- | --- | --- | --- |
| International | `qwen3-tts-flash-realtime` | Input text characters | `$0.13 / 10K characters` | Not billed | 10,000 characters, valid 90 days after activating Model Studio |
| Chinese Mainland | `qwen3-tts-flash-realtime` | Input text characters | `$0.143353 / 10K characters` | Not charged | No free quota |

Future cost tracking should store the model, deployment mode, input character count, pricing source date, and calculated estimated cost per generation. Pricing can change, so keep this as a documented baseline rather than hard-coding it as permanent billing truth.

## Legacy Environment Cleanup

Existing deployments should use `TTS_MODEL`, `OCR_MODEL`, and `OCR_PROVIDER=qwen`. Remove old `QWEN_MODEL`, `QWEN_OCR_MODEL`, and `QWEN_VOICE` entries from `.envrc.local`.
