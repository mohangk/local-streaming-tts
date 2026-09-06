import { escapeHtml, formatSpeed } from './utils.js?v=playback-progress-1';
import { clearSamplePlayback } from './voice-controls.js?v=long-samples-1';
export { clearSamplePlayback };

const languageSelect = document.querySelector('#language-select');
const selector = document.querySelector('#profile-select');
const key = 'readvox.profileSelection.v1';
let profiles = [];
let editProfile = () => {};

function readSelection() {
  try { return JSON.parse(window.localStorage.getItem(key) || '{}'); } catch { return {}; }
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
  const matching = profiles.filter(profile => profile.language === currentLanguage());
  const selected = matching.find(profile => profile.id === readSelection()[currentLanguage()]) || matching[0];
  selector.innerHTML = matching.map(profile => `<option value="${profile.id}">${escapeHtml(profile.name)}</option>`).join('');
  if (selected) selector.value = String(selected.id);
  updateSummary();
}
function updateSummary() {
  const profile = selectedProfile();
  document.querySelector('#voice-summary-text').textContent = profile?.voice || 'No profile — choose Edit to create one';
  document.querySelector('#voice-summary-speed').textContent = profile ? formatSpeed(profile.speed) : '';
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
  selector?.addEventListener('change', updateSummary);
  document.querySelector('#voice-edit')?.addEventListener('click', () => editProfile(selectedProfile(), profiles));
  if (languageSelect) languageSelect.value = readSelection().language || 'en';
}

export async function refreshGenerationPayload() {
  await loadProfiles();
  return voiceGenerationPayload();
}
