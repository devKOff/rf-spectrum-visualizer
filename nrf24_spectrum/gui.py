"""Tkinter + Matplotlib front-end: spectrum, waterfall, controls, status."""
import time
import tkinter as tk
from collections import deque
from tkinter import messagebox, ttk

import matplotlib
matplotlib.use("TkAgg")
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

from . import config as cfg
from .scanner import DATA_RATES, Scanner

BG, FG, GRID = "#12161c", "#d7dde5", "#2a323d"
IDLE_C, ACTIVE_C, PEAK_C, WIFI_C = "#3b4756", "#ff5a36", "#ffd166", "#5aa9e6"
OK_C = "#6bd18a"
N = cfg.NUM_CHANNELS
FREQS = cfg.BASE_MHZ + np.arange(N)
MIN_BAR = 0.012          # so idle channels still show a thin grey baseline tick


class App:
    def __init__(self, root, radio, radio_info):
        self.root, self.radio = root, radio
        self.scanner = None
        self.window = deque(maxlen=cfg.WINDOW_FRAMES)     # (hit_counts, sweeps) per frame
        self.waterfall = np.zeros((cfg.WATERFALL_ROWS, N))
        self.peak = np.zeros(N)
        self.smooth = np.zeros(N)
        self._rate_t, self._rate_n, self._rate = time.perf_counter(), 0, 0.0
        root.title("nRF24L01 RF Activity Scanner")
        self._build_controls()
        self._build_plots()
        self._build_status(radio_info)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------------------------------------------------------- layout
    def _build_controls(self):
        bar = ttk.Frame(self.root, padding=4)
        bar.pack(side=tk.TOP, fill=tk.X)
        self.btn_start = ttk.Button(bar, text="Start Scan", command=self.start)
        self.btn_stop = ttk.Button(bar, text="Stop Scan", command=self.stop, state=tk.DISABLED)
        self.btn_clear = ttk.Button(bar, text="Clear", command=self.clear)
        for b in (self.btn_start, self.btn_stop, self.btn_clear):
            b.pack(side=tk.LEFT, padx=2)
        ttk.Label(bar, text="   Data rate:").pack(side=tk.LEFT)
        self.rate_var = tk.StringVar(value="1 Mbps")
        self.cmb_rate = ttk.Combobox(bar, textvariable=self.rate_var, values=list(DATA_RATES),
                                     state="readonly", width=24)
        self.cmb_rate.pack(side=tk.LEFT, padx=2)
        ttk.Label(bar, text="  Dwell (µs):").pack(side=tk.LEFT)
        self.dwell_var = tk.IntVar(value=cfg.DEFAULT_DWELL_US)
        self.spn_dwell = ttk.Spinbox(bar, from_=cfg.MIN_DWELL_US, to=5000, increment=50,
                                     textvariable=self.dwell_var, width=6)
        self.spn_dwell.pack(side=tk.LEFT, padx=2)
        self.peak_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Peak hold", variable=self.peak_var,
                        command=self._toggle_peak).pack(side=tk.LEFT, padx=10)

    def _style(self, ax):
        ax.set_facecolor(BG)
        ax.tick_params(colors=FG, labelsize=8)
        for s in ax.spines.values():
            s.set_color(GRID)

    def _build_plots(self):
        fig = Figure(figsize=(9, 5.8), dpi=80, facecolor=BG)
        self.ax_spec, self.ax_wf = fig.subplots(2, 1, sharex=True,
                                                gridspec_kw={"height_ratios": [3, 2]})
        fig.subplots_adjust(left=0.08, right=0.985, top=0.94, bottom=0.10, hspace=0.22)
        ticks = list(range(cfg.BASE_MHZ, cfg.BASE_MHZ + N, 10)) + [cfg.BASE_MHZ + N - 1]
        lo, hi = cfg.BASE_MHZ - 0.5, cfg.BASE_MHZ + N - 0.5

        ax = self.ax_spec
        self._style(ax)
        self.bars = ax.bar(FREQS, np.full(N, MIN_BAR), width=1.0, color=IDLE_C, linewidth=0)
        self.peak_line, = ax.step(FREQS, self.peak, where="mid", color=PEAK_C, lw=1.0)
        ax.set_xlim(lo, hi)
        ax.set_ylim(0, 1.05)
        ax.set_xticks(ticks)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.grid(True, color=GRID, lw=0.5, alpha=0.7)
        ax.set_ylabel("Relative RF activity\n(% of sweeps with a hit)", color=FG, fontsize=9)
        ax.set_title("nRF24L01 RF activity - relative and uncalibrated (not dBm)", color=FG, fontsize=10)
        for centre, name in ((2412, "Wi-Fi 1"), (2437, "Wi-Fi 6"), (2462, "Wi-Fi 11")):   # reference only
            ax.axvline(centre, color=WIFI_C, lw=0.8, ls=":", alpha=0.6)
            ax.text(centre + 0.6, 0.98, name, transform=ax.get_xaxis_transform(),
                    color=WIFI_C, fontsize=7, va="top")
        ax.legend(handles=[Patch(color=ACTIVE_C, label="RF activity detected"),
                           Patch(color=IDLE_C, label="No activity detected"),
                           Line2D([0], [0], color=PEAK_C, label="Peak hold")],
                  loc="upper right", fontsize=8, facecolor=BG, edgecolor=GRID,
                  labelcolor=FG, framealpha=0.85)

        ax = self.ax_wf
        self._style(ax)
        span = cfg.WATERFALL_ROWS * cfg.UPDATE_MS / 1000.0
        self.image = ax.imshow(self.waterfall, aspect="auto", cmap="magma", vmin=0, vmax=1,
                               interpolation="nearest", extent=(lo, hi, span, 0))
        ax.set_xlim(lo, hi)
        ax.set_xticks(ticks)
        ax.set_xlabel("Frequency (MHz)     [channel n = 2400 + n MHz]", color=FG, fontsize=9)
        ax.set_ylabel("Seconds ago", color=FG, fontsize=9)
        ax.set_title("Waterfall - brighter = hit in more sweeps", color=FG, fontsize=9)

        self.canvas = FigureCanvasTkAgg(fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect("motion_notify_event", self._hover)

    def _build_status(self, radio_info):
        f = ttk.Frame(self.root, padding=(6, 2))
        f.pack(side=tk.BOTTOM, fill=tk.X)
        self.lbl_state = tk.Label(f, text="Idle - press Start Scan", anchor="w",
                                  font=("TkDefaultFont", 11, "bold"))
        self.lbl_scan = tk.Label(f, text="Scanner not running", anchor="w")
        self.lbl_cursor = tk.Label(f, text="Cursor: hover over a graph", anchor="w")
        for w in (self.lbl_state, self.lbl_scan, self.lbl_cursor,
                  tk.Label(f, text=radio_info, anchor="w", fg="#777777")):
            w.pack(fill=tk.X)

    # --------------------------------------------------------------- actions
    def start(self):
        if self.scanner:
            return
        try:
            dwell = int(self.dwell_var.get())
        except (ValueError, tk.TclError):
            dwell = cfg.DEFAULT_DWELL_US
        dwell = max(cfg.MIN_DWELL_US, dwell)
        self.dwell_var.set(dwell)
        self.scanner = Scanner(self.radio, DATA_RATES[self.rate_var.get()], dwell / 1e6)
        self.scanner.start()
        self._rate_t, self._rate_n = time.perf_counter(), 0
        self._set_running(True)
        self.root.after(cfg.UPDATE_MS, self._tick)

    def stop(self):
        if self.scanner:
            self.scanner.stop()
            self.scanner.join(timeout=2)
            self.scanner = None
        self._set_running(False)
        self.lbl_state.config(text="Stopped - display frozen. Press Start Scan to resume.", fg="#aaaaaa")
        self.lbl_scan.config(text="Scanner not running")

    def clear(self):
        self.window.clear()
        self.waterfall[:] = 0
        self.peak[:] = 0
        self.smooth[:] = 0
        if self.scanner:
            self.scanner.take_frame()
        self._render()

    def on_close(self):
        self.stop()
        try:
            self.radio.power = False
        except Exception:
            pass
        self.root.destroy()

    def _set_running(self, running):
        self.btn_start.config(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_stop.config(state=tk.NORMAL if running else tk.DISABLED)
        self.cmb_rate.config(state="disabled" if running else "readonly")
        self.spn_dwell.config(state="disabled" if running else "normal")

    def _toggle_peak(self):
        self.peak_line.set_visible(self.peak_var.get())
        self.canvas.draw_idle()

    # -------------------------------------------------------------- updating
    def _tick(self):
        s = self.scanner
        if s is None:
            return
        if s.error or not s.is_alive():
            msg = s.error or "Scanner thread ended unexpectedly."
            self.stop()
            messagebox.showerror("Scan error", msg)
            return
        frame = s.take_frame()
        if frame:
            acc, n = frame
            self.window.append((acc, n))
            self.waterfall = np.roll(self.waterfall, 1, axis=0)
            self.waterfall[0] = acc / n
            total = sum(a for a, _ in self.window)
            sweeps = sum(k for _, k in self.window)
            self.smooth = total / sweeps
            self.peak = np.maximum(self.peak * cfg.PEAK_DECAY, self.smooth)
            self._render()
        now = time.perf_counter()
        if now - self._rate_t >= 1.0:
            self._rate = (s.total_sweeps - self._rate_n) / (now - self._rate_t)
            self._rate_t, self._rate_n = now, s.total_sweeps
        ch = s.current_channel
        per_sweep = f"{1000.0 / self._rate:.0f} ms/sweep" if self._rate > 0 else "measuring..."
        self.lbl_scan.config(text=f"Scanning channel {ch:3d} = {cfg.BASE_MHZ + ch} MHz   |   "
                                  f"{self._rate:.1f} sweeps/s ({per_sweep})   |   "
                                  f"{s.total_sweeps} sweeps total")
        self.root.after(cfg.UPDATE_MS, self._tick)

    def _render(self):
        active = self.smooth >= cfg.ACTIVITY_THRESHOLD
        shown = np.maximum(self.smooth, MIN_BAR)
        for bar, h, a in zip(self.bars, shown, active):
            bar.set_height(h)
            bar.set_facecolor(ACTIVE_C if a else IDLE_C)
        self.peak_line.set_ydata(self.peak)
        self.image.set_data(self.waterfall)
        count = int(active.sum())
        if count:
            top = int(np.argmax(self.smooth))
            self.lbl_state.config(
                fg=ACTIVE_C,
                text=f"RF ACTIVITY DETECTED on {count} channel(s) - strongest: channel {top} "
                     f"= {cfg.BASE_MHZ + top} MHz ({self.smooth[top] * 100:.0f}% of sweeps)")
        elif self.scanner:
            self.lbl_state.config(fg=OK_C, text="No activity detected (nothing above the RPD threshold)")
        self.canvas.draw_idle()

    def _hover(self, event):
        if event.inaxes in (self.ax_spec, self.ax_wf) and event.xdata is not None:
            ch = int(min(max(round(event.xdata - cfg.BASE_MHZ), 0), N - 1))
            self.lbl_cursor.config(text=f"Cursor: channel {ch} = {cfg.BASE_MHZ + ch} MHz   |   "
                                        f"recent activity {self.smooth[ch] * 100:.0f}%   |   "
                                        f"peak {self.peak[ch] * 100:.0f}%")
