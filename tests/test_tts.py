import numpy as np

from agent_say import tts


def test_resample_linear_changes_length():
    audio = np.linspace(-1.0, 1.0, 10, dtype=np.float32)

    out = tts._resample_linear(audio, 10_000, 20_000)

    assert out.dtype == np.float32
    assert out.size == 20
    assert np.isclose(out[0], audio[0])
    assert np.isclose(out[-1], audio[-1])
