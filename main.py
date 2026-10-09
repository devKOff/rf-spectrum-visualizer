#!/usr/bin/env python3
"""nRF24L01 RF activity scanner.  Run:  python3 main.py   (or: python3 main.py --check)"""
import argparse
import sys
import time


def check():
    from nrf24_spectrum import config as cfg
    from nrf24_spectrum.scanner import REQUIRED_API, open_radio, sweep_once
    import pyrf24
    print("pyrf24 driver:", getattr(pyrf24, "RF24_DRIVER", "?"))
    print("API names present:", ", ".join(REQUIRED_API))
    radio = open_radio()
    print("Chip variant:", "nRF24L01+" if radio.is_plus_variant else "nRF24L01 (non-plus)")
    t0 = time.perf_counter()
    hits = sweep_once(radio, cfg.DEFAULT_DWELL_US / 1e6)
    dt = time.perf_counter() - t0
    active = [f"{cfg.BASE_MHZ + i}" for i, h in enumerate(hits) if h]
    print(f"One sweep of {cfg.NUM_CHANNELS} channels took {dt * 1000:.0f} ms")
    print("Channels with a hit (MHz):", ", ".join(active) if active else "none")
    radio.power = False
    return 0


def gui():
    import tkinter as tk
    from tkinter import messagebox
    from nrf24_spectrum import config as cfg
    from nrf24_spectrum.gui import App
    from nrf24_spectrum.scanner import open_radio
    sys.setswitchinterval(0.001)          # let the scanner thread run while Matplotlib draws
    root = tk.Tk()
    try:
        radio = open_radio()
    except Exception as exc:
        messagebox.showerror("Radio error", str(exc))
        return 1
    kind = "nRF24L01+" if radio.is_plus_variant else "nRF24L01 (non-plus)"
    App(root, radio, f"Radio: {kind}   CE=GPIO{cfg.CE_PIN}   SPI device index {cfg.CSN_PIN}")
    root.mainloop()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="headless self-test: verify API, do one sweep")
    sys.exit(check() if ap.parse_args().check else gui())
