from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

import numpy as np
from scipy.io import wavfile


class AudioRecording:
    def __init__(self, sample_rate, max_seconds=60):
        self.sample_rate = sample_rate
        self.capacity = int(sample_rate * max_seconds)
        self._lock = Lock()
        self._buffer = None
        self._frames = 0
        self._recording = False
        self._warnings = 0

    @property
    def status(self):
        with self._lock:
            return self._recording, self._frames, self._warnings

    def start(self):
        buffer = np.empty((self.capacity, 2), dtype=np.float32)
        with self._lock:
            if self._recording:
                raise RuntimeError("A recording is already running.")
            self._buffer = buffer
            self._frames = 0
            self._warnings = 0
            self._recording = True

    def append(self, original, filtered, status=False):
        with self._lock:
            if not self._recording:
                return
            count = min(len(original), self.capacity - self._frames)
            end = self._frames + count
            self._buffer[self._frames:end, 0] = original[:count]
            self._buffer[self._frames:end, 1] = filtered[:count]
            self._frames = end
            self._warnings += int(bool(status))
            if end == self.capacity:
                self._recording = False

    def stop(self):
        with self._lock:
            self._recording = False

    def snapshot(self):
        with self._lock:
            if self._recording:
                raise RuntimeError("Stop recording before exporting.")
            if not self._frames:
                raise ValueError("There is no recorded audio to export.")
            samples = self._buffer[:self._frames]
            warnings = self._warnings
        return samples.copy(), warnings

    def export(self, parent):
        samples, warnings = self.snapshot()
        if not np.isfinite(samples).all():
            raise ValueError("The recording contains invalid samples.")
        peak = float(np.max(np.abs(samples)))
        gain = min(1.0, 0.99 / max(peak, 1e-12))
        pcm = np.rint(np.clip(samples * gain, -1.0, 1.0) * 32767).astype(np.int16)
        name = datetime.now().strftime("recording_%Y%m%d_%H%M%S_") + uuid4().hex[:6]
        destination = Path(parent) / name
        destination.mkdir()
        try:
            wavfile.write(destination / "original.wav", self.sample_rate, pcm[:, 0].copy())
            wavfile.write(destination / "filtered.wav", self.sample_rate, pcm[:, 1].copy())
            (destination / "details.txt").write_text(
                f"Sample rate: {self.sample_rate} Hz\n"
                f"Frames per file: {len(samples)}\n"
                f"Duration: {len(samples) / self.sample_rate:.3f} s\n"
                f"Shared export gain: {gain:.8f}\n"
                f"Audio callbacks reporting warnings during recording: {warnings}\n"
                "Original is microphone input; filtered is the processed version.\n"
                "Monitoring volume and Listen do not affect the saved signals.\n"
                "Filter changes during recording are included in filtered.wav.\n"
                "Device overruns may cause gaps in captured sound.\n",
                encoding="utf-8",
            )
        except Exception:
            for filename in ("original.wav", "filtered.wav", "details.txt"):
                (destination / filename).unlink(missing_ok=True)
            destination.rmdir()
            raise
        return destination, gain
