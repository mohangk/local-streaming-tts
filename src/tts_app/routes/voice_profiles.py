from sqlite3 import IntegrityError
from fastapi import APIRouter, HTTPException, Response
from pydantic import Field, field_validator
from tts_app.synthesis import InstructionVoiceSampleRequest, SAMPLE_TEXT, validate_synthesis

AUDIOBOOK_INSTRUCTIONS = 'Read in a calm long-form audiobook style. Use clear articulation, steady pacing, low vocal fatigue, natural sentence endings, and restrained expressiveness. Avoid theatrical delivery, sales energy, exaggerated intonation, whispering, vocal fry, or sharp news-anchor emphasis.'


class VoiceProfileRequest(InstructionVoiceSampleRequest):
    name: str = Field(min_length=1, max_length=120)
    sample_text: str = Field(default='Preview', exclude=True)
    preview_text: str = Field(min_length=1, max_length=50_000)

    @field_validator('name', 'preview_text')
    @classmethod
    def nonempty(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('must not be empty')
        return value


def create_voice_profile_router(storage, cache):
    router = APIRouter(prefix='/api/voice-profiles')
    # Seed only on the first installation, even when all profiles were subsequently deleted.
    with storage.connection() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS profile_migrations (version INTEGER PRIMARY KEY)')
        if not conn.execute('SELECT 1 FROM profile_migrations WHERE version=1').fetchone():
            capabilities = getattr(cache.provider, 'instruction_sample_capabilities', None)
            if capabilities:
                for language, name in [('en', 'English audiobook'), ('zh', 'Chinese audiobook')]:
                    conn.execute('INSERT INTO voice_profiles(name,model,voice,language,speed,instructions,preview_text) VALUES(?,?,?,?,?,?,?)',
                                 (name, capabilities.default_model, capabilities.default_voice, language, 1.0, AUDIOBOOK_INSTRUCTIONS, SAMPLE_TEXT[language]))
                conn.execute('INSERT INTO profile_migrations VALUES(1)')

    @router.get('')
    async def list_profiles():
        return storage.list_voice_profiles()

    @router.get('/{profile_id}')
    async def get_profile(profile_id: int):
        try:
            return storage.get_voice_profile(profile_id)
        except KeyError:
            raise HTTPException(404, 'voice profile not found')

    def save(payload, profile_id=None):
        validate_synthesis(cache, payload)
        try:
            return storage.save_voice_profile(payload.model_dump(), profile_id)
        except IntegrityError:
            raise HTTPException(409, 'A voice profile with this name already exists')
        except KeyError:
            raise HTTPException(404, 'voice profile not found')

    @router.post('', status_code=201)
    async def create_profile(payload: VoiceProfileRequest):
        return save(payload)

    @router.put('/{profile_id}')
    async def update_profile(profile_id: int, payload: VoiceProfileRequest):
        return save(payload, profile_id)

    @router.delete('/{profile_id}', status_code=204)
    async def delete_profile(profile_id: int):
        try:
            storage.delete_voice_profile(profile_id)
        except KeyError:
            raise HTTPException(404, 'voice profile not found')
        return Response(status_code=204)

    return router
