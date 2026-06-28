from __future__ import annotations

import re
import tomllib
from pathlib import Path


STATIC_DIR = Path("src/tts_app/static")
SRC_DIR = Path("src/tts_app")
PYPROJECT = Path("pyproject.toml")
JS_FILES = (
    "app.js",
    "ocr.js",
    "playback.js",
    "telemetry.js",
    "voice-controls.js",
    "state.js",
    "dom.js",
    "utils.js",
)


def frontend_js() -> str:
    return "\n".join((STATIC_DIR / filename).read_text(encoding="utf-8") for filename in JS_FILES)


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
    assert 'href="/static/styles.css?v=' in html
    assert 'src="/static/app.js?v=' in html
    assert '<script type="module" src="/static/app.js?v=' in html


def test_frontend_versions_split_javascript_module_imports():
    local_import = re.compile(r'from "(\./[^"?]+\.js)(\?v=[^"]+)?"')
    for filename in JS_FILES:
        js = (STATIC_DIR / filename).read_text(encoding="utf-8")
        for match in local_import.finditer(js):
            assert match.group(2), f"{filename} imports {match.group(1)} without a cache-busting version"


def test_frontend_imports_playback_helpers():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    playback_js = (STATIC_DIR / "playback.js").read_text(encoding="utf-8")

    assert 'from "./playback.js?v=' in app_js
    assert "chooseResumeSegmentIndex" in app_js
    assert "buildProgressPayload" in app_js
    assert "endedPlaybackAction" in app_js
    assert "export function chooseResumeSegmentIndex" in playback_js
    assert "export function buildProgressPayload" in playback_js
    assert "export function endedPlaybackAction" in playback_js


def test_frontend_imports_playback_telemetry_module():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    telemetry_js = (STATIC_DIR / "telemetry.js").read_text(encoding="utf-8")

    assert 'from "./telemetry.js?v=' in app_js
    assert "createPlaybackTelemetry" in app_js
    assert "playbackTelemetry.record" in app_js
    assert "playbackTelemetry.flush" in app_js
    assert "export function createPlaybackTelemetry" in telemetry_js


def test_frontend_imports_voice_controls_module():
    app_js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    voice_controls_js = (STATIC_DIR / "voice-controls.js").read_text(encoding="utf-8")

    assert 'from "./voice-controls.js?v=' in app_js
    assert "renderVoiceControls" in app_js
    assert "voiceGenerationPayload" in app_js
    assert "export function renderVoiceControls" in voice_controls_js
    assert "export function voiceGenerationPayload" in voice_controls_js


def test_frontend_voice_sample_path_does_not_record_playback_telemetry():
    js = frontend_js()
    sampler = js.split("export async function playVoiceSample()", 1)[1].split(
        "export function setVoiceControlsHidden", 1
    )[0]

    assert "playbackTelemetry.record" not in sampler
    assert "state.samplePlayback = true" in sampler


def test_frontend_static_asset_version_bumped_for_playback_progress():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    sources = [html, *((STATIC_DIR / filename).read_text(encoding="utf-8") for filename in JS_FILES)]

    assert 'href="/static/styles.css?v=playback-progress-1"' in html
    assert 'src="/static/app.js?v=playback-progress-1"' in html
    assert "playback-progress-1" in (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "playback-progress-1" in (STATIC_DIR / "ocr.js").read_text(encoding="utf-8")
    assert "playback-progress-1" in (STATIC_DIR / "voice-controls.js").read_text(encoding="utf-8")
    for source in sources:
        assert "continuous-playback-1" not in source
        assert "playback-vitest-1" not in source
        assert "playback-telemetry-1" not in source


def test_frontend_voice_controls_are_collapsed_by_default():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    js = frontend_js()

    assert 'id="voice-panel"' in html
    assert 'id="voice-summary"' in html
    assert 'id="voice-summary-text"' in html
    assert 'id="voice-summary-speed"' in html
    assert 'id="voice-edit"' in html
    assert 'id="voice-expanded" class="voice-expanded hidden"' in html
    assert 'id="voice-done"' in html
    assert ".voice-panel-expanded .voice-summary" in css
    assert ".voice-panel-expanded .voice-expanded" in css
    assert "voiceEditButton?.addEventListener" in js
    assert "voiceDoneButton?.addEventListener" in js


def test_frontend_javascript_uses_history_and_event_endpoints():
    js = frontend_js()

    assert "/api/generations/text" in js
    assert "/api/generations/url" in js
    assert "/api/options" in js
    assert "/progress" in js
    assert "voiceGenerationPayload()" in js
    assert "voice:" in js
    assert "speed:" in js
    assert "language:" in js
    assert "EventSource" in js
    assert "scrollIntoView" in js


def test_frontend_javascript_uses_language_scoped_voice_preferences():
    js = frontend_js()

    assert "/preference" in js
    assert "JSON.stringify({ preferred, language" in js
    assert "option.language === voice.language" in js
    assert 'languageSelect?.addEventListener("change", handleLanguageChange)' in js


def test_frontend_has_image_input_controls():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="image-mode"' in html
    assert 'id="image-upload-input"' in html
    assert 'id="upload-image-files"' in html
    assert 'id="clear-ocr-draft"' in html
    assert 'id="image-selection-list"' in html
    assert 'id="ocr-upload-progress"' in html
    assert 'id="ocr-upload-bar"' in html
    assert 'id="cancel-ocr-upload"' in html
    assert 'accept="image/*"' in html
    assert "multiple" in html
    assert 'id="ocr-review-list"' in html
    assert 'id="image-camera-input"' not in html
    assert 'id="take-image-photo"' not in html
    assert 'id="clear-image-selection"' not in html
    assert ">Clear</button>" not in html
    assert 'capture="environment"' not in html


def test_frontend_has_draft_images_mode_and_preview_overlay():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="draft-images-mode"' in html
    assert 'id="ocr-drafts-list" class="history-list hidden"' in html
    assert 'id="image-preview-overlay"' in html
    assert 'id="image-preview-close"' in html
    assert 'id="image-preview-image"' in html


def test_frontend_styles_action_button_feedback_states():
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert "button:active" in css
    assert ".is-busy" in css
    assert ".is-busy::after" in css
    assert "aria-busy" in css
    assert "currentcolor" in css
    assert "currentColor" not in css


def test_frontend_hidden_class_overrides_display_utility_classes():
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".hidden { display: none !important; }" in css


def test_frontend_styles_ocr_upload_progress_panel():
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")

    assert ".upload-progress" in css
    assert ".upload-status" in css
    assert ".upload-progress progress" in css


def test_frontend_does_not_seed_hard_coded_voice_options():
    js = (STATIC_DIR / "state.js").read_text(encoding="utf-8")
    initial_state = js.split("};", 1)[0]

    assert "voices: []" in initial_state
    assert "Cherry" not in initial_state


def test_frontend_javascript_uses_ocr_draft_endpoints():
    js = frontend_js()

    assert "/api/ocr-drafts" in js
    assert "/images/" in js
    assert "FormData" in js
    assert "ocr-review-list" in js
    assert "/generation" in js
    assert "state.pendingOcrImages" in js
    assert "forEach((image)" in js


def test_frontend_queues_uploaded_images_before_ocr():
    js = frontend_js()

    assert "pendingOcrImages: []" in js
    assert 'document.querySelector("#image-upload-input")' in js
    assert 'document.querySelector("#upload-image-files")' in js
    assert "appendPendingOcrImages(Array.from(imageUploadInput.files || []))" in js
    assert "renderPendingOcrImages()" in js
    assert "clearPendingOcrImages" in js
    assert "imageCameraInput" not in js
    assert "takeImagePhotoButton" not in js
    assert "clearImageSelectionButton" not in js
    assert 'document.querySelector("#clear-image-selection")' not in js


def test_frontend_appends_uploaded_images_to_active_unlinked_draft():
    js = frontend_js()
    extractor = js.split("async function extractImageText", 1)[1].split("async function openOcrDraft", 1)[0]
    uploader = js.split("function uploadOcrDraft", 1)[1].split("function resizedImageFilename", 1)[0]

    assert "uploadOcrDraft(formData, appendDraftId)" in extractor
    assert "state.currentOcrDraftId" in extractor
    assert "!state.currentOcrDraft?.linked_generation_id" in extractor
    assert 'formData.append("combined_text", reviewedOcrText())' in extractor
    assert "draftId ? `/api/ocr-drafts/${draftId}/images` : \"/api/ocr-drafts\"" in uploader
    assert "xhr.open(\"POST\", endpoint)" in uploader


def test_frontend_exposes_warning_clear_images_for_active_ocr_draft():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    js = frontend_js()
    mode_switch = js.split("function setInputMode", 1)[1].split("function escapeHtml", 1)[0]

    assert '<button id="clear-ocr-draft" class="warning-action hidden" type="button">Clear images</button>' in html
    assert ".warning-action" in css
    assert "clearOcrDraftButton.classList.toggle(\"hidden\", !isImage || !state.currentOcrDraftId || Boolean(state.currentOcrDraft?.linked_generation_id))" in mode_switch
    assert "clearOcrDraftButton.addEventListener(\"click\", clearActiveOcrDraft)" in js
    assert "function clearActiveOcrDraft" in js


def test_frontend_resizes_large_ocr_images_before_upload():
    js = frontend_js()
    extractor = js.split("async function extractImageText", 1)[1].split("async function openOcrDraft", 1)[0]

    assert "prepareOcrImagesForUpload" in extractor
    assert "state.pendingOcrImages" in extractor
    assert "const OCR_IMAGE_MAX_EDGE = 2048" in js
    assert "const OCR_IMAGE_JPEG_QUALITY = 0.85" in js
    assert "canvas.toBlob" in js
    assert "image/jpeg" in js
    assert "Preparing" in js


def test_frontend_refreshes_ocr_drafts_after_upload_error():
    js = frontend_js()
    extractor = js.split("async function extractImageText", 1)[1].split("async function openOcrDraft", 1)[0]

    assert "await loadOcrDrafts()" in extractor


def test_frontend_uses_xhr_for_ocr_upload_progress_and_cancel():
    js = frontend_js()
    uploader = js.split("function uploadOcrDraft", 1)[1].split("async function openOcrDraft", 1)[0]

    assert "new XMLHttpRequest()" in uploader
    assert "xhr.upload.onprogress" in uploader
    assert "xhr.abort()" in js
    assert "showOcrExtractingProgress()" in uploader
    assert "Extracting text..." in js
    assert "cancelOcrUploadButton.addEventListener(\"click\", cancelOcrUpload)" in js


def test_frontend_disables_image_controls_during_ocr_upload():
    js = frontend_js()
    controls = js.split("function setOcrUploadActive", 1)[1].split("function uploadOcrDraft", 1)[0]

    assert "imageUploadInput.disabled = active" in controls
    assert "uploadImageFilesButton.disabled = active" in controls
    assert "clearOcrDraftButton.disabled = active" in controls
    assert "languageSelect.disabled = active" in controls
    assert "imageCameraInput" not in controls
    assert "takeImagePhotoButton" not in controls
    assert "clearImageSelectionButton" not in controls


def test_frontend_renders_one_combined_ocr_textarea_and_active_thumbnails():
    js = frontend_js()
    renderer = js.split("function renderOcrReview()", 1)[1].split("async function loadOcrDrafts()", 1)[0]

    assert "ocr-combined-text" in renderer
    assert "draft.combined_text" in renderer
    assert "ocr-thumbnail" in renderer
    assert "data-image-id" in renderer
    assert "data-action=\"delete-image\"" in renderer
    assert "data-action=\"retry-image\"" in renderer
    assert "Retry OCR" in renderer
    assert "ocr-image-text" not in renderer
    assert "No images stored for this draft" in renderer


def test_frontend_reports_successful_ocr_deletes_without_reading_204_body():
    js = frontend_js()
    draft_deleter = js.split("async function deleteOcrDraft", 1)[1].split("async function generateOcrAudio", 1)[0]
    image_deleter = js.split("async function deleteOcrDraftImage", 1)[1].split("async function openGeneration", 1)[0]

    assert "await response.json()" not in draft_deleter
    assert "await response.json()" not in image_deleter
    assert "Deleted image draft" in draft_deleter
    assert "Removed image" in image_deleter


def test_frontend_clears_active_ocr_draft_after_generation_success():
    js = frontend_js()
    generator = js.split("async function generateOcrAudio", 1)[1].split("async function retryOcrDraftImage", 1)[0]

    assert "method: \"PUT\"" not in generator
    assert "combined_text: combinedText" in generator
    assert "clearActiveOcrDraftState()" in generator
    assert generator.index("clearActiveOcrDraftState()") < generator.index("await openGeneration(result.generation_id")
    assert generator.rindex("updateGenerateOcrAudioState()") > generator.rindex("await withButtonBusy")
    assert "function clearActiveOcrDraftState()" in js
    reset_helper = js.split("function clearActiveOcrDraftState()", 1)[1].split("function renderOcrReview", 1)[0]
    assert "state.currentOcrDraftId = null" in reset_helper
    assert "state.currentOcrDraft = null" in reset_helper
    assert "ocrReviewList.innerHTML = \"\"" in reset_helper
    assert "generateOcrAudioButton.classList.add(\"hidden\")" in reset_helper
    assert "generateOcrAudioButton.disabled = true" in reset_helper
    assert "clearOcrDraftButton.classList.add(\"hidden\")" in reset_helper


def test_frontend_image_mode_clears_linked_current_ocr_draft():
    js = frontend_js()
    mode_sync = js.split("export function syncOcrInputMode(mode)", 1)[1].split("function showOcrDraft", 1)[0]

    assert "mode === \"image\"" in mode_sync
    assert "state.currentOcrDraft?.linked_generation_id" in mode_sync
    assert "clearActiveOcrDraftState()" in mode_sync


def test_frontend_shows_busy_feedback_while_generating_ocr_audio():
    js = frontend_js()
    ocr_js = (STATIC_DIR / "ocr.js").read_text(encoding="utf-8")
    ocr_imports = ocr_js.split('} from "./dom.js', 1)[0]
    generator = js.split("async function generateOcrAudio", 1)[1].split("async function deleteOcrDraftImage", 1)[0]

    assert "async function generateOcrAudio(button = null)" in js
    assert "withButtonBusy(button, \"Generating...\"" in generator
    assert "generateOcrAudioButton.addEventListener(\"click\", () => generateOcrAudio(generateOcrAudioButton))" in js
    assert "voiceSelect" not in ocr_imports
    assert "speedSelect" not in ocr_imports
    assert "voiceGenerationPayload()" in generator


def test_frontend_draft_images_mode_owns_unlinked_draft_list():
    js = frontend_js()
    renderer = js.split("function renderOcrDrafts()", 1)[1].split("function pendingImageLabel", 1)[0]
    image_mode = js.split("function setInputMode", 1)[1].split("function escapeHtml", 1)[0]

    assert "unlinkedDrafts" in renderer
    assert "draft.linked_generation_id" in renderer
    assert "No image drafts" in renderer
    assert "state.inputMode !== \"draft-images\"" in renderer
    assert "draft.combined_text" in renderer
    assert "draft-thumbnail-strip" in renderer
    assert "data-action=\"preview-image\"" in renderer
    assert "Continue" in renderer
    assert "ocrDraftsList.classList.toggle(\"hidden\", !isDraftImages)" in image_mode
    assert "setInputMode(state.inputMode)" in js
    assert "state.inputMode === \"image\" || state.inputMode === \"draft-images\"" in js


def test_frontend_wraps_async_button_actions_with_busy_state():
    js = frontend_js()

    assert "async function withButtonBusy" in js
    assert "button.classList.add(\"is-busy\")" in js
    assert "button.setAttribute(\"aria-busy\", \"true\")" in js
    assert "button.disabled = true" in js
    assert "button.classList.remove(\"is-busy\")" in js
    assert "button.removeAttribute(\"aria-busy\")" in js


def test_frontend_history_and_ocr_actions_pass_buttons_for_feedback():
    js = frontend_js()

    assert "extractImageTextButton.addEventListener(\"click\", () => extractImageText(extractImageTextButton))" in js
    assert "async function extractImageText(button = null)" in js
    assert "withButtonBusy(button, \"Extracting...\"" in js
    assert "openGeneration(Number(action.dataset.generationId)" in js
    assert "button: action" in js
    assert "deleteGeneration(Number(action.dataset.generationId), action)" in js
    assert "openOcrDraft(Number(action.dataset.draftId), action)" in js
    assert "deleteOcrDraft(Number(action.dataset.draftId), action)" in js
    assert "deleteOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action)" in js
    assert "retryOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action)" in js
    assert "withButtonBusy(button, \"Retrying...\"" in js
    assert "/retry" in js


def test_frontend_image_preview_opens_from_thumbnails_and_closes():
    js = frontend_js()

    assert "function openImagePreview" in js
    assert "function closeImagePreview" in js
    assert "imagePreviewOverlay.addEventListener(\"click\"" in js
    assert "imagePreviewClose.addEventListener(\"click\", closeImagePreview)" in js
    assert "event.key === \"Escape\"" in js
    assert "data-action=\"preview-image\"" in js


def test_frontend_voice_sample_marks_sample_playback_state():
    js = frontend_js()
    sampler = js.split("export async function playVoiceSample()", 1)[1].split(
        "export function setVoiceControlsHidden", 1
    )[0]

    assert 'document.querySelector("#voice-sample")' in js
    assert "state.samplePlayback = true" in sampler
    assert "state.sampleObjectUrl = URL.createObjectURL(blob)" in sampler
    assert "audioPlayer.src = state.sampleObjectUrl" in sampler


def test_frontend_voice_sample_revokes_object_urls():
    js = frontend_js()

    assert "URL.revokeObjectURL" in js
    assert "function clearSamplePlayback" in js or "export function clearSamplePlayback" in js
    assert "clearSamplePlayback()" in js.split("function stopPlayback", 1)[1].split(
        "function handleEventSourceError", 1
    )[0]


def test_frontend_ended_handler_skips_generation_progress_for_samples():
    js = frontend_js()
    handler = js.split('audioPlayer.addEventListener("ended"', 1)[1].split("document.addEventListener", 1)[0]
    sample_branch = handler.split('if (action.type === "complete")', 1)[0]

    assert "endedPlaybackAction({" in handler
    assert "samplePlayback: state.samplePlayback" in handler
    assert 'action.type === "clear-sample"' in sample_branch
    assert "clearSamplePlayback()" in sample_branch
    assert "return" in sample_branch
    assert "saveProgress" not in sample_branch


def test_frontend_javascript_ended_handler_respects_continuous_playback():
    js = frontend_js()
    handler = js.split('audioPlayer.addEventListener("ended"', 1)[1].split("loadHistory();", 1)[0]

    assert "continuousPlayback: state.continuousPlayback" in handler
    assert "generationStatus: state.currentDetail?.generation.status" in handler
    assert 'action.type === "play-next"' not in handler
    assert "playSegment(action.segmentIndex)" not in handler


def test_frontend_generated_playback_uses_continuous_audio_endpoint():
    js = frontend_js()
    play_segment = js.split("function playSegment(segmentIndex)", 1)[1].split("function saveProgress", 1)[0]

    assert "continuousAudioUrl" in js
    assert "estimateContinuousSegmentIndex" in js
    assert "audioPlayer.src = continuousAudioUrl(state.currentGenerationId, segmentIndex)" in play_segment
    assert "audioPlayer.src = `/api/audio/" not in play_segment


def test_continuous_audio_route_lives_outside_app_factory():
    api_py = (SRC_DIR / "api.py").read_text(encoding="utf-8")
    playback_py = (SRC_DIR / "routes" / "playback.py").read_text(encoding="utf-8")

    assert "create_playback_router" in api_py
    assert "continuous-audio" not in api_py
    assert "continuous-audio" in playback_py


def test_continuous_audio_route_offloads_blocking_stream_work():
    playback_py = (SRC_DIR / "routes" / "playback.py").read_text(encoding="utf-8")

    assert "anyio.to_thread.run_sync" in playback_py


def test_frontend_user_started_history_playback_continues_between_segments():
    js = frontend_js()
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
    js = frontend_js()

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
    js = frontend_js()
    handler = js.split('historyList.addEventListener("click"', 1)[1].split('readingPane.addEventListener("click"', 1)[0]

    assert 'historyItem = event.target.closest("[data-generation-id]")' in handler
    assert 'action?.dataset.action === "open"' in handler
    assert "openGeneration(generationId, { subscribe: false, autoplay: true })" in handler


def test_frontend_history_autoplay_resumes_saved_segment():
    js = frontend_js()
    opener = js.split("async function openGeneration(generationId", 1)[1].split(
        "async function loadGenerationDetail", 1
    )[0]

    assert "playSegment(state.currentSegmentIndex)" in opener
    assert "playSegment(0)" not in opener


def test_frontend_navigation_stops_playback_and_clears_audio_buffer():
    js = frontend_js()
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
    js = frontend_js()
    renderer = js.split("function renderHistory()", 1)[1].split("async function openGeneration", 1)[0]

    assert "item.url" in renderer
    assert "<details" in renderer
    assert "Voice" in renderer
    assert "Speed" in renderer
    assert "Progress" in renderer
    assert "data-action=\"delete\"" in renderer


def test_frontend_history_delete_calls_delete_endpoint():
    js = frontend_js()

    assert "async function deleteGeneration" in js
    assert "method: \"DELETE\"" in js
    assert "loadHistory()" in js


def test_frontend_playback_updates_progress():
    js = frontend_js()
    updater = js.split("function updateContinuousPlaybackSegment()", 1)[1].split(
        "function updateActiveSegment", 1
    )[0]

    assert "function saveProgress" in js
    assert "createQueuedProgressSaver" in js
    assert "const enqueueProgressSave = createQueuedProgressSaver(persistProgress)" in js
    assert "generationId: state.currentGenerationId" in js
    assert "detailGenerationId: state.currentDetail?.generation?.id ?? null" in js
    assert "async function persistProgress" in js
    assert "saveProgress(segmentIndex)" in js
    assert 'audioPlayer.addEventListener("timeupdate", updateContinuousPlaybackSegment)' in js
    assert "estimateContinuousSegmentIndex({" in updater
    assert "state.continuousPlaybackStartSegmentIndex ?? state.currentSegmentIndex" in updater
    assert "saveProgress(nextSegmentIndex)" in updater
    assert "completed: true" in js


def test_frontend_event_source_handles_errors():
    js = frontend_js()

    assert "state.eventSource.onerror" in js
    assert "state.eventSource.close()" in js


def test_frontend_fetch_paths_have_error_handling():
    js = frontend_js()

    assert js.count("try {") >= 3
    assert "catch" in js
    assert "resetPlaybackState(" in js


def test_frontend_generation_submit_uses_failed_response_detail():
    js = frontend_js()
    submit = js.split("async function submitGeneration(event)", 1)[1].split("async function loadHistory()", 1)[0]

    assert "await response.json()" in submit
    assert "error.detail" in submit
    assert "Generation failed to start" in submit


def test_frontend_generation_detail_loads_ignore_stale_results():
    js = frontend_js()
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
