"""Text-to-speech for scripted turns.

macOS uses the built-in ``say`` command. Windows uses the built-in SAPI voice
through Windows PowerShell. Both paths render a WAV, read it back with the
stdlib ``wave`` module, and return float32 samples in [-1, 1] for playback
through sounddevice.
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


def backend_name() -> str:
    if sys.platform == "darwin":
        return "macOS say"
    if sys.platform == "win32":
        return "Windows SAPI"
    return "unsupported"


def is_available() -> bool:
    if sys.platform == "darwin":
        return shutil.which("say") is not None
    if sys.platform == "win32":
        return shutil.which("powershell.exe") is not None or shutil.which("powershell") is not None
    return False


def synthesize(text: str, sample_rate: int) -> np.ndarray:
    """Render ``text`` to mono float32 samples at ``sample_rate``.

    Raises ``TTSError`` if the host TTS backend is unavailable or fails.
    """
    if not text.strip():
        raise TTSError("Nothing to speak: text is empty.")
    if not is_available():
        raise TTSError(f"{backend_name()} TTS backend is not available on this machine.")

    with tempfile.TemporaryDirectory(prefix="yel-tts-") as tmp:
        wav_path = Path(tmp) / "speech.wav"
        if sys.platform == "darwin":
            _synthesize_macos_say(text, sample_rate, wav_path)
        elif sys.platform == "win32":
            _synthesize_windows_sapi(text, wav_path)
        else:  # pragma: no cover - guarded by is_available()
            raise TTSError(f"Unsupported TTS platform: {sys.platform}")

        if not wav_path.exists():
            raise TTSError(f"{backend_name()} did not produce an audio file.")

        audio, actual_rate = _read_wav_mono(wav_path)
        if actual_rate != sample_rate:
            audio = _resample_linear(audio, actual_rate, sample_rate)
        return audio


def _synthesize_macos_say(text: str, sample_rate: int, wav_path: Path) -> None:
    cmd = [
        "say",
        "--data-format=LEI16@%d" % sample_rate,
        "--file-format=WAVE",
        "-o",
        str(wav_path),
        text,
    ]
    _run_tts_command(cmd, "'say'")


def _synthesize_windows_sapi(text: str, wav_path: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise TTSError("Windows PowerShell is required for SAPI text-to-speech.")
    script = (
        "& { param([string] $OutPath, [string] $Text) "
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { $s.SetOutputToWaveFile($OutPath); $s.Speak($Text) } "
        "finally { $s.Dispose() } "
        "}"
    )
    cmd = [
        powershell,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
        str(wav_path),
        text,
    ]
    _run_tts_command(cmd, "Windows SAPI")


def _run_tts_command(cmd: list[str], label: str) -> None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TTSError(f"{label} failed to run: {exc}") from exc

    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        raise TTSError(f"{label} exited with code {proc.returncode}: {detail}")


def _read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        sample_rate = w.getframerate()
        frames = w.readframes(w.getnframes())

    if width != 2:
        raise TTSError(f"Unexpected sample width from {backend_name()}: {width} bytes.")
    data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sample_rate


def _resample_linear(audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
    if from_rate <= 0 or to_rate <= 0:
        raise TTSError(f"Invalid WAV sample rate: {from_rate} -> {to_rate}")
    if audio.size == 0 or from_rate == to_rate:
        return audio.astype(np.float32, copy=False)
    out_len = max(1, int(round(audio.size * to_rate / from_rate)))
    src_x = np.arange(audio.size, dtype=np.float64)
    dst_x = np.linspace(0, audio.size - 1, out_len, dtype=np.float64)
    return np.interp(dst_x, src_x, audio).astype(np.float32)
