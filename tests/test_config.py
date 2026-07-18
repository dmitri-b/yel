import pytest
from pydantic import ValidationError

from yel.config import Settings


def test_defaults_are_blackhole_only():
    s = Settings()
    assert s.output_device == "BlackHole 2ch"
    assert s.listen_device == "BlackHole 2ch"
    assert s.speaker_output is True
    assert s.start_timeout == 30.0
    assert s.end_silence == 1.2
    assert s.vad == 2
    assert s.sample_rate == 16_000
    assert s.frame_samples == 480
    assert s.transcribe is True
    assert s.transcription_locale == "en-US"


def test_other_blackhole_variants_are_allowed():
    settings = Settings(
        output_device="BlackHole 16ch",
        listen_device="BlackHole 64ch",
    )
    assert settings.output_device == "BlackHole 16ch"
    assert settings.listen_device == "BlackHole 64ch"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("output_device", "MacBook Pro Speakers"),
        ("listen_device", "MacBook Pro Microphone"),
        ("output_device", None),
        ("listen_device", None),
    ],
)
def test_physical_and_system_default_routes_are_rejected(field, value):
    with pytest.raises(ValidationError, match="BlackHole"):
        Settings(**{field: value})


def test_apply_overrides_precedence():
    s = Settings(vad=1)
    assert s.vad == 1
    # CLI flag wins; None overrides are ignored.
    overridden = s.apply_overrides(
        vad=3,
        end_silence=None,
        output_device="BlackHole 16ch",
    )
    assert overridden.vad == 3
    assert overridden.end_silence == s.end_silence
    assert overridden.output_device == "BlackHole 16ch"
    # Original is untouched.
    assert s.vad == 1


def test_apply_overrides_revalidates_cli_devices():
    with pytest.raises(ValidationError, match="BlackHole"):
        Settings().apply_overrides(listen_device="MacBook Pro Microphone")


def test_vad_bounds():
    with pytest.raises(ValidationError):
        Settings(vad=5)
    with pytest.raises(ValidationError):
        Settings(vad=-1)


def test_invalid_frame_and_rate():
    with pytest.raises(ValidationError):
        Settings(frame_ms=25)
    with pytest.raises(ValidationError):
        Settings(sample_rate=44_100)


def test_positive_constraints():
    with pytest.raises(ValidationError):
        Settings(rms_threshold=0)
    with pytest.raises(ValidationError):
        Settings(end_silence=-1)
