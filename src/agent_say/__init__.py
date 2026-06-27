"""yel: script spoken turns against a local voice agent.

CLI entrypoint: ``agent_say.cli:main`` (the ``yel`` command).
Python API: :class:`agent_say.api.Speaker` / :func:`agent_say.api.speak` for
in-process spoken turns, and :func:`agent_say.runner.run_turn` for the full
speak-then-listen turn used by the CLI.
"""

from .api import Speaker, speak

__version__ = "0.1.0"

__all__ = ["Speaker", "speak", "__version__"]
