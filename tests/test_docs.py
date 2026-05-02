from __future__ import annotations

from pathlib import Path


def test_handoff_docs_exist_and_cover_local_operations():
    readme = Path("README.md").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")

    assert "Tailscale" in readme
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
    assert "Storage" in agents
    assert "Tailscale" in agents
    assert "setup/tts.service" in agents
    assert "Do not commit secrets" in agents
    assert "Pricing Notes" in agents


def test_systemd_setup_files_match_vps_pattern():
    service = Path("setup/tts.service").read_text(encoding="utf-8")
    readme = Path("setup/README.md").read_text(encoding="utf-8")
    env_example = Path("setup/envrc.local.example").read_text(encoding="utf-8")

    assert "WorkingDirectory=/home/mohan/tts" in service
    assert "EnvironmentFile=/home/mohan/tts/.envrc.local" in service
    assert "--reload" in service
    assert "--host 127.0.0.1" in service
    assert "--port 8001" in service
    assert "sudo install -m 0644 setup/tts.service /etc/systemd/system/tts.service" in readme
    assert "sudo tailscale serve --bg --https=8001 http://127.0.0.1:8001" in readme
    assert "journalctl -u tts -f" in readme
    assert "TTS_PROVIDER=qwen" in env_example
    assert "DASHSCOPE_API_KEY=" in env_example
