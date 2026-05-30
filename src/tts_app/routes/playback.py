from __future__ import annotations

import anyio
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from tts_app.config import Settings
from tts_app.continuous_audio import ContinuousAudioError
from tts_app.generation import GenerationService
from tts_app.storage import Storage


def create_playback_router(*, settings: Settings, storage: Storage, service: GenerationService) -> APIRouter:
    router = APIRouter()

    @router.get("/api/audio/{generation_id}/{audio_segment_id}")
    async def get_audio(generation_id: int, audio_segment_id: int):
        try:
            audio = storage.get_audio_segment(generation_id, audio_segment_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="audio not found") from exc
        path = settings.data_dir / audio["file_path"]
        if not path.exists():
            raise HTTPException(status_code=404, detail="audio file not found")
        return FileResponse(path, media_type=audio["mime_type"], stat_result=path.stat())

    @router.get("/api/generations/{generation_id}/continuous-audio")
    async def get_continuous_audio(generation_id: int, start_segment: int = 0):
        if start_segment < 0:
            raise HTTPException(status_code=422, detail="start_segment must be non-negative")
        try:
            detail = await anyio.to_thread.run_sync(storage.get_generation, generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc
        if start_segment >= len(detail["text_segments"]):
            raise HTTPException(status_code=416, detail="start segment outside generation")

        try:
            artifact = await anyio.to_thread.run_sync(service.continuous_audio.ensure_appended, generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc
        except ContinuousAudioError as exc:
            raise HTTPException(status_code=409, detail="continuous audio artifact unavailable") from exc
        appended_through = int(artifact["appended_through_segment_index"])
        if appended_through < start_segment:
            raise HTTPException(status_code=409, detail="start segment audio is not ready")

        completed_segments = await anyio.to_thread.run_sync(
            storage.list_completed_audio_segments_for_stitching,
            generation_id,
        )
        try:
            start_offset = _continuous_start_offset(completed_segments, start_segment, appended_through)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail="start segment audio is not ready") from exc

        async def stream_file():
            position = start_offset
            while True:
                try:
                    artifact, chunk, generation_status = await anyio.to_thread.run_sync(
                        _read_continuous_audio_chunk,
                        settings,
                        storage,
                        service,
                        generation_id,
                        position,
                    )
                except ContinuousAudioError:
                    break
                if chunk:
                    position += len(chunk)
                    yield chunk
                    continue

                if artifact["status"] == "completed" or generation_status in {"completed", "failed"}:
                    break
                await anyio.sleep(0.2)

        return StreamingResponse(
            stream_file(),
            media_type=artifact["mime_type"],
            headers={"Cache-Control": "no-store"},
        )

    return router


def _continuous_start_offset(
    completed_segments: list[dict],
    start_segment: int,
    appended_through: int,
) -> int:
    completed_by_index = {
        int(segment["segment_index"]): segment
        for segment in completed_segments
        if int(segment["segment_index"]) <= appended_through
    }
    for index in range(appended_through + 1):
        if index not in completed_by_index:
            raise KeyError(index)
    return sum(int(completed_by_index[index]["byte_size"]) for index in range(start_segment))


def _read_continuous_audio_chunk(
    settings: Settings,
    storage: Storage,
    service: GenerationService,
    generation_id: int,
    position: int,
) -> tuple[dict, bytes, str]:
    artifact = service.continuous_audio.ensure_appended(generation_id)
    path = settings.data_dir / artifact["file_path"]
    chunk = b""
    if path.exists() and position < path.stat().st_size:
        with path.open("rb") as audio_file:
            audio_file.seek(position)
            chunk = audio_file.read(64 * 1024)
    detail = storage.get_generation(generation_id)
    return artifact, chunk, detail["generation"]["status"]
