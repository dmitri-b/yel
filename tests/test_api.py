import numpy as np

from agent_say import Speaker, speak
from agent_say import api, audio, tts


def test_speaker_resolves_device_once_and_plays_each_turn(monkeypatch):
    resolved = []
    played = []

    def fake_resolve(dev):
        resolved.append(dev)
        return 7  # pretend "BlackHole 2ch" -> device index 7

    monkeypatch.setattr(audio, "resolve_output_device", fake_resolve)
    monkeypatch.setattr(tts, "synthesize", lambda text, sr: np.full(sr // 10, 0.1, dtype=np.float32))
    monkeypatch.setattr(
        api.audio,
        "play",
        lambda samples, sr, device, mirror_device=None: played.append((sr, device, mirror_device, len(samples))),
    )

    spk = Speaker("BlackHole 2ch", sample_rate=16_000)
    spk.speak("first turn")
    spk.speak("second turn")

    # Device resolved exactly once (at construction), reused for every turn.
    assert resolved == ["BlackHole 2ch"]
    assert [p[1] for p in played] == [7, 7]
    assert all(p[0] == 16_000 and p[2] is None for p in played)


def test_speak_oneshot_uses_mirror(monkeypatch):
    played = {}
    monkeypatch.setattr(audio, "resolve_output_device", lambda d: 0 if d == "BlackHole 2ch" else 1)
    monkeypatch.setattr(tts, "synthesize", lambda text, sr: np.zeros(160, dtype=np.float32))
    monkeypatch.setattr(
        api.audio,
        "play",
        lambda samples, sr, device, mirror_device=None: played.update(device=device, mirror=mirror_device),
    )

    speak("hello", out_device="BlackHole 2ch", mirror_device="Speakers")
    assert played == {"device": 0, "mirror": 1}
