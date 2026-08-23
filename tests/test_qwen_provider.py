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
            {"type": "response.done", "response": {"status": "completed"}},
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
    options = TTSOptions(voice="Cherry", audio_format="mp3", language="Chinese", sample_rate=16000, speed=1.25)

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
    assert websocket.sent_events[0]["session"]["speech_rate"] == 1.25
    assert "instructions" not in websocket.sent_events[0]["session"]
    assert websocket.sent_events[1]["text"] == "hello"
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_qwen_provider_sends_instruction_control_when_present():
    websocket = FakeWebSocket(
        [
            {"type": "response.audio.delta", "delta": base64.b64encode(b"abc").decode("ascii")},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
    )

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-instruct-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )
    options = TTSOptions(
        voice="Kai",
        audio_format="mp3",
        language="English",
        speed=0.9,
        instructions="Read in a calm long-form audiobook style.",
    )

    chunks = [chunk async for chunk in provider.stream_speech("hello", options)]

    assert [chunk.data for chunk in chunks] == [b"abc"]
    assert websocket.sent_events[0]["session"]["instructions"] == "Read in a calm long-form audiobook style."


@pytest.mark.asyncio
async def test_qwen_provider_uses_request_model_override():
    websocket = FakeWebSocket(
        [
            {"type": "response.audio.delta", "delta": base64.b64encode(b"abc").decode("ascii")},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
    )
    captured = {}

    async def connect(url, additional_headers):
        captured["url"] = url
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )
    options = TTSOptions(voice="Kai", model="qwen3-tts-instruct-flash-realtime-2026-01-22")

    chunks = [chunk async for chunk in provider.stream_speech("hello", options)]

    assert [chunk.data for chunk in chunks] == [b"abc"]
    assert captured["url"].endswith("?model=qwen3-tts-instruct-flash-realtime-2026-01-22")


@pytest.mark.asyncio
async def test_qwen_provider_rejects_incomplete_response():
    websocket = FakeWebSocket([{"type": "response.done", "response": {"status": "incomplete"}}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="response incomplete"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


@pytest.mark.asyncio
async def test_qwen_provider_rejects_completed_response_without_audio():
    websocket = FakeWebSocket([{"type": "response.done", "response": {"status": "completed"}}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="returned no audio"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


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


@pytest.mark.asyncio
async def test_qwen_provider_wraps_connect_failure_in_provider_error():
    async def connect(url, additional_headers):
        raise OSError("dns failed")

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="qwen provider failed: dns failed"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass


@pytest.mark.asyncio
async def test_qwen_provider_rejects_invalid_audio_delta_and_closes_websocket():
    websocket = FakeWebSocket([{"type": "response.audio.delta", "delta": "not base64!"}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="invalid audio delta"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_qwen_provider_rejects_missing_audio_delta_and_closes_websocket():
    websocket = FakeWebSocket([{"type": "response.audio.delta"}])

    async def connect(url, additional_headers):
        return websocket

    provider = QwenTTSProvider(
        api_key="key",
        model="qwen3-tts-flash-realtime",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime",
        connect=connect,
    )

    with pytest.raises(ProviderError, match="invalid audio delta"):
        async for _ in provider.stream_speech("hello", TTSOptions(voice="Cherry")):
            pass
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_qwen_provider_close_error_does_not_mask_provider_error():
    websocket = FakeWebSocket([{"type": "error", "error": {"message": "bad voice"}}], close_error=RuntimeError("close failed"))

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


def test_qwen_provider_build_url_preserves_query_and_urlencodes_model():
    provider = QwenTTSProvider(
        api_key="key",
        model="qwen 3/tts+flash",
        realtime_url="wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?workspace=abc",
    )

    assert provider._build_url() == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime?workspace=abc&model=qwen+3%2Ftts%2Bflash"


class FakeWebSocket:
    def __init__(self, events, close_error=None):
        self.events = [json.dumps(event) for event in events]
        self.sent_events = []
        self.closed = False
        self.close_error = close_error

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
        if self.close_error is not None:
            raise self.close_error
