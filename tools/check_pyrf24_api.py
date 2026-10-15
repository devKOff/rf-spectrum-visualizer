#!/usr/bin/env python3
"""Verify the pyrf24 API used by hardware_radio.py -- RUN THIS ON THE PI.

It checks that every pyrf24 name flagged "# VERIFY ON PI" in
hardware_radio.py actually exists in the installed pyrf24 version, then
tries a basic radio init + carrier-detect smoke test.

    python tools/check_pyrf24_api.py
"""

import sys
import time

CE_PIN = 25
CSN_PIN = 0          # SPI0 CE0 -> GPIO8

# names used by hardware_radio.py
MODULE_NAMES = ["RF24", "RF24_2MBPS"]
RF24_METHODS = [
    "begin", "isChipConnected", "setAutoAck", "setDataRate", "disableCRC",
    "setRetries", "powerUp", "powerDown",
    "setChannel", "startListening", "stopListening", "testRPD",
]


def main():
    print("python :", sys.version.split()[0])
    try:
        import pyrf24
    except ImportError as exc:
        print("FAIL  : cannot import pyrf24: %s" % exc)
        print("        install with:  pip install pyrf24")
        return 1
    print("pyrf24 : %s" % getattr(pyrf24, "__version__", "version unknown"))
    print("from   : %s" % getattr(pyrf24, "__file__", "?"))

    ok = True
    for name in MODULE_NAMES:
        has = hasattr(pyrf24, name)
        ok &= has
        print("%s : pyrf24.%s" % ("OK  " if has else "MISS", name))

    rf24_cls = getattr(pyrf24, "RF24", None)
    if rf24_cls is not None:
        for meth in RF24_METHODS:
            has = hasattr(rf24_cls, meth)
            ok &= has
            print("%s : RF24.%s()" % ("OK  " if has else "MISS", meth))
        others = sorted(m for m in dir(rf24_cls) if not m.startswith("_"))
        print("\nall public RF24 members:\n    %s" % ", ".join(others))

    if not ok:
        print("\n>>> Some names are MISSING - adjust hardware_radio.py to match.")
        return 1

    print("\nTrying a basic radio init (CE=GPIO%d, CSN=SPI%d)..."
          % (CE_PIN, CSN_PIN))
    try:
        radio = pyrf24.RF24(CE_PIN, CSN_PIN)
        if not radio.begin():
            print("FAIL  : begin() returned False (SPI enabled? ls /dev/spidev*)")
            return 1
        print("begin(): OK")
        print("isChipConnected():", radio.isChipConnected())
        radio.setAutoAck(False)
        radio.setDataRate(pyrf24.RF24_2MBPS)
        radio.disableCRC()
        radio.powerUp()
        radio.setChannel(76)          # 2476 MHz
        radio.startListening()
        time.sleep(0.005)
        print("testRPD() on ch 76:", radio.testRPD())
        radio.stopListening()
        radio.powerDown()
        print("\nRadio init + carrier-detect smoke test finished.")
        return 0
    except Exception as exc:
        print("FAIL  : %s: %s" % (type(exc).__name__, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
