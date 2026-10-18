"""rf_spectrum_visualizer.analysis

Start Analysis engine: multi-cycle channel scanning, averaging, ranking,
recommendations, contiguous clear-block finder, and CSV export.

The only metric is Activity % = (samples with RPD true / total samples) x 100.
This is NOT an SDR and no dBm or calibrated power is ever claimed.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Iterable, Optional

from rf_spectrum_visualizer.scan_backend import (
    ChannelStats,
    HardwareBackend,
    ScanBackend,
    SimBackend,
)

CHANNEL_MIN = 0
CHANNEL_MAX = 125
FREQ_BASE_MHZ = 2400

# Recommendation thresholds (Activity %)
THRESHOLD_BUSY = 50.0
THRESHOLD_HEAVY = 75.0

RECOMMENDED = "Recommended"
AVOID = "Avoid"
BLOCKED_EXCLUDED = "Blocked - excluded"


@dataclass
class ChannelAnalysis:
    """Analysis result for a single channel."""

    channel: int
    freq_mhz: float
    avg_activity_percent: float
    cycles: int
    status: str  # Clear / Busy / Heavy Load
    recommendation: str  # Recommended / Avoid / Blocked - excluded

    @property
    def is_clear(self) -> bool:
        return self.recommendation == RECOMMENDED


def _status_for_activity(activity: float) -> str:
    if activity >= THRESHOLD_HEAVY:
        return "Heavy Load"
    if activity >= THRESHOLD_BUSY:
        return "Busy"
    return "Clear"


def _recommendation_for(
    activity: float, excluded_channels: set[int], channel: int
) -> str:
    if channel in excluded_channels:
        return BLOCKED_EXCLUDED
    if activity >= THRESHOLD_BUSY:
        return AVOID
    return RECOMMENDED


@dataclass
class AnalysisResult:
    """Full analysis result across all scanned channels."""

    channels: list[ChannelAnalysis] = field(default_factory=list)
    cycles_run: int = 0
    channels_analyzed: int = 0
    busiest_channel: Optional[ChannelAnalysis] = None
    average_activity: float = 0.0
    recommended_clear: list[ChannelAnalysis] = field(default_factory=list)
    longest_clear_block: list[ChannelAnalysis] = field(default_factory=list)

    def to_csv(self) -> str:
        """Export analysis results as CSV text."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["Channel", "Freq MHz", "Avg Activity %", "Cycles", "Status", "Recommendation"]
        )
        for ch in self.channels:
            writer.writerow(
                [
                    ch.channel,
                    ch.freq_mhz,
                    round(ch.avg_activity_percent, 2),
                    ch.cycles,
                    ch.status,
                    ch.recommendation,
                ]
            )
        return buf.getvalue()


class AnalysisEngine:
    """Runs multi-cycle analysis over all channels 0-125.

    Each cycle scans every channel once and records Activity %.
    After all cycles, per-channel Activity % is averaged across cycles.
    """

    def __init__(self, backend: Optional[ScanBackend] = None) -> None:
        self.backend = backend or SimBackend()
        self._excluded_channels: set[int] = set()

    @property
    def excluded_channels(self) -> set[int]:
        return set(self._excluded_channels)

    def set_excluded_channels(self, channels: Iterable[int]) -> None:
        self._excluded_channels = {int(c) for c in channels}

    def run(
        self, cycles: int = 4, samples_per_channel: int = 100
    ) -> AnalysisResult:
        """Run multi-cycle analysis over all channels 0-125.

        Args:
            cycles: number of full scan cycles to perform.
            samples_per_channel: RPD samples per channel per cycle.

        Returns:
            AnalysisResult with averaged per-channel stats and rankings.
        """
        all_channels = list(range(CHANNEL_MIN, CHANNEL_MAX + 1))

        # Accumulate activity sums and counts per channel across cycles.
        activity_sum: dict[int, float] = {ch: 0.0 for ch in all_channels}
        sample_count: dict[int, int] = {ch: 0 for ch in all_channels}
        rpd_true_total: dict[int, int] = {ch: 0 for ch in all_channels}

        self.backend.open()
        try:
            for cycle in range(1, cycles + 1):
                for ch in all_channels:
                    stats = self.backend.scan_channel(ch, samples_per_channel)
                    activity_sum[ch] += stats.activity_percent
                    sample_count[ch] += stats.samples
                    rpd_true_total[ch] += stats.rpd_true
        finally:
            self.backend.close()

        # Build per-channel analysis from averaged activity.
        channel_analyses: list[ChannelAnalysis] = []
        for ch in all_channels:
            avg_activity = activity_sum[ch] / cycles if cycles else 0.0
            total_samples = sample_count[ch]
            total_rpd = rpd_true_total[ch]
            status = _status_for_activity(avg_activity)
            recommendation = _recommendation_for(
                avg_activity, self._excluded_channels, ch
            )
            channel_analyses.append(
                ChannelAnalysis(
                    channel=ch,
                    freq_mhz=FREQ_BASE_MHZ + ch,
                    avg_activity_percent=avg_activity,
                    cycles=cycles,
                    status=status,
                    recommendation=recommendation,
                )
            )

        # Sort by activity descending for ranking (busiest first).
        ranked = sorted(
            channel_analyses, key=lambda c: c.avg_activity_percent, reverse=True
        )

        busiest = ranked[0] if ranked else None
        average_activity = (
            sum(c.avg_activity_percent for c in channel_analyses) / len(channel_analyses)
            if channel_analyses
            else 0.0
        )
        recommended_clear = [c for c in channel_analyses if c.is_clear]
        longest_clear_block = self._find_longest_clear_block(channel_analyses)

        return AnalysisResult(
            channels=channel_analyses,
            cycles_run=cycles,
            channels_analyzed=len(channel_analyses),
            busiest_channel=busiest,
            average_activity=average_activity,
            recommended_clear=recommended_clear,
            longest_clear_block=longest_clear_block,
        )

    @staticmethod
    def _find_longest_clear_block(
        channels: list[ChannelAnalysis],
    ) -> list[ChannelAnalysis]:
        """Find the longest contiguous run of Recommended (clear) channels.

        Channels are sorted by channel number. A "clear block" is a maximal
        contiguous sequence where every channel's recommendation is Recommended
        (i.e. activity < busy threshold and not excluded).
        """
        sorted_by_ch = sorted(channels, key=lambda c: c.channel)
        best_block: list[ChannelAnalysis] = []
        current_block: list[ChannelAnalysis] = []
        prev_channel: Optional[int] = None

        for ch in sorted_by_ch:
            if ch.is_clear and (prev_channel is None or ch.channel == prev_channel + 1):
                current_block.append(ch)
            else:
                if len(current_block) > len(best_block):
                    best_block = current_block
                current_block = [ch] if ch.is_clear else []
            prev_channel = ch.channel

        if len(current_block) > len(best_block):
            best_block = current_block

        return best_block


def run_quick_analysis(
    cycles: int = 4, samples_per_channel: int = 100, use_hardware: bool = False
) -> AnalysisResult:
    """Convenience: run analysis with sim or hardware backend."""
    backend: ScanBackend
    if use_hardware:
        backend = HardwareBackend()
    else:
        backend = SimBackend()
    engine = AnalysisEngine(backend=backend)
    return engine.run(cycles=cycles, samples_per_channel=samples_per_channel)
