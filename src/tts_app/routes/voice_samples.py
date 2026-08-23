from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from tts_app.providers.base import TTSOptions
from tts_app.providers.options import QWEN_INSTRUCTION_MODELS, QWEN_INSTRUCTION_VOICES, SPEED_OPTIONS, SelectOption
from tts_app.voice_samples import VoiceSampleCache, VoiceSampleCacheError


logger = logging.getLogger(__name__)


SAMPLE_TEXT = {
    "en": "This is a short Readvox voice sample. Use it to check the voice, pacing, clarity, and listening comfort before generating the full article.",
    "zh": "这是一个简短的 Readvox 语音示例。请用它来检查声音、语速、清晰度和听感是否适合长时间收听。",
}

SAMPLE_LANGUAGES = {
    "en": "English",
    "zh": "Chinese",
}

ALLOWED_INSTRUCTION_SAMPLE_MODELS = {str(option.value) for option in QWEN_INSTRUCTION_MODELS}
ALLOWED_INSTRUCTION_SAMPLE_VOICES = {str(option.value) for option in QWEN_INSTRUCTION_VOICES}
DEFAULT_INSTRUCTION_SAMPLE_MODEL = "qwen3-tts-instruct-flash-realtime"
DEFAULT_INSTRUCTION_SAMPLE_VOICE = "Kai"
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


def create_voice_sample_router(voice_sample_cache: VoiceSampleCache) -> APIRouter:
    router = APIRouter()

    @router.get("/voice-sample", response_class=HTMLResponse)
    async def voice_sample_page() -> str:
        return _static_file("voice-sample.html").read_text(encoding="utf-8")

    @router.get("/api/voice-sample/options")
    async def instruction_voice_sample_options():
        return {
            "default_language": "en",
            "default_model": DEFAULT_INSTRUCTION_SAMPLE_MODEL,
            "default_speed": 1.0,
            "default_voice": DEFAULT_INSTRUCTION_SAMPLE_VOICE,
            "languages": [
                {"value": "en", "label": "English"},
                {"value": "zh", "label": "Chinese"},
            ],
            "models": _option_dicts(QWEN_INSTRUCTION_MODELS),
            "voices": _option_dicts(QWEN_INSTRUCTION_VOICES),
            "speeds": _option_dicts(SPEED_OPTIONS),
        }

    @router.post("/api/voice-sample")
    async def voice_sample(payload: VoiceSampleRequest):
        _validate_language(payload.language)
        text = SAMPLE_TEXT[payload.language]
        options = TTSOptions(
            voice=payload.voice,
            speed=payload.speed,
            language=SAMPLE_LANGUAGES[payload.language],
            audio_format="mp3",
        )
        try:
            audio, mime_type = await voice_sample_cache.get_or_create(
                text=text,
                options=options,
                language=payload.language,
            )
        except VoiceSampleCacheError as exc:
            logger.exception(
                "voice_sample_provider_failed model=%s voice=%s language=%s error=%s",
                voice_sample_cache.settings.qwen_model,
                payload.voice,
                payload.language,
                exc,
            )
            raise _provider_error() from exc
        return Response(content=audio, media_type=mime_type)

    @router.post("/api/voice-sample/instruction")
    async def instruction_voice_sample(payload: InstructionVoiceSampleRequest):
        _validate_language(payload.language)
        _validate_instruction_model(payload.model)
        _validate_instruction_voice(payload.model, payload.voice)
        options = TTSOptions(
            voice=payload.voice,
            model=payload.model,
            speed=payload.speed,
            language=SAMPLE_LANGUAGES[payload.language],
            audio_format="mp3",
            instructions=payload.instructions,
        )
        try:
            audio, mime_type = await voice_sample_cache.get_or_create(
                text=payload.sample_text,
                options=options,
                language=payload.language,
                model=payload.model,
            )
        except VoiceSampleCacheError as exc:
            logger.exception(
                "instruction_voice_sample_provider_failed model=%s voice=%s language=%s error=%s",
                payload.model,
                payload.voice,
                payload.language,
                exc,
            )
            raise _provider_error() from exc
        return Response(content=audio, media_type=mime_type)

    @router.delete("/api/voice-samples/cache", status_code=204)
    async def clear_voice_sample_cache() -> Response:
        try:
            voice_sample_cache.clear()
        except VoiceSampleCacheError as exc:
            logger.exception("voice_sample_cache_clear_failed error=%s", exc)
            raise HTTPException(
                status_code=500,
                detail={"code": "cache_clear_failed", "message": "Unable to clear voice samples"},
            ) from exc
        return Response(status_code=204)

    return router


def _validate_language(language: str) -> None:
    if language not in SAMPLE_LANGUAGES:
        raise HTTPException(status_code=400, detail="language must be en or zh")


def _validate_instruction_voice(model: str, voice: str) -> None:
    if voice not in ALLOWED_INSTRUCTION_SAMPLE_VOICES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unsupported_voice",
                "message": f"{voice} is not supported by {model}",
            },
        )


def _validate_instruction_model(model: str) -> None:
    if model not in ALLOWED_INSTRUCTION_SAMPLE_MODELS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "unsupported_model",
                "message": f"{model} is not supported for instruction samples",
            },
        )


def _provider_error() -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={
            "code": "provider_error",
            "message": "The speech provider could not generate this sample. Check the server logs for details.",
        },
    )


def _option_dicts(options: tuple[SelectOption, ...]) -> list[dict[str, str | float]]:
    return [{"value": option.value, "label": option.label} for option in options]


def _static_file(filename: str) -> Path:
    return Path(__file__).resolve().parents[1] / "static" / filename
