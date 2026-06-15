#!/usr/bin/env bash
# Fire a timed follow-up that interrupts the agent mid-reply.
#
# By default a turn blocks until the agent stops talking. With --timeout, the
# turn instead returns exit 0 after AT MOST that long (or when the agent
# finishes, whichever is first). That lets you start a long action and then cut
# in — here we ask the agent to count, give it 5 seconds, then tell it to stop.
#
# The clock starts once our prompt finishes playing (i.e. while listening).
#
# Usage:
#   bash examples/interrupt_with_timeout.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

uv run yel "Count slowly from zero to one hundred, starting now." --timeout 5s \
  && uv run yel "Okay, stop counting now."
