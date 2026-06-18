"""Silence application entry point."""
import sys
from silence.utils.logging_config import setup_logging
from silence.app import SilenceApp


def main():
    """Main entry point for the Silence application."""
    setup_logging("INFO")
    app = SilenceApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
