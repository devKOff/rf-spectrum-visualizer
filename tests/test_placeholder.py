"""Trivial passing test so pytest works on Phase 1 (no hardware required).

This file must keep passing on any machine, including the dev machine that has
no pyrf24, no radio, and no display.
"""

from rf_spectrum_visualizer import __version__, UI_VERSION


def test_version_is_3_1_0():
    assert __version__ == "3.1.0"


def test_ui_version_is_v3_1():
    assert UI_VERSION == "v3.1"
