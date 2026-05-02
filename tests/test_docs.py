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
    assert "Storage" in agents
    assert "Tailscale" in agents
    assert "Do not commit secrets" in agents
    assert "Pricing Notes" in agents
