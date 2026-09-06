import { escapeHtml } from './utils.js?v=playback-progress-1';
import { clearSamplePlayback } from './voice-controls.js?v=long-samples-1';
export { clearSamplePlayback };

const languageSelect = document.querySelector('#language-select');
const selector = document.querySelector('#profile-select');
const key = 'readvox.profileSelection.v1';
let profiles = [];
let inputMode = 'text';
let editProfile = () => {};

function readSelection() {
  try {
    const value = JSON.parse(window.localStorage.getItem(key) || '{}');
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  } catch { return {}; }
}
function remember(profile) {
  if (!profile) return;
  try {
    window.localStorage.setItem(key, JSON.stringify({...readSelection(), [profile.language]: profile.id, language: profile.language}));
  } catch { /* Selection still works when browser storage is unavailable. */ }
}
export function currentLanguage() { return languageSelect?.value || 'en'; }
export function selectedProfile() { return profiles.find(profile => String(profile.id) === selector?.value); }
export function voiceGenerationPayload() {
  const profile = selectedProfile();
  if (!profile) throw new Error('Create a voice profile before generating audio');
  return {profile_id: profile.id};
}
export function renderVoiceControls({language} = {}) {
  if (!selector) return;
  languageSelect.value = language || currentLanguage() || readSelection().language || 'en';
  const matching = inputMode === 'image' ? profiles.filter(profile => profile.language === currentLanguage()) : profiles;
  const selected = matching.find(profile => profile.id === readSelection()[currentLanguage()])
    || matching.find(profile => profile.language === currentLanguage()) || matching[0];
  selector.innerHTML = matching.map(profile => `<option value="${profile.id}">${escapeHtml(profile.name)}</option>`).join('');
  if (selected) selector.value = String(selected.id);
  rememberSelection();
}
function rememberSelection() {
  const profile = selectedProfile();
  if (profile && inputMode !== 'image') languageSelect.value = profile.language;
  remember(profile);
}
export async function loadProfiles(useProfile = null, {language} = {}) {
  const response = await fetch('/api/voice-profiles');
  if (!response.ok) throw new Error('Unable to load voice profiles');
  const previous = selectedProfile();
  profiles = await response.json();
  if (useProfile) remember(useProfile);
  renderVoiceControls({language: language || useProfile?.language || currentLanguage()});
  if (useProfile && language && useProfile.language !== language) {
    document.querySelector("#profile-status").textContent = "Profile saved. Image recognition language is unchanged; select a matching voice profile for this draft.";
  }
  if (previous && !profiles.some(profile => profile.id === previous.id)) {
    document.querySelector('#profile-status').textContent = 'The selected profile was deleted. Using the available language default.';
  }
  return profiles;
}
export function setVoiceControlsHidden(hidden) { document.querySelector('#voice-panel')?.classList.toggle('hidden', hidden); }
export function registerVoiceControlEvents({onEdit} = {}) {
  editProfile = onEdit || editProfile;
  languageSelect?.addEventListener('change', () => renderVoiceControls());
  selector?.addEventListener('change', rememberSelection);
  document.querySelector('#voice-edit')?.addEventListener('click', () => editProfile(selectedProfile(), profiles));
  if (languageSelect) languageSelect.value = readSelection().language || 'en';
}

export async function refreshGenerationPayload() {
  await loadProfiles();
  return voiceGenerationPayload();
}

export function setVoiceInputMode(mode, {language} = {}) {
  inputMode = mode;
  document.querySelector('#ocr-language-field')?.classList.toggle('hidden', mode !== 'image');
  renderVoiceControls({language});
}
