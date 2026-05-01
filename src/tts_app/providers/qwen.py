from __future__ import annotations

import base64
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable

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
        websocket = await self.connect(url, additional_headers={"Authorization": f"Bearer {self.api_key}"})
        try:
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
                    data = base64.b64decode(event.get("delta", ""))
                    yield AudioChunk(
                        data=data,
                        mime_type=_mime_type(options.audio_format),
                        extension=_extension(options.audio_format),
                    )
                if event_type in {"response.done", "session.finished"}:
                    break
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"qwen provider failed: {exc}") from exc
        finally:
            close = getattr(websocket, "close", None)
            if close is not None:
                await close()

    def _build_url(self) -> str:
        separator = "&" if "?" in self.realtime_url else "?"
        return f"{self.realtime_url}{separator}model={self.model}"

    async def _send_event(self, websocket: object, event: dict) -> None:
        event["event_id"] = f"event_{uuid.uuid4().hex}"
        await websocket.send(json.dumps(event))


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
