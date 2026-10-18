"""rf_spectrum_visualizer.gui.pages.live_spectrum

Page 1: Live Spectrum.

Toolbar: Mode dropdown (sim/hardware), Start Scan, Stop Scan, Clear Display,
Channels from-to spinboxes (0-125), Window (s), Interval (ms), scan-rate
readout, Data Source note label.
Channel table: Ch, Freq MHz, Activity %, Status (Clear/Busy/Heavy Load),
Samples, RPD+, Data OK — green/pink row colors.
Live bar chart: Activity % by channel, green/orange/red, dotted threshold
lines.  Bar heights are updated in place (no ax.clear) for speed.
Waterfall: heatmap of Activity % over time (rows = scan cycles, columns =
channels 0-125).  Uses set_data on a fixed numpy array for speed.
Diagnostics/Log box.

Background scan thread + queue; clean Start/Stop; errors logged; falls
back to SimBackend if HardwareBackend fails.

The only metric is Activity % = (samples with RPD true / total samples) x 100.
No dBm or calibrated power is ever claimed.
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Optional

from rf_spectrum_visualizer.gui.theme import (
    BG,
    CARD,
    GREEN,
    GREEN_BG,
    MUTED,
    NICE_SCALES,
    ORANGE,
    PINK,
    RED,
    RED_ALERT,
    TEXT,
    THRESHOLD_BUSY,
    THRESHOLD_HEAVY,
    WATERFALL_CMAP,
    YScaleManager,
    activity_color,
    channel_status,
)
from rf_spectrum_visualizer.scan_backend import (
    ChannelStats,
    HardwareBackend,
    SimBackend,
)
from rf_spectrum_visualizer.scan_worker import (
    ScanComplete,
    ScanError,
    ScanPass,
    ScanState,
    ScanWorker,
)

try:
    import numpy as np
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    HAS_MATPLOTLIB = True
except ImportError:  # pragma: no cover - matplotlib required for GUI
    HAS_MATPLOTLIB = False
    np = None  # type: ignore[assignment]

# Waterfall config
WATERFALL_MAX_ROWS = 120   # number of scan cycles to keep in the heatmap
WATERFALL_COLS = 126       # channels 0-125

# GUI update rate limits
MAX_TABLE_HZ = 4.0         # max table row updates per second


class LiveSpectrumPage(ttk.Frame):
    """Live Spectrum page."""

    def __init__(
        self, parent: tk.Widget, mode_var: Optional[tk.StringVar] = None, **kwargs
    ) -> None:
        super().__init__(parent, **kwargs)
        self.configure(style="Card.TFrame")

        self.worker: Optional[ScanWorker] = None
        self._channel_stats: dict[int, ChannelStats] = {}
        self._scanning = ScanState()
        self._after_id: Optional[str] = None

        # Waterfall buffer: fixed numpy array, rows = scan cycles.
        self._waterfall_data: Optional[np.ndarray] = None
        self._waterfill_row = 0

        # Mode shared with MainWindow; if not provided, create a local one.
        self.mode_var = mode_var or tk.StringVar(value="sim")

        # Y-axis auto-scale manager.
        self._y_scale = YScaleManager()

        # Peak hold: per-channel max activity over recent passes.
        self._peak_hold: dict[int, float] = {}
        self._peak_hold_scatter: Optional[object] = None

        # Waterfall colorbar.
        self._waterfall_colorbar: Optional[object] = None

        # Wi-Fi channel overlay (off by default).
        self._wifi_overlay = False
        self._wifi_spans: list = []

        # Rate limiting for redraws.
        self._last_table_redraw = 0.0
        self._pending_stats: dict[int, ChannelStats] = {}
        self._stop_poll_count = 0

        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        # Toolbar
        toolbar = tk.Frame(self, bg=BG)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

        tk.Label(toolbar, text="Mode:", bg=BG, fg=TEXT).pack(side=tk.LEFT)
        self.mode_combo = ttk.Combobox(
            toolbar,
            textvariable=self.mode_var,
            values=["sim", "hardware"],
            state="readonly",
            width=10,
        )
        self.mode_combo.pack(side=tk.LEFT, padx=(4, 12))

        self.start_btn = tk.Button(
            toolbar,
            text="Start Scan",
            bg=GREEN,
            fg="white",
            bd=0,
            padx=12,
            pady=4,
            command=self._start_scan,
        )
        self.start_btn.pack(side=tk.LEFT, padx=2)

        self.stop_btn = tk.Button(
            toolbar,
            text="Stop Scan",
            bg=RED,
            fg="white",
            bd=0,
            padx=12,
            pady=4,
            command=self._stop_scan,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=2)

        self.clear_btn = tk.Button(
            toolbar,
            text="Clear Display",
            bg=ORANGE,
            fg="white",
            bd=0,
            padx=12,
            pady=4,
            command=self._clear_display,
        )
        self.clear_btn.pack(side=tk.LEFT, padx=2)

        tk.Label(toolbar, text="Ch from:", bg=BG, fg=TEXT).pack(
            side=tk.LEFT, padx=(16, 2)
        )
        self.ch_from = tk.Spinbox(toolbar, from_=0, to=125, width=5)
        self.ch_from.delete(0, tk.END)
        self.ch_from.insert(0, "0")
        self.ch_from.pack(side=tk.LEFT)

        tk.Label(toolbar, text="to:", bg=BG, fg=TEXT).pack(side=tk.LEFT, padx=(4, 2))
        self.ch_to = tk.Spinbox(toolbar, from_=0, to=125, width=5)
        self.ch_to.delete(0, tk.END)
        self.ch_to.insert(0, "125")
        self.ch_to.pack(side=tk.LEFT)

        tk.Label(toolbar, text="Window (s):", bg=BG, fg=TEXT).pack(
            side=tk.LEFT, padx=(16, 2)
        )
        self.window_s = tk.Spinbox(toolbar, from_=1, to=3600, width=6)
        self.window_s.delete(0, tk.END)
        self.window_s.insert(0, "10")
        self.window_s.pack(side=tk.LEFT)

        tk.Label(toolbar, text="Interval (ms):", bg=BG, fg=TEXT).pack(
            side=tk.LEFT, padx=(8, 2)
        )
        self.interval_ms = tk.Spinbox(toolbar, from_=100, to=60000, width=6)
        self.interval_ms.delete(0, tk.END)
        self.interval_ms.insert(0, "250")
        self.interval_ms.pack(side=tk.LEFT)

        # Scan-rate readout
        self.scan_rate_var = tk.StringVar(value="Scan rate: -- ch/s")
        self.scan_rate_label = tk.Label(
            toolbar,
            textvariable=self.scan_rate_var,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self.scan_rate_label.pack(side=tk.LEFT, padx=(16, 0))

        # Data Source note
        self.data_source_var = tk.StringVar(
            value="Data Source: Simulation (deterministic model, no radio)"
        )
        self.data_source_label = tk.Label(
            toolbar,
            textvariable=self.data_source_var,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.data_source_label.pack(side=tk.LEFT, padx=(24, 0))

        # Y scale control: Auto / Fixed 0-100
        tk.Label(toolbar, text="Y scale:", bg=BG, fg=TEXT).pack(
            side=tk.LEFT, padx=(16, 2)
        )
        self.y_scale_var = tk.StringVar(value="Auto")
        self.y_scale_combo = ttk.Combobox(
            toolbar,
            textvariable=self.y_scale_var,
            values=["Auto", "Fixed 0-100"],
            state="readonly",
            width=10,
        )
        self.y_scale_combo.pack(side=tk.LEFT, padx=(0, 0))
        self.y_scale_combo.bind("<<ComboboxSelected>>", self._on_y_scale_change)

        self.reset_peaks_btn = tk.Button(
            toolbar,
            text="Reset peaks",
            bg=RED,
            fg="white",
            bd=0,
            padx=10,
            pady=4,
            command=self._reset_peaks,
        )
        self.reset_peaks_btn.pack(side=tk.LEFT, padx=(16, 0))

        # Wi-Fi channel overlay checkbox.
        self._wifi_var = tk.BooleanVar(value=False)
        self.wifi_cb = tk.Checkbutton(
            toolbar,
            text="Wi-Fi channels",
            variable=self._wifi_var,
            command=self._on_wifi_toggle,
            bg=BG,
            fg=TEXT,
            selectcolor=BG,
            activebackground=BG,
            activeforeground=TEXT,
            font=("Segoe UI", 9),
        )
        self.wifi_cb.pack(side=tk.LEFT, padx=(16, 0))

        # Middle: table + chart split
        middle = tk.PanedWindow(self, bg=BG, orient=tk.HORIZONTAL)
        middle.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Channel table
        table_frame = tk.Frame(middle, bg=CARD, bd=1, relief=tk.SOLID)
        middle.add(table_frame, width=520)

        tk.Label(
            table_frame,
            text="Channel Table",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=(6, 2))

        cols = ("ch", "freq", "activity", "status", "samples", "rpd", "ok")
        self.tree = ttk.Treeview(
            table_frame, columns=cols, show="headings", height=14
        )
        self.tree.heading("ch", text="Ch")
        self.tree.heading("freq", text="Freq MHz")
        self.tree.heading("activity", text="Activity %")
        self.tree.heading("status", text="Status")
        self.tree.heading("samples", text="Samples")
        self.tree.heading("rpd", text="RPD+")
        self.tree.heading("ok", text="Data OK")
        self.tree.column("ch", width=40, anchor=tk.CENTER)
        self.tree.column("freq", width=70, anchor=tk.CENTER)
        self.tree.column("activity", width=70, anchor=tk.CENTER)
        self.tree.column("status", width=90, anchor=tk.CENTER)
        self.tree.column("samples", width=60, anchor=tk.CENTER)
        self.tree.column("rpd", width=50, anchor=tk.CENTER)
        self.tree.column("ok", width=55, anchor=tk.CENTER)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

        tree_scroll = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        # Cache of tree item ids keyed by channel for in-place updates.
        self._tree_items: dict[int, str] = {}

        # Chart + waterfall stacked
        chart_frame = tk.Frame(middle, bg=CARD, bd=1, relief=tk.SOLID)
        middle.add(chart_frame)

        tk.Label(
            chart_frame,
            text="Activity % by Channel",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self.chart_canvas: Optional[object] = None
        if HAS_MATPLOTLIB:
            # Bar chart (top half)
            self.fig = Figure(figsize=(5, 5), dpi=100)
            self.ax_bar = self.fig.add_subplot(2, 1, 1)
            self.ax_bar.set_ylabel("Activity %")
            self.ax_bar.set_ylim(0, 105)
            self.ax_bar.axhline(
                THRESHOLD_BUSY, color=ORANGE, linestyle=":", linewidth=1
            )
            self.ax_bar.axhline(
                THRESHOLD_HEAVY, color=RED_ALERT, linestyle=":", linewidth=1
            )
            self._bar_rects: Optional[list] = None
            # Waterfall heatmap (bottom half)
            self.ax_wf = self.fig.add_subplot(2, 1, 2)
            self.ax_wf.set_xlabel("Channel")
            self.ax_wf.set_ylabel("Scan cycle")
            self.ax_wf.set_yticks([])
            self.im = None
            self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
            self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
            self.chart_canvas = self.canvas
        else:
            tk.Label(
                chart_frame,
                text="Matplotlib not installed - chart disabled",
                bg=CARD,
                fg=MUTED,
            ).pack(padx=8, pady=8)

        # Diagnostics / Log
        log_frame = tk.Frame(self, bg=CARD, bd=1, relief=tk.SOLID)
        log_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 8))

        tk.Label(
            log_frame,
            text="Diagnostics / Log",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=(4, 2))

        self.log_text = tk.Text(
            log_frame, height=6, bg="#fafafa", fg=TEXT, font=("Consolas", 9)
        )
        self.log_text.pack(fill=tk.X, padx=8, pady=(0, 6))
        log_scroll = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

    # ------------------------------------------------------------------ log
    def _log(self, message: str) -> None:
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)

    def _on_y_scale_change(self, _event=None) -> None:
        mode = "fixed" if self.y_scale_var.get() == "Fixed 0-100" else "auto"
        self._y_scale.set_mode(mode)
        self._log(f"Y scale: {mode}")

    def _reset_peaks(self) -> None:
        """Clear peak hold markers."""
        self._peak_hold.clear()
        self._peak_hold_scatter = None
        self._log("Peak hold reset")

    # ------------------------------------------------------------------ scan control
    def _start_scan(self) -> None:
        if not self._scanning.start_enabled:
            return
        if self.worker is not None and self.worker.running:
            # Old worker thread still alive - do not start a new one
            self._log("Scan already running - ignoring start request")
            return
        try:
            ch_from = int(self.ch_from.get())
            ch_to = int(self.ch_to.get())
        except ValueError:
            self._log("Error: invalid channel range")
            return
        if not (0 <= ch_from <= 125 and 0 <= ch_to <= 125 and ch_from <= ch_to):
            self._log("Error: channel range must be 0-125 and from <= to")
            return

        mode = self.mode_var.get()
        backend = None
        if mode == "hardware":
            try:
                backend = HardwareBackend()
                self.data_source_var.set(
                    "Data Source: Hardware (nRF24L01+, CE=GPIO25, CSN=CE0)"
                )
            except Exception as exc:
                self._log(f"Hardware unavailable, falling back to sim: {exc}")
                backend = None
                self.data_source_var.set(
                    "Data Source: Simulation (hardware fallback)"
                )
        if backend is None:
            backend = SimBackend()
            if mode == "hardware":
                self.data_source_var.set(
                    "Data Source: Simulation (hardware fallback)"
                )
            else:
                self.data_source_var.set(
                    "Data Source: Simulation (deterministic model)"
                )

        channels = list(range(ch_from, ch_to + 1))
        samples_per_pass = 1
        window_seconds = float(self.window_s.get())
        interval_ms = float(self.interval_ms.get())

        self.worker = ScanWorker(backend=backend)
        self._channel_stats.clear()
        self._pending_stats.clear()
        self._tree_items.clear()
        self._waterfall_data = None
        self._waterfill_row = 0
        self._peak_hold.clear()
        self._peak_hold_scatter = None
        self._waterfall_colorbar = None
        self._last_table_redraw = 0.0

        for item in self.tree.get_children():
            self.tree.delete(item)
        if self.chart_canvas is not None and HAS_MATPLOTLIB:
            self.ax_bar.clear()
            self.ax_bar.set_ylabel("Activity %")
            self.ax_bar.set_ylim(0, 105)
            self.ax_bar.axhline(
                THRESHOLD_BUSY, color=ORANGE, linestyle=":", linewidth=1
            )
            self.ax_bar.axhline(
                THRESHOLD_HEAVY, color=RED_ALERT, linestyle=":", linewidth=1
            )
            self._bar_rects = None
            self.ax_wf.clear()
            self.ax_wf.set_xlabel("Channel")
            self.ax_wf.set_ylabel("Scan cycle")
            self.ax_wf.set_yticks([])
            self.im = None
            self.canvas.draw()

        self._scanning.start()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.clear_btn.config(state=tk.NORMAL)
        self._y_scale.set_mode("fixed" if self.y_scale_var.get() == "Fixed 0-100" else "auto")
        self._log("Scan started")
        self._log(
            f"Scan: channels {ch_from}-{ch_to} ({mode}) "
            f"window={window_seconds}s interval={interval_ms}ms"
        )

        self.worker.start(
            channels,
            samples_per_pass=samples_per_pass,
            window_seconds=window_seconds,
            interval_ms=interval_ms,
        )
        self._scanning.started()

    def _stop_scan(self) -> None:
        if not self._scanning.stop_enabled:
            return
        if self.worker is None:
            return
        self.worker.stop()
        self._scanning.stop()
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.DISABLED)
        self._log("Scan stopping")
        self._stop_poll_count = 0
        self._poll_for_stop()

    def _poll_for_stop(self) -> None:
        """Poll until the worker thread has fully exited, then return to idle."""
        if self.worker is not None and self.worker.running:
            self._stop_poll_count += 1
            if self._stop_poll_count > 20:  # ~2 second timeout
                self._scanning.stopped()
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                self.worker = None
                self.scan_rate_var.set("Scan rate: -- ch/s")
                self._log("Scan stop timeout - worker thread did not exit; recovered to idle")
                return
            self._after_id = self.after(100, self._poll_for_stop)
            return
        # Worker thread has exited
        self._scanning.stopped()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.worker = None
        self.scan_rate_var.set("Scan rate: -- ch/s")
        self._log("Scan stopped")

    def _clear_display(self) -> None:
        """Clear the live display (table, chart, waterfall) without stopping the scan."""
        self._channel_stats.clear()
        self._pending_stats.clear()
        self._tree_items.clear()
        self._waterfall_data = None
        self._waterfill_row = 0
        self._peak_hold.clear()
        self._peak_hold_scatter = None
        self._waterfall_colorbar = None
        for item in self.tree.get_children():
            self.tree.delete(item)
        if self.chart_canvas is not None and HAS_MATPLOTLIB:
            self.ax_bar.clear()
            self.ax_bar.set_ylabel("Activity %")
            self.ax_bar.set_ylim(0, 105)
            self.ax_bar.axhline(
                THRESHOLD_BUSY, color=ORANGE, linestyle=":", linewidth=1
            )
            self.ax_bar.axhline(
                THRESHOLD_HEAVY, color=RED_ALERT, linestyle=":", linewidth=1
            )
            self._bar_rects = None
            self.ax_wf.clear()
            self.ax_wf.set_xlabel("Channel")
            self.ax_wf.set_ylabel("Scan cycle")
            self.ax_wf.set_yticks([])
            self.im = None
            self.canvas.draw()
        self._log("Display cleared")

    # ------------------------------------------------------------------ queue polling
    def _poll_queue(self) -> None:
        """Called periodically by tkinter.after() to drain the worker queue.

        If multiple ScanPass messages are queued, only the newest is rendered
        (older ones are dropped) to keep the GUI responsive.
        """
        # Update scan-rate readout every poll.
        if self.worker is not None:
            rate = self.worker.scan_rate
            last_pt = self.worker.last_pass_time
            if last_pt is not None:
                self.scan_rate_var.set(
                    f"Scan rate: {rate:.1f} ch/s  (pass: {last_pt*1000:.0f} ms)"
                )
            else:
                self.scan_rate_var.set(f"Scan rate: {rate:.1f} ch/s")

        if self.worker is None:
            self._after_id = self.after(200, self._poll_queue)
            return

        latest_pass: Optional[ScanPass] = None
        drained = False
        while True:
            try:
                msg = self.worker.result_queue.get_nowait()
            except Exception:
                break
            drained = True
            if isinstance(msg, ScanPass):
                latest_pass = msg  # keep only the newest
            elif isinstance(msg, ScanError):
                self._log(f"Error: {msg.message}")
                self._scanning.error()
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                self.scan_rate_var.set("Scan rate: -- ch/s")
                self.worker = None
            elif isinstance(msg, ScanComplete):
                self._log("Scan complete")
                self._scanning.complete()
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                self.scan_rate_var.set("Scan rate: -- ch/s")
                self.worker = None

        if latest_pass is not None:
            self._handle_scan_pass(latest_pass)

        if self.worker is not None and not self.worker.running and not drained and latest_pass is None:
            # Worker finished and queue empty
            if self._scanning.scanning:
                self._scanning.complete()
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                self.scan_rate_var.set("Scan rate: -- ch/s")
            self.worker = None
        else:
            self._after_id = self.after(100, self._poll_queue)

    def _handle_scan_pass(self, msg: ScanPass) -> None:
        """Apply one ScanPass: update stats, schedule table/chart refresh."""
        self._channel_stats = msg.channel_stats
        self._pending_stats = msg.channel_stats

        # Update peak hold per channel.
        for ch, s in msg.channel_stats.items():
            prev = self._peak_hold.get(ch, 0.0)
            self._peak_hold[ch] = max(prev, s.activity_percent)

        # Add waterfall row from newest pass.
        self._add_waterfall_row(msg.channel_stats)

        # Optional profiling log: pass timing.
        self._log(
            f"Pass {msg.pass_number}: {msg.pass_time_seconds*1000:.0f} ms, "
            f"rate {self.worker.scan_rate:.1f} ch/s"
            if self.worker is not None
            else f"Pass {msg.pass_number}: {msg.pass_time_seconds*1000:.0f} ms"
        )

        # Always refresh chart and table on new data.
        # Chart: update bar heights in place (no ax.clear) for speed.
        # Table: update rows in place at a reasonable rate.
        self._refresh_chart()

        now = time.perf_counter()
        table_interval = 1.0 / MAX_TABLE_HZ
        if now - self._last_table_redraw >= table_interval:
            self._refresh_table()
            self._last_table_redraw = now

    # ------------------------------------------------------------------ waterfall
    def _add_waterfall_row(self, channel_stats: dict[int, ChannelStats]) -> None:
        """Write one pass into the fixed numpy waterfall array.

        New pass is written to row 0 (top). Existing rows are shifted down
        by one so the newest scan cycle is always at the top, matching the
        "newest at top" label with origin="upper".
        """
        if not HAS_MATPLOTLIB or np is None:
            return
        row = [0.0] * WATERFALL_COLS
        for ch, s in channel_stats.items():
            if 0 <= ch < WATERFALL_COLS:
                row[ch] = s.activity_percent
        if self._waterfall_data is None:
            self._waterfall_data = np.zeros(
                (WATERFALL_MAX_ROWS, WATERFALL_COLS), dtype=np.float32
            )
        # Shift all existing rows down by 1, write new pass at row 0 (top)
        self._waterfall_data[1:, :] = self._waterfall_data[:-1, :]
        self._waterfall_data[0, :] = row
        self._waterfill_row += 1

    # ------------------------------------------------------------------ table (in-place updates)
    def _refresh_table(self) -> None:
        """Update table rows in place; only insert new rows for new channels."""
        if not self._channel_stats:
            return
        for ch, s in self._channel_stats.items():
            status = channel_status(s.activity_percent)
            rpd_plus = "yes" if s.rpd_true > 0 else "no"
            ok = "yes" if s.samples > 0 else "no"
            tags = ("busy",) if s.activity_percent >= THRESHOLD_BUSY else ("clear",)
            values = (
                s.channel,
                round(s.freq_mhz, 0),
                round(s.activity_percent, 1),
                status,
                s.samples,
                s.rpd_true,
                ok,
            )
            if ch in self._tree_items:
                item = self._tree_items[ch]
                self.tree.item(item, values=values, tags=tags)
            else:
                item = self.tree.insert(
                    "", tk.END, values=values, tags=tags
                )
                self._tree_items[ch] = item
        self.tree.tag_configure("clear", background=GREEN_BG)
        self.tree.tag_configure("busy", background=PINK)

    @staticmethod
    def _setup_xticks(ax) -> None:
        """Set x-axis ticks: major every 10 channels, minor every 5.

        Prevents tick-label overlap when all 126 channels are shown.
        """
        major_ticks = list(range(0, 126, 10))
        minor_ticks = list(range(0, 126, 5))
        ax.set_xticks(major_ticks)
        ax.set_xticks(minor_ticks, minor=True)
        ax.set_xticklabels([str(t) for t in major_ticks])

    def _apply_y_scale(self, ax, values: list[float]) -> None:
        """Apply auto-scale or fixed y-axis and update axis label."""
        if not values:
            return
        peak = max(values)
        y_max = self._y_scale.compute(peak)
        ax.set_ylim(0, y_max)
        ax.set_ylabel(self._y_scale.label())

    def _draw_peak_hold(self, chans: list[int], values: list[float]) -> None:
        """Draw peak hold markers (red diamonds) at per-channel max activity."""
        if not HAS_MATPLOTLIB:
            return
        peak_x = []
        peak_y = []
        for ch in chans:
            ph = self._peak_hold.get(ch)
            if ph is not None and ph > 0:
                peak_x.append(ch)
                peak_y.append(ph)

        if self._peak_hold_scatter is None:
            if peak_x:
                self._peak_hold_scatter = self.ax_bar.scatter(
                    peak_x, peak_y, marker="D", color="red", s=20, zorder=5
                )
        else:
            self._peak_hold_scatter.set_offsets(
                list(zip(peak_x, peak_y)) if peak_x else []
            )
            self._peak_hold_scatter.set_sizes([20] * len(peak_x))

    def _on_wifi_toggle(self) -> None:
        self._wifi_overlay = self._wifi_var.get()
        if self._wifi_overlay:
            self._draw_wifi_bands(self.ax_bar)
        else:
            self._remove_wifi_bands()
        if self.chart_canvas is not None:
            self.canvas.draw_idle()

    def _draw_wifi_bands(self, ax) -> None:
        """Draw faint shaded bands for Wi-Fi channels 1, 6, 11.

        nRF channel = freq - 2400.  Wi-Fi 20 MHz channels centered at
        2412 (ch 1), 2437 (ch 6), 2462 (ch 11) span roughly nRF
        channels 2-22, 27-47, 52-72.
        """
        bands = [
            (2, 22, "Wi-Fi ch 1 (2412 MHz)"),
            (27, 47, "Wi-Fi ch 6 (2437 MHz)"),
            (52, 72, "Wi-Fi ch 11 (2462 MHz)"),
        ]
        for start, end, label in bands:
            span = ax.axvspan(
                start - 0.5,
                end + 0.5,
                ymin=0,
                ymax=1,
                color="#9467bd",
                alpha=0.15,
                zorder=0,
            )
            self._wifi_spans.append(span)
            ax.text(
                (start + end) / 2,
                0.98,
                label,
                transform=ax.get_xaxis_transform(),
                fontsize=7,
                color="#9467bd",
                ha="center",
                va="top",
                alpha=0.8,
            )

    def _remove_wifi_bands(self) -> None:
        """Remove Wi-Fi band spans and labels."""
        for span in self._wifi_spans:
            try:
                span.remove()
            except ValueError:
                pass
        self._wifi_spans.clear()
        # Remove text labels (any text artists added for Wi-Fi labels)
        for txt in list(self.ax_bar.texts):
            if txt.get_text().startswith("Wi-Fi ch"):
                txt.remove()

    # ------------------------------------------------------------------ chart (in-place bar updates)
    def _refresh_chart(self) -> None:
        if not HAS_MATPLOTLIB or self.chart_canvas is None:
            return
        if self._bar_rects is None:
            # First draw: create bars.
            self.ax_bar.clear()
            self.ax_bar.set_ylabel("Activity %")
            self.ax_bar.set_ylim(0, 105)
            self.ax_bar.axhline(
                THRESHOLD_BUSY, color=ORANGE, linestyle=":", linewidth=1
            )
            self.ax_bar.axhline(
                THRESHOLD_HEAVY, color=RED_ALERT, linestyle=":", linewidth=1
            )
            chans = sorted(self._channel_stats)
            values = [self._channel_stats[c].activity_percent for c in chans]
            colors = [activity_color(v) for v in values]
            if not chans:
                # No data yet - keep bar_rects None so the next pass with
                # data goes through the first-draw path.
                self._bar_rects = None
                self._setup_xticks(self.ax_bar)
                self._apply_y_scale(self.ax_bar, values)
                if self._wifi_overlay:
                    self._draw_wifi_bands(self.ax_bar)
            else:
                self._bar_rects = self.ax_bar.bar(
                    chans, values, color=colors, width=1.0, edgecolor="none"
                )
                self._setup_xticks(self.ax_bar)
                self._apply_y_scale(self.ax_bar, values)
                self._draw_peak_hold(chans, values)
                if self._wifi_overlay:
                    self._draw_wifi_bands(self.ax_bar)
        else:
            # In-place update: change bar heights and colors only.
            chans = sorted(self._channel_stats)
            values = [self._channel_stats[c].activity_percent for c in chans]
            colors = [activity_color(v) for v in values]
            for rect, ch, val, col in zip(
                self._bar_rects, chans, values, colors
            ):
                rect.set_height(val)
                rect.set_color(col)
                rect.set_width(1.0)
                rect.set_edgecolor("none")
            self._setup_xticks(self.ax_bar)
            self._apply_y_scale(self.ax_bar, values)
            self._draw_peak_hold(chans, values)
            if self._wifi_overlay:
                self._draw_wifi_bands(self.ax_bar)

        # Waterfall: update image data in place via set_data.
        if self._waterfall_data is not None and self._waterfill_row > 0:
            rows_to_show = min(self._waterfill_row, WATERFALL_MAX_ROWS)
            # Use same auto-scale as bar chart for waterfall vmax.
            peak = max(
                [s.activity_percent for s in self._channel_stats.values()],
                default=0.0,
            )
            wf_vmax = self._y_scale.compute(peak) if self._channel_stats else 100.0

            if self.im is None:
                self.im = self.ax_wf.imshow(
                    self._waterfall_data[:rows_to_show, :],
                    aspect="auto",
                    interpolation="nearest",
                    cmap=WATERFALL_CMAP,
                    vmin=0,
                    vmax=wf_vmax,
                    origin="upper",
                    extent=[0, WATERFALL_COLS - 1, 0, rows_to_show - 1],
                )
                self.ax_wf.set_xlabel("Channel")
                self.ax_wf.set_ylabel("Scan cycle (newest at top)")
                self.ax_wf.set_yticks([])
                # Colorbar labelled Activity %.
                self._waterfall_colorbar = self.fig.colorbar(
                    self.im, ax=self.ax_wf, label="Activity %"
                )
            else:
                self.im.set_data(self._waterfall_data[:rows_to_show, :])
                self.im.set_clim(0, wf_vmax)
                self.im.set_extent(
                    [0, WATERFALL_COLS - 1, 0, rows_to_show - 1]
                )
                if self._waterfall_colorbar is not None:
                    self._waterfall_colorbar.draw_all()

        self.canvas.draw_idle()
