# rf_spectrum_visualizer

Standalone Raspberry Pi + nRF24L01+ 2.4 GHz RF activity visualizer, built
completely from scratch.

## What it is

A Tkinter + Matplotlib desktop app for the Raspberry Pi 3B+ that scans nRF24L01+
channels 0-125 (2400-2525 MHz) and shows RF activity. Pages:

1. **Live Spectrum** - per-channel Activity % bar chart + channel table.
2. **Start Analysis** - multi-cycle scan, ranking, recommendations, CSV export.
3. **Blocker** - software-level channel exclusion (saved to disk, restored on restart).

## What it is NOT (read this)

* **NOT an SDR.** The nRF24L01+ is a narrowband transceiver, not a spectrum
  analyzer. It reports one bit per channel: the RPD (Received Power Detector)
  flag, which trips at roughly -64 dBm.
* **Never claim dBm or calibrated power.** The only metric is
  **Activity % = (samples with RPD true / total samples) x 100**.
* **The Blocker does NOT physically block RF** or prevent transmissions. It only
  excludes a channel from Analysis recommendations; it stays visible in Live
  Spectrum.

## Hardware (fixed wiring)

| nRF24L01+ | Pi pin | Function |
|-----------|--------|----------|
| VCC | Pin 1 | 3.3V (NOT 5V) |
| GND | Pin 9 | Ground |
| CE | Pin 22 | GPIO 25 |
| CSN | Pin 24 | GPIO 8 (SPI CE0) |
| SCK | Pin 23 | GPIO 11 |
| MOSI | Pin 19 | GPIO 10 |
| MISO | Pin 21 | GPIO 9 |
| IRQ | - | unused |

Place a 10 uF capacitor across VCC/GND at the module.

## Setup on the Raspberry Pi

```bash
# 1. Enable SPI
sudo raspi-config   # Interface Options -> SPI -> Enable
sudo reboot

# 2. Install dependencies
sudo apt update
sudo apt install -y python3-spidev python3-dev python3-tk python3-pip
pip install pyrf24 matplotlib

# 3. (Recommended) SPI without sudo
sudo usermod -a -G spi $USER
# log out and back in
```

## Run

```bash
# From the project root
source .venv/bin/activate          # if using a venv
export PYTHONPATH="src"
python scripts/run_gui.py          # Phase 6: launch the GUI
python scripts/check_radio.py      # Phase 1: verify the radio
python scripts/check_rpd.py        # Phase 1: RPD activity on sample channels
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap (phases)

1. Scaffold + hardware check scripts (check_radio.py, check_rpd.py) — DONE
2. Scan backend (SimBackend / HardwareBackend, per-channel stats) — DONE
3. GUI shell + Live Spectrum page — DONE
4. Start Analysis page + CSV export — DONE
5. Blocker page + JSON persistence — DONE
6. Waterfall, scan-rate readout, Clear button, docs, launch script/desktop shortcut — DONE

## Launch script & desktop shortcut

* `scripts/run_gui.py` — launches the GUI with optional file logging
  (`rf_spectrum_visualizer.log`).
* `scripts/rf_spectrum_visualizer.desktop` — desktop shortcut; copy to
  `~/.local/share/applications/` or `~/.config/autostart/` for autostart.
* See `docs/phase6.md` for full launch/autostart/logging instructions.

## Limitations

* Developed and tested on a non-Pi dev machine. Hardware (pyrf24, radio, GPIO)
  can only be tested by you on the Raspberry Pi 3B+.
* pyrf24 0.6.0 method names/constructor args are assumed from documentation;
  verify on the Pi with `python -c "import pyrf24; help(pyrf24.RF24)"` before
  Phase 2.
