"""Integration of the transcribe path in run_turn (no audio hardware, no network)."""

import numpy as np

from yel import audio, runner, transcribe, tts
from yel.config import Settings
from yel.vad import SpeechState


def _patch_audio(monkeypatch):
    monkeypatch.setattr(audio, "resolve_output_device", lambda d: None)
    monkeypatch.setattr(audio, "resolve_input_device", lambda d: None)
    monkeypatch.setattr(tts, "synthesize", lambda text, sr: np.zeros(10, dtype=np.float32))
    monkeypatch.setattr(audio, "play", lambda samples, sr, dev, mirror_device=None: None)


def test_transcribes_and_prints_on_success(monkeypatch, capsys):
    _patch_audio(monkeypatch)
    clip = np.ones(480, dtype=np.float32)
    seen = {}

    def fake_transcribe(samples, sr, *, locale=transcribe.DEFAULT_LOCALE, timeout=60.0):
        seen["samples"] = samples
        seen["sample_rate"] = sr
        seen["locale"] = locale
        return "a quick greek salad"

    monkeypatch.setattr(
        runner,
        "_listen_for_turn_end",
        lambda *_args, **_kwargs: (SpeechState.ENDED, clip, 1.234),
    )
    monkeypatch.setattr(transcribe, "transcribe", fake_transcribe)

    settings = Settings(transcribe=True)
    code = runner.run_turn("recipe?", settings)
    out = capsys.readouterr().out
    assert code == 0
    assert "a quick greek salad" in out  # transcript on stdout
    assert seen["sample_rate"] == 16_000
    assert seen["locale"] == transcribe.DEFAULT_LOCALE
    assert seen["samples"] is clip


def test_transcription_failure_is_nonfatal(monkeypatch, capsys):
    _patch_audio(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_listen_for_turn_end",
        lambda *a, **k: (SpeechState.ENDED, np.ones(480, dtype=np.float32), 0.75),
    )

    def fail(*args, **kwargs):
        raise transcribe.TranscriptionError("nope")

    monkeypatch.setattr(transcribe, "transcribe", fail)
    settings = Settings(transcribe=True)
    code = runner.run_turn("hi", settings)
    # Turn still succeeded; transcription failure must not change the exit code.
    assert code == 0
    assert capsys.readouterr().out.strip() == ""


def test_no_transcription_when_disabled(monkeypatch, capsys):
    _patch_audio(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_listen_for_turn_end",
        lambda *a, **k: (SpeechState.ENDED, np.ones(480, dtype=np.float32), 0.5),
    )

    def must_not_call(*a, **k):
        raise AssertionError("native transcription should not run when disabled")

    monkeypatch.setattr(transcribe, "transcribe", must_not_call)
    settings = Settings(transcribe=False)
    assert runner.run_turn("hi", settings) == 0


def test_virtual_listen_device_uses_lower_rms_floor(monkeypatch):
    _patch_audio(monkeypatch)
    seen = {}

    def fake_listen(_device, settings, *_args, **_kwargs):
        seen["rms_threshold"] = settings.rms_threshold
        return SpeechState.ENDED, None, 0.4

    monkeypatch.setattr(runner, "_listen_for_turn_end", fake_listen)

    settings = Settings(listen_device="BlackHole 2ch")
    assert runner.run_turn("hi", settings) == 0
    assert seen["rms_threshold"] == runner.VIRTUAL_LISTEN_RMS_THRESHOLD


def test_explicit_rms_floor_is_not_changed_for_virtual_listen_device(monkeypatch):
    _patch_audio(monkeypatch)
    seen = {}

    def fake_listen(_device, settings, *_args, **_kwargs):
        seen["rms_threshold"] = settings.rms_threshold
        return SpeechState.ENDED, None, 0.4

    monkeypatch.setattr(runner, "_listen_for_turn_end", fake_listen)

    settings = Settings(
        listen_device="BlackHole 2ch",
        rms_threshold=0.004,
    )
    assert runner.run_turn("hi", settings) == 0
    assert seen["rms_threshold"] == 0.004


def test_blackhole_listen_always_enables_energy_fallback(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        runner,
        "WebrtcVad",
        lambda **kwargs: seen.update(kwargs) or object(),
    )

    runner._build_vad(Settings(listen_device="BlackHole 2ch"))
    assert seen["energy_fallback"] is True


def test_reports_ttfa_for_each_successful_turn(monkeypatch):
    _patch_audio(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_listen_for_turn_end",
        lambda *a, **k: (SpeechState.ENDED, None, 1.234),
    )
    messages = []
    monkeypatch.setattr(runner, "_log", lambda message, **_kwargs: messages.append(message))

    assert runner.run_turn("hi", Settings()) == 0
    assert "yel: TTFA: 1234 ms" in messages


def test_reports_unavailable_ttfa_when_agent_never_speaks(monkeypatch):
    _patch_audio(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_listen_for_turn_end",
        lambda *a, **k: (SpeechState.TIMEOUT_NO_SPEECH, None, None),
    )
    messages = []
    monkeypatch.setattr(runner, "_log", lambda message, **_kwargs: messages.append(message))

    assert runner.run_turn("hi", Settings()) != 0
    assert "yel: TTFA: n/a" in messages
