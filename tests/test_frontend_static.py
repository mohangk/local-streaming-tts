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
    assert 'id="language-select"' in html
    assert 'id="voice-select"' in html
    assert 'id="voice-star"' in html
    assert 'id="voice-sample"' in html
    assert 'id="speed-select"' in html


def test_frontend_javascript_uses_history_and_event_endpoints():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/api/generations/text" in js
    assert "/api/generations/url" in js
    assert "/api/options" in js
    assert "/progress" in js
    assert "payload.voice" in js
    assert "payload.speed" in js
    assert "payload.language" in js
    assert "EventSource" in js
    assert "scrollIntoView" in js


def test_frontend_javascript_uses_language_scoped_voice_preferences():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/preference" in js
    assert "JSON.stringify({ preferred, language" in js
    assert "option.language === voice.language" in js
    assert "languageSelect.addEventListener(\"change\", renderOptions)" in js


def test_frontend_has_image_input_controls():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="image-mode"' in html
    assert 'id="image-input"' in html
    assert 'accept="image/*"' in html
    assert "multiple" in html
    assert 'id="ocr-review-list"' in html
    assert 'id="ocr-drafts-list"' in html


def test_frontend_does_not_seed_hard_coded_voice_options():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    initial_state = js.split("};", 1)[0]

    assert "voices: []" in initial_state
    assert "Cherry" not in initial_state


def test_frontend_javascript_uses_ocr_draft_endpoints():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/api/ocr-drafts" in js
    assert "/images/" in js
    assert "FormData" in js
    assert "ocr-review-list" in js
    assert "/generation" in js
    assert "imageInput.files" in js
    assert "forEach((image)" in js


def test_frontend_refreshes_ocr_drafts_after_upload_error():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    extractor = js.split("async function extractImageText()", 1)[1].split("async function openOcrDraft", 1)[0]
    error_branch = extractor.split("if (!response.ok)", 1)[1].split("return;", 1)[0]

    assert "await loadOcrDrafts()" in error_branch


def test_frontend_renders_thumbnails_and_per_image_review_controls():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    renderer = js.split("function renderOcrReview()", 1)[1].split("async function loadOcrDrafts()", 1)[0]

    assert "ocr-thumbnail" in renderer
    assert "data-image-id" in renderer
    assert "data-action=\"delete-image\"" in renderer
    assert "ocr-image-text" in renderer
    assert "No images stored for this draft" in renderer


def test_frontend_reports_successful_ocr_deletes_without_reading_204_body():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    draft_deleter = js.split("async function deleteOcrDraft", 1)[1].split("async function generateOcrAudio", 1)[0]
    image_deleter = js.split("async function deleteOcrDraftImage", 1)[1].split("async function openGeneration", 1)[0]

    assert "await response.json()" not in draft_deleter
    assert "await response.json()" not in image_deleter
    assert "Deleted image draft" in draft_deleter
    assert "Removed image" in image_deleter


def test_frontend_voice_sample_marks_sample_playback_state():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    sampler = js.split("async function playVoiceSample()", 1)[1].split("async function loadHistory()", 1)[0]

    assert 'document.querySelector("#voice-sample")' in js
    assert "state.samplePlayback = true" in sampler
    assert "state.sampleObjectUrl = URL.createObjectURL(blob)" in sampler
    assert "audioPlayer.src = state.sampleObjectUrl" in sampler


def test_frontend_voice_sample_revokes_object_urls():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "URL.revokeObjectURL" in js
    assert "function clearSamplePlayback" in js
    assert "clearSamplePlayback()" in js.split("function stopPlayback", 1)[1].split(
        "function handleEventSourceError", 1
    )[0]


def test_frontend_ended_handler_skips_generation_progress_for_samples():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    handler = js.split('audioPlayer.addEventListener("ended"', 1)[1].split("document.addEventListener", 1)[0]
    sample_branch = handler.split("const nextIndex", 1)[0]

    assert "state.samplePlayback" in sample_branch
    assert "clearSamplePlayback()" in sample_branch
    assert "return" in sample_branch
    assert "saveProgress" not in sample_branch


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


def test_frontend_history_open_loads_and_autoplays_generation():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    handler = js.split('historyList.addEventListener("click"', 1)[1].split('readingPane.addEventListener("click"', 1)[0]

    assert 'historyItem = event.target.closest("[data-generation-id]")' in handler
    assert 'action?.dataset.action === "open"' in handler
    assert "openGeneration(generationId, { subscribe: false, autoplay: true })" in handler


def test_frontend_history_autoplay_resumes_saved_segment():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    opener = js.split("async function openGeneration(generationId", 1)[1].split(
        "async function loadGenerationDetail", 1
    )[0]

    assert "playSegment(state.currentSegmentIndex)" in opener
    assert "playSegment(0)" not in opener


def test_frontend_navigation_stops_playback_and_clears_audio_buffer():
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "function stopPlayback" in js
    stopper = js.split("function stopPlayback", 1)[1].split("function handleEventSourceError", 1)[0]
    nav_handler = js.split("navButtons.forEach", 1)[1].split("textModeButton.addEventListener", 1)[0]
    back_handler = js.split('backToHistory.addEventListener("click"', 1)[1].split(
        'historyList.addEventListener("click"', 1
    )[0]

    assert "audioPlayer.pause()" in stopper
    assert 'audioPlayer.removeAttribute("src")' in stopper
    assert "audioPlayer.load()" in stopper
    assert "state.continuousPlayback = false" in stopper
    assert "stopPlayback()" in nav_handler
    assert "stopPlayback()" in back_handler


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
