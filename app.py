import sounddevice as sd
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
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
            "Select your audio devices. Live audio is not connected yet."
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

        if input_data is None or output_data is None:
            self.device_message.setText(
                "Connect a microphone and a stereo output device, "
                "then refresh the list."
            )
            return

        api_name = getattr(self, "audio_api_name", "Audio")

        self.device_message.setText(
            f"{api_name} · Devices selected. "
            "Live audio will be connected in the next step."
        )

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

    def create_filters_card(self):
        card, layout = make_card(
            "Noise Reduction",
            "Use a preset or configure a filter manually.",
        )

        self.filter_tabs = QTabWidget()

        presets_page = QWidget()
        presets_layout = QVBoxLayout(presets_page)
        presets_layout.setContentsMargins(0, 14, 0, 0)
        presets_layout.addWidget(
            make_label(
                "Preset selection will be connected after the audio engine.",
                "MutedText",
            )
        )
        presets_layout.addStretch()

        custom_page = QWidget()
        custom_layout = QVBoxLayout(custom_page)
        custom_layout.setContentsMargins(0, 14, 0, 0)
        custom_layout.addWidget(
            make_label(
                "Custom settings will support high-pass, low-pass, "
                "band-stop, and notch filters.",
                "MutedText",
            )
        )
        custom_layout.addStretch()

        self.filter_tabs.addTab(presets_page, "Presets")
        self.filter_tabs.addTab(custom_page, "Custom")

        layout.addWidget(self.filter_tabs, 1)

        apply_button = QPushButton("Apply Changes")
        apply_button.setObjectName("PrimaryButton")
        apply_button.setEnabled(False)

        layout.addWidget(apply_button)
        layout.addWidget(
            make_label(
                "Filters attenuate selected frequencies. "
                "Voice components in those ranges may also be affected.",
                "MutedText",
            )
        )

        return card

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
            "Live Studio will capture and filter microphone audio.\n"
            "Test Lab will provide repeatable experiments with known noise.\n\n"
            "This version contains the interface layout only. "
            "Audio controls are intentionally disabled.",
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