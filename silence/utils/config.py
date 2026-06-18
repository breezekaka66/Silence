"""
Config — Persistent application settings using JSON.

Stores all user preferences to AppData\\Roaming\\Silence\\config.json.
Thread-safe for reads; writes should happen from the GUI thread only.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default configuration values
DEFAULTS: dict[str, Any] = {
    # Audio devices
    "input_device_index": None,   # None = system default microphone
    "output_device_index": None,  # None = system default output (use VB-Cable index)
    "input_device_name": "Default Microphone",
    "output_device_name": "CABLE Input (VB-Audio Virtual Cable)",

    # Denoising
    "denoise_strength": 80,       # 0–100
    "enabled": True,              # Global on/off

    # UI
    "hotkey_toggle": "ctrl+shift+s",
    "start_minimized": False,
    "start_on_boot": False,

    # Window
    "window_x": None,
    "window_y": None,
}


def _get_config_path() -> Path:
    """Return path to config file in Windows AppData."""
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    config_dir = Path(app_data) / "Silence"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


class Config:
    """
    Persistent configuration manager.

    Usage:
        config = Config()
        config.denoise_strength = 75
        config.save()
    """

    def __init__(self):
        self._path = _get_config_path()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self._load()

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _load(self):
        """Load config from disk, merging with defaults."""
        try:
            if self._path.exists():
                with open(self._path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Merge: saved values override defaults, but keep new defaults
                self._data.update(saved)
                logger.debug(f"Config loaded from {self._path}")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using defaults.")

    def save(self):
        """Persist current config to disk."""
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Config saved to {self._path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def reset(self):
        """Reset all settings to defaults."""
        self._data = dict(DEFAULTS)
        self.save()

    # -------------------------------------------------------------------------
    # Properties — typed accessors for all settings
    # -------------------------------------------------------------------------

    @property
    def input_device_index(self) -> int | None:
        return self._data.get("input_device_index")

    @input_device_index.setter
    def input_device_index(self, value: int | None):
        self._data["input_device_index"] = value

    @property
    def output_device_index(self) -> int | None:
        return self._data.get("output_device_index")

    @output_device_index.setter
    def output_device_index(self, value: int | None):
        self._data["output_device_index"] = value

    @property
    def input_device_name(self) -> str:
        return self._data.get("input_device_name", "Default")

    @input_device_name.setter
    def input_device_name(self, value: str):
        self._data["input_device_name"] = value

    @property
    def output_device_name(self) -> str:
        return self._data.get("output_device_name", "Default")

    @output_device_name.setter
    def output_device_name(self, value: str):
        self._data["output_device_name"] = value

    @property
    def denoise_strength(self) -> int:
        return int(self._data.get("denoise_strength", 80))

    @denoise_strength.setter
    def denoise_strength(self, value: int):
        self._data["denoise_strength"] = max(0, min(100, int(value)))

    @property
    def enabled(self) -> bool:
        return bool(self._data.get("enabled", True))

    @enabled.setter
    def enabled(self, value: bool):
        self._data["enabled"] = value

    @property
    def start_minimized(self) -> bool:
        return bool(self._data.get("start_minimized", False))

    @start_minimized.setter
    def start_minimized(self, value: bool):
        self._data["start_minimized"] = value

    @property
    def start_on_boot(self) -> bool:
        return bool(self._data.get("start_on_boot", False))

    @start_on_boot.setter
    def start_on_boot(self, value: bool):
        self._data["start_on_boot"] = value
        self._apply_boot_setting(value)

    @property
    def hotkey_toggle(self) -> str:
        return self._data.get("hotkey_toggle", "ctrl+shift+s")

    @hotkey_toggle.setter
    def hotkey_toggle(self, value: str):
        self._data["hotkey_toggle"] = value

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _apply_boot_setting(self, enable: bool):
        """Add or remove Silence from Windows startup registry."""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enable:
                    exe_path = os.path.abspath(
                        os.path.join(os.path.dirname(__file__), "..", "..", "silence.exe")
                    )
                    winreg.SetValueEx(key, "Silence", 0, winreg.REG_SZ, exe_path)
                else:
                    try:
                        winreg.DeleteValue(key, "Silence")
                    except FileNotFoundError:
                        pass
        except Exception as e:
            logger.debug(f"Boot setting update skipped: {e}")
