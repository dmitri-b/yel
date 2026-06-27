"""``yel`` Python API.

The CLI is ``yel`` but the implementation package was historically ``agent_say``.
This module makes the import name match the tool name, so callers can write:

    from yel import Speaker
    spk = Speaker("BlackHole 2ch")
    spk.speak("what is the weather in Tokyo")

It is a thin re-export of :mod:`agent_say`. ``Speaker`` / ``speak`` are the
lightweight in-process API (only numpy + macOS ``say`` + sounddevice). The full
speak-then-listen turn (``run_turn`` / ``AgentSaySettings``) is imported lazily so
that consumers of just the speaker API don't need yel's heavier deps (pydantic).
"""
from agent_say.api import Speaker, speak

__version__ = "0.1.0"
__all__ = ["Speaker", "speak", "run_turn", "AgentSaySettings", "__version__"]


def __getattr__(name: str):  # PEP 562 — lazy heavy imports
    if name == "run_turn":
        from agent_say.runner import run_turn
        return run_turn
    if name == "AgentSaySettings":
        from agent_say.config import AgentSaySettings
        return AgentSaySettings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
