from __future__ import annotations

from pathlib import Path


def test_handoff_docs_exist_and_cover_local_operations():
    readme = Path("README.md").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "# Readvox" in readme
    assert "name = \"readvox\"" in pyproject
    assert "Qwen" in readme
    assert "pytest" in readme
    assert "uvicorn" in readme
    assert "model-pricing" in readme
    assert "qwen3-tts-flash-realtime" in readme
    assert "$0.13 / 10K characters" in readme
    assert "Application Logging" in readme
    assert "tts_app.generation" in readme
    assert "Development Start" in readme
    assert "--reload-dir src" in readme
    assert "Systemd Deployment" in readme
    assert "OCR Image Mode" in readme
    assert "OCR_PROVIDER" in readme
    assert "QWEN_OCR_MODEL" in readme
    assert "TTS_IMAGE_DIR" in readme
    assert "TTS_MAX_IMAGE_BYTES" in readme
    assert "TTS_DEFAULT_ENGLISH_VOICE" in readme
    assert "TTS_DEFAULT_CHINESE_VOICE" in readme
    assert "data/images/" in readme
    assert "Voice samples" in readme
    assert "do not create History entries" in readme
    assert "Storage" in agents
    assert "Private Proxy" in agents
    assert "setup/tts.service" in agents
    assert "Do not commit secrets" in agents
    assert "Pricing Notes" in agents
    assert "src/tts_app/ocr_providers/" in agents
    assert "stored images" in agents
    assert "visible Chinese text and visible pinyin" in agents
    assert "Do not commit secrets, API keys, stored images" in agents


def test_systemd_setup_files_match_vps_pattern():
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    service = Path("setup/tts.service").read_text(encoding="utf-8")
    readme = Path("setup/README.md").read_text(encoding="utf-8")
    env_example = Path("setup/envrc.local.example").read_text(encoding="utf-8")
    install_script = Path("setup/install-service.sh").read_text(encoding="utf-8")
    venv_script = Path("setup/setup-venv.sh").read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/mohan/tts" in service
    assert "EnvironmentFile=/home/mohan/tts/.envrc.local" in service
    assert "--reload" in service
    assert "--host 127.0.0.1" in service
    assert "--port 8001" in service
    assert "sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service" in readme
    assert "journalctl -u tts -f" in readme
    assert "TTS_PROVIDER=qwen" in env_example
    assert "DASHSCOPE_API_KEY=" in env_example
    assert "setup/install-service.sh" in readme
    assert "setup/setup-venv.sh" in readme
    assert "DASHSCOPE_API_KEY" in install_script
    assert "sudo systemctl enable --now tts" in install_script
    assert "private" in readme
    assert "HTTPS proxy" in readme
    assert "python -m venv .venv" in venv_script
    assert '.venv/bin/pip install -e ".[dev]"' in venv_script
    assert "pip install" not in install_script
    assert "python -m venv" not in install_script
    assert ".envrc.local" in gitignore
