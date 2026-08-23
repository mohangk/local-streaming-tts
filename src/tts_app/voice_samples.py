from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from tts_app.config import Settings
from tts_app.providers.base import ProviderError, TTSOptions, TTSProvider
from tts_app.segmenter import segment_text


SAMPLE_CACHE_VERSION = "voice-sample-v4"


class VoiceSampleCacheError(RuntimeError):
    pass


class VoiceSampleCache:
    def __init__(self, settings: Settings, provider: TTSProvider):
        self.settings = settings
        self.provider = provider
        self.cache_dir = settings.audio_dir / "voice-samples"
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._locks_guard = asyncio.Lock()
        self._cache_epoch = 0
        self._lifecycle_lock = threading.Lock()

    def cache_path(self, *, text: str, options: TTSOptions, language: str, model: str | None = None) -> Path:
        provider_model = options.model or self.settings.qwen_model
        if model is not None and model != provider_model:
            raise ValueError("cache model must match provider options model")
        key = {
            "version": SAMPLE_CACHE_VERSION,
            "provider": self.provider.name,
            "model": provider_model,
            "language": language,
            "voice": options.voice,
            "speed": options.speed,
            "segment_max_chars": self.settings.segment_max_chars,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "instructions_sha256": hashlib.sha256((options.instructions or "").encode("utf-8")).hexdigest(),
        }
        digest = hashlib.sha256(json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.mp3"

    async def get_or_create(
        self,
        *,
        text: str,
        options: TTSOptions,
        language: str,
        model: str | None = None,
    ) -> tuple[bytes, str]:
        path = self.cache_path(text=text, options=options, language=language, model=model)
        if path.exists():
            return path.read_bytes(), "audio/mpeg"

        lock_key = str(path)
        lock = await self._acquire_lock(lock_key)
        try:
            if path.exists():
                return path.read_bytes(), "audio/mpeg"

            with self._lifecycle_lock:
                cache_epoch = self._cache_epoch
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                temp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid4().hex}")
            mime_type = "audio/mpeg"
            audio = bytearray()
            try:
                with temp_path.open("wb") as output:
                    for text_segment in segment_text(text, max_chars=self.settings.segment_max_chars):
                        segment_audio_bytes = 0
                        async for chunk in self.provider.stream_speech(text_segment, options):
                            mime_type = chunk.mime_type or mime_type
                            segment_audio_bytes += len(chunk.data)
                            audio.extend(chunk.data)
                            output.write(chunk.data)
                        if segment_audio_bytes == 0:
                            raise VoiceSampleCacheError("Provider returned no audio for sample segment")
                with self._lifecycle_lock:
                    if cache_epoch != self._cache_epoch:
                        temp_path.unlink(missing_ok=True)
                        return bytes(audio), mime_type
                    os.replace(temp_path, path)
            except asyncio.CancelledError:
                temp_path.unlink(missing_ok=True)
                raise
            except ProviderError as exc:
                temp_path.unlink(missing_ok=True)
                raise VoiceSampleCacheError(str(exc)) from exc
            except VoiceSampleCacheError:
                temp_path.unlink(missing_ok=True)
                raise
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise

            return bytes(audio), mime_type
        finally:
            await self._release_lock(lock_key, lock)

    def clear(self) -> None:
        with self._lifecycle_lock:
            self._cache_epoch += 1
            try:
                shutil.rmtree(self.cache_dir)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise VoiceSampleCacheError("Unable to clear voice sample cache") from exc

    async def _acquire_lock(self, lock_key: str) -> asyncio.Lock:
        async with self._locks_guard:
            lock, references = self._locks.get(lock_key, (asyncio.Lock(), 0))
            self._locks[lock_key] = (lock, references + 1)
        await lock.acquire()
        return lock

    async def _release_lock(self, lock_key: str, lock: asyncio.Lock) -> None:
        lock.release()
        async with self._locks_guard:
            current = self._locks.get(lock_key)
            if current is None or current[0] is not lock:
                return
            references = current[1] - 1
            if references <= 0:
                self._locks.pop(lock_key, None)
                return
            self._locks[lock_key] = (lock, references)
