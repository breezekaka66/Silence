"""
Main Settings Window — Silence's primary configuration UI.

Layout:
  ┌────────────────────────────────────┐
  │  🎙 Silence v0.1.0                 │
  ├────────────────────────────────────┤
  │  Status: ● Active                  │
  │  Latency: 18.3 ms                  │
  ├────────────────────────────────────┤
  │  Input:  [device dropdown    ▼]    │
  │  Output: [device dropdown    ▼]    │
  ├────────────────────────────────────┤
  │  VU Meter  [████████░░░░░] −18 dB  │
  ├────────────────────────────────────┤
  │  Noise Suppression                 │
  │  [━━━━━━━━━━━━━━━━━━━━] 80         │
  ├────────────────────────────────────┤
  │  [Enable]    [☐ Start on Boot]     │
  └────────────────────────────────────┘
"""
import logging

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QSlider, QPushButton, QCheckBox,
    QFrame, QSizePolicy, QSpacerItem,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor

from silence.core.audio_pipeline import AudioPipeline
from silence.utils.config import Config
from silence.utils.vbcable_check import check_vbcable
from silence.gui.vu_widget import VUMeterWidget

logger = logging.getLogger(__name__)

# Dark theme palette
STYLE_SHEET = """
QMainWindow, QWidget#central {
    background-color: #111827;
    color: #F9FAFB;
}
QLabel {
    color: #E5E7EB;
    font-family: "Segoe UI", sans-serif;
}
QLabel#title {
    font-size: 18px;
    font-weight: bold;
    color: #F9FAFB;
}
QLabel#subtitle {
    font-size: 11px;
    color: #6B7280;
}
QLabel#section {
    font-size: 11px;
    font-weight: bold;
    color: #9CA3AF;
    text-transform: uppercase;
    letter-spacing: 1px;
}
QLabel#status_active {
    color: #10B981;
    font-weight: bold;
}
QLabel#status_inactive {
    color: #6B7280;
    font-weight: bold;
}
QLabel#latency {
    color: #60A5FA;
    font-family: "Consolas", monospace;
    font-size: 12px;
}
QComboBox {
    background-color: #1F2937;
    border: 1px solid #374151;
    border-radius: 6px;
    color: #F9FAFB;
    padding: 6px 10px;
    font-size: 12px;
    min-height: 28px;
}
QComboBox:hover {
    border-color: #6366F1;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #1F2937;
    border: 1px solid #374151;
    color: #F9FAFB;
    selection-background-color: #6366F1;
}
QSlider::groove:horizontal {
    height: 6px;
    background-color: #374151;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #6366F1;
    border: 2px solid #818CF8;
    width: 18px;
    height: 18px;
    border-radius: 9px;
    margin: -6px 0;
}
QSlider::handle:horizontal:hover {
    background-color: #818CF8;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #10B981, stop:0.6 #F59E0B, stop:1 #EF4444);
    border-radius: 3px;
}
QPushButton#btn_primary {
    background-color: #6366F1;
    color: #F9FAFB;
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: bold;
    min-width: 120px;
}
QPushButton#btn_primary:hover {
    background-color: #818CF8;
}
QPushButton#btn_primary:pressed {
    background-color: #4F46E5;
}
QPushButton#btn_danger {
    background-color: #EF4444;
    color: #F9FAFB;
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: bold;
    min-width: 120px;
}
QPushButton#btn_danger:hover {
    background-color: #F87171;
}
QCheckBox {
    color: #D1D5DB;
    spacing: 8px;
    font-size: 12px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #374151;
    border-radius: 4px;
    background-color: #1F2937;
}
QCheckBox::indicator:checked {
    background-color: #6366F1;
    border-color: #6366F1;
}
QFrame#separator {
    background-color: #1F2937;
    border-top: 1px solid #374151;
}
"""


def _separator() -> QFrame:
    line = QFrame()
    line.setObjectName("separator")
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFixedHeight(1)
    return line


class MainWindow(QMainWindow):
    """Silence settings and status window."""

    def __init__(self, pipeline: AudioPipeline, config: Config, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._config = config

        self.setWindowTitle("Silence — Settings")
        self.setFixedWidth(420)
        self.setStyleSheet(STYLE_SHEET)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Build sections
        layout.addWidget(self._build_header())
        layout.addWidget(_separator())
        layout.addWidget(self._build_status_section())
        layout.addWidget(_separator())
        layout.addWidget(self._build_device_section())
        layout.addWidget(_separator())
        layout.addWidget(self._build_vu_section())
        layout.addWidget(_separator())
        layout.addWidget(self._build_strength_section())
        layout.addWidget(_separator())
        layout.addWidget(self._build_controls_section())

        self.adjustSize()

        # Wire pipeline VU callback
        self._pipeline.on_vu_update = self._on_vu_update
        self._pipeline.on_latency_update = self._on_latency_update

        # Status refresh timer
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(500)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start()

    # -------------------------------------------------------------------------
    # Section builders
    # -------------------------------------------------------------------------

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setContentsMargins(20, 16, 20, 12)
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("🔇 Silence")
        title.setObjectName("title")
        layout.addWidget(title)

        layout.addStretch()

        version = QLabel("v0.1.0")
        version.setObjectName("subtitle")
        layout.addWidget(version)

        return w

    def _build_status_section(self) -> QWidget:
        w = QWidget()
        w.setContentsMargins(20, 10, 20, 10)
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        # Status dot + text
        self._status_label = QLabel("● Inactive")
        self._status_label.setObjectName("status_inactive")
        layout.addWidget(self._status_label)

        layout.addStretch()

        # Latency
        latency_label = QLabel("Latency:")
        latency_label.setObjectName("subtitle")
        layout.addWidget(latency_label)

        self._latency_label = QLabel("— ms")
        self._latency_label.setObjectName("latency")
        layout.addWidget(self._latency_label)

        return w

    def _build_device_section(self) -> QWidget:
        w = QWidget()
        w.setContentsMargins(20, 12, 20, 12)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        section_lbl = QLabel("AUDIO DEVICES")
        section_lbl.setObjectName("section")
        layout.addWidget(section_lbl)

        # Input device
        input_row = QHBoxLayout()
        input_lbl = QLabel("Input:")
        input_lbl.setFixedWidth(52)
        input_row.addWidget(input_lbl)
        self._input_combo = QComboBox()
        self._input_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        input_row.addWidget(self._input_combo)
        layout.addLayout(input_row)

        # Output device
        output_row = QHBoxLayout()
        output_lbl = QLabel("Output:")
        output_lbl.setFixedWidth(52)
        output_row.addWidget(output_lbl)
        self._output_combo = QComboBox()
        self._output_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        output_row.addWidget(self._output_combo)
        layout.addLayout(output_row)

        self._populate_devices()

        # Connect change signals
        self._input_combo.currentIndexChanged.connect(self._on_input_device_changed)
        self._output_combo.currentIndexChanged.connect(self._on_output_device_changed)

        return w

    def _build_vu_section(self) -> QWidget:
        w = QWidget()
        w.setContentsMargins(20, 12, 20, 10)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        section_lbl = QLabel("INPUT LEVEL")
        section_lbl.setObjectName("section")
        header.addWidget(section_lbl)
        header.addStretch()
        layout.addLayout(header)

        self._vu_widget = VUMeterWidget()
        layout.addWidget(self._vu_widget)

        return w

    def _build_strength_section(self) -> QWidget:
        w = QWidget()
        w.setContentsMargins(20, 12, 20, 12)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        section_lbl = QLabel("NOISE SUPPRESSION STRENGTH")
        section_lbl.setObjectName("section")
        header.addWidget(section_lbl)
        header.addStretch()
        self._strength_value_label = QLabel(str(self._config.denoise_strength))
        self._strength_value_label.setObjectName("latency")
        header.addWidget(self._strength_value_label)
        layout.addLayout(header)

        self._strength_slider = QSlider(Qt.Orientation.Horizontal)
        self._strength_slider.setRange(0, 100)
        self._strength_slider.setValue(self._config.denoise_strength)
        self._strength_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self._strength_slider.valueChanged.connect(self._on_strength_changed)
        layout.addWidget(self._strength_slider)

        # Labels: Low ← → High
        hint_row = QHBoxLayout()
        low_lbl = QLabel("Low (preserve voice)")
        low_lbl.setObjectName("subtitle")
        hint_row.addWidget(low_lbl)
        hint_row.addStretch()
        high_lbl = QLabel("High (max noise removal)")
        high_lbl.setObjectName("subtitle")
        hint_row.addWidget(high_lbl)
        layout.addLayout(hint_row)

        return w

    def _build_controls_section(self) -> QWidget:
        w = QWidget()
        w.setContentsMargins(20, 12, 20, 16)
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Toggle button
        self._toggle_btn = QPushButton()
        self._toggle_btn.setObjectName("btn_primary")
        self._toggle_btn.clicked.connect(self._on_toggle)
        self._update_toggle_button()
        layout.addWidget(self._toggle_btn)

        # Checkboxes row
        checks = QHBoxLayout()

        self._boot_check = QCheckBox("Start on boot")
        self._boot_check.setChecked(self._config.start_on_boot)
        self._boot_check.toggled.connect(self._on_boot_toggled)
        checks.addWidget(self._boot_check)

        checks.addStretch()

        vbcable_ok = check_vbcable()
        vb_lbl = QLabel("VB-Cable: " + ("✅ Installed" if vbcable_ok else "❌ Not found"))
        vb_lbl.setObjectName("subtitle")
        checks.addWidget(vb_lbl)

        layout.addLayout(checks)
        return w

    # -------------------------------------------------------------------------
    # Device population
    # -------------------------------------------------------------------------

    def _populate_devices(self):
        """Fill device combo boxes from sounddevice."""
        devices = self._pipeline.get_devices()

        self._input_combo.blockSignals(True)
        self._output_combo.blockSignals(True)

        self._input_combo.clear()
        self._output_combo.clear()

        self._input_device_indices = []
        self._output_device_indices = []

        for dev in devices["inputs"]:
            self._input_combo.addItem(dev["name"])
            self._input_device_indices.append(dev["index"])

        for dev in devices["outputs"]:
            self._output_combo.addItem(dev["name"])
            self._output_device_indices.append(dev["index"])

        # Restore saved selections
        saved_in = self._config.input_device_name
        saved_out = self._config.output_device_name

        for i in range(self._input_combo.count()):
            if self._config.input_device_index == self._input_device_indices[i]:
                self._input_combo.setCurrentIndex(i)
                break

        for i in range(self._output_combo.count()):
            if saved_out in self._output_combo.itemText(i):
                self._output_combo.setCurrentIndex(i)
                break

        self._input_combo.blockSignals(False)
        self._output_combo.blockSignals(False)

    # -------------------------------------------------------------------------
    # Slots
    # -------------------------------------------------------------------------

    def _on_input_device_changed(self, index: int):
        if index < 0 or index >= len(self._input_device_indices):
            return
        dev_index = self._input_device_indices[index]
        dev_name = self._input_combo.currentText()
        self._config.input_device_index = dev_index
        self._config.input_device_name = dev_name
        self._config.save()

    def _on_output_device_changed(self, index: int):
        if index < 0 or index >= len(self._output_device_indices):
            return
        dev_index = self._output_device_indices[index]
        dev_name = self._output_combo.currentText()
        self._config.output_device_index = dev_index
        self._config.output_device_name = dev_name
        self._config.save()

    def _on_strength_changed(self, value: int):
        self._strength_value_label.setText(str(value))
        self._config.denoise_strength = value
        self._config.save()

    def _on_toggle(self):
        if self._pipeline.is_running:
            self._pipeline.stop()
            self._config.enabled = False
        else:
            self._pipeline.start()
            self._config.enabled = True
        self._config.save()
        self._update_toggle_button()

    def _on_boot_toggled(self, checked: bool):
        self._config.start_on_boot = checked
        self._config.save()

    def _on_vu_update(self, rms_db: float, peak_db: float):
        """Called from audio thread — just store values, widget polls them."""
        if hasattr(self, "_vu_widget"):
            self._vu_widget.update_level(rms_db, peak_db)

    def _on_latency_update(self, latency_ms: float):
        """Called from inference thread — update label via Qt-safe method."""
        # Use invokeMethod or just let the timer pick it up
        self._last_latency_ms = latency_ms

    def _refresh_status(self):
        """Periodic UI refresh from Qt main thread."""
        active = self._pipeline.is_running

        if active:
            self._status_label.setText("● Active")
            self._status_label.setObjectName("status_active")
        else:
            self._status_label.setText("● Inactive")
            self._status_label.setObjectName("status_inactive")

        # Latency
        if active and hasattr(self, "_last_latency_ms"):
            self._latency_label.setText(f"{self._last_latency_ms:.1f} ms")
        else:
            self._latency_label.setText("— ms")

        # Re-apply stylesheet for dynamic objectName changes
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

        self._update_toggle_button()

    def _update_toggle_button(self):
        if self._pipeline.is_running:
            self._toggle_btn.setText("⏸  Disable Noise Suppression")
            self._toggle_btn.setObjectName("btn_danger")
        else:
            self._toggle_btn.setText("▶  Enable Noise Suppression")
            self._toggle_btn.setObjectName("btn_primary")
        self._toggle_btn.style().unpolish(self._toggle_btn)
        self._toggle_btn.style().polish(self._toggle_btn)

    def closeEvent(self, event):
        """Don't quit the app when settings window closes."""
        # Remove callbacks to avoid dead references
        self._pipeline.on_vu_update = None
        self._pipeline.on_latency_update = None
        self._status_timer.stop()
        event.accept()
