from fastapi.testclient import TestClient
from tts_app.api import create_app


def test_profiles_crud_and_validation(test_settings):
    with TestClient(create_app(test_settings, run_background_inline=True)) as client:
        response = client.get('/api/voice-profiles')
        assert response.status_code == 200
        defaults = response.json()
        assert {p['language'] for p in defaults} == {'en', 'zh'}
        profile = {k: defaults[0][k] for k in ('model','voice','language','speed','instructions','preview_text')}
        profile['name'] = '  Reading  '
        created = client.post('/api/voice-profiles', json=profile)
        assert created.status_code == 201
        saved = created.json()
        assert saved['name'] == 'Reading'
        profile['name'] = 'reading'
        assert client.post('/api/voice-profiles', json=profile).status_code == 409
        profile['name'] = ' '
        assert client.post('/api/voice-profiles', json=profile).status_code == 422
        profile['name'] = 'Updated'
        assert client.put(f"/api/voice-profiles/{saved['id']}", json=profile).json()['name'] == 'Updated'
        assert client.delete(f"/api/voice-profiles/{saved['id']}").status_code == 204
        assert client.get(f"/api/voice-profiles/{saved['id']}").status_code == 404
        assert client.delete('/api/voice-samples/cache').status_code == 204
        assert len(client.get('/api/voice-profiles').json()) == 2


def test_profile_generation_snapshots_settings_and_preserves_audio(test_settings):
    app = create_app(test_settings, run_background_inline=True)
    with TestClient(app) as client:
        profile = client.get('/api/voice-profiles').json()[0]
        profile.update(speed=1.25, instructions='Read softly.')
        client.put(f"/api/voice-profiles/{profile['id']}", json=profile)
        response = client.post('/api/generations/text', json={'text': 'A saved voice.', 'profile_id': profile['id']})
        assert response.status_code == 200
        generation_id = response.json()['generation_id']
        detail = app.state.storage.get_generation(generation_id)
        assert detail['generation']['settings']['profile_id'] == profile['id']
        assert detail['generation']['settings']['model'] == profile['model']
        assert detail['generation']['settings']['instructions'] == 'Read softly.'
        audio = list((test_settings.audio_dir / str(generation_id)).glob('*.mp3'))
        assert audio
        assert b'instructions=Read softly.' in audio[0].read_bytes()
        assert b'speed=1.25' in audio[0].read_bytes()
        client.delete(f"/api/voice-profiles/{profile['id']}")
        assert audio[0].exists()
        assert app.state.storage.get_generation(generation_id)['generation']['settings'] == detail['generation']['settings']


def test_profile_rejects_explicit_overrides_and_missing_profile(test_settings):
    with TestClient(create_app(test_settings, run_background_inline=True)) as client:
        profile = client.get('/api/voice-profiles').json()[0]
        for field, value in [('voice', 'Kai'), ('speed', 1), ('language', 'en'), ('model', profile['model']), ('instructions', '')]:
            assert client.post('/api/generations/text', json={'text': 'Hello', 'profile_id': profile['id'], field: value}).status_code == 400
        assert client.post('/api/generations/text', json={'text': 'Hello', 'profile_id': 99999}).status_code == 404
        legacy = client.post('/api/generations/text', json={'text': 'Hello', 'voice': 'Legacy', 'speed': 1.1, 'language': 'zh'})
        assert legacy.status_code == 200


def test_url_and_ocr_use_profile_and_ocr_mismatch_is_readonly(test_settings, monkeypatch):
    from tts_app.extractor import ExtractedText
    async def extract(url):
        return ExtractedText(url=url, title='URL', text='From a web page.')
    monkeypatch.setattr('tts_app.api.fetch_and_extract', extract)
    app = create_app(test_settings, run_background_inline=True)
    with TestClient(app) as client:
        english, chinese = client.get('/api/voice-profiles').json()
        result = client.post('/api/generations/url', json={'url': 'https://example.com', 'profile_id': english['id']})
        assert result.status_code == 200
        detail = app.state.storage.get_generation(result.json()['generation_id'])
        assert detail['generation']['settings']['profile_id'] == english['id']
        draft_id = app.state.storage.create_ocr_draft(ocr_model='fake', language='zh', status='completed')
        app.state.storage.update_ocr_draft(draft_id, language='zh', combined_text='中文内容', image_texts={})
        mismatch = client.post(f'/api/ocr-drafts/{draft_id}/generation', json={'profile_id': english['id'], 'combined_text': 'Do not store this'})
        assert mismatch.status_code == 400
        assert app.state.storage.get_ocr_draft(draft_id)['combined_text'] == '中文内容'
        result = client.post(f'/api/ocr-drafts/{draft_id}/generation', json={'profile_id': chinese['id']})
        assert result.status_code == 200
        detail = app.state.storage.get_generation(result.json()['generation_id'])
        assert detail['generation']['settings']['language'] == 'zh'
        assert detail['generation']['settings']['instructions'] == chinese['instructions']
