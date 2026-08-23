import { responseErrorMessage } from "./api-client.js?v=long-samples-1";

const languageSelect = document.querySelector("#instruction-language");
const voiceSelect = document.querySelector("#instruction-voice");
const speedSelect = document.querySelector("#instruction-speed");
const modelInput = document.querySelector("#instruction-model");
const promptInput = document.querySelector("#instruction-prompt");
const textInput = document.querySelector("#instruction-text");
const form = document.querySelector("#instruction-sample-form");
const sampleButton = document.querySelector("#instruction-sample");
const clearButton = document.querySelector("#clear-instruction-samples");
const statusLine = document.querySelector("#instruction-status");
const audio = document.querySelector("#instruction-audio");

let options = {
  voices: [],
  speeds: [],
  models: [],
  languages: [],
  voices_by_model: {},
  default_language: "en",
  default_model: "",
  default_speed: 1,
  default_voice: "",
};
let objectUrl = null;

function languageLabel(language) {
  return { en: "English", zh: "Chinese" }[language] || language || "Auto";
}

function renderLanguageOptions() {
  languageSelect.innerHTML = options.languages
    .map((language) => {
      const selected = language.value === (options.default_language || "en") ? " selected" : "";
      return `<option value="${escapeHtml(language.value)}"${selected}>${escapeHtml(language.label || languageLabel(language.value))}</option>`;
    })
    .join("");
}

function renderVoiceOptions() {
  const voices = options.voices_by_model?.[modelInput.value] || options.voices;
  const currentVoice = voiceSelect.value;
  const selectedVoice = voices.some((voice) => String(voice.value) === currentVoice)
    ? currentVoice
    : voices.some((voice) => String(voice.value) === String(options.default_voice))
      ? String(options.default_voice)
      : String(voices[0]?.value || "");
  voiceSelect.innerHTML = voices
    .map((voice) => {
      const selected = String(voice.value) === selectedVoice ? " selected" : "";
      return `<option value="${escapeHtml(voice.value)}"${selected}>${escapeHtml(voice.label)}</option>`;
    })
    .join("");
}

function renderModelOptions() {
  modelInput.innerHTML = options.models
    .map((model) => {
      const selected = String(model.value) === String(options.default_model) ? " selected" : "";
      return `<option value="${escapeHtml(model.value)}"${selected}>${escapeHtml(model.label)}</option>`;
    })
    .join("");
}

function renderSpeedOptions() {
  speedSelect.innerHTML = options.speeds
    .map((speed) => {
      const selected = Number(speed.value) === Number(options.default_speed || 1) ? " selected" : "";
      return `<option value="${escapeHtml(speed.value)}"${selected}>${escapeHtml(speed.label)}</option>`;
    })
    .join("");
}

function clearObjectUrl() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
}

async function loadOptions() {
  const response = await fetch("/api/voice-sample/options");
  if (!response.ok) {
    throw new Error("options failed");
  }
  options = await response.json();
  renderLanguageOptions();
  renderModelOptions();
  renderVoiceOptions();
  renderSpeedOptions();
}

async function playInstructionSample(event) {
  event.preventDefault();
  const payload = {
    model: modelInput.value,
    voice: voiceSelect.value,
    speed: Number(speedSelect.value || "1"),
    language: languageSelect.value || "en",
    sample_text: textInput.value,
    instructions: promptInput.value,
  };
  sampleButton.disabled = true;
  statusLine.textContent = "Generating sample...";
  try {
    const response = await fetch("/api/voice-sample/instruction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      statusLine.textContent = await responseErrorMessage(response, "Unable to load voice sample");
      return;
    }
    const blob = await response.blob();
    clearObjectUrl();
    objectUrl = URL.createObjectURL(blob);
    audio.src = objectUrl;
    await audio.play();
    statusLine.textContent = "Playing sample";
  } catch {
    statusLine.textContent = "Unable to load voice sample";
  } finally {
    sampleButton.disabled = false;
  }
}

async function clearSampleCache() {
  clearButton.disabled = true;
  statusLine.textContent = "Clearing samples...";
  try {
    const response = await fetch("/api/voice-samples/cache", { method: "DELETE" });
    if (!response.ok) {
      statusLine.textContent = "Unable to clear samples";
      return;
    }
    clearObjectUrl();
    audio.removeAttribute("src");
    audio.load();
    statusLine.textContent = "Samples cleared";
  } catch {
    statusLine.textContent = "Unable to clear samples";
  } finally {
    clearButton.disabled = false;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

form?.addEventListener("submit", playInstructionSample);
clearButton?.addEventListener("click", clearSampleCache);
modelInput?.addEventListener("change", renderVoiceOptions);

loadOptions().catch(() => {
  statusLine.textContent = "Unable to load voice options";
});
