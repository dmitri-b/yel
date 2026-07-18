"""Single-turn orchestration: speak a prompt, then wait for the agent's reply.

Flow per invocation:

    1. Resolve output/listen devices.
    2. Render the prompt to speech (macOS ``say``).
    3. Play it to the output device.
    4. Listen on the input/monitor device.
    5. Wait for the agent to start speaking, then for trailing silence.
    6. Transcribe the captured reply on-device with macOS ``SpeechAnalyzer``.
    7. Return an exit code (see :mod:`yel.errors`).

Playback is sequential with listening: we send the prompt, then start
capturing. Holding a capture stream open on the listen device while playing
would be faster, but on a shared virtual loopback (BlackHole out AND listen)
CoreAudio intermittently fails one of the streams with kAudioUnitErr_
CannotDoInCurrentContext, silently killing the capture — so we keep the
streams strictly sequential and rely on the turn detector's gap tolerance to
catch replies whose onset lands in the short gap. Yel requires BlackHole for
both directions: the agent listens to Yel on the loopback and mirrors its reply
back to that loopback. Real speakers are an optional monitor only; there is no
physical-microphone capture path.
"""

from __future__ import annotations

import queue
import time
import numpy as np

from . import audio, tts, ui
from .config import Settings
from .errors import (
    EXIT_NO_SPEECH,
    EXIT_OK,
    YelError,
)
from .vad import SpeechState, TurnEndDetector, WebrtcVad

_STATE_EXIT = {
    SpeechState.ENDED: EXIT_OK,
    SpeechState.TIMED_OUT_OK: EXIT_OK,
    SpeechState.TIMEOUT_NO_SPEECH: EXIT_NO_SPEECH,
}
DEFAULT_RMS_THRESHOLD = Settings.model_fields["rms_threshold"].default
VIRTUAL_LISTEN_RMS_THRESHOLD = 0.001


def _log(msg: str, *, style: str = "cyan") -> None:
    ui.status(msg, style=style)


def run_turn(text: str, settings: Settings) -> int:
    """Run one spoken turn. Returns a process exit code; never raises on the
    expected error paths (they are logged and mapped to codes)."""
    try:
        return _run_turn(text, settings)
    except YelError as exc:
        _log(f"yel: {exc}", style="bold red")
        return exc.exit_code


def _run_turn(text: str, settings: Settings) -> int:
    out_device = audio.resolve_output_device(settings.output_device)
    listen_device = audio.resolve_input_device(settings.listen_device)
    listen_settings = _settings_for_listen_device(settings)

    monitor = None
    monitor_device = None
    if settings.monitor_device is not None and settings.speaker_output:
        monitor_device = audio.resolve_output_device(settings.monitor_device)
        monitor = audio.SpeakerMonitor(settings.sample_rate, monitor_device, settings.frame_samples)
    elif settings.monitor_device is not None:
        _log(
            "yel: --no-speaker-output set; not monitoring agent audio on speakers.",
            style="yellow",
        )

    # When the prompt is routed to a silent virtual loopback (e.g. BlackHole),
    # the operator can't hear it. Mirror the prompt onto a real output so it's
    # audible: the --speakers monitor if set, else the system default speakers.
    prompt_mirror_device = None
    if settings.speaker_output:
        prompt_mirror_device = (
            monitor_device if monitor_device is not None else audio.default_output_device()
        )
        if prompt_mirror_device is None or prompt_mirror_device == out_device:
            prompt_mirror_device = None

    _log(f'yel: speaking: "{text}"')
    samples = tts.synthesize(text, settings.sample_rate)
    audio.play(samples, settings.sample_rate, out_device, mirror_device=prompt_mirror_device)

    state, clip, ttfa_s = _listen_for_turn_end(
        listen_device,
        listen_settings,
        monitor,
    )
    if ttfa_s is None:
        _log("yel: TTFA: n/a", style="yellow")
    else:
        _log(f"yel: TTFA: {ttfa_s * 1000:.0f} ms", style="bold green")

    if state is SpeechState.TIMED_OUT_OK:
        _log(
            f"yel: returning after --timeout of {settings.response_timeout:g}s "
            "(agent may still be talking).",
            style="yellow",
        )
    elif state is SpeechState.TIMEOUT_NO_SPEECH:
        _log(
            f"yel: no agent speech within {settings.start_timeout:.0f}s start timeout.",
            style="bold red",
        )
    if settings.transcribe and clip is not None and state is not SpeechState.TIMEOUT_NO_SPEECH:
        _transcribe_clip(clip, listen_settings)
    return _STATE_EXIT[state]


def _settings_for_listen_device(settings: Settings) -> Settings:
    if settings.rms_threshold == DEFAULT_RMS_THRESHOLD:
        return settings.model_copy(update={"rms_threshold": VIRTUAL_LISTEN_RMS_THRESHOLD})
    return settings


def _build_vad(settings: Settings) -> WebrtcVad:
    return WebrtcVad(
        aggressiveness=settings.vad,
        sample_rate=settings.sample_rate,
        rms_threshold=settings.rms_threshold,
        energy_fallback=True,
    )


def _transcribe_clip(clip: np.ndarray, settings: Settings) -> None:
    """Print Apple's local transcript. Recognition failures remain non-fatal."""
    from . import transcribe as native_asr

    try:
        text = native_asr.transcribe(
            clip,
            settings.sample_rate,
            locale=settings.transcription_locale,
        )
    except native_asr.TranscriptionError as exc:
        _log(f"yel: transcription failed: {exc}", style="bold red")
        return
    if text:
        # Plain transcript on stdout so it can be captured (status logs are on stderr).
        print(text, flush=True)
    else:
        _log("yel: transcription returned no text.", style="yellow")


def _listen_for_turn_end(
    listen_device: int | None,
    settings: Settings,
    monitor: "audio.SpeakerMonitor | None" = None,
) -> tuple[SpeechState, np.ndarray | None, float | None]:
    import contextlib

    import sounddevice as sd

    detector = TurnEndDetector(
        start_timeout=settings.start_timeout,
        end_silence=settings.end_silence,
        min_speech=settings.min_speech,
        response_timeout=settings.response_timeout,
        gap_tolerance=settings.gap_tolerance,
    )
    vad = _build_vad(settings)

    frames: "queue.Queue[np.ndarray]" = queue.Queue()
    frame_samples = settings.frame_samples
    captured: list[np.ndarray] = []

    def callback(indata, _frames, _time, status):  # noqa: ANN001
        if status:
            _log(f"yel: audio status: {status}", style="yellow")
        block = indata[:, 0].copy()
        if monitor is not None:
            monitor.feed(block)  # passthrough: make the agent audible on speakers
        frames.put(block)

    buffer = np.empty(0, dtype=np.float32)
    wait_started_at = time.monotonic()
    with contextlib.ExitStack() as stack:
        if monitor is not None:
            stack.enter_context(monitor)
        stack.enter_context(
            sd.InputStream(
                samplerate=settings.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=frame_samples,
                device=listen_device,
                callback=callback,
            )
        )
        while not detector.finished:
            try:
                block = frames.get(timeout=0.5)
            except queue.Empty:
                # No audio arrived; still let the watchdogs advance.
                detector.update(False, time.monotonic())
                continue
            captured.append(block)
            buffer = np.concatenate((buffer, block))
            # Consume exactly one VAD frame at a time (webrtcvad is strict).
            while buffer.size >= frame_samples and not detector.finished:
                frame, buffer = buffer[:frame_samples], buffer[frame_samples:]
                is_speech = vad.is_speech(frame)
                detector.update(is_speech, time.monotonic())

    ttfa_s = (
        detector.speech_started_at - wait_started_at
        if detector.speech_started_at is not None
        else None
    )
    clip = np.concatenate(captured) if captured else None
    return detector.state, clip, ttfa_s
