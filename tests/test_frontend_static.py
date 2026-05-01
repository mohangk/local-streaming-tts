from __future__ import annotations

import tomllib
from pathlib import Path


STATIC_DIR = Path("src/tts_app/static")
PYPROJECT = Path("pyproject.toml")


def test_frontend_has_generate_history_and_playback_views():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="generate-view"' in html
    assert 'id="history-view"' in html
    assert 'id="playback-view"' in html
    assert 'id="autoplay"' in html


def test_frontend_javascript_uses_history_and_event_endpoints():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/api/generations/text" in js
    assert "/api/generations/url" in js
    assert "EventSource" in js
    assert "scrollIntoView" in js


def test_frontend_javascript_ended_handler_respects_autoplay_toggle():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    handler = js.split('audioPlayer.addEventListener("ended"', 1)[1].split("loadHistory();", 1)[0]

    assert "state.autoplay" in handler
    assert "playSegment(nextIndex)" in handler


def test_frontend_history_open_disables_subscription_and_autoplay():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    handler = js.split('historyList.addEventListener("click"', 1)[1].split('readingPane.addEventListener("click"', 1)[0]

    assert "openGeneration(Number(item.dataset.generationId), { subscribe: false, autoplay: false })" in handler


def test_frontend_event_source_handles_errors():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "state.eventSource.onerror" in js
    assert "state.eventSource.close()" in js


def test_frontend_fetch_paths_have_error_handling():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert js.count("try {") >= 3
    assert "catch" in js
    assert "resetPlaybackState(" in js


def test_frontend_generation_detail_loads_ignore_stale_results():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    detail_loader = js.split("async function loadGenerationDetail(generationId)", 1)[1].split(
        "function closeEventSource()", 1
    )[0]
    event_handler = js.split("function handleEventMessage(message, generationId)", 1)[1].split(
        "function subscribeToGeneration(generationId)", 1
    )[0]

    assert "state.currentGenerationId !== generationId" in detail_loader
    assert "return null" in detail_loader
    assert "return state.currentGenerationId === generationId" in detail_loader
    assert "loaded &&" in event_handler


def test_frontend_css_is_mobile_first():
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert "bottom-nav" in css
    assert "@media (min-width: 800px)" in css
    assert "active-segment" in css


def test_package_includes_frontend_static_assets():
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["tts_app"]

    assert "static/*.html" in package_data
    assert "static/*.css" in package_data
    assert "static/*.js" in package_data
