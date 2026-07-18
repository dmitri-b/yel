"""Tests for the live-passthrough ring buffer (no audio hardware)."""

import numpy as np

from yel.audio import _MonitorBuffer


def test_fifo_order_across_reads():
    buf = _MonitorBuffer()
    buf.feed(np.array([1, 2, 3], dtype=np.float32))
    buf.feed(np.array([4, 5], dtype=np.float32))
    assert buf.pending() == 5

    out = np.empty(2, dtype=np.float32)
    n = buf.read_into(out)
    assert n == 2
    assert list(out) == [1.0, 2.0]

    out2 = np.empty(3, dtype=np.float32)
    n2 = buf.read_into(out2)
    assert n2 == 3
    assert list(out2) == [3.0, 4.0, 5.0]
    assert buf.pending() == 0


def test_underrun_pads_with_silence():
    buf = _MonitorBuffer()
    buf.feed(np.array([0.5, 0.5], dtype=np.float32))
    out = np.full(5, 9.0, dtype=np.float32)
    n = buf.read_into(out)
    assert n == 2
    # First two are real samples; the rest is zero-filled.
    assert list(out) == [0.5, 0.5, 0.0, 0.0, 0.0]


def test_read_from_empty_is_all_silence():
    buf = _MonitorBuffer()
    out = np.full(4, 7.0, dtype=np.float32)
    n = buf.read_into(out)
    assert n == 0
    assert list(out) == [0.0, 0.0, 0.0, 0.0]


def test_feed_flattens_and_casts():
    buf = _MonitorBuffer()
    buf.feed([1, 2, 3])  # plain list of ints
    assert buf.pending() == 3
    out = np.empty(3, dtype=np.float32)
    buf.read_into(out)
    assert out.dtype == np.float32
    assert list(out) == [1.0, 2.0, 3.0]
