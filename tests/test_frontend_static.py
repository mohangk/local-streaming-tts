from __future__ import annotations

import tomllib
from pathlib import Path


STATIC_DIR = Path("src/tts_app/static")
PYPROJECT = Path("pyproject.toml")


def test_frontend_has_generate_history_and_playback_views():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="generate-view"' in html
    assert "<title>Readvox</title>" in html
    assert 'id="history-view"' in html
    assert 'id="playback-view"' in html
    assert 'id="autoplay"' in html
    assert 'id="voice-select"' in html
    assert 'id="speed-select"' in html


def test_frontend_javascript_uses_history_and_event_endpoints():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/api/generations/text" in js
    assert "/api/generations/url" in js
    assert "/api/options" in js
    assert "/progress" in js
    assert "payload.voice" in js
    assert "payload.speed" in js
    assert "EventSource" in js
    assert "scrollIntoView" in js


def test_frontend_javascript_ended_handler_respects_continuous_playback():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    handler = js.split('audioPlayer.addEventListener("ended"', 1)[1].split("loadHistory();", 1)[0]

    assert "state.continuousPlayback" in handler
    assert "playSegment(nextIndex)" in handler


def test_frontend_user_started_history_playback_continues_between_segments():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    play_button_handler = js.split('playPauseButton.addEventListener("click"', 1)[1].split(
        'audioPlayer.addEventListener("play"', 1
    )[0]
    reading_handler = js.split('readingPane.addEventListener("click"', 1)[1].split(
        'playPauseButton.addEventListener("click"', 1
    )[0]

    assert "state.continuousPlayback = true" in play_button_handler
    assert "state.continuousPlayback = false" in play_button_handler
    assert "state.continuousPlayback = true" in reading_handler


def test_frontend_requests_screen_wake_lock_during_playback():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "async function acquireWakeLock" in js
    assert "navigator.wakeLock.request(\"screen\")" in js
    assert "function releaseWakeLock" in js
    assert "document.addEventListener(\"visibilitychange\"" in js
    assert "acquireWakeLock()" in js.split('audioPlayer.addEventListener("play"', 1)[1].split(
        'audioPlayer.addEventListener("pause"', 1
    )[0]
    assert "releaseWakeLock()" in js.split('audioPlayer.addEventListener("pause"', 1)[1].split(
        'audioPlayer.addEventListener("ended"', 1
    )[0]


def test_frontend_history_open_disables_subscription_and_autoplay():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    handler = js.split('historyList.addEventListener("click"', 1)[1].split('readingPane.addEventListener("click"', 1)[0]

    assert 'action.dataset.action === "open"' in handler
    assert "openGeneration(generationId, { subscribe: false, autoplay: false })" in handler


def test_frontend_history_renders_url_metadata_and_delete_controls():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    renderer = js.split("function renderHistory()", 1)[1].split("async function openGeneration", 1)[0]

    assert "item.url" in renderer
    assert "<details" in renderer
    assert "Voice" in renderer
    assert "Speed" in renderer
    assert "Progress" in renderer
    assert "data-action=\"delete\"" in renderer


def test_frontend_history_delete_calls_delete_endpoint():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "async function deleteGeneration" in js
    assert "method: \"DELETE\"" in js
    assert "loadHistory()" in js


def test_frontend_playback_updates_progress():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "async function saveProgress" in js
    assert "saveProgress(segmentIndex)" in js
    assert "completed: true" in js


def test_frontend_event_source_handles_errors():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "state.eventSource.onerror" in js
    assert "state.eventSource.close()" in js


def test_frontend_fetch_paths_have_error_handling():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert js.count("try {") >= 3
    assert "catch" in js
    assert "resetPlaybackState(" in js


def test_frontend_generation_submit_uses_failed_response_detail():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    submit = js.split("async function submitGeneration(event)", 1)[1].split("async function loadHistory()", 1)[0]

    assert "await response.json()" in submit
    assert "error.detail" in submit
    assert "Generation failed to start" in submit


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
