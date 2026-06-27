"""Transcribe captured agent audio with Deepgram's streaming WebSocket API.

The CLI is turn-based: we record the agent's reply while detecting its turn
boundaries, then transcribe the captured clip. This module streams that clip to
Deepgram's realtime endpoint (``wss://api.deepgram.com/v1/listen``) — sending the
audio as linear16 frames, then ``Finalize`` + ``CloseStream`` — and concatenates
the ``is_final`` results. Streaming keeps yel on the same realtime path the live
agents use (and is ready for incremental, mid-turn transcription later).

Transcription is best-effort: failures surface as ``TranscriptionError`` and are
treated as non-fatal by the caller, since the turn itself already succeeded.
"""

from __future__ import annotations

import asyncio
import json
import urllib.parse
from typing import Optional

import numpy as np

DEEPGRAM_STREAM_URL = "wss://api.deepgram.com/v1/listen"


class TranscriptionError(Exception):
    """Deepgram transcription failed."""


def _pcm16_bytes(samples: np.ndarray, _sample_rate: int | None = None) -> bytes:
    """Encode mono float32 [-1, 1] samples as raw 16-bit little-endian PCM."""
    pcm16 = np.clip(samples * 32768.0, -32768, 32767).astype("<i2")
    return pcm16.tobytes()


def _stream_url(model: str, sample_rate: int, language: str) -> str:
    """Build the Deepgram realtime URL for raw linear16 mono audio."""
    query = urllib.parse.urlencode(
        {
            "model": model,
            "language": language,
            "encoding": "linear16",
            "sample_rate": sample_rate,
            "channels": 1,
            "smart_format": "true",
            "interim_results": "false",
        }
    )
    return f"{DEEPGRAM_STREAM_URL}?{query}"


def _final_from_message(msg: dict) -> Optional[str]:
    """Return the finalized transcript from a Deepgram ``Results`` message, or
    ``None`` if the message is not a non-empty final result."""
    if msg.get("type") != "Results" or not msg.get("is_final"):
        return None
    try:
        transcript = msg["channel"]["alternatives"][0]["transcript"]
    except (KeyError, IndexError, TypeError):
        return None
    transcript = (transcript or "").strip()
    return transcript or None


def transcribe(
    samples: np.ndarray,
    sample_rate: int,
    *,
    api_key: str,
    model: str = "nova-3",
    language: str = "en",
    timeout: float = 30.0,
) -> str:
    """Return the streamed transcript of ``samples``. Raises ``TranscriptionError``."""
    if not api_key:
        raise TranscriptionError(
            "No Deepgram API key. Set DEEPGRAM_API_KEY (in .env or the environment)."
        )
    if samples.size == 0:
        return ""

    pcm16 = _pcm16_bytes(samples)
    url = _stream_url(model, sample_rate, language)
    try:
        return asyncio.run(_stream(pcm16, sample_rate, url, api_key, timeout))
    except TranscriptionError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalize any failure for the caller
        raise TranscriptionError(f"Deepgram streaming failed: {exc}") from exc


async def _stream(
    pcm16: bytes,
    sample_rate: int,
    url: str,
    api_key: str,
    timeout: float,
) -> str:
    import websockets

    finals: list[str] = []
    # ~50 ms of linear16 mono per send (2 bytes/sample).
    chunk = max(2, (sample_rate // 20) * 2)

    try:
        ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Token {api_key}"},
            open_timeout=timeout,
        )
    except TypeError:
        # Older websockets used extra_headers instead of additional_headers.
        ws = await websockets.connect(
            url,
            extra_headers={"Authorization": f"Token {api_key}"},
            open_timeout=timeout,
        )

    async def receiver() -> None:
        async for raw in ws:
            if isinstance(raw, (bytes, bytearray)):
                continue
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            final = _final_from_message(msg)
            if final:
                finals.append(final)

    recv_task = asyncio.create_task(receiver())
    try:
        for i in range(0, len(pcm16), chunk):
            await ws.send(pcm16[i : i + chunk])
        # Flush buffered audio into a final, then signal end-of-stream so Deepgram
        # emits any remaining results and closes the socket.
        await ws.send(json.dumps({"type": "Finalize"}))
        await ws.send(json.dumps({"type": "CloseStream"}))
        try:
            await asyncio.wait_for(recv_task, timeout=timeout)
        except asyncio.TimeoutError:
            recv_task.cancel()
    finally:
        if not recv_task.done():
            recv_task.cancel()
        await ws.close()

    return " ".join(finals).strip()
