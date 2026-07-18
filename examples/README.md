# Examples

Runnable scripts that drive a local voice agent with `yel`. Run them from the
repo root after `uv sync`. Each turn blocks until the agent stops talking, so
prompts fire one after another in order.

| Script | What it shows |
| ------ | ------------- |
| [`two_turn_chain.sh`](two_turn_chain.sh) | The core building block: chain two spoken turns with `&&`. |
| [`transcribe_reply.sh`](transcribe_reply.sh) | Capture the local Apple Speech transcript and branch on it. |
| [`interrupt_with_timeout.sh`](interrupt_with_timeout.sh) | Fire a timed follow-up that cuts in mid-reply (`--timeout`). |
| [`greek_recipe_convo.sh`](greek_recipe_convo.sh) | A full multi-turn conversation with generous per-turn budgets. |

Yel requires `BlackHole 2ch` for both prompt injection and reply capture. Audio
routing can be changed only with CLI flags, and physical microphone routes are
rejected. See the main [README](../README.md).
