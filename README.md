# RF Spectrum Visualizer

A unified desktop application for 2.4 GHz ISM band spectrum analysis, channel avoidance, and software channel blocking. Integrates V3 (spectrum display) and V6 (analysis, blocking, channel avoidance) into a single robust, fully tested application.

## Features

### Three Main Sections

| Section | Description |
|---------|-------------|
| **Spectrum** | Live spectrum bar graph, waterfall display, and channel activity table with 126 channels (0-125) |
| **Analysis** | Summary cards, channel rankings, least-active eligible channel recommendations, data quality indicators |
| **Blocker** | Persistent JSON blocklist management, manual channel blocking (e.g., channel 122 = 2522 MHz), software-only blocking status |

### Core Capabilities

- **126-Channel Scanning**: Full 2.4 GHz ISM band coverage (channels 0-125, frequency = 2400 + channel MHz)
- **Dual Backend**: Deterministic simulation (offline testing) + hardware (Raspberry Pi 3B+ + nRF24L01+ via pyrf24)
- **Channel Avoidance Algorithm**: Ranks channels by activity, excludes blocked/high-activity/insufficient-data channels
- **Persistent JSON Blocklist**: Survives application restarts, atomic writes, corruption recovery
- **Multiple Export Formats**: JSON, CSV, PNG (spectrum/waterfall)
- **WiFi Overlap Indicators**: Visual markers for WiFi channels 1, 6, 11 (nRF 12, 37, 62)
- **Comprehensive Logging**: JSON Lines format for analysis
- **Automated Tests**: Full pytest suite for all core modules

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with simulation backend (default)
python main.py

# Run with hardware backend (requires Raspberry Pi + pyrf24)
python main.py --hardware

# Run with debug logging
python main.py --debug
```

## Hardware Setup

For hardware mode on Raspberry Pi 3B+:

1. Enable SPI: `sudo raspi-config` → Interface Options → SPI → Enable
2. Install pyrf24: `pip install pyrf24`
3. Connect nRF24L01+:
   - CE → GPIO25 (Pin 22)
   - CSN → GPIO8 / SPI CE0 (Pin 24)
   - SCK → GPIO11 (Pin 23)
   - MOSI → GPIO10 (Pin 19)
   - MISO → GPIO9 (Pin 21)
   - 3.3V → Pin 1 or 17
   - GND → Pin 6, 9, 14, 20, 25, 30, 34, or 39
4. Run: `python main.py --hardware`

## Project Structure

```
rf_spectrum_visualizer/
├── main.py                    # Entry point
├── config.py                  # Configuration dataclasses
├── exceptions.py              # Custom exceptions
├── logging_config.py          # JSON Lines logging
├── requirements.txt           # Dependencies
├── models/                    # Data models
│   ├── channel_record.py      # ChannelObservation, ChannelInfo
│   └── blocklist_model.py     # BlocklistEntry, BlocklistModel
├── services/                  # Shared services
│   ├── data_service.py        # Spectrum data coordination
│   └── persistence_service.py # Configuration persistence
├── radio/                     # Radio backends
│   ├── base_radio.py          # Abstract base class
│   ├── sim_radio.py           # Deterministic simulation
│   └── hardware_radio.py      # pyrf24 hardware interface
├── scanner/                   # Scanning engine
│   ├── scanner_engine.py      # ScannerThread, SpectrumData
│   └── channel_utils.py       # Channel conversion utilities
├── analysis/                  # Channel analysis
│   └── selector.py            # ChannelSelector, recommendations
├── mitigation/                # Channel blocking
│   └── blocklist_manager.py   # JSON blocklist manager
├── exports/                   # Export functionality
│   └── report_generator.py    # ReportGenerator
├── ui/                        # Tkinter UI
│   ├── main_window.py         # Main window with 3 tabs
│   ├── spectrum_page.py       # Spectrum display
│   ├── analysis_page.py       # Analysis & recommendations
│   └── blocker_page.py        # Blocklist management
└── tests/                     # Automated tests
    ├── test_channel_utils.py
    ├── test_blocklist.py
    ├── test_selector.py
    ├── test_scanner.py
    └── test_exports.py
```

## Safety Notice

> **⚠ IMPORTANT**: "BLOCKED IN SOFTWARE" prevents the **application** from selecting or recommending these channels. It does **NOT**:
> - Physically jam or block radio frequencies
> - Disrupt external devices or communications
> - Transmit any blocking signals
> - Affect the nRF24L01+ hardware operation

Blocked channels are only excluded from the application's channel avoidance recommendations and marked visually in the UI.

## Simulation Scenarios

The simulation backend includes deterministic scenarios for testing:

| Scenario | Description |
|----------|-------------|
| `quiet` | All channels <5% activity |
| `single_busy` | One channel at 80%, rest quiet |
| `spikes` | Random spikes across channels |
| `channel_122_high` | Channel 122 consistently 85% |
| `channel_122_low` | Channel 122 consistently 2% |
| `wifi_like` | WiFi channels 1,6,11 (nRF 12,37,62) active |
| `frequency_hopping` | Hopping pattern on some channels |
| `sensor_errors` | 1% random sensor failures |
| `mixed` | Realistic mixed environment |
| `burst` | Burst activity on some channels |
| `high_activity` | All channels 30-50% activity |

Run scenarios via Tools → Run Simulation Scenario in the GUI.

## Export Formats

| Format | Description |
|--------|-------------|
| JSON | Full report with metadata, assessments, recommendations |
| CSV | Channel data with eligibility, block status, peak activity |
| PNG (Spectrum) | Live spectrum bar graph |
| PNG (Waterfall) | Time vs frequency waterfall |
| Blocklist JSON/CSV | Just the blocklist entries |

## Configuration

Settings persist to `rf_spectrum_visualizer/config.json`:
- Channel range (default 0-125)
- Scan timing (measurement window, sampling interval)
- Activity thresholds (Clear/Moderate/Busy/Heavy)
- Mitigation parameters (persistent threshold, hysteresis)
- Hardware pins (CE, CSN, SPI speed)
- Simulation seed for reproducibility

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test module
pytest tests/test_blocklist.py -v

# With coverage
pytest tests/ --cov=rf_spectrum_visualizer --cov-report=html
```

## Limitations

- nRF24L01+ is a **narrowband transceiver** - RPD observations are not calibrated power measurements
- Hardware mode requires Raspberry Pi with SPI/GPIO access
- Simulation is deterministic but not representative of real RF environments
- Single-threaded scanner (channels scanned sequentially)
- No frequency-hopping synchronization with external devices

## License

MIT License - See LICENSE file for details.

## Acknowledgments

- Built on V3 (spectrum display) and V6 (analysis, blocking, channel avoidance) projects
- Uses pyrf24 for nRF24L01+ hardware interface
- Matplotlib for real-time visualization