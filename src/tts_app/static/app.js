const state = {
  inputMode: "text",
  generations: [],
  ocrDrafts: [],
  currentOcrDraftId: null,
  currentGenerationId: null,
  currentDetail: null,
  currentSegmentIndex: 0,
  eventSource: null,
  samplePlayback: false,
  sampleObjectUrl: null,
  autoplay: false,
  continuousPlayback: false,
  wakeLock: null,
  options: {
    default_language: "en",
    default_voice: "",
    default_speed: 1.0,
    voices: [],
    speeds: [{ value: 1.0, label: "1x" }],
  },
};

const views = document.querySelectorAll(".view");
const navButtons = document.querySelectorAll(".nav-button");
const textModeButton = document.querySelector("#text-mode");
const urlModeButton = document.querySelector("#url-mode");
const imageModeButton = document.querySelector("#image-mode");
const textInput = document.querySelector("#text-input");
const urlInput = document.querySelector("#url-input");
const imageInput = document.querySelector("#image-input");
const textLabel = document.querySelector("#text-label");
const urlLabel = document.querySelector("#url-label");
const imageActions = document.querySelector("#image-actions");
const extractImageTextButton = document.querySelector("#extract-image-text");
const ocrReviewText = document.querySelector("#ocr-review-text");
const generateOcrAudioButton = document.querySelector("#generate-ocr-audio");
const ocrDraftsList = document.querySelector("#ocr-drafts-list");
const generateForm = document.querySelector("#generate-form");
const generateSubmitButton = generateForm.querySelector('button[type="submit"]');
const languageSelect = document.querySelector("#language-select");
const voiceSelect = document.querySelector("#voice-select");
const voiceStar = document.querySelector("#voice-star");
const voiceSample = document.querySelector("#voice-sample");
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
  const isUrl = mode === "url";
  const isImage = mode === "image";
  textModeButton.classList.toggle("active", isText);
  urlModeButton.classList.toggle("active", isUrl);
  imageModeButton.classList.toggle("active", isImage);
  textInput.classList.toggle("hidden", !isText);
  textLabel.classList.toggle("hidden", !isText);
  urlInput.classList.toggle("hidden", !isUrl);
  urlLabel.classList.toggle("hidden", !isUrl);
  imageInput.classList.toggle("hidden", !isImage);
  imageActions.classList.toggle("hidden", !isImage);
  extractImageTextButton.classList.toggle("hidden", !isImage);
  ocrReviewText.classList.toggle("hidden", !isImage || !state.currentOcrDraftId);
  generateOcrAudioButton.classList.toggle("hidden", !isImage || !state.currentOcrDraftId);
  ocrDraftsList.classList.toggle("hidden", !isImage);
  generateSubmitButton.classList.toggle("hidden", isImage);
  if (isImage) {
    loadOcrDrafts();
  }
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

function currentLanguage() {
  return languageSelect.value || state.options.default_language || "en";
}

function languageLabel(language) {
  return { en: "English", zh: "Chinese" }[language] || language || "Auto";
}

function voiceMatchesLanguage(voice, language) {
  return !voice.language || voice.language === language;
}

function selectedVoiceOption() {
  const language = currentLanguage();
  return state.options.voices.find(
    (voice) => String(voice.value) === String(voiceSelect.value) && voiceMatchesLanguage(voice, language),
  );
}

async function submitGeneration(event) {
  event.preventDefault();
  if (state.inputMode === "image") {
    return;
  }
  const isText = state.inputMode === "text";
  const endpoint = isText ? "/api/generations/text" : "/api/generations/url";
  state.autoplay = autoplayInput.checked;
  const payload = {
    autoplay: state.autoplay,
  };
  payload.voice = voiceSelect.value;
  payload.speed = Number(speedSelect.value || "1");
  payload.language = currentLanguage();

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
  renderOptions();
}

function renderOptions() {
  const previousLanguage = currentLanguage();
  const languages = Array.from(
    new Set([
      state.options.default_language || "en",
      ...state.options.voices.map((voice) => voice.language).filter(Boolean),
    ]),
  );
  languageSelect.innerHTML = languages
    .map((language) => {
      const selected = language === previousLanguage ? " selected" : "";
      return `<option value="${escapeHtml(language)}"${selected}>${escapeHtml(languageLabel(language))}</option>`;
    })
    .join("");

  const language = currentLanguage();
  const voices = state.options.voices.filter((voice) => voiceMatchesLanguage(voice, language));
  const defaultVoice = state.options.default_voices?.[language] || state.options.default_voice;
  voiceSelect.innerHTML = voices
    .map((voice) => {
      const selected = voice.value === defaultVoice ? " selected" : "";
      const prefix = voice.preferred ? "★ " : "";
      return `<option value="${escapeHtml(voice.value)}"${selected}>${escapeHtml(prefix)}${escapeHtml(voice.label)}</option>`;
    })
    .join("");
  updateVoiceStar();

  speedSelect.innerHTML = state.options.speeds
    .map((speed) => {
      const selected = Number(speed.value) === Number(state.options.default_speed) ? " selected" : "";
      return `<option value="${escapeHtml(speed.value)}"${selected}>${escapeHtml(speed.label)}</option>`;
    })
    .join("");
}

function updateVoiceStar() {
  const voice = selectedVoiceOption();
  const preferred = Boolean(voice?.preferred);
  voiceStar.textContent = preferred ? "★" : "☆";
  voiceStar.classList.toggle("active", preferred);
  voiceStar.setAttribute("aria-pressed", preferred ? "true" : "false");
}

function clearSamplePlayback() {
  state.samplePlayback = false;
  if (state.sampleObjectUrl) {
    URL.revokeObjectURL(state.sampleObjectUrl);
    state.sampleObjectUrl = null;
  }
}

async function toggleVoicePreference() {
  const voice = selectedVoiceOption();
  if (!voice) {
    return;
  }
  const language = currentLanguage();
  const preferred = !voice.preferred;
  try {
    const response = await fetch(`/api/voices/${encodeURIComponent(voice.value)}/preference`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preferred, language }),
    });
    if (!response.ok) {
      playerStatus.textContent = "Unable to update voice preference";
      return;
    }
    state.options.voices.forEach((option) => {
      if (String(option.value) === String(voice.value) && option.language === voice.language) {
        option.preferred = preferred;
      }
    });
    renderOptions();
  } catch {
    playerStatus.textContent = "Unable to update voice preference";
  }
}

async function playVoiceSample() {
  const voice = voiceSelect.value;
  if (!voice) {
    return;
  }
  stopPlayback();
  try {
    const response = await fetch("/api/voice-sample", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        voice,
        speed: Number(speedSelect.value || "1"),
        language: currentLanguage(),
      }),
    });
    if (!response.ok) {
      playerStatus.textContent = "Unable to load voice sample";
      return;
    }
    const blob = await response.blob();
    clearSamplePlayback();
    state.sampleObjectUrl = URL.createObjectURL(blob);
    state.samplePlayback = true;
    audioPlayer.src = state.sampleObjectUrl;
    audioPlayer.play().catch(() => {
      playerStatus.textContent = "Tap Sample to play audio";
    });
  } catch {
    playerStatus.textContent = "Unable to load voice sample";
  }
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

function showOcrDraft(draft) {
  state.currentOcrDraftId = draft.id;
  if (draft.language) {
    languageSelect.value = draft.language;
    renderOptions();
  }
  ocrReviewText.value = draft.extracted_text || "";
  ocrReviewText.classList.remove("hidden");
  generateOcrAudioButton.classList.remove("hidden");
}

async function loadOcrDrafts() {
  try {
    const response = await fetch("/api/ocr-drafts");
    if (!response.ok) {
      ocrDraftsList.innerHTML = '<div class="history-item">Unable to load image drafts</div>';
      return;
    }
    state.ocrDrafts = await response.json();
    renderOcrDrafts();
  } catch {
    ocrDraftsList.innerHTML = '<div class="history-item">Unable to load image drafts</div>';
  }
}

function renderOcrDrafts() {
  if (state.inputMode !== "image") {
    return;
  }
  if (state.ocrDrafts.length === 0) {
    ocrDraftsList.innerHTML = '<div class="history-item">No image drafts</div>';
    return;
  }
  ocrDraftsList.innerHTML = state.ocrDrafts
    .map((draft) => {
      const created = draft.created_at ? new Date(`${draft.created_at}Z`).toLocaleString() : "";
      const preview = draft.extracted_text || draft.error || draft.original_filename || "Image draft";
      const generationButton = draft.linked_generation_id
        ? `<button class="secondary-action compact-action" type="button" data-action="open-generation" data-generation-id="${draft.linked_generation_id}">Open audio</button>`
        : "";
      return `
        <article class="history-item" data-draft-id="${draft.id}">
          <div class="history-item-title">${escapeHtml(draft.original_filename || "Image draft")}</div>
          <div class="history-item-meta">${escapeHtml(draft.status)} ${escapeHtml(created)}</div>
          <div class="history-item-preview">${escapeHtml(preview)}</div>
          <div class="history-actions">
            <button class="secondary-action compact-action" type="button" data-action="open-draft" data-draft-id="${draft.id}">Review</button>
            ${generationButton}
            <button class="danger-action compact-action" type="button" data-action="delete-draft" data-draft-id="${draft.id}">Delete</button>
          </div>
        </article>
      `;
    })
    .join("");
}

async function extractImageText() {
  const image = imageInput.files?.[0];
  if (!image) {
    return;
  }
  stopPlayback();
  const formData = new FormData();
  formData.append("image", image);
  formData.append("language", currentLanguage());
  playerStatus.textContent = "Extracting image text";
  try {
    const response = await fetch("/api/ocr-drafts", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json();
      playerStatus.textContent = error.detail || "Image text extraction failed";
      await loadOcrDrafts();
      return;
    }
    const draft = await response.json();
    showOcrDraft(draft);
    await loadOcrDrafts();
  } catch {
    playerStatus.textContent = "Image text extraction failed";
  }
}

async function openOcrDraft(draftId) {
  stopPlayback();
  try {
    const response = await fetch(`/api/ocr-drafts/${draftId}`);
    if (!response.ok) {
      playerStatus.textContent = "Unable to load image draft";
      return;
    }
    showOcrDraft(await response.json());
  } catch {
    playerStatus.textContent = "Unable to load image draft";
  }
}

async function deleteOcrDraft(draftId) {
  if (!window.confirm("Delete this image draft?")) {
    return;
  }
  try {
    const response = await fetch(`/api/ocr-drafts/${draftId}`, { method: "DELETE" });
    if (!response.ok) {
      playerStatus.textContent = "Unable to delete image draft";
      return;
    }
    if (state.currentOcrDraftId === draftId) {
      state.currentOcrDraftId = null;
      ocrReviewText.value = "";
      ocrReviewText.classList.add("hidden");
      generateOcrAudioButton.classList.add("hidden");
    }
    await loadOcrDrafts();
  } catch {
    playerStatus.textContent = "Unable to delete image draft";
  }
}

async function generateOcrAudio() {
  if (!state.currentOcrDraftId || !ocrReviewText.value.trim()) {
    return;
  }
  stopPlayback();
  state.autoplay = autoplayInput.checked;
  const language = currentLanguage();
  const text = ocrReviewText.value.trim();
  try {
    const update = await fetch(`/api/ocr-drafts/${state.currentOcrDraftId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language, extracted_text: text }),
    });
    if (!update.ok) {
      const error = await update.json();
      playerStatus.textContent = error.detail || "Unable to save reviewed text";
      return;
    }
    const response = await fetch(`/api/ocr-drafts/${state.currentOcrDraftId}/generation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        voice: voiceSelect.value,
        speed: Number(speedSelect.value || "1"),
        language,
        autoplay: state.autoplay,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      playerStatus.textContent = error.detail || "Image audio generation failed";
      return;
    }
    const result = await response.json();
    await loadOcrDrafts();
    await openGeneration(result.generation_id, { subscribe: true, autoplay: state.autoplay });
  } catch {
    playerStatus.textContent = "Image audio generation failed";
  }
}

async function openGeneration(generationId, options = {}) {
  const settings = { subscribe: false, autoplay: false, ...options };
  stopPlayback();
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
    playSegment(state.currentSegmentIndex);
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
  stopPlayback();
  state.currentGenerationId = null;
  state.currentDetail = null;
  state.currentSegmentIndex = 0;
  readingPane.innerHTML = "";
  playerStatus.textContent = message;
}

function stopPlayback() {
  state.autoplay = false;
  state.continuousPlayback = false;
  audioPlayer.pause();
  audioPlayer.removeAttribute("src");
  audioPlayer.load();
  clearSamplePlayback();
  releaseWakeLock();
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
  button.addEventListener("click", () => {
    stopPlayback();
    closeEventSource();
    showView(button.dataset.view);
  });
});

textModeButton.addEventListener("click", () => setInputMode("text"));
urlModeButton.addEventListener("click", () => setInputMode("url"));
imageModeButton.addEventListener("click", () => setInputMode("image"));
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
    deleteGeneration(generationId);
    return;
  }
  if (action?.dataset.action === "open" || !action) {
    if (event.target.closest(".history-details") && !action) {
      return;
    }
    openGeneration(generationId, { subscribe: false, autoplay: true });
  }
});

ocrDraftsList.addEventListener("click", (event) => {
  const action = event.target.closest("[data-action]");
  const draftItem = event.target.closest("[data-draft-id]");
  if (!action || !draftItem) {
    return;
  }
  const draftId = Number(draftItem.dataset.draftId);
  if (action.dataset.action === "delete-draft") {
    deleteOcrDraft(draftId);
    return;
  }
  if (action.dataset.action === "open-generation") {
    stopPlayback();
    openGeneration(Number(action.dataset.generationId), { subscribe: false, autoplay: true });
    return;
  }
  if (action.dataset.action === "open-draft") {
    openOcrDraft(draftId);
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

languageSelect.addEventListener("change", renderOptions);
voiceSelect.addEventListener("change", updateVoiceStar);
voiceStar.addEventListener("click", toggleVoicePreference);
voiceSample.addEventListener("click", playVoiceSample);
extractImageTextButton.addEventListener("click", extractImageText);
generateOcrAudioButton.addEventListener("click", generateOcrAudio);

audioPlayer.addEventListener("play", () => {
  playPauseButton.textContent = "Pause";
  acquireWakeLock();
});

audioPlayer.addEventListener("pause", () => {
  playPauseButton.textContent = "Play";
  releaseWakeLock();
});

audioPlayer.addEventListener("ended", () => {
  if (state.samplePlayback) {
    audioPlayer.pause();
    audioPlayer.removeAttribute("src");
    audioPlayer.load();
    clearSamplePlayback();
    releaseWakeLock();
    return;
  }
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
