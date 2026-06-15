# yel

Script spoken turns against a local voice agent. `yel` speaks a prompt out
loud (macOS `say`), then listens for the agent's reply and blocks until the
agent stops talking — so you can chain turns from the shell:

```sh
uv run yel "recommend a Greek recipe under 30 minutes" \
  && uv run yel "now give me the exact steps"
```

The second command starts only after the first detects that the agent's spoken
response has ended.

## Quick start

```sh
uv sync
uv run yel --help
uv run yel --devices
uv run yel "hello, can you hear me?"
```

Handy alias:

```sh
alias say-ai='uv run yel'
say-ai "first prompt" && say-ai "second prompt"
```

## How it works

1. Render the prompt to speech with the macOS `say` command.
2. Play it to the configured **output** device. If that device is a virtual
   loopback you can't hear (e.g. `BlackHole`), the prompt is *also* played on a
   real output — your `--speakers` monitor if set, otherwise the system default
   — so you hear what's being said to the agent.
3. Listen on the configured **input/monitor** device.
4. Optionally play the captured agent audio live on your **speakers** (`--speakers`),
   so you can hear the reply even when it's routed digitally into the listen device.
5. Wait for the agent to start speaking, then for trailing silence.
6. Exit `0` once the agent appears finished.

Speech detection uses `webrtcvad` gated by an RMS floor, with a small state
machine (`agent_say.vad.TurnEndDetector`) deciding turn boundaries.

## macOS setup (BlackHole loopback)

Route `yel`'s speech into your agent's microphone input and listen for the
agent's voice on a separate device:

```sh
brew install --cask blackhole-2ch
```

Set the agent's input device to `BlackHole 2ch`, then:

```sh
uv run yel \
  --out "BlackHole 2ch" \
  --listen "MacBook Pro Microphone" \
  "what is a quick Greek recipe?"
```

Because `BlackHole` is a silent loopback, `yel` automatically mirrors the
spoken prompt onto your real speakers (the system default, or `--speakers` if
set) so you can hear what it's saying to the agent. No extra flag needed.

### Fully digital loop (hear the agent on your speakers)

If you also route the agent's **output** into a virtual device so `yel` can
capture it cleanly (no acoustic echo), pass `--speakers` to play that audio live
on your real speakers — otherwise you'd hear nothing:

```sh
uv run yel \
  --out "BlackHole 2ch" \
  --listen "BlackHole 2ch" \
  --speakers "MacBook Pro Speakers" \
  "what is a quick Greek recipe?"
```

## Transcribe the agent's reply (Deepgram)

Pass `--transcribe` to transcribe what the agent said. `yel` records the
captured reply, sends it to Deepgram's prerecorded API once the turn ends, and
prints the transcript to **stdout** (status logs stay on stderr, so the
transcript is cleanly capturable):

```sh
reply=$(uv run yel --transcribe "what is a quick Greek recipe?")
echo "agent said: $reply"
```

The Deepgram key is read from `DEEPGRAM_API_KEY` — in your environment or a
`.env` file. `yel` walks up from the working directory to find the nearest
`.env`, so a key at your repo root is picked up automatically. Choose a model
with `--deepgram-model` (default `nova-3`). Transcription is best-effort: if it
fails, the turn's exit code is unchanged so chaining still works.

```sh
export DEEPGRAM_API_KEY=dg_xxx      # or put it in .env
uv run yel --transcribe --deepgram-model nova-3 "give me the exact steps"
```

## Bounded wait / timed follow-ups (`--timeout`)

By default a turn blocks until the agent's reply ends. Pass `--timeout DURATION`
to return **exit 0** after at most that long (whichever comes first: the agent
finishing, or the timeout), so a chained command can fire a timed follow-up —
e.g. start a long action, then interrupt it:

```sh
uv run yel "count zero to 24 immediately" --timeout 5s \
  && uv run yel "stop now"
```

`DURATION` accepts `5s`, `500ms`, `2m`, or a bare number (seconds). The clock
starts once our prompt finishes playing (i.e. while listening to the agent).
Note: if you set `--timeout` *larger* than `--start-timeout` (30 s default) and
the agent never speaks, the no-speech error (exit 2) can still fire first.

## Configuration

Precedence (highest first): **CLI flags → environment variables → `.env` → defaults.**

| Setting          | Flag                | Env var                 | Default |
| ---------------- | ------------------- | ----------------------- | ------- |
| Output device    | `--out`             | `AGENT_SAY_OUT`         | system  |
| Listen device    | `--listen`          | `AGENT_SAY_LISTEN`      | system  |
| Speakers (monitor) | `--speakers`      | `AGENT_SAY_SPEAKERS`    | off     |
| Transcribe reply | `--transcribe`      | `AGENT_SAY_TRANSCRIBE`  | off     |
| Deepgram model   | `--deepgram-model`  | `AGENT_SAY_DEEPGRAM_MODEL` | nova-3 |
| Deepgram key     | —                   | `DEEPGRAM_API_KEY`      | —       |
| Start timeout    | `--start-timeout`   | `AGENT_SAY_START_TIMEOUT` | 30 s  |
| End silence      | `--end-silence`     | `AGENT_SAY_END_SILENCE` | 1.2 s   |
| Overall timeout  | `--overall-timeout` | `AGENT_SAY_OVERALL_TIMEOUT` | 180 s |
| Bounded wait     | `--timeout`         | `AGENT_SAY_TIMEOUT`     | off     |
| VAD aggressiveness | `--vad`           | `AGENT_SAY_VAD`         | 2       |
| RMS threshold    | `--rms-threshold`   | `AGENT_SAY_RMS_THRESHOLD` | 0.012 |

Inspect what got resolved:

```sh
uv run yel config show
uv run yel config path
uv run yel doctor
```

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | success |
| 1 | general error |
| 2 | no agent speech detected before start timeout |
| 3 | overall timeout reached |
| 4 | audio device not found |
| 5 | TTS backend failed |
| 6 | invalid config |

## Development

```sh
uv run pytest
uv run ruff check .
uv run mypy src
```
