#!/usr/bin/env python3
"""2.4 GHz RF activity / spectrum visualizer (nRF24L01) - Tkinter + Matplotlib.

    python app.py            # auto: hardware if found, otherwise simulation
    python app.py --sim      # force simulation backend
    python app.py --hw       # force nRF24L01 hardware backend (Raspberry Pi)
"""

import argparse
import csv
import signal
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from hardware_radio import HARDWARE_HINTS, RadioError
from scanner import (BASE_FREQ_MHZ, NUM_CHANNELS, ScannerThread, SpectrumData,
                     create_radio)

WF_ROWS = 200               # waterfall history rows
REFRESH_MS = 100            # GUI refresh period (~10 fps)


class App:
    def __init__(self, root, radio, label, window, smoke=0.0):
        self.root = root
        self.radio = radio
        self.label = label
        self.data = SpectrumData(window=window, waterfall_rows=WF_ROWS)
        self.scanner = None

        self._act = np.zeros(NUM_CHANNELS, dtype=np.float32)
        self._init_window = window
        self._peak = np.zeros(NUM_CHANNELS, dtype=np.float32)
        self._wf_img = np.zeros((WF_ROWS, NUM_CHANNELS), dtype=np.float32)
        self._wf_last = 0
        self._closing = False
        self._sigint = False
        self._err_shown = False
        self._t0 = time.monotonic()
        self._smoke = smoke

        self._build_controls()
        self._build_figure()
        self._build_info()

    # ------------------------------------------------------------------ UI
    def _build_controls(self):
        bar = ttk.Frame(self.root, padding=4)
        bar.pack(side=tk.TOP, fill=tk.X)

        self.btn_start = ttk.Button(bar, text="Start", command=self.on_start)
        self.btn_stop = ttk.Button(bar, text="Stop", command=self.on_stop,
                                   state=tk.DISABLED)
        self.btn_clear = ttk.Button(bar, text="Clear", command=self.on_clear)
        self.btn_start.pack(side=tk.LEFT, padx=2)
        self.btn_stop.pack(side=tk.LEFT, padx=2)
        self.btn_clear.pack(side=tk.LEFT, padx=2)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(bar, text="Window:").pack(side=tk.LEFT)
        self.window_var = tk.IntVar(value=self._init_window)
        spin = ttk.Spinbox(bar, from_=10, to=1000, width=6,
                           textvariable=self.window_var,
                           command=self._apply_window)
        spin.bind("<Return>", lambda _e: self._apply_window())
        spin.pack(side=tk.LEFT, padx=4)
        ttk.Label(bar, text="sweeps").pack(side=tk.LEFT)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        self.peak_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Peak hold", variable=self.peak_var,
                        command=self._toggle_peak).pack(side=tk.LEFT, padx=2)

        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Button(bar, text="Save CSV", command=self.save_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Save PNG", command=self.save_png).pack(side=tk.LEFT, padx=2)

        bg = "#2a7d2a" if self.label == "HARDWARE" else "#b26a00"
        tk.Label(bar, text=self.label, fg="white", bg=bg, padx=10, pady=2,
                 font=("TkDefaultFont", 9, "bold")).pack(side=tk.RIGHT, padx=4)

    def _build_figure(self):
        self.fig = Figure(figsize=(8.2, 5.4), dpi=90)
        gs = self.fig.add_gridspec(2, 1, height_ratios=[3, 2], hspace=0.35,
                                   left=0.08, right=0.97, top=0.92, bottom=0.10)
        xs = np.arange(BASE_FREQ_MHZ, BASE_FREQ_MHZ + NUM_CHANNELS)
        self._xs = xs
        zeros = np.zeros(NUM_CHANNELS)

        # --- spectrum ----------------------------------------------------
        self.ax = self.fig.add_subplot(gs[0])
        (self.line,) = self.ax.plot(xs, zeros, color="#1f77b4", lw=1.0)
        (self.peak_line,) = self.ax.plot(xs, zeros, color="#ff7f0e", lw=0.9,
                                         alpha=0.9)
        self.peak_line.set_visible(False)

        self.ax.set_xlim(BASE_FREQ_MHZ, BASE_FREQ_MHZ + NUM_CHANNELS)
        self.ax.set_ylim(0, 100)
        self.ax.set_ylabel("Activity (%)", fontsize=9)
        self.ax.set_title("2.4 GHz activity - nRF24L01 carrier detect "
                          "(RPD threshold \u2248 -64 dBm, relative indicator only)",
                          fontsize=10)
        self.ax.grid(alpha=0.3)

        # Wi-Fi channel 1-13 bands (center 2407 + 5*ch MHz, ~22 MHz wide)
        for ch in range(1, 14):
            center = 2407 + 5 * ch
            self.ax.axvspan(center - 11, center + 11,
                            color="#1f77b4", alpha=0.06, lw=0)
            self.ax.text(center, 0.965, str(ch),
                         transform=self.ax.get_xaxis_transform(),
                         ha="center", va="top", fontsize=6,
                         color="#1f77b4", alpha=0.7)

        # --- waterfall ---------------------------------------------------
        self.axw = self.fig.add_subplot(gs[1], sharex=self.ax)
        self.im = self.axw.imshow(self._wf_img, aspect="auto", origin="lower",
                                  extent=[BASE_FREQ_MHZ,
                                          BASE_FREQ_MHZ + NUM_CHANNELS,
                                          0, WF_ROWS],
                                  cmap="inferno", vmin=0, vmax=100,
                                  interpolation="nearest")
        self.axw.set_xlabel("Frequency (MHz)", fontsize=9)
        self.axw.set_ylabel("time \u2192 now", fontsize=9)
        self.axw.set_yticks([])
        cbar = self.fig.colorbar(self.im, ax=self.axw, pad=0.01, aspect=30)
        cbar.set_label("activity %", fontsize=8)
        cbar.ax.tick_params(labelsize=7)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)

    def _build_info(self):
        info = ttk.Frame(self.root, padding=4)
        info.pack(side=tk.BOTTOM, fill=tk.X)
        self.var_rate = tk.StringVar(value="0.0 sweeps/s")
        self.var_total = tk.StringVar(value="0 sweeps")
        self.var_busy = tk.StringVar(value="busiest: -")
        self.var_status = tk.StringVar(value="Stopped")
        self.var_hover = tk.StringVar(value="")
        for var, width in ((self.var_rate, 15), (self.var_total, 12),
                           (self.var_busy, 30), (self.var_status, 9)):
            ttk.Label(info, textvariable=var, width=width).pack(side=tk.LEFT, padx=6)
        ttk.Label(info, textvariable=self.var_hover).pack(side=tk.RIGHT, padx=6)

    # ------------------------------------------------------------- buttons
    def on_start(self):
        if self.scanner is not None and self.scanner.is_alive():
            return
        self.data.error = None
        self._err_shown = False
        self.scanner = ScannerThread(self.radio, self.data)
        self.scanner.start()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)

    def on_stop(self):
        if self.scanner is not None:
            self.scanner.stop()
            self.scanner.join(timeout=2.0)
            self.scanner = None
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def on_clear(self):
        self.data.clear()
        self._wf_img[:] = 0
        self._peak[:] = 0
        self._act[:] = 0
        self._wf_last = 0
        self.im.set_data(self._wf_img)

    def _apply_window(self):
        try:
            self.data.set_window(int(self.window_var.get()))
        except (ValueError, tk.TclError):
            pass

    def _toggle_peak(self):
        self.peak_line.set_visible(self.peak_var.get())
        if not self.peak_var.get():
            self._peak[:] = 0

    # --------------------------------------------------------------- export
    def save_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="spectrum.csv",
            filetypes=[("CSV files", "*.csv")], title="Export spectrum as CSV")
        if not path:
            return
        try:
            act = self.data.activity()
            with open(path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["channel", "freq_mhz", "activity_pct"])
                for ch, pct in enumerate(act):
                    writer.writerow([ch, BASE_FREQ_MHZ + ch, "%.1f" % pct])
        except OSError as exc:
            messagebox.showerror("CSV export failed", str(exc))

    def save_png(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".png", initialfile="spectrum.png",
            filetypes=[("PNG image", "*.png")], title="Save screenshot as PNG")
        if not path:
            return
        try:
            self.fig.savefig(path, dpi=150)
        except OSError as exc:
            messagebox.showerror("PNG export failed", str(exc))

    # --------------------------------------------------------------- events
    def _on_motion(self, event):
        if event.inaxes not in (self.ax, self.axw) or event.xdata is None:
            return
        ch = int(round(event.xdata - BASE_FREQ_MHZ))
        if 0 <= ch < NUM_CHANNELS:
            self.var_hover.set("ch %d | %d MHz | %.0f%%"
                               % (ch, BASE_FREQ_MHZ + ch, self._act[ch]))

    def sigint_received(self):
        self._sigint = True

    # ----------------------------------------------------------------- tick
    def tick(self):
        if self._closing:
            return
        if self._sigint:
            self.on_close()
            return

        self._act = np.asarray(self.data.activity(), dtype=np.float32)
        self.line.set_ydata(self._act)
        if self.peak_var.get():
            np.maximum(self._peak, self._act, out=self._peak)
            self.peak_line.set_ydata(self._peak)

        rows, self._wf_last = self.data.waterfall_since(self._wf_last)
        if rows:
            k = min(len(rows), WF_ROWS)
            self._wf_img = np.roll(self._wf_img, -k, axis=0)
            self._wf_img[-k:] = np.asarray(rows[-k:], dtype=np.float32)
            self.im.set_data(self._wf_img)

        st = self.data.stats()
        self.var_rate.set("%.1f sweeps/s" % st["sweeps_per_sec"])
        self.var_total.set("%d sweeps" % st["total_sweeps"])
        self.var_busy.set("busiest: ch %d (%d MHz) %.0f%%"
                          % (st["busiest_channel"], st["busiest_freq_mhz"],
                             st["busiest_pct"]))
        if st["error"]:
            self.var_status.set("Error")
            if not self._err_shown:
                self._err_shown = True
                self.on_stop()
                messagebox.showerror("Scanner error", st["error"])
        else:
            self.var_status.set("Running" if st["running"] else "Stopped")

        self.canvas.draw_idle()

        if self._smoke and time.monotonic() - self._t0 > self._smoke:
            self.on_close()
            return
        self.root.after(REFRESH_MS, self.tick)

    # -------------------------------------------------------------- shutdown
    def on_close(self):
        if self._closing:
            return
        self._closing = True
        if self.scanner is not None:
            self.scanner.stop()
            self.scanner.join(timeout=2.0)
            self.scanner = None
        try:
            self.radio.close()
        except Exception:
            pass
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--sim", action="store_true", help="simulation backend")
    src.add_argument("--hw", action="store_true", help="nRF24L01 hardware backend")
    parser.add_argument("--window", type=int, default=100,
                        help="rolling window size in sweeps (default 100)")
    parser.add_argument("--smoke", type=float, default=0.0,
                        help="self-test: auto-close after N seconds")
    args = parser.parse_args(argv)

    mode = "hw" if args.hw else ("sim" if args.sim else "auto")
    try:
        radio, label, fallback_err = create_radio(mode)
    except RadioError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        print(HARDWARE_HINTS, file=sys.stderr)
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("Radio not found",
                                 "%s\n\n%s" % (exc, HARDWARE_HINTS))
            r.destroy()
        except tk.TclError:
            pass
        return 2
    if fallback_err is not None:
        print("note: hardware not available (%s) -> %s" % (fallback_err, label),
              file=sys.stderr)

    root = tk.Tk()
    root.title("2.4 GHz RF Activity Visualizer")
    root.geometry("980x660")
    app = App(root, radio, label, args.window, smoke=args.smoke)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    signal.signal(signal.SIGINT, lambda *_: app.sigint_received())

    app.on_start()
    root.after(REFRESH_MS, app.tick)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.on_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
