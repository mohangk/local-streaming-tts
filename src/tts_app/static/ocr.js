import { state } from "./state.js?v=playback-vitest-1";
import {
  autoplayInput,
  cancelOcrUploadButton,
  clearOcrDraftButton,
  extractImageTextButton,
  generateOcrAudioButton,
  imageActions,
  imagePreviewClose,
  imagePreviewImage,
  imagePreviewOverlay,
  imageSelectionList,
  imageUploadInput,
  languageSelect,
  ocrDraftsList,
  ocrReviewList,
  ocrUploadBar,
  ocrUploadProgress,
  ocrUploadStatus,
  playerStatus,
  speedSelect,
  uploadImageFilesButton,
  voiceSelect,
} from "./dom.js?v=playback-vitest-1";
import { escapeHtml, withButtonBusy } from "./utils.js?v=playback-vitest-1";

const OCR_IMAGE_MAX_EDGE = 2048;
const OCR_IMAGE_JPEG_QUALITY = 0.85;

const appCallbacks = {};

export function initOcr(callbacks) {
  Object.assign(appCallbacks, callbacks);
}

function setInputMode(mode) {
  appCallbacks.setInputMode(mode);
}

function renderOptions() {
  appCallbacks.renderOptions();
}

function currentLanguage() {
  return appCallbacks.currentLanguage();
}

function stopPlayback() {
  appCallbacks.stopPlayback();
}

function openGeneration(generationId, options = {}) {
  return appCallbacks.openGeneration(generationId, options);
}

export function syncOcrInputMode(mode) {
  const isImage = mode === "image";
  const isDraftImages = mode === "draft-images";
  if (isImage && state.currentOcrDraft?.linked_generation_id) {
    clearActiveOcrDraftState();
  }
  imageUploadInput.classList.add("hidden");
  imageActions.classList.toggle("hidden", !isImage);
  imageSelectionList.classList.toggle("hidden", !isImage || state.pendingOcrImages.length === 0);
  clearOcrDraftButton.classList.toggle("hidden", !isImage || !state.currentOcrDraftId || Boolean(state.currentOcrDraft?.linked_generation_id));
  extractImageTextButton.classList.toggle("hidden", !isImage || state.pendingOcrImages.length === 0);
  ocrReviewList.classList.toggle("hidden", !isImage || !state.currentOcrDraftId);
  generateOcrAudioButton.classList.toggle("hidden", !isImage || !state.currentOcrDraftId);
  ocrDraftsList.classList.toggle("hidden", !isDraftImages);
  if (isDraftImages) {
    loadOcrDrafts();
  }
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

function clearActiveOcrDraftState() {
  state.currentOcrDraftId = null;
  state.currentOcrDraft = null;
  ocrReviewList.innerHTML = "";
  ocrReviewList.classList.add("hidden");
  generateOcrAudioButton.classList.add("hidden");
  generateOcrAudioButton.disabled = true;
  clearOcrDraftButton.classList.add("hidden");
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
      let body;
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
        clearActiveOcrDraftState();
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
      clearActiveOcrDraftState();
      setInputMode("image");
      await loadOcrDrafts();
      playerStatus.textContent = "Cleared images";
    } catch {
      playerStatus.textContent = "Unable to clear images";
    }
  });
}

async function generateOcrAudio(button = null) {
  if (!state.currentOcrDraftId || state.currentOcrDraft?.linked_generation_id || !hasReviewedOcrText()) {
    return;
  }
  await withButtonBusy(button, "Generating...", async () => {
    stopPlayback();
    state.autoplay = autoplayInput.checked;
    const language = currentLanguage();
    const combinedText = reviewedOcrText();
    playerStatus.textContent = "Generating audio...";
    try {
      const response = await fetch(`/api/ocr-drafts/${state.currentOcrDraftId}/generation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice: voiceSelect.value,
          speed: Number(speedSelect.value || "1"),
          language,
          autoplay: state.autoplay,
          combined_text: combinedText,
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
      clearActiveOcrDraftState();
      await loadOcrDrafts();
      await openGeneration(result.generation_id, { subscribe: true, autoplay: state.autoplay });
    } catch {
      playerStatus.textContent = "Image audio generation failed";
    }
  });
  updateGenerateOcrAudioState();
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

export function registerOcrEvents() {
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
  uploadImageFilesButton.addEventListener("click", () => imageUploadInput.click());
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
  generateOcrAudioButton.addEventListener("click", () => generateOcrAudio(generateOcrAudioButton));

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !imagePreviewOverlay.classList.contains("hidden")) {
      closeImagePreview();
    }
  });
}
