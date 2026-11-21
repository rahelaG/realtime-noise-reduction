from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from scipy.io import wavfile
from scipy.signal import resample_poly
from math import gcd

from audio_filters import AudioFilter
from auto_noise import detect_steady_tone


def read_voice(path):
    sample_rate, data = wavfile.read(path)
    if data.size == 0 or data.ndim not in (1, 2):
        raise ValueError("Choose a WAV file containing audio.")
    if sample_rate < 8000 or not 1 <= len(data) / sample_rate <= 60:
        raise ValueError("Choose a WAV from 1 to 60 seconds, at 8 kHz or higher.")

    samples = data.astype(np.float64)
    if np.issubdtype(data.dtype, np.unsignedinteger):
        midpoint = (int(np.iinfo(data.dtype).max) + 1) / 2
        samples = (samples - midpoint) / midpoint
    elif np.issubdtype(data.dtype, np.signedinteger):
        samples /= abs(int(np.iinfo(data.dtype).min))

    if samples.ndim == 2:
        samples = samples.mean(axis=1)

    if not np.isfinite(samples).all():
        raise ValueError("The WAV file contains invalid audio samples.")

    target_rate = 48000
    if sample_rate != target_rate:
        divisor = gcd(sample_rate, target_rate)
        samples = resample_poly(samples, target_rate // divisor, sample_rate // divisor)

    peak = np.max(np.abs(samples))
    if peak < 1e-8:
        raise ValueError("Choose a WAV with audible speech.")

    return target_rate, samples * (0.7 / peak)


def filter_in_blocks(samples, sample_rate, frequency):
    audio_filter = AudioFilter(
        filter_type="notch",
        sample_rate=sample_rate,
        frequency=frequency,
        quality=20.0,
    )
    block_size = 1024
    return np.concatenate([
        audio_filter.process(samples[start:start + block_size])
        for start in range(0, len(samples), block_size)
    ])


def rms(samples):
    return float(np.sqrt(np.mean(samples ** 2)))


def run_tone_test(voice, sample_rate, frequency, tone_percent):
    time = np.arange(len(voice)) / sample_rate
    tone = (tone_percent / 100) * np.sin(2 * np.pi * frequency * time)
    detected = detect_steady_tone(tone[:sample_rate], sample_rate)
    if detected is None:
        raise ValueError("No stable tone was found in the calibration sample.")

    noisy = voice + tone
    filtered = filter_in_blocks(noisy, sample_rate, detected)
    filtered_tone = filter_in_blocks(tone, sample_rate, detected)
    attenuation = 20 * np.log10(rms(tone) / max(rms(filtered_tone), 1e-12))
    return detected, attenuation, {"Clean": voice, "Noisy": noisy, "Filtered": filtered}


class TestLab(QWidget):
    def __init__(self, live_is_active, output_device):
        super().__init__()
        self.live_is_active = live_is_active
        self.output_device = output_device
        self.voice = None
        self.sample_rate = None
        self.results = {}

        layout = QVBoxLayout(self)
        instructions = QLabel(
            "Load a voice WAV. The test calibrates on a generated tone, "
            "then applies the detected filter to the voice and tone together."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        open_button = QPushButton("Open WAV")
        open_button.clicked.connect(self.open_voice)
        layout.addWidget(open_button)

        self.file_label = QLabel("No recording loaded.")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        form = QFormLayout()
        self.frequency = QSpinBox()
        self.frequency.setRange(40, 3000)
        self.frequency.setValue(1000)
        self.frequency.setSuffix(" Hz")
        form.addRow("Test tone", self.frequency)

        self.level = QSpinBox()
        self.level.setRange(1, 25)
        self.level.setValue(10)
        self.level.setSuffix("%")
        form.addRow("Tone peak (relative to full scale)", self.level)
        layout.addLayout(form)

        self.run_button = QPushButton("Run Test")
        self.run_button.setObjectName("PrimaryButton")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.run_test)
        layout.addWidget(self.run_button)

        self.result_label = QLabel("Load a WAV file to begin.")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        playback = QHBoxLayout()
        self.play_buttons = []
        for variant in ("Clean", "Noisy", "Filtered"):
            button = QPushButton(f"Play {variant}")
            button.setEnabled(False)
            button.clicked.connect(lambda checked=False, name=variant: self.play_audio(name))
            playback.addWidget(button)
            self.play_buttons.append(button)

        stop_button = QPushButton("Stop Playback")
        stop_button.clicked.connect(self.stop_playback)
        playback.addWidget(stop_button)
        layout.addLayout(playback)

        self.playback_message = QLabel("")
        self.playback_message.setWordWrap(True)
        layout.addWidget(self.playback_message)
        layout.addStretch()

        self.frequency.valueChanged.connect(self.invalidate_result)
        self.level.valueChanged.connect(self.invalidate_result)

    def stop_playback(self):
        sd.stop()

    def invalidate_result(self, _value=None):
        self.stop_playback()
        self.results = {}
        self.playback_message.clear()
        for button in self.play_buttons:
            button.setEnabled(False)
        if self.voice is not None:
            self.result_label.setText("Press Run Test to process these settings.")

    def open_voice(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open voice recording", "", "WAV audio (*.wav)"
        )
        if not path:
            return

        try:
            sample_rate, voice = read_voice(path)
        except (ValueError, OSError) as error:
            self.playback_message.setText(f"Could not load WAV: {error}")
            return

        self.sample_rate = sample_rate
        self.voice = voice
        self.file_label.setText(
            f"{Path(path).name} · {len(voice) / sample_rate:.1f} s"
        )
        self.run_button.setEnabled(True)
        self.invalidate_result()

    def run_test(self):
        self.invalidate_result()
        try:
            detected, attenuation, self.results = run_tone_test(
                self.voice, self.sample_rate, self.frequency.value(), self.level.value()
            )
        except ValueError as error:
            self.result_label.setText(str(error))
            return

        for button in self.play_buttons:
            button.setEnabled(True)
        self.result_label.setText(
            f"Detected tone: {detected:,.1f} Hz\n"
            f"Test tone attenuation: {attenuation:.1f} dB"
        )

    def play_audio(self, variant):
        if self.live_is_active():
            self.playback_message.setText(
                "Stop the microphone in Live Studio before playing a test."
            )
            return

        device = self.output_device()
        if device is None:
            self.playback_message.setText("Select an output device in Live Studio.")
            return

        self.playback_message.clear()
        samples = self.results[variant]
        peak = max(np.max(np.abs(track)) for track in self.results.values())
        gain = min(0.5, 0.95 / max(peak, 1e-12))
        stereo = np.column_stack((samples, samples)).astype(np.float32)
        stereo *= gain

        try:
            sd.play(stereo, samplerate=self.sample_rate, device=device)
        except (sd.PortAudioError, ValueError) as error:
            self.playback_message.setText(f"Could not play audio: {error}")
