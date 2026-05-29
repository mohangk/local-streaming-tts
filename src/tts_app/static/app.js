const state = {
  inputMode: "text",
  generations: [],
  ocrDrafts: [],
  pendingOcrImages: [],
  ocrUploadXhr: null,
  ocrUploadActive: false,
  ocrUploadCancelled: false,
  currentOcrDraftId: null,
  currentOcrDraft: null,
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

const OCR_IMAGE_MAX_EDGE = 2048;
const OCR_IMAGE_JPEG_QUALITY = 0.85;

const views = document.querySelectorAll(".view");
const navButtons = document.querySelectorAll(".nav-button");
const textModeButton = document.querySelector("#text-mode");
const urlModeButton = document.querySelector("#url-mode");
const imageModeButton = document.querySelector("#image-mode");
const draftImagesModeButton = document.querySelector("#draft-images-mode");
const textInput = document.querySelector("#text-input");
const urlInput = document.querySelector("#url-input");
const imageUploadInput = document.querySelector("#image-upload-input");
const textLabel = document.querySelector("#text-label");
const urlLabel = document.querySelector("#url-label");
const imageActions = document.querySelector("#image-actions");
const uploadImageFilesButton = document.querySelector("#upload-image-files");
const clearImageSelectionButton = document.querySelector("#clear-image-selection");
const clearOcrDraftButton = document.querySelector("#clear-ocr-draft");
const extractImageTextButton = document.querySelector("#extract-image-text");
const imageSelectionList = document.querySelector("#image-selection-list");
const ocrUploadProgress = document.querySelector("#ocr-upload-progress");
const ocrUploadStatus = document.querySelector("#ocr-upload-status");
const ocrUploadBar = document.querySelector("#ocr-upload-bar");
const cancelOcrUploadButton = document.querySelector("#cancel-ocr-upload");
const ocrReviewList = document.querySelector("#ocr-review-list");
const generateOcrAudioButton = document.querySelector("#generate-ocr-audio");
const ocrDraftsList = document.querySelector("#ocr-drafts-list");
const generateForm = document.querySelector("#generate-form");
const generateSubmitButton = generateForm.querySelector('button[type="submit"]');
const optionGrid = document.querySelector(".option-grid");
const languageSelect = document.querySelector("#language-select");
const voiceSelect = document.querySelector("#voice-select");
const voiceStar = document.querySelector("#voice-star");
const voiceSample = document.querySelector("#voice-sample");
const speedSelect = document.querySelector("#speed-select");
const autoplayInput = document.querySelector("#autoplay");
const autoplayRow = autoplayInput.closest(".toggle-row");
const historySearch = document.querySelector("#history-search");
const historyList = document.querySelector("#history-list");
const backToHistory = document.querySelector("#back-to-history");
const playPauseButton = document.querySelector("#play-pause");
const playerStatus = document.querySelector("#player-status");
const scrollFollow = document.querySelector("#scroll-follow");
const readingPane = document.querySelector("#reading-pane");
const audioPlayer = document.querySelector("#audio-player");
const imagePreviewOverlay = document.querySelector("#image-preview-overlay");
const imagePreviewClose = document.querySelector("#image-preview-close");
const imagePreviewImage = document.querySelector("#image-preview-image");

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
  imageUploadInput.classList.add("hidden");
  imageActions.classList.toggle("hidden", !isImage);
  imageSelectionList.classList.toggle("hidden", !isImage || state.pendingOcrImages.length === 0);
  clearImageSelectionButton.classList.toggle("hidden", !isImage || state.pendingOcrImages.length === 0);
  clearOcrDraftButton.classList.toggle("hidden", !isImage || !state.currentOcrDraftId || Boolean(state.currentOcrDraft?.linked_generation_id));
  extractImageTextButton.classList.toggle("hidden", !isImage || state.pendingOcrImages.length === 0);
  ocrReviewList.classList.toggle("hidden", !isImage || !state.currentOcrDraftId);
  generateOcrAudioButton.classList.toggle("hidden", !isImage || !state.currentOcrDraftId);
  ocrDraftsList.classList.toggle("hidden", !isDraftImages);
  generateSubmitButton.classList.toggle("hidden", isImage || isDraftImages);
  optionGrid.classList.toggle("hidden", isDraftImages);
  voiceSample.classList.toggle("hidden", isDraftImages);
  autoplayRow.classList.toggle("hidden", isDraftImages);
  if (isDraftImages) {
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

function setButtonBusy(button, busy, label) {
  if (!button) {
    return;
  }
  if (busy) {
    button.dataset.originalLabel = button.textContent;
    if (label) {
      button.textContent = label;
    }
    button.classList.add("is-busy");
    button.setAttribute("aria-busy", "true");
    button.disabled = true;
    return;
  }
  if ("originalLabel" in button.dataset) {
    button.textContent = button.dataset.originalLabel;
    delete button.dataset.originalLabel;
  }
  button.classList.remove("is-busy");
  button.removeAttribute("aria-busy");
  button.disabled = false;
}

async function withButtonBusy(button, label, operation) {
  setButtonBusy(button, true, label);
  try {
    return await operation();
  } finally {
    setButtonBusy(button, false);
  }
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
  if (state.inputMode === "image" || state.inputMode === "draft-images") {
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

function showOcrDraft(draft) {
  state.currentOcrDraftId = draft.id;
  state.currentOcrDraft = draft;
  if (state.inputMode !== "image") {
    setInputMode("image");
  }
  if (draft.language) {
    languageSelect.value = draft.language;
    renderOptions();
  }
  renderOcrReview();
  ocrReviewList.classList.remove("hidden");
  generateOcrAudioButton.classList.remove("hidden");
  updateGenerateOcrAudioState();
}

function markCurrentOcrDraftLinked(generationId) {
  if (!state.currentOcrDraft) {
    return;
  }
  state.currentOcrDraft.linked_generation_id = generationId;
  generateOcrAudioButton.classList.add("hidden");
  generateOcrAudioButton.disabled = true;
  playerStatus.textContent = "Audio already generated";
  renderOcrReview();
  renderOcrDrafts();
}

function renderOcrReview() {
  const draft = state.currentOcrDraft;
  if (!draft) {
    ocrReviewList.innerHTML = "";
    return;
  }
  const images = draft.images || [];
  const thumbnails = images
    .map((image) => {
      const error = image.error ? `<div class="history-item-url">${escapeHtml(image.error)}</div>` : "";
      const retryButton =
        image.status === "failed" && !draft.linked_generation_id
          ? `<button class="secondary-action compact-action" type="button" data-action="retry-image" data-image-id="${image.id}">Retry OCR</button>`
          : "";
      const removeButton = !draft.linked_generation_id
        ? `<button class="danger-action compact-action" type="button" data-action="delete-image" data-image-id="${image.id}">Remove</button>`
        : "";
      return `
        <article class="ocr-image-card" data-image-id="${image.id}">
          <div class="ocr-image-header">
            <button class="ocr-thumbnail-button" type="button" data-action="preview-image" data-draft-id="${draft.id}" data-image-id="${image.id}" aria-label="Preview OCR image ${image.position + 1}">
              <img class="ocr-thumbnail" src="/api/ocr-drafts/${draft.id}/images/${image.id}" alt="OCR image ${image.position + 1}" />
            </button>
            <div>
              <div class="history-item-title">Image ${image.position + 1}</div>
              <div class="history-item-meta">${escapeHtml(image.status)} ${escapeHtml(image.original_filename || "")}</div>
              ${error}
            </div>
            <div class="ocr-image-actions">
              ${retryButton}
              ${removeButton}
            </div>
          </div>
        </article>
      `;
    })
    .join("");
  ocrReviewList.innerHTML = `
    <textarea class="ocr-combined-text" rows="10" aria-label="Reviewed OCR text">${escapeHtml(draft.combined_text || "")}</textarea>
    ${images.length ? `<div class="ocr-thumbnail-strip">${thumbnails}</div>` : '<div class="history-item">No images stored for this draft</div>'}
  `;
}

function reviewedOcrText() {
  return ocrReviewList.querySelector(".ocr-combined-text")?.value || "";
}

function hasReviewedOcrText() {
  return reviewedOcrText().trim().length > 0;
}

function updateGenerateOcrAudioState() {
  generateOcrAudioButton.disabled =
    !state.currentOcrDraftId || Boolean(state.currentOcrDraft?.linked_generation_id) || !hasReviewedOcrText();
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
  if (state.inputMode !== "draft-images") {
    return;
  }
  const unlinkedDrafts = state.ocrDrafts.filter((draft) => !draft.linked_generation_id);
  if (unlinkedDrafts.length === 0) {
    ocrDraftsList.innerHTML = '<div class="history-item">No image drafts</div>';
    return;
  }
  ocrDraftsList.innerHTML = unlinkedDrafts
    .map((draft) => {
      const created = draft.created_at ? new Date(`${draft.created_at}Z`).toLocaleString() : "";
      const filenames = (draft.images || []).map((image) => image.original_filename).filter(Boolean).join(", ");
      const preview = draftTextPreview(draft.combined_text || draft.error || filenames || "Image draft");
      const thumbnails = (draft.images || [])
        .map(
          (image) => `
            <button class="ocr-thumbnail-button" type="button" data-action="preview-image" data-draft-id="${draft.id}" data-image-id="${image.id}" aria-label="Preview image ${image.position + 1}">
              <img class="ocr-thumbnail" src="/api/ocr-drafts/${draft.id}/images/${image.id}" alt="OCR image ${image.position + 1}" />
            </button>
          `,
        )
        .join("");
      return `
        <article class="history-item" data-draft-id="${draft.id}">
          <div class="history-item-title">${escapeHtml(filenames || "Image draft")}</div>
          <div class="history-item-meta">${escapeHtml(draft.status)} ${escapeHtml(created)}</div>
          <div class="history-item-preview">${escapeHtml(preview)}</div>
          <div class="ocr-thumbnail-strip draft-thumbnail-strip">${thumbnails}</div>
          <div class="history-actions">
            <button class="secondary-action compact-action" type="button" data-action="open-draft" data-draft-id="${draft.id}">Continue</button>
            <button class="danger-action compact-action" type="button" data-action="delete-draft" data-draft-id="${draft.id}">Delete</button>
          </div>
        </article>
      `;
    })
    .join("");
}

function draftTextPreview(text) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= 180) {
    return normalized;
  }
  return `${normalized.slice(0, 177)}...`;
}

function pendingImageLabel(file, index) {
  const name = file.name || `Image ${index + 1}`;
  const size = file.size ? ` ${Math.round(file.size / 1024)} KB` : "";
  return `${index + 1}. ${name}${size}`;
}

function renderPendingOcrImages() {
  const hasImages = state.pendingOcrImages.length > 0;
  const isImageMode = state.inputMode === "image";
  imageSelectionList.classList.toggle("hidden", !isImageMode || !hasImages);
  clearImageSelectionButton.classList.toggle("hidden", !isImageMode || !hasImages);
  extractImageTextButton.classList.toggle("hidden", !isImageMode || !hasImages);
  if (!hasImages) {
    imageSelectionList.innerHTML = "";
    return;
  }
  imageSelectionList.innerHTML = state.pendingOcrImages
    .map(
      (image, index) => `
        <div class="image-selection-item">
          <span class="image-selection-name">${escapeHtml(pendingImageLabel(image, index))}</span>
          <button class="danger-action compact-action" type="button" data-action="remove-pending-image" data-index="${index}">Remove</button>
        </div>
      `,
    )
    .join("");
}

function appendPendingOcrImages(images) {
  if (images.length === 0) {
    return;
  }
  state.pendingOcrImages.push(...images);
  renderPendingOcrImages();
  playerStatus.textContent = `${state.pendingOcrImages.length} ${state.pendingOcrImages.length === 1 ? "image" : "images"} selected`;
}

function removePendingOcrImage(index) {
  state.pendingOcrImages.splice(index, 1);
  renderPendingOcrImages();
  playerStatus.textContent = state.pendingOcrImages.length
    ? `${state.pendingOcrImages.length} ${state.pendingOcrImages.length === 1 ? "image" : "images"} selected`
    : "No images selected";
}

function clearPendingOcrImages(options = {}) {
  state.pendingOcrImages = [];
  imageUploadInput.value = "";
  renderPendingOcrImages();
  if (!options.silent) {
    playerStatus.textContent = "No images selected";
  }
}

function showOcrUploadProgress(message, percent = null) {
  ocrUploadProgress.classList.remove("hidden");
  ocrUploadStatus.textContent = message;
  if (percent === null) {
    ocrUploadBar.removeAttribute("value");
    return;
  }
  ocrUploadBar.value = Math.max(0, Math.min(100, percent));
}

function showOcrExtractingProgress() {
  showOcrUploadProgress("Extracting text...");
}

function clearOcrUploadProgress() {
  ocrUploadProgress.classList.add("hidden");
  ocrUploadStatus.textContent = "Preparing images...";
  ocrUploadBar.value = 0;
}

function showOcrUploadError(message) {
  ocrUploadProgress.classList.remove("hidden");
  ocrUploadStatus.textContent = message;
  ocrUploadBar.value = 0;
}

function setOcrUploadActive(active) {
  state.ocrUploadActive = active;
  if (active) {
    state.ocrUploadCancelled = false;
  } else {
    state.ocrUploadXhr = null;
  }
  imageUploadInput.disabled = active;
  uploadImageFilesButton.disabled = active;
  clearImageSelectionButton.disabled = active;
  clearOcrDraftButton.disabled = active;
  languageSelect.disabled = active;
  cancelOcrUploadButton.disabled = !active;
}

function cancelOcrUpload() {
  state.ocrUploadCancelled = true;
  if (state.ocrUploadXhr) {
    const xhr = state.ocrUploadXhr;
    xhr.abort();
    return;
  }
  setOcrUploadActive(false);
  showOcrUploadError("Image upload cancelled");
}

function uploadOcrDraft(formData, draftId = null) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const endpoint = draftId ? `/api/ocr-drafts/${draftId}/images` : "/api/ocr-drafts";
    state.ocrUploadXhr = xhr;
    xhr.open("POST", endpoint);
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        showOcrUploadProgress("Uploading images...");
        return;
      }
      const percent = Math.round((event.loaded / event.total) * 100);
      showOcrUploadProgress(`Uploading images: ${percent}%`, percent);
    };
    xhr.upload.onload = () => {
      showOcrExtractingProgress();
    };
    xhr.onload = () => {
      let body = {};
      try {
        body = JSON.parse(xhr.responseText || "{}");
      } catch {
        body = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body);
        return;
      }
      reject(new Error(body.detail || "Image text extraction failed"));
    };
    xhr.onerror = () => reject(new Error("Image text extraction failed"));
    xhr.onabort = () => reject(new Error("Image upload cancelled"));
    xhr.send(formData);
  });
}

function resizedImageFilename(file) {
  const stem = (file.name || "image").replace(/\.[^.]*$/, "") || "image";
  return `${stem}.jpg`;
}

function loadImageElement(file) {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("Unable to read image"));
    };
    image.src = objectUrl;
  });
}

function scaledImageSize(width, height) {
  const longestEdge = Math.max(width, height);
  if (longestEdge <= OCR_IMAGE_MAX_EDGE) {
    return { width, height, resized: false };
  }
  const scale = OCR_IMAGE_MAX_EDGE / longestEdge;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
    resized: true,
  };
}

function canvasToJpegBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error("Unable to resize image"));
        }
      },
      "image/jpeg",
      OCR_IMAGE_JPEG_QUALITY,
    );
  });
}

async function resizeOcrImageIfNeeded(file) {
  const image = await loadImageElement(file);
  const size = scaledImageSize(image.naturalWidth || image.width, image.naturalHeight || image.height);
  if (!size.resized) {
    return { file, resized: false };
  }

  const canvas = document.createElement("canvas");
  canvas.width = size.width;
  canvas.height = size.height;
  const context = canvas.getContext("2d");
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, size.width, size.height);
  context.drawImage(image, 0, 0, size.width, size.height);
  const blob = await canvasToJpegBlob(canvas);
  const resizedFile = new File([blob], resizedImageFilename(file), { type: "image/jpeg" });
  return { file: resizedFile, resized: true };
}

async function prepareOcrImagesForUpload(images) {
  const prepared = [];
  let resizedCount = 0;
  playerStatus.textContent = `Preparing ${images.length} ${images.length === 1 ? "image" : "images"}...`;
  for (const image of images) {
    const result = await resizeOcrImageIfNeeded(image);
    prepared.push(result.file);
    if (result.resized) {
      resizedCount += 1;
    }
  }
  if (resizedCount > 0) {
    playerStatus.textContent = `Resized ${resizedCount} of ${images.length} ${images.length === 1 ? "image" : "images"}`;
  }
  return prepared;
}

async function extractImageText(button = null) {
  const images = state.pendingOcrImages.slice();
  if (images.length === 0) {
    return;
  }
  await withButtonBusy(button, "Extracting...", async () => {
    stopPlayback();
    setOcrUploadActive(true);
    showOcrUploadProgress(`Preparing ${images.length} ${images.length === 1 ? "image" : "images"}...`, 0);
    let uploadImages;
    try {
      uploadImages = await prepareOcrImagesForUpload(images);
    } catch {
      playerStatus.textContent = "Unable to prepare image for upload";
      showOcrUploadError("Unable to prepare image for upload");
      setOcrUploadActive(false);
      return;
    }
    if (state.ocrUploadCancelled) {
      playerStatus.textContent = "Image upload cancelled";
      showOcrUploadError("Image upload cancelled");
      return;
    }
    const formData = new FormData();
    uploadImages.forEach((image) => {
      formData.append("image", image);
    });
    formData.append("language", currentLanguage());
    playerStatus.textContent = "Extracting image text";
    try {
      const appendDraftId = state.currentOcrDraftId && !state.currentOcrDraft?.linked_generation_id ? state.currentOcrDraftId : null;
      if (appendDraftId) {
        formData.append("combined_text", reviewedOcrText());
      }
      const draft = await uploadOcrDraft(formData, appendDraftId);
      showOcrDraft(draft);
      clearPendingOcrImages({ silent: true });
      clearOcrUploadProgress();
      await loadOcrDrafts();
    } catch (error) {
      const message = error.message || "Image text extraction failed";
      playerStatus.textContent = message;
      showOcrUploadError(message);
      await loadOcrDrafts();
    } finally {
      setOcrUploadActive(false);
      state.ocrUploadCancelled = false;
    }
  });
}

async function openOcrDraft(draftId, button = null) {
  await withButtonBusy(button, "Opening...", async () => {
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
  });
}

async function deleteOcrDraft(draftId, button = null) {
  if (!window.confirm("Delete this image draft?")) {
    return;
  }
  await withButtonBusy(button, "Deleting...", async () => {
    try {
      const response = await fetch(`/api/ocr-drafts/${draftId}`, { method: "DELETE" });
      if (!response.ok) {
        playerStatus.textContent = "Unable to delete image draft";
        return;
      }
      if (state.currentOcrDraftId === draftId) {
        state.currentOcrDraftId = null;
        state.currentOcrDraft = null;
        ocrReviewList.innerHTML = "";
        ocrReviewList.classList.add("hidden");
        generateOcrAudioButton.classList.add("hidden");
      }
      await loadOcrDrafts();
      playerStatus.textContent = "Deleted image draft";
    } catch {
      playerStatus.textContent = "Unable to delete image draft";
    }
  });
}

async function clearActiveOcrDraft() {
  if (!state.currentOcrDraftId || state.currentOcrDraft?.linked_generation_id) {
    return;
  }
  if (!window.confirm("Clear these OCR images and start fresh?")) {
    return;
  }
  await withButtonBusy(clearOcrDraftButton, "Clearing...", async () => {
    try {
      const draftId = state.currentOcrDraftId;
      const response = await fetch(`/api/ocr-drafts/${draftId}`, { method: "DELETE" });
      if (!response.ok) {
        playerStatus.textContent = "Unable to clear images";
        return;
      }
      state.currentOcrDraftId = null;
      state.currentOcrDraft = null;
      ocrReviewList.innerHTML = "";
      setInputMode("image");
      await loadOcrDrafts();
      playerStatus.textContent = "Cleared images";
    } catch {
      playerStatus.textContent = "Unable to clear images";
    }
  });
}

async function generateOcrAudio() {
  if (!state.currentOcrDraftId || state.currentOcrDraft?.linked_generation_id || !hasReviewedOcrText()) {
    return;
  }
  stopPlayback();
  state.autoplay = autoplayInput.checked;
  const language = currentLanguage();
  const combinedText = reviewedOcrText();
  try {
    const update = await fetch(`/api/ocr-drafts/${state.currentOcrDraftId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language, combined_text: combinedText }),
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
        voice: voiceSelect.value,
        speed: Number(speedSelect.value || "1"),
        language,
        autoplay: state.autoplay,
      }),
    });
    if (!response.ok) {
      const error = await response.json();
      if (response.status === 409) {
        const refreshed = await fetch(`/api/ocr-drafts/${state.currentOcrDraftId}`);
        if (refreshed.ok) {
          showOcrDraft(await refreshed.json());
        }
        playerStatus.textContent = error.detail || "Audio already generated";
        return;
      }
      playerStatus.textContent = error.detail || "Image audio generation failed";
      return;
    }
    const result = await response.json();
    markCurrentOcrDraftLinked(result.generation_id);
    await loadOcrDrafts();
    await openGeneration(result.generation_id, { subscribe: true, autoplay: state.autoplay });
  } catch {
    playerStatus.textContent = "Image audio generation failed";
  }
}

async function retryOcrDraftImage(draftId, imageId, button = null) {
  await withButtonBusy(button, "Retrying...", async () => {
    try {
      const response = await fetch(`/api/ocr-drafts/${draftId}/images/${imageId}/retry`, { method: "POST" });
      if (!response.ok) {
        const error = await response.json();
        playerStatus.textContent = error.detail || "Unable to retry OCR";
        return;
      }
      showOcrDraft(await response.json());
      await loadOcrDrafts();
      playerStatus.textContent = "Retried OCR";
    } catch {
      playerStatus.textContent = "Unable to retry OCR";
    }
  });
}

async function deleteOcrDraftImage(draftId, imageId, button = null) {
  if (!window.confirm("Remove this image from the draft?")) {
    return;
  }
  await withButtonBusy(button, "Removing...", async () => {
    try {
      const response = await fetch(`/api/ocr-drafts/${draftId}/images/${imageId}`, { method: "DELETE" });
      if (!response.ok) {
        playerStatus.textContent = "Unable to remove image";
        return;
      }
      await openOcrDraft(draftId);
      await loadOcrDrafts();
      playerStatus.textContent = "Removed image";
    } catch {
      playerStatus.textContent = "Unable to remove image";
    }
  });
}

function openImagePreview(draftId, imageId, alt = "Image preview") {
  imagePreviewImage.src = `/api/ocr-drafts/${draftId}/images/${imageId}`;
  imagePreviewImage.alt = alt;
  imagePreviewOverlay.classList.remove("hidden");
  imagePreviewOverlay.setAttribute("aria-hidden", "false");
}

function closeImagePreview() {
  imagePreviewOverlay.classList.add("hidden");
  imagePreviewOverlay.setAttribute("aria-hidden", "true");
  imagePreviewImage.removeAttribute("src");
  imagePreviewImage.alt = "";
}

async function openGeneration(generationId, options = {}) {
  const settings = { subscribe: false, autoplay: false, ...options };
  await withButtonBusy(settings.button, "Opening...", async () => {
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

ocrDraftsList.addEventListener("click", (event) => {
  const action = event.target.closest("[data-action]");
  const draftItem = event.target.closest("[data-draft-id]");
  if (!draftItem) {
    return;
  }
  const draftId = Number(draftItem.dataset.draftId);
  if (!action) {
    openOcrDraft(draftId);
    return;
  }
  if (action.dataset.action === "preview-image") {
    openImagePreview(Number(action.dataset.draftId), Number(action.dataset.imageId), action.querySelector("img")?.alt || "Image preview");
    return;
  }
  if (action.dataset.action === "delete-draft") {
    deleteOcrDraft(Number(action.dataset.draftId), action);
    return;
  }
  if (action.dataset.action === "open-generation") {
    stopPlayback();
    openGeneration(Number(action.dataset.generationId), { subscribe: false, autoplay: true, button: action });
    return;
  }
  if (action.dataset.action === "open-draft") {
    openOcrDraft(Number(action.dataset.draftId), action);
  }
});

ocrReviewList.addEventListener("input", () => {
  if (state.currentOcrDraft) {
    state.currentOcrDraft.combined_text = reviewedOcrText();
  }
  updateGenerateOcrAudioState();
});

ocrReviewList.addEventListener("click", (event) => {
  const action = event.target.closest("[data-action]");
  if (!action || !state.currentOcrDraftId) {
    return;
  }
  if (action.dataset.action === "preview-image") {
    openImagePreview(state.currentOcrDraftId, Number(action.dataset.imageId), action.querySelector("img")?.alt || "Image preview");
    return;
  }
  if (action.dataset.action === "delete-image") {
    deleteOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action);
    return;
  }
  if (action.dataset.action === "retry-image") {
    retryOcrDraftImage(state.currentOcrDraftId, Number(action.dataset.imageId), action);
  }
});

imagePreviewOverlay.addEventListener("click", (event) => {
  if (event.target === imagePreviewOverlay) {
    closeImagePreview();
  }
});

imagePreviewClose.addEventListener("click", closeImagePreview);

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
uploadImageFilesButton.addEventListener("click", () => imageUploadInput.click());
clearImageSelectionButton.addEventListener("click", clearPendingOcrImages);
clearOcrDraftButton.addEventListener("click", clearActiveOcrDraft);
imageUploadInput.addEventListener("change", () => {
  appendPendingOcrImages(Array.from(imageUploadInput.files || []));
  imageUploadInput.value = "";
});
imageSelectionList.addEventListener("click", (event) => {
  const action = event.target.closest("[data-action]");
  if (!action || action.dataset.action !== "remove-pending-image") {
    return;
  }
  removePendingOcrImage(Number(action.dataset.index));
});
cancelOcrUploadButton.addEventListener("click", cancelOcrUpload);
extractImageTextButton.addEventListener("click", () => extractImageText(extractImageTextButton));
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

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !imagePreviewOverlay.classList.contains("hidden")) {
    closeImagePreview();
  }
});

setInputMode(state.inputMode);
loadOptions();
loadHistory();
