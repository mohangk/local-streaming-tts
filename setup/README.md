# Deploying Readvox

This folder is the source of truth for the VPS deployment. The unit file in
`/etc/systemd/system/` should be installed from `tts.service` in this
folder.

The setup mirrors `time-consumer`: a localhost-bound development server runs
under systemd with reload enabled. If remote access is needed, put a private
HTTPS proxy in front of `127.0.0.1:8001`.

## One-time install

Prerequisite: repo cloned at `/home/mohan/tts`.

Run the venv setup script:

```bash
cd /home/mohan/tts
setup/setup-venv.sh
```

Run the systemd setup script:

```bash
setup/install-service.sh
```

The venv script creates `.venv` if needed and installs dependencies. The systemd
script creates `.envrc.local` from the example if it is missing and
installs/enables the service.

Manual equivalent:

1. Create the venv and install dependencies:

   ```bash
   python -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

2. Copy `setup/envrc.local.example` to `/home/mohan/tts/.envrc.local`, fill in
   the real DashScope API key, and restrict permissions:

   ```bash
   cp setup/envrc.local.example .envrc.local
   chmod 0600 .envrc.local
   ```

3. Install the unit file and enable the service:

   ```bash
   sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now tts
   ```

4. Verify locally:

   ```text
   http://127.0.0.1:8001
   ```

## Qwen API key

Put the key in `/home/mohan/tts/.envrc.local`:

```bash
DASHSCOPE_API_KEY=<your-key>
```

The systemd unit reads this file through `EnvironmentFile=`. After changing the
key, restart the service:

```bash
sudo systemctl restart tts
```

## Day-to-day update flows

### Code edits

```bash
cd /home/mohan/tts
git pull
```

Uvicorn's reloader detects Python changes under `src/`. Frontend assets usually
only need a browser refresh. Confirm reloads with:

```bash
journalctl -u tts -f
```

### Dependency change

```bash
cd /home/mohan/tts
git pull
.venv/bin/pip install -e ".[dev]"
sudo systemctl restart tts
```

### Unit file or env file change

```bash
cd /home/mohan/tts
git pull
sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service
sudo systemctl daemon-reload
sudo systemctl restart tts
```

Edits to `.envrc.local` are picked up on service restart. They do not require
`daemon-reload`.

## Diagnostics

```bash
systemctl status tts
journalctl -u tts -f
ss -ltnp | grep :8001
```

## Failure modes

| Mode | Symptom | Recovery |
|---|---|---|
| SyntaxError after `git pull` | Reloader logs traceback; previous worker may keep serving | Save a fix; reloader re-imports |
| Missing API key | Qwen generations fail with provider auth errors | Add `DASHSCOPE_API_KEY` to `.envrc.local`; restart |
| Env file missing | Unit fails during startup | Copy `setup/envrc.local.example` to `.envrc.local`; restart |
| Port 8001 already in use | Unit fails with address-in-use error | `ss -ltnp \| grep :8001`, stop the conflicting process, restart |

### Named voice profile upgrade

Set the local `.envrc.local` override to `TTS_MODEL=qwen3-tts-instruct-flash-realtime` before restarting; a preexisting `TTS_MODEL` overrides the new default. New installations use `TTS_DEFAULT_ENGLISH_VOICE=Kai`, a supported instruction voice. Review any explicit legacy default voice override separately; named profiles snapshot their own supported voice/model. Keep credentials local and uncommitted.

Check `/api/generations` for `queued` or `running` work and wait for it to finish before restarting `tts.service`. Startup adds profile tables and editable English/Chinese defaults without rewriting generation settings or touching cached audio. Profiles are shared across devices; selected profile IDs are browser-local.
