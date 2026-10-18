# Phase 6 - Launch, autostart, logging, waterfall

This document describes how to run the rf_spectrum_visualizer GUI on the
Raspberry Pi, including the launch script, desktop shortcut, optional
autostart, and optional file logging.

## Run the GUI

From the project root on the Pi:

```bash
source .venv/bin/activate
export PYTHONPATH="src"
python scripts/run_gui.py
```

The GUI opens with three pages: Live Spectrum, Start Analysis, and Blocker.
It starts in simulation mode (deterministic model, no radio).  Switch the
Mode dropdown to "hardware" and click Start Scan to use the real nRF24L01+
radio (CE=GPIO25, CSN=CE0).

## Desktop shortcut

A `.desktop` file is provided at `scripts/rf_spectrum_visualizer.desktop`.
To install it:

```bash
cp scripts/rf_spectrum_visualizer.desktop ~/.local/share/applications/
chmod +x ~/.local/share/applications/rf_spectrum_visualizer.desktop
```

The app will then appear in your desktop environment's application menu.

## Optional autostart on boot

To launch the visualizer automatically when the Pi boots into the desktop:

```bash
cp scripts/rf_spectrum_visualizer.desktop ~/.config/autostart/
```

Then edit `~/.config/autostart/rf_spectrum_visualizer.desktop` and change the
`Exec=` line to include the virtualenv python and PYTHONPATH, for example:

```ini
Exec=bash -c 'source /home/pi/workshop-hardware-/v7/.venv/bin/activate && export PYTHONPATH="/home/pi/workshop-hardware-/v7/src" && python /home/pi/workshop-hardware-/v7/scripts/run_gui.py'
```

Log out and back in (or reboot) for autostart to take effect.

## Optional file logging

`scripts/run_gui.py` logs to stdout and to `rf_spectrum_visualizer.log` in
the current working directory by default.  The log file is gitignored and
never committed.

To disable file logging, edit `scripts/run_gui.py` and change
`_setup_logging(enable_file_logging=True)` to
`_setup_logging(enable_file_logging=False)`.

## GUI features (Phase 6)

* **Live Spectrum** page:
  * Toolbar: Mode (sim/hardware), Start Scan, Stop Scan, Clear Display,
    Channels from-to spinboxes (0-125), Window (s), Interval (ms),
    scan-rate readout (channels/second), Data Source note.
  * Channel table: Ch, Freq MHz, Activity %, Status (Clear/Busy/Heavy Load),
    Samples, RPD+, Data OK — green/pink row colors.
  * Live bar chart: Activity % by channel, green/orange/red, dotted threshold
    lines at 50% (Busy) and 75% (Heavy Load).
  * Waterfall heatmap: Activity % over time (rows = scan cycles, columns =
    channels 0-125), newest cycle at top.
  * Diagnostics/Log box.
* **Start Analysis** page (Phase 4): multi-cycle averaging, ranking,
  recommendations, contiguous clear-block finder, CSV export.
* **Blocker** page (Phase 5): software-level channel exclusion with JSON
  persistence; does NOT block RF.

## No dBm / no calibrated power

This is NOT an SDR.  The nRF24 RPD flag is a yes/no that trips at roughly
-64 dBm, so the only metric is Activity % = (samples with RPD true /
total samples) x 100.  Never claim dBm or calibrated power.
