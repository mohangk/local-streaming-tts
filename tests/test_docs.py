from __future__ import annotations

import tomllib
from pathlib import Path


def _normalized_block_between(text: str, start: str, end: str) -> str:
    block = text.split(start, 1)[1].split(end, 1)[0]
    return "\n".join(line.rstrip() for line in block.strip().splitlines())


def _normalized_prompt_body(markdown: str) -> str:
    return "\n".join(line.rstrip() for line in markdown.split("## Prompt", 1)[1].strip().splitlines())


def test_handoff_docs_exist_and_cover_local_operations():
    readme = Path("README.md").read_text(encoding="utf-8")
    agents = Path("AGENTS.md").read_text(encoding="utf-8")
    architecture = Path("docs/architecture.md").read_text(encoding="utf-8")
    architecture_reviewer = Path("docs/architecture-review-subagent.md").read_text(encoding="utf-8")
    architecture_agent_text = Path(".codex/agents/architecture-reviewer.toml").read_text(encoding="utf-8")
    architecture_agent = tomllib.loads(architecture_agent_text)
    architecture_agent_instructions = architecture_agent["developer_instructions"]
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "# Readvox" in readme
    assert "name = \"readvox\"" in pyproject
    assert "Qwen" in readme
    assert "pytest" in readme
    assert "npm run test:js" in readme
    assert "npm run test:js" in agents
    assert "npm run test:js" in architecture
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
    assert architecture_agent["name"] == "architecture_reviewer"
    assert architecture_agent["sandbox_mode"] == "read-only"
    assert architecture_agent["model_reasoning_effort"] == "high"
    assert "docs/architecture.md" in architecture_agent_instructions
    assert "Architecture Review" in architecture_agent_instructions
    assert _normalized_prompt_body(architecture_reviewer) == "\n".join(
        line.rstrip() for line in architecture_agent_instructions.strip().splitlines()
    )
    assert _normalized_block_between(
        architecture_reviewer,
        "Check these areas:",
        "Output format:",
    ) == _normalized_block_between(
        architecture_agent_instructions,
        "Check these areas:",
        "Output format:",
    )
    assert _normalized_block_between(
        architecture_reviewer,
        "Output format:",
        "If there are no findings",
    ) == _normalized_block_between(
        architecture_agent_instructions,
        "Output format:",
        "If there are no findings",
    )
    for checklist_anchor in (
        "Runtime shape",
        "Provider boundaries",
        "Storage and migrations",
        "Drafts and linked artifacts",
        "Route/API boundaries",
        "Frontend modularity",
        "Tests",
        "Commit and PR shape",
    ):
        assert checklist_anchor in architecture_reviewer
        assert checklist_anchor in architecture_agent_instructions
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
