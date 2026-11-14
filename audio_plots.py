import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget


class AudioPlots(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.sample_rate = engine.sample_rate
        self.history = np.empty((2, 0))
        self.window = np.hanning(self.sample_rate)
        self.frequencies = np.fft.rfftfreq(
            self.sample_rate, d=1 / self.sample_rate
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.waveform = self.make_plot("Waveform", "Time", "ms", "Amplitude")
        self.waveform.setXRange(-50, 0, padding=0)
        self.waveform.setYRange(-1, 1, padding=0)

        self.spectrum = self.make_plot(
            "Spectrum", "Frequency", "Hz", "Level (dBFS)"
        )
        self.spectrum.setXRange(0, 6000, padding=0)
        self.spectrum.setYRange(-120, 0, padding=0)

        self.response = self.make_plot(
            "Filter Response", "Frequency", "Hz", "Gain (dB)"
        )
        self.response.setXRange(0, 6000, padding=0)
        self.response.setYRange(-120, 5, padding=0)

        self.wave_curves = self.make_comparison_curves(self.waveform)
        self.spectrum_curves = self.make_comparison_curves(self.spectrum)
        self.response_curve = self.response.plot(
            pen=pg.mkPen("#2dd4bf", width=2)
        )

        self.note = QLabel(
            "Press Start for live data. Drag to pan and scroll to zoom."
        )
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.update_response()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(80)

    def make_plot(self, title, x_label, x_unit, y_label):
        plot = pg.PlotWidget(background="#111827")
        plot.setMinimumHeight(250)
        plot.setLabel("bottom", x_label, units=x_unit)
        plot.setLabel("left", y_label)
        plot.showGrid(x=True, y=True, alpha=0.2)
        self.tabs.addTab(plot, title)
        return plot

    @staticmethod
    def make_comparison_curves(plot):
        plot.addLegend()
        return (
            plot.plot(name="Original", pen=pg.mkPen("#60a5fa", width=2)),
            plot.plot(name="Filtered", pen=pg.mkPen("#2dd4bf", width=2)),
        )

    def reset_live(self):
        self.history = np.empty((2, 0))
        for curve in (*self.wave_curves, *self.spectrum_curves):
            curve.setData([], [])
        self.note.setText("Collecting the first second for the spectrum...")

    def update_response(self):
        frequencies, gain_db = self.engine.filter_response()
        self.response_curve.setData(frequencies, gain_db)

    def refresh(self):
        queue = self.engine.analysis_blocks
        count = len(queue)
        if not count:
            return

        blocks = [queue.popleft() for _ in range(count)]
        new_samples = np.concatenate(
            [np.stack((original, filtered)) for original, filtered in blocks],
            axis=1,
        )
        self.history = np.concatenate((self.history, new_samples), axis=1)
        self.history = self.history[:, -self.sample_rate:].copy()

        waveform = self.history[:, -round(0.050 * self.sample_rate):]
        time_ms = (
            np.arange(1 - waveform.shape[1], 1) * 1000 / self.sample_rate
        )
        for curve, samples in zip(self.wave_curves, waveform):
            curve.setData(time_ms, samples)

        if self.history.shape[1] < self.sample_rate:
            return

        amplitude = np.abs(
            np.fft.rfft(self.history * self.window, axis=1)
        )
        amplitude *= 2 / self.window.sum()
        amplitude[:, 0] *= 0.5
        if self.sample_rate % 2 == 0:
            amplitude[:, -1] *= 0.5

        levels_db = 20 * np.log10(np.maximum(amplitude, 1e-6))
        for curve, levels in zip(self.spectrum_curves, levels_db):
            curve.setData(self.frequencies, levels)

        message = "Spectrum: last 1 second. Drag to pan and scroll to zoom."
        if self.note.text() != message:
            self.note.setText(message)