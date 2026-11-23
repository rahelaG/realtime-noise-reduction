import sounddevice as sd
import sys
from pathlib import Path
from test_lab import TestLab

from PySide6.QtCore import Qt, QTimer
from audio_engine import AudioEngine
from audio_plots import AudioPlots
from auto_noise import detect_steady_tone
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QCheckBox,
    QSlider,
    QDoubleSpinBox,
    QFormLayout,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def make_label(text, object_name=None):
    label = QLabel(text)
    label.setWordWrap(True)

    if object_name:
        label.setObjectName(object_name)

    return label


def make_card(title, description=None):
    card = QFrame()
    card.setObjectName("Card")

    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)
    layout.addWidget(make_label(title, "SectionTitle"))

    if description:
        layout.addWidget(make_label(description, "MutedText"))

    return card, layout


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.audio_engine = AudioEngine()
        self.audio_timer = QTimer(self)
        self.audio_timer.setInterval(250)
        self.audio_timer.timeout.connect(self.check_audio_stream)

        self.setWindowTitle("Noise Reduction Studio")
        self.resize(1180, 820)
        self.setMinimumSize(860, 640)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(20)

        root.addLayout(self.create_header())

        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_live_page(), "Live Studio")

        self.test_lab = TestLab(
            live_is_active=lambda: self.audio_engine.active,
            output_device=self.test_lab_output_device,
        )
        self.tabs.addTab(self.test_lab, "Test Lab")

        root.addWidget(self.tabs, 1)
        self.statusBar().showMessage("Select your audio devices and press Start.")

        self.recording_timer = QTimer(self)
        self.recording_timer.setInterval(100)
        self.recording_timer.timeout.connect(self.update_recording_controls)
        self.recording_timer.start()
        self.update_recording_controls()
        self.refresh_devices()

    def test_lab_output_device(self):
        selected = self.output_device.currentData()
        return selected[0] if selected is not None else None

    def create_header(self):
        layout = QHBoxLayout()
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)

        text_layout.addWidget(
            make_label("Noise Reduction Studio", "AppTitle")
        )
        text_layout.addWidget(
            make_label(
                "Real-time audio filtering and signal analysis",
                "Subtitle",
            )
        )

        layout.addLayout(text_layout)
        layout.addStretch()

        help_button = QPushButton("Help")
        help_button.clicked.connect(self.show_help)
        layout.addWidget(help_button)

        return layout

    def create_live_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(18)

        layout.addWidget(self.create_devices_card())
        layout.addWidget(self.create_monitoring_card())
        layout.addWidget(self.create_recording_card())

        workspace = QHBoxLayout()
        workspace.setSpacing(18)

        filters_card = self.create_filters_card()
        filters_card.setMinimumWidth(280)
        filters_card.setMaximumWidth(360)

        analysis_card = self.create_analysis_card()

        filters_card.setFixedHeight(460)
        analysis_card.setFixedHeight(460)

        workspace.addWidget(filters_card, 1)
        workspace.addWidget(analysis_card, 2)

        layout.addLayout(workspace)
        layout.addStretch()

        return page
    def refresh_devices(self):
        """Read devices and preserve the previous selection if possible."""
        previous_input = self.input_device.currentData()
        previous_output = self.output_device.currentData()

        self.refresh_button.setEnabled(False)
        self.input_device.blockSignals(True)
        self.output_device.blockSignals(True)
        self.start_button.setEnabled(False)

        self.input_device.clear()
        self.output_device.clear()

        try:
            devices = sd.query_devices()
            host_apis = sd.query_hostapis()

            wasapi_ids = [
                index
                for index, api in enumerate(host_apis)
                if "WASAPI" in api["name"].upper()
            ]

            if wasapi_ids:
                selected_api = wasapi_ids[0]
            else:
                selected_api = sd.default.hostapi

            api_name = host_apis[selected_api]["name"]

            default_input = host_apis[selected_api]["default_input_device"]
            default_output = host_apis[selected_api]["default_output_device"]

            for device_id, device in enumerate(devices):
                if device["hostapi"] != selected_api:
                    continue

                # Store a stable description alongside the current device ID.
                device_data = (
                    device_id,
                    device["name"],
                    device["hostapi"],
                )

                if device["max_input_channels"] >= 1:
                    self.input_device.addItem(
                        device["name"],
                        device_data,
                    )

                if device["max_output_channels"] >= 2:
                    self.output_device.addItem(
                        device["name"],
                        device_data,
                    )

            self.restore_device_selection(
                self.input_device,
                previous_input,
                default_input,
            )
            self.restore_device_selection(
                self.output_device,
                previous_output,
                default_output,
            )

            self.input_device.setEnabled(self.input_device.count() > 0)
            self.output_device.setEnabled(self.output_device.count() > 0)

            if self.input_device.count() == 0:
                self.input_device.addItem("No microphone available", None)

            if self.output_device.count() == 0:
                self.output_device.addItem("No stereo output available", None)

            self.audio_api_name = api_name
            self.update_device_message()

        except (sd.PortAudioError, ValueError, IndexError) as error:
            self.input_device.clear()
            self.output_device.clear()

            self.input_device.addItem("Devices unavailable", None)
            self.output_device.addItem("Devices unavailable", None)

            self.input_device.setEnabled(False)
            self.output_device.setEnabled(False)

            self.device_message.setText(
                f"Could not read audio devices: {error}"
            )

        finally:
            self.input_device.blockSignals(False)
            self.output_device.blockSignals(False)
            self.refresh_button.setEnabled(True)

    def restore_device_selection(self, combo, previous, default_id):
        """Prefer the previous device, then the API's default device."""
        if previous is not None:
            # First try to match both the old ID and device description.
            for index in range(combo.count()):
                if combo.itemData(index) == previous:
                    combo.setCurrentIndex(index)
                    return

            # Device IDs can change, so also compare name and host API.
            for index in range(combo.count()):
                data = combo.itemData(index)

                if data[1:] == previous[1:]:
                    combo.setCurrentIndex(index)
                    return

        for index in range(combo.count()):
            if combo.itemData(index)[0] == default_id:
                combo.setCurrentIndex(index)
                return

        if combo.count() > 0:
            combo.setCurrentIndex(0)

    def update_device_message(self, _index=None):
        input_data = self.input_device.currentData()
        output_data = self.output_device.currentData()
        ready = input_data is not None and output_data is not None

        self.start_button.setEnabled(ready and not self.audio_timer.isActive())

        if not ready:
            self.device_message.setText(
                "Connect a microphone and stereo output, then refresh."
            )
            return

        api_name = getattr(self, "audio_api_name", "Audio")
        self.device_message.setText(f"{api_name} · Ready to start.")

    def start_audio(self):
        input_data = self.input_device.currentData()
        output_data = self.output_device.currentData()

        if input_data is None or output_data is None:
            self.update_device_message()
            return

        self.test_lab.stop_playback()

        try:
            self.audio_engine.start(input_data[0], output_data[0])
        except (sd.PortAudioError, ValueError, RuntimeError) as error:
            self.statusBar().showMessage("Audio could not start.")
            QMessageBox.warning(self, "Could not start audio", str(error))
            return
        self.audio_plots.reset_live()
        self.audio_timer.start()
        self.set_audio_running(True)
        self.device_message.setText("Running · Live microphone audio")
        self.statusBar().showMessage("Audio running at 48 kHz.")

    def stop_audio(self, message="Audio stopped."):
        if self.auto_timer.isActive():
            self.auto_timer.stop()
            self.auto_button.setEnabled(True)
            self.auto_result.setText("Calibration cancelled. Audio stopped.")

        self.audio_timer.stop()

        try:
            self.audio_engine.stop()
        except sd.PortAudioError as error:
            message = f"Could not close audio cleanly: {error}"
        finally:
            self.set_audio_running(False)
            self.update_device_message()
            self.statusBar().showMessage(message)

    def set_audio_running(self, running):
        self.input_device.setEnabled(
            not running and self.input_device.currentData() is not None
        )
        self.output_device.setEnabled(
            not running and self.output_device.currentData() is not None
        )
        self.refresh_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

        if running:
            self.start_button.setEnabled(False)

    def check_audio_stream(self):
        try:
            active = self.audio_engine.active
        except sd.PortAudioError as error:
            self.stop_audio(f"Audio device error: {error}")
            return

        if not active:
            self.stop_audio(
                "Audio stopped unexpectedly. Check your devices and try again."
            )
            return

        peak, processing_ms, warnings = self.audio_engine.metrics
        self.audio_metrics_label.setText(
            f"Input peak: {peak * 100:.1f}%  |  "
            f"Processing: {processing_ms:.2f} ms  |  "
            f"Audio warnings: {warnings}"
        )

    def closeEvent(self, event):
        self.audio_engine.recording.stop()
        self.update_recording_controls()
        if self.recording_unsaved and self.audio_engine.recording.status[1]:
            choice = QMessageBox.question(
                self, "Unsaved recording",
                "The recording has not been exported. Close and discard it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.test_lab.stop_playback()
        self.stop_audio()
        super().closeEvent(event)
    def create_devices_card(self):
        card, layout = make_card(
            "Audio Devices",
            "Choose the microphone and playback device for live processing.",
        )

        devices_row = QHBoxLayout()
        devices_row.setSpacing(16)

        input_column = QVBoxLayout()
        input_column.addWidget(make_label("Input Device"))

        self.input_device = QComboBox()
        input_column.addWidget(self.input_device)

        output_column = QVBoxLayout()
        output_column.addWidget(make_label("Output Device"))

        self.output_device = QComboBox()
        output_column.addWidget(self.output_device)

        devices_row.addLayout(input_column, 1)
        devices_row.addLayout(output_column, 1)
        layout.addLayout(devices_row)

        self.device_message = make_label(
            "Reading available audio devices...",
            "MutedText",
        )
        layout.addWidget(self.device_message)

        buttons = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh Devices")
        self.refresh_button.clicked.connect(self.refresh_devices)

        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setEnabled(False)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(self.start_audio)
        self.stop_button.clicked.connect(lambda: self.stop_audio())

        buttons.addWidget(self.refresh_button)
        buttons.addStretch()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)

        layout.addLayout(buttons)
        self.audio_metrics_label = make_label(
            "Input peak: —  |  Processing: —  |  Audio warnings: —",
            "MutedText",
        )
        layout.addWidget(self.audio_metrics_label)

        self.input_device.currentIndexChanged.connect(
            self.update_device_message
        )
        self.output_device.currentIndexChanged.connect(
            self.update_device_message
        )

        return card

    def create_monitoring_card(self):
        card, layout = make_card("Monitoring")
        controls = QHBoxLayout()
        self.listen_checkbox = QCheckBox("Listen")
        self.listen_checkbox.setChecked(True)
        self.monitor_source = QComboBox()
        self.monitor_source.addItem("Original", False)
        self.monitor_source.addItem("Filtered", True)
        self.monitor_source.setAccessibleName("Playback source")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.setAccessibleName("Output volume")
        self.volume_value = make_label("50%")
        self.volume_value.setMinimumWidth(44)

        controls.addWidget(self.listen_checkbox)
        controls.addWidget(make_label("Playback"))
        controls.addWidget(self.monitor_source)
        controls.addWidget(make_label("Output Volume"))
        controls.addWidget(self.volume_slider, 1)
        controls.addWidget(self.volume_value)
        layout.addLayout(controls)
        self.listen_checkbox.toggled.connect(self.update_monitoring)
        self.monitor_source.currentIndexChanged.connect(self.update_monitoring)
        self.volume_slider.valueChanged.connect(self.update_monitoring)
        self.update_monitoring()
        return card

    def update_monitoring(self, _value=None):
        volume = self.volume_slider.value()
        self.volume_value.setText(f"{volume}%")
        self.audio_engine.set_monitoring(
            self.listen_checkbox.isChecked(),
            bool(self.monitor_source.currentData()),
            volume / 100,
        )

    def create_recording_card(self):
        card, layout = make_card("Recording")
        self.recording_unsaved = False
        controls = QHBoxLayout()
        self.record_button = QPushButton("Record")
        self.record_button.setObjectName("PrimaryButton")
        self.record_button.clicked.connect(self.start_recording)
        self.stop_record_button = QPushButton("Stop Recording")
        self.stop_record_button.clicked.connect(self.stop_recording)
        self.export_button = QPushButton("Export WAV")
        self.export_button.clicked.connect(self.export_recording)
        self.recording_duration = make_label("00:00 / 01:00")
        for widget in (self.record_button, self.stop_record_button,
                       self.export_button, self.recording_duration):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)
        self.recording_message = make_label(
            "Records original and filtered audio together, even with Listen off.",
            "MutedText",
        )
        layout.addWidget(self.recording_message)
        return card

    def update_recording_controls(self):
        recording, frames, warnings = self.audio_engine.recording.status
        try:
            active = self.audio_engine.active
        except sd.PortAudioError:
            active = False
        if recording and not active:
            self.audio_engine.recording.stop()
            recording = False
        seconds = frames / self.audio_engine.sample_rate
        self.recording_duration.setText(
            f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d} / 01:00"
        )
        self.record_button.setEnabled(active and not recording)
        self.stop_record_button.setEnabled(recording)
        self.export_button.setEnabled(frames > 0 and not recording)
        if recording:
            self.recording_message.setText(
                "Recording original + filtered. Listen and output volume do not affect the files."
            )
        elif self.recording_unsaved and frames:
            reason = "60-second limit reached. " if seconds >= 60 else ""
            warning = f" Audio warning callbacks: {warnings}." if warnings else ""
            self.recording_message.setText(
                reason + "Recording ready. Export before starting a new recording or closing." + warning
            )

    def start_recording(self):
        if self.recording_unsaved and self.audio_engine.recording.status[1]:
            choice = QMessageBox.question(
                self, "Replace recording",
                "The previous recording has not been exported. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        try:
            self.audio_engine.start_recording()
        except (RuntimeError, MemoryError) as error:
            QMessageBox.warning(self, "Could not record", str(error))
            return
        self.recording_unsaved = True
        self.update_recording_controls()

    def stop_recording(self):
        self.audio_engine.recording.stop()
        self.update_recording_controls()

    def export_recording(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose an export folder")
        if not folder:
            return
        try:
            destination, gain = self.audio_engine.recording.export(folder)
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Could not export recording", str(error))
            return
        self.recording_unsaved = False
        self.recording_message.setText(f"Saved original.wav and filtered.wav in {destination}")
        self.statusBar().showMessage("Recording exported successfully.")
        QMessageBox.information(
            self, "Recording exported",
            f"Saved in:\n{destination}\n\noriginal.wav\nfiltered.wav\ndetails.txt\n\n"
            f"Shared export gain: {gain:.3f}",
        )
        self.update_recording_controls()

    def create_filters_card(self):
        card, layout = make_card(
            "Noise Reduction",
            "Choose which frequencies to attenuate.",
        )

        self.filter_tabs = QTabWidget()

        presets_page = QWidget()
        presets_layout = QVBoxLayout(presets_page)
        self.preset_combo = QComboBox()
        for name, kind, settings, description in (
             ("Low Voice Notch Demo", "notch", {"frequency": 300, "quality": 0.7},
             "Wide notch at 300 Hz (Q 0.7)"),
            ("Muffled Voice Demo", "lowpass", {"cutoff": 500},
             "Low-pass at 500 Hz"),
            ("Thin Voice Demo", "highpass", {"cutoff": 1500},
             "High-pass at 1,500 Hz"),
            ("Mid Voice Notch Demo", "notch", {"frequency": 1000, "quality": 0.7},
             "Wide notch at 1,000 Hz (Q 0.7)"),
        ):
            self.preset_combo.addItem(name, (kind, settings, description))

        self.preset_description = make_label("", "MutedText")
        self.preset_error = make_label("")
        self.preset_error.setStyleSheet("color: #fca5a5;")
        apply_preset = QPushButton("Apply Preset")
        apply_preset.setObjectName("PrimaryButton")
        apply_preset.clicked.connect(self.apply_preset)
        customize = QPushButton("Customize")
        customize.clicked.connect(self.customize_preset)
        for widget in (
            self.preset_combo, self.preset_description, self.preset_error,
            apply_preset, customize,
        ):
            presets_layout.addWidget(widget)
        presets_layout.addStretch()

        custom_page = QWidget()
        custom_layout = QVBoxLayout(custom_page)
        custom_layout.setContentsMargins(0, 14, 0, 0)

        form = QFormLayout()
        self.filter_type = QComboBox()

        for label, value in (
            ("High-pass", "highpass"),
            ("Low-pass", "lowpass"),
            ("Band-stop", "bandstop"),
            ("Notch", "notch"),
        ):
            self.filter_type.addItem(label, value)

        self.filter_type.setCurrentIndex(1)
        form.addRow("Filter Type", self.filter_type)

        self.filter_fields = {}
        maximum_hz = self.audio_engine.sample_rate / 2 - 0.1

        for key, label, default in (
            ("cutoff", "Cutoff Frequency", 1000.0),
            ("low", "Lower Frequency", 800.0),
            ("high", "Upper Frequency", 1200.0),
            ("frequency", "Notch Frequency", 1000.0),
            ("quality", "Quality Factor", 30.0),
        ):
            field = QDoubleSpinBox()
            field.setDecimals(1)
            field.setKeyboardTracking(False)

            if key == "quality":
                field.setRange(0.1, 200.0)
                field.setSingleStep(1.0)
            else:
                field.setRange(1.0, maximum_hz)
                field.setSingleStep(10.0)
                field.setSuffix(" Hz")

            field.setValue(default)
            self.filter_fields[key] = field
            form.addRow(label, field)

        self.filter_form = form
        custom_layout.addLayout(form)

        self.filter_error = make_label("")
        self.filter_error.setStyleSheet("color: #fca5a5;")
        self.filter_error.hide()
        custom_layout.addWidget(self.filter_error)

        apply_button = QPushButton("Apply Changes")
        apply_button.setObjectName("PrimaryButton")
        apply_button.clicked.connect(self.apply_custom_filter)
        custom_layout.addWidget(apply_button)
        custom_layout.addStretch()

        self.filter_tabs.addTab(presets_page, "Presets")
        self.filter_tabs.addTab(custom_page, "Custom")
        self.filter_tabs.addTab(self.create_auto_page(), "Auto")
        self.filter_tabs.setCurrentWidget(custom_page)
        layout.addWidget(self.filter_tabs, 1)

        self.applied_filter_label = make_label(
            "Applied: Low-pass at 1,000 Hz",
            "MutedText",
        )
        layout.addWidget(self.applied_filter_label)

        self.applied_settings = ("lowpass", {"cutoff": 1000})
        self.pending_filter_label = make_label("", "MutedText")
        layout.addWidget(self.pending_filter_label)
        self.preset_combo.currentIndexChanged.connect(self.update_filter_status)
        self.filter_tabs.currentChanged.connect(self.update_filter_status)
        for field in self.filter_fields.values():
            field.valueChanged.connect(self.update_filter_status)

        self.filter_type.currentIndexChanged.connect(self.update_filter_fields)
        self.update_filter_fields()

        return card

    FILTER_FIELDS = {
        "highpass": ("cutoff",),
        "lowpass": ("cutoff",),
        "bandstop": ("low", "high"),
        "notch": ("frequency", "quality"),
    }

    def update_filter_fields(self, _index=None):
        visible_fields = self.FILTER_FIELDS[self.filter_type.currentData()]
        for key, field in self.filter_fields.items():
            visible = key in visible_fields
            field.setVisible(visible)
            self.filter_form.labelForField(field).setVisible(visible)
        self.update_filter_status()

    def update_filter_status(self, _value=None):
        kind, settings, description = self.preset_combo.currentData()
        self.preset_description.setText(description)
        self.preset_error.hide()
        self.filter_error.hide()
        if self.filter_tabs.currentIndex() == 1:
            kind = self.filter_type.currentData()
            settings = {
                key: self.filter_fields[key].value()
                for key in self.FILTER_FIELDS[kind]
            }
        if self.filter_tabs.currentIndex() == 2:
            self.pending_filter_label.clear()
            return

        self.pending_filter_label.setText(
            "Unapplied changes" if (kind, settings) != self.applied_settings else ""
        )

    def customize_preset(self):
        kind, settings, _description = self.preset_combo.currentData()
        self.filter_type.setCurrentIndex(self.filter_type.findData(kind))
        for key, value in settings.items():
            self.filter_fields[key].setValue(value)
        self.filter_tabs.setCurrentIndex(1)

    def apply_preset(self):
        kind, settings, description = self.preset_combo.currentData()
        self.apply_filter(kind, settings, description, self.preset_error)

    def apply_custom_filter(self):
        filter_type = self.filter_type.currentData()
        filter_name = self.filter_type.currentText()

        if filter_type in ("highpass", "lowpass"):
            cutoff = self.filter_fields["cutoff"].value()
            settings = {"cutoff": cutoff}
            description = f"{filter_name} at {cutoff:,.1f} Hz"

        elif filter_type == "bandstop":
            low = self.filter_fields["low"].value()
            high = self.filter_fields["high"].value()

            if low >= high:
                self.filter_error.setText(
                    "Upper frequency must be greater than lower frequency."
                )
                self.filter_error.show()
                return

            settings = {"low": low, "high": high}
            description = f"{filter_name} from {low:,.1f} to {high:,.1f} Hz"

        else:
            frequency = self.filter_fields["frequency"].value()
            quality = self.filter_fields["quality"].value()
            settings = {"frequency": frequency, "quality": quality}
            description = f"{filter_name} at {frequency:,.1f} Hz (Q {quality:g})"

        self.apply_filter(filter_type, settings, description, self.filter_error)

    def apply_filter(self, filter_type, settings, description, error_label):
        try:
            self.audio_engine.set_filter(filter_type, **settings)
        except ValueError as error:
            error_label.setText(str(error))
            error_label.show()
            return False

        self.applied_settings = (filter_type, settings)
        self.applied_filter_label.setText(f"Applied: {description}")
        self.audio_plots.update_response()
        self.update_filter_status()
        return True

    def create_auto_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(make_label(
            "Start the microphone and stay quiet during calibration.",
            "MutedText",
        ))

        self.auto_button = QPushButton("Calibrate")
        self.auto_button.setObjectName("PrimaryButton")
        self.auto_button.clicked.connect(self.start_auto_calibration)
        layout.addWidget(self.auto_button)

        self.auto_result = make_label("Ready to calibrate.", "MutedText")
        layout.addWidget(self.auto_result)
        layout.addStretch()

        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(self.finish_auto_calibration)
        return page

    def start_auto_calibration(self):
        if not self.audio_engine.active:
            self.auto_result.setText("Press Start before calibrating.")
            return

        self.auto_button.setEnabled(False)
        self.auto_result.setText("Listening to the background. Please stay quiet.")
        self.auto_timer.start(2000)

    def finish_auto_calibration(self):
        self.auto_button.setEnabled(True)
        if not self.audio_engine.active:
            self.auto_result.setText("Calibration cancelled. Audio stopped.")
            return

        samples = self.audio_plots.history[0]
        sample_rate = self.audio_engine.sample_rate
        if len(samples) < sample_rate:
            self.auto_result.setText("Not enough audio. Try calibrating again.")
            return

        frequency = detect_steady_tone(samples, sample_rate)
        if frequency is None:
            if self.apply_filter("none", {}, "No filter", self.auto_result):
                self.auto_result.setText("No stable tone detected. No filter applied.")
            return

        if self.apply_filter(
            "notch",
            {"frequency": frequency, "quality": 20.0},
            f"Auto notch at {frequency:,.1f} Hz",
            self.auto_result,
        ):
            self.auto_result.setText(
                f"Detected steady tone at {frequency:,.1f} Hz. Notch applied."
            )

    def create_analysis_card(self):
        card, layout = make_card(
            "Audio Analysis",
            "Compare the original and filtered signals.",
        )
        self.audio_plots = AudioPlots(self.audio_engine)
        layout.addWidget(self.audio_plots, 1)
        return card


    def show_help(self):
        QMessageBox.information(
            self,
            "Noise Reduction Studio — Quick Guide",
            "LIVE STUDIO\n"
            "Select an input and stereo output, then press Start. Use headphones for live monitoring.\n"
            "Listen enables playback. Select Original or Filtered and adjust output volume.\n\n"
            "FILTERS\n"
            "Presets: prepared voice demonstrations; click Apply Preset.\n"
            "Custom: choose a filter, edit its parameters, then click Apply Changes.\n"
            "High-pass reduces lows; low-pass reduces highs; band-stop reduces a band; "
            "notch reduces a narrow region. Filtering can also change the voice.\n\n"
            "AUTO\n"
            "Start live audio, keep the background noise present and stay quiet. Click Calibrate. "
            "Auto detects one steady tone between 40 and 3000 Hz and applies a notch. "
            "Recalibrate if the tone changes. It does not remove every type of noise.\n\n"
            "RECORDING\n"
            "Record saves original and filtered signals together, even with Listen off. "
            "Stop Recording ends the take; Export WAV saves both tracks in a new folder. "
            "Maximum duration: 60 seconds. Export before closing.\n\n"
            "TEST LAB\n"
            "Open a 1–60 second WAV, choose the added noise and filter, then Run Test. "
            "Compare Clean, Noisy and Filtered. Noise and filter choices are independent. "
            "Auto calibrates on generated noise alone. Attenuation measures that noise, not voice quality. "
            "Stop live audio before test playback.\n\n"
            "PLOTS AND METRICS\n"
            "Blue: original; green: filtered. The spectrum uses the last second. "
            "Processing time is callback work, not total audio latency. "
            "Audio warnings may indicate missing or interrupted sound.\n\n"
            "TROUBLESHOOTING\n"
            "Check Windows microphone permissions, the selected device and its input level. "
            "Noise suppression may hide test tones. Bluetooth can add delay. "
            "For repeatable tests, use Test Lab. See README.md for full instructions.",
        )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    stylesheet_path = Path(__file__).resolve().with_name("styles.qss")
    app.setStyleSheet(stylesheet_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
