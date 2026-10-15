# HOW TO USE GUIDE - RF Spectrum Visualizer

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Requirements](#2-system-requirements)
3. [Installation](#3-installation)
4. [Launching the Application](#4-launching-the-application)
5. [UI Navigation](#5-ui-navigation)
6. [Spectrum Section](#6-spectrum-section)
7. [Analysis Section](#7-analysis-section)
8. [Blocker Section](#8-blocker-section)
9. [Hardware Setup](#9-hardware-setup)
10. [Simulation Mode](#10-simulation-mode)
11. [Settings & Configuration](#11-settings--configuration)
12. [Data Export](#12-data-export)
13. [Automated Testing](#13-automated-testing)
14. [Troubleshooting](#14-troubleshooting)
15. [Limitations & Safety](#15-limitations--safety)
16. [Developer Guide](#16-developer-guide)

---

## 1. Project Overview

RF Spectrum Visualizer is a unified desktop application for monitoring the 2.4 GHz ISM band using the nRF24L01+ transceiver. It integrates two predecessor projects:

- **V3 (Spectrum Display)**: Live spectrum bars, waterfall, channel activity table
- **V6 (Analysis & Blocking)**: Channel rankings, avoidance recommendations, persistent JSON blocklist

### Three-Section Architecture

| Section | Purpose | Key Features |
|---------|---------|--------------|
| **Spectrum** | Real-time RF visualization | 126-channel bar graph, waterfall, activity table |
| **Analysis** | Channel assessment & recommendations | Summary cards, rankings, least-active eligible channels |
| **Blocker** | Software channel blocking | Persistent JSON blocklist, manual entry, eligibility preview |

### Key Concepts

- **Channels**: 126 channels numbered 0-125, frequency = 2400 + channel MHz
- **RPD (Received Power Detector)**: Binary indicator of energy above threshold
- **Activity Percentage**: (RPD positive samples / valid samples) × 100%
- **Channel Status**: Clear (≤24%), Moderate (25-49%), Busy (50-74%), Heavy Load (≥75%)
- **Blocked in Software**: Application-level exclusion only - **no physical RF blocking**

---

## 2. System Requirements

### Minimum Requirements
- Python 3.9+
- Tkinter (usually included with Python)
- matplotlib 3.7+
- numpy 1.24+

### For Hardware Mode (Raspberry Pi 3B+)
- Raspberry Pi 3B+ or later
- nRF24L01+ module
- SPI enabled (`sudo raspi-config`)
- pyrf24 library (`pip install pyrf24`)
- GPIO access (user in `gpio` group)

### Operating Systems
- Linux (Raspberry Pi OS, Ubuntu, Debian)
- Windows 10/11 (simulation mode only)
- macOS (simulation mode only)

---

## 3. Installation

### 1. Clone or Copy the Project

```bash
cd /path/to/workshop
# The rf_spectrum_visualizer/ directory should already exist
```

### 2. Install Python Dependencies

```bash
cd rf_spectrum_visualizer
pip install -r requirements.txt
```

### 3. (Optional) Install Hardware Backend

```bash
# On Raspberry Pi only
pip install pyrf24
sudo usermod -a -G gpio $USER
# Log out and back in for group change to take effect
```

### 4. Verify Installation

```bash
python -c "import rf_spectrum_visualizer; print('Import OK')"
```

---

## 4. Launching the Application

### Default (Simulation Mode)

```bash
cd rf_spectrum_visualizer
python main.py
```

### Hardware Mode

```bash
python main.py --hardware
```

### With Custom Configuration

```bash
python main.py --config /path/to/custom_config.json
```

### With Debug Logging

```bash
python main.py --debug
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--sim` | Force simulation backend (default) |
| `--hardware` | Force hardware backend |
| `--config PATH` | Load configuration from JSON file |
| `--debug` | Enable DEBUG level logging |
| `--version` | Show version and exit |

---

## 5. UI Navigation

### Main Window Layout

```
┌─────────────────────────────────────────────────────────────┐
│ File  View  Tools  Help                          [Menu Bar] │
├─────────────────────────────────────────────────────────────┤
│ Backend: [sim ▼] │ Start Scanning │ Stop │ Ch: [0]-[125]  │
│ Window: [1.0]s   │ Interval: [10]ms │ Export All/JSON/CSV/PNG│
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │  Spectrum    │ │  Analysis    │ │  Blocker     │  ← Tabs │
│  │              │ │              │ │              │         │
│  │  [Content]   │ │  [Content]   │ │  [Content]   │         │
│  │              │ │              │ │              │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
├─────────────────────────────────────────────────────────────┤
│ Status: Scanning... (SIM)                    [Status Bar]  │
└─────────────────────────────────────────────────────────────┘
```

### Toolbar Controls

| Control | Function |
|---------|----------|
| **Backend** | Switch between `sim` and `hardware` (stop scanning first) |
| **Start Scanning** | Begin continuous channel scanning |
| **Stop** | Halt scanning |
| **Channels** | Set start/end channel range (0-125) |
| **Window (s)** | Measurement window per channel (0.1-10.0s) |
| **Interval (ms)** | Sampling interval between RPD reads (1-1000ms) |
| **Export Buttons** | Quick export to JSON, CSV, PNG |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+E` | Export all formats |
| `Ctrl+J` | Export JSON |
| `Ctrl+Shift+C` | Export CSV |
| `Ctrl+Q` | Quit application |

---

## 6. Spectrum Section

The Spectrum tab provides real-time RF visualization across three panes.

### Channel Activity Table

| Column | Description |
|--------|-------------|
| **Ch** | Channel number (0-125) |
| **Freq (MHz)** | Frequency = 2400 + channel |
| **Activity** | Visual bar (█ = active, ░ = inactive) |
| **%** | Activity percentage |
| **Status** | Clear/Moderate/Busy/Heavy Load/INSUFFICIENT DATA/SENSOR_ERROR |
| **Samples** | Valid RPD samples collected |
| **RPD+** | Positive RPD detections |
| **Data OK** | Yes/No (sufficient samples) |
| **Eligible** | Yes/No for channel avoidance |
| **Blocked** | Yes/No (software blocked) |

**Table Features:**
- Click column headers to sort
- Search filter (matches channel or frequency)
- Status filter dropdown
- Color coding: Green=Clear, Yellow=Moderate, Orange=Busy, Red=Heavy, Red bg=Blocked, Blue=Eligible

### Live Spectrum Graph

- **X-axis**: Channel number (0-125)
- **Y-axis**: Activity percentage (0-100%)
- **Bars**: Color-coded by status
- **Blue dashed lines**: WiFi channels 1 (Ch 12), 6 (Ch 37), 11 (Ch 62)
- **Horizontal dotted lines**: Threshold boundaries (Clear/Moderate/Busy)

### Waterfall Display

- **X-axis**: Channel number
- **Y-axis**: Time (seconds ago, most recent at bottom)
- **Color**: Black → Blue → Cyan → Yellow → Red (0-100% activity)
- **Colorbar**: Activity percentage scale

### Alerts & Diagnostics Panel

Real-time log of:
- Scanner start/stop events
- Channel alerts (persistent high activity)
- Hardware errors
- Export confirmations

---

## 7. Analysis Section

The Analysis tab provides channel assessment and recommendations.

### Summary Cards (Top)

Eight cards showing:
1. **Total Channels** - Channels in configured range
2. **Eligible** - Channels available for use
3. **Blocked** - Software-blocked channels
4. **Clear** - Channels with ≤24% activity
5. **Moderate** - Channels with 25-49% activity
6. **Busy/Heavy** - Channels with ≥50% activity
7. **Insufficient Data** - Channels needing more samples
8. **Sensor Errors** - Channels with read errors

### Channel Rankings Table

All channels ranked by activity (lowest first):

| Column | Description |
|--------|-------------|
| **Rank** | Position in sorted list |
| **Ch** | Channel number |
| **Freq (MHz)** | Channel frequency |
| **Activity (%)** | Current activity percentage |
| **Status** | Classification |
| **Eligible** | Yes/No for avoidance |
| **Blocked** | Yes/No |
| **Reason** | Eligibility reason |
| **Peak (%)** | Highest activity seen |

**Filter Options:**
- All channels
- Eligible Only
- Blocked Only
- High Activity (≥50%)

### Recommendations Panel

Shows top 10 least-active eligible channels:

```
RECOMMENDED CHANNELS (lowest activity first):
============================================================
 1. Ch  12 (2412 MHz)  Current: 2.3%  Peak: 5.1%  Status: Clear
 2. Ch  37 (2437 MHz)  Current: 3.1%  Peak: 4.8%  Status: Clear
 3. Ch  62 (2462 MHz)  Current: 4.5%  Peak: 6.2%  Status: Clear
 ...
```

Blocked channels are listed at the bottom with note: "These channels are excluded from recommendations."

---

## 8. Blocker Section

The Blocker tab manages the persistent JSON blocklist.

### Blocklist Controls

| Control | Function |
|---------|----------|
| **Channel** | Enter channel number (e.g., `122`, `Ch 122`, `2522 MHz`) |
| **Block Channel** | Add channel to blocklist with reason |
| **Unblock Channel** | Remove channel from blocklist |
| **Check Channel** | Query block status |
| **Reason** | Text description for block entry |
| **Refresh Blocklist** | Reload from disk |
| **Clear All Blocks** | Remove all entries (with confirmation) |
| **Export Blocklist** | Save blocklist to JSON file |
| **Import Blocklist** | Load blocklist from JSON file |

### Blocked Channels Table

Shows all currently blocked channels:

| Column | Description |
|--------|-------------|
| **Ch** | Channel number |
| **Freq (MHz)** | Frequency (auto-calculated as 2400 + channel) |
| **Blocked At (UTC)** | ISO timestamp when blocked |
| **Reason** | User-provided reason |

### Channel Eligibility Preview

Real-time preview of how current scan data interacts with blocklist:

- Shows eligibility assessment for all channels
- Blocked channels marked with red background
- Updates automatically when scanning or blocklist changes

### Information Panel

**Critical safety notice displayed permanently:**

> ⚠ **SOFTWARE CHANNEL BLOCKING**
> 
> "BLOCKED IN SOFTWARE" prevents the **application** from selecting or recommending these channels. It does **NOT**:
> - Physically jam or block radio frequencies
> - Disrupt external devices or communications
> - Transmit any blocking signals
> - Affect the nRF24L01+ hardware operation

---

## 9. Hardware Setup

### Raspberry Pi 3B+ Wiring

| nRF24L01+ Pin | Raspberry Pi GPIO | Physical Pin |
|---------------|-------------------|--------------|
| VCC | 3.3V | 1 or 17 |
| GND | GND | 6, 9, 14, 20, 25, 30, 34, 39 |
| CE | GPIO 25 | 22 |
| CSN | GPIO 8 (SPI CE0) | 24 |
| SCK | GPIO 11 | 23 |
| MOSI | GPIO 10 | 19 |
| MISO | GPIO 9 | 21 |

### Enable SPI

```bash
sudo raspi-config
# Navigate to: Interface Options → SPI → Yes → OK → Finish
sudo reboot
```

### Verify SPI

```bash
ls /dev/spidev*
# Should show: /dev/spidev0.0  /dev/spidev0.1
```

### Test Hardware

From the GUI: Tools → Hardware Diagnostic

Or from command line:
```bash
python -c "
from radio.hardware_radio import check_hardware_availability
import json
print(json.dumps(check_hardware_availability(), indent=2))
"
```

### Common Hardware Issues

| Issue | Solution |
|-------|----------|
| "pyrf24 not installed" | `pip install pyrf24` |
| "SPI device not found" | Enable SPI in raspi-config, reboot |
| "GPIO access denied" | Add user to gpio group, logout/login |
| "nRF24L01+ not responding" | Check wiring, try 3.3V not 5V, add capacitor |

---

## 10. Simulation Mode

Simulation mode requires no hardware and provides deterministic, repeatable test scenarios.

### Running Simulations

1. Select **sim** backend in toolbar
2. Click **Start Scanning** for continuous scanning
3. Or: Tools → Run Simulation Scenario for one-shot scenarios

### Available Scenarios

| Scenario | Use Case |
|----------|----------|
| **quiet** | Baseline testing, all channels clear |
| **single_busy** | Test single interferer avoidance |
| **spikes** | Test transient interference handling |
| **channel_122_high** | Test blocking specific channel (122) |
| **channel_122_low** | Test channel 122 as clear candidate |
| **wifi_like** | Test WiFi coexistence (channels 12, 37, 62) |
| **frequency_hopping** | Test FHSS pattern detection |
| **sensor_errors** | Test error handling |
| **mixed** | Realistic environment (default) |
| **burst** | Test burst interference |
| **high_activity** | Test congested environment |

### Deterministic Behavior

- Set **Simulation Seed** in Tools → Settings for reproducible results
- Same seed = identical scan sequences
- Useful for regression testing

### Custom Scenarios

Create custom channel models programmatically:

```python
from radio.sim_radio import SimRadio, ChannelModel, ScenarioType
from config import ChannelConfig, ScanConfig

# Custom model for channel 50 at 90% activity
models = {50: ChannelModel(channel=50, base_probability=0.9, scenario=ScenarioType.HIGH_ACTIVITY)}
radio = SimRadio(ChannelConfig(), ScanConfig(), channel_models=models)
```

---

## 11. Settings & Configuration

### Access Settings

Tools → Settings opens the configuration dialog with three tabs:

### Thresholds Tab

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| Clear max | 24% | 0-100 | Max activity for "Clear" |
| Moderate max | 49% | 0-100 | Max activity for "Moderate" |
| Busy max | 74% | 0-100 | Max activity for "Busy" |
| Heavy min | 75% | 0-100 | Min activity for "Heavy Load" |

*Must maintain: Clear < Moderate < Busy < Heavy*

### Mitigation Tab

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| Persistent threshold | 75% | 0-100 | Activity % for persistent detection |
| Hysteresis | 5% | 0-50 | Margin below threshold for eligibility |
| Armed | False | - | Enable/disable mitigation engine |

### Hardware Tab

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| CE Pin | 25 | 0-27 | GPIO for Chip Enable |
| CSN Pin | 0 | 0-1 | SPI Chip Select (0=CE0, 1=CE1) |
| SPI Speed | 4,000,000 | 100k-16M | SPI clock frequency |

### Configuration Persistence

- Settings saved to `rf_spectrum_visualizer/config.json`
- Blocklist saved to `rf_spectrum_visualizer/blocklist.json`
- Logs written to `rf_spectrum_visualizer/logs/countermeasures.jsonl`
- Exports saved to `rf_spectrum_visualizer/exports/`

---

## 12. Data Export

### Export Options (File Menu & Toolbar)

| Export | Description | File Format |
|--------|-------------|-------------|
| **Export All Formats** | Complete report package | Multiple files |
| **Export JSON** | Full report with metadata | `.json` |
| **Export CSV** | Channel data table | `.csv` |
| **Export PNG (Spectrum)** | Live spectrum graph | `.png` |
| **Export PNG (Waterfall)** | Waterfall display | `.png` |

### Export All Formats

Creates timestamped files in `exports/`:
```
full_report_sim_20240115_143022.json
full_report_sim_20240115_143022_channels.csv
full_report_sim_20240115_143022_blocklist.json
full_report_sim_20240115_143022_blocklist.csv
full_report_sim_20240115_143022_waterfall.csv
```

### JSON Report Structure

```json
{
  "metadata": { "backend": "sim", "scan_count": 42, ... },
  "blocklist": { "blocked_channels": [122], "entries": [...] },
  "channel_assessments": [ { "channel": 0, "eligible": true, ... }, ... ],
  "recommendations": [ { "channel": 12, "activity_percentage": 2.3, ... }, ... ],
  "summary": { "total_channels": 126, "eligible_channels": 89, ... }
}
```

### CSV Columns

| Column | Description |
|--------|-------------|
| channel | Channel number |
| frequency_mhz | Frequency in MHz |
| activity_percentage | Current activity % |
| status | Clear/Moderate/Busy/Heavy/INSUFFICIENT DATA/SENSOR_ERROR |
| data_sufficient | true/false |
| valid_samples | Number of valid RPD samples |
| rpd_positive | RPD detections |
| rpd_negative | No signal detections |
| eligible | true/false |
| eligibility_reason | eligible/blocked/insufficient_data/sensor_error/high_activity/persistent_high_activity |
| blocked | true/false |
| blocked_at | ISO timestamp if blocked |
| block_reason | Reason if blocked |

---

## 13. Automated Testing

### Run All Tests

```bash
cd rf_spectrum_visualizer
pytest tests/ -v
```

### Run Specific Module

```bash
pytest tests/test_blocklist.py -v
pytest tests/test_selector.py -v
pytest tests/test_scanner.py -v
pytest tests/test_exports.py -v
pytest tests/test_channel_utils.py -v
```

### With Coverage

```bash
pytest tests/ --cov=rf_spectrum_visualizer --cov-report=html --cov-report=term
```

### Test Categories

| Test Module | Coverage |
|-------------|----------|
| `test_channel_utils.py` | Channel conversion, validation, formatting, parsing, WiFi overlap |
| `test_blocklist.py` | Block/unblock, persistence, import/export, corruption recovery |
| `test_selector.py` | Eligibility assessment, recommendations, ranking, peak tracking, hysteresis |
| `test_scanner.py` | ScannerThread lifecycle, callbacks, SpectrumData storage, waterfall |
| `test_exports.py` | JSON/CSV/PNG export, report generation, summary statistics |

### Expected Test Results

All tests should pass. Typical output:
```
tests/test_channel_utils.py ........... [ 12%]
tests/test_blocklist.py .............. [ 25%]
tests/test_selector.py .............. [ 37%]
tests/test_scanner.py ................ [ 50%]
tests/test_exports.py ................ [ 62%]
========== 31 passed in 2.34s ==========
```

---

## 14. Troubleshooting

### Application Won't Start

| Symptom | Solution |
|---------|----------|
| `ModuleNotFoundError: matplotlib` | `pip install matplotlib numpy` |
| `ModuleNotFoundError: tkinter` | Install `python3-tk` (Linux) or reinstall Python with Tkinter |
| `ImportError: rf_spectrum_visualizer` | Run from parent directory, check PYTHONPATH |

### Scanning Issues

| Symptom | Solution |
|---------|----------|
| "Hardware Unavailable" | Check pyrf24 install, SPI enabled, wiring |
| No data updating | Click Stop then Start, check channel range |
| All channels "INSUFFICIENT DATA" | Increase measurement window, decrease interval |
| Scanner crashes | Check logs in `logs/countermeasures.jsonl` |

### Blocklist Issues

| Symptom | Solution |
|---------|----------|
| Blocklist not persisting | Check write permissions to `rf_spectrum_visualizer/` |
| "Corrupted blocklist file" | Backup `.corrupted.*.bak` file is created, delete `blocklist.json` to reset |
| Import fails | Ensure JSON has `blocklist` array or is an array |

### Performance Issues

| Symptom | Solution |
|---------|----------|
| UI lagging | Increase refresh interval in Settings (default 500ms) |
| High CPU | Reduce channel range, increase measurement window |
| Memory growth | Click View → Clear History periodically |

### Log Analysis

```bash
# View recent logs
tail -f rf_spectrum_visualizer/logs/countermeasures.jsonl

# Filter for errors
grep '"level": "ERROR"' rf_spectrum_visualizer/logs/countermeasures.jsonl

# Filter for specific channel
grep '"channel": 122' rf_spectrum_visualizer/logs/countermeasures.jsonl
```

---

## 15. Limitations & Safety

### Technical Limitations

| Limitation | Impact |
|------------|--------|
| **Narrowband transceiver** | nRF24L01+ RPD is not calibrated power; relative only |
| **Sequential scanning** | Channels scanned one at a time (~1s per channel default) |
| **No frequency sync** | Cannot synchronize with external hopping patterns |
| **Single antenna** | No direction finding or beamforming |
| **Simulation ≠ Reality** | Deterministic models don't capture real RF complexity |

### Safety Notice (Critical)

> **⚠ "BLOCKED IN SOFTWARE" MEANS SOFTWARE-LEVEL ONLY**
> 
> When a channel shows **"BLOCKED IN SOFTWARE"**:
> - ✅ The application will **not recommend** this channel
> - ✅ The application will **not auto-select** this channel
> - ✅ The channel appears **red** in Spectrum and Analysis views
> - ❌ **NO** radio jamming or transmission occurs
> - ❌ **NO** physical RF blocking or interference
> - ❌ **NO** effect on other devices using that frequency
> - ❌ **NO** hardware-level blocking on the nRF24L01+
> 
> This is purely a **configuration preference** within this application.

### Legal Compliance

- This application **only receives** (passive scanning via RPD)
- No transmission capability in this software
- Comply with local regulations for 2.4 GHz ISM band use
- nRF24L01+ hardware must be configured per regional requirements

---

## 16. Developer Guide

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                               │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      MainWindow                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │SpectrumPage │  │AnalysisPage │  │ BlockerPage │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
└─────────┼────────────────┼────────────────┼──────────────────┘
          ▼                ▼                ▼
    ┌─────────────────────────────────────────────┐
    │           Shared Services                   │
    │  DataService │ PersistenceService           │
    └────────────────────┬────────────────────────┘
                         ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │   Radio    │  │  Scanner   │  │  Analysis  │
    │  (Base)    │  │  Engine    │  │  (Selector)│
    │  ┌──────┐  │  │            │  │            │
    │  │ Sim  │  │  │ ScannerThread │            │
    │  │HW    │  │  │ SpectrumData │            │
    │  └──────┘  │  └────────────┘  └────────────┘
    └────────────┘         ▼
                    ┌────────────┐
                    │ Mitigation │
                    │ (Blocklist)│
                    └────────────┘
```

### Adding a New Radio Backend

1. Subclass `radio.base_radio.BaseRadio`
2. Implement all abstract methods:
   - `initialize()`, `is_initialized()`
   - `set_channel()`, `get_channel()`
   - `read_rpd()`, `scan_channel()`
   - `cleanup()`
3. Register in `radio/__init__.py`
4. Update `ScannerThread._create_radio()`

### Adding a New Simulation Scenario

1. Add entry to `ScenarioType` enum in `radio/sim_radio.py`
2. Add scenario config to `SimRadio.SCENARIOS` dict
3. Handle in `SimRadio._create_models()`
4. Add case in `ChannelModel.get_rpd_probability()`

### Adding a New Export Format

1. Add method to `ReportGenerator` in `exports/report_generator.py`
2. Update `export_all_formats()` to include new format
3. Add UI button in `MainWindow._create_toolbar()` or menu

### Running Type Checks

```bash
mypy rf_spectrum_visualizer/
```

### Code Style

- Follow PEP 8
- Type hints for all public functions
- Docstrings for all classes and public methods
- No print statements - use logging
- Thread-safe with locks for shared state

### Key Extension Points

| Area | Extension Method |
|------|------------------|
| New radio backend | Subclass `BaseRadio` |
| New scenario | Add to `ScenarioType` + `SCENARIOS` |
| New export | Add to `ReportGenerator` |
| New analysis | Extend `ChannelSelector` |
| New UI tab | Add to `MainWindow._create_notebook()` |
| New config option | Add to `AppConfig` dataclass |

---

## Appendix: Channel Reference

### nRF24L01+ Channels ↔ Frequencies

| Channel | Frequency | Notes |
|---------|-----------|-------|
| 0 | 2400 MHz | Band start |
| 12 | 2412 MHz | **WiFi Channel 1** |
| 37 | 2437 MHz | **WiFi Channel 6** |
| 62 | 2462 MHz | **WiFi Channel 11** |
| 76-78 | 2476-2478 MHz | Common nRF24 default channels |
| 122 | 2522 MHz | Example blocked channel |
| 125 | 2525 MHz | Band end |

### WiFi Channel Overlap (2.4 GHz)

| WiFi Ch | Frequency | nRF Ch | Overlap |
|---------|-----------|--------|---------|
| 1 | 2412 | 12 | Center |
| 2 | 2417 | 17 | Adjacent |
| 3 | 2422 | 22 | Adjacent |
| 4 | 2427 | 27 | Adjacent |
| 5 | 2432 | 32 | Adjacent |
| 6 | 2437 | 37 | **Center** |
| 7 | 2442 | 42 | Adjacent |
| 8 | 2447 | 47 | Adjacent |
| 9 | 2452 | 52 | Adjacent |
| 10 | 2457 | 57 | Adjacent |
| 11 | 2462 | 62 | **Center** |

---

*Generated for RF Spectrum Visualizer v1.0.0*
*Last Updated: October 2026*