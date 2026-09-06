import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => { vi.resetModules(); vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = ''; window.localStorage.clear(); });

const profiles = [
  { id: 1, name: 'English audiobook', language: 'en', voice: 'Kai', speed: 1, model: 'instruct', instructions: 'Calm', preview_text: 'Preview' },
  { id: 2, name: 'Chinese audiobook', language: 'zh', voice: 'Kai', speed: 1, model: 'instruct', instructions: 'Calm', preview_text: '中文' },
  { id: 3, name: 'Slow English', language: 'en', voice: 'Kai', speed: 0.75, model: 'instruct', instructions: 'Soft', preview_text: 'Preview' },
];

function selectionDom() {
  document.body.innerHTML = '<div id="voice-panel"><select id="language-select"><option value="en">English</option><option value="zh">Chinese</option></select><select id="profile-select"></select><label id="ocr-language-field"></label><button id="voice-edit">Edit</button><p id="profile-status"></p></div>';
}

describe('named profile selection', () => {
  it('remembers selection per language and falls back after a profile is deleted', async () => {
    selectionDom();
    vi.stubGlobal('fetch', vi.fn(async () => ({ok: true, json: async () => profiles})));
    const module = await import('../../src/tts_app/static/profile-selection.js');
    await module.loadProfiles();
    module.registerVoiceControlEvents();
    const selector = document.querySelector('#profile-select');
    selector.value = '3'; selector.dispatchEvent(new window.Event('change'));
    expect(module.voiceGenerationPayload()).toEqual({ profile_id: 3 });
    module.renderVoiceControls({language:'zh'});
    expect(module.voiceGenerationPayload()).toEqual({profile_id:2});
    module.renderVoiceControls({language:'en'});
    expect(module.voiceGenerationPayload()).toEqual({profile_id:3});
    vi.stubGlobal('fetch', vi.fn(async () => ({ok:true, json:async () => profiles.slice(0,2)})));
    await module.loadProfiles();
    expect(module.voiceGenerationPayload()).toEqual({profile_id:1});
  });
});

function editorDom() {
  document.body.innerHTML = `<section id="profile-editor"><select id="editor-profiles"></select><input id="profile-name"><button id="profile-save-as"></button><button id="profile-delete"></button><button id="profile-save"></button><button id="profile-cancel"></button><form id="instruction-sample-form"><select id="instruction-language"></select><select id="instruction-model"></select><select id="instruction-voice"></select><select id="instruction-speed"></select><textarea id="instruction-prompt"></textarea><textarea id="instruction-text"></textarea><button id="instruction-sample"></button><button id="clear-instruction-samples"></button><p id="instruction-status"></p></form><audio id="instruction-audio"></audio></section>`;
}

describe('named profile editor', () => {
  it('previews unsaved values, confirms cancel, and saves the edited snapshot', async () => {
    editorDom();
    const requests = [];
    vi.stubGlobal('fetch', vi.fn(async (url, init) => {
      if (url.endsWith('/options')) return {ok:true,json:async()=>({languages:[{value:'en',label:'English'},{value:'zh',label:'Chinese'}],models:[{value:'instruct',label:'Instruct'}],voices:[{value:'Kai',label:'Kai'}],speeds:[{value:1,label:'1x'}],default_voice:'Kai',default_model:'instruct'})};
      requests.push([url, init]);
      return {ok:true,json:async()=>({...profiles[0],...JSON.parse(init.body)}),blob:async()=>new Blob(['audio'])};
    }));
    vi.spyOn(window.HTMLMediaElement.prototype,'play').mockResolvedValue();
    vi.spyOn(window.HTMLMediaElement.prototype,'pause').mockImplementation(()=>{});
    URL.createObjectURL = vi.fn(()=> 'blob:preview'); URL.revokeObjectURL = vi.fn();
    const { createProfileEditor } = await import('../../src/tts_app/static/profile-editor.js');
    const onUse = vi.fn(), onClose = vi.fn();
    const editor = createProfileEditor({onUse, onClose});
    await editor.open(profiles[0], profiles);
    document.querySelector('#instruction-prompt').value = 'Unsaved soft narration';
    document.querySelector('#instruction-sample-form').dispatchEvent(new window.Event('submit', {cancelable:true}));
    await vi.waitFor(()=>expect(requests).toHaveLength(1));
    expect(JSON.parse(requests[0][1].body).instructions).toBe('Unsaved soft narration');
    expect(requests[0][0]).toBe('/api/voice-sample/instruction');
    vi.spyOn(window,'confirm').mockReturnValue(false);
    expect(editor.canLeave()).toBe(false);
    document.querySelector('#profile-save').click();
    await vi.waitFor(()=>expect(onUse).toHaveBeenCalled());
    expect(JSON.parse(requests[1][1].body).instructions).toBe('Unsaved soft narration');
    expect(requests[1][1].method).toBe('PUT');
    expect(onClose).toHaveBeenCalled();
  });
});

it('ignores malformed persisted selection without removing legacy data', async () => {
  selectionDom();
  window.localStorage.setItem('readvox.profileSelection.v1', 'null');
  window.localStorage.setItem('readvox.voiceSelection.v1', '{broken');
  vi.stubGlobal('fetch', vi.fn(async()=>({ok:true,json:async()=>profiles})));
  const module = await import('../../src/tts_app/static/profile-selection.js');
  await module.loadProfiles();
  expect(module.voiceGenerationPayload()).toEqual({profile_id:1});
  expect(window.localStorage.getItem('readvox.voiceSelection.v1')).toBe('{broken');
});

async function mountEditor(handler = async () => ({ok:true,json:async()=>profiles[0]})) {
  editorDom();
  vi.spyOn(window.HTMLMediaElement.prototype, 'pause').mockImplementation(()=>{});
  const play = vi.spyOn(window.HTMLMediaElement.prototype, 'play').mockResolvedValue();
  URL.createObjectURL = vi.fn(()=> 'blob:preview'); URL.revokeObjectURL = vi.fn();
  const requests = [];
  vi.stubGlobal('fetch', vi.fn(async (url, init) => {
    if (url.endsWith('/options')) return {ok:true,json:async()=>({
      languages:[{value:'en',label:'English'},{value:'zh',label:'Chinese'}],
      models:[{value:'instruct',label:'Instruct'},{value:'legacy',label:'Legacy'}],
      voices:[{value:'Kai',label:'Kai'}], voices_by_model:{instruct:[{value:'Kai',label:'Kai'}],legacy:[{value:'Jennifer',label:'Jennifer'}]},
      speeds:[{value:1,label:'1x'},{value:1.25,label:'1.25x'}], default_model:'instruct',default_voice:'Kai',
    })};
    requests.push([url,init]); return handler(url,init);
  }));
  const { createProfileEditor } = await import('../../src/tts_app/static/profile-editor.js');
  const onUse = vi.fn(), onClose = vi.fn();
  const editor = createProfileEditor({onUse,onClose});
  await editor.open(profiles[0], profiles);
  return {editor,onUse,onClose,requests,play};
}

it('requires deletion confirmation and cancel leaves saved profile unchanged', async () => {
  const {requests, onClose, onUse} = await mountEditor();
  vi.spyOn(window,'confirm').mockReturnValue(false);
  document.querySelector('#profile-delete').click();
  expect(requests).toHaveLength(0);
  document.querySelector('#instruction-text').value = 'Unsaved text';
  document.querySelector('#profile-cancel').click();
  expect(onClose).not.toHaveBeenCalled();
  window.confirm.mockReturnValue(true);
  document.querySelector('#profile-cancel').click();
  expect(onClose).toHaveBeenCalled();
  expect(onUse).not.toHaveBeenCalled();
  expect(requests).toHaveLength(0);
});

it('Save As creates a named voice from unsaved settings without updating the original', async () => {
  const {requests,onUse,onClose} = await mountEditor(async (url,init)=>({ok:true,json:async()=>({...JSON.parse(init.body),id:99})}));
  document.querySelector('#instruction-prompt').value = 'New narration';
  vi.spyOn(window,'prompt').mockReturnValue('  Evening reading  ');
  document.querySelector('#profile-save-as').click();
  await vi.waitFor(()=>expect(onUse).toHaveBeenCalled());
  expect(requests).toHaveLength(1);
  expect(requests[0][0]).toBe('/api/voice-profiles');
  expect(requests[0][1].method).toBe('POST');
  expect(JSON.parse(requests[0][1].body)).toMatchObject({name:'Evening reading',instructions:'New narration'});
  expect(onUse).toHaveBeenCalledWith(expect.objectContaining({id:99}));
  expect(onClose).toHaveBeenCalled();
});

it('cancelled or blank Save As sends nothing and leaves edits intact', async () => {
  const {requests,onClose} = await mountEditor();
  document.querySelector('#instruction-text').value = 'Keep my changes';
  vi.spyOn(window,'prompt').mockReturnValueOnce(null).mockReturnValueOnce(' ');
  document.querySelector('#profile-save-as').click();
  document.querySelector('#profile-save-as').click();
  expect(requests).toHaveLength(0);
  expect(onClose).not.toHaveBeenCalled();
  expect(document.querySelector('#instruction-text').value).toBe('Keep my changes');
});

it('a conflicting Save As keeps the original identity for a later Save', async () => {
  const {requests} = await mountEditor(async()=>({ok:false,json:async()=>({detail:'Name already exists'})}));
  vi.spyOn(window,'prompt').mockReturnValue('Existing name');
  document.querySelector('#profile-save-as').click();
  await vi.waitFor(()=>expect(document.querySelector('#profile-save').disabled).toBe(false));
  expect(document.querySelector('#instruction-status').textContent).toBe('Name already exists');
  document.querySelector('#profile-save').click();
  await vi.waitFor(()=>expect(requests).toHaveLength(2));
  expect(requests[1][0]).toBe('/api/voice-profiles/1');
  expect(requests[1][1].method).toBe('PUT');
});

it('locks mutations during save and restores controls after failure', async () => {
  let finish;
  const response = new Promise(resolve=>{finish=resolve;});
  const {editor,requests} = await mountEditor(()=>response);
  document.querySelector('#profile-save').click();
  expect(editor.canLeave()).toBe(false);
  expect(document.querySelector('#profile-save-as').disabled).toBe(true);
  document.querySelector('#profile-save-as').click();
  expect(document.querySelector('#profile-name').value).toBe('English audiobook');
  finish({ok:false,json:async()=>({detail:'Duplicate name'})});
  await vi.waitFor(()=>expect(document.querySelector('#profile-save').disabled).toBe(false));
  expect(document.querySelector('#instruction-status').textContent).toBe('Duplicate name');
  expect(requests).toHaveLength(1);
});

it('never plays a pending preview after leaving the editor', async () => {
  let finish;
  const response = new Promise(resolve=>{finish=resolve;});
  const {editor,play,requests} = await mountEditor(()=>response);
  document.querySelector('#instruction-sample-form').dispatchEvent(new window.Event('submit',{cancelable:true}));
  expect(requests).toHaveLength(1);
  editor.leave();
  finish({ok:true,blob:async()=>new Blob(['audio'])});
  await vi.waitFor(()=>expect(document.querySelector('#instruction-sample').disabled).toBe(false));
  expect(play).not.toHaveBeenCalled();
});

it('keeps OCR recognition language when saving a profile of another language', async () => {
  selectionDom();
  vi.stubGlobal('fetch', vi.fn(async()=>({ok:true,json:async()=>profiles})));
  const module = await import('../../src/tts_app/static/profile-selection.js');
  await module.loadProfiles();
  module.setVoiceInputMode('image');
  module.renderVoiceControls({language:'zh'});
  await module.loadProfiles(profiles[0], {language:module.currentLanguage()});
  expect(module.currentLanguage()).toBe('zh');
  expect(module.voiceGenerationPayload()).toEqual({profile_id:2});
  expect(document.querySelector('#profile-status').textContent).toContain('recognition language is unchanged');
});

it('shows OCR profile rejection in Generate and preserves reviewed draft text', async () => {
  const {readFileSync} = await import('node:fs');
  document.body.innerHTML = readFileSync('src/tts_app/static/index.html', 'utf8');
  const {state} = await import('../../src/tts_app/static/state.js?v=playback-progress-1');
  state.inputMode = 'image'; state.currentOcrDraftId = 42;
  state.currentOcrDraft = {id:42,language:'zh',linked_generation_id:null,combined_text:'中文'};
  document.querySelector('#ocr-review-list').innerHTML = '<textarea class="ocr-combined-text">Reviewed 中文</textarea>';
  vi.stubGlobal('fetch', vi.fn(async()=>({ok:false,status:400,json:async()=>({detail:'Select a voice profile matching the OCR draft language'})})));
  const {initOcr,registerOcrEvents} = await import('../../src/tts_app/static/ocr.js?v=profiles-1');
  initOcr({voiceGenerationPayload:async()=>({profile_id:1}),stopPlayback:vi.fn()});
  registerOcrEvents();
  document.querySelector('#generate-ocr-audio').click();
  await vi.waitFor(()=>expect(document.querySelector('#profile-status').textContent).toContain('matching the OCR draft language'));
  expect(document.querySelector('.ocr-combined-text').value).toBe('Reviewed 中文');
  expect(state.currentOcrDraftId).toBe(42);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({profile_id:1,combined_text:'Reviewed 中文'});
});

it('Text and URL select all named voices while Image filters by OCR language', async () => {
  selectionDom();
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>profiles})));
  const module = await import('../../src/tts_app/static/profile-selection.js');
  module.registerVoiceControlEvents();
  await module.loadProfiles();
  expect(document.querySelector('#profile-select').options).toHaveLength(3);
  const select = document.querySelector('#profile-select');
  select.value='2'; select.dispatchEvent(new window.Event('change'));
  expect(module.currentLanguage()).toBe('zh');
  expect(module.voiceGenerationPayload()).toEqual({profile_id:2});
  module.setVoiceInputMode('image');
  expect(select.options).toHaveLength(1);
  expect(document.querySelector('#ocr-language-field').classList.contains('hidden')).toBe(false);
  module.setVoiceInputMode('url');
  expect(select.options).toHaveLength(3);
  expect(document.querySelector('#ocr-language-field').classList.contains('hidden')).toBe(true);
});

it('keeps the new identity after Save As succeeds but returning to Generate fails', async () => {
  const {onUse,requests} = await mountEditor(async (url,init)=>({ok:true,json:async()=>({...JSON.parse(init.body),id:99})}));
  onUse.mockRejectedValue(new Error('Offline while refreshing voices'));
  vi.spyOn(window,'prompt').mockReturnValue('New voice');
  document.querySelector('#profile-save-as').click();
  await vi.waitFor(()=>expect(document.querySelector('#instruction-status').textContent).toContain('Offline'));
  expect(document.querySelector('#profile-name').value).toBe('New voice');
  document.querySelector('#profile-save').click();
  await vi.waitFor(()=>expect(requests).toHaveLength(2));
  expect(requests[1][0]).toBe('/api/voice-profiles/99');
});

it('confirmed deletion removes only the selected saved voice', async () => {
  const {requests,onUse,onClose} = await mountEditor(async()=>({ok:true}));
  vi.spyOn(window,'confirm').mockReturnValue(true);
  document.querySelector('#profile-delete').click();
  await vi.waitFor(()=>expect(onClose).toHaveBeenCalled());
  expect(requests).toHaveLength(1);
  expect(requests[0][0]).toBe('/api/voice-profiles/1');
  expect(requests[0][1].method).toBe('DELETE');
  expect(onUse).toHaveBeenCalledWith(null);
});

it('an empty collection permits creation through Save As, not Save', async () => {
  const {editor,requests,onUse} = await mountEditor(async(url,init)=>({ok:true,json:async()=>({...JSON.parse(init.body),id:99})}));
  await editor.open(null,[]);
  expect(document.querySelector('#profile-save').disabled).toBe(true);
  expect(document.querySelector('#profile-delete').disabled).toBe(true);
  expect(document.querySelector('#profile-save-as').disabled).toBe(false);
  vi.spyOn(window,'prompt').mockReturnValue('First voice');
  document.querySelector('#profile-save-as').click();
  await vi.waitFor(()=>expect(onUse).toHaveBeenCalled());
  expect(requests[0][1].method).toBe('POST');
});
