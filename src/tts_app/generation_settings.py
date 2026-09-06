"""Resolve request settings once; generation jobs consume only stored snapshots."""
from fastapi import HTTPException
from pydantic import BaseModel, Field
from tts_app.synthesis import InstructionVoiceSampleRequest, SAMPLE_LANGUAGES, validate_synthesis
from tts_app.voice_samples import VoiceSampleCache


class GenerationSynthesisRequest(BaseModel):
    profile_id: int | None = Field(default=None, gt=0)
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = 'en'
    model: str | None = None
    instructions: str | None = None
    autoplay: bool = True


def resolve_generation_settings(payload, storage, settings, provider, required_language=None):
    if payload.profile_id is not None:
        if payload.model_fields_set & {'voice', 'speed', 'language', 'model', 'instructions'}:
            raise HTTPException(400, 'A profile cannot be combined with explicit synthesis overrides')
        try:
            profile = storage.get_voice_profile(payload.profile_id)
        except KeyError:
            raise HTTPException(404, 'voice profile not found')
        validate_synthesis(VoiceSampleCache(settings, provider), InstructionVoiceSampleRequest(
            **{key: profile[key] for key in ('model', 'voice', 'speed', 'language', 'instructions')},
            sample_text=profile['preview_text'],
        ))
        if required_language is not None and profile['language'] != required_language:
            raise HTTPException(400, 'Select a voice profile matching the OCR draft language')
        return {**{key: profile[key] for key in ('model', 'voice', 'speed', 'language', 'instructions')},
                'profile_id': profile['id'], 'profile_name': profile['name'], 'autoplay': payload.autoplay}
    if payload.language not in SAMPLE_LANGUAGES:
        raise HTTPException(400, 'language must be en or zh')
    return {'voice': payload.voice or (settings.default_chinese_voice if payload.language == 'zh' else settings.default_english_voice),
            'speed': payload.speed, 'language': payload.language, 'model': settings.qwen_model,
            'instructions': '', 'autoplay': payload.autoplay}
