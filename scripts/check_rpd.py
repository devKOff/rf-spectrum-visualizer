#!/usr/bin/env python3
"""Phase 1 - hardware verification: check_rpd.py

Standalone script (no GUI) to measure nRF24L01+ RPD activity on a few channels.

Usage on the Pi:
    python scripts/check_rpd.py
    python scripts/check_rpd.py --channels 12 37 62 100 --samples 200

What it does:
    * Imports pyrf24 only at runtime (safe for pytest collection).
    * Configures the radio for scanning: auto-ack off, CRC disabled,
      1 Mbps, address width / payload size set for RX scan.
    * For each chosen channel: setChannel -> startListening -> short wait
      (~200 microseconds) -> testRPD() -> stopListening, repeated N times.
    * Prints per-channel RPD+ counts and Activity % = (RPD true / total) x 100.
    * Always releases the radio cleanly at exit via try/finally.

Timing note (Linux / time.sleep):
    * The nRF24 datasheet recommends ~130-200 us for the radio to settle
      after a channel change / entering RX mode before RPD is meaningful.
    * time.sleep() on Linux is NOT real-time: a 200 us request typically
      sleeps several milliseconds (scheduler granularity). This is fine for a
      verification script - it just makes each sample slower than the
      theoretical minimum. Do not interpret per-sample timing as precise.
    * For production scanning (Phase 2) we will measure elapsed time and
      compensate rather than relying on sleep precision.

This script never claims dBm or calibrated power values.
"""

from __future__ import annotations

import argparse
import sys
import time

CE_PIN = 25        # GPIO 25 (BCM) -> nRF24 CE pin
CSN_PIN = 0        # spidev device 0 = /dev/spidev0.0 = SPI CE0 = GPIO8
DEFAULT_CHANNELS = [12, 37, 62, 100]   # 12/37/62 ~ Wi-Fi ch 1/6/11; 100 = quiet
DEFAULT_SAMPLES = 100
SETTLE_SECONDS = 0.0002   # ~200 us settle (see timing note above)


def _fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def configure_for_scan(radio) -> None:
    """Put the radio into a scan-ready RX configuration.

    Settings chosen for RPD-based channel activity scanning:
      * auto-ack off       - we are only listening, never transmitting
      * CRC disabled       - RPD does not depend on packet integrity
      * data rate 1 Mbps   - most sensitive / common setting
      * address width 5    - default; irrelevant to RPD
      * payload size 1     - minimum; irrelevant to RPD
      * stopListening()    - start in idle, we call startListening per sample

    Note: pyrf24 0.6.0 expects the CRC / data-rate enums (module-level,
    e.g. pyrf24.RF24_CRC_DISABLED), not bare ints. Passing 0 raises
    TypeError: setCRCLength() incompatible function arguments.
    """
    import pyrf24  # module-level enums; safe - pyrf24 never imported at package import time
    radio.setAutoAck(False)

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


def scan_channel(radio, channel: int, samples: int, settle: float) -> tuple[int, int]:
    """Scan one channel for RPD activity.

    Returns (rpd_true_count, total_valid_samples).
    """
    rpd_true = 0
    valid = 0
    for _ in range(samples):
        radio.setChannel(channel)
        radio.startListening()
        time.sleep(settle)   # ~200 us settle; see timing note in module docstring
        try:
            tripped = bool(radio.testRPD())
        except Exception as exc:
            # A transient SPI read failure - count the sample but not as true.
            print(f"    (testRPD error on ch {channel}: {exc})")
            tripped = False
        finally:
            radio.stopListening()
        valid += 1
        if tripped:
            rpd_true += 1
    return rpd_true, valid


def run(channels: list[int], samples: int, ce_pin: int = CE_PIN,
        csn_pin: int = CSN_PIN, settle: float = SETTLE_SECONDS) -> int:
    try:
        import pyrf24
    except ImportError as exc:
        return _fail(
            "pyrf24 is not installed. On the Pi run: "
            "sudo apt install python3-spidev python3-dev && pip install pyrf24 "
            f"(original error: {exc})"
        )

    radio = None
    try:
        radio = pyrf24.RF24(ce_pin, csn_pin)
    except Exception as exc:  # SPI not enabled, permission, wiring, etc.
        return _fail(
            f"RF24 constructor raised {type(exc).__name__}: {exc}\n"
            "  Common causes: SPI not enabled (sudo raspi-config), user not in "
            "the spi group, wrong wiring/power."
        )

    try:
        if not radio.begin():
            return _fail(
                "radio.begin() returned False - the nRF24L01+ is not responding."
            )

        configure_for_scan(radio)

        print(f"{'Channel':>8} {'Freq MHz':>9} {'RPD+':>6} {'Samples':>8} {'Activity %':>10}")
        print("-" * 48)
        any_fail = False
        for ch in channels:
            if not (0 <= ch <= 125):
                print(f"  skip channel {ch}: out of range 0-125")
                any_fail = True
                continue
            freq_mhz = 2400 + ch
            rpd_true, valid = scan_channel(radio, ch, samples, settle)
            activity = (rpd_true / valid * 100) if valid else 0.0
            flag = ""
            if activity >= 75:
                flag = "  <- Heavy Load"
            elif activity >= 50:
                flag = "  <- Busy"
            elif activity >= 25:
                flag = "  <- Moderate"
            print(f"{ch:8d} {freq_mhz:9d} {rpd_true:6d} {valid:8d} {activity:9.1f}%{flag}")
            if valid < samples:
                print(f"    WARNING: only {valid}/{samples} valid samples on ch {ch}")
                any_fail = True

        print("-" * 48)
        print(
            "Activity % = (RPD true samples / total samples) x 100. "
            "RPD trips at about -64 dBm (yes/no flag only - no calibrated power)."
        )
        return 1 if any_fail else 0
    finally:
        # Always release the radio cleanly, even on error.
        try:
            radio.powerDown()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure nRF24L01+ RPD activity on selected channels."
    )
    parser.add_argument(
        "--channels", type=int, nargs="*", default=DEFAULT_CHANNELS,
        help=f"Channels to scan (0-125). Default: {DEFAULT_CHANNELS}",
    )
    parser.add_argument(
        "--samples", type=int, default=DEFAULT_SAMPLES,
        help=f"RPD samples per channel. Default: {DEFAULT_SAMPLES}.",
    )
    parser.add_argument(
        "--ce-pin", type=int, default=CE_PIN,
        help="CE GPIO pin number (BCM). Default: 25.",
    )
    parser.add_argument(
        "--csn-pin", type=int, default=CSN_PIN,
        help="CSN spidev device index (0=/dev/spidev0.0=CE0=GPIO8). Default: 0.",
    )
    parser.add_argument(
        "--settle", type=float, default=SETTLE_SECONDS,
        help=f"Settle time in seconds after startListening. Default: {SETTLE_SECONDS}.",
    )
    args = parser.parse_args(argv)
    return run(
        channels=args.channels,
        samples=args.samples,
        ce_pin=args.ce_pin,
        csn_pin=args.csn_pin,
        settle=args.settle,
    )


if __name__ == "__main__":
    sys.exit(main())
