# Repository Guide

## Project

This repo contains Readvox, a local, mobile-first FastAPI app for generating streamed text-to-speech audio from pasted text or simple HTML URLs. It is intended to run as a localhost HTTP service and optionally be exposed to trusted devices through a private HTTPS proxy.

For durable architecture, module boundaries, storage semantics, frontend modularization direction, and future feature patterns, read `docs/architecture.md`.

## Layout

- `src/tts_app/api.py`: FastAPI routes and app factory.
- `src/tts_app/storage.py`: SQLite schema, migrations, generation history, progress, and segment metadata.
- `src/tts_app/generation.py`: text segmentation to provider streaming to cached audio files.
- `src/tts_app/providers/`: provider interface plus fake and Qwen realtime implementations.
- `src/tts_app/ocr_providers/`: OCR provider interface plus fake and Qwen OCR implementations.
- `src/tts_app/static/`: lightweight HTML/CSS/JavaScript frontend.
- `tests/`: API, storage, provider, generation, extractor, segmenter, frontend-static, and docs tests.

## Local Commands

Run tests before claiming work is complete:

```bash
.venv/bin/pytest -q
npm run check:js
npm run lint:js
npm run test:js
```

Run locally with the fake provider:

```bash
TTS_PROVIDER=fake .venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001
```

Run locally with Qwen:

```bash
TTS_PROVIDER=qwen .venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001
```

## Private Proxy

The deployment pattern is a plain HTTP service bound to `127.0.0.1:8001`. If remote access is needed, put a private HTTPS proxy in front of that local port and grant access only to trusted devices.

## Systemd

The versioned systemd deployment source lives under `setup/`, mirroring
the setup folder used by companion local services.

- `setup/tts.service` installs to `/etc/systemd/system/tts.service`.
- `setup/envrc.local.example` is copied to `/home/mohan/tts/.envrc.local` and filled with real secrets.
- `setup/README.md` contains install, update, diagnostics, and failure-mode commands.

Do not commit `.envrc.local`.

## Storage

The default data directory is `data/`. SQLite stores generations, text segments, audio segment metadata, provider settings, and playback progress. Audio files are cached under `data/audio/<generation_id>/`.

Images are stored under `data/images/<ocr_draft_id>/` by default, with one child directory per source image. Do not remove user data, stored images, or generated audio unless the user explicitly asks or the app deletion flow is being exercised. Deleting an unlinked OCR draft through the app removes its stored image directory. Deleting an image generation through the app removes the SQLite row, cached audio directory, linked OCR draft, and stored source image directories.

## Secrets And Providers

Do not commit secrets, API keys, stored images, generated smoke-test audio, generated audio, or local data files. Use the fake providers for tests and local UI checks unless a task explicitly requires Qwen.

## Pricing Notes

The app currently uses `qwen3-tts-flash-realtime` by default. Alibaba Cloud Model Studio pricing is captured in `README.md` with the source URL and capture date. As of the May 02, 2026 capture, the international endpoint price is `$0.13 / 10K input text characters` with output not billed. Use that as context for future estimated-cost tracking, but re-check the Alibaba pricing page before implementing billing-sensitive behavior.

## Development Rules

- Follow `docs/architecture.md` for module boundaries, schema migration style, provider boundaries, frontend modularization, and future feature sequencing.
- After every non-trivial change, run the `architecture_reviewer` custom agent from `.codex/agents/architecture-reviewer.toml`, or simulate the same checklist from `docs/architecture-review-subagent.md`, before merging or pushing to `main`.
- Treat the same text or URL with a different voice or speed as a separate generation.
- Preserve unrelated untracked files such as `.codex` or smoke-test artifacts unless the user asks otherwise.
