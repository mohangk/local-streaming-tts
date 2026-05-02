# Deploying local TTS on pongo

This folder is the source of truth for the VPS deployment. The unit file in
`/etc/systemd/system/` on pongo should be installed from `tts.service` in this
folder.

The setup mirrors `time-consumer`: a localhost-bound development server runs
under systemd with reload enabled, and Tailscale Serve terminates HTTPS for
tailnet clients.

## One-time install

Prerequisites: repo cloned at `/home/mohan/tts` with venv created and
dependencies installed:

```bash
cd /home/mohan/tts
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

1. Copy `setup/envrc.local.example` to `/home/mohan/tts/.envrc.local`, fill in
   the real DashScope API key, and restrict permissions:

   ```bash
   cp setup/envrc.local.example .envrc.local
   chmod 0600 .envrc.local
   ```

2. Install the unit file and enable the service:

   ```bash
   sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now tts
   ```

3. Expose via Tailscale Serve:

   ```bash
   sudo tailscale serve --bg --https=8001 http://127.0.0.1:8001
   ```

4. Verify from a trusted tailnet client:

   ```text
   https://pongo.lorikeet-dragon.ts.net:8001
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
tailscale serve status
ss -ltnp | grep :8001
```

## Failure modes

| Mode | Symptom | Recovery |
|---|---|---|
| SyntaxError after `git pull` | Reloader logs traceback; previous worker may keep serving | Save a fix; reloader re-imports |
| Missing API key | Qwen generations fail with provider auth errors | Add `DASHSCOPE_API_KEY` to `.envrc.local`; restart |
| Env file missing | Unit fails during startup | Copy `setup/envrc.local.example` to `.envrc.local`; restart |
| Tailscale Serve config drift | URL no longer resolves | Re-run `sudo tailscale serve --bg --https=8001 http://127.0.0.1:8001` |
| Port 8001 already in use | Unit fails with address-in-use error | `ss -ltnp \| grep :8001`, stop the conflicting process, restart |
