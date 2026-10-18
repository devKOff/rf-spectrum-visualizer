# Hardware Check — Phase 1

Standalone hardware-verification scripts for the Raspberry Pi + nRF24L01+.
Run these **on the Pi** (not on the Windows dev machine). They do not use the
GUI and do not claim dBm or calibrated power values. The metric is **Activity %**
= (samples where RPD was true / total samples) x 100.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/check_radio.py` | Imports pyrf24, builds `RF24(25, 0)` (CE=GPIO25, CSN=CE0), calls `begin()`, reports PASS/FAIL and radio details. |
| `scripts/check_rpd.py`   | Scans chosen channels with `setChannel -> startListening -> ~200 us wait -> testRPD() -> stopListening`, prints per-channel RPD+ counts and Activity %. |

## Prerequisites (on the Pi)

```bash
# 1. Enable SPI
sudo raspi-config   # Interface Options -> SPI -> Enable
sudo reboot

# 2. Install system + Python dependencies
sudo apt update
sudo apt install -y python3-spidev python3-dev
pip install pyrf24

# 3. (Recommended) allow SPI access without sudo
sudo usermod -a -G spi $USER
# then log out and back in, or reboot
```

Wiring (fixed, do not change):

| nRF24L01+ | Raspberry Pi pin | Function |
|-----------|------------------|----------|
| VCC       | Pin 1            | 3.3V (NOT 5V) |
| GND       | Pin 9            | Ground |
| CE        | Pin 22           | GPIO 25 |
| CSN       | Pin 24           | GPIO 8 (SPI CE0) |
| SCK       | Pin 23           | GPIO 11 (SPI CLK) |
| MOSI      | Pin 19           | GPIO 10 (SPI MOSI) |
| MISO      | Pin 21           | GPIO 9 (SPI MISO) |
| IRQ       | —                | not used |

Place a **10 uF capacitor across VCC/GND at the module** to stabilize power.

## Exact commands to run

From the project root on the Pi:

```bash
# 1. Verify the radio chip responds
python scripts/check_radio.py

# 2. Measure RPD activity on the default channels (12, 37, 62, 100)
python scripts/check_rpd.py

# 2b. Custom channel list and sample count
python scripts/check_rpd.py --channels 12 37 62 100 --samples 200

# 2c. Quiet-channel-only check
python scripts/check_rpd.py --channels 100 110 120 --samples 100
```

## What PASS looks like

`check_radio.py` PASS example:

```
pyrf24 version: 0.6.0
Constructing RF24(ce_pin=25, csn_pin=0)
  (CE=GPIO number BCM; CSN=spidev device index, 0=/dev/spidev0.0=CE0=GPIO8)
PASS: nRF24L01+ chip is connected and responding.
  begin()            = True
  isChipConnected()  = True
  data rate          = 1 Mbps (1MBPS)
  PA level           = PA_LOW
  channel            = 2
  is PVariant (plus) = True
  Note: values above are raw register reads, not calibrated power
  measurements. The metric used by this project is Activity % ...
```

`check_rpd.py` PASS example:

```
Channel  Freq MHz   RPD+  Samples Activity %
----------------------------------------------
      12     2412     12      100      12.0%
      37     2437      5      100       5.0%
      62     2462     90      100      90.0%  <- Heavy Load
     100     2500      0      100       0.0%
----------------------------------------------
Activity % = (RPD true samples / total samples) x 100. RPD trips at about
-64 dBm (yes/no flag only - no calibrated power).
```

Interpretation:
* `is PVariant (plus) = True` confirms an nRF24L01+ (not the older nRF24L01).
* Channels 12/37/62 correspond to Wi-Fi channels 1/6/11 and often show higher
  Activity %; a quiet channel such as 100 should read near 0% unless there is
  local 2.4 GHz traffic.
* `RPD+` is the count of samples where the RPD flag tripped; `Activity %` is
  `(RPD+ / Samples) x 100`.

## Troubleshooting table

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `pyrf24 is not installed` | pyrf24 missing | `pip install pyrf24` (needs `python3-dev`, `cmake` if building from source) |
| `RF24 constructor raised ... SPI ...` / `FileNotFoundError` | SPI not enabled | `sudo raspi-config` → Interface Options → SPI → Enable → reboot; `ls /dev/spidev*` should show `/dev/spidev0.0` |
| `radio.begin() returned False` | Wiring, power, or wrong pins | Re-check CE=GPIO25/pin22, CSN=CE0/pin24, SCK=GPIO11, MOSI=GPIO10, MISO=GPIO9; VCC=3.3V not 5V; 10 uF cap across VCC/GND |
| Permission denied on `/dev/spidev0.0` | User not in `spi` group | `sudo usermod -a -G spi $USER`, log out/in or reboot |
| Always 0% activity | Radio in TX/idle, no settle, or truly quiet channel | Confirm `startListening()` is called before `testRPD()`; try a known-busy channel (12/37/62 near Wi-Fi); increase `--samples` |
| Always 100% activity | Radio never leaves RX, strong local interferer, or CE stuck high | Check CE wiring; move away from 2.4 GHz sources; confirm `stopListening()` is called between samples |
| `testRPD` errors mid-scan | SPI noise / power dip | Add/better decoupling cap; keep wires short; reduce SPI speed if supported |
| `isChipConnected()` missing | pyrf24 0.6.0 does not document it | Script falls back to `begin()` (chip detection). Run `python -c "import pyrf24; help(pyrf24.RF24)"` on the Pi to confirm available methods |

## Pin-numbering convention used (and why)

`RF24(ce_pin=25, csn_pin=0)`:

* **CE** = GPIO number (BCM) = `25` → wiring pin 22.
* **CSN** = spidev device index = `0` → `/dev/spidev0.0` = SPI CE0 → wiring pin 24 = GPIO 8.

This matches the project wiring spec (CE=GPIO25, CSN=GPIO8/CE0). If `begin()`
returns False, run `python -c "import pyrf24; help(pyrf24.RF24)"` on the Pi and
paste the constructor signature before proceeding to Phase 2.

## Safety / scope

* These scripts only read RPD; they never transmit and never modify the GUI or
  existing app logic.
* No dBm or calibrated-power claims are made anywhere.
* pyrf24 is imported only inside functions, so importing these files on a
  machine without pyrf24 (or in pytest) does not fail.
