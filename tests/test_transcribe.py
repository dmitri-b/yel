"""Tests for the fully local macOS SpeechAnalyzer adapter."""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from yel import transcribe as native_asr


def _tone(seconds=0.2, sr=16000):
    return (0.2 * np.sin(2 * np.pi * 220 * np.arange(int(seconds * sr)) / sr)).astype(
        np.float32
    )


def test_pcm16_bytes_roundtrip():
    samples = _tone()
    pcm = native_asr._pcm16_bytes(samples, 16000)
    assert len(pcm) == len(samples) * 2
    back = np.frombuffer(pcm, dtype="<i2")
    assert back.shape[0] == samples.shape[0]


def test_empty_audio_returns_without_building_helper(monkeypatch):
    monkeypatch.setattr(
        native_asr,
        "_helper_executable",
        lambda: (_ for _ in ()).throw(AssertionError("helper should not be built")),
    )
    assert native_asr.transcribe(np.zeros(0, dtype=np.float32), 16000) == ""


def test_transcribe_passes_pcm_and_locale_to_native_helper(monkeypatch):
    captured = {}
    monkeypatch.setattr(native_asr, "_helper_executable", lambda: Path("/tmp/yel-native-asr"))

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        return subprocess.CompletedProcess(command, 0, stdout=b"hello locally\n", stderr=b"")

    monkeypatch.setattr(native_asr.subprocess, "run", fake_run)
    samples = _tone()
    result = native_asr.transcribe(samples, 16_000, locale="en_US")

    assert result == "hello locally"
    assert captured["command"] == [
        "/tmp/yel-native-asr",
        "--sample-rate",
        "16000",
        "--locale",
        "en-US",
    ]
    assert captured["input"] == native_asr._pcm16_bytes(samples)


def test_native_failure_becomes_transcription_error(monkeypatch):
    monkeypatch.setattr(native_asr, "_helper_executable", lambda: Path("/tmp/yel-native-asr"))
    monkeypatch.setattr(
        native_asr.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout=b"", stderr=b"native model unavailable\n"
        ),
    )
    with pytest.raises(native_asr.TranscriptionError, match="native model unavailable"):
        native_asr.transcribe(_tone(), 16_000)


def test_timeout_becomes_transcription_error(monkeypatch):
    monkeypatch.setattr(native_asr, "_helper_executable", lambda: Path("/tmp/yel-native-asr"))

    def time_out(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(native_asr.subprocess, "run", time_out)
    with pytest.raises(native_asr.TranscriptionError, match="timed out"):
        native_asr.transcribe(_tone(), 16_000, timeout=2)


def test_helper_is_compiled_once_and_cached(monkeypatch, tmp_path):
    source = tmp_path / "speech_transcriber.swift"
    source.write_text("// native helper", encoding="utf-8")
    monkeypatch.setattr(native_asr, "_HELPER_SOURCE", source)
    monkeypatch.setattr(native_asr.sys, "platform", "darwin")
    monkeypatch.setattr(native_asr, "_macos_major", lambda: 26)
    monkeypatch.setattr(
        native_asr,
        "_compile_command",
        lambda _source, output, _cache: ["swiftc", "-o", str(output)],
    )
    builds = []

    def fake_compile(command, **kwargs):
        builds.append(command)
        Path(command[-1]).write_bytes(b"Mach-O placeholder")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(native_asr.subprocess, "run", fake_compile)

    first = native_asr._helper_executable(cache_root=tmp_path / "cache")
    second = native_asr._helper_executable(cache_root=tmp_path / "cache")

    assert first == second
    assert first.is_file()
    assert len(builds) == 1


def test_old_macos_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(native_asr.sys, "platform", "darwin")
    monkeypatch.setattr(native_asr, "_macos_major", lambda: 15)
    with pytest.raises(native_asr.TranscriptionError, match="macOS 26"):
        native_asr._helper_executable(cache_root=tmp_path)
