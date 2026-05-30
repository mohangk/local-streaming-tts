from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from tts_app.storage import Storage


class ContinuousAudioError(RuntimeError):
    pass


class ContinuousAudioStitcher:
    def __init__(self, storage: Storage, audio_dir: Path):
        self.storage = storage
        self.audio_dir = Path(audio_dir)
        self.data_dir = self.audio_dir.parent
        self._locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def artifact_relative_path(self, generation_id: int) -> str:
        return f"{self.audio_dir.name}/{generation_id}/full.mp3"

    def ensure_appended(self, generation_id: int) -> dict[str, Any]:
        with self._lock_for(generation_id):
            return self._ensure_appended_locked(generation_id)

    def _lock_for(self, generation_id: int) -> threading.Lock:
        with self._locks_guard:
            if generation_id not in self._locks:
                self._locks[generation_id] = threading.Lock()
            return self._locks[generation_id]

    def _ensure_appended_locked(self, generation_id: int) -> dict[str, Any]:
        detail = self.storage.get_generation(generation_id)
        segments = self.storage.list_completed_audio_segments_for_stitching(generation_id)
        expected_next = 0
        try:
            artifact = self.storage.get_continuous_audio_artifact(generation_id)
            expected_next = int(artifact["appended_through_segment_index"]) + 1
        except KeyError:
            artifact = None

        relative_path = self.artifact_relative_path(generation_id)
        absolute_path = self.data_dir / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        should_rebuild = artifact is None or self._should_rebuild_artifact(artifact, absolute_path)
        if should_rebuild:
            expected_next = 0
            appended = self._rebuild_artifact(generation_id, relative_path, absolute_path, segments)
        else:
            appended = self._append_artifact(generation_id, relative_path, absolute_path, segments, expected_next)

        byte_size = absolute_path.stat().st_size
        status = (
            "completed"
            if appended + 1 >= len(detail["text_segments"]) and detail["generation"]["status"] == "completed"
            else "building"
        )
        self.storage.upsert_continuous_audio_artifact(
            generation_id,
            file_path=relative_path,
            mime_type="audio/mpeg",
            status=status,
            appended_through_segment_index=appended,
            byte_size=byte_size,
            error=None,
        )
        return self.storage.get_continuous_audio_artifact(generation_id)

    def _append_artifact(
        self,
        generation_id: int,
        relative_path: str,
        absolute_path: Path,
        segments: list[dict[str, Any]],
        expected_next: int,
    ) -> int:
        with absolute_path.open("ab") as output:
            return self._write_available_segments(
                output,
                generation_id,
                relative_path,
                absolute_path,
                segments,
                expected_next,
            )

    def _rebuild_artifact(
        self,
        generation_id: int,
        relative_path: str,
        absolute_path: Path,
        segments: list[dict[str, Any]],
    ) -> int:
        temp_path = absolute_path.with_name(f"{absolute_path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
        try:
            with temp_path.open("wb") as output:
                appended = self._write_available_segments(
                    output,
                    generation_id,
                    relative_path,
                    absolute_path,
                    segments,
                    0,
                )
            os.replace(temp_path, absolute_path)
            return appended
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _write_available_segments(
        self,
        output,
        generation_id: int,
        relative_path: str,
        absolute_path: Path,
        segments: list[dict[str, Any]],
        expected_next: int,
    ) -> int:
        appended = expected_next - 1
        for segment in segments:
            index = int(segment["segment_index"])
            if index < expected_next:
                continue
            if index != expected_next:
                break
            source_path = self.data_dir / segment["file_path"]
            if not source_path.exists():
                self._mark_failed(generation_id, relative_path, absolute_path, "audio segment file missing")
                raise ContinuousAudioError("audio segment file missing")
            output.write(source_path.read_bytes())
            appended = index
            expected_next += 1
        return appended

    def _should_rebuild_artifact(self, artifact: dict[str, Any], absolute_path: Path) -> bool:
        if artifact["status"] == "failed":
            return True
        if not absolute_path.exists():
            return True
        return absolute_path.stat().st_size != int(artifact["byte_size"])

    def _mark_failed(self, generation_id: int, relative_path: str, absolute_path: Path, error: str) -> None:
        self.storage.upsert_continuous_audio_artifact(
            generation_id,
            file_path=relative_path,
            mime_type="audio/mpeg",
            status="failed",
            appended_through_segment_index=-1,
            byte_size=absolute_path.stat().st_size if absolute_path.exists() else 0,
            error=error,
        )
