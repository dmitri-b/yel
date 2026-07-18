"""Tests for BlackHole and virtual-output detection (no audio hardware)."""

import pytest

from yel import audio
from yel.audio import is_virtual_device, is_virtual_name, is_virtual_output
from yel.errors import DeviceNotFoundError


def test_blackhole_is_virtual():
    assert is_virtual_name("BlackHole 2ch")
    assert is_virtual_name("blackhole 16ch")


def test_other_loopbacks_are_virtual():
    assert is_virtual_name("Loopback Audio")
    assert is_virtual_name("Soundflower (2ch)")
    assert is_virtual_name("VB-Cable")


def test_real_devices_are_not_virtual():
    assert not is_virtual_name("MacBook Pro Speakers")
    assert not is_virtual_name("Beats Fit Pro")
    assert not is_virtual_name("External Headphones")


def test_is_virtual_output_by_name_string():
    # A name string is matched directly, no hardware query needed.
    assert is_virtual_output("BlackHole 2ch")
    assert not is_virtual_output("MacBook Pro Speakers")


def test_is_virtual_output_none_is_real():
    # System default (None) is treated as real: we only mirror on explicit routing.
    assert not is_virtual_output(None)


def test_is_virtual_device_by_name_string():
    assert is_virtual_device("BlackHole 2ch")
    assert not is_virtual_device("MacBook Pro Speakers")


def test_missing_blackhole_reports_install_command(monkeypatch):
    class FakeSoundDevice:
        @staticmethod
        def query_devices():
            return [
                {
                    "name": "MacBook Pro Microphone",
                    "max_input_channels": 1,
                    "max_output_channels": 0,
                },
                {
                    "name": "MacBook Pro Speakers",
                    "max_input_channels": 0,
                    "max_output_channels": 2,
                },
            ]

    monkeypatch.setattr(audio, "_sd", lambda: FakeSoundDevice())

    with pytest.raises(DeviceNotFoundError, match="brew install --cask blackhole-2ch"):
        audio.resolve_input_device("BlackHole 2ch")
    with pytest.raises(DeviceNotFoundError, match="brew install --cask blackhole-2ch"):
        audio.resolve_output_device("BlackHole 2ch")


@pytest.mark.parametrize("device", ["MacBook Pro Microphone", None, 1])
def test_input_resolver_has_no_physical_or_default_path(device):
    with pytest.raises(DeviceNotFoundError, match="must be BlackHole"):
        audio.resolve_input_device(device)
