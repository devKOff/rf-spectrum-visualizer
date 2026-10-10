# 2.4 GHz RF Activity / Spectrum Visualizer

A small spectrum-activity visualizer for the 2.4 GHz ISM band built around an
**nRF24L01+** module on a Raspberry Pi. It sweeps channels 0-125
(2400-2525 MHz, 1 MHz steps) and shows how busy each channel is, in percent.

The nRF24 cannot measure real power: its **RPD (Received Power Detector)** bit
only says "energy above ≈ -64 dBm seen in the last listening window". This tool
turns many RPD samples into an activity percentage per channel - great for
spotting Wi-Fi, Bluetooth and other 2.4 GHz devices.

Runs with two swappable backends:

* `--hw` - real nRF24L01 via [pyrf24](https://github.com/nRF24/pyrf24) (Raspberry Pi)
* `--sim` - built-in simulation (Wi-Fi-like blocks on ch 1/6/11, a bursty
  hopping narrow signal, noise floor)
* default: **auto** (tries hardware, falls back to simulation; the GUI shows a
  visible `SIMULATION` / `HARDWARE` badge)

## Features (GUI)

* Live spectrum plot (activity % vs frequency), optional peak-hold line
* Scrolling waterfall view (200 rows of history, colormap)
* Wi-Fi channels 1-13 overlaid on the spectrum
* Start / Stop / Clear, rolling-window size, CSV export, PNG screenshot
* Info bar: sweeps/sec, total sweeps, busiest channel (number + MHz), status
* Hover readout: channel, frequency, activity %

## Project layout

```
app.py                    Tkinter + Matplotlib GUI (entry point)
scanner.py                scan thread + thread-safe SpectrumData (backend-agnostic)
hardware_radio.py         nRF24L01 backend (all pyrf24 calls isolated here)
sim_radio.py              simulation backend
cli_scan.py               headless text bar-graph scanner
tools/check_pyrf24_api.py run on the Pi to verify the pyrf24 API + radio init
requirements.txt
```

## Install on a PC (simulation only)

```
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
python cli_scan.py --sim
python app.py --sim
```

(`cli_scan.py` needs only the standard library; the GUI needs numpy + matplotlib.)

## Install on the Raspberry Pi (Raspberry Pi OS, Python 3)

```
sudo apt update
sudo apt install -y python3-tk python3-matplotlib python3-numpy python3-pip
pip install pyrf24              # tested target: pyrf24==0.6.0
```

Enable SPI if not already done:

```
sudo raspi-config   # Interface Options -> SPI -> Yes
ls /dev/spidev*     # should list /dev/spidev0.0 and /dev/spidev0.1
```

### Wiring (nRF24L01 -> Pi 3B+)

| nRF24 pin | Pi pin (BCM) | Pi header |
|-----------|--------------|-----------|
| VCC       | 3.3 V        | pin 1/17  |
| GND       | GND          | pin 6/9/… |
| CE        | GPIO25       | pin 22    |
| CSN       | GPIO8 (CE0)  | pin 24    |
| SCK       | GPIO11       | pin 23    |
| MOSI      | GPIO10       | pin 19    |
| MISO      | GPIO9        | pin 21    |
| IRQ       | not used     | -         |

Power from **3.3 V only** (not 5 V) with a **10 uF capacitor across VCC/GND** at
the module; keep jumper leads short.

## Usage

```
python app.py            # auto-detect (hardware if found, else simulation)
python app.py --sim      # force simulation
python app.py --hw       # force hardware

python cli_scan.py --sim                # headless sim scan
python cli_scan.py --hw                 # headless hardware scan
python cli_scan.py --hw --window 50     # rolling window of 50 sweeps
python cli_scan.py --seconds 10         # run 10 s then exit
python cli_scan.py --ascii              # ASCII bars (no unicode)
```

## First run on the Pi - checklist

1. `python tools/check_pyrf24_api.py`
   Verifies every pyrf24 call used by `hardware_radio.py` (all are marked
   `# VERIFY ON PI`) and tries a basic init + carrier-detect smoke test.
2. `python cli_scan.py --hw`
   Confirms sweeping works headless. Wi-Fi traffic should light up the
   channels around 2412 / 2437 / 2462 MHz.
3. `python app.py --hw`
   The full GUI. The badge in the top right must read `HARDWARE`.

If step 1 or 2 fails, check: SPI enabled (`/dev/spidev*` exists), wiring per the
table above, 3.3 V power with the 10 uF cap, short leads.

## Limitations

* **RPD is a one-bit threshold detector** (triggers around -64 dBm). The plots
  show hit percentage, *not* dBm power levels.
* Receiver bandwidth is only ~1-2 MHz (2 Mbps mode), so wide signals appear
  spread over several adjacent 1 MHz channels.
* It cannot demodulate or decode anything: no SSIDs, no packet contents - only
  "was energy present on this channel during the sample window".
* SPI overhead limits sweep rate; expect tens of sweeps per second on a Pi 3B+.
* Channels 0-125 cover 2400-2525 MHz in 1 MHz steps.

## Note on the hardware API

All pyrf24 calls live in `hardware_radio.py` and are tagged `# VERIFY ON PI`
because the exact 0.6.0 API could not be confirmed on the development machine.
If `tools/check_pyrf24_api.py` reports a `MISS`, adjust the matching line(s) in
`hardware_radio.py` - no other file needs to change.
