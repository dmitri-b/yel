"""Error types and process exit codes for yel.

Exit codes (also documented in the CLI help):

    0  success
    1  general error
    2  no agent speech detected before start timeout
    3  audio device not found
    4  TTS backend failed
    5  invalid config
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_NO_SPEECH = 2
EXIT_DEVICE_NOT_FOUND = 3
EXIT_TTS_FAILED = 4
EXIT_INVALID_CONFIG = 5


class YelError(Exception):
    """Base error. Carries the process exit code to report."""

    exit_code: int = EXIT_GENERAL


class DeviceNotFoundError(YelError):
    exit_code = EXIT_DEVICE_NOT_FOUND


class TTSError(YelError):
    exit_code = EXIT_TTS_FAILED


class ConfigError(YelError):
    exit_code = EXIT_INVALID_CONFIG


class NoSpeechError(YelError):
    """Agent never started speaking before the start timeout."""

    exit_code = EXIT_NO_SPEECH
