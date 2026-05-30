from __future__ import annotations

from pathlib import Path

import pytest

from tts_app.continuous_audio import ContinuousAudioError, ContinuousAudioStitcher
from tts_app.storage import Storage


def _generation_with_audio(storage: Storage, data_dir: Path, count: int = 3) -> int:
    generation_id = storage.create_generation("text", "Manual text", None, "A B C", "fake", "Test", {})
    segment_ids = storage.create_text_segments(generation_id, ["A", "B", "C"][:count])
    audio_dir = data_dir / "audio" / str(generation_id)
    audio_dir.mkdir(parents=True)
    for index, text_segment_id in enumerate(segment_ids):
        path = audio_dir / f"segment-{index + 1:04d}.mp3"
        path.write_bytes(f"SEG{index}".encode())
        storage.record_audio_segment(
            generation_id,
            text_segment_id,
            index,
            str(path.relative_to(data_dir)),
            "audio/mpeg",
            None,
            path.stat().st_size,
            "completed",
            None,
        )
    return generation_id


def test_stitcher_appends_completed_segments_in_order(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = _generation_with_audio(storage, test_settings.data_dir)
    stitcher = ContinuousAudioStitcher(storage, test_settings.data_dir)

    artifact = stitcher.ensure_appended(generation_id)

    full_path = test_settings.data_dir / artifact["file_path"]
    assert full_path.read_bytes() == b"SEG0SEG1SEG2"
    assert artifact["appended_through_segment_index"] == 2
    assert artifact["byte_size"] == len(b"SEG0SEG1SEG2")


def test_stitcher_is_idempotent(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = _generation_with_audio(storage, test_settings.data_dir)
    stitcher = ContinuousAudioStitcher(storage, test_settings.data_dir)

    stitcher.ensure_appended(generation_id)
    stitcher.ensure_appended(generation_id)

    artifact = storage.get_continuous_audio_artifact(generation_id)
    assert (test_settings.data_dir / artifact["file_path"]).read_bytes() == b"SEG0SEG1SEG2"


def test_stitcher_repairs_missing_artifact_file(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = _generation_with_audio(storage, test_settings.data_dir)
    stitcher = ContinuousAudioStitcher(storage, test_settings.data_dir)
    artifact = stitcher.ensure_appended(generation_id)
    full_path = test_settings.data_dir / artifact["file_path"]
    full_path.unlink()

    repaired = stitcher.ensure_appended(generation_id)

    assert repaired["appended_through_segment_index"] == 2
    assert repaired["byte_size"] == len(b"SEG0SEG1SEG2")
    assert full_path.read_bytes() == b"SEG0SEG1SEG2"


def test_stitcher_repairs_truncated_artifact_file(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = _generation_with_audio(storage, test_settings.data_dir)
    stitcher = ContinuousAudioStitcher(storage, test_settings.data_dir)
    artifact = stitcher.ensure_appended(generation_id)
    full_path = test_settings.data_dir / artifact["file_path"]
    full_path.write_bytes(b"SEG0")

    repaired = stitcher.ensure_appended(generation_id)

    assert repaired["appended_through_segment_index"] == 2
    assert repaired["byte_size"] == len(b"SEG0SEG1SEG2")
    assert full_path.read_bytes() == b"SEG0SEG1SEG2"


def test_stitcher_marks_artifact_failed_when_source_segment_file_is_missing(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = _generation_with_audio(storage, test_settings.data_dir)
    missing_path = test_settings.data_dir / "audio" / str(generation_id) / "segment-0002.mp3"
    missing_path.unlink()
    stitcher = ContinuousAudioStitcher(storage, test_settings.data_dir)

    with pytest.raises(ContinuousAudioError, match="audio segment file missing"):
        stitcher.ensure_appended(generation_id)

    artifact = storage.get_continuous_audio_artifact(generation_id)
    assert artifact["status"] == "failed"
    assert artifact["error"] == "audio segment file missing"


def test_stitcher_stops_at_missing_segment_gap(test_settings):
    storage = Storage(test_settings.db_path)
    storage.init_schema()
    generation_id = storage.create_generation("text", "Manual text", None, "A B C", "fake", "Test", {})
    segment_ids = storage.create_text_segments(generation_id, ["A", "B", "C"])
    audio_dir = test_settings.data_dir / "audio" / str(generation_id)
    audio_dir.mkdir(parents=True)
    for index in (0, 2):
        path = audio_dir / f"segment-{index + 1:04d}.mp3"
        path.write_bytes(f"SEG{index}".encode())
        storage.record_audio_segment(
            generation_id,
            segment_ids[index],
            index,
            str(path.relative_to(test_settings.data_dir)),
            "audio/mpeg",
            None,
            path.stat().st_size,
            "completed",
            None,
        )
    stitcher = ContinuousAudioStitcher(storage, test_settings.data_dir)

    artifact = stitcher.ensure_appended(generation_id)

    assert artifact["appended_through_segment_index"] == 0
    assert (test_settings.data_dir / artifact["file_path"]).read_bytes() == b"SEG0"
