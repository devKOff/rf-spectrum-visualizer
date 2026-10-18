#!/usr/bin/env python3
"""Launch script for rf_spectrum_visualizer GUI.

Usage on the Raspberry Pi:
    python scripts/run_gui.py

Sets up optional logging to rf_spectrum_visualizer.log and starts the
Tkinter + Matplotlib GUI.

Hardware imports (pyrf24) happen only inside the scan backend, never at
package import time, so this script is safe to run on any machine with
Python + tkinter + matplotlib (GUI will run in sim mode without pyrf24).
"""

from __future__ import annotations

import logging
import os
import sys

LOG_FILENAME = "rf_spectrum_visualizer.log"


def _setup_logging(enable_file_logging: bool = True) -> None:
    """Configure logging to stdout and optionally to a file.

    Logging is intentionally minimal and optional.  If file logging is
    disabled or the file cannot be opened, we fall back to stdout only.
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    if enable_file_logging:
        try:
            handlers.append(logging.FileHandler(LOG_FILENAME, encoding="utf-8"))
        except OSError as exc:
            print(f"Could not open log file {LOG_FILENAME}: {exc}", file=sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> int:
    _setup_logging(enable_file_logging=True)
    logger = logging.getLogger("rf_spectrum_visualizer")

    logger.info("rf_spectrum_visualizer v3.1 starting")
    logger.info("Python %s on %s", sys.version.split()[0], sys.platform)

    # Import the GUI only after logging is configured.  Nothing in the GUI
    # package creates a window at import time.
    try:
        from rf_spectrum_visualizer.gui.main_window import run
    except ImportError as exc:
        logger.error("Failed to import GUI: %s", exc)
        print(
            "Failed to import the GUI.  Make sure you are in the project "
            "root and have installed the dependencies (matplotlib, tkinter).",
            file=sys.stderr,
        )
        return 1

    logger.info("Launching GUI event loop")
    try:
        run()
    except Exception as exc:  # pragma: no cover - GUI runtime errors
        logger.exception("GUI exited with error: %s", exc)
        raise
    logger.info("GUI event loop ended")
    return 0


if __name__ == "__main__":
    sys.exit(main())
