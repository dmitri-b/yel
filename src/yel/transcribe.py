"""Fully local transcription with macOS 26 ``SpeechAnalyzer``.

Apple exposes the current ``SpeechTranscriber`` API in Swift, so yel ships a
small Swift source helper and compiles it into the user's cache on first use.
Captured mono PCM is passed to that helper over stdin and the final transcript
is returned on stdout. No captured audio or transcript leaves the Mac.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

DEFAULT_LOCALE = "en-US"
_HELPER_SOURCE = Path(__file__).with_name("native") / "speech_transcriber.swift"
_HELPER_TIMEOUT = 120.0


class TranscriptionError(Exception):
    """The local Apple Speech transcription path failed."""


def _pcm16_bytes(samples: np.ndarray, _sample_rate: int | None = None) -> bytes:
    """Encode mono float32 [-1, 1] samples as raw 16-bit little-endian PCM."""
    pcm16 = np.clip(samples * 32768.0, -32768, 32767).astype("<i2")
    return pcm16.tobytes()


def _cache_root() -> Path:
    return Path.home() / "Library" / "Caches" / "yel" / "native"


def _macos_major() -> int:
    version = platform.mac_ver()[0]
    try:
        return int(version.split(".", 1)[0])
    except (ValueError, IndexError):
        return 0


def _compile_command(source: Path, output: Path, module_cache: Path) -> list[str]:
    """Return a Swift 6 compiler command, preferring a full Xcode toolchain."""
    xcode = Path("/Applications/Xcode.app/Contents/Developer")
    swiftc = xcode / "Toolchains/XcodeDefault.xctoolchain/usr/bin/swiftc"
    sdk = xcode / "Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk"
    common = [
        "-module-cache-path",
        str(module_cache),
        "-O",
        "-parse-as-library",
        str(source),
        "-o",
        str(output),
    ]
    if swiftc.is_file() and sdk.is_dir():
        return [str(swiftc), "-sdk", str(sdk), *common]

    xcrun = shutil.which("xcrun")
    if xcrun:
        return [xcrun, "--sdk", "macosx", "swiftc", *common]
    raise TranscriptionError(
        "Apple's native ASR helper is not built and no Swift compiler was found. "
        "Install Xcode 26 or its Command Line Tools once, then rerun yel."
    )


def _helper_executable(*, cache_root: Path | None = None) -> Path:
    if sys.platform != "darwin" or _macos_major() < 26:
        raise TranscriptionError("Native transcription requires macOS 26 or newer.")
    if not _HELPER_SOURCE.is_file():
        raise TranscriptionError(f"Native ASR source is missing: {_HELPER_SOURCE}")

    root = cache_root or _cache_root()
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(_HELPER_SOURCE.read_bytes()).hexdigest()[:16]
    executable = root / f"yel-speech-transcriber-{digest}"
    if executable.is_file() and os.access(executable, os.X_OK):
        return executable

    module_cache = root / "swift-module-cache"
    module_cache.mkdir(parents=True, exist_ok=True)
    temporary = root / f".{executable.name}.{os.getpid()}.tmp"
    command = _compile_command(_HELPER_SOURCE, temporary, module_cache)
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_HELPER_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        temporary.unlink(missing_ok=True)
        raise TranscriptionError(f"Could not build the native ASR helper: {exc}") from exc

    if proc.returncode != 0:
        temporary.unlink(missing_ok=True)
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown compiler error"
        raise TranscriptionError(f"Could not build the native ASR helper: {detail}")

    temporary.chmod(0o755)
    os.replace(temporary, executable)
    return executable


def transcribe(
    samples: np.ndarray,
    sample_rate: int,
    *,
    locale: str = DEFAULT_LOCALE,
    timeout: float = 60.0,
) -> str:
    """Return Apple's on-device transcript for a captured mono audio clip."""
    if samples.size == 0:
        return ""

    helper = _helper_executable()
    command = [
        str(helper),
        "--sample-rate",
        str(sample_rate),
        "--locale",
        locale.replace("_", "-"),
    ]
    try:
        proc = subprocess.run(
            command,
            input=_pcm16_bytes(samples),
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError(
            f"Apple Speech transcription timed out after {timeout:g}s."
        ) from exc
    except OSError as exc:
        raise TranscriptionError(f"Could not run Apple's native ASR helper: {exc}") from exc

    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip() or "unknown native ASR error"
        raise TranscriptionError(detail)
    return proc.stdout.decode(errors="replace").strip()


def check_available(*, locale: str = DEFAULT_LOCALE) -> None:
    """Compile and exercise the native backend with a short silent buffer."""
    transcribe(np.zeros(1_600, dtype=np.float32), 16_000, locale=locale)
