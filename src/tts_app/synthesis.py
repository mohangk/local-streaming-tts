"""Shared preview and generation synthesis validation."""
from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from tts_app.providers.options import InstructionModelCapabilities, InstructionSampleCapabilities
from tts_app.voice_samples import VoiceSampleCache

SAMPLE_TEXT = {
    "en": "This is a short Readvox voice sample. Use it to check the voice, pacing, clarity, and listening comfort before generating the full article.",
    "zh": "这是一个简短的 Readvox 语音示例。请用它来检查声音、语速、清晰度和听感是否适合长时间收听。",
}

SAMPLE_LANGUAGES = {
    "en": "English",
    "zh": "Chinese",
}

MAX_INSTRUCTION_SAMPLE_CHARS = 50_000


class VoiceSampleRequest(BaseModel):
    voice: str
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"


class InstructionVoiceSampleRequest(BaseModel):
    model: str = Field(max_length=120)
    voice: str = Field(min_length=1, max_length=120)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"
    sample_text: str = Field(max_length=MAX_INSTRUCTION_SAMPLE_CHARS)
    instructions: str = Field(max_length=4000)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("sample_text")
    @classmethod
    def validate_sample_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("instructions")
    @classmethod
    def validate_instructions(cls, value: str) -> str:
        return value.strip()


def _validate_language(language: str) -> None:
    if language not in SAMPLE_LANGUAGES:
        raise HTTPException(status_code=400, detail="language must be en or zh")


def _validate_instruction_voice(model: InstructionModelCapabilities, voice: str) -> None:
    if voice not in {str(option.value) for option in model.voices}:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unsupported_voice",
                "message": f"{voice} is not supported by {model.option.value}",
            },
        )


def _instruction_capabilities(voice_sample_cache: VoiceSampleCache) -> InstructionSampleCapabilities:
    capabilities = getattr(voice_sample_cache.provider, "instruction_sample_capabilities", None)
    if capabilities is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "instruction_samples_unavailable",
                "message": "The configured speech provider does not support instruction samples",
            },
        )
    return capabilities


def _instruction_model(
    capabilities: InstructionSampleCapabilities,
    model: str,
) -> InstructionModelCapabilities:
    for candidate in capabilities.models:
        if candidate.option.value == model:
            return candidate
    raise HTTPException(
        status_code=400,
        detail={
            "code": "unsupported_model",
            "message": f"{model} is not supported for instruction samples",
        },
    )



def validate_synthesis(cache, payload):
    _validate_language(payload.language)
    model = _instruction_model(_instruction_capabilities(cache), payload.model)
    _validate_instruction_voice(model, payload.voice)
