"""Validated runtime settings.

Precedence (highest first): CLI flags -> environment variables -> .env file ->
built-in defaults. CLI flags are applied by the caller via ``apply_overrides``;
everything else is handled by pydantic-settings.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# webrtcvad only accepts these.
_VALID_RATES = (8_000, 16_000, 32_000, 48_000)
_VALID_FRAME_MS = (10, 20, 30)


def find_dotenv(start: Path | None = None) -> str:
    """Find the nearest ``.env`` walking up from ``start`` (default: CWD).

    Lets the standalone ``yel`` package pick up a ``.env`` that lives at the
    repo root (where ``DEEPGRAM_API_KEY`` is kept) even when run from a subdir.
    Falls back to ``".env"`` if none is found.
    """
    base = (start or Path.cwd()).resolve()
    for parent in (base, *base.parents):
        candidate = parent / ".env"
        if candidate.is_file():
            return str(candidate)
    return ".env"


class AgentSaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_SAY_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    output_device: str | int | None = Field(
        default=None,
        validation_alias=AliasChoices("AGENT_SAY_OUT", "AGENT_SAY_OUTPUT_DEVICE"),
        description="Output device for generated speech.",
    )
    listen_device: str | int | None = Field(
        default=None,
        validation_alias=AliasChoices("AGENT_SAY_LISTEN", "AGENT_SAY_LISTEN_DEVICE"),
        description="Input/monitor device to listen for the agent.",
    )
    monitor_device: str | int | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AGENT_SAY_SPEAKERS", "AGENT_SAY_MONITOR", "AGENT_SAY_MONITOR_DEVICE"
        ),
        description="Speakers to play the agent's captured audio on (live monitor).",
    )

    start_timeout: float = Field(default=30.0, gt=0)
    end_silence: float = Field(default=1.2, gt=0)
    min_speech: float = Field(default=0.3, gt=0)
    overall_timeout: float = Field(default=180.0, gt=0)
    # Success cap: return exit 0 after at most this long (from listen start),
    # even if the agent is still talking. None disables it. Env is plain seconds;
    # the CLI accepts human durations (5s/500ms/2m).
    response_timeout: float | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("AGENT_SAY_TIMEOUT", "AGENT_SAY_RESPONSE_TIMEOUT"),
        description="Return successfully after at most this long (seconds).",
    )

    vad: int = Field(default=2, ge=0, le=3)
    rms_threshold: float = Field(default=0.012, gt=0)
    sample_rate: int = 16_000
    frame_ms: int = Field(default=30, ge=10, le=30)

    # Deepgram transcription of the agent's reply.
    transcribe: bool = Field(default=False, description="Transcribe the agent's reply.")
    deepgram_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEEPGRAM_API_KEY", "AGENT_SAY_DEEPGRAM_API_KEY"),
        description="Deepgram API key (read from DEEPGRAM_API_KEY by default).",
    )
    deepgram_model: str = Field(default="nova-3", description="Deepgram model.")

    @field_validator("sample_rate")
    @classmethod
    def _check_rate(cls, value: int) -> int:
        if value not in _VALID_RATES:
            raise ValueError(f"sample_rate must be one of {_VALID_RATES}, got {value}")
        return value

    @field_validator("frame_ms")
    @classmethod
    def _check_frame_ms(cls, value: int) -> int:
        if value not in _VALID_FRAME_MS:
            raise ValueError(f"frame_ms must be one of {_VALID_FRAME_MS}, got {value}")
        return value

    def apply_overrides(self, **overrides: object) -> "AgentSaySettings":
        """Return a copy with the non-``None`` overrides applied (CLI flags)."""
        updates = {key: value for key, value in overrides.items() if value is not None}
        return self.model_copy(update=updates)

    @property
    def frame_samples(self) -> int:
        return int(self.sample_rate * self.frame_ms / 1000)
