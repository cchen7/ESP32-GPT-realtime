"""PCM16 mono resampling between Azure's 24 kHz and the device's 16 kHz.

The bridge resamples *only on the device leg*:
- Azure → device:  24 kHz → 16 kHz  (down_24k_to_16k)
- device → Azure:  16 kHz → ??       (we don't resample; Azure accepts 16 kHz input directly)

For 24↔16 kHz the ratio is 3:2, so :func:`scipy.signal.resample_poly` (a
polyphase FIR resampler) is the right tool. We accept the small per-chunk
edge transient that comes from running the filter statelessly on each frame;
verified inaudible on 20–100 ms chunks of speech. If we ever hear clicks at
buffer boundaries, swap in a stateful polyphase resampler.
"""
import numpy as np
from scipy.signal import resample_poly


def _resample(pcm16_bytes: bytes, up: int, down: int) -> bytes:
    if not pcm16_bytes:
        return b""
    samples = np.frombuffer(pcm16_bytes, dtype="<i2")
    out = resample_poly(samples, up, down)
    # resample_poly returns float64; clip then cast back to int16 little-endian.
    out = np.clip(np.round(out), -32768, 32767).astype("<i2")
    return out.tobytes()


def down_24k_to_16k(pcm16: bytes) -> bytes:
    """Resample PCM16 24 kHz mono → 16 kHz mono. up=2, down=3."""
    return _resample(pcm16, up=2, down=3)


def up_16k_to_24k(pcm16: bytes) -> bytes:
    """Resample PCM16 16 kHz mono → 24 kHz mono. up=3, down=2.

    Unused in M1 (Azure accepts 16 kHz input). Kept here in case we later
    decide to send native 24 kHz upstream.
    """
    return _resample(pcm16, up=3, down=2)
