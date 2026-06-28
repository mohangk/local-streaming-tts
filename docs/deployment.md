# Deployment

Readvox is intended to run as a localhost HTTP service. If remote access is needed, put a private HTTPS proxy in front of `127.0.0.1:8001` and grant access only to trusted devices.

The versioned systemd deployment files live in `setup/`:

- `setup/tts.service`: source-of-truth systemd unit for `/etc/systemd/system/tts.service`
- `setup/envrc.local.example`: environment file template for `/home/mohan/tts/.envrc.local`
- `setup/setup-venv.sh`: creates `.venv` and installs Python dependencies
- `setup/install-service.sh`: installs/enables the systemd service
- `setup/README.md`: lower-level install, update, diagnostics, and recovery commands

## One-Time Install

Prerequisite: repo cloned at `/home/mohan/tts`.

```bash
cd /home/mohan/tts
setup/setup-venv.sh
setup/install-service.sh
```

Manual equivalent:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp setup/envrc.local.example .envrc.local
chmod 0600 .envrc.local
sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service
sudo systemctl daemon-reload
sudo systemctl enable --now tts
```

Set the provider API key in `/home/mohan/tts/.envrc.local`:

```bash
DASHSCOPE_API_KEY=<your-key>
```

Restart after changing environment values:

```bash
sudo systemctl restart tts
```

## Trust Boundary

URL generation fetches pages server-side from the host running this app. Anyone who can access Readvox can ask that host to fetch arbitrary HTTP(S) URLs reachable from the machine. Do not expose the app publicly.
