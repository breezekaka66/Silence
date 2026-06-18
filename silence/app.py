"""
Silence Application — Top-level Qt Application wrapper.
Manages the system tray, audio pipeline lifecycle, and global state.
"""
import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from silence.gui.tray import SilenceTrayIcon
from silence.core.audio_pipeline import AudioPipeline
from silence.utils.config import Config
from silence.utils.vbcable_check import check_vbcable

logger = logging.getLogger(__name__)


class SilenceApp(QApplication):
    """Main Qt application for Silence."""

    def __init__(self, argv: list[str]):
        super().__init__(argv)

        # Keep running even if all windows are closed (system tray app)
        self.setQuitOnLastWindowClosed(False)
        self.setApplicationName("Silence")
        self.setApplicationVersion("0.1.0")
        self.setOrganizationName("Silence")

        # Set app icon
        icon_path = self._resolve_icon()
        if icon_path:
            self.setWindowIcon(QIcon(icon_path))

        # Load config
        self.config = Config()

        # Check VB-Cable and auto-set output device index
        vbcable_ok = check_vbcable()
        if vbcable_ok:
            from silence.utils.vbcable_check import find_vbcable_input_index
            cable_in_idx = find_vbcable_input_index()
            if cable_in_idx is not None and self.config.output_device_index is None:
                # Auto-set on first run
                self.config.output_device_index = cable_in_idx
                self.config.save()
                logger.info(f"Auto-set VB-Cable output device index: {cable_in_idx}")
        else:
            logger.warning("VB-Cable not detected. Virtual microphone output disabled.")

        # Create audio pipeline (not started yet)
        self.pipeline = AudioPipeline(self.config)

        # Create system tray icon (this is the main UI)
        self.tray = SilenceTrayIcon(self.pipeline, self.config, self)
        self.tray.show()

        logger.info("Silence application started.")

    def _resolve_icon(self) -> str | None:
        """Resolve the application icon path."""
        import os
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png"),
            os.path.join(os.path.dirname(__file__), "..", "assets", "icon.ico"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return os.path.abspath(path)
        return None
