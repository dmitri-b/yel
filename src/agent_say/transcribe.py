"""Transcribe captured agent audio with Deepgram's prerecorded REST API.

The CLI is turn-based: we already record the agent's reply while detecting its
turn boundaries, so once the turn ends we send the whole clip to Deepgram in a
single request. Uses the stdlib ``urllib`` (no extra dependency). Transcription
is best-effort — failures are surfaced as ``TranscriptionError`` and treated as
non-fatal by the caller, since the turn itself already succeeded.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse
import urllib.request
import wave

import numpy as np

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


class TranscriptionError(Exception):
    """Deepgram transcription failed."""


def _pcm16_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
    """Encode mono float32 [-1, 1] samples as 16-bit PCM WAV bytes."""
    pcm16 = np.clip(samples * 32768.0, -32768, 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm16.tobytes())
    return buf.getvalue()


def transcribe(
    samples: np.ndarray,
    sample_rate: int,
    *,
    api_key: str,
    model: str = "nova-3",
    timeout: float = 30.0,
) -> str:
    """Return the transcript of ``samples``. Raises ``TranscriptionError``."""
    if not api_key:
        raise TranscriptionError(
            "No Deepgram API key. Set DEEPGRAM_API_KEY (in .env or the environment)."
        )
    if samples.size == 0:
        return ""

    wav = _pcm16_wav_bytes(samples, sample_rate)
    query = urllib.parse.urlencode({"model": model, "smart_format": "true"})
    request = urllib.request.Request(
        f"{DEEPGRAM_URL}?{query}",
        data=wav,
        method="POST",
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "audio/wav",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        raise TranscriptionError(f"Deepgram HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TranscriptionError(f"Deepgram request failed: {exc}") from exc

    return _extract_transcript(payload)


def _extract_transcript(payload: dict) -> str:
    try:
        alternatives = payload["results"]["channels"][0]["alternatives"]
    except (KeyError, IndexError, TypeError) as exc:
        raise TranscriptionError(f"Unexpected Deepgram response: {payload!r}") from exc
    if not alternatives:
        return ""
    return (alternatives[0].get("transcript") or "").strip()
