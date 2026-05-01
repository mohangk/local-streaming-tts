from __future__ import annotations

import base64
import binascii
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import urlencode

import websockets

from tts_app.providers.base import AudioChunk, ProviderError, TTSOptions

QwenConnect = Callable[..., Awaitable[object]]


class QwenTTSProvider:
    name = "qwen"

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
        url = self._build_url()
        websocket = None
        primary_error: BaseException | None = None
        try:
            websocket = await self.connect(url, additional_headers={"Authorization": f"Bearer {self.api_key}"})
            await self._send_event(
                websocket,
                {
                    "type": "session.update",
                    "session": {
                        "voice": options.voice,
                        "mode": "commit",
                        "language_type": options.language,
                        "response_format": options.audio_format,
                        "sample_rate": options.sample_rate,
                    },
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
                    yield AudioChunk(
                        data=data,
                        mime_type=_mime_type(options.audio_format),
                        extension=_extension(options.audio_format),
                    )
                if event_type in {"response.done", "session.finished"}:
                    break
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

    def _build_url(self) -> str:
        separator = "&" if "?" in self.realtime_url else "?"
        return f"{self.realtime_url}{separator}{urlencode({'model': self.model})}"

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
