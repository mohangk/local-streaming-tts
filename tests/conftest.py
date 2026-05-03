from __future__ import annotations

import pytest

from tts_app.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        db_path=data_dir / "app.db",
        audio_dir=data_dir / "audio",
        image_dir=data_dir / "images",
        provider_name="fake",
        ocr_provider_name="fake",
        qwen_api_key=None,
        qwen_model="qwen3-tts-flash-realtime",
        ocr_model="qwen-vl-ocr",
        qwen_realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        default_audio_ext="mp3",
        segment_max_chars=80,
        max_image_bytes=10_485_760,
        default_english_voice="Jennifer",
        default_chinese_voice="Cherry",
    )
