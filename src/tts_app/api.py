from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Iterable
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tts_app.config import Settings, load_settings
from tts_app.events import EventBroker
from tts_app.extractor import ExtractionError, fetch_and_extract
from tts_app.generation import GenerationService
from tts_app.ocr_providers.base import OCROptions, OCRProviderError
from tts_app.ocr_providers.registry import get_ocr_provider
from tts_app.providers.base import TTSOptions
from tts_app.providers.options import SelectOption
from tts_app.providers.registry import get_provider
from tts_app.storage import Storage

logger = logging.getLogger(__name__)


class TextGenerationRequest(BaseModel):
    text: str = Field(min_length=1)
    title: str = "Manual text"
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"
    autoplay: bool = True


class UrlGenerationRequest(BaseModel):
    url: str = Field(min_length=1)
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"
    autoplay: bool = True


class ProgressRequest(BaseModel):
    segment_index: int = Field(ge=0)
    completed: bool = False


class VoicePreferenceRequest(BaseModel):
    preferred: bool
    language: str = "en"


TTS_LANGUAGES = {
    "en": "English",
    "zh": "Chinese",
}


class VoiceSampleRequest(BaseModel):
    voice: str
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"


class OcrDraftUpdateRequest(BaseModel):
    language: str
    extracted_text: str


class OcrDraftGenerationRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"
    autoplay: bool = True


SAMPLE_TEXT = {
    "en": "This is a short Readvox voice sample. Use it to check the voice, pacing, clarity, and listening comfort before generating the full article.",
    "zh": "这是一个简短的 Readvox 语音示例。请用它来检查声音、语速、清晰度和听感是否适合长时间收听。",
}

SAMPLE_LANGUAGES = {
    "en": "English",
    "zh": "Chinese",
}


def create_app(settings: Settings | None = None, run_background_inline: bool = False) -> FastAPI:
    active_settings = settings or load_settings()
    storage = Storage(active_settings.db_path)
    storage.init_schema()
    broker = EventBroker()
    provider = get_provider(active_settings)
    ocr_provider = get_ocr_provider(active_settings)
    service = GenerationService(
        storage=storage,
        provider=provider,
        broker=broker,
        audio_dir=active_settings.audio_dir,
        segment_max_chars=active_settings.segment_max_chars,
    )
    app = FastAPI(title="Readvox")
    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.state.settings = active_settings
    app.state.storage = storage
    app.state.broker = broker
    app.state.service = service
    app.state.ocr_provider = ocr_provider

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

    @app.get("/api/options")
    async def options():
        preferences = storage.list_voice_preferences()
        provider_voices = tuple(provider.english_voices) + tuple(provider.chinese_voices)
        default_english_voice = active_settings.qwen_voice
        default_chinese_voice = _default_voice_for_language(provider.chinese_voices, preferred="Cherry")
        voices = _voice_option_dicts(provider_voices, preferences)
        if not _has_voice(voices, default_english_voice, "en"):
            voices.insert(
                0,
                {
                    "value": default_english_voice,
                    "label": default_english_voice,
                    "language": "en",
                    "preferred": preferences.get((default_english_voice, "en"), False),
                },
            )
        if default_chinese_voice and not _has_voice(voices, default_chinese_voice, "zh"):
            voices.insert(
                len([voice for voice in voices if voice["language"] == "en"]),
                {
                    "value": default_chinese_voice,
                    "label": default_chinese_voice,
                    "language": "zh",
                    "preferred": preferences.get((default_chinese_voice, "zh"), False),
                },
            )
        return {
            "default_language": "en",
            "default_voices": {
                "en": default_english_voice,
                "zh": default_chinese_voice,
            },
            "default_voice": default_english_voice,
            "default_speed": 1.0,
            "voices": voices,
            "speeds": _option_dicts(getattr(provider, "speed_options", ())),
        }

    @app.put("/api/voices/{voice}/preference")
    async def update_voice_preference(voice: str, payload: VoicePreferenceRequest):
        _validate_language(payload.language)
        storage.set_voice_preference(voice, payload.language, payload.preferred)
        logger.info(
            "voice_preference_updated voice=%s language=%s preferred=%s",
            voice,
            payload.language,
            payload.preferred,
        )
        return {"voice": voice, "language": payload.language, "preferred": payload.preferred}

    @app.post("/api/voice-sample")
    async def voice_sample(payload: VoiceSampleRequest):
        text = SAMPLE_TEXT.get(payload.language, SAMPLE_TEXT["en"])
        options = TTSOptions(
            voice=payload.voice,
            speed=payload.speed,
            language=SAMPLE_LANGUAGES.get(payload.language, "Auto"),
            audio_format="mp3",
        )

        async def stream():
            async for chunk in provider.stream_speech(text, options):
                yield chunk.data

        return StreamingResponse(stream(), media_type="audio/mpeg")

    @app.post("/api/ocr-drafts")
    async def create_ocr_draft(image: UploadFile = File(...), language: str = Form("en")):
        _validate_ocr_language(language)
        mime_type = image.content_type or "application/octet-stream"
        if not mime_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="uploaded file must be an image")

        image_bytes = await image.read(active_settings.max_image_bytes + 1)
        if not image_bytes:
            raise HTTPException(status_code=400, detail="uploaded image is empty")
        if len(image_bytes) > active_settings.max_image_bytes:
            raise HTTPException(status_code=413, detail="uploaded image is too large")

        extension = _image_extension(image.filename)
        pending_path = f"images/pending/source{extension}"
        draft_id = storage.create_ocr_draft(
            image_path=pending_path,
            original_filename=image.filename,
            mime_type=mime_type,
            byte_size=len(image_bytes),
            ocr_model=ocr_provider.name,
            language=language,
            extracted_text="",
            status="running",
        )
        relative_image_path = f"images/{draft_id}/source{extension}"
        image_path = active_settings.image_dir / str(draft_id) / f"source{extension}"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(image_bytes)

        try:
            extracted_text = await ocr_provider.extract_text(
                image_bytes,
                mime_type,
                OCROptions(language=language, model=active_settings.qwen_ocr_model),
            )
        except OCRProviderError as exc:
            storage.update_ocr_draft_ocr_result(
                draft_id,
                image_path=relative_image_path,
                extracted_text="",
                status="failed",
                error=str(exc),
            )
            logger.warning("ocr_draft_failed draft_id=%s error=%s", draft_id, exc)
            raise HTTPException(status_code=502, detail=f"OCR failed: {exc}") from exc

        storage.update_ocr_draft_ocr_result(
            draft_id,
            image_path=relative_image_path,
            extracted_text=extracted_text,
            status="completed",
            error=None,
        )
        logger.info(
            "ocr_draft_created draft_id=%s language=%s image_bytes=%s text_chars=%s",
            draft_id,
            language,
            len(image_bytes),
            len(extracted_text),
        )
        return storage.get_ocr_draft(draft_id)

    @app.get("/api/ocr-drafts")
    async def list_ocr_drafts():
        return storage.list_ocr_drafts()

    @app.get("/api/ocr-drafts/{draft_id}")
    async def get_ocr_draft(draft_id: int):
        try:
            return storage.get_ocr_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc

    @app.put("/api/ocr-drafts/{draft_id}")
    async def update_ocr_draft(draft_id: int, payload: OcrDraftUpdateRequest):
        _validate_ocr_language(payload.language)
        try:
            draft = storage.get_ocr_draft(draft_id)
            storage.update_ocr_draft(draft_id, extracted_text=payload.extracted_text, language=payload.language)
            storage.update_ocr_draft_ocr_result(
                draft_id,
                image_path=draft["image_path"],
                extracted_text=payload.extracted_text,
                status="completed",
                error=None,
            )
            return storage.get_ocr_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc

    @app.delete("/api/ocr-drafts/{draft_id}", status_code=204)
    async def delete_ocr_draft(draft_id: int):
        try:
            storage.delete_ocr_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        shutil.rmtree(active_settings.image_dir / str(draft_id), ignore_errors=True)
        logger.info("ocr_draft_deleted draft_id=%s", draft_id)
        return Response(status_code=204)

    @app.post("/api/ocr-drafts/{draft_id}/generation")
    async def create_generation_from_ocr_draft(
        draft_id: int,
        payload: OcrDraftGenerationRequest,
        background_tasks: BackgroundTasks,
    ):
        _validate_ocr_language(payload.language)
        try:
            draft = storage.get_ocr_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc

        if draft["status"] != "completed":
            raise HTTPException(status_code=409, detail="ocr draft is not completed")
        if draft["linked_generation_id"] is not None:
            raise HTTPException(status_code=409, detail="ocr draft is already linked to a generation")
        reviewed_text = str(draft["extracted_text"])
        if not reviewed_text.strip():
            raise HTTPException(status_code=400, detail="ocr draft text is empty")
        voice = payload.voice or _default_voice_for_language(active_settings, payload.language)
        generation_id = await service.create_from_text(
            text=reviewed_text,
            title="Image text",
            source_type="image",
            url=None,
            voice=voice,
            settings={
                "autoplay": payload.autoplay,
                "speed": payload.speed,
                "language": payload.language,
                "ocr_draft_id": draft_id,
            },
        )
        try:
            storage.link_ocr_draft_generation(draft_id, generation_id)
        except ValueError as exc:
            storage.delete_generation(generation_id)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KeyError as exc:
            storage.delete_generation(generation_id)
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc
        logger.info(
            "ocr_generation_submitted draft_id=%s generation_id=%s voice=%s speed=%s text_chars=%s",
            draft_id,
            generation_id,
            voice,
            payload.speed,
            len(reviewed_text),
        )
        await _schedule_generation(service, generation_id, voice, payload.speed, background_tasks, run_background_inline)
        return {"generation_id": generation_id}

    @app.post("/api/generations/text")
    async def submit_text(payload: TextGenerationRequest, background_tasks: BackgroundTasks):
        _validate_language(payload.language)
        voice = payload.voice or active_settings.qwen_voice
        generation_id = await service.create_from_text(
            text=payload.text,
            title=payload.title,
            voice=voice,
            settings={"autoplay": payload.autoplay, "speed": payload.speed, "language": payload.language},
        )
        logger.info(
            "text_generation_submitted generation_id=%s voice=%s speed=%s text_chars=%s",
            generation_id,
            voice,
            payload.speed,
            len(payload.text),
        )
        await _schedule_generation(
            service,
            generation_id,
            voice,
            payload.speed,
            _tts_language(payload.language),
            background_tasks,
            run_background_inline,
        )
        return {"generation_id": generation_id}

    @app.post("/api/generations/url")
    async def submit_url(payload: UrlGenerationRequest, background_tasks: BackgroundTasks):
        _validate_language(payload.language)
        voice = payload.voice or active_settings.qwen_voice
        try:
            extracted = await fetch_and_extract(payload.url)
        except ExtractionError as exc:
            logger.warning("url_extraction_failed url=%s error=%s", payload.url, exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        generation_id = await service.create_from_text(
            text=extracted.text,
            title=extracted.title,
            source_type="url",
            url=extracted.url,
            voice=voice,
            settings={"autoplay": payload.autoplay, "speed": payload.speed, "language": payload.language},
        )
        logger.info(
            "url_generation_submitted generation_id=%s voice=%s speed=%s url=%s text_chars=%s",
            generation_id,
            voice,
            payload.speed,
            extracted.url,
            len(extracted.text),
        )
        await _schedule_generation(
            service,
            generation_id,
            voice,
            payload.speed,
            _tts_language(payload.language),
            background_tasks,
            run_background_inline,
        )
        return {"generation_id": generation_id}

    @app.get("/api/generations")
    async def list_generations():
        return storage.list_generations()

    @app.get("/api/generations/{generation_id}")
    async def get_generation(generation_id: int):
        try:
            return storage.get_generation(generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc

    @app.put("/api/generations/{generation_id}/progress")
    async def update_progress(generation_id: int, payload: ProgressRequest):
        try:
            progress = storage.update_generation_progress(generation_id, payload.segment_index, payload.completed)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc
        logger.info(
            "generation_progress_updated generation_id=%s segment_index=%s completed=%s progress_percent=%s",
            generation_id,
            progress["last_segment_index"],
            payload.completed,
            progress["progress_percent"],
        )
        return progress

    @app.delete("/api/generations/{generation_id}", status_code=204)
    async def delete_generation(generation_id: int):
        try:
            storage.get_generation(generation_id)
            linked_ocr_draft = storage.get_ocr_draft_for_generation(generation_id)
            storage.delete_generation(generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc
        shutil.rmtree(active_settings.audio_dir / str(generation_id), ignore_errors=True)
        if linked_ocr_draft is not None:
            shutil.rmtree(active_settings.image_dir / str(linked_ocr_draft["id"]), ignore_errors=True)
            storage.force_delete_ocr_draft(linked_ocr_draft["id"])
        logger.info("generation_deleted generation_id=%s", generation_id)
        return Response(status_code=204)

    @app.get("/api/audio/{generation_id}/{audio_segment_id}")
    async def get_audio(generation_id: int, audio_segment_id: int):
        try:
            audio = storage.get_audio_segment(generation_id, audio_segment_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audio not found") from exc
        path = active_settings.data_dir / audio["file_path"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="audio file not found")
        return FileResponse(path, media_type=audio["mime_type"], stat_result=path.stat())

    @app.get("/api/generations/{generation_id}/events")
    async def generation_events(generation_id: int):
        async def stream():
            async for event in broker.subscribe(generation_id):
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return app


async def _schedule_generation(
    service: GenerationService,
    generation_id: int,
    voice: str,
    speed: float,
    language: str,
    background_tasks: BackgroundTasks,
    run_background_inline: bool,
) -> None:
    if run_background_inline:
        await service.run_generation(generation_id, voice, speed, language)
        return
    background_tasks.add_task(service.run_generation, generation_id, voice, speed, language)


def _validate_language(language: str) -> None:
    if language not in TTS_LANGUAGES:
        raise HTTPException(status_code=400, detail="language must be en or zh")


def _tts_language(language: str) -> str:
    return TTS_LANGUAGES.get(language, "Auto")


def _default_voice_for_language(options: tuple[SelectOption, ...], preferred: str) -> str:
    values = [str(option.value) for option in options]
    if preferred in values:
        return preferred
    return values[0] if values else preferred


def _has_voice(voices: list[dict[str, str | float | bool | None]], value: str, language: str) -> bool:
    return any(str(voice["value"]) == value and voice["language"] == language for voice in voices)


def _validate_ocr_language(language: str) -> None:
    if language not in {"en", "zh"}:
        raise HTTPException(status_code=400, detail="ocr draft language must be en or zh")


def _default_voice_for_language(settings: Settings, language: str) -> str:
    if language == "zh":
        return settings.default_chinese_voice
    return settings.default_english_voice


def _image_extension(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
        return suffix
    return ".img"


def _option_dicts(options: Iterable[SelectOption]) -> list[dict[str, str | float]]:
    return [{"value": option.value, "label": option.label} for option in options]


def _voice_option_dicts(
    options: Iterable[SelectOption],
    preferences: dict[tuple[str, str], bool],
) -> list[dict[str, str | float | bool | None]]:
    voice_options = list(options)
    language_order: dict[str | None, int] = {}
    for option in voice_options:
        language_order.setdefault(option.language, len(language_order))

    sorted_options = sorted(
        enumerate(voice_options),
        key=lambda item: (
            language_order[item[1].language],
            not preferences.get((str(item[1].value), str(item[1].language)), False),
            item[0],
        ),
    )
    return [
        {
            "value": option.value,
            "label": option.label,
            "language": option.language,
            "preferred": preferences.get((str(option.value), str(option.language)), False),
        }
        for _, option in sorted_options
    ]
