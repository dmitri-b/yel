import pytest
from pydantic import ValidationError

from agent_say.config import AgentSaySettings


def test_defaults(monkeypatch):
    # Ensure no AGENT_SAY_* env vars leak in from the host.
    for key in list(__import__("os").environ):
        if key.startswith("AGENT_SAY_"):
            monkeypatch.delenv(key, raising=False)
    s = AgentSaySettings(_env_file=None)
    assert s.output_device is None
    assert s.listen_device is None
    assert s.speaker_output is True
    assert s.start_timeout == 30.0
    assert s.end_silence == 1.2
    assert s.vad == 2
    assert s.sample_rate == 16_000
    assert s.frame_samples == 480


def test_env_aliases(monkeypatch):
    monkeypatch.setenv("AGENT_SAY_OUT", "BlackHole 2ch")
    monkeypatch.setenv("AGENT_SAY_LISTEN", "MacBook Pro Microphone")
    monkeypatch.setenv("AGENT_SAY_END_SILENCE", "0.8")
    monkeypatch.setenv("AGENT_SAY_VAD", "3")
    s = AgentSaySettings(_env_file=None)
    assert s.output_device == "BlackHole 2ch"
    assert s.listen_device == "MacBook Pro Microphone"
    assert s.end_silence == 0.8
    assert s.vad == 3


def test_deepgram_key_from_plain_env(monkeypatch):
    # The key uses its conventional name, not the AGENT_SAY_ prefix.
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg-secret")
    s = AgentSaySettings(_env_file=None)
    assert s.deepgram_api_key == "dg-secret"
    assert s.transcribe is False
    assert s.deepgram_model == "nova-3"


def test_transcribe_env_toggle(monkeypatch):
    monkeypatch.setenv("AGENT_SAY_TRANSCRIBE", "true")
    s = AgentSaySettings(_env_file=None)
    assert s.transcribe is True


def test_speaker_output_env_toggle(monkeypatch):
    monkeypatch.setenv("AGENT_SAY_SPEAKER_OUTPUT", "false")
    s = AgentSaySettings(_env_file=None)
    assert s.speaker_output is False


def test_speakers_alias(monkeypatch):
    monkeypatch.setenv("AGENT_SAY_SPEAKERS", "MacBook Pro Speakers")
    s = AgentSaySettings(_env_file=None)
    assert s.monitor_device == "MacBook Pro Speakers"


def test_long_form_output_alias(monkeypatch):
    monkeypatch.delenv("AGENT_SAY_OUT", raising=False)
    monkeypatch.setenv("AGENT_SAY_OUTPUT_DEVICE", "Speakers")
    s = AgentSaySettings(_env_file=None)
    assert s.output_device == "Speakers"


def test_apply_overrides_precedence(monkeypatch):
    monkeypatch.setenv("AGENT_SAY_VAD", "1")
    s = AgentSaySettings(_env_file=None)
    assert s.vad == 1
    # CLI flag wins; None overrides are ignored.
    overridden = s.apply_overrides(vad=3, end_silence=None, output_device="X")
    assert overridden.vad == 3
    assert overridden.end_silence == s.end_silence
    assert overridden.output_device == "X"
    # Original is untouched.
    assert s.vad == 1


def test_vad_bounds():
    with pytest.raises(ValidationError):
        AgentSaySettings(_env_file=None, vad=5)
    with pytest.raises(ValidationError):
        AgentSaySettings(_env_file=None, vad=-1)


def test_invalid_frame_and_rate():
    with pytest.raises(ValidationError):
        AgentSaySettings(_env_file=None, frame_ms=25)
    with pytest.raises(ValidationError):
        AgentSaySettings(_env_file=None, sample_rate=44_100)


def test_positive_constraints():
    with pytest.raises(ValidationError):
        AgentSaySettings(_env_file=None, rms_threshold=0)
    with pytest.raises(ValidationError):
        AgentSaySettings(_env_file=None, end_silence=-1)
