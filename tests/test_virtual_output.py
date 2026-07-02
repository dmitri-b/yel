"""Tests for virtual-output detection (no audio hardware)."""

from agent_say.audio import is_virtual_device, is_virtual_name, is_virtual_output


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
