from math import gcd
from pathlib import Path

import numpy as np
import sounddevice as sd
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
from scipy.io import wavfile
from scipy.signal import butter, resample_poly, sosfilt

from audio_filters import AudioFilter
from auto_noise import detect_steady_tone


PRESETS = [
    ("Reduce low rumble", "highpass", {"cutoff": 300.0}),
    ("Reduce high hiss", "lowpass", {"cutoff": 3500.0}),
    ("Reduce mid-band noise", "bandstop", {"low": 800.0, "high": 1200.0}),
    ("Reduce 1 kHz tone", "notch", {"frequency": 1000.0, "quality": 20.0}),
    ("Reduce 50 Hz hum", "notch", {"frequency": 50.0, "quality": 20.0}),
]


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


def filter_in_blocks(samples, sample_rate, filter_type, settings):
    audio_filter = AudioFilter(filter_type, sample_rate, **settings)
    return np.concatenate([
        audio_filter.process(samples[start:start + 1024])
        for start in range(0, len(samples), 1024)
    ])


def rms(samples):
    return float(np.sqrt(np.mean(np.square(samples))))


def generate_noise(length, sample_rate, kind, level, frequency=1000, low=800, high=1200):
    if length < sample_rate:
        raise ValueError("At least one second of audio is required.")
    if not 0 < level <= 25:
        raise ValueError("Noise level must be between 0 and 25 percent RMS.")
    t = np.arange(length) / sample_rate
    if kind == "tone":
        if not 40 <= frequency <= 3000:
            raise ValueError("Test tone must be between 40 and 3000 Hz.")
        noise = np.sin(2 * np.pi * frequency * t)
    else:
        rng = np.random.default_rng(42)
        padding = sample_rate
        white = rng.standard_normal(length + padding)
        if kind == "rumble":
            limits = [40, 180]
        elif kind == "hiss":
            limits = [6000, 12000]
        elif kind == "band":
            if not 0 < low < high < sample_rate / 2:
                raise ValueError("Noise band must satisfy 0 < low < high < Nyquist.")
            limits = [low, high]
        else:
            raise ValueError("Unknown noise type.")
        sos = butter(4, limits, btype="bandpass", fs=sample_rate, output="sos")
        noise = sosfilt(sos, white)[padding:]
    return noise * ((level / 100) / max(rms(noise), 1e-12))


def run_controlled_test(voice, sample_rate, noise_kind, noise_settings,
                        mode, filter_type, filter_settings):
    noise = generate_noise(len(voice), sample_rate, noise_kind, **noise_settings)
    calibration = ""
    if mode == "auto":
        detected = detect_steady_tone(noise[:sample_rate], sample_rate)
        if detected is None:
            filter_type, filter_settings = "none", {}
            calibration = "No stable tone detected. No filter applied.\n"
        else:
            filter_type = "notch"
            filter_settings = {"frequency": float(detected), "quality": 20.0}
            calibration = f"Detected tone: {detected:,.1f} Hz.\n"
    noisy = voice + noise
    filtered = filter_in_blocks(noisy, sample_rate, filter_type, filter_settings)
    filtered_noise = filter_in_blocks(noise, sample_rate, filter_type, filter_settings)
    attenuation = 20 * np.log10(rms(noise) / max(rms(filtered_noise), 1e-12))
    parameters = ", ".join(f"{key}={value:g}" for key, value in filter_settings.items())
    description = f"{filter_type}" + (f" ({parameters})" if parameters else "")
    text = (f"{calibration}Applied filter: {description}\n"
            f"Added noise attenuation: {attenuation:.1f} dB\n"
            "Attenuation measures the generated noise only. Listen to check voice quality.")
    return text, {"Clean": voice.copy(), "Noisy": noisy, "Filtered": filtered}


class TestLab(QWidget):
    def __init__(self, live_is_active, output_device):
        super().__init__()
        self.live_is_active = live_is_active
        self.output_device = output_device
        self.voice = None
        self.sample_rate = None
        self.results = {}
        layout = QVBoxLayout(self)
        intro = QLabel("Load a clean voice WAV, add a known noise, then choose how to filter it.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        open_button = QPushButton("Open WAV")
        open_button.clicked.connect(self.open_voice)
        layout.addWidget(open_button)
        self.file_label = QLabel("No recording loaded.")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        noise_group = QGroupBox("1. Added noise")
        noise_form = QFormLayout(noise_group)
        self.noise_kind = QComboBox()
        for label, key in [("Single tone / hum", "tone"), ("Low-frequency rumble", "rumble"),
                           ("High-frequency hiss", "hiss"), ("Band-limited noise", "band")]:
            self.noise_kind.addItem(label, key)
        noise_form.addRow("Noise type", self.noise_kind)
        self.frequency = self.spin(40, 3000, 1000)
        self.noise_low = self.spin(1, 23999, 800)
        self.noise_high = self.spin(1, 23999, 1200)
        noise_form.addRow("Tone frequency", self.frequency)
        noise_form.addRow("Noise band start", self.noise_low)
        noise_form.addRow("Noise band end", self.noise_high)
        self.level = QSpinBox()
        self.level.setRange(1, 25)
        self.level.setValue(10)
        self.level.setSuffix("% RMS")
        noise_form.addRow("Noise level (relative to full scale)", self.level)
        self.noise_hint = QLabel()
        self.noise_hint.setWordWrap(True)
        noise_form.addRow(self.noise_hint)
        layout.addWidget(noise_group)

        filter_group = QGroupBox("2. Filter configuration")
        filter_form = QFormLayout(filter_group)
        self.mode = QComboBox()
        for label, key in [("Presets", "presets"), ("Custom", "custom"), ("Auto", "auto")]:
            self.mode.addItem(label, key)
        filter_form.addRow("Mode", self.mode)
        self.preset = QComboBox()
        for name, _, _ in PRESETS:
            self.preset.addItem(name)
        filter_form.addRow("Preset", self.preset)
        self.filter_type = QComboBox()
        for label, key in [("High-pass", "highpass"), ("Low-pass", "lowpass"),
                           ("Band-stop", "bandstop"), ("Notch", "notch")]:
            self.filter_type.addItem(label, key)
        filter_form.addRow("Filter type", self.filter_type)
        self.cutoff = self.spin(1, 23999, 300)
        self.filter_low = self.spin(1, 23999, 800)
        self.filter_high = self.spin(1, 23999, 1200)
        self.notch_frequency = self.spin(1, 23999, 1000)
        self.quality = QDoubleSpinBox()
        self.quality.setRange(0.1, 200)
        self.quality.setValue(20)
        self.quality.setDecimals(1)
        for label, widget in [("Cutoff frequency", self.cutoff), ("Stop band start", self.filter_low),
                              ("Stop band end", self.filter_high), ("Notch frequency", self.notch_frequency),
                              ("Notch quality Q", self.quality)]:
            filter_form.addRow(label, widget)
        self.filter_hint = QLabel()
        self.filter_hint.setWordWrap(True)
        filter_form.addRow(self.filter_hint)
        layout.addWidget(filter_group)
        self.noise_form = noise_form
        self.filter_form = filter_form

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
        for combo in (self.noise_kind, self.mode, self.preset, self.filter_type):
            combo.currentIndexChanged.connect(self.settings_changed)
        for spin in (self.frequency, self.noise_low, self.noise_high, self.level,
                     self.cutoff, self.filter_low, self.filter_high, self.notch_frequency, self.quality):
            spin.valueChanged.connect(self.invalidate_result)
        self.update_fields()

    @staticmethod
    def spin(low, high, value):
        widget = QSpinBox()
        widget.setRange(low, high)
        widget.setValue(value)
        widget.setSuffix(" Hz")
        return widget

    @staticmethod
    def show_row(form, widget, visible):
        widget.setVisible(visible)
        label = form.labelForField(widget)
        if label is not None:
            label.setVisible(visible)

    def update_fields(self):
        kind = self.noise_kind.currentData()
        for widget, visible in [(self.frequency, kind == "tone"),
                                (self.noise_low, kind == "band"), (self.noise_high, kind == "band")]:
            self.show_row(self.noise_form, widget, visible)
        self.noise_hint.setText({
            "tone": "A steady tone. Try a matching notch, or Auto.",
            "rumble": "Noise concentrated around 40-180 Hz. Try Reduce low rumble.",
            "hiss": "Noise concentrated around 6-12 kHz. Try Reduce high hiss.",
            "band": "Noise concentrated in your selected band. Try a matching band-stop.",
        }[kind])
        mode = self.mode.currentData()
        custom = mode == "custom"
        kind = self.filter_type.currentData()
        self.show_row(self.filter_form, self.preset, mode == "presets")
        self.show_row(self.filter_form, self.filter_type, custom)
        for widget, visible in [(self.cutoff, kind in ("highpass", "lowpass")),
                                (self.filter_low, kind == "bandstop"), (self.filter_high, kind == "bandstop"),
                                (self.notch_frequency, kind == "notch"), (self.quality, kind == "notch")]:
            self.show_row(self.filter_form, widget, custom and visible)
        if mode == "auto":
            text = ("Auto analyzes one second of generated noise alone, simulating a noise-only calibration. "
                    "It detects steady tones and applies a notch; broadband noise may produce no detection.")
        elif mode == "presets":
            _, selected, parameters = PRESETS[self.preset.currentIndex()]
            text = f"{selected}: " + ", ".join(f"{k}={v:g}" for k, v in parameters.items())
        else:
            text = {"highpass": "Reduces low frequencies below the cutoff.",
                    "lowpass": "Reduces high frequencies above the cutoff.",
                    "bandstop": "Reduces frequencies between the two band limits.",
                    "notch": "Reduces a narrow region around the notch frequency. Higher Q means a narrower region."}[kind]
        self.filter_hint.setText(text)

    def settings_changed(self, _value=None):
        self.update_fields()
        self.invalidate_result()

    def stop_playback(self):
        sd.stop()

    def invalidate_result(self, _value=None):
        self.stop_playback()
        self.results = {}
        self.playback_message.clear()
        for button in self.play_buttons:
            button.setEnabled(False)
        if self.voice is not None:
            self.result_label.setText("Settings changed. Press Run Test to update the results.")

    def open_voice(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open voice recording", "", "WAV audio (*.wav)")
        if not path:
            return
        try:
            sample_rate, voice = read_voice(path)
        except (ValueError, OSError) as error:
            self.playback_message.setText(f"Could not load WAV: {error}")
            return
        self.sample_rate, self.voice = sample_rate, voice
        self.file_label.setText(f"{Path(path).name} · {len(voice) / sample_rate:.1f} s")
        self.run_button.setEnabled(True)
        self.invalidate_result()

    def selected_filter(self):
        if self.mode.currentData() == "presets":
            _, kind, settings = PRESETS[self.preset.currentIndex()]
            return kind, dict(settings)
        kind = self.filter_type.currentData()
        if kind in ("highpass", "lowpass"):
            return kind, {"cutoff": self.cutoff.value()}
        if kind == "bandstop":
            return kind, {"low": self.filter_low.value(), "high": self.filter_high.value()}
        return kind, {"frequency": self.notch_frequency.value(), "quality": self.quality.value()}

    def run_test(self):
        if self.voice is None:
            return
        self.invalidate_result()
        kind, settings = self.selected_filter()
        try:
            text, results = run_controlled_test(
                self.voice, self.sample_rate, self.noise_kind.currentData(),
                {"level": self.level.value(), "frequency": self.frequency.value(),
                 "low": self.noise_low.value(), "high": self.noise_high.value()},
                self.mode.currentData(), kind, settings,
            )
        except ValueError as error:
            self.result_label.setText(str(error))
            return
        self.results = results
        self.result_label.setText(text)
        for button in self.play_buttons:
            button.setEnabled(True)

    def play_audio(self, variant):
        if variant not in self.results:
            return
        if self.live_is_active():
            self.playback_message.setText("Stop the microphone in Live Studio before playing a test.")
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
