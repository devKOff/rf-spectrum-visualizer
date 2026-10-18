"""Regression tests for scripts/check_rpd.py

These tests do not require pyrf24, a radio, or a display. They verify that
configure_for_scan() passes pyrf24 module-level enums (not bare ints) to the
radio - the bug that caused TypeError on real hardware.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from rf_spectrum_visualizer import __version__


def _load_check_rpd():
    """Load scripts/check_rpd.py as a module without pyrf24 installed."""
    spec = importlib.util.spec_from_file_location("check_rpd", "scripts/check_rpd.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_version_still_3_1_0():
    assert __version__ == "3.1.0"


def test_configure_for_scan_passes_crc_enum_not_int():
    """setCRCLength must receive pyrf24.RF24_CRC_DISABLED enum, not 0."""
    mod = _load_check_rpd()

    fake_pyrf24 = ModuleType("pyrf24")
    fake_pyrf24.RF24_CRC_DISABLED = "CRC_DISABLED_ENUM"
    fake_pyrf24.RF24_1MBPS = "1MBPS_ENUM"

    radio = MagicMock()

    with patch.dict(sys.modules, {"pyrf24": fake_pyrf24}):
        mod.configure_for_scan(radio)

    radio.setCRCLength.assert_called_once_with("CRC_DISABLED_ENUM")
    # Must NOT have been called with bare int 0
    assert radio.setCRCLength.call_args[0][0] is not 0


def test_configure_for_scan_passes_rate_enum_not_int():
    """set_data_rate must receive pyrf24.RF24_1MBPS enum, not 0."""
    mod = _load_check_rpd()

    fake_pyrf24 = ModuleType("pyrf24")
    fake_pyrf24.RF24_CRC_DISABLED = "CRC_DISABLED_ENUM"
    fake_pyrf24.RF24_1MBPS = "1MBPS_ENUM"

    radio = MagicMock()

    with patch.dict(sys.modules, {"pyrf24": fake_pyrf24}):
        mod.configure_for_scan(radio)

    radio.set_data_rate.assert_called_once_with("1MBPS_ENUM")
    assert radio.set_data_rate.call_args[0][0] is not 0


def test_configure_for_scan_calls_stop_listening():
    mod = _load_check_rpd()

    fake_pyrf24 = ModuleType("pyrf24")
    fake_pyrf24.RF24_CRC_DISABLED = "CRC_DISABLED_ENUM"
    fake_pyrf24.RF24_1MBPS = "1MBPS_ENUM"

    radio = MagicMock()
    with patch.dict(sys.modules, {"pyrf24": fake_pyrf24}):
        mod.configure_for_scan(radio)

    radio.stopListening.assert_called_once()
