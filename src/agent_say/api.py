"""Programmatic, in-process API for driving spoken turns.

Test harnesses that script many turns against a local voice agent — and detect
the agent's reply some other way (e.g. by tailing the agent's own JSONL log) —
should NOT spawn the ``yel`` CLI per turn. Each CLI process re-initializes
CoreAudio and re-acquires the output device, which is flaky on a shared virtual
loopback (BlackHole): the second and later prompts often never reach the agent's
mic. Use a persistent :class:`Speaker` instead — it resolves the output device
once and renders + plays every prompt from the SAME process.

Example:
    from agent_say.api import Speaker
    spk = Speaker("BlackHole 2ch")          # resolve device once
    spk.speak("what is the weather in Tokyo")
    spk.speak("tell me a joke")             # same process, same stream backend
"""
from __future__ import annotations

import numpy as np

from . import audio, tts

DEFAULT_OUT_DEVICE = "BlackHole 2ch"
DEFAULT_SAMPLE_RATE = 16_000


class Speaker:
    """Persistent in-process speaker that plays prompts to one output device.

    ``out_device`` is the device the agent listens on (e.g. ``"BlackHole 2ch"``).
    ``mirror_device`` optionally plays each prompt on a second (real) output so a
    human operator can hear it too; pass ``None`` for headless/automated runs.
    """

    def __init__(
        self,
        out_device: str | int | None = DEFAULT_OUT_DEVICE,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        mirror_device: str | int | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.out_device = audio.resolve_output_device(out_device)
        self.mirror_device = (
            audio.resolve_output_device(mirror_device)
            if mirror_device is not None
            else None
        )

    def speak(self, text: str) -> np.ndarray:
        """Render ``text`` to speech and play it into the output device (blocking
        until playback finishes). Returns the mono float32 samples."""
        samples = tts.synthesize(text, self.sample_rate)
        audio.play(
            samples,
            self.sample_rate,
            self.out_device,
            mirror_device=self.mirror_device,
        )
        return samples


def speak(
    text: str,
    *,
    out_device: str | int | None = DEFAULT_OUT_DEVICE,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    mirror_device: str | int | None = None,
) -> np.ndarray:
    """One-shot convenience wrapper around :meth:`Speaker.speak`. Prefer a
    long-lived :class:`Speaker` when speaking multiple turns."""
    return Speaker(
        out_device, sample_rate=sample_rate, mirror_device=mirror_device
    ).speak(text)
