#!/usr/bin/env python3
"""Headless 2.4 GHz spectrum scanner - live text bar graph in the terminal.

    python cli_scan.py --sim     # simulation
    python cli_scan.py --hw      # real nRF24L01 (Raspberry Pi)
    python cli_scan.py           # auto-detect
"""

import argparse
import os
import sys
import time

from hardware_radio import HARDWARE_HINTS, RadioError
from scanner import BASE_FREQ_MHZ, NUM_CHANNELS, ScannerThread, SpectrumData, create_radio

BLOCKS = " ▁▂▃▄▅▆▇█"
ASCII = " .:-=+*#%@"


def enable_ansi():
    """Try to enable ANSI escape codes (needed on Windows consoles)."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11, ENABLE_PROCESSED_OUTPUT|WRAP|VIRTUAL_TERMINAL = 7
        return bool(kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7))
    except Exception:
        return False


def sparkline(values, chars):
    hi = len(chars) - 1
    return "".join(chars[min(hi, int(v * (hi + 0.999) / 100.0))] for v in values)


def frame_lines(data, label, chars):
    act = data.activity()
    st = data.stats()
    half = NUM_CHANNELS // 2          # 63
    row1 = sparkline(act[:half], chars)
    row2 = sparkline(act[half:], chars)
    return [
        "  ch   0- 62 |%s|" % row1,
        "  ch  63-125 |%s|" % row2,
        " %5.1f sweeps/s | total %6d | busiest ch %3d (%d MHz) %5.1f%% | %s" % (
            st["sweeps_per_sec"], st["total_sweeps"],
            st["busiest_channel"], st["busiest_freq_mhz"],
            st["busiest_pct"], label),
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--sim", action="store_true", help="simulation backend")
    src.add_argument("--hw", action="store_true", help="nRF24L01 hardware backend")
    parser.add_argument("--window", type=int, default=100,
                        help="rolling window size in sweeps (default 100)")
    parser.add_argument("--interval", type=float, default=0.25,
                        help="redraw interval in seconds (default 0.25)")
    parser.add_argument("--seconds", type=float, default=0.0,
                        help="stop after N seconds (default: run until Ctrl+C)")
    parser.add_argument("--ascii", action="store_true",
                        help="use ASCII bars instead of unicode blocks")
    args = parser.parse_args(argv)

    mode = "hw" if args.hw else ("sim" if args.sim else "auto")
    try:
        radio, label, fallback_err = create_radio(mode)
    except RadioError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        print(HARDWARE_HINTS, file=sys.stderr)
        return 2
    if fallback_err is not None:
        print("note: hardware not available (%s) -> %s" % (fallback_err, label),
              file=sys.stderr)

    chars = ASCII if args.ascii else BLOCKS
    if not args.ascii:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            chars = ASCII

    data = SpectrumData(window=args.window)
    scanner = ScannerThread(radio, data)
    scanner.start()

    ansi = enable_ansi() and sys.stdout.isatty()
    print("2.4 GHz nRF24L01 spectrum  |  backend: %s  |  window: %d sweeps  |  2400-2525 MHz (1 MHz/ch)"
          % (label, args.window))
    print("bars: rolling-average carrier-detect hits per channel (0-100%)")

    t_end = time.monotonic() + args.seconds if args.seconds > 0 else None
    first = True
    try:
        while True:
            lines = frame_lines(data, label, chars)
            if ansi:
                if not first:
                    sys.stdout.write("\x1b[%dA" % len(lines))
                for line in lines:
                    sys.stdout.write("\x1b[2K%s\n" % line)
                sys.stdout.flush()
            else:
                print("\n".join(lines))
            first = False
            if t_end is not None and time.monotonic() >= t_end:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        scanner.stop()
        scanner.join(timeout=2.0)
        radio.close()
        print("stopped - %d sweeps total" % data.stats()["total_sweeps"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
