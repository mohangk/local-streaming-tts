import {
  audioPlayer,
  languageSelect,
  playerStatus,
  speedSelect,
  voiceDoneButton,
  voiceEditButton,
  voicePanel,
  voiceSample,
  voiceSelect,
  voiceStar,
  voiceSummarySpeed,
  voiceSummaryText,
} from "./dom.js?v=playback-progress-1";
import { state } from "./state.js?v=playback-progress-1";
import { escapeHtml, formatSpeed } from "./utils.js?v=playback-progress-1";

export const VOICE_SELECTION_STORAGE_KEY = "readvox.voiceSelection.v1";

let stopPlaybackCallback = () => {};

export function languageLabel(language) {
  return { en: "English", zh: "Chinese" }[language] || language || "Auto";
}

export function voiceMatchesLanguage(voice, language) {
  return !voice.language || voice.language === language;
}

function languagesForOptions(options) {
  return Array.from(
    new Set([options.default_language || "en", ...(options.voices || []).map((voice) => voice.language).filter(Boolean)]),
  );
}

function defaultVoiceForLanguage(options, language) {
  const voices = (options.voices || []).filter((voice) => voiceMatchesLanguage(voice, language));
  const defaultVoice = options.default_voices?.[language] || options.default_voice;
  if (voices.some((voice) => String(voice.value) === String(defaultVoice))) {
    return defaultVoice;
  }
  return voices[0]?.value || defaultVoice || "";
}

function hasSpeed(options, speed) {
  return (options.speeds || []).some((option) => Number(option.value) === Number(speed));
}

function hasVoice(options, language, voiceValue) {
  return (options.voices || []).some(
    (voice) => voiceMatchesLanguage(voice, language) && String(voice.value) === String(voiceValue),
  );
}

export function applyStoredVoiceSelection(options, storedSelection = {}) {
  const languages = languagesForOptions(options);
  const defaultLanguage = options.default_language || "en";
  const language = languages.includes(storedSelection.language) ? storedSelection.language : defaultLanguage;
  const storedVoice = storedSelection.voices?.[language];
  const voice = hasVoice(options, language, storedVoice) ? storedVoice : defaultVoiceForLanguage(options, language);
  const speed = hasSpeed(options, storedSelection.speed) ? Number(storedSelection.speed) : Number(options.default_speed || 1);
  return { language, voice, speed };
}

export function updateStoredVoiceSelection(storedSelection = {}, selection) {
  return {
    ...storedSelection,
    language: selection.language,
    speed: selection.speed,
    voices: {
      ...(storedSelection.voices || {}),
      [selection.language]: selection.voice,
    },
  };
}

function readStoredVoiceSelection(storage = window.localStorage) {
  try {
    return JSON.parse(storage.getItem(VOICE_SELECTION_STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function writeStoredVoiceSelection(selection, storage = window.localStorage) {
  try {
    storage.setItem(VOICE_SELECTION_STORAGE_KEY, JSON.stringify(selection));
  } catch {
    // Browser storage can be unavailable in private or locked-down contexts.
  }
}

export function currentLanguage() {
  return languageSelect?.value || state.options.default_language || "en";
}

export function selectedVoiceOption() {
  const language = currentLanguage();
  return state.options.voices.find(
    (voice) => String(voice.value) === String(voiceSelect?.value) && voiceMatchesLanguage(voice, language),
  );
}

export function voiceGenerationPayload() {
  return {
    voice: voiceSelect?.value || "",
    speed: Number(speedSelect?.value || "1"),
    language: currentLanguage(),
  };
}

export function renderVoiceControls(selectionOverride = {}) {
  const selected = applyStoredVoiceSelection(state.options, {
    ...readStoredVoiceSelection(),
    ...selectionOverride,
  });
  renderLanguageOptions(selected.language);
  renderVoiceOptions(selected.language, selected.voice);
  renderSpeedOptions(selected.speed);
  updateVoiceStar();
  updateVoiceSummary();
}

function renderLanguageOptions(selectedLanguage) {
  if (!languageSelect) {
    return;
  }
  languageSelect.innerHTML = languagesForOptions(state.options)
    .map((language) => {
      const selected = language === selectedLanguage ? " selected" : "";
      return `<option value="${escapeHtml(language)}"${selected}>${escapeHtml(languageLabel(language))}</option>`;
    })
    .join("");
}

function renderVoiceOptions(language, selectedVoice) {
  if (!voiceSelect) {
    return;
  }
  const voices = state.options.voices.filter((voice) => voiceMatchesLanguage(voice, language));
  voiceSelect.innerHTML = voices
    .map((voice) => {
      const selected = String(voice.value) === String(selectedVoice) ? " selected" : "";
      const prefix = voice.preferred ? "★ " : "";
      return `<option value="${escapeHtml(voice.value)}"${selected}>${escapeHtml(prefix)}${escapeHtml(voice.label)}</option>`;
    })
    .join("");
}

function renderSpeedOptions(selectedSpeed) {
  if (!speedSelect) {
    return;
  }
  speedSelect.innerHTML = state.options.speeds
    .map((speed) => {
      const selected = Number(speed.value) === Number(selectedSpeed) ? " selected" : "";
      return `<option value="${escapeHtml(speed.value)}"${selected}>${escapeHtml(speed.label)}</option>`;
    })
    .join("");
}

export function updateVoiceStar() {
  const voice = selectedVoiceOption();
  const preferred = Boolean(voice?.preferred);
  voiceStar.textContent = preferred ? "★" : "☆";
  voiceStar.classList.toggle("active", preferred);
  voiceStar.setAttribute("aria-pressed", preferred ? "true" : "false");
}

export function persistCurrentVoiceSelection() {
  const payload = voiceGenerationPayload();
  const stored = readStoredVoiceSelection();
  writeStoredVoiceSelection(updateStoredVoiceSelection(stored, payload));
}

function updateVoiceSummary() {
  if (voiceSummaryText) {
    const voice = selectedVoiceOption();
    voiceSummaryText.textContent = voice?.label || voiceSelect?.value || "Voice";
  }
  if (voiceSummarySpeed) {
    voiceSummarySpeed.textContent = formatSpeed(speedSelect?.value || 1);
  }
}

function handleLanguageChange() {
  const language = currentLanguage();
  const stored = readStoredVoiceSelection();
  const selected = applyStoredVoiceSelection(state.options, { ...stored, language });
  renderVoiceOptions(language, selected.voice);
  renderSpeedOptions(selected.speed);
  updateVoiceStar();
  updateVoiceSummary();
  persistCurrentVoiceSelection();
}

function handleVoiceOrSpeedChange() {
  updateVoiceStar();
  updateVoiceSummary();
  persistCurrentVoiceSelection();
}

export function clearSamplePlayback() {
  state.samplePlayback = false;
  if (state.sampleObjectUrl) {
    URL.revokeObjectURL(state.sampleObjectUrl);
    state.sampleObjectUrl = null;
  }
}

export async function toggleVoicePreference() {
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
    renderVoiceControls();
  } catch {
    playerStatus.textContent = "Unable to update voice preference";
  }
}

export async function playVoiceSample() {
  const payload = voiceGenerationPayload();
  if (!payload.voice) {
    return;
  }
  stopPlaybackCallback();
  try {
    const response = await fetch("/api/voice-sample", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
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

export function setVoiceControlsHidden(hidden) {
  voicePanel?.classList.toggle("hidden", hidden);
}

function setVoiceControlsExpanded(expanded) {
  voicePanel?.classList.toggle("voice-panel-expanded", expanded);
}

export function registerVoiceControlEvents({ stopPlayback } = {}) {
  stopPlaybackCallback = stopPlayback || stopPlaybackCallback;
  languageSelect?.addEventListener("change", handleLanguageChange);
  voiceSelect?.addEventListener("change", handleVoiceOrSpeedChange);
  speedSelect?.addEventListener("change", handleVoiceOrSpeedChange);
  voiceStar?.addEventListener("click", toggleVoicePreference);
  voiceSample?.addEventListener("click", playVoiceSample);
  voiceEditButton?.addEventListener("click", () => setVoiceControlsExpanded(true));
  voiceDoneButton?.addEventListener("click", () => setVoiceControlsExpanded(false));
}
