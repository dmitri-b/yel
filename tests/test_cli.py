import pytest
from typer.testing import CliRunner

from yel import cli
from yel.cli import parse_duration

runner = CliRunner()


@pytest.mark.parametrize(
    "text,expected",
    [("5s", 5.0), ("500ms", 0.5), ("2m", 120.0), ("5", 5.0), ("1.5s", 1.5), (" 250ms ", 0.25)],
)
def test_parse_duration_ok(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["abc", "", "5x", "-3s", "0", "s"])
def test_parse_duration_bad(text):
    with pytest.raises(ValueError):
        parse_duration(text)


def test_help():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    assert "voice agent" in result.stdout
    assert "╭" not in result.stdout
    assert any(
        "--devices" in line and "List audio devices and exit." in line
        for line in result.stdout.splitlines()
    )
    assert "--vad" not in result.stdout
    assert "--rms-threshold" not in result.stdout
    assert "--transcription-locale" not in result.stdout
    assert "doctor" not in result.stdout
    assert "config" not in result.stdout


def test_devices_lists_and_exits(monkeypatch):
    called = {}

    def fake_print_devices():
        called["yes"] = True
        print("DEVICE LIST")

    monkeypatch.setattr(cli, "print_devices", fake_print_devices)
    result = runner.invoke(cli.app, ["--devices"])
    assert result.exit_code == 0
    assert called.get("yes")
    assert "DEVICE LIST" in result.stdout


def test_text_invokes_run_turn_and_propagates_exit_code(monkeypatch):
    captured = {}

    def fake_run_turn(text, settings):
        captured["text"] = text
        captured["settings"] = settings
        return 2

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)
    result = runner.invoke(cli.app, ["hello there"])
    assert result.exit_code == 2
    assert captured["text"] == "hello there"


def test_cli_overrides_reach_settings(monkeypatch):
    captured = {}

    def fake_run_turn(text, settings):
        captured["settings"] = settings
        return 0

    monkeypatch.setattr(cli, "run_turn", fake_run_turn)
    result = runner.invoke(
        cli.app,
        [
            "hi",
            "--vad",
            "3",
            "--rms-threshold",
            "0.002",
            "--end-silence",
            "0.5",
            "--out",
            "BlackHole 2ch",
            "--speakers",
            "MacBook Pro Speakers",
            "--no-speaker-output",
        ],
    )
    assert result.exit_code == 0
    s = captured["settings"]
    assert s.vad == 3
    assert s.rms_threshold == 0.002
    assert s.end_silence == 0.5
    assert s.output_device == "BlackHole 2ch"
    assert s.listen_device == "BlackHole 2ch"
    assert s.monitor_device == "MacBook Pro Speakers"
    assert s.speaker_output is False


@pytest.mark.parametrize(
    "args",
    [
        ["hi", "--out", "MacBook Pro Speakers"],
        ["hi", "--listen", "MacBook Pro Microphone"],
    ],
)
def test_cli_rejects_physical_audio_routes(monkeypatch, args):
    monkeypatch.setattr(
        cli,
        "run_turn",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("run_turn must not receive a physical route")
        ),
    )
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 5
    assert "BlackHole" in result.stderr


def _capture_settings(captured):
    def fake_run_turn(text, settings):
        captured["s"] = settings
        return 0

    return fake_run_turn


def test_transcribe_flag_reaches_settings(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "run_turn", _capture_settings(captured))
    result = runner.invoke(
        cli.app,
        ["hi", "--transcribe"],
    )
    assert result.exit_code == 0
    assert captured["s"].transcribe is True


def test_transcription_locale_flag_is_not_supported():
    result = runner.invoke(cli.app, ["hi", "--transcription-locale", "en-GB"])
    assert result.exit_code != 0


def test_transcription_is_enabled_by_default(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "run_turn", _capture_settings(captured))
    result = runner.invoke(cli.app, ["hi"])
    assert result.exit_code == 0
    assert captured["s"].transcribe is True


def test_no_transcribe_flag_overrides(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "run_turn", _capture_settings(captured))
    result = runner.invoke(cli.app, ["hi", "--no-transcribe"])
    assert result.exit_code == 0
    assert captured["s"].transcribe is False


def test_timeout_flag_reaches_settings_as_seconds(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "run_turn", _capture_settings(captured))
    result = runner.invoke(cli.app, ["hi", "--timeout", "5s"])
    assert result.exit_code == 0
    assert captured["s"].response_timeout == 5.0


def test_timeout_default_is_none(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "run_turn", _capture_settings(captured))
    result = runner.invoke(cli.app, ["hi"])
    assert result.exit_code == 0
    assert captured["s"].response_timeout is None


def test_bad_timeout_is_usage_error(monkeypatch):
    monkeypatch.setattr(cli, "run_turn", lambda text, settings: 0)
    result = runner.invoke(cli.app, ["hi", "--timeout", "soon"])
    assert result.exit_code != 0


def test_missing_text_is_error(monkeypatch):
    # Invoke with only a flag value that leaves no text argument.
    monkeypatch.setattr(cli, "run_turn", lambda text, settings: 0)
    result = runner.invoke(cli.app, ["--vad", "2"])
    assert result.exit_code != 0


def test_removed_overall_timeout_is_rejected(monkeypatch):
    monkeypatch.setattr(cli, "run_turn", lambda text, settings: 0)
    result = runner.invoke(cli.app, ["hi", "--overall-timeout", "90"])
    assert result.exit_code != 0
    assert "No such option" in result.stderr
