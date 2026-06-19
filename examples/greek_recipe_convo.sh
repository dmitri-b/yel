#!/usr/bin/env bash
# A scripted Greek-recipe conversation: one turn per line, chained with &&.
# Each `yel` invocation blocks until the agent stops talking, so the next prompt
# only fires once the agent has had its full say. Text is passed unquoted.
#
# Usage:
#   bash examples/greek_recipe_convo.sh
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

# Aliases aren't expanded in non-interactive shells unless we opt in.
shopt -s expand_aliases
alias yel="uv run yel --out 'BlackHole 2ch'"

yel Hi can you recommend a quick Greek dinner I can make in under thirty minutes \
  && yel That sounds great what ingredients do I need and roughly how much of each \
  && yel Got it now walk me through the preparation steps one at a time \
  && yel While that is cooking what prep can I do in parallel \
  && yel How do I know when it is done and ready to serve \
  && yel Any tips to make it taste more authentic like a Greek grandmother would \
  && yel And what is a simple side dish or drink that pairs well with it \
  && yel Perfect thank you so much for the help
