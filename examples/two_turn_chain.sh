#!/usr/bin/env bash
# Minimal example: chain two spoken turns.
#
# The first `yel` speaks its prompt, then blocks until the agent finishes
# replying (trailing-silence detection). Only then does the `&&` fire and the
# second prompt get spoken. This is the core building block of yel — every
# other example is just more turns wired together the same way.
#
# Usage:
#   bash examples/two_turn_chain.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

uv run yel "Hi! Can you recommend a quick weeknight dinner?" \
  && uv run yel "Great — now list the exact ingredients."
