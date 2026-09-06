import { afterEach, describe, expect, it, vi } from 'vitest';

afterEach(() => { vi.resetModules(); vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = ''; window.localStorage.clear(); });

const profiles = [
  { id: 1, name: 'English audiobook', language: 'en', voice: 'Kai', speed: 1, model: 'instruct', instructions: 'Calm', preview_text: 'Preview' },
  { id: 2, name: 'Chinese audiobook', language: 'zh', voice: 'Kai', speed: 1, model: 'instruct', instructions: 'Calm', preview_text: '中文' },
  { id: 3, name: 'Slow English', language: 'en', voice: 'Kai', speed: 0.75, model: 'instruct', instructions: 'Soft', preview_text: 'Preview' },
];

function selectionDom() {
  document.body.innerHTML = '<div id="voice-panel"><select id="language-select"><option value="en">English</option><option value="zh">Chinese</option></select><select id="profile-select"></select><span id="voice-summary-text"></span><span id="voice-summary-speed"></span><button id="voice-edit">Edit</button><p id="profile-status"></p></div>';
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
  document.body.innerHTML = `<section id="profile-editor"><select id="editor-profiles"></select><input id="profile-name"><button id="profile-new"></button><button id="profile-duplicate"></button><button id="profile-delete"></button><button id="profile-save"></button><button id="profile-cancel"></button><button id="profile-import"></button><form id="instruction-sample-form"><select id="instruction-language"></select><select id="instruction-model"></select><select id="instruction-voice"></select><select id="instruction-speed"></select><textarea id="instruction-prompt"></textarea><textarea id="instruction-text"></textarea><button id="instruction-sample"></button><button id="clear-instruction-samples"></button><p id="instruction-status"></p></form><audio id="instruction-audio"></audio></section>`;
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
