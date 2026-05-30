from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from tts_app.config import Settings
from tts_app.generation import GenerationService
from tts_app.ocr_providers.base import OCROptions, OCRProvider, OCRProviderError
from tts_app.routes.shared import schedule_generation
from tts_app.storage import Storage

logger = logging.getLogger(__name__)

OCR_TTS_LANGUAGES = {
    "en": "English",
    "zh": "Chinese",
}


class OcrDraftImageUpdate(BaseModel):
    id: int
    extracted_text: str


class OcrDraftUpdateRequest(BaseModel):
    language: str
    combined_text: str | None = None
    images: list[OcrDraftImageUpdate] = Field(default_factory=list)
    extracted_text: str | None = None


class OcrDraftGenerationRequest(BaseModel):
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    language: str = "en"
    autoplay: bool = True
    combined_text: str | None = None


def create_ocr_router(
    *,
    settings: Settings,
    storage: Storage,
    ocr_provider: OCRProvider,
    service: GenerationService,
    run_background_inline: bool,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/ocr-drafts")
    async def create_ocr_draft(image: list[UploadFile] = File(...), language: str = Form("en")):
        _validate_ocr_language(language)
        uploads = await _read_ocr_uploads(image, settings.max_image_bytes)
        draft_id = storage.create_ocr_draft(
            ocr_model=ocr_provider.name,
            language=language,
            status="running",
        )

        await _store_ocr_uploads(storage, settings, ocr_provider, draft_id, uploads, language, start_position=0)
        storage.rebuild_ocr_draft_combined_text(draft_id)
        draft = storage.get_ocr_draft(draft_id)
        logger.info(
            "ocr_draft_created draft_id=%s language=%s image_count=%s text_chars=%s status=%s",
            draft_id,
            language,
            len(draft["images"]),
            len(draft["combined_text"]),
            draft["status"],
        )
        return draft

    @router.post("/api/ocr-drafts/{draft_id}/images")
    async def append_ocr_draft_images(
        draft_id: int,
        image: list[UploadFile] = File(...),
        language: str = Form("en"),
        combined_text: str | None = Form(None),
    ):
        _validate_ocr_language(language)
        try:
            draft = storage.get_ocr_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc
        if draft["linked_generation_id"] is not None:
            raise HTTPException(status_code=409, detail="ocr draft is linked to generation")

        uploads = await _read_ocr_uploads(image, settings.max_image_bytes)
        appended_texts = await _store_ocr_uploads(
            storage,
            settings,
            ocr_provider,
            draft_id,
            uploads,
            language,
            start_position=len(draft["images"]),
        )
        base_text = str(draft["combined_text"]) if combined_text is None else combined_text
        updated_combined_text = _append_ocr_text(base_text, appended_texts)
        storage.update_ocr_draft(draft_id, language=language, combined_text=updated_combined_text, image_texts={})
        updated = storage.get_ocr_draft(draft_id)
        logger.info(
            "ocr_draft_images_appended draft_id=%s language=%s image_count=%s text_chars=%s status=%s",
            draft_id,
            language,
            len(updated["images"]),
            len(updated["combined_text"]),
            updated["status"],
        )
        return updated

    @router.get("/api/ocr-drafts")
    async def list_ocr_drafts():
        return storage.list_ocr_drafts()

    @router.get("/api/ocr-drafts/{draft_id}")
    async def get_ocr_draft(draft_id: int):
        try:
            return storage.get_ocr_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc

    @router.get("/api/ocr-drafts/{draft_id}/images/{image_id}")
    async def get_ocr_draft_image(draft_id: int, image_id: int):
        try:
            image = storage.get_ocr_draft_image(draft_id, image_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft image not found") from exc
        path = _stored_ocr_image_path(settings, image)
        if not path.exists():
            raise HTTPException(status_code=404, detail="ocr draft image file not found")
        return FileResponse(path, media_type=image["mime_type"], stat_result=path.stat())

    @router.post("/api/ocr-drafts/{draft_id}/images/{image_id}/retry")
    async def retry_ocr_draft_image(draft_id: int, image_id: int):
        try:
            draft = storage.get_ocr_draft(draft_id)
            image = storage.get_ocr_draft_image(draft_id, image_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft image not found") from exc

        if draft["linked_generation_id"] is not None:
            raise HTTPException(status_code=409, detail="ocr draft is linked to generation")

        image_path = _stored_ocr_image_path(settings, image)
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="ocr draft image file not found")

        relative_image_path = str(image["image_path"])
        storage.update_ocr_draft_image_ocr_result(
            draft_id,
            image_id,
            image_path=relative_image_path,
            extracted_text="",
            status="running",
            error=None,
        )
        try:
            extracted_text = await ocr_provider.extract_text(
                image_path.read_bytes(),
                str(image["mime_type"]),
                OCROptions(language=str(draft["language"]), model=settings.ocr_model),
            )
        except OCRProviderError as exc:
            storage.update_ocr_draft_image_ocr_result(
                draft_id,
                image_id,
                image_path=relative_image_path,
                extracted_text="",
                status="failed",
                error=str(exc),
            )
            storage.rebuild_ocr_draft_combined_text(draft_id)
            logger.warning("ocr_draft_image_failed draft_id=%s image_id=%s error=%s", draft_id, image_id, exc, exc_info=True)
            return storage.get_ocr_draft(draft_id)

        if not extracted_text.strip():
            error = "OCR returned no visible text"
            storage.update_ocr_draft_image_ocr_result(
                draft_id,
                image_id,
                image_path=relative_image_path,
                extracted_text="",
                status="failed",
                error=error,
            )
            storage.rebuild_ocr_draft_combined_text(draft_id)
            logger.warning("ocr_draft_image_failed draft_id=%s image_id=%s error=%s", draft_id, image_id, error)
            return storage.get_ocr_draft(draft_id)

        storage.update_ocr_draft_image_ocr_result(
            draft_id,
            image_id,
            image_path=relative_image_path,
            extracted_text=extracted_text,
            status="completed",
            error=None,
        )
        storage.rebuild_ocr_draft_combined_text(draft_id)
        logger.info("ocr_draft_image_retried draft_id=%s image_id=%s text_chars=%s", draft_id, image_id, len(extracted_text))
        return storage.get_ocr_draft(draft_id)

    @router.put("/api/ocr-drafts/{draft_id}")
    async def update_ocr_draft(draft_id: int, payload: OcrDraftUpdateRequest):
        _validate_ocr_language(payload.language)
        try:
            image_texts = {item.id: item.extracted_text for item in payload.images}
            combined_text = payload.combined_text
            if combined_text is None and payload.extracted_text is not None:
                combined_text = payload.extracted_text
            storage.update_ocr_draft(draft_id, language=payload.language, combined_text=combined_text, image_texts=image_texts)
            return storage.get_ocr_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc

    @router.delete("/api/ocr-drafts/{draft_id}/images/{image_id}", status_code=204)
    async def delete_ocr_draft_image(draft_id: int, image_id: int):
        try:
            image = storage.delete_ocr_draft_image(draft_id, image_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft image not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        shutil.rmtree(_stored_ocr_image_path(settings, image).parent, ignore_errors=True)
        logger.info("ocr_draft_image_deleted draft_id=%s image_id=%s", draft_id, image_id)
        return Response(status_code=204)

    @router.delete("/api/ocr-drafts/{draft_id}", status_code=204)
    async def delete_ocr_draft(draft_id: int):
        try:
            storage.delete_ocr_draft(draft_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="ocr draft not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        shutil.rmtree(settings.image_dir / str(draft_id), ignore_errors=True)
        logger.info("ocr_draft_deleted draft_id=%s", draft_id)
        return Response(status_code=204)

    @router.post("/api/ocr-drafts/{draft_id}/generation")
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

        if draft["linked_generation_id"] is not None:
            raise HTTPException(status_code=409, detail="ocr draft is already linked to a generation")
        if payload.combined_text is not None:
            storage.update_ocr_draft(
                draft_id,
                language=payload.language,
                combined_text=payload.combined_text,
                image_texts={},
            )
            draft = storage.get_ocr_draft(draft_id)
        reviewed_text = str(draft["combined_text"]).strip()
        if not reviewed_text.strip():
            raise HTTPException(status_code=400, detail="ocr draft text is empty")
        voice = payload.voice or _default_voice_for_language(settings, payload.language)
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
        await schedule_generation(
            service,
            generation_id,
            voice,
            payload.speed,
            _tts_language_for_ocr_language(payload.language),
            background_tasks,
            run_background_inline,
        )
        return {"generation_id": generation_id}

    return router


def _validate_ocr_language(language: str) -> None:
    if language not in {"en", "zh"}:
        raise HTTPException(status_code=400, detail="ocr draft language must be en or zh")


def _default_voice_for_language(settings: Settings, language: str) -> str:
    if language == "zh":
        return settings.default_chinese_voice
    return settings.default_english_voice


def _tts_language_for_ocr_language(language: str) -> str:
    return OCR_TTS_LANGUAGES.get(language, "Auto")


def _stored_ocr_image_path(settings: Settings, image: dict[str, object]) -> Path:
    image_path = str(image["image_path"])
    data_path = settings.data_dir / image_path
    if data_path.exists():
        return data_path
    parts = Path(image_path).parts
    if parts and parts[0] == "images":
        return settings.image_dir.joinpath(*parts[1:])
    return settings.image_dir / image_path


async def _read_ocr_uploads(images: list[UploadFile], max_image_bytes: int) -> list[dict[str, bytes | str | None]]:
    if not images:
        raise HTTPException(status_code=400, detail="uploaded image is required")
    uploads: list[dict[str, bytes | str | None]] = []
    for image in images:
        mime_type = image.content_type or "application/octet-stream"
        if not mime_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="uploaded file must be an image")
        image_bytes = await image.read(max_image_bytes + 1)
        if not image_bytes:
            raise HTTPException(status_code=400, detail="uploaded image is empty")
        if len(image_bytes) > max_image_bytes:
            raise HTTPException(status_code=413, detail="uploaded image is too large")
        uploads.append({"filename": image.filename, "mime_type": mime_type, "bytes": image_bytes})
    return uploads


def _image_extension(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}:
        return suffix
    return ".img"


async def _store_ocr_uploads(
    storage: Storage,
    settings: Settings,
    ocr_provider: OCRProvider,
    draft_id: int,
    uploads: list[dict[str, bytes | str | None]],
    language: str,
    *,
    start_position: int,
) -> list[str]:
    successful_texts: list[str] = []
    for offset, upload in enumerate(uploads):
        filename = upload["filename"] if isinstance(upload["filename"], str) else None
        mime_type = str(upload["mime_type"] or "application/octet-stream")
        image_bytes = upload["bytes"]
        if not isinstance(image_bytes, bytes):
            raise HTTPException(status_code=400, detail="uploaded image is invalid")

        position = start_position + offset
        extension = _image_extension(filename)
        image_id = storage.create_ocr_draft_image(
            draft_id,
            position=position,
            image_path=f"images/{draft_id}/pending-{position}{extension}",
            original_filename=filename,
            mime_type=mime_type,
            byte_size=len(image_bytes),
            extracted_text="",
            status="running",
        )
        relative_image_path = f"images/{draft_id}/{image_id}/source{extension}"
        image_path = settings.image_dir / str(draft_id) / str(image_id) / f"source{extension}"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(image_bytes)

        try:
            extracted_text = await ocr_provider.extract_text(
                image_bytes,
                mime_type,
                OCROptions(language=language, model=settings.ocr_model),
            )
        except OCRProviderError as exc:
            storage.update_ocr_draft_image_ocr_result(
                draft_id,
                image_id,
                image_path=relative_image_path,
                extracted_text="",
                status="failed",
                error=str(exc),
            )
            logger.warning("ocr_draft_image_failed draft_id=%s image_id=%s error=%s", draft_id, image_id, exc, exc_info=True)
            continue

        if not extracted_text.strip():
            error = "OCR returned no visible text"
            storage.update_ocr_draft_image_ocr_result(
                draft_id,
                image_id,
                image_path=relative_image_path,
                extracted_text="",
                status="failed",
                error=error,
            )
            logger.warning("ocr_draft_image_failed draft_id=%s image_id=%s error=%s", draft_id, image_id, error)
            continue

        storage.update_ocr_draft_image_ocr_result(
            draft_id,
            image_id,
            image_path=relative_image_path,
            extracted_text=extracted_text,
            status="completed",
            error=None,
        )
        successful_texts.append(extracted_text)
    return successful_texts


def _append_ocr_text(existing_text: str, appended_texts: list[str]) -> str:
    parts = [existing_text.strip()] if existing_text.strip() else []
    parts.extend(text.strip() for text in appended_texts if text.strip())
    return "\n\n".join(parts)
