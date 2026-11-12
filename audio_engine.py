import numpy as np
import sounddevice as sd

from audio_filters import AudioFilter


class AudioEngine:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self._stream = None
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

    def start(self, input_id, output_id):
        if self._stream is not None:
            raise RuntimeError("The audio stream is already open.")

        sd.check_input_settings(
            device=input_id, channels=1, dtype="float32",
            samplerate=self.sample_rate,
        )
        sd.check_output_settings(
            device=output_id, channels=2, dtype="float32",
            samplerate=self.sample_rate,
        )

        self._active_filter = self._requested_filter
        self._active_filter.reset()
        self._next_filter = None
        self._fade_position = 0

        stream = sd.Stream(
            device=(input_id, output_id),
            samplerate=self.sample_rate,
            channels=(1, 2),
            dtype="float32",
            blocksize=0,
            latency="high",
            callback=self._process_audio,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream = stream

    def stop(self):
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
        blended[:count] = (
            previous[:count] * (1.0 - weights) + current[:count] * weights
        )
        self._fade_position += count
        if self._fade_position == len(self._fade):
            self._active_filter = self._next_filter
            self._next_filter = None
        return blended

    def _process_audio(self, indata, outdata, frames, time_info, status):
        listen, use_filtered, volume = self._monitoring
        original = indata[:, 0]
        filtered = self._filter_block(original)

        if not listen:
            outdata.fill(0)
            return

        playback = filtered if use_filtered else original
        np.multiply(playback, volume, out=outdata[:, 0])
        np.clip(outdata[:, 0], -1.0, 1.0, out=outdata[:, 0])
        outdata[:, 1] = outdata[:, 0]
