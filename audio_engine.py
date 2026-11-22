from collections import deque
from time import perf_counter

import numpy as np
import sounddevice as sd
from scipy.signal import freqz_sos

from audio_filters import AudioFilter
from audio_recording import AudioRecording


class AudioEngine:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self._stream = None
        self.metrics = (0.0, 0.0, 0)
        self.analysis_blocks = deque(maxlen=128)
        self.recording = AudioRecording(sample_rate)
        self._monitoring = (True, False, 0.5)
        self._requested_settings = ("lowpass", {"cutoff": 1000})
        self._requested_filter = AudioFilter("lowpass", sample_rate, cutoff=1000)
        self._active_filter = self._requested_filter
        self._next_filter = None
        self._fade_position = 0
        self._fade = np.linspace(0.0, 1.0, max(2, round(sample_rate * 0.020)))

    @property
    def active(self):
        return self._stream is not None and self._stream.active

    def set_monitoring(self, listen, use_filtered, volume):
        self._monitoring = (listen, use_filtered, volume)

    def set_filter(self, filter_type, **settings):
        if (filter_type, settings) == self._requested_settings:
            return
        self._requested_filter = AudioFilter(
            filter_type=filter_type, sample_rate=self.sample_rate, **settings
        )
        self._requested_settings = (filter_type, settings)

    def filter_response(self):
        kind, settings = self._requested_settings
        frequencies = np.linspace(0, self.sample_rate / 2, 24001)
        if kind == "notch":
            frequencies = np.unique(np.append(frequencies, settings["frequency"]))
        sos = self._requested_filter.sos
        if sos is None:
            return frequencies, np.zeros_like(frequencies)
        frequencies, response = freqz_sos(sos, worN=frequencies, fs=self.sample_rate)
        gain_db = 20 * np.log10(np.maximum(np.abs(response), 1e-6))
        return frequencies, gain_db

    def start(self, input_id, output_id):
        if self._stream is not None:
            raise RuntimeError("The audio stream is already open.")
        sd.check_input_settings(device=input_id, channels=1, dtype="float32", samplerate=self.sample_rate)
        sd.check_output_settings(device=output_id, channels=2, dtype="float32", samplerate=self.sample_rate)
        self.metrics = (0.0, 0.0, 0)
        self.analysis_blocks.clear()
        self._active_filter = self._requested_filter
        self._active_filter.reset()
        self._next_filter = None
        self._fade_position = 0
        stream = sd.Stream(
            device=(input_id, output_id), samplerate=self.sample_rate,
            channels=(1, 2), dtype="float32", blocksize=0,
            latency="high", callback=self._process_audio,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream = stream

    def start_recording(self):
        if not self.active:
            raise RuntimeError("Start live audio before recording.")
        self.recording.start()

    def stop(self):
        self.recording.stop()
        stream = self._stream
        if stream is None:
            return
        try:
            stream.abort()
        finally:
            try:
                stream.close()
            finally:
                self._stream = None

    def _filter_block(self, original):
        requested = self._requested_filter
        if self._next_filter is None and requested is not self._active_filter:
            self._next_filter = requested
            self._fade_position = 0
        if self._next_filter is None:
            return self._active_filter.process(original)
        previous = self._active_filter.process(original)
        current = self._next_filter.process(original)
        start = self._fade_position
        count = min(len(original), len(self._fade) - start)
        weights = self._fade[start:start + count]
        blended = current.copy()
        blended[:count] = previous[:count] * (1.0 - weights) + current[:count] * weights
        self._fade_position += count
        if self._fade_position == len(self._fade):
            self._active_filter = self._next_filter
            self._next_filter = None
        return blended

    def _process_audio(self, indata, outdata, frames, time_info, status):
        started_at = perf_counter()
        listen, use_filtered, volume = self._monitoring
        original = indata[:, 0]
        filtered = self._filter_block(original)
        self.recording.append(original, filtered, status)
        self.analysis_blocks.append((original.copy(), filtered.copy()))
        if listen:
            playback = filtered if use_filtered else original
            np.multiply(playback, volume, out=outdata[:, 0])
            np.clip(outdata[:, 0], -1.0, 1.0, out=outdata[:, 0])
            outdata[:, 1] = outdata[:, 0]
        else:
            outdata.fill(0)
        peak = float(np.max(np.abs(original))) if frames else 0.0
        warnings = self.metrics[2] + int(bool(status))
        elapsed_ms = (perf_counter() - started_at) * 1000
        self.metrics = (peak, elapsed_ms, warnings)
