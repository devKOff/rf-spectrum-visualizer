"""Tests for scan_worker.py ScanState state machine.

Run on any machine - no pyrf24, no radio, no display required.
"""

from __future__ import annotations

import pytest

from rf_spectrum_visualizer.scan_worker import ScanState


def test_scan_state_initial_idle():
    s = ScanState()
    assert s.state == ScanState.IDLE
    assert s.is_idle
    assert not s.is_running
    assert not s.is_stopping
    assert s.start_enabled
    assert not s.stop_enabled


def test_scan_state_start_transitions_to_starting():
    s = ScanState()
    assert s.start() is True
    assert s.state == ScanState.STARTING
    assert not s.start_enabled
    assert not s.stop_enabled


def test_scan_state_double_start_blocked():
    s = ScanState()
    assert s.start() is True
    assert s.start() is False
    assert s.state == ScanState.STARTING


def test_scan_state_started_transitions_to_running():
    s = ScanState()
    s.start()
    s.started()
    assert s.state == ScanState.RUNNING
    assert not s.start_enabled
    assert s.stop_enabled


def test_scan_state_stop_transitions_to_stopping():
    s = ScanState()
    s.start()
    s.started()
    assert s.stop() is None
    assert s.state == ScanState.STOPPING
    assert not s.start_enabled
    assert not s.stop_enabled


def test_scan_state_stop_when_idle_noop():
    s = ScanState()
    s.stop()
    assert s.state == ScanState.IDLE


def test_scan_state_stopped_transitions_to_idle():
    s = ScanState()
    s.start()
    s.started()
    s.stop()
    s.stopped()
    assert s.state == ScanState.IDLE
    assert s.start_enabled
    assert not s.stop_enabled


def test_scan_state_complete_from_running():
    s = ScanState()
    s.start()
    s.started()
    s.complete()
    assert s.state == ScanState.FINISHED
    assert s.start_enabled  # can start again after complete
    assert not s.stop_enabled


def test_scan_state_complete_from_stopping():
    s = ScanState()
    s.start()
    s.started()
    s.stop()
    s.complete()
    assert s.state == ScanState.FINISHED


def test_scan_state_error_from_running():
    s = ScanState()
    s.start()
    s.started()
    s.error()
    assert s.state == ScanState.ERROR
    assert s.start_enabled  # can start again after error
    assert not s.stop_enabled


def test_scan_state_error_from_stopping():
    s = ScanState()
    s.start()
    s.started()
    s.stop()
    s.error()
    assert s.state == ScanState.ERROR


def test_scan_state_reset_to_idle():
    s = ScanState()
    s.start()
    s.started()
    s.stop()
    s.stopped()
    assert s.state == ScanState.IDLE

    s.start()
    s.started()
    s.error()
    s.reset()
    assert s.state == ScanState.IDLE
    assert s.start_enabled


def test_scan_state_rapid_start_stop_50_times():
    s = ScanState()
    for _ in range(50):
        assert s.start() is True
        assert s.started() is None
        assert s.stop() is None
        assert s.stopped() is None
    assert s.state == ScanState.IDLE
    assert s.start_enabled