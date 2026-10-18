#!/usr/bin/env python3
"""Phase 1 - hardware verification: check_radio.py

Standalone script (no GUI) to verify the nRF24L01+ radio is wired and
responding on the Raspberry Pi.

Usage on the Pi:
    python scripts/check_radio.py

What it does:
    1. Imports pyrf24 (only at runtime - safe for test collection).
    2. Constructs RF24 with CE=GPIO25 (BCM), CSN=SPI CE0 (/dev/spidev0.0).
    3. Calls begin() and reports whether the chip responded.
    4. Prints PASS / FAIL and radio details (data rate, PA level, channel,
       plus-variant flag).

Pin/CSN numbering choice (pyrf24 0.6.0 on Raspberry Pi):
    * CE is a GPIO number in BCM numbering -> 25 (wiring pin 22).
    * CSN is the spidev device index: 0 = /dev/spidev0.0 = SPI CE0 = GPIO8
      (wiring pin 24). So RF24(ce_pin=25, csn_pin=0).
    This matches the project wiring spec: CE=GPIO25, CSN=GPIO8/CE0.

This script never claims dBm or calibrated power values.
"""

from __future__ import annotations

import argparse
import sys

CE_PIN = 25        # GPIO 25 (BCM) -> nRF24 CE pin (wiring pin 22)
CSN_PIN = 0        # spidev device 0 = /dev/spidev0.0 = SPI CE0 = GPIO8 (pin 24)


def _fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def check_radio(ce_pin: int = CE_PIN, csn_pin: int = CSN_PIN) -> int:
    """Verify the nRF24L01+ is connected and responding.

    Returns 0 on PASS, non-zero on FAIL.
    """
    # Import pyrf24 only at runtime so this file is safe to collect in
    # pytest on machines where pyrf24 is not installed.
    try:
        import pyrf24
    except ImportError as exc:
        return _fail(
            "pyrf24 is not installed. On the Pi run: "
            "sudo apt install python3-spidev python3-dev && pip install pyrf24 "
            f"(original error: {exc})"
        )

    version = getattr(pyrf24, "__version__", "unknown")
    print(f"pyrf24 version: {version}")
    print(f"Constructing RF24(ce_pin={ce_pin}, csn_pin={csn_pin})")
    print("  (CE=GPIO number BCM; CSN=spidev device index, 0=/dev/spidev0.0=CE0=GPIO8)")

    radio = None
    try:
        radio = pyrf24.RF24(ce_pin, csn_pin)
    except TypeError as exc:
        return _fail(
            f"RF24(ce_pin, csn_pin) constructor raised TypeError: {exc}\n"
            "  Check the pyrf24 0.6.0 constructor signature on the Pi with "
            "python -c \"import pyrf24; help(pyrf24.RF24)\""
        )
    except Exception as exc:  # SPI bus not enabled, permission, etc.
        return _fail(
            f"RF24 constructor raised {type(exc).__name__}: {exc}\n"
            "  Common causes: SPI not enabled (sudo raspi-config), user not in "
            "the spi group, or wrong wiring/power."
        )

    # begin() returns True when the chip responds over SPI (chip detection).
    try:
        chip_ok = radio.begin()
    except Exception as exc:
        return _fail(
            f"radio.begin() raised {type(exc).__name__}: {exc}\n"
            "  If this is an SPI error, enable SPI and reboot the Pi."
        )

    if not chip_ok:
        return _fail(
            "radio.begin() returned False - the nRF24L01+ is not responding.\n"
            "  Check wiring: CE=GPIO25, CSN=GPIO8/CE0, SCK=GPIO11, MOSI=GPIO10, "
            "MISO=GPIO9, VCC=3.3V (NOT 5V), GND, with a 10 uF cap across VCC/GND."
        )

    # isChipConnected() is not documented in pyrf24 0.6.0; probe it safely.
    is_chip_connected = None
    if hasattr(radio, "isChipConnected"):
        try:
            is_chip_connected = bool(radio.isChipConnected())
        except Exception as exc:
            print(f"  (isChipConnected() raised {type(exc).__name__}: {exc}; ignored)")
    elif hasattr(radio, "is_chip_connected"):
        try:
            is_chip_connected = bool(radio.is_chip_connected())
        except Exception as exc:
            print(f"  (is_chip_connected() raised {type(exc).__name__}: {exc}; ignored)")

    # Gather relevant details (raw register reads, not calibrated power).
    details = {}
    for attr in ("getDataRate", "getPALevel", "getChannel", "isPVariant"):
        if hasattr(radio, attr):
            try:
                details[attr] = getattr(radio, attr)()
            except Exception as exc:
                details[attr] = f"error: {exc}"

    print("PASS: nRF24L01+ chip is connected and responding.")
    print(f"  begin()            = True")
    print(f"  isChipConnected()  = {is_chip_connected}")
    print(f"  data rate          = {details.get('getDataRate')}")
    print(f"  PA level           = {details.get('getPALevel')}")
    print(f"  channel            = {details.get('getChannel')}")
    print(f"  is PVariant (plus) = {details.get('isPVariant')}")
    print(
        "  Note: values above are raw register reads, not calibrated power "
        "measurements. The metric used by this project is Activity % "
        "(RPD true / total samples) x 100, not dBm."
    )

    # Release the radio cleanly.
    try:
        radio.powerDown()
    except Exception:
        pass

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the nRF24L01+ radio is connected and responding."
    )
    parser.add_argument(
        "--ce-pin", type=int, default=CE_PIN,
        help="CE GPIO pin number (BCM). Default: 25.",
    )
    parser.add_argument(
        "--csn-pin", type=int, default=CSN_PIN,
        help="CSN spidev device index (0=/dev/spidev0.0=CE0=GPIO8). Default: 0.",
    )
    args = parser.parse_args(argv)
    return check_radio(ce_pin=args.ce_pin, csn_pin=args.csn_pin)


if __name__ == "__main__":
    sys.exit(main())
