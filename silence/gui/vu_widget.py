"""
VU Meter Widget — Animated real-time audio level display.

Displays:
  - Horizontal bar: green → yellow → red (RMS level)
  - Peak hold needle (white line)
  - dBFS numerical readout

Receives updates via Qt signals from the audio thread.
Uses QTimer to poll from the main thread (thread-safe).
"""
import logging

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QLinearGradient, QColor, QPen, QFont

from silence.core.vu_meter import VUMeter, VU_FLOOR_DB, VU_RED_THRESHOLD, VU_YELLOW_THRESHOLD

logger = logging.getLogger(__name__)

# Colors
COLOR_GREEN = QColor("#10B981")
COLOR_YELLOW = QColor("#F59E0B")
COLOR_RED = QColor("#EF4444")
COLOR_BACKGROUND = QColor("#1F2937")
COLOR_BORDER = QColor("#374151")
COLOR_PEAK = QColor("#F9FAFB")
COLOR_TEXT = QColor("#E5E7EB")


class VUMeterWidget(QWidget):
    """
    A horizontal VU meter bar widget with peak hold and dBFS label.

    Thread safety: rms_db and peak_db are set atomically from the audio
    callback thread; Qt renders them on the GUI thread via a QTimer.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rms_db: float = VU_FLOOR_DB
        self._peak_db: float = VU_FLOOR_DB
        self._smooth_rms: float = VU_FLOOR_DB  # Smoothed for visual damping

        self.setMinimumSize(200, 28)
        self.setMaximumHeight(36)

        # Refresh at 30 fps
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    # -------------------------------------------------------------------------
    # Public API — called from audio thread (atomic float assignment is safe)
    # -------------------------------------------------------------------------

    def update_level(self, rms_db: float, peak_db: float):
        """Receive new audio level data. Safe to call from any thread."""
        self._rms_db = rms_db
        self._peak_db = peak_db

    # -------------------------------------------------------------------------
    # Qt painting
    # -------------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        bar_right = w - 52  # Reserve space for dBFS label
        bar_h = h - 4
        bar_y = 2

        # Smooth the RMS for less jittery visual
        alpha = 0.35
        self._smooth_rms = alpha * self._rms_db + (1 - alpha) * self._smooth_rms

        # Convert dBFS → fractions
        rms_frac = VUMeter.db_to_fraction(self._smooth_rms)
        peak_frac = VUMeter.db_to_fraction(self._peak_db)

        # --- Background ---
        painter.setBrush(COLOR_BACKGROUND)
        painter.setPen(QPen(COLOR_BORDER, 1))
        painter.drawRoundedRect(0, bar_y, bar_right, bar_h, 4, 4)

        # --- Gradient bar ---
        if rms_frac > 0:
            fill_w = int(bar_right * rms_frac)
            gradient = QLinearGradient(0, 0, bar_right, 0)
            gradient.setColorAt(0.0, COLOR_GREEN)
            gradient.setColorAt(VUMeter.db_to_fraction(VU_YELLOW_THRESHOLD), COLOR_YELLOW)
            gradient.setColorAt(VUMeter.db_to_fraction(VU_RED_THRESHOLD), COLOR_RED)
            gradient.setColorAt(1.0, COLOR_RED)

            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            # Clip to fill width
            painter.setClipRect(1, bar_y + 1, fill_w - 1, bar_h - 2)
            painter.drawRoundedRect(1, bar_y + 1, bar_right - 2, bar_h - 2, 3, 3)
            painter.setClipping(False)

        # --- Peak hold needle ---
        if self._peak_db > VU_FLOOR_DB:
            peak_x = int(bar_right * peak_frac)
            painter.setPen(QPen(COLOR_PEAK, 2))
            painter.drawLine(peak_x, bar_y + 2, peak_x, bar_y + bar_h - 2)

        # --- dBFS label ---
        label_x = bar_right + 6
        label_w = w - label_x
        db_val = self._smooth_rms
        if db_val <= VU_FLOOR_DB:
            label_text = "−∞"
        else:
            label_text = f"{db_val:+.1f}"

        font = QFont("Consolas", 8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(COLOR_TEXT)
        painter.drawText(
            label_x, bar_y, label_w, bar_h,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            label_text,
        )

        painter.end()
