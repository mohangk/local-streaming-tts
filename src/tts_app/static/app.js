import {
  audioPlayer,
  autoplayInput,
  autoplayRow,
  backToHistory,
  draftImagesModeButton,
  generateForm,
  generateSubmitButton,
  historyList,
  historySearch,
  imageModeButton,
  navButtons,
  playPauseButton,
  playerStatus,
  readingPane,
  scrollFollow,
  textInput,
  textLabel,
  textModeButton,
  urlInput,
  urlLabel,
  urlModeButton,
  views,
} from "./dom.js?v=playback-progress-1";
import { initOcr, registerOcrEvents, syncOcrInputMode } from "./ocr.js?v=playback-progress-1";
import {
  buildProgressPayload,
  chooseResumeSegmentIndex,
  continuousAudioUrl,
  createQueuedProgressSaver,
  endedPlaybackAction,
  estimateContinuousSegmentIndex,
} from "./playback.js?v=playback-progress-1";
import { state } from "./state.js?v=playback-progress-1";
import { createPlaybackTelemetry } from "./telemetry.js?v=playback-progress-1";
import { escapeHtml, formatSpeed, withButtonBusy } from "./utils.js?v=playback-progress-1";
import {
  clearSamplePlayback,
  currentLanguage,
  registerVoiceControlEvents,
  renderVoiceControls,
  setVoiceControlsHidden,
  voiceGenerationPayload,
} from "./voice-controls.js?v=playback-progress-1";

const playbackTelemetry = createPlaybackTelemetry();
const enqueueProgressSave = createQueuedProgressSaver(persistProgress);

function showView(viewId) {
  views.forEach((view) => {
    view.classList.toggle("active-view", view.id === viewId);
  });
  navButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.view === viewId);
  });
  if (viewId === "history-view") {
    loadHistory();
  }
}

function setInputMode(mode) {
  state.inputMode = mode;
  const isText = mode === "text";
  const isUrl = mode === "url";
  const isImage = mode === "image";
  const isDraftImages = mode === "draft-images";
  textModeButton.classList.toggle("active", isText);
  urlModeButton.classList.toggle("active", isUrl);
  imageModeButton.classList.toggle("active", isImage);
  draftImagesModeButton.classList.toggle("active", isDraftImages);
  textInput.classList.toggle("hidden", !isText);
  textLabel.classList.toggle("hidden", !isText);
  urlInput.classList.toggle("hidden", !isUrl);
  urlLabel.classList.toggle("hidden", !isUrl);
  syncOcrInputMode(mode);
  generateSubmitButton?.classList.toggle("hidden", isImage || isDraftImages);
  setVoiceControlsHidden(isDraftImages);
  autoplayRow?.classList.toggle("hidden", isDraftImages);
}

function recordPlaybackTelemetry(eventName, payload = {}) {
  if (playbackTelemetry.record(state, audioPlayer, eventName, payload)) {
    playbackTelemetry.flush();
  }
}

function telemetryPlatform() {
  const platform = (navigator.platform || "").toLowerCase();
  const userAgent = (navigator.userAgent || "").toLowerCase();
  if (userAgent.includes("android")) {
    return "android";
  }
  if (/iphone|ipad|ipod/.test(userAgent)) {
    return "ios";
  }
  if (platform.includes("mac")) {
    return "macos";
  }
  if (platform.includes("win")) {
    return "windows";
  }
  if (platform.includes("linux")) {
    return "linux";
  }
  return "unknown";
}

function telemetryUserAgent() {
  const userAgent = (navigator.userAgent || "").toLowerCase();
  if (userAgent.includes("firefox")) {
    return "firefox";
  }
  if (userAgent.includes("edg/")) {
    return "edge";
  }
  if (userAgent.includes("chrome") || userAgent.includes("crios")) {
    return "chrome";
  }
  if (userAgent.includes("safari")) {
    return "safari";
  }
  return "unknown";
}

async function submitGeneration(event) {
  event.preventDefault();
  if (state.inputMode === "image" || state.inputMode === "draft-images") {
    return;
  }
  const isText = state.inputMode === "text";
  const endpoint = isText ? "/api/generations/text" : "/api/generations/url";
  state.autoplay = autoplayInput.checked;
  const payload = {
    autoplay: state.autoplay,
    ...voiceGenerationPayload(),
  };

  if (isText) {
    payload.text = textInput.value.trim();
    payload.title = "Manual text";
  } else {
    payload.url = urlInput.value.trim();
  }

  if ((isText && !payload.text) || (!isText && !payload.url)) {
    return;
  }

  stopPlayback();
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json();
      playerStatus.textContent = error.detail || "Generation failed to start";
      return;
    }

    const result = await response.json();
    await openGeneration(result.generation_id, { subscribe: true, autoplay: state.autoplay });
  } catch {
    playerStatus.textContent = "Generation failed to start";
  }
}

async function loadOptions() {
  try {
    const response = await fetch("/api/options");
    if (response.ok) {
      state.options = await response.json();
    }
  } catch {
    // Keep built-in fallback options when the app starts before the API responds.
  }
  renderVoiceControls();
}

async function loadHistory() {
  try {
    const response = await fetch("/api/generations");
    if (!response.ok) {
      historyList.innerHTML = '<div class="history-item">Unable to load history</div>';
      return;
    }
    state.generations = await response.json();
    renderHistory();
  } catch {
    historyList.innerHTML = '<div class="history-item">Unable to load history</div>';
  }
}

async function acquireWakeLock() {
  if (!("wakeLock" in navigator) || state.wakeLock) {
    return;
  }
  try {
    state.wakeLock = await navigator.wakeLock.request("screen");
    state.wakeLock.addEventListener("release", () => {
      state.wakeLock = null;
    });
    recordPlaybackTelemetry("wake_lock_acquired");
  } catch {
    state.wakeLock = null;
    recordPlaybackTelemetry("wake_lock_failed");
  }
}

function releaseWakeLock() {
  if (!state.wakeLock) {
    return;
  }
  const lock = state.wakeLock;
  recordPlaybackTelemetry("wake_lock_released");
  state.wakeLock = null;
  lock.release().catch(() => {});
}

function renderHistory() {
  const query = historySearch.value.trim().toLowerCase();
  const rows = state.generations.filter((item) => {
    const text = `${item.title} ${item.text_preview} ${item.url ?? ""} ${item.voice} ${item.settings?.speed ?? ""}`.toLowerCase();
    return text.includes(query);
  });

  if (rows.length === 0) {
    historyList.innerHTML = '<div class="history-item">No generations found</div>';
    return;
  }

  historyList.innerHTML = rows
    .map((item) => {
      const created = item.created_at ? new Date(`${item.created_at}Z`).toLocaleString() : "";
      const speed = item.settings?.speed ?? 1;
      const progress = Number(item.progress_percent || 0);
      const urlMarkup = item.url
        ? `<div class="history-item-url">${escapeHtml(item.url)}</div>`
        : "";
      return `
        <article class="history-item" data-generation-id="${item.id}">
          <div class="history-item-title">${escapeHtml(item.title)}</div>
          <div class="history-item-meta">${escapeHtml(item.status)} ${escapeHtml(created)}</div>
          ${urlMarkup}
          <div class="history-item-preview">${escapeHtml(item.text_preview)}</div>
          <details class="history-details">
            <summary>Details</summary>
            <dl>
              <div><dt>Voice</dt><dd>${escapeHtml(item.voice)}</dd></div>
              <div><dt>Speed</dt><dd>${escapeHtml(formatSpeed(speed))}</dd></div>
              <div><dt>Provider</dt><dd>${escapeHtml(item.provider)}</dd></div>
              <div><dt>Progress</dt><dd>${escapeHtml(progress)}%</dd></div>
            </dl>
          </details>
          <div class="history-actions">
            <button class="secondary-action compact-action" type="button" data-action="open" data-generation-id="${item.id}">Open</button>
            <button class="danger-action compact-action" type="button" data-action="delete" data-generation-id="${item.id}">Delete</button>
          </div>
        </article>
      `;
    })
    .join("");
}

async function deleteGeneration(generationId, button = null) {
  if (!window.confirm("Delete this history entry and cached audio?")) {
    return;
  }
  await withButtonBusy(button, "Deleting...", async () => {
    try {
      const response = await fetch(`/api/generations/${generationId}`, { method: "DELETE" });
      if (!response.ok) {
        playerStatus.textContent = "Unable to delete history entry";
        return;
      }
      if (state.currentGenerationId === generationId) {
        resetPlaybackState("Deleted generation");
      }
      await loadHistory();
    } catch {
      playerStatus.textContent = "Unable to delete history entry";
    }
  });
}

async function openGeneration(generationId, options = {}) {
  const settings = { subscribe: false, autoplay: false, ...options };
  await withButtonBusy(settings.button, "Opening...", async () => {
    stopPlayback();
    state.currentDetail = null;
    state.currentGenerationId = generationId;
    state.currentSegmentIndex = 0;
    state.continuousPlaybackStartSegmentIndex = null;
    state.autoplay = Boolean(settings.autoplay);
    state.continuousPlayback = state.autoplay;
    showView("playback-view");
    if (settings.subscribe) {
      subscribeToGeneration(generationId);
    } else {
      closeEventSource();
    }
    const loaded = await loadGenerationDetail(generationId);
    if (loaded) {
      recordPlaybackTelemetry("generation_opened", {
        platform: telemetryPlatform(),
        user_agent: telemetryUserAgent(),
      });
    }
    if (loaded && state.autoplay) {
      playSegment(state.currentSegmentIndex);
    }
  });
}

async function loadGenerationDetail(generationId) {
  try {
    const response = await fetch(`/api/generations/${generationId}`);
    if (!response.ok) {
      if (state.currentGenerationId === generationId) {
        resetPlaybackState("Unable to load generation");
      }
      return null;
    }
    const detail = await response.json();
    if (state.currentGenerationId !== generationId) {
      return null;
    }
    state.currentDetail = detail;
    state.currentSegmentIndex = chooseResumeSegmentIndex({
      lastSegmentIndex: detail.generation.last_segment_index,
      totalSegments: detail.text_segments.length,
    });
    renderPlayback();
    return state.currentGenerationId === generationId;
  } catch {
    if (state.currentGenerationId === generationId) {
      resetPlaybackState("Unable to load generation");
    }
    return null;
  }
}

function closeEventSource() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
}

function resetPlaybackState(message) {
  closeEventSource();
  stopPlayback();
  state.currentGenerationId = null;
  state.currentDetail = null;
  state.currentSegmentIndex = 0;
  state.continuousPlaybackStartSegmentIndex = null;
  readingPane.innerHTML = "";
  playerStatus.textContent = message;
}

function stopPlayback() {
  state.autoplay = false;
  state.continuousPlayback = false;
  state.continuousPlaybackStartSegmentIndex = null;
  audioPlayer.pause();
  audioPlayer.removeAttribute("src");
  audioPlayer.load();
  clearSamplePlayback();
  releaseWakeLock();
  playPauseButton.textContent = "Play";
}

function handleEventSourceError() {
  recordPlaybackTelemetry("event_source_error");
  playerStatus.textContent = "Live updates disconnected";
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
}

function handleEventMessage(message, generationId) {
  let event;
  try {
    event = JSON.parse(message.data);
  } catch {
    playerStatus.textContent = "Unable to read live update";
    return;
  }

  if (event.type === "segment_completed" || event.type === "generation_completed") {
    loadGenerationDetail(generationId).then((loaded) => {
      if (
        loaded &&
        state.currentGenerationId === generationId &&
        state.autoplay &&
        audioPlayer.paused &&
        event.type === "segment_completed" &&
        event.segment_index === state.currentSegmentIndex
      ) {
        playSegment(event.segment_index);
      }
    });
  }
  if (event.type === "generation_failed") {
    playerStatus.textContent = event.error || "Generation failed";
  }
}

function subscribeToGeneration(generationId) {
  closeEventSource();

  try {
    state.eventSource = new EventSource(`/api/generations/${generationId}/events`);
  } catch {
    playerStatus.textContent = "Live updates unavailable";
    return;
  }

  state.eventSource.onmessage = (message) => {
    handleEventMessage(message, generationId);
  };
  state.eventSource.onerror = () => {
    handleEventSourceError();
  };
}

function renderPlayback() {
  const detail = state.currentDetail;
  if (!detail) {
    playerStatus.textContent = "Unable to load generation";
    return;
  }

  document.querySelector("#playback-title").textContent = detail.generation.title;
  const audioByIndex = new Map(detail.audio_segments.map((segment) => [segment.segment_index, segment]));
  readingPane.innerHTML = detail.text_segments
    .map((segment) => {
      const audio = audioByIndex.get(segment.segment_index);
      const isReady = Boolean(audio);
      const classes = ["text-segment"];
      if (!isReady) {
        classes.push("pending");
      }
      if (segment.segment_index === state.currentSegmentIndex) {
        classes.push("active-segment");
      }
      return `
        <section class="${classes.join(" ")}" data-segment-index="${segment.segment_index}" data-audio-id="${audio ? audio.id : ""}">
          ${escapeHtml(segment.text)}
        </section>
      `;
    })
    .join("");

  updatePlayerStatus();
  scrollActiveSegmentIntoView();
}

function audioSegmentForIndex(segmentIndex) {
  if (!state.currentDetail) {
    return null;
  }
  return state.currentDetail.audio_segments.find((segment) => segment.segment_index === segmentIndex) || null;
}

function playSegment(segmentIndex) {
  const audio = audioSegmentForIndex(segmentIndex);
  state.currentSegmentIndex = segmentIndex;
  state.continuousPlaybackStartSegmentIndex = segmentIndex;
  updateActiveSegment();
  updatePlayerStatus();
  recordPlaybackTelemetry("segment_play_attempted");

  if (!audio || !state.currentGenerationId) {
    return;
  }

  audioPlayer.src = continuousAudioUrl(state.currentGenerationId, segmentIndex);
  recordPlaybackTelemetry("continuous_audio_selected");
  saveProgress(segmentIndex);
  audioPlayer.play().catch(() => {
    playerStatus.textContent = "Tap Play to start audio";
  });
}

function saveProgress(segmentIndex, options = {}) {
  return enqueueProgressSave({
    generationId: state.currentGenerationId,
    detailGenerationId: state.currentDetail?.generation?.id ?? null,
    segmentIndex,
    options,
  });
}

async function persistProgress({ generationId, detailGenerationId, segmentIndex, options = {} }) {
  if (!generationId) {
    return;
  }
  const payload = buildProgressPayload(segmentIndex, options);
  try {
    recordPlaybackTelemetry("progress_save_attempted", payload);
    const response = await fetch(`/api/generations/${generationId}/progress`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (
      response.ok &&
      state.currentGenerationId === generationId &&
      detailGenerationId === generationId &&
      state.currentDetail?.generation?.id === detailGenerationId
    ) {
      const progress = await response.json();
      state.currentDetail.generation.last_segment_index = progress.last_segment_index;
      state.currentDetail.generation.progress_percent = progress.progress_percent;
      recordPlaybackTelemetry("progress_save_succeeded", {
        last_segment_index: progress.last_segment_index,
        progress_percent: progress.progress_percent,
      });
    }
  } catch {
    recordPlaybackTelemetry("progress_save_failed");
    // Playback should continue even if progress cannot be saved.
  }
}

function updateContinuousPlaybackSegment() {
  if (state.samplePlayback || !state.continuousPlayback || !state.currentDetail) {
    return;
  }

  const nextSegmentIndex = estimateContinuousSegmentIndex({
    currentTime: audioPlayer.currentTime,
    duration: audioPlayer.duration,
    startSegmentIndex: state.continuousPlaybackStartSegmentIndex ?? state.currentSegmentIndex,
    totalSegments: state.currentDetail.text_segments.length,
    audioSegments: state.currentDetail.audio_segments,
  });

  if (nextSegmentIndex === state.currentSegmentIndex) {
    return;
  }

  state.currentSegmentIndex = nextSegmentIndex;
  updateActiveSegment();
  updatePlayerStatus();
  saveProgress(nextSegmentIndex);
}

function updateActiveSegment() {
  document.querySelectorAll(".text-segment").forEach((segment) => {
    segment.classList.toggle("active-segment", Number(segment.dataset.segmentIndex) === state.currentSegmentIndex);
  });
  scrollActiveSegmentIntoView();
}

function scrollActiveSegmentIntoView() {
  if (!scrollFollow.checked) {
    return;
  }
  document.querySelector(".active-segment")?.scrollIntoView({ block: "center", behavior: "smooth" });
}

function updatePlayerStatus() {
  if (!state.currentDetail) {
    playerStatus.textContent = "No segment selected";
    return;
  }
  const total = state.currentDetail.text_segments.length;
  const audio = audioSegmentForIndex(state.currentSegmentIndex);
  playerStatus.textContent = audio
    ? `Segment ${state.currentSegmentIndex + 1} of ${total}`
    : `Segment ${state.currentSegmentIndex + 1} pending`;
}

navButtons.forEach((button) => {
  button.addEventListener("click", () => {
    stopPlayback();
    closeEventSource();
    showView(button.dataset.view);
  });
});

textModeButton.addEventListener("click", () => setInputMode("text"));
urlModeButton.addEventListener("click", () => setInputMode("url"));
imageModeButton.addEventListener("click", () => setInputMode("image"));
draftImagesModeButton.addEventListener("click", () => setInputMode("draft-images"));
generateForm.addEventListener("submit", submitGeneration);
historySearch.addEventListener("input", renderHistory);
backToHistory.addEventListener("click", () => {
  stopPlayback();
  closeEventSource();
  showView("history-view");
});

historyList.addEventListener("click", (event) => {
  const action = event.target.closest("[data-action]");
  const historyItem = event.target.closest("[data-generation-id]");
  if (!historyItem) {
    return;
  }
  const generationId = Number(historyItem.dataset.generationId);
  if (action?.dataset.action === "delete") {
    deleteGeneration(Number(action.dataset.generationId), action);
    return;
  }
  if (action?.dataset.action === "open") {
    openGeneration(Number(action.dataset.generationId), { subscribe: false, autoplay: true, button: action });
    return;
  }
  if (!action) {
    if (event.target.closest(".history-details") && !action) {
      return;
    }
    openGeneration(generationId, { subscribe: false, autoplay: true });
  }
});

readingPane.addEventListener("click", (event) => {
  const segment = event.target.closest("[data-segment-index]");
  if (segment) {
    state.continuousPlayback = true;
    playSegment(Number(segment.dataset.segmentIndex));
  }
});

playPauseButton.addEventListener("click", () => {
  if (audioPlayer.paused) {
    state.continuousPlayback = true;
    const audio = audioSegmentForIndex(state.currentSegmentIndex);
    if (audioPlayer.src && audio) {
      audioPlayer.play().catch(() => {
        playerStatus.textContent = "Tap Play to start audio";
      });
    } else {
      playSegment(state.currentSegmentIndex);
    }
    return;
  }
  state.continuousPlayback = false;
  audioPlayer.pause();
});

registerVoiceControlEvents({ stopPlayback });

audioPlayer.addEventListener("play", () => {
  playPauseButton.textContent = "Pause";
  acquireWakeLock();
  recordPlaybackTelemetry("audio_play");
});

audioPlayer.addEventListener("pause", () => {
  playPauseButton.textContent = "Play";
  recordPlaybackTelemetry("audio_pause");
  releaseWakeLock();
});

audioPlayer.addEventListener("timeupdate", updateContinuousPlaybackSegment);

audioPlayer.addEventListener("ended", () => {
  const action = endedPlaybackAction({
    samplePlayback: state.samplePlayback,
    continuousPlayback: state.continuousPlayback,
    generationStatus: state.currentDetail?.generation.status,
    currentSegmentIndex: state.currentSegmentIndex,
    totalSegments: state.currentDetail?.text_segments.length || 0,
  });
  recordPlaybackTelemetry("audio_ended");
  recordPlaybackTelemetry("playback_ended_action", action);

  if (action.type === "clear-sample") {
    audioPlayer.pause();
    audioPlayer.removeAttribute("src");
    audioPlayer.load();
    clearSamplePlayback();
    releaseWakeLock();
    return;
  }

  if (action.type === "complete") {
    saveProgress(action.segmentIndex, { completed: true });
  }

  state.continuousPlayback = false;
  releaseWakeLock();
});

audioPlayer.addEventListener("waiting", () => recordPlaybackTelemetry("audio_waiting"));
audioPlayer.addEventListener("stalled", () => recordPlaybackTelemetry("audio_stalled"));
audioPlayer.addEventListener("suspend", () => recordPlaybackTelemetry("audio_suspend"));
audioPlayer.addEventListener("error", () =>
  recordPlaybackTelemetry("audio_error", { error_code: audioPlayer.error?.code ?? null }),
);

document.addEventListener("visibilitychange", () => {
  recordPlaybackTelemetry("visibility_changed", {
    visibility_state: document.visibilityState,
    document_hidden: document.hidden,
  });
  if (document.visibilityState === "visible" && !audioPlayer.paused) {
    acquireWakeLock();
  }
});

window.addEventListener("pagehide", () => recordPlaybackTelemetry("page_hidden"));
window.addEventListener("pageshow", () => recordPlaybackTelemetry("page_shown"));
document.addEventListener("freeze", () => recordPlaybackTelemetry("page_frozen"));
document.addEventListener("resume", () => recordPlaybackTelemetry("page_resumed"));

initOcr({
  setInputMode,
  renderOptions: renderVoiceControls,
  currentLanguage,
  voiceGenerationPayload,
  stopPlayback,
  openGeneration,
});
registerOcrEvents();
setInputMode(state.inputMode);
loadOptions();
loadHistory();
