from __future__ import annotations


_BITRATE_KBPS: dict[tuple[str, int], list[int | None]] = {
    ("1", 1): [None, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448, None],
    ("1", 2): [None, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, None],
    ("1", 3): [None, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, None],
    ("2", 1): [None, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256, None],
    ("2", 2): [None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, None],
    ("2", 3): [None, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, None],
}

_SAMPLE_RATES: dict[str, list[int | None]] = {
    "1": [44100, 48000, 32000, None],
    "2": [22050, 24000, 16000, None],
    "2.5": [11025, 12000, 8000, None],
}


def estimate_audio_duration_ms(data: bytes, mime_type: str) -> int | None:
    if mime_type not in {"audio/mpeg", "audio/mp3", "audio/x-mpeg"}:
        return None

    duration_seconds = _estimate_mp3_duration_seconds(data)
    if duration_seconds is None:
        return None
    return max(0, round(duration_seconds * 1000))


def _estimate_mp3_duration_seconds(data: bytes) -> float | None:
    offset = _skip_id3v2(data)
    duration = 0.0
    frames = 0

    while offset + 4 <= len(data):
        header = int.from_bytes(data[offset : offset + 4], "big")
        frame = _parse_mp3_frame_header(header)
        if frame is None:
            offset += 1
            continue

        frame_length, frame_duration = frame
        if frame_length <= 0:
            offset += 1
            continue

        duration += frame_duration
        frames += 1
        offset += frame_length

    if frames == 0:
        return None
    return duration


def _skip_id3v2(data: bytes) -> int:
    if len(data) < 10 or data[:3] != b"ID3":
        return 0

    tag_size = 0
    for byte in data[6:10]:
        tag_size = (tag_size << 7) | (byte & 0x7F)
    footer_size = 10 if data[5] & 0x10 else 0
    return min(len(data), 10 + tag_size + footer_size)


def _parse_mp3_frame_header(header: int) -> tuple[int, float] | None:
    if (header & 0xFFE00000) != 0xFFE00000:
        return None

    version_bits = (header >> 19) & 0x3
    layer_bits = (header >> 17) & 0x3
    bitrate_index = (header >> 12) & 0xF
    sample_rate_index = (header >> 10) & 0x3
    padding = (header >> 9) & 0x1

    version = {0: "2.5", 2: "2", 3: "1"}.get(version_bits)
    layer = {1: 3, 2: 2, 3: 1}.get(layer_bits)
    if version is None or layer is None:
        return None

    bitrate_kbps = _BITRATE_KBPS[("1" if version == "1" else "2", layer)][bitrate_index]
    sample_rate = _SAMPLE_RATES[version][sample_rate_index]
    if bitrate_kbps is None or sample_rate is None:
        return None

    bitrate = bitrate_kbps * 1000
    if layer == 1:
        frame_length = int(((12 * bitrate) / sample_rate + padding) * 4)
        samples_per_frame = 384
    elif layer == 3 and version != "1":
        frame_length = int((72 * bitrate) / sample_rate + padding)
        samples_per_frame = 576
    else:
        frame_length = int((144 * bitrate) / sample_rate + padding)
        samples_per_frame = 1152

    return frame_length, samples_per_frame / sample_rate
