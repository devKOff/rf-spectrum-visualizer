"""Phase 4 tests for analysis.py

Run on any machine - no pyrf24, no radio, no display required.
Uses SimBackend and mocked backends only.
"""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from rf_spectrum_visualizer.analysis import (
    AnalysisEngine,
    AnalysisResult,
    ChannelAnalysis,
    AVOID,
    BLOCKED_EXCLUDED,
    RECOMMENDED,
    run_quick_analysis,
)
from rf_spectrum_visualizer.scan_backend import ChannelStats, SimBackend


# ------------------------------------------------------------------ ChannelAnalysis
def test_channel_analysis_freq_mhz():
    ch = ChannelAnalysis(
        channel=12,
        freq_mhz=2412.0,
        avg_activity_percent=25.0,
        cycles=4,
        status="Clear",
        recommendation=RECOMMENDED,
    )
    assert ch.freq_mhz == 2412.0
    assert ch.is_clear is True


def test_channel_analysis_not_clear_when_avoid():
    ch = ChannelAnalysis(
        channel=37,
        freq_mhz=2437.0,
        avg_activity_percent=60.0,
        cycles=4,
        status="Busy",
        recommendation=AVOID,
    )
    assert ch.is_clear is False


def test_channel_analysis_not_clear_when_blocked():
    ch = ChannelAnalysis(
        channel=62,
        freq_mhz=2462.0,
        avg_activity_percent=10.0,
        cycles=4,
        status="Clear",
        recommendation=BLOCKED_EXCLUDED,
    )
    assert ch.is_clear is False


# ------------------------------------------------------------------ AnalysisEngine sim run
def test_analysis_engine_sim_runs():
    engine = AnalysisEngine(backend=SimBackend(seed=7))
    result = engine.run(cycles=2, samples_per_channel=50)

    assert result.cycles_run == 2
    assert result.channels_analyzed == 126
    assert result.busiest_channel is not None
    assert 0.0 <= result.average_activity <= 100.0
    assert len(result.channels) == 126


def test_analysis_engine_all_channels_0_125():
    engine = AnalysisEngine(backend=SimBackend(seed=7))
    result = engine.run(cycles=1, samples_per_channel=25)

    channels = sorted(c.channel for c in result.channels)
    assert channels == list(range(0, 126))


def test_analysis_engine_deterministic():
    a = AnalysisEngine(backend=SimBackend(seed=42)).run(cycles=2, samples_per_channel=50)
    b = AnalysisEngine(backend=SimBackend(seed=42)).run(cycles=2, samples_per_channel=50)
    assert [c.avg_activity_percent for c in a.channels] == [
        c.avg_activity_percent for c in b.channels
    ]


def test_analysis_engine_busiest_channel():
    engine = AnalysisEngine(backend=SimBackend(seed=7))
    result = engine.run(cycles=3, samples_per_channel=100)
    # Busiest should have the highest activity
    assert result.busiest_channel.avg_activity_percent == max(
        c.avg_activity_percent for c in result.channels
    )


# ------------------------------------------------------------------ Recommendations
def test_recommendation_clear_for_low_activity():
    engine = AnalysisEngine(backend=SimBackend(seed=7))
    engine.set_excluded_channels(set())
    result = engine.run(cycles=2, samples_per_channel=50)

    for ch in result.channels:
        if ch.avg_activity_percent < 50.0 and ch.channel not in engine.excluded_channels:
            assert ch.recommendation == RECOMMENDED


def test_recommendation_avoid_for_high_activity():
    engine = AnalysisEngine(backend=SimBackend(seed=7))
    engine.set_excluded_channels(set())
    result = engine.run(cycles=2, samples_per_channel=50)

    for ch in result.channels:
        if ch.avg_activity_percent >= 50.0:
            assert ch.recommendation == AVOID


def test_recommendation_blocked_for_excluded():
    engine = AnalysisEngine(backend=SimBackend(seed=7))
    engine.set_excluded_channels([12, 37])
    result = engine.run(cycles=2, samples_per_channel=50)

    for ch in result.channels:
        if ch.channel in (12, 37):
            assert ch.recommendation == BLOCKED_EXCLUDED


def test_excluded_channels_not_in_recommended_clear():
    engine = AnalysisEngine(backend=SimBackend(seed=7))
    engine.set_excluded_channels([12])
    result = engine.run(cycles=2, samples_per_channel=50)

    blocked = [c for c in result.channels if c.channel == 12][0]
    assert blocked.recommendation == BLOCKED_EXCLUDED
    assert blocked not in result.recommended_clear


# ------------------------------------------------------------------ Longest clear block
def test_longest_clear_block_contiguous():
    # Build a synthetic result where channels 10-15 are clear, others busy.
    analyses = []
    for ch in range(0, 126):
        if 10 <= ch <= 15:
            rec = RECOMMENDED
            activity = 10.0
        else:
            rec = AVOID
            activity = 80.0
        analyses.append(
            ChannelAnalysis(
                channel=ch,
                freq_mhz=2400 + ch,
                avg_activity_percent=activity,
                cycles=1,
                status="Clear" if activity < 50 else "Heavy Load",
                recommendation=rec,
            )
        )

    block = AnalysisEngine._find_longest_clear_block(analyses)
    assert len(block) == 6
    assert [c.channel for c in block] == [10, 11, 12, 13, 14, 15]


def test_longest_clear_block_excluded_breaks_block():
    analyses = []
    for ch in range(0, 126):
        rec = RECOMMENDED
        activity = 10.0
        analyses.append(
            ChannelAnalysis(
                channel=ch,
                freq_mhz=2400 + ch,
                avg_activity_percent=activity,
                cycles=1,
                status="Clear",
                recommendation=rec,
            )
        )
    # Exclude channel 50, breaking the 0-125 run into two blocks.
    analyses[50].recommendation = BLOCKED_EXCLUDED

    block = AnalysisEngine._find_longest_clear_block(analyses)
    # 0-49 = 50 channels, 51-125 = 75 channels. Longest is 51-125.
    assert len(block) == 75
    assert block[0].channel == 51
    assert block[-1].channel == 125


# ------------------------------------------------------------------ CSV export
def test_analysis_result_csv():
    analyses = [
        ChannelAnalysis(
            channel=12,
            freq_mhz=2412.0,
            avg_activity_percent=25.5,
            cycles=4,
            status="Clear",
            recommendation=RECOMMENDED,
        ),
        ChannelAnalysis(
            channel=37,
            freq_mhz=2437.0,
            avg_activity_percent=60.0,
            cycles=4,
            status="Busy",
            recommendation=AVOID,
        ),
    ]
    result = AnalysisResult(channels=analyses, cycles_run=4, channels_analyzed=2)
    csv_text = result.to_csv()

    assert "Channel,Freq MHz,Avg Activity %" in csv_text
    assert "12,2412.0,25.5,4,Clear,Recommended" in csv_text
    assert "37,2437.0,60.0,4,Busy,Avoid" in csv_text


# ------------------------------------------------------------------ run_quick_analysis
def test_run_quick_analysis_returns_result():
    result = run_quick_analysis(cycles=1, samples_per_channel=25, use_hardware=False)
    assert isinstance(result, AnalysisResult)
    assert result.channels_analyzed == 126


def test_run_quick_analysis_hardware_uses_hardware_backend():
    from rf_spectrum_visualizer import scan_backend as sb

    with patch.object(sb.HardwareBackend, "open", return_value=None), patch.object(
        sb.HardwareBackend, "close", return_value=None
    ), patch.object(
        sb.HardwareBackend,
        "scan_channel",
        return_value=ChannelStats.from_counts(channel=100, samples=10, rpd_true=0),
    ):
        result = run_quick_analysis(cycles=1, samples_per_channel=10, use_hardware=True)
        assert isinstance(result, AnalysisResult)
        assert result.channels_analyzed == 126


def test_analysis_engine_uses_hardware_backend_when_mode_hardware():
    """AnalysisEngine must use the passed hardware backend, not silently fall back to SimBackend."""
    from rf_spectrum_visualizer import scan_backend as sb

    captured_backend = None

    class CapturingHardwareBackend(sb.HardwareBackend):
        def open(self) -> None:
            nonlocal captured_backend
            captured_backend = self
            super().open()

    with patch.object(sb.HardwareBackend, "open", return_value=None), patch.object(
        sb.HardwareBackend, "close", return_value=None
    ), patch.object(
        sb.HardwareBackend,
        "scan_channel",
        return_value=ChannelStats.from_counts(channel=100, samples=10, rpd_true=0),
    ):
        # Patch SimBackend to raise if accidentally used
        with patch.object(
            sb.SimBackend, "scan_channel", side_effect=RuntimeError("SimBackend must not be used in hardware mode")
        ):
            engine = AnalysisEngine(backend=sb.HardwareBackend())
            result = engine.run(cycles=1, samples_per_channel=10)

    assert isinstance(result, AnalysisResult)
    assert result.channels_analyzed == 126
