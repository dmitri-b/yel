"""Tests for the Deepgram streaming transcription module (websocket mocked)."""

import json
import sys

import numpy as np
import pytest

from agent_say import transcribe as dg


def _tone(seconds=0.2, sr=16000):
    return (0.2 * np.sin(2 * np.pi * 220 * np.arange(int(seconds * sr)) / sr)).astype(
        np.float32
    )


def _fake_websockets(connect):
    return type("W", (), {"connect": staticmethod(connect)})


def test_pcm16_bytes_roundtrip():
    samples = _tone()
    pcm = dg._pcm16_bytes(samples, 16000)
    assert len(pcm) == len(samples) * 2  # 16-bit mono
    back = np.frombuffer(pcm, dtype="<i2")
    assert back.shape[0] == samples.shape[0]


def test_stream_url_has_streaming_params():
    url = dg._stream_url("nova-3", 16000, "en")
    assert url.startswith("wss://api.deepgram.com/v1/listen?")
    assert "model=nova-3" in url
    assert "encoding=linear16" in url
    assert "sample_rate=16000" in url
    assert "interim_results=false" in url


def test_final_from_message_extracts_only_finals():
    final = {
        "type": "Results",
        "is_final": True,
        "channel": {"alternatives": [{"transcript": "hello world  "}]},
    }
    assert dg._final_from_message(final) == "hello world"

    interim = dict(final, is_final=False)
    assert dg._final_from_message(interim) is None

    empty = {"type": "Results", "is_final": True, "channel": {"alternatives": [{"transcript": "  "}]}}
    assert dg._final_from_message(empty) is None

    assert dg._final_from_message({"type": "Metadata"}) is None


def test_missing_key_raises():
    with pytest.raises(dg.TranscriptionError):
        dg.transcribe(_tone(), 16000, api_key="")


def test_empty_audio_returns_empty():
    assert dg.transcribe(np.zeros(0, dtype=np.float32), 16000, api_key="k") == ""


class _FakeWS:
    """Minimal async websocket: collects sends, replays scripted server messages."""

    def __init__(self, server_messages):
        self._server = list(server_messages)
        self.sent = []
        self.closed = False

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        self._iter = iter(self._server)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def close(self):
        self.closed = True


def test_transcribe_streams_audio_and_joins_finals(monkeypatch):
    captured = {}
    server_messages = [
        json.dumps({"type": "Results", "is_final": False,
                    "channel": {"alternatives": [{"transcript": "hi"}]}}),
        json.dumps({"type": "Results", "is_final": True,
                    "channel": {"alternatives": [{"transcript": "hi there,"}]}}),
        json.dumps({"type": "Results", "is_final": True,
                    "channel": {"alternatives": [{"transcript": "how are you?"}]}}),
    ]
    fake = _FakeWS(server_messages)

    async def fake_connect(url, **kwargs):
        captured["url"] = url
        headers = kwargs.get("additional_headers") or kwargs.get("extra_headers") or {}
        captured["auth"] = headers.get("Authorization")
        return fake

    monkeypatch.setitem(sys.modules, "websockets", _fake_websockets(fake_connect))

    text = dg.transcribe(_tone(0.3), 16000, api_key="secret", model="nova-3")

    assert text == "hi there, how are you?"
    assert captured["url"].startswith("wss://api.deepgram.com/v1/listen?")
    assert "model=nova-3" in captured["url"]
    assert captured["auth"] == "Token secret"
    audio_frames = [s for s in fake.sent if isinstance(s, (bytes, bytearray))]
    control = [json.loads(s) for s in fake.sent if isinstance(s, str)]
    assert len(audio_frames) >= 1
    assert {"type": "Finalize"} in control
    assert {"type": "CloseStream"} in control
    assert fake.closed


def test_connect_failure_becomes_transcription_error(monkeypatch):
    async def boom(url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setitem(sys.modules, "websockets", _fake_websockets(boom))
    with pytest.raises(dg.TranscriptionError) as exc:
        dg.transcribe(_tone(), 16000, api_key="x")
    assert "streaming failed" in str(exc.value).lower()
