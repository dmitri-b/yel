"""Tests for the Deepgram transcription module (network mocked)."""

import io
import json
import wave

import numpy as np
import pytest

from agent_say import transcribe as dg


def _tone(seconds=0.2, sr=16000):
    return (0.2 * np.sin(2 * np.pi * 220 * np.arange(int(seconds * sr)) / sr)).astype(
        np.float32
    )


def test_pcm16_wav_bytes_roundtrip():
    samples = _tone()
    wav = dg._pcm16_wav_bytes(samples, 16000)
    with wave.open(io.BytesIO(wav)) as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 16000
        assert w.getnframes() == len(samples)


def test_extract_transcript():
    payload = {
        "results": {"channels": [{"alternatives": [{"transcript": "hello world  "}]}]}
    }
    assert dg._extract_transcript(payload) == "hello world"


def test_extract_transcript_empty_alternatives():
    payload = {"results": {"channels": [{"alternatives": []}]}}
    assert dg._extract_transcript(payload) == ""


def test_extract_transcript_malformed():
    with pytest.raises(dg.TranscriptionError):
        dg._extract_transcript({"nope": True})


def test_missing_key_raises():
    with pytest.raises(dg.TranscriptionError):
        dg.transcribe(_tone(), 16000, api_key="")


def test_empty_audio_returns_empty():
    assert dg.transcribe(np.zeros(0, dtype=np.float32), 16000, api_key="k") == ""


def test_transcribe_posts_and_parses(monkeypatch):
    captured = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(
                {"results": {"channels": [{"alternatives": [{"transcript": "hi there"}]}]}}
            ).encode()

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["body_len"] = len(request.data)
        return FakeResp()

    # json.load reads from the response object; FakeResp.read returns bytes.
    monkeypatch.setattr(dg.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(dg.json, "load", lambda resp: json.loads(resp.read()))

    text = dg.transcribe(_tone(), 16000, api_key="secret", model="nova-3")
    assert text == "hi there"
    assert "model=nova-3" in captured["url"]
    assert captured["auth"] == "Token secret"
    assert captured["body_len"] > 44  # WAV header + samples


def test_http_error_becomes_transcription_error(monkeypatch):
    import urllib.error

    def boom(request, timeout=0):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key"))

    monkeypatch.setattr(dg.urllib.request, "urlopen", boom)
    with pytest.raises(dg.TranscriptionError) as exc:
        dg.transcribe(_tone(), 16000, api_key="x")
    assert "401" in str(exc.value)
