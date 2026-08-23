from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import urlencode

import websockets

from tts_app.providers.base import AudioChunk, ProviderError, TTSOptions
from tts_app.providers.options import (
    QWEN_CHINESE_VOICES,
    QWEN_ENGLISH_VOICES,
    QWEN_INSTRUCTION_SAMPLE_CAPABILITIES,
    SPEED_OPTIONS,
)

QwenConnect = Callable[..., Awaitable[object]]


class QwenTTSProvider:
    name = "qwen"
    english_voices = QWEN_ENGLISH_VOICES
    chinese_voices = QWEN_CHINESE_VOICES
    speed_options = SPEED_OPTIONS
    instruction_sample_capabilities = QWEN_INSTRUCTION_SAMPLE_CAPABILITIES

    def __init__(
        self,
        api_key: str | None,
        model: str,
        realtime_url: str,
        connect: QwenConnect | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.realtime_url = realtime_url
        self.connect = connect or websockets.connect

    async def stream_speech(self, text: str, options: TTSOptions) -> AsyncIterator[AudioChunk]:
        if not self.api_key:
            raise ProviderError("API key is required for qwen provider")
        url = self._build_url(options.model)
        websocket = None
        primary_error: BaseException | None = None
        response_completed = False
        audio_received = False
        try:
            websocket = await self.connect(url, additional_headers={"Authorization": f"Bearer {self.api_key}"})
            session = {
                "voice": options.voice,
                "mode": "commit",
                "language_type": options.language,
                "response_format": options.audio_format,
                "sample_rate": options.sample_rate,
                "speech_rate": options.speed,
            }
            if options.instructions:
                session["instructions"] = options.instructions
            await self._send_event(
                websocket,
                {
                    "type": "session.update",
                    "session": session,
                },
            )
            await self._send_event(websocket, {"type": "input_text_buffer.append", "text": text})
            await self._send_event(websocket, {"type": "input_text_buffer.commit"})
            await self._send_event(websocket, {"type": "session.finish"})

            async for message in websocket:
                event = json.loads(message)
                event_type = event.get("type")
                if event_type == "error":
                    error = event.get("error") or {}
                    raise ProviderError(error.get("message") or json.dumps(error))
                if event_type == "response.audio.delta":
                    data = self._decode_audio_delta(event)
                    audio_received = True
                    yield AudioChunk(
                        data=data,
                        mime_type=_mime_type(options.audio_format),
                        extension=_extension(options.audio_format),
                    )
                if event_type == "response.done":
                    response = event.get("response")
                    status = response.get("status") if isinstance(response, dict) else None
                    if status != "completed":
                        raise ProviderError(f"qwen provider response {status or 'missing completion status'}")
                    if not audio_received:
                        raise ProviderError("qwen provider returned no audio")
                    response_completed = True
                    break
                if event_type == "session.finished":
                    raise ProviderError("qwen provider session finished before a completed response")
            if not response_completed:
                raise ProviderError("qwen provider ended before a completed response")
        except ProviderError as exc:
            primary_error = exc
            raise
        except Exception as exc:
            provider_error = ProviderError(f"qwen provider failed: {exc}")
            primary_error = provider_error
            raise provider_error from exc
        finally:
            if websocket is not None:
                close = getattr(websocket, "close", None)
                if close is not None:
                    try:
                        await close()
                    except Exception as exc:
                        if primary_error is None:
                            raise ProviderError(f"qwen provider failed: {exc}") from exc

    def _build_url(self, model: str | None = None) -> str:
        separator = "&" if "?" in self.realtime_url else "?"
        return f"{self.realtime_url}{separator}{urlencode({'model': model or self.model})}"

    async def _send_event(self, websocket: object, event: dict) -> None:
        event["event_id"] = f"event_{uuid.uuid4().hex}"
        await websocket.send(json.dumps(event))

    def _decode_audio_delta(self, event: dict) -> bytes:
        delta = event.get("delta")
        if not isinstance(delta, str) or not delta:
            raise ProviderError("invalid audio delta from qwen provider")
        try:
            return base64.b64decode(delta, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ProviderError("invalid audio delta from qwen provider") from exc


def _mime_type(audio_format: str) -> str:
    if audio_format == "mp3":
        return "audio/mpeg"
    if audio_format == "wav":
        return "audio/wav"
    if audio_format == "opus":
        return "audio/ogg"
    return "application/octet-stream"


def _extension(audio_format: str) -> str:
    if audio_format in {"mp3", "wav", "opus"}:
        return audio_format
    return "bin"
