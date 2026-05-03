from tts_app.config import Settings
from tts_app.ocr_providers.fake import FakeOCRProvider
from tts_app.ocr_providers.qwen import QwenOCRProvider


def get_ocr_provider(settings: Settings):
    if settings.ocr_provider_name == "fake":
        return FakeOCRProvider()
    if settings.ocr_provider_name == "qwen":
        return QwenOCRProvider(api_key=settings.qwen_api_key, model=settings.qwen_ocr_model)
    raise ValueError(f"Unknown OCR provider: {settings.ocr_provider_name}")
