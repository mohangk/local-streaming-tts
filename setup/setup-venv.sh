#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_DIR}"

if [[ ! -d ".venv" ]]; then
  python -m venv .venv
fi

.venv/bin/pip install -e ".[dev]"

echo "Python environment ready at ${REPO_DIR}/.venv"
