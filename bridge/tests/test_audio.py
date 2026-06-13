"""Unit tests for bridge.audio resampling."""
import numpy as np

from bridge import audio


def test_empty():
    assert audio.down_24k_to_16k(b"") == b""
    assert audio.up_16k_to_24k(b"") == b""


def test_down_size_20ms():
    # 24 kHz * 20 ms = 480 samples = 960 bytes
    pcm = (b"\x00\x00") * 480
    out = audio.down_24k_to_16k(pcm)
    # 16 kHz * 20 ms = 320 samples = 640 bytes
    assert len(out) == 640


def test_up_size_20ms():
    # 16 kHz * 20 ms = 320 samples = 640 bytes
    pcm = (b"\x00\x00") * 320
    out = audio.up_16k_to_24k(pcm)
    # 24 kHz * 20 ms = 480 samples = 960 bytes
    assert len(out) == 960


def test_silence_stays_silence_within_clip_bound():
    # Pure silence should map to silence (or near-silence within int16 quant).
    pcm = (b"\x00\x00") * 4800  # 200 ms
    out_down = audio.down_24k_to_16k(pcm)
    assert max(abs(s) for s in np.frombuffer(out_down, dtype="<i2")) == 0


def test_sine_preserves_frequency_after_round_trip():
    # 440 Hz sine at 24 kHz, 200 ms.
    fs_in = 24000
    duration = 0.2
    t = np.arange(int(fs_in * duration)) / fs_in
    pcm_in = (np.sin(2 * np.pi * 440 * t) * 16000).astype("<i2").tobytes()

    pcm_16k = audio.down_24k_to_16k(pcm_in)
    pcm_24k_back = audio.up_16k_to_24k(pcm_16k)

    samples = np.frombuffer(pcm_24k_back, dtype="<i2").astype(np.float64)
    # FFT peak should still sit at ~440 Hz.
    fft = np.fft.rfft(samples)
    freqs = np.fft.rfftfreq(len(samples), 1 / 24000)
    peak_hz = freqs[np.argmax(np.abs(fft))]
    assert abs(peak_hz - 440) < 10  # within 10 Hz
