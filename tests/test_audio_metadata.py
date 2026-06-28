from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tinytag import TinyTagException

import tts_app.audio_metadata as audio_metadata
from tts_app.audio_metadata import estimate_audio_duration_ms


def _mp3_frame(*, bitrate_index: int = 3, sample_rate_index: int = 1) -> bytes:
    header = 0
    header |= 0x7FF << 21
    header |= 0b10 << 19  # MPEG 2
    header |= 0b01 << 17  # Layer III
    header |= 0b1 << 16
    header |= bitrate_index << 12
    header |= sample_rate_index << 10
    frame_length = 72
    return header.to_bytes(4, "big") + bytes(frame_length - 4)


def test_estimate_audio_duration_ms_sums_mp3_frames(tmp_path):
    path = tmp_path / "sample.mp3"
    path.write_bytes(_mp3_frame() * 10)

    assert estimate_audio_duration_ms(path, "audio/mpeg") > 0


def test_estimate_audio_duration_ms_rounds_tinytag_seconds(monkeypatch, tmp_path):
    path = tmp_path / "sample.mp3"
    path.write_bytes(b"audio")

    monkeypatch.setattr(audio_metadata.TinyTag, "get", lambda received_path: SimpleNamespace(duration=1.2345))

    assert estimate_audio_duration_ms(path, "audio/mpeg") == 1234


def test_estimate_audio_duration_ms_ignores_tinytag_errors(monkeypatch, tmp_path):
    path = tmp_path / "bad.mp3"
    path.write_bytes(b"not an mp3")

    def raise_tinytag_error(received_path):
        raise TinyTagException("bad file")

    monkeypatch.setattr(audio_metadata.TinyTag, "get", raise_tinytag_error)

    assert estimate_audio_duration_ms(path, "audio/mpeg") is None


def test_estimate_audio_duration_ms_skips_id3v2_header(tmp_path):
    id3_header = b"ID3\x03\x00\x00\x00\x00\x00\x05abcde"
    path = tmp_path / "sample.mp3"
    path.write_bytes(id3_header + _mp3_frame())

    assert estimate_audio_duration_ms(path, "audio/mpeg") > 0


def test_estimate_audio_duration_ms_ignores_unparseable_audio(tmp_path):
    path = tmp_path / "bad.mp3"
    path.write_bytes(b"not an mp3")

    assert estimate_audio_duration_ms(path, "audio/mpeg") is None
    assert estimate_audio_duration_ms(Path("missing.wav"), "audio/wav") is None
