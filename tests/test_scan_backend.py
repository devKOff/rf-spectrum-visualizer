"""Phase 2 tests for scan_backend.py

Run on any machine - no pyrf24, no radio, no display required.
pyrf24 is never imported at module import time, so these tests pass on a
bare dev machine.
"""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from rf_spectrum_visualizer.scan_backend import (
    ChannelStats,
    HardwareBackend,
    ScanBackend,
    SimBackend,
    busy_wait_settle,
)


def test_channel_stats_activity_percent():
    s = ChannelStats.from_counts(channel=12, samples=100, rpd_true=25)
    assert s.freq_mhz == 2412.0
    assert s.activity_percent == 25.0


def test_channel_stats_zero_samples():
    s = ChannelStats.from_counts(channel=100, samples=0, rpd_true=0)
    assert s.activity_percent == 0.0


def test_sim_backend_name():
    assert SimBackend().name == "sim"


def test_sim_backend_deterministic():
    a = SimBackend(seed=7).scan_channel(12, 1000)
    b = SimBackend(seed=7).scan_channel(12, 1000)
    assert a == b


def test_sim_backend_different_seed_different_result():
    a = SimBackend(seed=1).scan_channel(12, 1000)
    b = SimBackend(seed=2).scan_channel(12, 1000)
    assert a != b


def test_sim_backend_peak_channels_above_noise():
    sim = SimBackend(seed=7)
    peak = sim.scan_channel(12, 2000)
    quiet = sim.scan_channel(100, 2000)
    assert peak.activity_percent > quiet.activity_percent


def test_sim_backend_wifi_peaks_high():
    sim = SimBackend(seed=7)
    for ch in (12, 37, 62):
        activity = sim.scan_channel(ch, 2000).activity_percent
        assert activity > 50.0, f"channel {ch} activity {activity} not high"


def test_sim_backend_activity_in_range():
    sim = SimBackend(seed=7)
    for ch in range(0, 126):
        s = sim.scan_channel(ch, 100)
        assert 0.0 <= s.activity_percent <= 100.0


def test_sim_backend_out_of_range_raises():
    sim = SimBackend()
    with pytest.raises(ValueError):
        sim.scan_channel(-1, 10)
    with pytest.raises(ValueError):
        sim.scan_channel(126, 10)


def test_sim_backend_scan_channels_returns_all():
    sim = SimBackend(seed=7)
    results = sim.scan_channels([1, 2, 3], 50)
    assert len(results) == 3
    assert [r.channel for r in results] == [1, 2, 3]


def test_busy_wait_settle_returns():
    busy_wait_settle(0.0001)


def _make_fake_pyrf24():
    fake = ModuleType("pyrf24")
    fake.RF24_CRC_DISABLED = "CRC_DISABLED"
    fake.RF24_1MBPS = "1MBPS"
    fake.__version__ = "0.6.0"
    return fake


def test_hardware_backend_name():
    assert HardwareBackend().name == "hardware"


def test_hardware_backend_open_without_pyrf24_raises():
    with patch.dict("sys.modules", {"pyrf24": None}):
        backend = HardwareBackend()
        with pytest.raises(RuntimeError, match="pyrf24 is not installed"):
            backend.open()


def test_hardware_backend_scan_channel_opens_lazily():
    fake_pyrf24 = _make_fake_pyrf24()
    radio = MagicMock()
    radio.begin.return_value = True
    radio.testRPD.return_value = False

    backend = HardwareBackend()
    assert backend._radio is None
    fake_pyrf24.RF24 = MagicMock(return_value=radio)
    with patch.dict("sys.modules", {"pyrf24": fake_pyrf24}):
        stats = backend.scan_channel(5, 10)

    assert backend._radio is radio
    radio.begin.assert_called_once()
    assert stats.channel == 5
    assert stats.freq_mhz == 2405.0
    assert stats.samples == 10
    assert stats.rpd_true == 0
    assert stats.activity_percent == 0.0


def test_hardware_backend_scan_channel_counts_rpd_true():
    fake_pyrf24 = _make_fake_pyrf24()
    radio = MagicMock()
    radio.begin.return_value = True
    # 30 RPD-true samples out of 100
    radio.testRPD.side_effect = [True] * 30 + [False] * 70

    backend = HardwareBackend()
    fake_pyrf24.RF24 = MagicMock(return_value=radio)
    with patch.dict("sys.modules", {"pyrf24": fake_pyrf24}):
        stats = backend.scan_channel(12, 100)

    assert stats.rpd_true == 30
    assert stats.activity_percent == 30.0
    # stopListening: once in open()/_configure_for_scan() + once per sample
    assert radio.stopListening.call_count == 101


def test_hardware_backend_close_powers_down():
    fake_pyrf24 = _make_fake_pyrf24()
    radio = MagicMock()
    radio.begin.return_value = True
    backend = HardwareBackend()
    fake_pyrf24.RF24 = MagicMock(return_value=radio)
    with patch.dict("sys.modules", {"pyrf24": fake_pyrf24}):
        backend.open()
        backend.close()
    radio.powerDown.assert_called_once()
    assert backend._radio is None


def test_scan_backend_is_abstract():
    with pytest.raises(TypeError):
        ScanBackend()
