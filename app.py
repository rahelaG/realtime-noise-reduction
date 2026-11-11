import sounddevice as sd
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from audio_engine import AudioEngine
from PySide6.QtWidgets import (
    QApplication,
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

        # Enabled when controlled testing is implemented.
        self.tabs.addTab(QWidget(), "Test Lab")
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabToolTip(
            1,
            "Controlled audio testing will be added in a later step.",
        )

        root.addWidget(self.tabs, 1)
        root.addLayout(self.create_footer())
        self.statusBar().showMessage(
             self.statusBar().showMessage("Select your audio devices and press Start.")
        )

        self.refresh_devices()

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

        workspace = QHBoxLayout()
        workspace.setSpacing(18)

        filters_card = self.create_filters_card()
        filters_card.setMinimumWidth(280)
        filters_card.setMaximumWidth(360)

        workspace.addWidget(filters_card, 1)
        workspace.addWidget(self.create_analysis_card(), 2)

        layout.addLayout(workspace, 1)
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

        try:
            self.audio_engine.start(input_data[0], output_data[0])
        except (sd.PortAudioError, ValueError, RuntimeError) as error:
            self.statusBar().showMessage("Audio could not start.")
            QMessageBox.warning(self, "Could not start audio", str(error))
            return

        self.audio_timer.start()
        self.set_audio_running(True)
        self.device_message.setText("Running · Live microphone audio")
        self.statusBar().showMessage("Audio running at 48 kHz.")

    def stop_audio(self, message="Audio stopped."):
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

    def closeEvent(self, event):
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
        controls.setSpacing(16)

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
        layout.addWidget(make_label(
            "Choose Filtered to hear the filter applied in Noise Reduction.",
            "MutedText",
        ))

        self.listen_checkbox.toggled.connect(self.update_monitoring)
        self.monitor_source.currentIndexChanged.connect(self.update_monitoring)
        self.volume_slider.valueChanged.connect(self.update_monitoring)
        self.update_monitoring()
        return card

    def update_monitoring(self, _value=None):
        volume_percent = self.volume_slider.value()
        self.volume_value.setText(f"{volume_percent}%")
        self.audio_engine.set_monitoring(
            listen=self.listen_checkbox.isChecked(),
            use_filtered=bool(self.monitor_source.currentData()),
            volume=volume_percent / 100,
        )

    def create_filters_card(self):
        card, layout = make_card(
            "Noise Reduction",
            "Choose which frequencies to attenuate.",
        )

        self.filter_tabs = QTabWidget()

        presets_page = QWidget()
        presets_layout = QVBoxLayout(presets_page)
        presets_layout.addWidget(
            make_label("Presets will be available in the next step.", "MutedText")
        )
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
        self.filter_tabs.setCurrentWidget(custom_page)
        layout.addWidget(self.filter_tabs, 1)

        self.applied_filter_label = make_label(
            "Applied: Low-pass at 1,000 Hz",
            "MutedText",
        )
        layout.addWidget(self.applied_filter_label)

        self.filter_type.currentIndexChanged.connect(self.update_filter_fields)
        self.update_filter_fields()

        return card

    def update_filter_fields(self, _index=None):
        fields_by_filter = {
            "highpass": ("cutoff",),
            "lowpass": ("cutoff",),
            "bandstop": ("low", "high"),
            "notch": ("frequency", "quality"),
        }
        visible_fields = fields_by_filter[self.filter_type.currentData()]

        for key, field in self.filter_fields.items():
            visible = key in visible_fields
            field.setVisible(visible)
            self.filter_form.labelForField(field).setVisible(visible)

        self.filter_error.hide()

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

        try:
            self.audio_engine.set_filter(filter_type, **settings)
        except ValueError as error:
            self.filter_error.setText(str(error))
            self.filter_error.show()
            return

        self.filter_error.hide()
        self.applied_filter_label.setText(f"Applied: {description}")

    def create_analysis_card(self):
        card, layout = make_card(
            "Audio Analysis",
            "Compare the original and filtered signals.",
        )

        legend = QHBoxLayout()
        original = make_label("Original")
        original.setStyleSheet("color: #60a5fa;")

        filtered = make_label("Filtered")
        filtered.setStyleSheet("color: #2dd4bf;")

        legend.addWidget(original)
        legend.addWidget(filtered)
        legend.addStretch()
        layout.addLayout(legend)

        placeholder = make_label(
            "Live plots will appear here once audio processing "
            "and visualization are connected.",
            "MutedText",
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setMinimumHeight(230)

        layout.addWidget(placeholder, 1)
        layout.addWidget(
            make_label(
                "Planned views: Waveform · Frequency Spectrum · "
                "Filter Response",
                "MutedText",
            )
        )

        return card

    def create_footer(self):
        layout = QHBoxLayout()

        layout.addWidget(make_label("Not connected", "StatusBadge"))
        layout.addStretch()
        layout.addWidget(
            make_label("Development stage: interface layout", "MutedText")
        )

        return layout

    def show_help(self):
        QMessageBox.information(
            self,
            "About Noise Reduction Studio",
            "This application reduces audio components in selected "
            "frequency ranges.\n\n"
            "Live Studio captures and filters microphone audio.\n"
            "Test Lab will provide repeatable experiments with known noise.\n\n"
            "Select your microphone and headphones, then press Start. "
            "Choose Filtered in Monitoring to hear the applied filter.",
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
