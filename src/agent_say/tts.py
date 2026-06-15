"""Text-to-speech via the macOS ``say`` command.

``say`` renders a clean mono 16-bit WAV at an arbitrary rate with no extra
Python dependencies. We read it back with the stdlib ``wave`` module and return
float32 samples in [-1, 1] for playback through sounddevice.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from .errors import TTSError


def is_available() -> bool:
    return sys.platform == "darwin" and shutil.which("say") is not None


def synthesize(text: str, sample_rate: int) -> np.ndarray:
    """Render ``text`` to mono float32 samples at ``sample_rate``.

    Raises ``TTSError`` if the ``say`` backend is unavailable or fails.
    """
    if not text.strip():
        raise TTSError("Nothing to speak: text is empty.")
    if not is_available():
        raise TTSError(
            "macOS 'say' command not available; yel's TTS backend requires macOS."
        )

    with tempfile.TemporaryDirectory(prefix="yel-tts-") as tmp:
        wav_path = Path(tmp) / "speech.wav"
        cmd = [
            "say",
            "--data-format=LEI16@%d" % sample_rate,
            "--file-format=WAVE",
            "-o",
            str(wav_path),
            text,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TTSError(f"'say' failed to run: {exc}") from exc

        if proc.returncode != 0:
            detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            raise TTSError(f"'say' exited with code {proc.returncode}: {detail}")
        if not wav_path.exists():
            raise TTSError("'say' did not produce an audio file.")

        return _read_wav_mono(wav_path)


def _read_wav_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        frames = w.readframes(w.getnframes())

    if width != 2:
        raise TTSError(f"Unexpected sample width from 'say': {width} bytes.")
    data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data
