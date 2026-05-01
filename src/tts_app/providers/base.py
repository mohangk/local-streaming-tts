from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TTSOptions:
    voice: str
    audio_format: str = "mp3"
    language: str = "Auto"
    sample_rate: int = 24000
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0


@dataclass(frozen=True)
class AudioChunk:
    data: bytes
    mime_type: str
    extension: str


class TTSProvider(Protocol):
    name: str

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        ...
