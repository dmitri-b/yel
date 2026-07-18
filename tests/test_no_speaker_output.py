import numpy as np

from yel import audio, runner, tts
from yel.config import Settings


def test_no_speaker_output_disables_virtual_prompt_mirror(monkeypatch):
    calls = {}

    monkeypatch.setattr(audio, "resolve_output_device", lambda d: 0)
    monkeypatch.setattr(audio, "resolve_input_device", lambda d: 0)
    monkeypatch.setattr(audio, "is_virtual_output", lambda d: True)
    monkeypatch.setattr(
        tts, "synthesize", lambda text, sample_rate: np.zeros(160, dtype=np.float32)
    )
    monkeypatch.setattr(
        audio,
        "play",
        lambda samples, sample_rate, device, mirror_device=None: calls.setdefault(
            "mirror_device", mirror_device
        ),
    )
    monkeypatch.setattr(
        runner,
        "_listen_for_turn_end",
        lambda listen_device, settings, monitor: (
            runner.SpeechState.ENDED,
            None,
            0.25,
        ),
    )

    settings = Settings(
        output_device="BlackHole 2ch",
        listen_device="BlackHole 2ch",
        speaker_output=False,
    )

    assert runner.run_turn("quiet test", settings) == 0
    assert calls["mirror_device"] is None
