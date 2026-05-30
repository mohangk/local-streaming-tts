from __future__ import annotations

from tts_app.ocr_providers.base import OCROptions


class FakeOCRProvider:
    name = "fake-ocr"

    async def extract_text(self, image: bytes, mime_type: str, options: OCROptions) -> str:
        return "Fake OCR text. 你好 ni hao." if options.language == "zh" else "Fake OCR text."
