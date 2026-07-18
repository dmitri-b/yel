#!/usr/bin/env bash
# Capture the agent's spoken reply as text.
#
# Yel transcribes the reply on-device with Apple Speech and prints ONLY the
# final transcript to stdout (status logs go to stderr), so it's safe to capture
# into a shell variable and branch on.
#
# Usage:
#   bash examples/transcribe_reply.sh
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

reply="$(uv run yel "What is a quick Greek recipe?")"
echo "agent said: ${reply:-<no transcript>}"

# Trivial branch on what the agent actually said.
if [[ "$reply" == *[Ss]alad* ]]; then
  uv run yel "A salad sounds perfect — what dressing goes with it?"
fi
