#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_DIR}/.envrc.local"
ENV_EXAMPLE="${SCRIPT_DIR}/envrc.local.example"
SERVICE_FILE="${SCRIPT_DIR}/tts.service"
SYSTEMD_SERVICE="/etc/systemd/system/tts.service"

cd "${REPO_DIR}"

if [[ ! -x ".venv/bin/python" ]]; then
  echo "Missing .venv. Run setup/setup-venv.sh first." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  chmod 0600 "${ENV_FILE}"
  echo "Created ${ENV_FILE}"
  echo "Edit ${ENV_FILE} and set DASHSCOPE_API_KEY before generating with Qwen."
else
  chmod 0600 "${ENV_FILE}"
  echo "Using existing ${ENV_FILE}"
fi

sudo install -m 0644 "${SERVICE_FILE}" "${SYSTEMD_SERVICE}"
sudo systemctl daemon-reload
sudo systemctl enable --now tts

echo
echo "TTS systemd service setup complete."
echo "Qwen API key location: ${ENV_FILE}"
echo "Set it as: DASHSCOPE_API_KEY=<your-key>"
echo "After changing the key, run: sudo systemctl restart tts"
echo "Tail logs with: journalctl -u tts -f"
