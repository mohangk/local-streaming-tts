from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from tts_app.config import load_settings
from tts_app.audio_metadata import estimate_audio_duration_ms
from tts_app.storage import Storage


@dataclass(frozen=True)
class AudioDurationBackfillResult:
    scanned: int
    updated: int
    skipped_missing_file: int
    skipped_unparseable: int


def backfill_audio_segment_durations(storage: Storage, data_dir: Path) -> AudioDurationBackfillResult:
    scanned = 0
    updated = 0
    skipped_missing_file = 0
    skipped_unparseable = 0

    for generation in storage.list_generations():
        detail = storage.get_generation(int(generation["id"]))
        for audio_segment in detail["audio_segments"]:
            if audio_segment["duration_ms"] is not None or audio_segment["status"] != "completed":
                continue
            scanned += 1
            path = data_dir / audio_segment["file_path"]
            if not path.exists():
                skipped_missing_file += 1
                continue
            duration_ms = estimate_audio_duration_ms(path, audio_segment["mime_type"])
            if duration_ms is None:
                skipped_unparseable += 1
                continue
            storage.update_audio_segment_duration(int(audio_segment["id"]), duration_ms)
            updated += 1

    return AudioDurationBackfillResult(
        scanned=scanned,
        updated=updated,
        skipped_missing_file=skipped_missing_file,
        skipped_unparseable=skipped_unparseable,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing audio segment durations from cached audio files.")
    parser.parse_args()

    settings = load_settings()
    storage = Storage(settings.db_path)
    storage.init_schema()
    result = backfill_audio_segment_durations(storage, settings.data_dir)
    print(
        "audio duration backfill: "
        f"scanned={result.scanned} "
        f"updated={result.updated} "
        f"missing_file={result.skipped_missing_file} "
        f"unparseable={result.skipped_unparseable}"
    )


if __name__ == "__main__":
    main()
