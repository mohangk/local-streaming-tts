# Local Streaming TTS

Local, mobile-first web app for generating streamed text-to-speech audio from pasted text or basic HTML page URLs.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
uvicorn tts_app.api:create_app --factory --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000` locally, or use the machine's Tailscale address when exposing it to your own devices.

## Development Provider

The default provider is `fake`, which writes deterministic small audio-like files and does not call an external API.

```bash
TTS_PROVIDER=fake uvicorn tts_app.api:create_app --factory --reload
```

## Qwen Provider Configuration

```bash
TTS_PROVIDER=qwen
DASHSCOPE_API_KEY=...
QWEN_MODEL=qwen3-tts-flash-realtime
QWEN_REALTIME_URL=wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
QWEN_VOICE=Cherry
```

## Tests

```bash
pytest
```

## Verification Checklist

1. Run `pytest`.
2. Run `TTS_PROVIDER=fake uvicorn tts_app.api:create_app --factory --host 0.0.0.0 --port 8000`.
3. Open `http://127.0.0.1:8000`.
4. Paste text with multiple sentences and generate audio.
5. Confirm segments appear in Playback.
6. Tap a text segment and confirm playback jumps to that segment.
7. Open History and confirm the generation is listed.
8. Reopen the item from History and confirm cached segments are still available.
9. Try a basic HTML URL and confirm extracted text appears in Playback.
