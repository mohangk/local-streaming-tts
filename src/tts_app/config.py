from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    audio_dir: Path
    image_dir: Path
    provider_name: str
    ocr_provider_name: str
    qwen_api_key: str | None
    qwen_model: str
    qwen_ocr_model: str
    qwen_realtime_url: str
    qwen_voice: str
    default_audio_ext: str
    segment_max_chars: int
    max_image_bytes: int
    default_english_voice: str
    default_chinese_voice: str


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("TTS_DATA_DIR", "data")).resolve()
    return Settings(
        data_dir=data_dir,
        db_path=Path(os.environ.get("TTS_DB_PATH", data_dir / "app.db")).resolve(),
        audio_dir=Path(os.environ.get("TTS_AUDIO_DIR", data_dir / "audio")).resolve(),
        image_dir=Path(os.environ.get("TTS_IMAGE_DIR", data_dir / "images")).resolve(),
        provider_name=os.environ.get("TTS_PROVIDER", "fake"),
        ocr_provider_name=os.environ.get("OCR_PROVIDER", "fake"),
        qwen_api_key=os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY"),
        qwen_model=os.environ.get("QWEN_MODEL", "qwen3-tts-flash-realtime"),
        qwen_ocr_model=os.environ.get("QWEN_OCR_MODEL", "qwen-vl-ocr"),
        qwen_realtime_url=os.environ.get("QWEN_REALTIME_URL", "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime"),
        qwen_voice=os.environ.get("QWEN_VOICE", "Jennifer"),
        default_audio_ext=os.environ.get("TTS_AUDIO_EXT", "mp3"),
        segment_max_chars=int(os.environ.get("TTS_SEGMENT_MAX_CHARS", "550")),
        max_image_bytes=int(os.environ.get("TTS_MAX_IMAGE_BYTES", "10485760")),
        default_english_voice=os.environ.get("TTS_DEFAULT_ENGLISH_VOICE", os.environ.get("QWEN_VOICE", "Jennifer")),
        default_chinese_voice=os.environ.get("TTS_DEFAULT_CHINESE_VOICE", "Cherry"),
    )
