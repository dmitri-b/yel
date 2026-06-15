import pytest
from typer.testing import CliRunner

from agent_say import cli
from agent_say.cli import parse_duration

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
            "--end-silence",
            "0.5",
            "--out",
            "BlackHole 2ch",
            "--speakers",
            "MacBook Pro Speakers",
        ],
    )
    assert result.exit_code == 0
    s = captured["settings"]
    assert s.vad == 3
    assert s.end_silence == 0.5
    assert s.output_device == "BlackHole 2ch"
    assert s.monitor_device == "MacBook Pro Speakers"


def _capture_settings(captured):
    def fake_run_turn(text, settings):
        captured["s"] = settings
        return 0

    return fake_run_turn


def test_transcribe_flag_reaches_settings(monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "run_turn", _capture_settings(captured))
    result = runner.invoke(cli.app, ["hi", "--transcribe", "--deepgram-model", "nova-2"])
    assert result.exit_code == 0
    assert captured["s"].transcribe is True
    assert captured["s"].deepgram_model == "nova-2"


def test_no_transcribe_flag_overrides(monkeypatch):
    monkeypatch.setenv("AGENT_SAY_TRANSCRIBE", "true")
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


def test_config_show(monkeypatch):
    monkeypatch.delenv("AGENT_SAY_VAD", raising=False)
    result = runner.invoke(cli.admin_app, ["config", "show"])
    assert result.exit_code == 0
    assert "vad = 2" in result.stdout


def test_doctor_runs(monkeypatch):
    monkeypatch.setattr(cli, "print_devices", lambda: print("devices"))
    result = runner.invoke(cli.admin_app, ["doctor"])
    # On this macOS host the 'say' backend is present -> exit 0.
    assert result.exit_code == 0
    assert "TTS backend" in result.stdout
