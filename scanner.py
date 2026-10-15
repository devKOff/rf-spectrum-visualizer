"""Backend-agnostic scanning engine.

SpectrumData   - thread-safe rolling history of per-channel sweep results
ScannerThread  - background thread that sweeps all 126 channels in a loop
create_radio() - pick the hardware or simulation backend

A radio backend must provide:
    open()
    test_carrier(channel) -> 0 or 1   (carrier-detect on that channel)
    close()
"""

import threading
import time
from collections import deque

from hardware_radio import HardwareRadio, RadioError
from sim_radio import SimRadio

NUM_CHANNELS = 126          # channels 0..125 -> 2400..2525 MHz (1 MHz steps)
BASE_FREQ_MHZ = 2400
DEFAULT_WINDOW = 100        # sweeps kept in the rolling window
WATERFALL_ROWS = 200        # time rows kept for the waterfall view
WATERFALL_INTERVAL = 0.02   # min seconds between waterfall rows (~50 rows/s max)


class SpectrumData:
    """Rolling window of the last N sweeps, safe to share between threads."""

    def __init__(self, window=DEFAULT_WINDOW,
                 waterfall_rows=WATERFALL_ROWS,
                 waterfall_interval=WATERFALL_INTERVAL):
        self._lock = threading.Lock()
        self._window = max(1, int(window))
        self._wf_max = max(1, int(waterfall_rows))
        self._wf_interval = float(waterfall_interval)
        self._reset()

    def _reset(self):
        self._sweeps = deque()
        self._sums = [0] * NUM_CHANNELS
        self._times = deque(maxlen=120)     # sweep end timestamps (rate calc)
        self._wf_rows = deque(maxlen=self._wf_max)
        self._wf_count = 0                  # id of newest waterfall row
        self._wf_last_t = 0.0
        self.total_sweeps = 0
        self.error = None
        self.running = False

    # -- writer side (scanner thread) --------------------------------------
    def add_sweep(self, hits):
        """hits: sequence of NUM_CHANNELS 0/1 carrier-detect results."""
        now = time.monotonic()
        hits = tuple(1 if h else 0 for h in hits)
        with self._lock:
            if len(self._sweeps) == self._window:
                old = self._sweeps.popleft()
                self._sums = [a - b for a, b in zip(self._sums, old)]
            self._sweeps.append(hits)
            self._sums = [a + b for a, b in zip(self._sums, hits)]
            self.total_sweeps += 1
            self._times.append(now)
            if now - self._wf_last_t >= self._wf_interval:
                n = len(self._sweeps)
                self._wf_rows.append(tuple(100.0 * s / n for s in self._sums))
                self._wf_count += 1
                self._wf_last_t = now

    # -- reader side (GUI / CLI) -------------------------------------------
    def activity(self):
        """Current rolling activity per channel, 0..100 %."""
        with self._lock:
            n = len(self._sweeps)
            if not n:
                return [0.0] * NUM_CHANNELS
            return [100.0 * s / n for s in self._sums]

    def stats(self):
        with self._lock:
            t = self._times
            rate = ((len(t) - 1) / (t[-1] - t[0])
                    if len(t) >= 2 and t[-1] > t[0] else 0.0)
            n = len(self._sweeps)
            if n:
                best = max(range(NUM_CHANNELS), key=lambda i: self._sums[i])
                busiest_pct = 100.0 * self._sums[best] / n
            else:
                best, busiest_pct = 0, 0.0
            return {
                "sweeps_per_sec": rate,
                "total_sweeps": self.total_sweeps,
                "busiest_channel": best,
                "busiest_freq_mhz": BASE_FREQ_MHZ + best,
                "busiest_pct": busiest_pct,
                "running": self.running,
                "error": self.error,
            }

    def waterfall_since(self, last_count):
        """Return (rows, newest_count): waterfall rows newer than last_count.

        rows: list of tuples (activity % per channel), oldest first.
        """
        with self._lock:
            newest = self._wf_count
            missing = newest - last_count
            if missing <= 0:
                return [], newest
            rows = list(self._wf_rows)
            return rows[-missing:] if missing <= len(rows) else rows, newest

    # -- control -------------------------------------------------------------
    def set_window(self, window):
        """Change the rolling-window size (in sweeps)."""
        with self._lock:
            self._window = max(1, int(window))
            keep = list(self._sweeps)[-self._window:]
            self._sweeps = deque(keep)
            self._sums = [0] * NUM_CHANNELS
            for sweep in keep:
                self._sums = [a + b for a, b in zip(self._sums, sweep)]

    def clear(self):
        """Throw away all history (counters restart)."""
        with self._lock:
            self._reset()


class ScannerThread(threading.Thread):
    """Sweeps all channels in a loop until stop() is called."""

    def __init__(self, radio, data, num_channels=NUM_CHANNELS):
        super().__init__(name="scanner", daemon=True)
        self._radio = radio
        self._data = data
        self._channels = tuple(range(num_channels))
        self._stop = threading.Event()

    def run(self):
        self._data.running = True
        try:
            while not self._stop.is_set():
                hits = [self._radio.test_carrier(ch) for ch in self._channels]
                if self._stop.is_set():
                    break
                self._data.add_sweep(hits)
        except Exception as exc:                # radio died mid-scan etc.
            self._data.error = "%s: %s" % (type(exc).__name__, exc)
        finally:
            self._data.running = False

    def stop(self):
        self._stop.set()


def create_radio(mode):
    """Pick a backend.

    mode: 'hw' | 'sim' | 'auto'  ->  (radio, label, fallback_error_or_None)
    'auto' uses hardware when available, otherwise simulation.
    Raises RadioError for mode 'hw' when the radio is not usable.
    """
    if mode == "sim":
        radio = SimRadio()
        radio.open()
        return radio, "SIMULATION", None

    radio = HardwareRadio()
    try:
        radio.open()
        return radio, "HARDWARE", None
    except Exception as exc:
        radio.close()
        if mode == "hw":
            raise
        sim = SimRadio()
        sim.open()
        return sim, "SIMULATION", exc
