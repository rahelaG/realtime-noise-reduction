import numpy as np
import sounddevice as sd


class AudioEngine:
    def __init__(self, sample_rate=48000):
        self.sample_rate = sample_rate
        self._stream = None

    @property
    def active(self):
        return self._stream is not None and self._stream.active

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

        stream = sd.Stream(
            device=(input_id, output_id),
            samplerate=self.sample_rate,
            channels=(1, 2),
            dtype="float32",
            blocksize=0,
            latency="high",
            callback=self._copy_audio,
        )

        try:
            stream.start()
        except Exception:
            stream.close()
            raise

        self._stream = stream

    def stop(self):
        if self._stream is None:
            return

        stream = self._stream
        try:
            stream.abort()
        finally:
            stream.close()
            self._stream = None

    @staticmethod
    def _copy_audio(indata, outdata, frames, time_info, status):
        np.multiply(indata[:, 0], 0.5, out=outdata[:, 0])
        outdata[:, 1] = outdata[:, 0]