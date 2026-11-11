import numpy as np
import sounddevice as sd

from audio_filters import AudioFilter


class AudioEngine:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self._stream = None
        self._monitoring = (True, False, 0.5)

        self._filter = AudioFilter(
            filter_type="lowpass",
            sample_rate=sample_rate,
            cutoff=1000,
        )

    @property
    def active(self):
        return self._stream is not None and self._stream.active

    def set_monitoring(self, listen, use_filtered, volume):
        self._monitoring = (listen, use_filtered, volume)

    def set_filter(self, filter_type, **settings):
        new_filter = AudioFilter(
            filter_type=filter_type,
            sample_rate=self.sample_rate,
            **settings,
        )
        self._filter = new_filter

    def start(self, input_id, output_id):
        if self._stream is not None:
            raise RuntimeError("The audio stream is already open.")

        sd.check_input_settings(
            device=input_id,
            channels=1,
            dtype="float32",
            samplerate=self.sample_rate,
        )
        sd.check_output_settings(
            device=output_id,
            channels=2,
            dtype="float32",
            samplerate=self.sample_rate,
        )

        self._filter.reset()

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
            try:
                stream.abort()
            finally:
                stream.close()
        finally:
            self._stream = None

    def _process_audio(self, indata, outdata, frames, time_info, status):
        listen, use_filtered, volume = self._monitoring

        original = indata[:, 0]
        active_filter = self._filter
        filtered = active_filter.process(original)

        if not listen:
            outdata.fill(0)
            return

        playback = filtered if use_filtered else original
        np.multiply(playback, volume, out=outdata[:, 0])
        np.clip(outdata[:, 0], -1.0, 1.0, out=outdata[:, 0])
        outdata[:, 1] = outdata[:, 0]