"""
Silence — Logging configuration.
Sets up structured logging for both console and rotating file output.
"""
import logging
import logging.handlers
import os
from pathlib import Path


def setup_logging(level: str = "INFO"):
    """Configure application-wide logging."""
    app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
    log_dir = Path(app_data) / "Silence" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "silence.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)

    # Rotating file handler (max 5MB × 3 files)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(console)
    root.addHandler(file_handler)

    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
