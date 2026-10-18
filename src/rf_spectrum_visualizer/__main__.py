"""Placeholder entry point: `python -m rf_spectrum_visualizer`.

The real GUI application is built in later phases. This placeholder keeps the
package importable and runnable from Phase 1 without pulling in pyrf24 or a GUI
toolkit at import time.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(f"rf_spectrum_visualizer {__import__('rf_spectrum_visualizer').__version__}")
    print("GUI entry point not implemented yet (Phase 3).")
    print("For hardware checks run: python scripts/check_radio.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
