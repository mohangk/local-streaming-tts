import pytest

from tts_app.config import Settings
from tts_app.ocr_providers.base import OCROptions, OCRProviderError
from tts_app.ocr_providers.fake import FakeOCRProvider
from tts_app.ocr_providers.qwen import QwenOCRProvider
from tts_app.ocr_providers.registry import get_ocr_provider


def make_settings(ocr_provider_name: str = "fake") -> Settings:
    return Settings(
        data_dir="data",
        db_path="data/app.db",
        audio_dir="data/audio",
        image_dir="data/images",
        provider_name="fake",
        ocr_provider_name=ocr_provider_name,
        qwen_api_key="test-key",
        qwen_model="qwen3-tts-flash-realtime",
        qwen_ocr_model="qwen-vl-ocr",
        qwen_realtime_url="wss://example.test/realtime",
        qwen_voice="Jennifer",
        default_audio_ext="mp3",
        segment_max_chars=550,
        max_image_bytes=10485760,
        default_english_voice="Jennifer",
        default_chinese_voice="Cherry",
    )


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


def test_get_ocr_provider_returns_fake_by_default():
    provider = get_ocr_provider(make_settings())

    assert isinstance(provider, FakeOCRProvider)


def test_get_ocr_provider_returns_qwen_for_explicit_qwen():
    provider = get_ocr_provider(make_settings(ocr_provider_name="qwen"))

    assert isinstance(provider, QwenOCRProvider)


def test_get_ocr_provider_rejects_unknown_provider_name():
    with pytest.raises(ValueError, match="unknown-provider"):
        get_ocr_provider(make_settings(ocr_provider_name="unknown-provider"))
