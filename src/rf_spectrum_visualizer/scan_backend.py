"""Scan backend for rf_spectrum_visualizer Phase 2.

Provides:
    ChannelStats   - per-channel scan results
    ScanBackend    - abstract interface (name, open, close, scan_channel)
    SimBackend     - deterministic simulation; no hardware, no pyrf24 required
    HardwareBackend - real nRF24L01+ via pyrf24 (imported at runtime only)

The only metric is Activity % = (samples with RPD true / total samples) x 100.
The nRF24 RPD flag is a yes/no that trips at roughly -64 dBm.  This is NOT an
SDR and this module never claims dBm or calibrated power.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable

FREQ_BASE_MHZ = 2400
CHANNEL_MIN = 0
CHANNEL_MAX = 125

# ~200 us settle after startListening before testRPD() is meaningful.
SETTLE_SECONDS = 0.0002


@dataclass(frozen=True)
class ChannelStats:
    """Result of scanning a single channel.

    activity_percent = (rpd_true / samples) x 100.  RPD is a yes/no flag; it
    is NOT a calibrated power measurement and no dBm value is ever claimed.
    """

    channel: int
    freq_mhz: float
    samples: int
    rpd_true: int
    activity_percent: float

    @classmethod
    def from_counts(cls, channel: int, samples: int, rpd_true: int) -> "ChannelStats":
        activity = (rpd_true / samples * 100) if samples else 0.0
        return cls(
            channel=channel,
            freq_mhz=FREQ_BASE_MHZ + channel,
            samples=samples,
            rpd_true=rpd_true,
            activity_percent=activity,
        )


def _validate_channel(channel: int) -> None:
    if not (CHANNEL_MIN <= channel <= CHANNEL_MAX):
        raise ValueError(f"channel {channel} out of range {CHANNEL_MIN}-{CHANNEL_MAX}")


def busy_wait_settle(seconds: float) -> None:
    """Wait approximately `seconds` using time.perf_counter().

    time.sleep() on Linux is not real-time: a 200 us request typically sleeps
    several milliseconds.  This busy-wait stays closer to the requested settle
    time for short settles, sleeping in small chunks so it does not peg the CPU
    for very long settles.
    """
    deadline = time.perf_counter() + seconds
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.00005))


class ScanBackend(ABC):
    """Abstract interface for scanning nRF24L01+ channels."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name (e.g. 'sim' or 'hardware')."""

    @abstractmethod
    def open(self) -> None:
        """Prepare the backend for scanning."""

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the backend."""

    @abstractmethod
    def scan_channel(self, channel: int, samples: int) -> ChannelStats:
        """Scan one channel for RPD activity and return ChannelStats."""

    def scan_channels(
        self, channels: Iterable[int], samples: int
    ) -> list[ChannelStats]:
        """Scan many channels, returning a list of ChannelStats in order."""
        return [self.scan_channel(ch, samples) for ch in channels]

    def __enter__(self) -> "ScanBackend":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class SimBackend(ScanBackend):
    """Deterministic simulation backend.

    Model: low noise floor plus deterministic peaks near channels 12, 37, 62
    (Wi-Fi channels 1/6/11) and a few others.  Same seed + same channel always
    yields the same activity, so results are reproducible on any machine with
    no radio and no pyrf24 required.
    """

    # Peak channel -> base activity probability (Wi-Fi 1/6/11 plus a few others)
    PEAK_CHANNELS = {
        12: 0.85,   # Wi-Fi ch 1
        37: 0.78,   # Wi-Fi ch 6
        62: 0.90,   # Wi-Fi ch 11
        1: 0.30,
        13: 0.25,
        25: 0.20,
        50: 0.15,
        75: 0.10,
        100: 0.05,
    }
    NOISE_FLOOR = 0.02   # baseline activity probability on every channel
    JITTER = 0.05        # deterministic per-channel jitter

    def __init__(self, seed: int = 4242) -> None:
        self._seed = seed
        self._open = False

    @property
    def name(self) -> str:
        return "sim"

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def _activity_probability(self, channel: int) -> float:
        base = self.NOISE_FLOOR
        peak = self.PEAK_CHANNELS.get(channel, 0.0)
        rng = random.Random((self._seed * 1000) + channel)
        jitter = rng.random() * self.JITTER
        return min(1.0, base + peak + jitter)

    def scan_channel(self, channel: int, samples: int) -> ChannelStats:
        _validate_channel(channel)
        p = self._activity_probability(channel)
        rng = random.Random((self._seed * 1000) + channel)
        rpd_true = sum(1 for _ in range(samples) if rng.random() < p)
        return ChannelStats.from_counts(channel, samples, rpd_true)


class HardwareBackend(ScanBackend):
    """Real nRF24L01+ backend via pyrf24.

    pyrf24 is imported only inside methods, so this class can be imported and
    instantiated on any machine without pyrf24 installed.  Construction is safe
    without hardware; pyrf24/RF24 only runs when open() or scan_channel() is
    called on the Raspberry Pi.
    """

    def __init__(
        self,
        ce_pin: int = 25,
        csn_pin: int = 0,
        settle_seconds: float = SETTLE_SECONDS,
    ) -> None:
        self.ce_pin = ce_pin
        self.csn_pin = csn_pin
        self.settle_seconds = settle_seconds
        self._radio = None

    @property
    def name(self) -> str:
        return "hardware"

    def _import_pyrf24(self):
        try:
            import pyrf24
        except ImportError as exc:
            raise RuntimeError(
                "pyrf24 is not installed. On the Pi: pip install pyrf24 "
                "(needs python3-spidev python3-dev). "
                f"(original error: {exc})"
            ) from exc
        return pyrf24

    def open(self) -> None:
        if self._radio is not None:
            return
        pyrf24 = self._import_pyrf24()
        self._radio = pyrf24.RF24(self.ce_pin, self.csn_pin)
        if not self._radio.begin():
            self.close()
            raise RuntimeError(
                "radio.begin() returned False - nRF24L01+ is not responding."
            )
        self._configure_for_scan()

    def _configure_for_scan(self) -> None:
        radio = self._radio
        radio.setAutoAck(False)
        import pyrf24  # module-level enums; runtime import only

        crc_disabled = getattr(pyrf24, "RF24_CRC_DISABLED", None)
        if hasattr(radio, "setCRCLength") and crc_disabled is not None:
            radio.setCRCLength(crc_disabled)
        elif hasattr(radio, "set_crc_length") and crc_disabled is not None:
            radio.set_crc_length(crc_disabled)

        rate = getattr(pyrf24, "RF24_1MBPS", None)
        if rate is not None:
            if hasattr(radio, "set_data_rate"):
                radio.set_data_rate(rate)
            else:
                radio.setDataRate(rate)

        if hasattr(radio, "set_address_width"):
            radio.set_address_width(5)
        else:
            radio.setAddressWidth(5)
        if hasattr(radio, "set_payload_size"):
            radio.set_payload_size(1)
        else:
            radio.setPayloadSize(1)
        radio.stopListening()

    def close(self) -> None:
        if self._radio is not None:
            try:
                self._radio.powerDown()
            except Exception:
                pass
            self._radio = None

    def scan_channel(self, channel: int, samples: int) -> ChannelStats:
        _validate_channel(channel)
        if self._radio is None:
            self.open()
        radio = self._radio
        rpd_true = 0
        valid = 0
        for _ in range(samples):
            radio.setChannel(channel)
            radio.startListening()
            busy_wait_settle(self.settle_seconds)
            try:
                tripped = bool(radio.testRPD())
            except Exception as exc:
                print(f"    (testRPD error on ch {channel}: {exc})")
                tripped = False
            finally:
                radio.stopListening()
            valid += 1
            if tripped:
                rpd_true += 1
        return ChannelStats.from_counts(channel, valid, rpd_true)
