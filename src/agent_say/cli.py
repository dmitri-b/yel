"""Typer entry points for yel.

Click can't host both a positional default action (``yel "text"``) and named
subcommands in the same group: the positional argument swallows the subcommand
token. So we keep two Typer apps and dispatch on the first token in ``main``:

* ``app``        — the default "speak" action (positional text + run options).
* ``admin_app``  — ``config show``/``config path`` and ``doctor``.
"""

from __future__ import annotations

import re
import sys

import typer
from pydantic import ValidationError

from . import ui
from .audio import print_devices
from .config import AgentSaySettings, find_dotenv
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
    help="Script spoken turns against a [bold]local voice agent[/bold].",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
    epilog="Also: 'yel config show', 'yel config path', 'yel doctor'.",
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
        None, "--out", help="Output device for generated speech."
    ),
    listen: str | None = typer.Option(
        None, "--listen", help="Input or monitor device to listen for the agent."
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
    overall_timeout: float | None = typer.Option(
        None, "--overall-timeout", help="Hard cap (s) on the whole turn."
    ),
    timeout: str | None = typer.Option(
        None,
        "--timeout",
        help="Return after at most this long (e.g. 5s, 500ms, 2m), exit 0 even if "
        "the agent is still talking — for timed follow-ups / barge-in via && chaining.",
    ),
    vad: int | None = typer.Option(
        None, "--vad", min=0, max=3, help="webrtcvad aggressiveness (0-3)."
    ),
    rms_threshold: float | None = typer.Option(
        None, "--rms-threshold", help="RMS floor below which audio is treated as silence."
    ),
    transcribe: bool | None = typer.Option(
        None,
        "--transcribe/--no-transcribe",
        help="Transcribe the agent's reply with Deepgram.",
    ),
    deepgram_model: str | None = typer.Option(
        None, "--deepgram-model", help="Deepgram model to use (default: nova-3)."
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
        overall_timeout=overall_timeout,
        response_timeout=response_timeout,
        vad=vad,
        rms_threshold=rms_threshold,
        transcribe=transcribe,
        deepgram_model=deepgram_model,
    )
    raise typer.Exit(run_turn(text=spoken_text, settings=settings))


admin_app = typer.Typer(
    name="yel",
    help="yel maintenance commands.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)
config_app = typer.Typer(
    help="Inspect resolved configuration.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)
admin_app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """Print the resolved settings (env + .env + defaults)."""
    settings = _load_settings()
    rows: list[tuple[str, object]] = []
    for key, value in settings.model_dump().items():
        if key == "deepgram_api_key" and value:
            value = "***" + str(value)[-4:]  # mask the secret
        rows.append((key, value))
    ui.print_settings_table(rows)


@config_app.command("path")
def config_path() -> None:
    """Print the .env file that settings are loaded from, if present."""
    from pathlib import Path

    env_path = Path(".env").resolve()
    ui.print_path_status(env_path, found=env_path.exists())


@admin_app.command("doctor")
def doctor() -> None:
    """Check that the TTS backend and an audio output device are available."""
    from . import tts

    ok = True
    if tts.is_available():
        try:
            voice, locale = tts.voice_for_language()
            ui.print_check(
                "TTS backend", ok=True, detail=f"macOS 'say' available; {voice} ({locale}) installed"
            )
        except Exception as exc:
            ok = False
            ui.print_check("TTS backend", ok=False, detail=str(exc))
    else:
        ok = False
        ui.print_check("TTS backend", ok=False, detail="macOS 'say' not available")

    try:
        print_devices()
    except Exception as exc:  # pragma: no cover - hardware dependent
        ok = False
        ui.print_check("Audio devices", ok=False, detail=f"could not query devices: {exc}")

    raise typer.Exit(0 if ok else 1)


def _load_settings() -> AgentSaySettings:
    try:
        return AgentSaySettings(_env_file=find_dotenv())  # type: ignore[call-arg]
    except ValidationError as exc:
        ui.error(f"yel: invalid config: {exc}")
        raise typer.Exit(EXIT_INVALID_CONFIG) from exc


def _build_settings(**overrides: object) -> AgentSaySettings:
    settings = _load_settings()
    try:
        return settings.apply_overrides(**overrides)
    except ValidationError as exc:
        ui.error(f"yel: invalid config: {exc}")
        raise typer.Exit(EXIT_INVALID_CONFIG) from exc


_ADMIN = {"config", "doctor"}


def main() -> None:
    """Dispatch: admin subcommands go to ``admin_app``; everything else speaks."""
    argv = sys.argv[1:]
    if not argv:
        app(args=["--help"], prog_name="yel")
    elif argv[0] in _ADMIN:
        admin_app(args=argv, prog_name="yel")
    else:
        app()


if __name__ == "__main__":
    main()
