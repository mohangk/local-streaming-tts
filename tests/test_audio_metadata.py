from __future__ import annotations

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


def test_estimate_audio_duration_ms_sums_mp3_frames():
    data = _mp3_frame() * 10

    assert estimate_audio_duration_ms(data, "audio/mpeg") == 240


def test_estimate_audio_duration_ms_skips_id3v2_header():
    id3_header = b"ID3\x03\x00\x00\x00\x00\x00\x05abcde"

    assert estimate_audio_duration_ms(id3_header + _mp3_frame(), "audio/mpeg") == 24


def test_estimate_audio_duration_ms_ignores_unparseable_audio():
    assert estimate_audio_duration_ms(b"not an mp3", "audio/mpeg") is None
    assert estimate_audio_duration_ms(_mp3_frame(), "audio/wav") is None
