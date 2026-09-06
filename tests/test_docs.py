from __future__ import annotations

import sqlite3
import tomllib
from pathlib import Path

from tts_app.storage import Storage


def _normalized_block_between(text: str, start: str, end: str) -> str:
    block = text.split(start, 1)[1].split(end, 1)[0]
    return "\n".join(line.rstrip() for line in block.strip().splitlines())


def _normalized_prompt_body(markdown: str) -> str:
    return "\n".join(line.rstrip() for line in markdown.split("## Prompt", 1)[1].strip().splitlines())


def test_handoff_docs_exist_and_cover_local_operations():
    readme = Path("README.md").read_text(encoding="utf-8")
    configuration = Path("docs/configuration.md").read_text(encoding="utf-8")
    data_model = Path("docs/data-model.md").read_text(encoding="utf-8")
    deployment = Path("docs/deployment.md").read_text(encoding="utf-8")
    operations = Path("docs/operations.md").read_text(encoding="utf-8")
    schema = Path("docs/schema.sql").read_text(encoding="utf-8")
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
    assert "local-first" in readme
    assert "continuous playback" in readme
    assert "flowchart LR" in readme
    assert "docs/schema.sql" in readme
    assert "docs/data-model.md" in readme
    assert "docs/configuration.md" in readme
    assert "docs/deployment.md" in readme
    assert "docs/operations.md" in readme
    assert "Qwen" in readme
    assert "pytest" in readme
    assert "npm run test:js" in readme
    assert "npm run test:js" in agents
    assert "RUN_QWEN_INTEGRATION=1" in agents
    assert "npm run test:js" in architecture
    assert "RUN_QWEN_INTEGRATION=1" in architecture
    assert "uvicorn" in readme
    assert "model-pricing" in configuration
    assert "qwen3-tts-flash-realtime" in configuration
    assert "TTS_MODEL" in readme
    assert "Remove old `QWEN_MODEL`, `QWEN_OCR_MODEL`, and `QWEN_VOICE` entries" in configuration
    assert "$0.13 / 10K characters" in configuration
    assert "Application Logging" in operations
    assert "tts_app.generation" in operations
    assert "Development Server" in operations
    assert "--reload-dir src" in operations
    assert "# Deployment" in deployment
    assert "setup/tts.service" in deployment
    assert "OCR Image Mode" in configuration
    assert "OCR_PROVIDER" in configuration
    assert "OCR_MODEL" in configuration
    assert "TTS_IMAGE_DIR" in configuration
    assert "TTS_MAX_IMAGE_BYTES" in configuration
    assert "TTS_DEFAULT_ENGLISH_VOICE" in configuration
    assert "TTS_DEFAULT_CHINESE_VOICE" in configuration
    assert "data/images/" in configuration
    assert "Voice samples" in configuration
    assert "Previewing never creates a History entry" in configuration
    assert "/voice-sample" in configuration
    assert "Model/voice capabilities and language validation are shared" in configuration
    assert "live provider integration" in configuration
    assert "# Data Model" in data_model
    assert "erDiagram" in data_model
    assert "continuous_audio_artifacts" in data_model
    assert "playback_telemetry_events" in data_model
    assert "current unsaved preview text and instructions" in data_model
    assert "DELETE /api/voice-samples/cache" in data_model
    assert "full voice sample cache" in data_model
    assert "CREATE TABLE generations" in schema
    assert "CREATE TABLE continuous_audio_artifacts" in schema
    assert "CREATE TABLE playback_telemetry_events" in schema
    assert "CREATE TABLE ocr_drafts" in schema
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
    assert "SQLite-backed playback telemetry" in architecture
    assert "content-free" in architecture
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
    assert "TTS_MODEL=qwen3-tts-instruct-flash-realtime" in env_example
    assert "OCR_PROVIDER=qwen" in env_example
    assert "OCR_MODEL=qwen-vl-ocr" in env_example
    assert "TTS_DEFAULT_ENGLISH_VOICE=Kai" in env_example
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


def test_schema_doc_matches_initialized_storage_schema(tmp_path):
    schema = Path("docs/schema.sql").read_text(encoding="utf-8")
    documented_db = sqlite3.connect(":memory:")
    documented_db.executescript(schema)

    storage = Storage(tmp_path / "app.db")
    storage.init_schema()
    storage_db = sqlite3.connect(tmp_path / "app.db")

    def object_definitions(conn: sqlite3.Connection, object_type: str) -> dict[str, str]:
        rows = conn.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = ?
              AND name NOT LIKE 'sqlite_%'
              AND name NOT LIKE 'sqlite_autoindex_%'
            ORDER BY name
            """,
            (object_type,),
        ).fetchall()
        return {str(row[0]): " ".join(str(row[1]).split()) for row in rows}

    assert object_definitions(documented_db, "table") == object_definitions(storage_db, "table")
    assert object_definitions(documented_db, "index") == object_definitions(storage_db, "index")
