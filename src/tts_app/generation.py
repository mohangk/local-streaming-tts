from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from tts_app.events import EventBroker
from tts_app.providers.base import TTSOptions, TTSProvider
from tts_app.segmenter import segment_text
from tts_app.storage import Storage

logger = logging.getLogger(__name__)


class GenerationService:
    def __init__(
        self,
        storage: Storage,
        provider: TTSProvider,
        broker: EventBroker,
        audio_dir: Path,
        segment_max_chars: int,
    ):
        self.storage = storage
        self.provider = provider
        self.broker = broker
        self.audio_dir = Path(audio_dir)
        self.segment_max_chars = segment_max_chars

    async def create_from_text(
        self,
        text: str,
        title: str,
        source_type: str = "text",
        url: str | None = None,
        voice: str = "Test",
        settings: dict[str, Any] | None = None,
    ) -> int:
        segments = segment_text(text, max_chars=self.segment_max_chars)
        generation_id = self.storage.create_generation(
            source_type=source_type,
            title=title,
            url=url,
            full_text=text,
            provider=self.provider.name,
            voice=voice,
            settings=settings or {},
        )
        self.storage.create_text_segments(generation_id, segments)
        logger.info(
            "generation_created generation_id=%s source_type=%s provider=%s voice=%s segment_count=%s text_chars=%s",
            generation_id,
            source_type,
            self.provider.name,
            voice,
            len(segments),
            len(text),
        )
        await self.broker.publish(generation_id, {"type": "generation_created", "generation_id": generation_id})
        return generation_id

    async def run_generation(
        self,
        generation_id: int,
        voice: str = "Test",
        speed: float = 1.0,
        language: str = "Auto",
    ) -> None:
        detail = self.storage.get_generation(generation_id)
        self.storage.update_generation_status(generation_id, "running")
        logger.info(
            "generation_started generation_id=%s provider=%s voice=%s speed=%s segment_count=%s",
            generation_id,
            self.provider.name,
            voice,
            speed,
            len(detail["text_segments"]),
        )
        await self.broker.publish(generation_id, {"type": "generation_started", "generation_id": generation_id})

        try:
            for text_segment in detail["text_segments"]:
                await self._run_segment(
                    generation_id,
                    text_segment,
                    TTSOptions(voice=voice, speed=speed, language=language),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.storage.update_generation_status(generation_id, "failed", str(exc))
            logger.exception("generation_failed generation_id=%s error=%s", generation_id, exc)
            await self.broker.publish(
                generation_id,
                {"type": "generation_failed", "generation_id": generation_id, "error": str(exc)},
            )
            return

        self.storage.update_generation_status(generation_id, "completed")
        logger.info("generation_completed generation_id=%s", generation_id)
        await self.broker.publish(generation_id, {"type": "generation_completed", "generation_id": generation_id})

    async def _run_segment(self, generation_id: int, text_segment: dict[str, Any], options: TTSOptions) -> None:
        segment_index = int(text_segment["segment_index"])
        self.storage.update_text_segment_status(int(text_segment["id"]), "running")

        try:
            logger.info(
                "segment_started generation_id=%s segment_index=%s text_segment_id=%s text_chars=%s",
                generation_id,
                segment_index,
                text_segment["id"],
                len(text_segment["text"]),
            )
            await self.broker.publish(
                generation_id,
                {"type": "segment_started", "segment_index": segment_index, "text_segment_id": text_segment["id"]},
            )
            data_parts: list[bytes] = []
            mime_type = "audio/mpeg"
            extension = "mp3"
            async for chunk in self.provider.stream_speech(text_segment["text"], options):
                data_parts.append(chunk.data)
                mime_type = chunk.mime_type
                extension = chunk.extension

            data = b"".join(data_parts)
            filename = f"segment-{segment_index + 1:04d}.{extension}"
            absolute_path = self.audio_dir / str(generation_id) / filename
            relative_path = absolute_path.relative_to(self.audio_dir.parent)
            absolute_path.parent.mkdir(parents=True, exist_ok=True)
            absolute_path.write_bytes(data)

            self.storage.update_text_segment_status(int(text_segment["id"]), "completed")
            audio_id = self.storage.record_audio_segment(
                generation_id=generation_id,
                text_segment_id=int(text_segment["id"]),
                segment_index=segment_index,
                file_path=str(relative_path),
                mime_type=mime_type,
                duration_ms=None,
                byte_size=len(data),
                status="completed",
                error=None,
            )
            logger.info(
                "segment_completed generation_id=%s segment_index=%s text_segment_id=%s audio_segment_id=%s byte_size=%s",
                generation_id,
                segment_index,
                text_segment["id"],
                audio_id,
                len(data),
            )
            await self.broker.publish(
                generation_id,
                {
                    "type": "segment_completed",
                    "generation_id": generation_id,
                    "segment_index": segment_index,
                    "text_segment_id": text_segment["id"],
                    "audio_segment_id": audio_id,
                    "audio_url": f"/api/audio/{generation_id}/{audio_id}",
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.storage.update_text_segment_status(int(text_segment["id"]), "failed")
            logger.exception(
                "segment_failed generation_id=%s segment_index=%s text_segment_id=%s error=%s",
                generation_id,
                segment_index,
                text_segment["id"],
                exc,
            )
            raise
