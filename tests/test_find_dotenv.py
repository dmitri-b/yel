from pathlib import Path

from agent_say.config import find_dotenv


def test_finds_dotenv_in_ancestor(tmp_path):
    (tmp_path / ".env").write_text("DEEPGRAM_API_KEY=abc\n")
    sub = tmp_path / "pkg" / "deep"
    sub.mkdir(parents=True)
    found = find_dotenv(sub)
    assert Path(found) == (tmp_path / ".env")


def test_falls_back_when_absent(tmp_path):
    found = find_dotenv(tmp_path)
    # No .env anywhere up the (temp) tree we control -> default name.
    assert Path(found).name == ".env"
