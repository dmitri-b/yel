#!/usr/bin/env bash
# Capture the agent's spoken reply as text.
#
# With --transcribe, yel records the agent's reply, sends it to Deepgram once
# the turn ends, and prints ONLY the transcript to stdout (status logs go to
# stderr) — so it's safe to capture into a shell variable and branch on.
#
# Requires a Deepgram key in DEEPGRAM_API_KEY (env or a nearby .env file).
#
# Usage:
#   DEEPGRAM_API_KEY=dg_xxx bash examples/transcribe_reply.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

reply="$(uv run yel --transcribe "What is a quick Greek recipe?")"
echo "agent said: ${reply:-<no transcript>}"

# Trivial branch on what the agent actually said.
if [[ "$reply" == *[Ss]alad* ]]; then
  uv run yel "A salad sounds perfect — what dressing goes with it?"
fi
