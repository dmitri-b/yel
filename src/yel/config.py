"""Validated CLI runtime settings for the BlackHole-only audio path."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

# webrtcvad only accepts these.
_VALID_RATES = (8_000, 16_000, 32_000, 48_000)
_VALID_FRAME_MS = (10, 20, 30)
DEFAULT_BLACKHOLE_DEVICE = "BlackHole 2ch"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_device: str = Field(
        default=DEFAULT_BLACKHOLE_DEVICE,
        description="BlackHole output device for generated speech.",
    )
    listen_device: str = Field(
        default=DEFAULT_BLACKHOLE_DEVICE,
        description="BlackHole input device used to capture the agent.",
    )
    monitor_device: str | int | None = Field(
        default=None,
        description="Speakers to play the agent's captured audio on (live monitor).",
    )
    speaker_output: bool = Field(
        default=True,
        description="Allow audio to be sent to real speaker outputs.",
    )

    start_timeout: float = Field(default=30.0, gt=0)
    end_silence: float = Field(default=1.2, gt=0)
    min_speech: float = Field(default=0.3, gt=0)
    # Success cap: return exit 0 after at most this long (from listen start),
    # even if the agent is still talking. None disables it.
    response_timeout: float | None = Field(
        default=None,
        gt=0,
        description="Return successfully after at most this long (seconds).",
    )

    # Silence dips up to this long (s) do not break the min_speech run while
    # waiting for the agent to start; digital loopback replies are bursty.
    gap_tolerance: float = Field(default=0.3, ge=0)

    vad: int = Field(default=2, ge=0, le=3)
    rms_threshold: float = Field(default=0.012, gt=0)
    sample_rate: int = 16_000
    frame_ms: int = Field(default=30, ge=10, le=30)

    # Fully local Apple Speech transcription. ``--no-transcribe`` opts out.
    transcribe: bool = Field(default=True, description="Transcribe the agent's reply.")

    @field_validator("output_device", "listen_device", mode="before")
    @classmethod
    def _require_blackhole(cls, value: object) -> str:
        if not isinstance(value, str) or "blackhole" not in value.casefold():
            raise ValueError(
                "must name a BlackHole device; physical and system-default audio routes "
                "are not supported"
            )
        return value

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

    def apply_overrides(self, **overrides: object) -> "Settings":
        """Return a copy with the non-``None`` overrides applied (CLI flags)."""
        updates = {key: value for key, value in overrides.items() if value is not None}
        values = self.model_dump()
        values.update(updates)
        return type(self).model_validate(values)

    @property
    def frame_samples(self) -> int:
        return int(self.sample_rate * self.frame_ms / 1000)
