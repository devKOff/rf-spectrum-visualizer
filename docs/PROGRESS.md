# Progress - rf_spectrum_visualizer v3.1

Phase status: **in progress** (Phase 7 - Performance + Correctness).

## Phase 1 - Scaffold + hardware check scripts (APPROVED)

Tag `v3.1-phase1` pushed.

## Phase 2 - Scan backend (APPROVED)

Tag `v3.1-phase2` pushed.

## Phase 3 - GUI shell + Live Spectrum page (APPROVED)

Tag `v3.1-phase3` pushed.

## Phase 4 - Start Analysis page (APPROVED)

Tag `v3.1-phase4` pushed.

## Phase 5 - Blocker page + JSON persistence (APPROVED)

Tag `v3.1-phase5` pushed.

## Phase 6 - Waterfall, scan-rate readout, Clear button, docs, launch script/desktop shortcut (APPROVED)

Tag `v3.1-phase6` pushed.

## Phase 7 - Performance + Correctness (in progress)

New files: none.

Changed files:
- `src/rf_spectrum_visualizer/scan_worker.py` — PASS-based continuous scanning
  (1-3 samples per channel per pass, repeated until Stop). Rolling window per
  channel (length from Window setting) for Activity %. Publishes ScanPass per
  pass with pass timing. scan_rate reports real ch/s.
- `src/rf_spectrum_visualizer/gui/pages/live_spectrum.py` — Handles ScanPass
  (drops older passes, renders newest only). Bar heights updated in place
  (no ax.clear). draw_idle with max 10 Hz chart redraw, 4 Hz table redraw.
  Table rows updated in place, only changed rows. Waterfall uses fixed numpy
  array with set_data. Profiling log: pass time and redraw time.
- `tests/test_phase3.py` — Updated for start(samples_per_pass=...) API and ScanPass.
- `docs/PROGRESS.md` — updated.

Dev-machine pytest: 57 passed.
Could NOT verify without hardware: HardwareBackend end-to-end in GUI on Pi,
Tkinter on Pi OS, waterfall rendering on Pi, desktop shortcut, autostart.

Open issues:
- Tkinter on Raspberry Pi OS not yet verified (no display on dev machine).
- Matplotlib on Pi OS: user reported installing it; not yet verified with GUI.
- Hardware config unchanged: auto-ack off, CRC off, 1 Mbps.
