"""Agent-speech turn detection.

Two pieces, deliberately separated so the timing logic is testable without any
audio hardware:

* ``TurnEndDetector`` — a pure state machine driven by ``(is_speech, now)``
  updates. It decides when the agent started talking and when it has gone quiet
  long enough to count the turn as finished.
* ``WebrtcVad`` — a thin wrapper over ``webrtcvad`` that classifies a single PCM
  frame, gated by an RMS floor to ignore low-level background noise.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


class SpeechState(str, Enum):
    WAITING = "waiting"  # waiting for the agent to start speaking
    SPEAKING = "speaking"  # agent is actively speaking
    ENDED = "ended"  # agent finished (trailing silence reached)
    TIMEOUT_NO_SPEECH = "timeout_no_speech"  # never started before start_timeout
    TIMEOUT_OVERALL = "timeout_overall"  # overall_timeout elapsed
    TIMED_OUT_OK = "timed_out_ok"  # response_timeout cap reached (success, exit 0)


_TERMINAL = {
    SpeechState.ENDED,
    SpeechState.TIMEOUT_NO_SPEECH,
    SpeechState.TIMEOUT_OVERALL,
    SpeechState.TIMED_OUT_OK,
}


class TurnEndDetector:
    """Decide when an agent's spoken turn has ended.

    Feed it ``update(is_speech, now)`` once per audio frame. It returns the
    current :class:`SpeechState`; once a terminal state is returned it sticks.

    * The agent is considered to have *started* once speech activity spans at
      least ``min_speech`` seconds. Silence dips up to ``gap_tolerance`` do not
      break the run — agent replies over digital loopbacks (BlackHole) arrive
      as short vocoder bursts separated by exact-zero word gaps, so requiring
      strictly contiguous speech would miss short replies entirely. To keep
      stray clicks from counting as a start, at least half the qualifying span
      must be actual speech frames.
    * Once speaking, the turn *ends* after ``end_silence`` seconds with no speech.
    * If no start happens within ``start_timeout`` seconds -> TIMEOUT_NO_SPEECH.
    * If the whole turn exceeds ``overall_timeout`` seconds -> TIMEOUT_OVERALL.
    * If ``response_timeout`` is set and elapses first, -> TIMED_OUT_OK: a
      deliberate *success* cap (exit 0) so the caller can return early and chain
      a timed follow-up, even if the agent is still talking.

    All times are caller-supplied (seconds, monotonic), so tests drive it with
    synthetic clocks.
    """

    def __init__(
        self,
        *,
        start_timeout: float,
        end_silence: float,
        min_speech: float,
        overall_timeout: float,
        response_timeout: float | None = None,
        gap_tolerance: float = 0.3,
    ) -> None:
        self.start_timeout = start_timeout
        self.end_silence = end_silence
        self.min_speech = min_speech
        self.overall_timeout = overall_timeout
        self.response_timeout = response_timeout
        self.gap_tolerance = gap_tolerance

        self.state = SpeechState.WAITING
        self.speech_started_at: float | None = None
        self._t0: float | None = None
        self._speech_run_start: float | None = None
        self._last_speech: float | None = None
        self._speech_accum = 0.0
        self._prev_now: float | None = None
        self._prev_speech = False

    @property
    def finished(self) -> bool:
        return self.state in _TERMINAL

    def update(self, is_speech: bool, now: float) -> SpeechState:
        if self.finished:
            return self.state
        if self._t0 is None:
            self._t0 = now

        # Success cap: return early (exit 0) once response_timeout elapses,
        # whichever comes first vs. the turn ending. Checked before the
        # waiting/speaking branch so it pre-empts the no-speech start_timeout.
        if self.response_timeout is not None and now - self._t0 >= self.response_timeout:
            self.state = SpeechState.TIMED_OUT_OK
            return self.state

        # Overall watchdog applies in every non-terminal state.
        if now - self._t0 >= self.overall_timeout:
            self.state = SpeechState.TIMEOUT_OVERALL
            return self.state

        if self.state is SpeechState.WAITING:
            self._update_waiting(is_speech, now)
        elif self.state is SpeechState.SPEAKING:
            self._update_speaking(is_speech, now)
        self._prev_now = now
        self._prev_speech = is_speech
        return self.state

    def _update_waiting(self, is_speech: bool, now: float) -> None:
        assert self._t0 is not None
        if is_speech:
            if self._speech_run_start is None:
                self._speech_run_start = now
                self._speech_accum = 0.0
            elif self._prev_speech and self._prev_now is not None:
                self._speech_accum += now - self._prev_now
            self._last_speech = now
        elif self._speech_run_start is not None:
            assert self._last_speech is not None
            # A dip longer than gap_tolerance is a real gap: drop the candidate
            # run. Shorter dips (word gaps, zero-filled chunk seams) are bridged.
            if now - self._last_speech > self.gap_tolerance:
                self._speech_run_start = None

        if self._speech_run_start is not None:
            span = now - self._speech_run_start
            if span >= self.min_speech and self._speech_accum >= self.min_speech / 2:
                self.speech_started_at = self._speech_run_start
                self.state = SpeechState.SPEAKING
                return
        if not is_speech and now - self._t0 >= self.start_timeout:
            self.state = SpeechState.TIMEOUT_NO_SPEECH

    def _update_speaking(self, is_speech: bool, now: float) -> None:
        if is_speech:
            self._last_speech = now
            return
        assert self._last_speech is not None
        if now - self._last_speech >= self.end_silence:
            self.state = SpeechState.ENDED


class WebrtcVad:
    """Classify a single PCM frame as speech, gated by an RMS floor.

    WebRTC VAD is tuned for human microphone speech. Local voice agents can
    produce vocoder audio that is clearly audible and transcribable but rejected
    by WebRTC, especially through virtual loopback devices. Once the RMS floor is
    crossed, treat sustained monitor energy as speech so scripted turns do not
    wait until the start timeout despite having captured a real reply.
    """

    def __init__(self, *, aggressiveness: int, sample_rate: int, rms_threshold: float) -> None:
        import webrtcvad

        self._vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.rms_threshold = rms_threshold

    def is_speech(self, frame: "np.ndarray") -> bool:
        """``frame`` is mono float32 in [-1, 1], exactly one VAD frame long."""
        import numpy as np

        rms = float(np.sqrt(np.mean(np.square(frame)))) if frame.size else 0.0
        if rms < self.rms_threshold:
            return False
        pcm16 = np.clip(frame * 32768.0, -32768, 32767).astype("<i2").tobytes()
        return self._vad.is_speech(pcm16, self.sample_rate) or rms >= self.rms_threshold
