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
            detail = storage.get_generation(generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc
        if start_segment >= len(detail["text_segments"]):
            raise HTTPException(status_code=416, detail="start segment outside generation")

        try:
            artifact = service.continuous_audio.ensure_appended(generation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="generation not found") from exc
        except ContinuousAudioError as exc:
            raise HTTPException(status_code=409, detail="continuous audio artifact unavailable") from exc
        appended_through = int(artifact["appended_through_segment_index"])
        if appended_through < start_segment:
            raise HTTPException(status_code=409, detail="start segment audio is not ready")

        completed_segments = storage.list_completed_audio_segments_for_stitching(generation_id)
        completed_by_index = {int(segment["segment_index"]): segment for segment in completed_segments}
        try:
            start_offset = sum(int(completed_by_index[index]["byte_size"]) for index in range(start_segment))
        except KeyError as exc:
            raise HTTPException(status_code=409, detail="start segment audio is not ready") from exc

        async def stream_file():
            position = start_offset
            while True:
                try:
                    artifact = service.continuous_audio.ensure_appended(generation_id)
                except ContinuousAudioError:
                    break
                path = settings.data_dir / artifact["file_path"]
                if path.exists():
                    size = path.stat().st_size
                    if position < size:
                        with path.open("rb") as audio_file:
                            audio_file.seek(position)
                            while chunk := audio_file.read(64 * 1024):
                                position += len(chunk)
                                yield chunk
                        continue

                detail = storage.get_generation(generation_id)
                if artifact["status"] == "completed" or detail["generation"]["status"] in {"completed", "failed"}:
                    break
                await anyio.sleep(0.2)

        return StreamingResponse(
            stream_file(),
            media_type=artifact["mime_type"],
            headers={"Cache-Control": "no-store"},
        )

    return router
