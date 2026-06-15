"""Error types and process exit codes for yel.

Exit codes (also documented in the CLI help):

    0  success
    1  general error
    2  no agent speech detected before start timeout
    3  overall timeout reached
    4  audio device not found
    5  TTS backend failed
    6  invalid config
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_GENERAL = 1
EXIT_NO_SPEECH = 2
EXIT_OVERALL_TIMEOUT = 3
EXIT_DEVICE_NOT_FOUND = 4
EXIT_TTS_FAILED = 5
EXIT_INVALID_CONFIG = 6


class AgentSayError(Exception):
    """Base error. Carries the process exit code to report."""

    exit_code: int = EXIT_GENERAL


class DeviceNotFoundError(AgentSayError):
    exit_code = EXIT_DEVICE_NOT_FOUND


class TTSError(AgentSayError):
    exit_code = EXIT_TTS_FAILED


class ConfigError(AgentSayError):
    exit_code = EXIT_INVALID_CONFIG


class NoSpeechError(AgentSayError):
    """Agent never started speaking before the start timeout."""

    exit_code = EXIT_NO_SPEECH


class OverallTimeoutError(AgentSayError):
    """The overall turn timeout elapsed before the agent finished."""

    exit_code = EXIT_OVERALL_TIMEOUT
