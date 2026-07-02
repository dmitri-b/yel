"""Tests for the pure turn-end state machine (no audio hardware involved)."""

import sys
from types import SimpleNamespace

import numpy as np

from agent_say.vad import SpeechState, TurnEndDetector, WebrtcVad


def _drive(detector, samples, frame_ms=30, t0=0.0):
    """Feed a sequence of booleans at fixed cadence; return final state."""
    dt = frame_ms / 1000.0
    t = t0
    state = detector.state
    for is_speech in samples:
        state = detector.update(is_speech, t)
        t += dt
        if detector.finished:
            break
    return state


def make(**kw):
    base = dict(start_timeout=5.0, end_silence=1.0, min_speech=0.3, overall_timeout=60.0)
    base.update(kw)
    return TurnEndDetector(**base)


def test_starts_after_min_speech():
    d = make(min_speech=0.3)
    # 0.3s of speech at 30ms frames = ~10 frames before it flips to SPEAKING.
    state = _drive(d, [True] * 20)
    assert state is SpeechState.SPEAKING


def test_brief_blip_does_not_start():
    d = make(min_speech=0.3)
    # A couple of speech frames then silence: below min_speech, stays WAITING.
    state = _drive(d, [True, True] + [False] * 5)
    assert state is SpeechState.WAITING


def test_full_turn_speak_then_silence_ends():
    d = make(min_speech=0.3, end_silence=1.0)
    # Speak ~1s, then ~1.2s of silence -> ENDED.
    seq = [True] * 34 + [False] * 40
    state = _drive(d, seq)
    assert state is SpeechState.ENDED


def test_silence_gap_shorter_than_end_silence_keeps_speaking():
    d = make(min_speech=0.3, end_silence=1.0)
    # Speak, brief 0.5s pause (mid-sentence), keep speaking -> not ended.
    seq = [True] * 20 + [False] * 16 + [True] * 20
    state = _drive(d, seq)
    assert state in (SpeechState.SPEAKING,)


def test_no_speech_times_out():
    d = make(start_timeout=2.0)
    # All silence past the start timeout.
    state = _drive(d, [False] * 200)
    assert state is SpeechState.TIMEOUT_NO_SPEECH


def test_overall_timeout_while_speaking():
    d = make(start_timeout=5.0, end_silence=100.0, overall_timeout=3.0)
    # Keep speaking forever; overall watchdog fires first.
    state = _drive(d, [True] * 1000)
    assert state is SpeechState.TIMEOUT_OVERALL


def test_response_timeout_caps_while_speaking():
    # Agent talks well past the 1.5s cap -> TIMED_OUT_OK (success), not still SPEAKING.
    d = make(min_speech=0.3, end_silence=100.0, response_timeout=1.5)
    state = _drive(d, [True] * 200)
    assert state is SpeechState.TIMED_OUT_OK


def test_response_timeout_preempts_no_speech_timeout():
    # Cap (1.5s) shorter than start_timeout (5s); agent never speaks ->
    # success cap wins so the caller exits 0 for chaining (not exit-2 no-speech).
    d = make(start_timeout=5.0, response_timeout=1.5)
    state = _drive(d, [False] * 200)
    assert state is SpeechState.TIMED_OUT_OK


def test_turn_end_before_cap_still_wins():
    # Agent finishes (ENDED) at ~2s, well before a 10s cap -> early return.
    d = make(min_speech=0.3, end_silence=1.0, response_timeout=10.0)
    state = _drive(d, [True] * 34 + [False] * 40)
    assert state is SpeechState.ENDED


def test_no_response_timeout_keeps_default_behavior():
    # Without a cap, a long reply just stays SPEAKING (no premature exit).
    d = make(min_speech=0.3, end_silence=100.0)  # response_timeout defaults to None
    state = _drive(d, [True] * 200)
    assert state is SpeechState.SPEAKING


def test_terminal_state_is_sticky():
    d = make(start_timeout=2.0)
    _drive(d, [False] * 200)
    assert d.finished
    # Further updates must not change a terminal state.
    assert d.update(True, 999.0) is SpeechState.TIMEOUT_NO_SPEECH


def test_uses_supplied_clock_not_wall_time():
    d = make(start_timeout=10.0, min_speech=0.3, end_silence=1.0)
    # Jump the clock: one speech frame then a far-future silent frame.
    d.update(True, 0.0)
    d.update(True, 0.1)
    d.update(True, 0.4)  # 0.4s >= min_speech -> SPEAKING
    assert d.state is SpeechState.SPEAKING
    d.update(False, 0.5)
    assert d.update(False, 2.0) is SpeechState.ENDED  # 1.5s silence >= end_silence


def test_webrtc_vad_uses_energy_fallback_for_loopback_audio(monkeypatch):
    class RejectingVad:
        def __init__(self, _aggressiveness):
            pass

        def is_speech(self, _pcm16, _sample_rate):
            return False

    monkeypatch.setitem(sys.modules, "webrtcvad", SimpleNamespace(Vad=RejectingVad))
    vad = WebrtcVad(aggressiveness=2, sample_rate=16_000, rms_threshold=0.01)

    assert vad.is_speech(np.full(480, 0.02, dtype=np.float32)) is True
    assert vad.is_speech(np.full(480, 0.005, dtype=np.float32)) is False
