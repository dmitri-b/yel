# Contributing to yel

Bug reports and focused pull requests are welcome. Please describe the BlackHole
routing setup, macOS version, Python version, and reproduction steps for
hardware-dependent problems.

## Development setup

```sh
git clone https://github.com/dmitri-b/yel.git
cd yel
uv sync
```

The automated suite does not require audio hardware. Before submitting a
change, run:

```sh
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

Keep changes small, add tests for behavior changes, and update the README when
CLI flags, defaults, or supported workflows change.
