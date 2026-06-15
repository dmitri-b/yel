"""Single-turn orchestration: speak a prompt, then wait for the agent's reply.

Flow per invocation:

    1. Resolve output/listen devices.
    2. Render the prompt to speech (macOS ``say``).
    3. Play it to the output device.
    4. Listen on the input/monitor device.
    5. Wait for the agent to start speaking, then for trailing silence.
    6. Optionally transcribe the captured reply with Deepgram (``--transcribe``).
    7. Return an exit code (see :mod:`agent_say.errors`).

Playback is sequential with listening: we send the prompt, then start
capturing. The intended setup routes our speech to the agent's input (e.g.
BlackHole) and the agent's voice to a separate monitor/mic. When the prompt is
routed to a virtual loopback the operator can't hear, we also mirror it onto a
real output (the --speakers monitor, or the system default) so it stays audible.
"""

from __future__ import annotations

import queue
import sys
import time

import numpy as np

from . import audio, tts
from .config import AgentSaySettings
from .errors import (
    EXIT_NO_SPEECH,
    EXIT_OK,
    EXIT_OVERALL_TIMEOUT,
    AgentSayError,
)
from .vad import SpeechState, TurnEndDetector, WebrtcVad

_STATE_EXIT = {
    SpeechState.ENDED: EXIT_OK,
    SpeechState.TIMED_OUT_OK: EXIT_OK,
    SpeechState.TIMEOUT_NO_SPEECH: EXIT_NO_SPEECH,
    SpeechState.TIMEOUT_OVERALL: EXIT_OVERALL_TIMEOUT,
}


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def run_turn(text: str, settings: AgentSaySettings) -> int:
    """Run one spoken turn. Returns a process exit code; never raises on the
    expected error paths (they are logged and mapped to codes)."""
    try:
        return _run_turn(text, settings)
    except AgentSayError as exc:
        _log(f"yel: {exc}")
        return exc.exit_code


def _run_turn(text: str, settings: AgentSaySettings) -> int:
    out_device = audio.resolve_output_device(settings.output_device)
    listen_device = audio.resolve_input_device(settings.listen_device)

    monitor = None
    monitor_device = None
    if settings.monitor_device is not None:
        monitor_device = audio.resolve_output_device(settings.monitor_device)
        monitor = audio.SpeakerMonitor(
            settings.sample_rate, monitor_device, settings.frame_samples
        )

    # When the prompt is routed to a silent virtual loopback (e.g. BlackHole),
    # the operator can't hear it. Mirror the prompt onto a real output so it's
    # audible: the --speakers monitor if set, else the system default speakers.
    prompt_mirror_device = None
    if audio.is_virtual_output(settings.output_device):
        prompt_mirror_device = (
            monitor_device
            if monitor_device is not None
            else audio.default_output_device()
        )
        if prompt_mirror_device is not None and prompt_mirror_device != out_device:
            _log("yel: out is a virtual device; mirroring prompt to real speakers.")
        else:
            prompt_mirror_device = None

    _log(f'yel: speaking: "{text}"')
    samples = tts.synthesize(text, settings.sample_rate)
    audio.play(
        samples, settings.sample_rate, out_device, mirror_device=prompt_mirror_device
    )

    if monitor is not None:
        _log("yel: listening for the agent's reply (monitoring on speakers)...")
    else:
        _log("yel: listening for the agent's reply...")
    state, clip = _listen_for_turn_end(
        listen_device, settings, monitor, record=settings.transcribe
    )

    if state is SpeechState.ENDED:
        _log("yel: agent finished.")
    elif state is SpeechState.TIMED_OUT_OK:
        _log(
            f"yel: returning after --timeout of {settings.response_timeout:g}s "
            "(agent may still be talking)."
        )
    elif state is SpeechState.TIMEOUT_NO_SPEECH:
        _log(
            f"yel: no agent speech within {settings.start_timeout:.0f}s start timeout."
        )
    elif state is SpeechState.TIMEOUT_OVERALL:
        _log(f"yel: overall timeout of {settings.overall_timeout:.0f}s reached.")

    if settings.transcribe and clip is not None and clip.size:
        _transcribe_and_print(clip, settings)
    return _STATE_EXIT[state]


def _transcribe_and_print(clip: np.ndarray, settings: AgentSaySettings) -> None:
    """Transcribe the agent's clip and print it to stdout. Best-effort: a
    failure is logged but does not change the turn's exit code."""
    from . import transcribe as dg

    _log("yel: transcribing agent reply with Deepgram...")
    try:
        text = dg.transcribe(
            clip,
            settings.sample_rate,
            api_key=settings.deepgram_api_key or "",
            model=settings.deepgram_model,
        )
    except dg.TranscriptionError as exc:
        _log(f"yel: transcription failed: {exc}")
        return
    if text:
        # Plain transcript on stdout so it can be captured (status logs are on stderr).
        print(text, flush=True)
    else:
        _log("yel: transcription returned no text.")


def _listen_for_turn_end(
    listen_device: int | None,
    settings: AgentSaySettings,
    monitor: "audio.SpeakerMonitor | None" = None,
    record: bool = False,
) -> tuple[SpeechState, np.ndarray | None]:
    import contextlib

    import sounddevice as sd

    detector = TurnEndDetector(
        start_timeout=settings.start_timeout,
        end_silence=settings.end_silence,
        min_speech=settings.min_speech,
        overall_timeout=settings.overall_timeout,
        response_timeout=settings.response_timeout,
    )
    vad = WebrtcVad(
        aggressiveness=settings.vad,
        sample_rate=settings.sample_rate,
        rms_threshold=settings.rms_threshold,
    )

    frames: "queue.Queue[np.ndarray]" = queue.Queue()
    frame_samples = settings.frame_samples

    def callback(indata, _frames, _time, status):  # noqa: ANN001
        if status:
            _log(f"yel: audio status: {status}")
        block = indata[:, 0].copy()
        if monitor is not None:
            monitor.feed(block)  # passthrough: make the agent audible on speakers
        frames.put(block)

    announced_speaking = False
    buffer = np.empty(0, dtype=np.float32)
    recorded: list[np.ndarray] = []
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
            if record:
                recorded.append(block)
            buffer = np.concatenate((buffer, block))
            # Consume exactly one VAD frame at a time (webrtcvad is strict).
            while buffer.size >= frame_samples and not detector.finished:
                frame, buffer = buffer[:frame_samples], buffer[frame_samples:]
                is_speech = vad.is_speech(frame)
                state = detector.update(is_speech, time.monotonic())
                if state is SpeechState.SPEAKING and not announced_speaking:
                    announced_speaking = True
                    _log("yel: agent started speaking...")

    audio_clip = np.concatenate(recorded) if recorded else None
    return detector.state, audio_clip
