# yel - programmatically drive a voice agent from your terminal w/o any external service

##   TLDR
Problem: automatically testing voice agents end-to-end is a very cumbersome process, especially when you need to drive tests from a harness like Codex or Claude Code. `yel` allows you to yell a sequence of sepeech turn to the agent. record the responses and statistics like TTFA. it doesn't use any external SR models and relies on services provided by an IKS. it would not be possible without the excellent Blackhole product.

Script spoken turns against a local voice agent. `yel` speaks a prompt out
loud (macOS `say`), then listens for the agent's reply and blocks until the
agent stops talking — so you can chain turns from the shell:

```sh
uvx --from git+https://github.com/dmitri-b/yel.git yel \
  "recommend a Greek recipe under 30 minutes" \
  && uvx --from git+https://github.com/dmitri-b/yel.git yel \
    "now give me the exact steps"
```

The second command starts only after the first detects that the agent's spoken
response has ended.

![Yel scripting spoken turns through BlackHole](docs/assets/yel-screen.png)

## Quick start

Requirements: macOS 26 or newer, Python 3.11 or newer,
[`uv`](https://docs.astral.sh/uv/getting-started/installation/), and
`BlackHole 2ch`. Yel has no physical-microphone fallback. It uses the built-in
`say` command for speech and Apple's on-device `SpeechAnalyzer` for
transcription. Xcode 26 or its Command Line Tools is needed once to compile the
small native transcription helper; no account, API key, or network service is
used at runtime.

Run Yel directly from GitHub—no clone or persistent installation required:

```sh
brew install --cask blackhole-2ch
uvx --from git+https://github.com/dmitri-b/yel.git yel --help
uvx --from git+https://github.com/dmitri-b/yel.git yel --devices
uvx --from git+https://github.com/dmitri-b/yel.git yel "hello, can you hear me?"
```

`uvx` runs Yel in an isolated environment managed by uv. The first invocation
fetches it into uv's disposable cache; later invocations reuse that cache.

### Optional: install `yel` on your PATH

For regular shell use, install the checkout as an editable uv tool. The
`--editable` flag means source changes in this repository take effect without
reinstalling:

```sh
uv tool install --editable /path/to/yel
uv tool update-shell
exec zsh
```

Then run `yel` from any directory:

```sh
yel --help
yel "first prompt" && yel "second prompt"
```

If it is already installed, refresh the editable installation with:

```sh
uv tool install --editable --force /path/to/yel
```

`uv tool update-shell` normally adds uv's tool directory (`~/.local/bin`) to
your `PATH` and only needs to be run once.

## How it works

```text
yel how many Rs in strawberry → <local TTS> → voice agent → <listen> → VAD → print to stdout + exit 0
```

1. Render the prompt to speech with the macOS `say` command.
2. Play it into the configured **BlackHole output**. The prompt is also played
   on your `--speakers` monitor, or the system-default output, when speaker
   output is enabled.
3. Capture the agent's mirrored reply from the configured **BlackHole input**.
4. Optionally play the captured agent audio live on your **speakers** (`--speakers`),
   so you can hear the reply even when it's routed digitally into the listen device.
5. Wait for the agent to start speaking and then for trailing silence.
6. Transcribe the captured reply locally with Apple's macOS 26 Speech framework,
   print the final transcript, and exit `0` once the agent appears finished.

Speech detection uses `webrtcvad` gated by an RMS floor, with a small state
machine (`yel.vad.TurnEndDetector`) deciding turn boundaries. BlackHole replies
use an RMS fallback because WebRTC can reject synthetic vocoder output.

Prompt synthesis never relies on the macOS system voice: the default is
`Samantha` (`en_US`). Programmatic multilingual runs can call
`Speaker.speak(text, language="es")` for `Mónica` (`es_ES`), `"fr"` for
`Thomas` (`fr_FR`), or `"de"` for the male `Eddy (German (Germany))` voice
(`de_DE`). Yel validates these mappings against `say -v '?'` before rendering,
and rejects unsupported or mismatched locales.

## Required BlackHole routing

Yel requires BlackHole for both directions:

```sh
brew install --cask blackhole-2ch
```

Configure the agent to listen on `BlackHole 2ch` and mirror its reply back to
`BlackHole 2ch`. The agent can keep real speakers as its primary output so the
reply remains audible. Yel defaults both of its routes to BlackHole:

```sh
uvx --from git+https://github.com/dmitri-b/yel.git yel \
  --out "BlackHole 2ch" \
  --listen "BlackHole 2ch" \
  --speaker-output \
  "what is a quick Greek recipe?"
```

Physical devices and system-default input/output routes are rejected. Use
`--out` and `--listen` only to select another installed BlackHole variant.

## Fully local transcription (Apple Speech)

Transcription is enabled by default and runs entirely on this Mac using
`SpeechAnalyzer` and `SpeechTranscriber`. `yel` passes the captured 16 kHz mono
PCM to a bundled Swift helper over local pipes; no audio or transcript is sent
over the network. The helper is compiled into `~/Library/Caches/yel/native` on
first use and reused afterward.

The final transcript is printed to **stdout** (status logs stay on stderr, so
the transcript is cleanly capturable). Pass `--no-transcribe` to opt out, or
select a supported locale with `--transcription-locale`.

Every turn also reports `yel: TTFA: N ms` on stderr, measured from the end of
prompt playback to the first detected agent speech frame (`n/a` when no speech
is detected):

```sh
reply=$(uvx --from git+https://github.com/dmitri-b/yel.git yel \
  "what is a quick Greek recipe?")
echo "agent said: $reply"
```

```sh
uvx --from git+https://github.com/dmitri-b/yel.git yel \
  --transcription-locale en-GB "give me the exact steps"
```

Recognition failures are reported on stderr but do not change a completed
turn's exit code, so shell chains remain usable. The native helper does not
download models; it uses speech assets already managed by macOS.

## Bounded wait / timed follow-ups (`--timeout`)

By default a turn blocks until the agent's reply ends. Pass `--timeout DURATION`
to return **exit 0** after at most that long (whichever comes first: the agent
finishing, or the timeout), so a chained command can fire a timed follow-up —
e.g. start a long action, then interrupt it:

```sh
uvx --from git+https://github.com/dmitri-b/yel.git yel \
  "count zero to 24 immediately" --timeout 5s \
  && uvx --from git+https://github.com/dmitri-b/yel.git yel "stop now"
```

`DURATION` accepts `5s`, `500ms`, `2m`, or a bare number (seconds). The clock
starts once our prompt finishes playing (i.e. while listening to the agent).
Note: if you set `--timeout` *larger* than `--start-timeout` (30 s default) and
the agent never speaks, the no-speech error (exit 2) can still fire first.

## CLI options

Yel does not read environment variables or `.env` files. Runtime configuration
is supplied through CLI flags, with BlackHole-safe built-in defaults.

| Setting          | Flag                | Default |
| ---------------- | ------------------- | ------- |
| Output device    | `--out`             | BlackHole 2ch |
| Listen device    | `--listen`          | BlackHole 2ch |
| Speakers (monitor) | `--speakers`      | off |
| Speaker output   | `--speaker-output` / `--no-speaker-output` | on |
| Transcribe reply | `--transcribe` / `--no-transcribe` | on |
| Transcription locale | `--transcription-locale` | en-US |
| Start timeout    | `--start-timeout`   | 30 s |
| End silence      | `--end-silence`     | 1.2 s |
| Bounded wait     | `--timeout`         | off |

Quiet routing for shared spaces:

```sh
uvx --from git+https://github.com/dmitri-b/yel.git yel \
  --out "BlackHole 2ch" \
  --listen "BlackHole 2ch" \
  --no-speaker-output \
  "what is a quick Greek recipe?"
```

`--no-speaker-output` disables the automatic real-speaker prompt mirror and
live speaker monitoring even if `--speakers` is configured.

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | success |
| 1 | general error |
| 2 | no agent speech detected before start timeout |
| 3 | audio device not found |
| 4 | TTS backend failed |
| 5 | invalid config |

## Development

The distribution, CLI, and Python package are all named `yel`:

```python
from yel import Speaker, speak
```

```sh
uv run pytest
uv run ruff check .
uv run mypy src
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the contribution workflow. This
project is available under the [MIT License](LICENSE).
