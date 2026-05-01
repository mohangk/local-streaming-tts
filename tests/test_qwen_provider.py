from __future__ import annotations

import base64
import json

import pytest

from tts_app.providers.base import ProviderError, TTSOptions
from tts_app.providers.qwen import QwenTTSProvider


@pytest.mark.asyncio
async def test_qwen_provider_requires_api_key():
    provider = QwenTTSProvider(
        api_key=None,
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
    )

    with pytest.raises(ProviderError, match="API key is required"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


@pytest.mark.asyncio
async def test_qwen_provider_sends_realtime_events_and_yields_audio():
    websocket = FakeWebSocket(
        [
            {"type": "session.created"},
            {"type": "session.updated"},
            {"type": "input_text_buffer.committed"},
            {"type": "response.created"},
            {"type": "response.audio.delta", "delta": base64.b64encode(b"abc").decode("ascii")},
            {"type": "response.audio.delta", "delta": base64.b64encode(b"def").decode("ascii")},
            {"type": "response.done"},
            {"type": "response.audio.delta", "delta": base64.b64encode(b"ignored").decode("ascii")},
        ]
    )
    captured = {}

    async def connect(url, additional_headers):
        captured["url"] = url
        captured["headers"] = additional_headers
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )
    options = TTSOptions(voice="Cherry", audio_format="mp3", language="Chinese", sample_rate=16000)

    chunks = [chunk async for chunk in provider.stream_speech("hello", options)]

    assert [chunk.data for chunk in chunks] == [b"abc", b"def"]
    assert all(chunk.mime_type == "audio/mpeg" for chunk in chunks)
    assert all(chunk.extension == "mp3" for chunk in chunks)
    assert captured["url"] == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?model=qwen3-tts-flash-realtime"
    assert captured["headers"] == {"Authorization": "Bearer key"}
    assert [event["type"] for event in websocket.sent_events] == [
        "session.update",
        "input_text_buffer.append",
        "input_text_buffer.commit",
        "session.finish",
    ]
    assert websocket.sent_events[0]["session"]["voice"] == "Cherry"
    assert websocket.sent_events[0]["session"]["mode"] == "commit"
    assert websocket.sent_events[0]["session"]["language_type"] == "Chinese"
    assert websocket.sent_events[0]["session"]["response_format"] == "mp3"
    assert websocket.sent_events[0]["session"]["sample_rate"] == 16000
    assert websocket.sent_events[1]["text"] == "hello"
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_qwen_provider_turns_server_error_into_provider_error():
    websocket = FakeWebSocket([{"type": "error", "error": {"message": "bad voice"}}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="bad voice"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Missing")):
            pass
    assert websocket.closed is True


class FakeWebSocket:
    def __init__(self, events):
        self.events = [json.dumps(event) for event in events]
        self.sent_events = []
        self.closed = False

    async def send(self, message):
        self.sent_events.append(json.loads(message))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.events:
            raise StopAsyncIteration
        return self.events.pop(0)

    async def close(self):
        self.closed = True
