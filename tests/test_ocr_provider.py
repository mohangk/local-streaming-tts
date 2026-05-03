import pytest

from tts_app.config import Settings
from tts_app.ocr_providers import qwen
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


class FakeQwenResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class CapturingAsyncClient:
    requests = []
    response = FakeQwenResponse(200, {"choices": [{"message": {"content": " OCR text \n"}}]})

    def __init__(self, *args, **kwargs):
        self.init_args = args
        self.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, *, headers, json):
        self.requests.append({"url": url, "headers": headers, "json": json})
        return self.response


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


@pytest.mark.asyncio
async def test_qwen_ocr_provider_posts_image_data_url_and_returns_text(monkeypatch):
    CapturingAsyncClient.requests = []
    CapturingAsyncClient.response = FakeQwenResponse(
        200, {"choices": [{"message": {"content": " Visible text\n"}}]}
    )
    monkeypatch.setattr(qwen.httpx, "AsyncClient", CapturingAsyncClient)
    provider = QwenOCRProvider(api_key="secret-key", model="qwen-vl-ocr")

    text = await provider.extract_text(b"image-bytes", "image/png", OCROptions(language="zh"))

    assert text == "Visible text"
    request = CapturingAsyncClient.requests[0]
    assert request["url"] == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer secret-key"
    assert request["headers"]["Content-Type"] == "application/json"
    assert request["json"]["model"] == "qwen-vl-ocr"
    content = request["json"]["messages"][0]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"] == "data:image/png;base64,aW1hZ2UtYnl0ZXM="
    assert content[1]["type"] == "text"
    assert "preserve only visible text" in content[1]["text"].lower()
    assert "do not infer" in content[1]["text"].lower()


@pytest.mark.asyncio
async def test_qwen_ocr_provider_uses_options_model_override(monkeypatch):
    CapturingAsyncClient.requests = []
    CapturingAsyncClient.response = FakeQwenResponse(
        200, {"choices": [{"message": {"content": "text"}}]}
    )
    monkeypatch.setattr(qwen.httpx, "AsyncClient", CapturingAsyncClient)
    provider = QwenOCRProvider(api_key="secret-key", model="default-model")

    await provider.extract_text(b"image", "image/jpeg", OCROptions(language="en", model="override-model"))

    assert CapturingAsyncClient.requests[0]["json"]["model"] == "override-model"


@pytest.mark.asyncio
async def test_qwen_ocr_provider_maps_non_2xx_to_provider_error(monkeypatch):
    CapturingAsyncClient.requests = []
    CapturingAsyncClient.response = FakeQwenResponse(401, {"error": {"message": "unauthorized"}})
    monkeypatch.setattr(qwen.httpx, "AsyncClient", CapturingAsyncClient)
    provider = QwenOCRProvider(api_key="secret-key", model="qwen-vl-ocr")

    with pytest.raises(OCRProviderError, match="qwen ocr provider request failed.*401.*unauthorized"):
        await provider.extract_text(b"image", "image/png", OCROptions(language="en"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"choices": [{"message": {"content": "  "}}]},
        {"choices": []},
        {"not_choices": []},
    ],
)
async def test_qwen_ocr_provider_maps_empty_or_malformed_response_to_provider_error(monkeypatch, payload):
    CapturingAsyncClient.requests = []
    CapturingAsyncClient.response = FakeQwenResponse(200, payload)
    monkeypatch.setattr(qwen.httpx, "AsyncClient", CapturingAsyncClient)
    provider = QwenOCRProvider(api_key="secret-key", model="qwen-vl-ocr")

    with pytest.raises(OCRProviderError):
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
