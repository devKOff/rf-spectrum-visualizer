"""rf_spectrum_visualizer.scan_worker

Background scan worker that runs a ScanBackend in a worker thread and
publishes results through a queue.  The GUI thread pulls from the queue
via tkinter.after().

Hardware imports (pyrf24) happen only inside HardwareBackend methods, never
at module import time, so this module is safe to import on any machine.

Scan model (Phase 7B):
    PASS-BASED continuous scanning.  One pass = N samples on every channel
    (0-125 by default), repeated continuously until Stop.  A rolling window
    (length from the Window setting) keeps recent samples per channel, and
    Activity % is computed from the window.  One update is published per pass.
"""

from __future__ import annotations

import collections
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from rf_spectrum_visualizer.scan_backend import (
    ChannelStats,
    HardwareBackend,
    ScanBackend,
    SimBackend,
)

CHANNEL_MIN = 0
CHANNEL_MAX = 125

# Default samples per pass per channel (1-3 keeps each pass fast).
DEFAULT_SAMPLES_PER_PASS = 1
# Default rolling window length in seconds.
DEFAULT_WINDOW_SECONDS = 10.0
# Default interval between passes in milliseconds.
DEFAULT_INTERVAL_MS = 250


@dataclass
class ScanPass:
    """One pass of scanning: per-channel results plus timing info.

    Published once per pass by ScanWorker.  The GUI consumes the latest
    ScanPass to refresh the table, bar chart, and waterfall.
    """

    pass_number: int
    pass_time_seconds: float   # measured time to complete this pass
    channel_stats: dict[int, ChannelStats]  # channel -> ChannelStats
    timestamp: float           # time.perf_counter() when pass finished


@dataclass
class ScanResult:
    """Legacy single-channel result (kept for test compatibility).

    No longer emitted by ScanWorker, which now emits ScanPass instead.
    """

    stats: ChannelStats


@dataclass
class ScanProgress:
    """Legacy progress message (kept for test compatibility).

    No longer emitted by ScanWorker, which now emits ScanPass instead.
    """

    channel: int
    total: int
    message: str


@dataclass
class ScanError:
    """Error message published to the GUI queue."""

    message: str


@dataclass
class ScanComplete:
    """Completion signal published to the GUI queue."""

    pass


class ScanState:
    """Explicit scan state machine for the Live Spectrum page.

    States: IDLE, STARTING, RUNNING, STOPPING, FINISHED, ERROR.

    Start is enabled only in IDLE. Stop is enabled only in RUNNING.
    Both are disabled in STOPPING.  No tkinter, no pyrf24, no display
    required - safe to unit test headless.
    """

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FINISHED = "finished"
    ERROR = "error"

    def __init__(self) -> None:
        self._state = self.IDLE

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_idle(self) -> bool:
        return self._state == self.IDLE

    @property
    def is_running(self) -> bool:
        return self._state == self.RUNNING

    @property
    def is_stopping(self) -> bool:
        return self._state == self.STOPPING

    @property
    def start_enabled(self) -> bool:
        return self._state in (self.IDLE, self.FINISHED, self.ERROR)

    @property
    def stop_enabled(self) -> bool:
        return self._state == self.RUNNING

    def start(self) -> bool:
        """Attempt to start scanning. Returns True if started, False if not in a startable state."""
        if self._state not in (self.IDLE, self.FINISHED, self.ERROR):
            return False
        self._state = self.STARTING
        return True

    def started(self) -> None:
        """Called when the worker thread has been created."""
        if self._state == self.STARTING:
            self._state = self.RUNNING

    def stop(self) -> None:
        """Mark scanning as stopping (user pressed Stop Scan)."""
        if self._state == self.RUNNING:
            self._state = self.STOPPING

    def stopped(self) -> None:
        """Called when the worker thread has fully exited."""
        if self._state == self.STOPPING:
            self._state = self.IDLE

    def complete(self) -> None:
        """Mark scanning as complete (scan finished normally)."""
        if self._state in (self.RUNNING, self.STOPPING):
            self._state = self.FINISHED

    def error(self) -> None:
        """Mark scanning as errored (radio failure, etc.)."""
        if self._state in (self.RUNNING, self.STOPPING):
            self._state = self.ERROR

    def reset(self) -> None:
        """Return to idle state."""
        self._state = self.IDLE


class RollingChannelBuffer:
    """Keeps a rolling window of per-channel RPD samples.

    Entries are (rpd_true_count, samples_count, timestamp).  Entries older
    than `window_seconds` are evicted on each update.  Activity % is
    (sum of rpd_true in window / sum of samples in window) x 100.
    """

    def __init__(self, window_seconds: float) -> None:
        self.window_seconds = window_seconds
        self._entries: "collections.deque[tuple[int, int, float]]" = (
            collections.deque()
        )

    def add(self, rpd_true: int, samples: int, timestamp: float) -> None:
        self._entries.append((rpd_true, samples, timestamp))
        self._evict(timestamp)

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._entries and self._entries[0][2] < cutoff:
            self._entries.popleft()

    def activity_percent(self) -> float:
        total_rpd = sum(e[0] for e in self._entries)
        total_samples = sum(e[1] for e in self._entries)
        if total_samples == 0:
            return 0.0
        return (total_rpd / total_samples) * 100.0


class ScanWorker:
    """Runs continuous pass-based channel scans in a background thread.

    The GUI thread calls start() and polls result_queue.get() (non-blocking)
    via tkinter.after().  The worker thread owns the ScanBackend lifecycle
    (open / close) so the radio is never touched from the GUI thread.
    """

    def __init__(self, backend: Optional[ScanBackend] = None) -> None:
        self.backend = backend or SimBackend()
        self.result_queue: "queue.Queue[object]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._channels: list[int] = []
        self._samples_per_pass: int = DEFAULT_SAMPLES_PER_PASS
        self._window_seconds: float = DEFAULT_WINDOW_SECONDS
        self._interval_ms: float = DEFAULT_INTERVAL_MS
        self._lock = threading.Lock()

        # Rolling buffers, one per channel.
        self._buffers: dict[int, RollingChannelBuffer] = {}

        # Pass telemetry.
        self._pass_number = 0
        self._last_pass_time: Optional[float] = None
        self._pass_times: list[float] = []

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def scan_rate(self) -> float:
        """Channels scanned per second over the rolling window of passes."""
        with self._lock:
            if not self._pass_times:
                return 0.0
            total_time = sum(self._pass_times[-10:])  # last 10 passes
            if total_time <= 0:
                return 0.0
            total_channels = len(self._channels) * min(10, len(self._pass_times))
            return total_channels / total_time

    @property
    def last_pass_time(self) -> Optional[float]:
        with self._lock:
            return self._last_pass_time

    def start(
        self,
        channels: list[int],
        samples_per_pass: int = DEFAULT_SAMPLES_PER_PASS,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        interval_ms: float = DEFAULT_INTERVAL_MS,
        backend: Optional[ScanBackend] = None,
    ) -> None:
        """Begin continuous pass-based scanning of `channels`.

        Safe to call only when not already running.
        """
        if self.running:
            return
        if backend is not None:
            self.backend = backend
        self._channels = list(channels)
        self._samples_per_pass = max(1, samples_per_pass)
        self._window_seconds = max(0.1, window_seconds)
        self._interval_ms = max(50.0, interval_ms)
        self._stop.clear()
        self._pass_number = 0
        self._pass_times = []
        self._buffers = {ch: RollingChannelBuffer(self._window_seconds) for ch in self._channels}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request the worker stop after the current pass finishes."""
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _update_buffer(self, channel: int, stats: ChannelStats, now: float) -> None:
        buf = self._buffers.get(channel)
        if buf is None:
            buf = RollingChannelBuffer(self._window_seconds)
            self._buffers[channel] = buf
        buf.add(stats.rpd_true, stats.samples, now)

    def _run(self) -> None:
        """Worker thread entry point: continuous passes."""
        self.backend.open()
        try:
            while not self._stop.is_set():
                pass_start = time.perf_counter()
                pass_stats: dict[int, ChannelStats] = {}

                for ch in self._channels:
                    if self._stop.is_set():
                        break
                    try:
                        stats = self.backend.scan_channel(ch, self._samples_per_pass)
                    except Exception as exc:  # hardware error on one channel
                        self.result_queue.put(
                            ScanError(message=f"Channel {ch}: {exc}")
                        )
                        continue
                    self._update_buffer(ch, stats, pass_start)
                    # Recompute Activity % from rolling window.
                    activity = self._buffers[ch].activity_percent()
                    total_samples = sum(
                        e[1] for e in self._buffers[ch]._entries
                    )
                    total_rpd = sum(
                        e[0] for e in self._buffers[ch]._entries
                    )
                    pass_stats[ch] = ChannelStats(
                        channel=ch,
                        freq_mhz=2400.0 + ch,
                        samples=total_samples,
                        rpd_true=total_rpd,
                        activity_percent=activity,
                    )

                pass_end = time.perf_counter()
                pass_time = pass_end - pass_start
                self._pass_number += 1
                with self._lock:
                    self._last_pass_time = pass_time
                    self._pass_times.append(pass_time)
                    if len(self._pass_times) > 50:
                        self._pass_times.pop(0)

                if pass_stats:
                    self.result_queue.put(
                        ScanPass(
                            pass_number=self._pass_number,
                            pass_time_seconds=pass_time,
                            channel_stats=pass_stats,
                            timestamp=pass_end,
                        )
                    )

                # Interval pacing: wait until interval_ms has elapsed since pass start.
                elapsed_ms = (pass_end - pass_start) * 1000.0
                sleep_ms = max(0.0, self._interval_ms - elapsed_ms)
                if sleep_ms > 0 and not self._stop.is_set():
                    time.sleep(sleep_ms / 1000.0)

            if not self._stop.is_set():
                self.result_queue.put(ScanComplete())
        finally:
            self.backend.close()
