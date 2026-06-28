from __future__ import annotations

from pathlib import Path

from tinytag import TinyTag, TinyTagException


def estimate_audio_duration_ms(path: Path, mime_type: str) -> int | None:
    if mime_type not in {"audio/mpeg", "audio/mp3", "audio/x-mpeg"}:
        return None

    try:
        duration = TinyTag.get(path).duration
    except (OSError, TinyTagException):
        return None
    if duration is None:
        return None
    return max(0, round(duration * 1000))
