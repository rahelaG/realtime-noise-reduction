import numpy as np


def detect_steady_tone(samples, sample_rate):
    """Find one narrow tone that persists throughout one second of audio."""
    if len(samples) < sample_rate:
        return None

    block_size = sample_rate // 4
    window = np.hanning(block_size)
    fft_size = sample_rate * 2
    frequencies = np.fft.rfftfreq(fft_size, d=1 / sample_rate)
    search = np.flatnonzero((frequencies >= 40) & (frequencies <= 3000))
    peaks = []

    for block in np.split(samples[-4 * block_size:], 4):
        centered = block - np.mean(block)
        if np.sqrt(np.mean(centered ** 2)) < 0.001:
            return None

        spectrum = np.abs(np.fft.rfft(centered * window, n=fft_size))
        peak = search[np.argmax(spectrum[search])]
        frequency = frequencies[peak]

        # Compare a narrow peak against nearby frequencies outside its lobe.
        nearby = np.abs(frequencies - frequency)
        background = np.median(spectrum[(nearby >= 16) & (nearby <= 40)])
        if spectrum[peak] < 8 * max(background, 1e-12):
            return None

        peaks.append(frequency)

    if max(peaks) - min(peaks) > 2:
        return None

    return float(np.median(peaks))