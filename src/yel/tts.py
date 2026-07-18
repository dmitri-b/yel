"""Text-to-speech via the macOS ``say`` command.

``say`` renders a clean mono 16-bit WAV at an arbitrary rate with no extra
Python dependencies. We read it back with the stdlib ``wave`` module and return
float32 samples in [-1, 1] for playback through sounddevice.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from .errors import TTSError

DEFAULT_LANGUAGE = "en_US"
VOICE_BY_LOCALE = {
    "en_US": "Samantha",
    "es_ES": "Mónica",
    "fr_FR": "Thomas",
    "de_DE": "Eddy (German (Germany))",
}
VOICE_GENDER_BY_LOCALE = {
    "de_DE": "male",
}
LANGUAGE_ALIASES = {
    "en": "en_US",
    "en_us": "en_US",
    "es": "es_ES",
    "es_es": "es_ES",
    "fr": "fr_FR",
    "fr_fr": "fr_FR",
    "de": "de_DE",
    "de_de": "de_DE",
}


def parse_voices(output: str) -> dict[str, str]:
    """Parse ``say -v '?'`` output into voice-name → locale mappings."""
    voices: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(r"^(.*?)\s+([a-z]{2}_[A-Z]{2})\s+#", line)
        if match:
            voices[match.group(1).strip()] = match.group(2)
    return voices


@functools.lru_cache(maxsize=1)
def available_voices() -> dict[str, str]:
    if not is_available():
        raise TTSError("macOS 'say' command not available; yel's TTS backend requires macOS.")
    try:
        proc = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=30, check=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise TTSError(f"could not query macOS voices with `say -v ?`: {exc}") from exc
    return parse_voices(proc.stdout)


def voice_for_language(
    language: str | None = None,
    *,
    voices: dict[str, str] | None = None,
) -> tuple[str, str]:
    key = str(language or DEFAULT_LANGUAGE).strip().replace("-", "_").lower()
    locale = LANGUAGE_ALIASES.get(key)
    if locale is None:
        raise TTSError(f"Unsupported TTS language: {language!r}")
    voice = VOICE_BY_LOCALE[locale]
    installed_locale = (voices if voices is not None else available_voices()).get(voice)
    if installed_locale != locale:
        raise TTSError(
            f"macOS voice {voice!r} must be installed as {locale}; found {installed_locale!r}"
        )
    return voice, locale


def is_available() -> bool:
    return sys.platform == "darwin" and shutil.which("say") is not None


def synthesize(
    text: str,
    sample_rate: int,
    *,
    language: str | None = None,
) -> np.ndarray:
    """Render text with a locale-matched voice; default explicitly to US English."""
    if not text.strip():
        raise TTSError("Nothing to speak: text is empty.")
    if not is_available():
        raise TTSError(
            "macOS 'say' command not available; yel's TTS backend requires macOS."
        )

    voice, _locale = voice_for_language(language)
    with tempfile.TemporaryDirectory(prefix="yel-tts-") as tmp:
        wav_path = Path(tmp) / "speech.wav"
        cmd = [
            "say",
            "-v",
            voice,
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
