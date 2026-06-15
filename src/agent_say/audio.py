"""Audio device discovery and playback via sounddevice.

``sounddevice`` (PortAudio) is imported lazily so the rest of the package — and
the test suite — can be imported on machines without a working audio backend.
"""

from __future__ import annotations

import threading
from typing import Any

import numpy as np

from .errors import DeviceNotFoundError


def _sd():
    import sounddevice as sd  # lazy: avoids importing PortAudio at module load

    return sd


def list_devices() -> list[dict]:
    """Return the raw sounddevice device list."""
    return list(_sd().query_devices())


def print_devices() -> None:
    """Print input/output devices in a readable table."""
    sd = _sd()
    devices = sd.query_devices()
    try:
        default_in, default_out = sd.default.device
    except Exception:
        default_in = default_out = None

    print("Audio devices (index: name  [in/out channels])")
    print("-" * 60)
    for idx, dev in enumerate(devices):
        ins = dev["max_input_channels"]
        outs = dev["max_output_channels"]
        marks = []
        if idx == default_in and ins:
            marks.append("default-in")
        if idx == default_out and outs:
            marks.append("default-out")
        mark = f"  <{', '.join(marks)}>" if marks else ""
        print(f"  {idx:>2}: {dev['name']}  [{ins} in / {outs} out]{mark}")


def _resolve(device: str | int | None, *, want_output: bool) -> int | None:
    """Resolve a device name or index to an index.

    ``None`` resolves to the system default (returned as ``None`` so PortAudio
    picks it). A string is matched case-insensitively as a substring of the
    device name, considering only devices with the right channel direction.
    """
    if device is None:
        return None

    sd = _sd()
    devices = sd.query_devices()

    if isinstance(device, int):
        if device < 0 or device >= len(devices):
            raise DeviceNotFoundError(f"Audio device index {device} is out of range.")
        return device

    needle = device.strip().lower()
    channel_key = "max_output_channels" if want_output else "max_input_channels"
    matches = [
        idx
        for idx, dev in enumerate(devices)
        if needle in dev["name"].lower() and dev[channel_key] > 0
    ]
    if not matches:
        direction = "output" if want_output else "input"
        raise DeviceNotFoundError(f"No {direction} device matching {device!r}.")
    return matches[0]


def resolve_output_device(device: str | int | None) -> int | None:
    return _resolve(device, want_output=True)


def resolve_input_device(device: str | int | None) -> int | None:
    return _resolve(device, want_output=False)


# Output devices the operator cannot physically hear — virtual loopbacks used to
# route our speech digitally into the agent's input. When the prompt goes to one
# of these, we mirror it onto a real speaker so a human can still hear it.
_VIRTUAL_OUTPUT_HINTS = (
    "blackhole",
    "loopback",
    "soundflower",
    "vb-audio",
    "vb-cable",
    "aggregate",
    "multi-output",
)


def is_virtual_name(name: str) -> bool:
    """True if ``name`` looks like a virtual/loopback audio device."""
    low = name.lower()
    return any(hint in low for hint in _VIRTUAL_OUTPUT_HINTS)


def is_virtual_output(device: str | int | None) -> bool:
    """True if ``device`` (name or index) is a virtual loopback output.

    ``None`` (system default) is treated as real — we only mirror when the user
    explicitly routes the prompt to a virtual device.
    """
    if device is None:
        return False
    if isinstance(device, str):
        return is_virtual_name(device)
    devices = _sd().query_devices()
    if 0 <= device < len(devices):
        return is_virtual_name(devices[device]["name"])
    return False


def default_output_device() -> int | None:
    """Index of the system default output device, or ``None`` if unknown."""
    try:
        out = _sd().default.device[1]
    except Exception:
        return None
    return out if isinstance(out, int) and out >= 0 else None


def _write_to_device(sd: Any, data: np.ndarray, sample_rate: int, device: int | None) -> None:
    """Blocking write of a whole buffer to one output device via its own stream."""
    with sd.OutputStream(
        samplerate=sample_rate, channels=1, dtype="float32", device=device
    ) as stream:
        stream.write(data)


def play(
    samples: np.ndarray,
    sample_rate: int,
    device: int | None,
    mirror_device: int | None = None,
) -> None:
    """Play mono float32 samples to ``device`` (blocking until finished).

    When ``mirror_device`` is given and differs from ``device``, the same audio
    is played simultaneously on that second device — used to make the prompt
    audible on real speakers while it is routed into a virtual loopback (e.g.
    BlackHole) for the agent.
    """
    sd = _sd()
    if mirror_device is None or mirror_device == device:
        sd.play(samples, samplerate=sample_rate, device=device, blocking=True)
        sd.stop()
        return

    # Two independent output streams so both devices play at once. Each runs in
    # its own thread doing a blocking write; we join both before returning.
    data = np.ascontiguousarray(samples, dtype=np.float32).reshape(-1, 1)
    errors: list[BaseException] = []

    def _run(dev: int | None) -> None:
        try:
            _write_to_device(sd, data, sample_rate, dev)
        except BaseException as exc:  # noqa: BLE001 — surfaced after join
            errors.append(exc)

    threads = [
        threading.Thread(target=_run, args=(dev,), daemon=True)
        for dev in (device, mirror_device)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if errors:
        raise errors[0]


class _MonitorBuffer:
    """Thread-safe FIFO of mono float32 samples for live passthrough.

    The capture thread calls :meth:`feed`; the audio output callback calls
    :meth:`read_into`. Pure numpy + a lock, so it is unit-testable without any
    audio hardware. When the buffer underruns, the remainder is filled with
    silence rather than blocking the output callback.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buf = np.zeros(0, dtype=np.float32)

    def feed(self, block: np.ndarray) -> None:
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        with self._lock:
            self._buf = np.concatenate((self._buf, block))

    def read_into(self, out: np.ndarray) -> int:
        """Fill ``out`` (1-D) with buffered samples; pad with silence. Returns
        the number of real (non-silence) samples written."""
        n = len(out)
        with self._lock:
            avail = min(n, len(self._buf))
            out[:avail] = self._buf[:avail]
            self._buf = self._buf[avail:]
        out[avail:] = 0.0
        return avail

    def pending(self) -> int:
        with self._lock:
            return len(self._buf)


class SpeakerMonitor:
    """Live passthrough player.

    Open as a context manager, then ``feed`` captured frames to hear them on
    ``device`` in near-real time. Used to make an agent's reply audible when its
    audio is routed digitally into the listen device (e.g. BlackHole).
    """

    def __init__(self, sample_rate: int, device: int | None, blocksize: int) -> None:
        self._sample_rate = sample_rate
        self._device = device
        self._blocksize = blocksize
        self._buffer = _MonitorBuffer()
        self._stream: Any = None

    def _callback(self, outdata, _frames, _time, status):  # noqa: ANN001
        self._buffer.read_into(outdata[:, 0])

    def feed(self, block: np.ndarray) -> None:
        self._buffer.feed(block)

    def __enter__(self) -> "SpeakerMonitor":
        sd = _sd()
        self._stream = sd.OutputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self._blocksize,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
