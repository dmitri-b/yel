#!/usr/bin/env bash
# A longer scripted conversation about a Greek recipe, driven turn-by-turn with
# yel. Each turn BLOCKS until the agent stops talking (trailing-silence
# detection), so the next prompt only fires once the agent has had its full say.
#
# "Timeouts to let the agent speak" here means generous per-turn budgets:
#   --start-timeout   how long to wait for the agent to BEGIN replying
#   --end-silence     trailing silence that marks the reply as finished
#   --overall-timeout hard cap per turn (long, so multi-sentence recipe answers
#                     are never cut off mid-thought)
# We deliberately do NOT pass --timeout, because that caps the wait and would
# interrupt the agent; the blocking default is what lets it finish.
#
# Usage:
#   bash examples/greek_recipe_convo.sh
#
# Audio routing (override via env). Default pairs with a single BlackHole 2ch:
#   yel speaks INTO BlackHole (set the agent's mic/input to "BlackHole 2ch")
#   and LISTENS on the real mic, which hears the agent's speakers acoustically.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

OUT_DEVICE="${OUT_DEVICE:-BlackHole 2ch}"
LISTEN_DEVICE="${LISTEN_DEVICE:-MacBook Pro Microphone}"
START_TIMEOUT="${START_TIMEOUT:-30}"
END_SILENCE="${END_SILENCE:-1.5}"
OVERALL_TIMEOUT="${OVERALL_TIMEOUT:-90}"

# Each turn waits for the agent to finish before returning.
turn() {
  local prompt="$1"
  echo
  echo "=== YOU: $prompt"
  local reply
  reply="$(uv run yel \
    --out "$OUT_DEVICE" \
    --listen "$LISTEN_DEVICE" \
    --start-timeout "$START_TIMEOUT" \
    --end-silence "$END_SILENCE" \
    --overall-timeout "$OVERALL_TIMEOUT" \
    --transcribe \
    "$prompt")"
  local code=$?
  if [[ $code -ne 0 ]]; then
    echo "!!! turn failed (exit $code): $prompt" >&2
    return $code
  fi
  echo "--- AGENT: ${reply:-<no transcript>}"
  return 0
}

echo "Greek recipe conversation — out='$OUT_DEVICE' listen='$LISTEN_DEVICE'"
echo "(each turn blocks until the agent stops speaking; end-silence=${END_SILENCE}s, cap=${OVERALL_TIMEOUT}s)"

turn "Hi! Can you recommend a quick Greek dinner I can make in under thirty minutes?" \
  && turn "That sounds great. What ingredients do I need, and roughly how much of each?" \
  && turn "Got it. Now walk me through the preparation steps one at a time." \
  && turn "While that's cooking, what should I be doing — any prep I can do in parallel?" \
  && turn "How do I know when it's done and ready to serve?" \
  && turn "Any tips to make it taste more authentic, like a Greek grandmother would?" \
  && turn "And what's a simple side dish or drink that pairs well with it?" \
  && turn "Perfect — thank you so much for the help!"

code=$?
echo
if [[ $code -eq 0 ]]; then
  echo "=== conversation complete ==="
else
  echo "=== conversation stopped early (exit $code) ===" >&2
fi
exit $code
