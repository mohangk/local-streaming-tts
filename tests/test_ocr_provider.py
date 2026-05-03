import pytest

from tts_app.ocr_providers.base import OCROptions, OCRProviderError
from tts_app.ocr_providers.fake import FakeOCRProvider
from tts_app.ocr_providers.qwen import QwenOCRProvider


@pytest.mark.asyncio
async def test_fake_ocr_provider_returns_deterministic_text():
    provider = FakeOCRProvider()

    text = await provider.extract_text(b"image", "image/png", OCROptions(language="zh"))

    assert "Fake OCR text" in text


@pytest.mark.asyncio
async def test_qwen_ocr_provider_requires_api_key():
    provider = QwenOCRProvider(api_key=None, model="qwen-vl-ocr")

    with pytest.raises(OCRProviderError, match="API key is required"):
        await provider.extract_text(b"image", "image/png", OCROptions(language="en"))
