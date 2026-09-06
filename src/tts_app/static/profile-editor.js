import { sampleReady, sampleValues, setSampleValues, stopSamplePlayback } from './instruction-voice-sample.js?v=profiles-1';
import { responseErrorMessage } from './api-client.js?v=long-samples-1';
import { escapeHtml } from './utils.js?v=playback-progress-1';

export function createProfileEditor({onUse, onClose}) {
  const field = document.querySelector('#profile-name');
  const selector = document.querySelector('#editor-profiles');
  const status = document.querySelector('#instruction-status');
  const save = document.querySelector('#profile-save');
  const remove = document.querySelector('#profile-delete');
  const saveAs = document.querySelector('#profile-save-as');
  let id = null, saved = '', profiles = [], active = false, busy = false;
  const values = () => ({name:field.value, ...sampleValues()});
  const dirty = () => JSON.stringify(values()) !== saved;
  function canLeave() {
    if (busy) return false;
    return !active || !dirty() || window.confirm('Discard unsaved voice profile edits?');
  }
  function close() {
    active = false;
    stopSamplePlayback();
    onClose();
  }
  function fill(profile) {
    stopSamplePlayback();
    id = profile.id || null;
    field.value = profile.name;
    setSampleValues(profile);
    saved = JSON.stringify(values());
    selector.value = String(id || '');
    remove.disabled = !id;
    save.disabled = !id;
    status.textContent = 'Preview changes before saving';
  }
  async function open(profile, available) {
    const options = await sampleReady;
    if (!options) { status.textContent = 'Unable to load voice options'; return; }
    profiles = available;
    selector.innerHTML = (profiles.length ? '' : '<option value="">No saved voices</option>') + profiles.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join('');
    fill(profile || {name:'New voice',model:options.default_model,voice:options.default_voice,language:'en',speed:1,instructions:'',preview_text:'Readvox voice preview.'});
    active = true;
    field.focus();
  }
  function setBusy(value) {
    busy = value;
    document.querySelectorAll('#profile-editor button, #profile-editor select, #profile-editor input, #profile-editor textarea')
      .forEach(control => { control.disabled = value; });
    remove.disabled = value || !id;
    save.disabled = value || !id;
  }
  async function persist(asNew = false) {
    if (busy || (!id && !asNew)) return;
    const payload = values();
    if (asNew) {
      const name = window.prompt('Save voice as:', payload.name);
      if (name === null) return;
      payload.name = name.trim();
      if (!payload.name) { status.textContent = 'Enter a name for the new voice.'; return; }
    }
    const targetId = asNew ? null : id;
    setBusy(true);
    try {
      const response = await fetch(`/api/voice-profiles${targetId ? `/${targetId}` : ''}`, {
        method:targetId ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await responseErrorMessage(response, 'Unable to save profile'));
      const profile = await response.json();
      profiles = [...profiles.filter(item => item.id !== profile.id), profile];
      selector.innerHTML = profiles.map(item => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join('');
      fill(profile);
      await onUse(profile);
      close();
    } catch (error) { status.textContent = error.message; }
    finally { setBusy(false); }
  }
  selector.addEventListener('change', () => {
    if (!canLeave()) { selector.value = String(id || ''); return; }
    const profile = profiles.find(item => String(item.id) === selector.value);
    if (profile) fill(profile);
    else { fill({...values(),id:null,name:'New voice'}); saved = ''; }
  });
  document.querySelector('#profile-cancel').addEventListener('click', () => { if (canLeave()) close(); });
  save.addEventListener('click', () => persist());
  saveAs.addEventListener('click', () => persist(true));
  remove.addEventListener('click', async () => {
    if (!id || !canLeave() || !window.confirm(`Delete “${field.value}”? Existing audio will be kept.`)) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/voice-profiles/${id}`, {method:'DELETE'});
      if (!response.ok) throw new Error(await responseErrorMessage(response, 'Unable to delete profile'));
      await onUse(null);
      close();
    } catch (error) { status.textContent = error.message; }
    finally { setBusy(false); }
  });
  window.addEventListener('beforeunload', event => { if (active && dirty()) { event.preventDefault(); event.returnValue = ''; } });
  return {open, canLeave, leave:close};
}
