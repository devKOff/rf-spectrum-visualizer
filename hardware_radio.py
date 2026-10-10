"""Hardware backend for the nRF24L01(+) via pyrf24 (SPI).

Wiring on the Raspberry Pi 3B+:
    CE   -> GPIO25 (pin 22)
    CSN  -> GPIO8  (pin 24, SPI0 CE0)
    SCK  -> GPIO11 (pin 23)
    MOSI -> GPIO10 (pin 19)
    MISO -> GPIO9  (pin 21)
    VCC  -> 3.3 V, with a 10 uF capacitor across VCC/GND
    IRQ  -> not used

ALL pyrf24 API calls are isolated in this file and each one is flagged
"# VERIFY ON PI" (pyrf24 0.6.0 API could not be confirmed during
development). Run tools/check_pyrf24_api.py on the Pi to verify them.
"""

import time

CE_PIN = 25
CSN_PIN = 0          # SPI0 chip-select 0 -> GPIO8 (CE0)
DWELL_US = 150       # listen time per channel, in microseconds

HARDWARE_HINTS = """\
Hints:
  * Is SPI enabled?  sudo raspi-config -> Interface Options -> SPI
    (check: ls /dev/spidev*)
  * Wiring: CE=GPIO25, CSN=GPIO8(CE0), SCK=GPIO11, MOSI=GPIO10, MISO=GPIO9
  * Power the nRF24 from 3.3 V (NOT 5 V) with a 10 uF cap across VCC/GND
  * Keep jumper leads short; reseat the module and try again
  * Run:  python tools/check_pyrf24_api.py   (to compare the pyrf24 API)
"""


class RadioError(Exception):
    """Raised when the radio library or the radio itself is not usable."""


class HardwareRadio:
    """nRF24L01 scanner backend. Interface: open() / test_carrier(ch) / close()."""

    NUM_CHANNELS = 126

    def __init__(self, dwell_us=DWELL_US):
        self._radio = None
        self._dwell_ns = int(dwell_us * 1000)

    def open(self):
        try:
            from pyrf24 import RF24, RF24_2MBPS  # VERIFY ON PI (import names)
        except ImportError as exc:
            raise RadioError("pyrf24 is not installed (pip install pyrf24).") from exc

        radio = RF24(CE_PIN, CSN_PIN)            # VERIFY ON PI: ctor (ce_pin, csn_pin)
        if not radio.begin():                    # VERIFY ON PI: begin() args & return value
            radio_power = getattr(radio, "powerDown", None)
            if callable(radio_power):
                radio_power()
            raise RadioError("RF24.begin() failed - is SPI enabled?")
        if not radio.isChipConnected():          # VERIFY ON PI
            raise RadioError("nRF24L01 not detected on the SPI bus.")

        radio.setAutoAck(False)                  # VERIFY ON PI
        radio.setDataRate(RF24_2MBPS)            # VERIFY ON PI (constant + method)
        radio.disableCRC()                       # VERIFY ON PI
        radio.setRetries(0, 0)                   # VERIFY ON PI
        radio.powerUp()                          # VERIFY ON PI
        self._radio = radio

    def test_carrier(self, channel):
        """Listen on `channel` for ~dwell_us and return 1 if RPD fired, else 0."""
        r = self._radio
        r.setChannel(channel)                    # VERIFY ON PI
        r.startListening()                       # VERIFY ON PI
        hit = 0
        deadline = time.perf_counter_ns() + self._dwell_ns
        # Poll RPD repeatedly during the dwell window (raises sensitivity).
        while time.perf_counter_ns() < deadline:
            if r.testRPD():                      # VERIFY ON PI
                hit = 1
        r.stopListening()                        # VERIFY ON PI
        return hit

    def close(self):
        r, self._radio = self._radio, None
        if r is not None:
            try:
                r.stopListening()                # VERIFY ON PI
                r.powerDown()                    # VERIFY ON PI
            except Exception:
                pass
