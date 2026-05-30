from __future__ import annotations

from pathlib import Path


def test_handoff_docs_exist_and_cover_local_operations():
    readme = Path("README.md").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")
    architecture_reviewer = Path("docs/architecture-review-subagent.md").read_text(encoding="utf-8")
    architecture_agent = Path(".codex/agents/architecture-reviewer.toml").read_text(encoding="utf-8")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "# Readvox" in readme
    assert "name = \"readvox\"" in pyproject
    assert "Qwen" in readme
    assert "pytest" in readme
    assert "uvicorn" in readme
    assert "model-pricing" in readme
    assert "qwen3-tts-flash-realtime" in readme
    assert "TTS_MODEL" in readme
    assert "remove old `QWEN_MODEL`, `QWEN_OCR_MODEL`, and `QWEN_VOICE` entries" in readme
    assert "$0.13 / 10K characters" in readme
    assert "Application Logging" in readme
    assert "tts_app.generation" in readme
    assert "Development Start" in readme
    assert "--reload-dir src" in readme
    assert "Systemd Deployment" in readme
    assert "OCR Image Mode" in readme
    assert "OCR_PROVIDER" in readme
    assert "OCR_MODEL" in readme
    assert "TTS_IMAGE_DIR" in readme
    assert "TTS_MAX_IMAGE_BYTES" in readme
    assert "TTS_DEFAULT_ENGLISH_VOICE" in readme
    assert "TTS_DEFAULT_CHINESE_VOICE" in readme
    assert "data/images/" in readme
    assert "Voice samples" in readme
    assert "do not create History entries" in readme
    assert "# Readvox Architecture" in architecture
    assert "provider interfaces" in architecture
    assert "SQLite" in architecture
    assert "filesystem" in architecture
    assert "Drafts And Linked Artifacts" in architecture
    assert "workflow drafts" in architecture
    assert "Linked drafts should disappear from active draft-picking surfaces" in architecture
    assert "OCR is the current example of this model" in architecture
    assert "visible Chinese text and visible pinyin" in architecture
    assert "Future modularization should split `app.js` further" in architecture
    assert "history.js" in architecture
    assert "playback.js" in architecture
    assert "generation-form.js" in architecture
    assert "voice-controls.js" in architecture
    assert "api-client.js" in architecture
    assert "forward migrations" in architecture
    assert "fake implementation" in architecture
    assert "Architecture Review" in architecture
    assert "docs/architecture-review-subagent.md" in architecture
    assert "# Architecture Review Subagent" in architecture_reviewer
    assert ".codex/agents/architecture-reviewer.toml" in architecture_reviewer
    assert "architecture_reviewer" in architecture_reviewer
    assert "Review the current diff against `docs/architecture.md`" in architecture_reviewer
    assert "Provider boundaries" in architecture_reviewer
    assert "Drafts and linked artifacts" in architecture_reviewer
    assert "Frontend modularity" in architecture_reviewer
    assert "Output format" in architecture_reviewer
    assert 'name = "architecture_reviewer"' in architecture_agent
    assert 'sandbox_mode = "read-only"' in architecture_agent
    assert 'developer_instructions = """' in architecture_agent
    assert "docs/architecture.md" in architecture_agent
    assert "Frontend modularity" in architecture_agent
    assert "Architecture Review" in architecture_agent
    assert ".codex/*" in gitignore
    assert "!.codex/agents/*.toml" in gitignore
    assert "docs/architecture.md" in agents
    assert ".codex/agents/architecture-reviewer.toml" in agents
    assert "docs/architecture-review-subagent.md" in agents
    assert "Storage" in agents
    assert "Private Proxy" in agents
    assert "setup/tts.service" in agents
    assert "Do not commit secrets" in agents
    assert "Pricing Notes" in agents
    assert "src/tts_app/ocr_providers/" in agents
    assert "stored images" in agents
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
    assert "TTS_MODEL=qwen3-tts-flash-realtime" in env_example
    assert "OCR_PROVIDER=qwen" in env_example
    assert "OCR_MODEL=qwen-vl-ocr" in env_example
    assert "TTS_DEFAULT_ENGLISH_VOICE=Jennifer" in env_example
    assert "TTS_DEFAULT_CHINESE_VOICE=Cherry" in env_example
    assert "QWEN_MODEL=" not in env_example
    assert "QWEN_OCR_MODEL=" not in env_example
    assert "QWEN_VOICE=" not in env_example
    assert "remove old" in env_example
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
