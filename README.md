# Readvox

Readvox is a local, mobile-first web app for generating streamed text-to-speech audio from pasted text or basic HTML page URLs.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
.venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001` locally.

## Development Start

Use this while actively editing the app. `--reload` restarts the Python process when files under `src/` change.

```bash
cd /home/mohan/tts

TTS_PROVIDER=qwen \
.venv/bin/uvicorn tts_app.api:create_app \
  --factory \
  --reload \
  --reload-dir src \
  --host 127.0.0.1 \
  --port 8001 \
  --log-level info
```

Open `http://127.0.0.1:8001` locally, or use your private HTTPS proxy URL if you have one configured.

To keep application and access logs in a file while still seeing them in the terminal:

```bash
mkdir -p logs
TTS_PROVIDER=qwen .venv/bin/uvicorn tts_app.api:create_app --factory --reload --reload-dir src --host 127.0.0.1 --port 8001 --log-level info 2>&1 | tee -a logs/app.log
```

## Systemd Deployment

Versioned VPS deployment files live in `setup/`, matching the pattern used by
the companion local services on the host:

- `setup/tts.service`: source-of-truth systemd unit for `/etc/systemd/system/tts.service`
- `setup/envrc.local.example`: environment file template for `/home/mohan/tts/.envrc.local`
- `setup/setup-venv.sh`: creates `.venv` and installs Python dependencies
- `setup/install-service.sh`: installs/enables the systemd service
- `setup/README.md`: install, update, diagnostics, and recovery commands

Prepare the Python environment, then install or update the unit:

```bash
setup/setup-venv.sh
setup/install-service.sh
```

Manual equivalent:

```bash
sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service
sudo systemctl daemon-reload
sudo systemctl enable --now tts
```

Set the Qwen API key in `/home/mohan/tts/.envrc.local`:

```bash
DASHSCOPE_API_KEY=<your-key>
```

## Trust Boundary

URL generation fetches pages server-side from the host running this app. When exposing the app beyond localhost, only grant access to trusted devices and users: anyone who can use the app can ask the host to fetch arbitrary HTTP(S) URLs reachable from that machine.

## Development Provider

The default provider is `fake`, which writes deterministic small audio-like files and does not call an external API.

```bash
TTS_PROVIDER=fake .venv/bin/uvicorn tts_app.api:create_app --factory --reload --host 127.0.0.1 --port 8001
```

## Qwen Provider Configuration

```bash
TTS_PROVIDER=qwen
DASHSCOPE_API_KEY=...
QWEN_MODEL=qwen3-tts-flash-realtime
QWEN_REALTIME_URL=wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
QWEN_VOICE=Jennifer
```

The Generate page loads English-capable Qwen voice choices and speed presets from `/api/options`. The selected voice and speed are stored with each generation.

## Pricing Context

Alibaba Cloud Model Studio pricing is documented at <https://www.alibabacloud.com/help/en/model-studio/model-pricing>. The pricing page was last updated by Alibaba on Apr 01, 2026.

For the app's current default realtime TTS model, `qwen3-tts-flash-realtime`, the relevant text-to-speech pricing captured on May 02, 2026 is:

| Deployment mode | Model | Billing unit | Input price | Output price | Free quota |
| --- | --- | --- | --- | --- | --- |
| International | `qwen3-tts-flash-realtime` | Input text characters | `$0.13 / 10K characters` | Not billed | 10,000 characters, valid 90 days after activating Model Studio |
| Chinese Mainland | `qwen3-tts-flash-realtime` | Input text characters | `$0.143353 / 10K characters` | Not charged | No free quota |

Future cost tracking should store the model, deployment mode, input character count, pricing source date, and calculated estimated cost per generation. Pricing can change, so keep this as a documented baseline rather than hard-coding it as permanent billing truth.

## History And Playback

Generated entries are persisted in SQLite with the full extracted or pasted text, provider, voice, speed, URL when applicable, cached audio metadata, and segment-based playback progress. Regenerating the same text or URL with a different voice or speed creates a separate history entry and a separate cached audio directory.

History entries can be deleted from the UI. Deletion removes the database row, cascades text/audio segment metadata, and removes cached audio files for that generation.

## Application Logging

Uvicorn access logs show HTTP requests. The app also emits structured application logs through Python's standard `logging` module under `tts_app.api` and `tts_app.generation`. These include generation submission, URL extraction failures, generation start/completion/failure, segment start/completion/failure, playback progress updates, and deletion.

In development, run with Uvicorn log level `info` and pipe stdout/stderr if you want a file:

```bash
mkdir -p logs
TTS_PROVIDER=qwen .venv/bin/uvicorn tts_app.api:create_app --factory --reload --reload-dir src --host 127.0.0.1 --port 8001 --log-level info 2>&1 | tee -a logs/app.log
```

## Tests

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```

## Verification Checklist

1. Run `pytest`.
2. Run `TTS_PROVIDER=fake .venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001`.
3. Open `http://127.0.0.1:8001`.
4. Paste text with multiple sentences and generate audio.
5. Confirm segments appear in Playback.
6. Tap a text segment and confirm playback jumps to that segment.
7. Open History and confirm the generation is listed.
8. Reopen the item from History and confirm cached segments are still available.
9. Try a basic HTML URL and confirm extracted text appears in Playback.
10. Confirm History shows URL, voice, speed, and progress details.
11. Delete a history entry and confirm it disappears.
