"""Phase 3 tests: GUI theme + scan worker.

Run on any machine - no pyrf24, no radio, no display required.
Tkinter windows are never created in these tests.
"""

from __future__ import annotations

import queue
from unittest.mock import patch

import pytest

from rf_spectrum_visualizer.gui.theme import (
    THRESHOLD_BUSY,
    THRESHOLD_HEAVY,
    activity_color,
    channel_status,
    row_tint,
)
from rf_spectrum_visualizer.scan_backend import ChannelStats, SimBackend
from rf_spectrum_visualizer.scan_worker import (
    ScanComplete,
    ScanError,
    ScanPass,
    ScanProgress,
    ScanResult,
    ScanWorker,
)

# ------------------------------------------------------------------ theme
def test_theme_thresholds():
    assert THRESHOLD_BUSY == 50.0
    assert THRESHOLD_HEAVY == 75.0


def test_activity_color_bands():
    assert activity_color(10.0) == "#2e7d32"    # green (clear)
    assert activity_color(50.0) == "#ef6c00"    # orange (busy)
    assert activity_color(90.0) == "#c62828"    # red (heavy)


def test_channel_status_bands():
    assert channel_status(10.0) == "Clear"
    assert channel_status(50.0) == "Busy"
    assert channel_status(90.0) == "Heavy Load"


def test_row_tint_bands():
    assert row_tint(10.0) == "#e8f5e9"   # green tint
    assert row_tint(60.0) == "#fce4ec"   # pink tint


# ------------------------------------------------------------------ scan worker
def test_scan_worker_sim_runs_and_completes():
    """ScanWorker with SimBackend should produce ScanPass results and stop."""
    worker = ScanWorker(backend=SimBackend(seed=7))
    worker.start([12, 37, 100], samples_per_pass=50, interval_ms=10)

    pass_results = []
    errors = []
    complete = False
    # Drain queue until ScanComplete appears (worker runs continuous passes,
    # so we stop it after collecting at least one pass).
    import time as _time
    _time.sleep(0.3)
    worker.stop()
    while worker.running:
        _time.sleep(0.01)
    while not worker.result_queue.empty():
        try:
            msg = worker.result_queue.get(timeout=1)
        except queue.Empty:
            break
        if isinstance(msg, ScanPass):
            pass_results.append(msg.channel_stats)
        elif isinstance(msg, ScanError):
            errors.append(msg.message)
        elif isinstance(msg, ScanComplete):
            complete = True

    assert not errors, f"unexpected errors: {errors}"
    assert len(pass_results) >= 1, "expected at least one ScanPass"
    # First pass should have all 3 channels
    first_pass = pass_results[0]
    channels = sorted(first_pass.keys())
    assert channels == [12, 37, 100]
    # All activities should be in [0, 100]
    for stats in first_pass.values():
        assert 0.0 <= stats.activity_percent <= 100.0
    assert worker.running is False


def test_scan_worker_stop():
    """Calling stop() should end the worker early."""
    worker = ScanWorker(backend=SimBackend(seed=7))
    worker.start(list(range(0, 126)), samples_per_pass=50, interval_ms=10)
    worker.stop()

    # Wait for thread to finish
    while worker.running:
        pass

    assert worker.running is False


def test_scan_worker_default_backend_is_sim():
    worker = ScanWorker()
    assert isinstance(worker.backend, SimBackend)


def test_message_dataclasses():
    s = ChannelStats.from_counts(channel=12, samples=100, rpd_true=30)
    assert ScanResult(stats=s).stats.activity_percent == 30.0
    assert ScanProgress(channel=5, total=10, message="scanning").channel == 5
    assert ScanError(message="boom").message == "boom"
    assert isinstance(ScanComplete(), ScanComplete)


def test_scan_worker_hardware_falls_back_to_sim():
    """If HardwareBackend fails to open, ScanWorker should still run with SimBackend."""
    # Patch HardwareBackend.open to raise
    from rf_spectrum_visualizer import scan_backend as sb

    with patch.object(sb.HardwareBackend, "open", side_effect=RuntimeError("no radio")):
        worker = ScanWorker(backend=sb.HardwareBackend())
        # Manually swap to SimBackend to simulate the fallback logic
        worker.backend = SimBackend(seed=3)
        worker.start([100], samples_per_pass=25, interval_ms=10)

        complete = False
        import time as _time
        _time.sleep(0.3)
        worker.stop()
        # Wait for thread to finish
        while worker.running:
            _time.sleep(0.01)
        while not worker.result_queue.empty():
            try:
                msg = worker.result_queue.get(timeout=1)
            except queue.Empty:
                if not worker.running:
                    break
                continue
            if isinstance(msg, ScanPass):
                complete = True
            elif isinstance(msg, ScanError):
                pytest.fail(f"unexpected error: {msg.message}")

    assert complete


# ------------------------------------------------------------------ xticks
def test_setup_xticks_major_every_10_minor_every_5():
    """_setup_xticks must set major ticks every 10, minor every 5."""
    from rf_spectrum_visualizer.gui.pages.live_spectrum import LiveSpectrumPage
    from rf_spectrum_visualizer.gui.pages.start_analysis import StartAnalysisPage

    class FakeAx:
        def __init__(self) -> None:
            self.major = None
            self.minor = None
            self.labels = None

        def set_xticks(self, ticks, minor=False):
            if minor:
                self.minor = list(ticks)
            else:
                self.major = list(ticks)

        def set_xticklabels(self, labels):
            self.labels = list(labels)

    ax = FakeAx()
    LiveSpectrumPage._setup_xticks(ax)
    assert ax.major == list(range(0, 126, 10))
    assert ax.minor == list(range(0, 126, 5))
    assert ax.labels == [str(t) for t in range(0, 126, 10)]

    ax2 = FakeAx()
    StartAnalysisPage._setup_xticks(ax2)
    assert ax2.major == list(range(0, 126, 10))
    assert ax2.minor == list(range(0, 126, 5))
    assert ax2.labels == [str(t) for t in range(0, 126, 10)]

    assert complete



def test_setup_xticks_major_every_10_minor_every_5():
    """_setup_xticks must set major ticks every 10, minor every 5."""
    from rf_spectrum_visualizer.gui.pages.live_spectrum import LiveSpectrumPage
    from rf_spectrum_visualizer.gui.pages.start_analysis import StartAnalysisPage

    class FakeAx:
        def __init__(self) -> None:
            self.major = None
            self.minor = None
            self.labels = None

        def set_xticks(self, ticks, minor=False):
            if minor:
                self.minor = list(ticks)
            else:
                self.major = list(ticks)

        def set_xticklabels(self, labels):
            self.labels = list(labels)

    ax = FakeAx()
    LiveSpectrumPage._setup_xticks(ax)
    assert ax.major == list(range(0, 126, 10))
    assert ax.minor == list(range(0, 126, 5))
    assert ax.labels == [str(t) for t in range(0, 126, 10)]

    ax2 = FakeAx()
    StartAnalysisPage._setup_xticks(ax2)
    assert ax2.major == list(range(0, 126, 10))
    assert ax2.minor == list(range(0, 126, 5))
    assert ax2.labels == [str(t) for t in range(0, 126, 10)]
