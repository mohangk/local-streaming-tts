from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from tts_app.providers.options import InstructionSampleCapabilities, SelectOption


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class TTSOptions:
    voice: str
    model: str | None = None
    audio_format: str = "mp3"
    language: str = "Auto"
    sample_rate: int = 24000
    speed: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    instructions: str | None = None


@dataclass(frozen=True)
class AudioChunk:
    data: bytes
    mime_type: str
    extension: str


class TTSProvider(Protocol):
    name: str
    english_voices: tuple[SelectOption, ...]
    chinese_voices: tuple[SelectOption, ...]
    instruction_sample_capabilities: InstructionSampleCapabilities | None

    def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        ...
