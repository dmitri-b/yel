"""yel: script spoken turns against a local voice agent.

Use :class:`Speaker` / :func:`speak` for lightweight in-process speech output.
The full speak-then-listen turn and validated settings are imported lazily so
speaker-only callers don't load the heavier configuration stack.
"""

from .api import Speaker, speak

__version__ = "0.1.0"
__all__ = ["Speaker", "speak", "run_turn", "Settings", "__version__"]


def __getattr__(name: str):
    if name == "run_turn":
        from .runner import run_turn

        return run_turn
    if name == "Settings":
        from .config import Settings

        return Settings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
