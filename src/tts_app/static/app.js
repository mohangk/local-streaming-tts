const state = {
  inputMode: "text",
  generations: [],
  currentGenerationId: null,
  currentDetail: null,
  currentSegmentIndex: 0,
  eventSource: null,
  autoplay: false,
  continuousPlayback: false,
  wakeLock: null,
  options: {
    default_voice: "Cherry",
    default_speed: 1.0,
    voices: [{ value: "Cherry", label: "Cherry" }],
    speeds: [{ value: 1.0, label: "1x" }],
  },
};

const views = document.querySelectorAll(".view");
const navButtons = document.querySelectorAll(".nav-button");
const textModeButton = document.querySelector("#text-mode");
const urlModeButton = document.querySelector("#url-mode");
const textInput = document.querySelector("#text-input");
const urlInput = document.querySelector("#url-input");
const textLabel = document.querySelector("#text-label");
const urlLabel = document.querySelector("#url-label");
const generateForm = document.querySelector("#generate-form");
const voiceSelect = document.querySelector("#voice-select");
const speedSelect = document.querySelector("#speed-select");
const autoplayInput = document.querySelector("#autoplay");
const historySearch = document.querySelector("#history-search");
const historyList = document.querySelector("#history-list");
const backToHistory = document.querySelector("#back-to-history");
const playPauseButton = document.querySelector("#play-pause");
const playerStatus = document.querySelector("#player-status");
const scrollFollow = document.querySelector("#scroll-follow");
const readingPane = document.querySelector("#reading-pane");
const audioPlayer = document.querySelector("#audio-player");

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
  textModeButton.classList.toggle("active", isText);
  urlModeButton.classList.toggle("active", !isText);
  textInput.classList.toggle("hidden", !isText);
  textLabel.classList.toggle("hidden", !isText);
  urlInput.classList.toggle("hidden", isText);
  urlLabel.classList.toggle("hidden", isText);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatSpeed(value) {
  const speed = Number(value || 1);
  return `${Number.isInteger(speed) ? speed.toFixed(0) : speed}x`;
}

async function submitGeneration(event) {
  event.preventDefault();
  const isText = state.inputMode === "text";
  const endpoint = isText ? "/api/generations/text" : "/api/generations/url";
  state.autoplay = autoplayInput.checked;
  const payload = {
    autoplay: state.autoplay,
  };
  payload.voice = voiceSelect.value;
  payload.speed = Number(speedSelect.value || "1");

  if (isText) {
    payload.text = textInput.value.trim();
    payload.title = "Manual text";
  } else {
    payload.url = urlInput.value.trim();
  }

  if ((isText && !payload.text) || (!isText && !payload.url)) {
    return;
  }

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
  renderOptions();
}

function renderOptions() {
  voiceSelect.innerHTML = state.options.voices
    .map((voice) => {
      const selected = voice.value === state.options.default_voice ? " selected" : "";
      return `<option value="${escapeHtml(voice.value)}"${selected}>${escapeHtml(voice.label)}</option>`;
    })
    .join("");

  speedSelect.innerHTML = state.options.speeds
    .map((speed) => {
      const selected = Number(speed.value) === Number(state.options.default_speed) ? " selected" : "";
      return `<option value="${escapeHtml(speed.value)}"${selected}>${escapeHtml(speed.label)}</option>`;
    })
    .join("");
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
  } catch {
    state.wakeLock = null;
  }
}

function releaseWakeLock() {
  if (!state.wakeLock) {
    return;
  }
  const lock = state.wakeLock;
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

async function deleteGeneration(generationId) {
  if (!window.confirm("Delete this history entry and cached audio?")) {
    return;
  }
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
}

async function openGeneration(generationId, options = {}) {
  const settings = { subscribe: false, autoplay: false, ...options };
  state.currentGenerationId = generationId;
  state.currentSegmentIndex = 0;
  state.autoplay = Boolean(settings.autoplay);
  state.continuousPlayback = state.autoplay;
  showView("playback-view");
  if (settings.subscribe) {
    subscribeToGeneration(generationId);
  } else {
    closeEventSource();
  }
  const loaded = await loadGenerationDetail(generationId);
  if (loaded && state.autoplay) {
    playSegment(0);
  }
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
    if (detail.text_segments.length > 0) {
      const savedIndex = Number(detail.generation.last_segment_index || 0);
      state.currentSegmentIndex = Math.min(Math.max(savedIndex, 0), detail.text_segments.length - 1);
    }
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
  audioPlayer.pause();
  audioPlayer.removeAttribute("src");
  state.currentGenerationId = null;
  state.currentDetail = null;
  state.currentSegmentIndex = 0;
  state.autoplay = false;
  state.continuousPlayback = false;
  releaseWakeLock();
  readingPane.innerHTML = "";
  playerStatus.textContent = message;
  playPauseButton.textContent = "Play";
}

function handleEventSourceError() {
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
  updateActiveSegment();
  updatePlayerStatus();

  if (!audio || !state.currentGenerationId) {
    return;
  }

  audioPlayer.src = `/api/audio/${state.currentGenerationId}/${audio.id}`;
  saveProgress(segmentIndex);
  audioPlayer.play().catch(() => {
    playerStatus.textContent = "Tap Play to start audio";
  });
}

async function saveProgress(segmentIndex, options = {}) {
  if (!state.currentGenerationId) {
    return;
  }
  try {
    const response = await fetch(`/api/generations/${state.currentGenerationId}/progress`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ segment_index: segmentIndex, completed: Boolean(options.completed) }),
    });
    if (response.ok && state.currentDetail) {
      const progress = await response.json();
      state.currentDetail.generation.last_segment_index = progress.last_segment_index;
      state.currentDetail.generation.progress_percent = progress.progress_percent;
    }
  } catch {
    // Playback should continue even if progress cannot be saved.
  }
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
  button.addEventListener("click", () => showView(button.dataset.view));
});

textModeButton.addEventListener("click", () => setInputMode("text"));
urlModeButton.addEventListener("click", () => setInputMode("url"));
generateForm.addEventListener("submit", submitGeneration);
historySearch.addEventListener("input", renderHistory);
backToHistory.addEventListener("click", () => showView("history-view"));

historyList.addEventListener("click", (event) => {
  const action = event.target.closest("[data-action]");
  if (!action) {
    return;
  }
  const generationId = Number(action.dataset.generationId);
  if (action.dataset.action === "delete") {
    deleteGeneration(generationId);
    return;
  }
  if (action.dataset.action === "open") {
    openGeneration(generationId, { subscribe: false, autoplay: false });
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

audioPlayer.addEventListener("play", () => {
  playPauseButton.textContent = "Pause";
  acquireWakeLock();
});

audioPlayer.addEventListener("pause", () => {
  playPauseButton.textContent = "Play";
  releaseWakeLock();
});

audioPlayer.addEventListener("ended", () => {
  const nextIndex = state.currentSegmentIndex + 1;
  if (state.continuousPlayback && state.currentDetail && nextIndex < state.currentDetail.text_segments.length) {
    playSegment(nextIndex);
    return;
  }
  if (state.currentDetail && state.currentSegmentIndex >= state.currentDetail.text_segments.length - 1) {
    saveProgress(state.currentSegmentIndex, { completed: true });
  }
  state.continuousPlayback = false;
  releaseWakeLock();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !audioPlayer.paused) {
    acquireWakeLock();
  }
});

loadOptions();
loadHistory();
