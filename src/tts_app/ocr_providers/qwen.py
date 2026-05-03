from __future__ import annotations

from tts_app.ocr_providers.base import OCROptions, OCRProviderError


class QwenOCRProvider:
    name = "qwen-ocr"

    def __init__(self, api_key: str | None, model: str):
        self.api_key = api_key
        self.model = model

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        if not self.api_key:
            raise OCRProviderError("API key is required for qwen ocr provider")
        raise OCRProviderError("qwen ocr provider is not implemented yet")
