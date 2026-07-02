"""Integration of the transcribe path in run_turn (no audio hardware, no network)."""

import numpy as np

from agent_say import audio, runner, transcribe, tts
from agent_say.config import AgentSaySettings
from agent_say.vad import SpeechState


def _patch_audio(monkeypatch):
    monkeypatch.setattr(audio, "resolve_output_device", lambda d: None)
    monkeypatch.setattr(audio, "resolve_input_device", lambda d: None)
    monkeypatch.setattr(tts, "synthesize", lambda text, sr: np.zeros(10, dtype=np.float32))
    monkeypatch.setattr(audio, "play", lambda samples, sr, dev, mirror_device=None: None)


def test_transcribes_and_prints_on_success(monkeypatch, capsys):
    _patch_audio(monkeypatch)
    clip = np.ones(480, dtype=np.float32)
    monkeypatch.setattr(
        runner, "_listen_for_turn_end", lambda *a, **k: (SpeechState.ENDED, clip)
    )
    seen = {}

    def fake_transcribe(samples, sr, *, api_key, model, timeout=30.0):
        seen["api_key"] = api_key
        seen["model"] = model
        return "a quick greek salad"

    monkeypatch.setattr(transcribe, "transcribe", fake_transcribe)

    settings = AgentSaySettings(
        _env_file=None, transcribe=True, deepgram_api_key="k", deepgram_model="nova-3"
    )
    code = runner.run_turn("recipe?", settings)
    out = capsys.readouterr().out
    assert code == 0
    assert "a quick greek salad" in out  # transcript on stdout
    assert seen == {"api_key": "k", "model": "nova-3"}


def test_transcription_failure_is_nonfatal(monkeypatch, capsys):
    _patch_audio(monkeypatch)
    clip = np.ones(480, dtype=np.float32)
    monkeypatch.setattr(
        runner, "_listen_for_turn_end", lambda *a, **k: (SpeechState.ENDED, clip)
    )

    def boom(*a, **k):
        raise transcribe.TranscriptionError("nope")

    monkeypatch.setattr(transcribe, "transcribe", boom)
    settings = AgentSaySettings(_env_file=None, transcribe=True, deepgram_api_key="k")
    code = runner.run_turn("hi", settings)
    # Turn still succeeded; transcription failure must not change the exit code.
    assert code == 0
    assert capsys.readouterr().out.strip() == ""


def test_no_transcription_when_disabled(monkeypatch, capsys):
    _patch_audio(monkeypatch)
    monkeypatch.setattr(
        runner,
        "_listen_for_turn_end",
        lambda *a, **k: (SpeechState.ENDED, None),
    )

    def must_not_call(*a, **k):
        raise AssertionError("transcribe should not be called when disabled")

    monkeypatch.setattr(transcribe, "transcribe", must_not_call)
    settings = AgentSaySettings(_env_file=None, transcribe=False)
    assert runner.run_turn("hi", settings) == 0


def test_virtual_listen_device_uses_lower_rms_floor(monkeypatch):
    _patch_audio(monkeypatch)
    seen = {}

    def fake_listen(_device, settings, *_args, **_kwargs):
        seen["rms_threshold"] = settings.rms_threshold
        return SpeechState.ENDED, None

    monkeypatch.setattr(runner, "_listen_for_turn_end", fake_listen)

    settings = AgentSaySettings(_env_file=None, listen_device="BlackHole 2ch")
    assert runner.run_turn("hi", settings) == 0
    assert seen["rms_threshold"] == runner.VIRTUAL_LISTEN_RMS_THRESHOLD


def test_explicit_rms_floor_is_not_changed_for_virtual_listen_device(monkeypatch):
    _patch_audio(monkeypatch)
    seen = {}

    def fake_listen(_device, settings, *_args, **_kwargs):
        seen["rms_threshold"] = settings.rms_threshold
        return SpeechState.ENDED, None

    monkeypatch.setattr(runner, "_listen_for_turn_end", fake_listen)

    settings = AgentSaySettings(
        _env_file=None,
        listen_device="BlackHole 2ch",
        rms_threshold=0.004,
    )
    assert runner.run_turn("hi", settings) == 0
    assert seen["rms_threshold"] == 0.004
