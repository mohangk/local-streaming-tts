from __future__ import annotations

from pathlib import Path
from typing import Any

from tts_app.storage import Storage


class ContinuousAudioStitcher:
    def __init__(self, storage: Storage, data_dir: Path):
        self.storage = storage
        self.data_dir = Path(data_dir)

    def artifact_relative_path(self, generation_id: int) -> str:
        return f"audio/{generation_id}/full.mp3"

    def ensure_appended(self, generation_id: int) -> dict[str, Any]:
        self.storage.get_generation(generation_id)
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
        if artifact is None:
            absolute_path.write_bytes(b"")

        appended = expected_next - 1
        with absolute_path.open("ab") as output:
            for segment in segments:
                index = int(segment["segment_index"])
                if index < expected_next:
                    continue
                if index != expected_next:
                    break
                output.write((self.data_dir / segment["file_path"]).read_bytes())
                appended = index
                expected_next += 1

        byte_size = absolute_path.stat().st_size
        detail = self.storage.get_generation(generation_id)
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
