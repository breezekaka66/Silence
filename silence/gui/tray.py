"""
System Tray Icon — Silence's primary UI entry point.

The tray icon provides:
  - Status indicator (active/inactive/loading)
  - Right-click context menu (toggle, settings, quit)
  - Left-click to open settings window
  - Tooltip with current status
"""
import logging
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush
from PySide6.QtCore import Qt, QTimer, Signal, QObject

from silence.core.audio_pipeline import AudioPipeline
from silence.utils.config import Config

logger = logging.getLogger(__name__)


def _make_tray_icon(active: bool, loading: bool = False) -> QIcon:
    """
    Generate a simple colored circle icon for the system tray.
    
    active=True  → green circle  (processing)
    active=False → grey circle   (paused)
    loading=True → yellow circle (initialising)
    """
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if loading:
        color = QColor("#F59E0B")  # amber
    elif active:
        color = QColor("#10B981")  # emerald green
    else:
        color = QColor("#6B7280")  # grey

    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    margin = 4
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)

    # Inner white "S" would be nice but skip for simplicity
    painter.end()
    return QIcon(pixmap)


class SilenceTrayIcon(QSystemTrayIcon):
    """System tray icon with context menu for Silence."""

    def __init__(self, pipeline: AudioPipeline, config: Config, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline
        self._config = config
        self._settings_window = None

        # Set initial icon
        self.setIcon(_make_tray_icon(active=False))
        self.setToolTip("Silence — Noise Suppression (Inactive)")

        # Build context menu
        self._menu = QMenu()
        self._build_menu()
        self.setContextMenu(self._menu)

        # Left-click opens settings
        self.activated.connect(self._on_activated)

        # Auto-start if configured
        if self._config.enabled:
            # Delay start slightly so Qt event loop is ready
            QTimer.singleShot(500, self._start_pipeline)

    # -------------------------------------------------------------------------
    # Menu
    # -------------------------------------------------------------------------

    def _build_menu(self):
        """Build the right-click context menu."""
        self._menu.clear()

        # Status label (non-clickable)
        self._status_action = self._menu.addAction("● Inactive")
        self._status_action.setEnabled(False)
        self._menu.addSeparator()

        # Toggle action
        self._toggle_action = self._menu.addAction("▶  Enable Noise Suppression")
        self._toggle_action.triggered.connect(self._on_toggle)

        self._menu.addSeparator()

        # Settings
        settings_action = self._menu.addAction("⚙  Settings...")
        settings_action.triggered.connect(self._open_settings)

        self._menu.addSeparator()

        # Quit
        quit_action = self._menu.addAction("✕  Quit Silence")
        quit_action.triggered.connect(self._on_quit)

    def _update_menu_state(self, active: bool):
        """Reflect pipeline state in the context menu."""
        if active:
            self._status_action.setText("● Active — Noise Suppression ON")
            self._toggle_action.setText("⏸  Disable Noise Suppression")
            self.setIcon(_make_tray_icon(active=True))
            self.setToolTip("Silence — Noise Suppression Active")
        else:
            self._status_action.setText("● Inactive")
            self._toggle_action.setText("▶  Enable Noise Suppression")
            self.setIcon(_make_tray_icon(active=False))
            self.setToolTip("Silence — Noise Suppression Inactive")

    # -------------------------------------------------------------------------
    # Slots
    # -------------------------------------------------------------------------

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handle tray icon click."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open_settings()

    def _on_toggle(self):
        """Toggle noise suppression on/off."""
        if self._pipeline.is_running:
            self._pipeline.stop()
            self._config.enabled = False
            self._config.save()
            self._update_menu_state(active=False)
        else:
            self._start_pipeline()

    def _start_pipeline(self):
        """Start audio pipeline and update UI."""
        self.setIcon(_make_tray_icon(active=False, loading=True))
        self.setToolTip("Silence — Loading model...")
        self._toggle_action.setEnabled(False)

        # Run in a short-delay so the tray icon updates visually
        QTimer.singleShot(100, self._do_start)

    def _do_start(self):
        success = self._pipeline.start()
        self._toggle_action.setEnabled(True)
        if success:
            self._config.enabled = True
            self._config.save()
            self._update_menu_state(active=True)
        else:
            self._update_menu_state(active=False)
            self.showMessage(
                "Silence — Error",
                "Failed to start audio pipeline. Check logs for details.",
                QSystemTrayIcon.MessageIcon.Critical,
                3000,
            )

    def _open_settings(self):
        """Open or focus the settings window."""
        from silence.gui.main_window import MainWindow
        if self._settings_window is None or not self._settings_window.isVisible():
            self._settings_window = MainWindow(self._pipeline, self._config)
            self._settings_window.show()
        else:
            self._settings_window.raise_()
            self._settings_window.activateWindow()

    def _on_quit(self):
        """Stop pipeline and exit the application."""
        self._pipeline.stop()
        self._config.save()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()
