# Operations

## Development Server

Use this while actively editing the app. `--reload` restarts the Python process when files under `src/` change.

```bash
cd /home/mohan/tts

TTS_PROVIDER=fake \
.venv/bin/uvicorn tts_app.api:create_app \
  --factory \
  --reload \
  --reload-dir src \
  --host 127.0.0.1 \
  --port 8001 \
  --log-level info
```

Open `http://127.0.0.1:8001` locally, or use your private HTTPS proxy URL if configured.

## Application Logging

Uvicorn access logs show HTTP requests. The app also emits structured application logs through Python's standard `logging` module under `tts_app.api` and `tts_app.generation`. These include generation submission, URL extraction failures, generation start/completion/failure, segment start/completion/failure, playback progress updates, and deletion.

To keep application and access logs in a file while still seeing them in the terminal:

```bash
mkdir -p logs
TTS_PROVIDER=fake .venv/bin/uvicorn tts_app.api:create_app --factory --reload --reload-dir src --host 127.0.0.1 --port 8001 --log-level info 2>&1 | tee -a logs/app.log
```

For systemd logs:

```bash
journalctl -u tts -f
```

## Verification Checklist

1. Run `.venv/bin/pytest -q`.
2. Run `npm run check:js`, `npm run lint:js`, and `npm run test:js`.
3. Run `TTS_PROVIDER=fake .venv/bin/uvicorn tts_app.api:create_app --factory --host 127.0.0.1 --port 8001`.
4. Open `http://127.0.0.1:8001`.
5. Paste text with multiple sentences and generate audio.
6. Confirm segments appear in Playback.
7. Tap a text segment and confirm playback jumps to that segment.
8. Let playback continue and confirm the highlighted text advances.
9. Open History and confirm the generation is listed with voice, speed, and progress details.
10. Reopen the item from History and confirm cached audio is still available.
11. Try a basic HTML URL and confirm extracted text appears in Playback.
12. Delete a history entry and confirm it disappears.
