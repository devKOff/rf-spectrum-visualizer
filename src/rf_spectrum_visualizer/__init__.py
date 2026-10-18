"""rf_spectrum_visualizer - Raspberry Pi + nRF24L01+ 2.4 GHz RF activity visualizer.

Scans nRF24L01+ channels 0-125 (2400-2525 MHz) and shows RF activity as
Activity % = (samples with RPD true / total samples) x 100.

This is NOT an SDR. The nRF24 RPD flag is a yes/no that trips at roughly
-64 dBm, so the only metric is Activity %. Never claim dBm or calibrated
power in code, UI, or docs.

Hardware imports (pyrf24) must never execute at package import time, so tests
and sim mode work on any machine without pyrf24.

UI version label: v3.1  (package version: __version__)
"""

__version__ = "3.1.0"
UI_VERSION = "v3.1"
