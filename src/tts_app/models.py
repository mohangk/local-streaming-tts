from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SourceType = Literal["text", "url", "image"]
Language = Literal["en", "zh"]
Status = Literal["queued", "running", "completed", "failed"]


@dataclass(frozen=True)
class TextSegment:
    id: int
    generation_id: int
    segment_index: int
    text: str
    status: str


@dataclass(frozen=True)
class AudioSegment:
    id: int
    generation_id: int
    text_segment_id: int
    segment_index: int
    file_path: str
    mime_type: str
    duration_ms: int | None
    byte_size: int
    status: str
    error: str | None
