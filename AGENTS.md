# Repository Guide

## Project

This repo contains a local, mobile-first FastAPI app for generating streamed text-to-speech audio from pasted text or simple HTML URLs. It is intended to run on the VPS as a localhost HTTP service and be exposed to trusted devices through Tailscale Serve.

## Layout

- `src/tts_app/api.py`: FastAPI routes and app factory.
- `src/tts_app/storage.py`: SQLite schema, migrations, generation history, progress, and segment metadata.
- `src/tts_app/generation.py`: text segmentation to provider streaming to cached audio files.
- `src/tts_app/providers/`: provider interface plus fake and Qwen realtime implementations.
- `src/tts_app/static/`: lightweight HTML/CSS/JavaScript frontend.
- `tests/`: API, storage, provider, generation, extractor, segmenter, frontend-static, and docs tests.

## Local Commands

Run tests before claiming work is complete:

```bash
.venv/bin/pytest -q
node --check src/tts_app/static/app.js
```

Run locally with the fake provider:

```bash
TTS_PROVIDER=fake .venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001
```

Run locally with Qwen:

```bash
TTS_PROVIDER=qwen .venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001
```

## Tailscale

The VPS pattern is a plain HTTP service bound to localhost, exposed through HTTPS by Tailscale Serve:

```bash
sudo tailscale serve --bg --https=8001 http://127.0.0.1:8001
```

Then open `https://pongo.lorikeet-dragon.ts.net:8001` from a trusted tailnet device.

## Storage

The default data directory is `data/`. SQLite stores generations, text segments, audio segment metadata, provider settings, and playback progress. Audio files are cached under `data/audio/<generation_id>/`.

Do not remove user data or generated audio unless the user explicitly asks. Deleting a generation through the app removes the SQLite row and cached audio directory for that generation.

## Provider Notes

The fake provider is deterministic and should be used for tests and local UI checks. Qwen credentials come from `DASHSCOPE_API_KEY` or `QWEN_API_KEY`. Do not commit secrets, API keys, generated smoke-test audio, or local data files.

## Development Rules

- Prefer focused tests for storage/API/frontend behavior before implementation.
- Keep frontend JavaScript lightweight and mobile-first.
- Keep TTS provider behavior behind the provider interface.
- Treat the same text or URL with a different voice or speed as a separate generation.
- Preserve unrelated untracked files such as `.codex` or smoke-test artifacts unless the user asks otherwise.
