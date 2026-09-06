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
