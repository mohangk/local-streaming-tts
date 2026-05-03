from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class OCRProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class OCROptions:
    language: str
    model: str | None = None


class OCRProvider(Protocol):
    name: str

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        raise NotImplementedError
