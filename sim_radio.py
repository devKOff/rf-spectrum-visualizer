"""Simulated 2.4 GHz radio backend.

Drop-in replacement for the hardware backend (same interface:
open() / test_carrier(channel) / close()). Generates realistic fake
activity so the app can be developed and tested without an nRF24L01:

  * Wi-Fi-like blocks ~20 MHz wide around channels 1, 6 and 11
    (2412 / 2437 / 2462 MHz), with slowly varying intensity
  * a bursty narrow signal that hops to a new center on every burst
  * a low random noise floor everywhere
"""

import math
import random
import time

NUM_CHANNELS = 126            # nRF24 channels 0..125 -> 2400..2525 MHz
BASE_FREQ_MHZ = 2400.0


class SimRadio:
    def __init__(self, seed=None):
        self._rng = random.Random(seed)
        self._t0 = time.monotonic()
        self._closed = False
        # (center MHz, base strength 0..1, half-width MHz, phase offset)
        self._wifi = [
            (2412.0, 0.85, 10.0, 0.0),    # Wi-Fi channel 1
            (2437.0, 0.55, 10.0, 2.1),    # Wi-Fi channel 6
            (2462.0, 0.70, 10.0, 4.2),    # Wi-Fi channel 11
        ]

    # -- backend interface ------------------------------------------------
    def open(self):
        self._closed = False
        self._t0 = time.monotonic()

    def close(self):
        self._closed = True

    def test_carrier(self, channel):
        """Return 1 if a 'carrier' was seen on this channel, else 0."""
        freq = BASE_FREQ_MHZ + channel
        t = time.monotonic() - self._t0
        p = self._noise_prob(t, channel)
        p = max(p, self._wifi_prob(freq, t))
        p = max(p, self._burst_prob(freq, t))
        return 1 if self._rng.random() < min(p, 0.99) else 0

    # -- signal model -----------------------------------------------------
    def _wifi_prob(self, freq_mhz, t):
        p = 0.0
        for center, base, halfw, phase in self._wifi:
            d = abs(freq_mhz - center)
            if d > halfw:
                continue
            # slow traffic variation per network, raised-cosine band shape
            mod = 0.55 + 0.45 * math.sin(0.45 * t + phase)
            shape = 0.5 + 0.5 * math.cos(math.pi * d / halfw)
            p = max(p, base * mod * shape * self._rng.uniform(0.7, 1.0))
        return p

    def _burst_prob(self, freq_mhz, t):
        period = 3.0
        width = 0.25 + 0.15 * math.sin(t * 0.13)     # duty cycle wanders
        if (t % period) > width:
            return 0.0
        burst = int(t / period)
        center = 2405.0 + (burst * 37) % 110         # hops on every burst
        if abs(freq_mhz - center) <= 2.0:
            return 0.9 * self._rng.uniform(0.6, 1.0)
        return 0.0

    def _noise_prob(self, t, channel):
        return (0.02
                + 0.01 * math.sin(0.8 * t + channel * 0.07)
                + self._rng.random() * 0.01)
