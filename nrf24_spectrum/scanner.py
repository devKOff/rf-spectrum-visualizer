"""nRF24L01 channel scanner built on the pyrf24 (snake_case) API."""
import threading
import time

import numpy as np
import pyrf24
from pyrf24 import RF24

from . import config as cfg


def _enum(cls_name, member):
    """Return an enum member whether pyrf24 exports it at top level or only on its enum class."""
    value = getattr(pyrf24, member, None)
    return value if value is not None else getattr(getattr(pyrf24, cls_name), member)


DATA_RATES = {
    "250 kbps (nRF24L01+ only)": _enum("rf24_datarate_e", "RF24_250KBPS"),
    "1 Mbps": _enum("rf24_datarate_e", "RF24_1MBPS"),
    "2 Mbps": _enum("rf24_datarate_e", "RF24_2MBPS"),
}
_CRC_OFF = _enum("rf24_crclength_e", "RF24_CRC_DISABLED")
_PA_MIN = _enum("rf24_pa_dbm_e", "RF24_PA_MIN")

# Everything this program relies on (names as documented for pyrf24).
REQUIRED_API = (
    "begin", "start_listening", "stop_listening", "flush_rx", "set_auto_ack",
    "set_pa_level", "channel", "rpd", "data_rate", "crc_length", "power",
    "is_chip_connected", "is_plus_variant",
)


def _val(x):
    return getattr(x, "value", x)


def open_radio():
    """Create and configure the radio for receive-only scanning."""
    radio = RF24(cfg.CE_PIN, cfg.CSN_PIN, cfg.SPI_SPEED_HZ)
    missing = [n for n in REQUIRED_API if not hasattr(radio, n)]
    if missing:
        raise RuntimeError("Installed pyrf24 lacks: " + ", ".join(missing))
    if not radio.begin():
        raise RuntimeError("radio.begin() failed - check wiring, SPI, and that no other program is using the radio.")
    if not radio.is_chip_connected:
        raise RuntimeError("SPI works but the nRF24L01 did not answer - check wiring and 3.3 V supply.")
    radio.set_auto_ack(False)         # we never transmit or acknowledge
    radio.crc_length = _CRC_OFF
    radio.set_pa_level(_PA_MIN)       # irrelevant for RX/RPD; keeps TX power minimal if code is reused
    return radio


def sweep_once(radio, dwell_s, on_channel=None):
    """Visit channels 0..125 once. Returns a uint8 array: 1 = RPD tripped (signal above threshold)."""
    hits = np.zeros(cfg.NUM_CHANNELS, dtype=np.uint8)
    perf = time.perf_counter
    for ch in range(cfg.NUM_CHANNELS):
        radio.channel = ch                 # channel N = 2400 + N MHz
        radio.start_listening()            # enter RX
        end = perf() + dwell_s
        while perf() < end:                # busy-wait: time.sleep() is too coarse for ~200 us
            pass
        if radio.rpd:                      # read while still in RX mode
            hits[ch] = 1
        radio.stop_listening()             # back to standby
        if on_channel is not None:
            on_channel(ch)
    radio.flush_rx()                       # discard any noise "packets" (CRC is off)
    return hits


class Scanner(threading.Thread):
    """Runs sweeps in the background and accumulates hit counts for the GUI."""

    def __init__(self, radio, data_rate, dwell_s):
        super().__init__(daemon=True)
        self.radio, self.data_rate, self.dwell_s = radio, data_rate, dwell_s
        self.current_channel = 0
        self.total_sweeps = 0
        self.error = None
        self._halt = threading.Event()
        self._lock = threading.Lock()
        self._acc = np.zeros(cfg.NUM_CHANNELS, dtype=np.float64)
        self._n = 0

    def stop(self):
        self._halt.set()

    def _set_channel(self, ch):
        self.current_channel = ch

    def take_frame(self):
        """Return (hit_counts, sweeps) accumulated since the last call, or None."""
        with self._lock:
            if self._n == 0:
                return None
            acc, n = self._acc.copy(), self._n
            self._acc[:] = 0
            self._n = 0
        return acc, n

    def run(self):
        r = self.radio
        try:
            r.data_rate = self.data_rate
            if _val(r.data_rate) != _val(self.data_rate):
                raise RuntimeError("Radio rejected this data rate (250 kbps needs an nRF24L01+).")
            if hasattr(r, "tx_delay"):
                r.tx_delay = 0             # we never transmit, so skip the TX-settle delay
            while not self._halt.is_set():
                hits = sweep_once(r, self.dwell_s, self._set_channel)
                with self._lock:
                    self._acc += hits
                    self._n += 1
                self.total_sweeps += 1
        except Exception as exc:           # report to the GUI instead of dying silently
            self.error = str(exc)
        finally:
            try:
                r.stop_listening()
            except Exception:
                pass
