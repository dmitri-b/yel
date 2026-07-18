"""Typer entry point for the BlackHole-only yel CLI."""

from __future__ import annotations

import re

import typer
from pydantic import ValidationError

from . import ui
from .audio import print_devices
from .config import Settings
from .errors import EXIT_INVALID_CONFIG
from .runner import run_turn

_DURATION_UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0}
_DURATION_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(ms|s|m)?\s*$")


def parse_duration(text: str) -> float:
    """Parse a human duration (``5s``, ``500ms``, ``2m``, or bare seconds)."""
    match = _DURATION_RE.match(text)
    if not match:
        raise ValueError(f"invalid duration {text!r} (try e.g. 5s, 500ms, 2m)")
    value = float(match.group(1)) * _DURATION_UNITS[match.group(2) or "s"]
    if value <= 0:
        raise ValueError(f"duration must be positive, got {text!r}")
    return value


app = typer.Typer(
    name="yel",
    help="Script spoken turns against a local voice agent.",
    no_args_is_help=True,
    add_completion=False,
    # Typer's Rich help renderer expands four option columns evenly across the
    # terminal, leaving large blank gaps and a narrow, heavily wrapped help
    # column on wide windows. Standard Click help is denser and easier to scan.
    rich_markup_mode=None,
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.command()
def speak(
    text: list[str] | None = typer.Argument(
        None,
        help="Text to speak to the agent. Multiple words are joined, so quoting "
        "is optional: `yel hello how are you`.",
    ),
    devices: bool = typer.Option(False, "--devices", help="List audio devices and exit."),
    out: str | None = typer.Option(
        None,
        "--out",
        help="BlackHole output device for generated speech (default: BlackHole 2ch).",
    ),
    listen: str | None = typer.Option(
        None,
        "--listen",
        help="BlackHole input device for the agent reply (default: BlackHole 2ch).",
    ),
    speakers: str | None = typer.Option(
        None,
        "--speakers",
        help="Play the agent's captured audio live on this output device.",
    ),
    speaker_output: bool | None = typer.Option(
        None,
        "--speaker-output/--no-speaker-output",
        help="Allow generated prompts and monitored replies to play on real speakers.",
    ),
    start_timeout: float | None = typer.Option(
        None, "--start-timeout", help="Seconds to wait for the agent to start speaking."
    ),
    end_silence: float | None = typer.Option(
        None, "--end-silence", help="Trailing silence (s) that marks the turn's end."
    ),
    timeout: str | None = typer.Option(
        None,
        "--timeout",
        help="Return after at most this long (e.g. 5s, 500ms, 2m), exit 0 even if "
        "the agent is still talking — for timed follow-ups / barge-in via && chaining.",
    ),
    vad: int | None = typer.Option(
        None,
        "--vad",
        min=0,
        max=3,
        help="WebRTC VAD aggressiveness for BlackHole input (0-3).",
        hidden=True,
    ),
    rms_threshold: float | None = typer.Option(
        None,
        "--rms-threshold",
        help="Speech-energy floor; loopbacks default to 0.001.",
        hidden=True,
    ),
    transcribe: bool | None = typer.Option(
        None,
        "--transcribe/--no-transcribe",
        help="Transcribe the reply locally with Apple Speech (enabled by default).",
    ),
) -> None:
    """Speak TEXT to a local voice agent and wait until it stops replying."""
    if devices:
        print_devices()
        raise typer.Exit(0)

    if not text:
        raise typer.BadParameter("Missing text to speak.")
    spoken_text = " ".join(text)

    response_timeout: float | None = None
    if timeout is not None:
        try:
            response_timeout = parse_duration(timeout)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--timeout") from exc

    settings = _build_settings(
        output_device=out,
        listen_device=listen,
        monitor_device=speakers,
        speaker_output=speaker_output,
        start_timeout=start_timeout,
        end_silence=end_silence,
        response_timeout=response_timeout,
        vad=vad,
        rms_threshold=rms_threshold,
        transcribe=transcribe,
    )
    raise typer.Exit(run_turn(text=spoken_text, settings=settings))


def _build_settings(**overrides: object) -> Settings:
    try:
        return Settings().apply_overrides(**overrides)
    except ValidationError as exc:
        ui.error(f"yel: invalid config: {exc}")
        raise typer.Exit(EXIT_INVALID_CONFIG) from exc


def main() -> None:
    """Run the single yel speak command."""
    app(prog_name="yel")


if __name__ == "__main__":
    main()
