"""rf_spectrum_visualizer.gui.pages.start_analysis

Page 2: Start Analysis.

Start Analysis button + status line ("Analysis complete - 126 channel(s)
analyzed, 4 scan cycle(s)").
4 summary cards: Channels Analyzed, Busiest Channel, Average Activity,
Recommended Clear.
"Channel Activity Comparison" chart (excluded channels purple).
Results table (Ch, Freq, Activity %, Status, Recommendation:
Recommended / Avoid / "Blocked - excluded").
Integration with Blocker: excluded channels come from an external set.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional
import threading

from rf_spectrum_visualizer.analysis import (
    AnalysisEngine,
    AVOID,
    BLOCKED_EXCLUDED,
    RECOMMENDED,
    run_quick_analysis,
)
from rf_spectrum_visualizer.blocker import BlockerManager
from rf_spectrum_visualizer.gui.theme import (
    BG,
    CARD,
    GREEN,
    MUTED,
    NICE_SCALES,
    ORANGE,
    PINK,
    RED_ALERT,
    TEXT,
    YScaleManager,
)
from rf_spectrum_visualizer.scan_backend import HardwareBackend, ScanBackend, SimBackend

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    HAS_MATPLOTLIB = True
except ImportError:  # pragma: no cover - matplotlib required for GUI
    HAS_MATPLOTLIB = False


class StartAnalysisPage(ttk.Frame):
    """Start Analysis page."""

    def __init__(
        self,
        parent: tk.Widget,
        blocker_manager: BlockerManager,
        mode: str = "sim",
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.configure(style="Card.TFrame")

        self.blocker_manager = blocker_manager
        self.mode = mode
        self.excluded_channels: set[int] = set(blocker_manager.excluded_channels)
        self.analysis_result = None
        self._after_id: Optional[str] = None
        self._y_scale = YScaleManager()

        self._build_ui()

    # ------------------------------------------------------------------ type hint
    from typing import Optional  # noqa: E402

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        # Header + Start button
        header = tk.Frame(self, bg=BG)
        header.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

        tk.Label(
            header,
            text="Start Analysis",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)

        self.start_btn = tk.Button(
            header,
            text="Start Analysis",
            bg=GREEN,
            fg="white",
            bd=0,
            padx=16,
            pady=6,
            font=("Segoe UI", 10, "bold"),
            command=self._start_analysis,
        )
        self.start_btn.pack(side=tk.RIGHT, padx=(0, 16))

        # Y scale control: Auto / Fixed 0-100
        tk.Label(header, text="Y scale:", bg=BG, fg=TEXT).pack(side=tk.RIGHT)
        self.y_scale_var = tk.StringVar(value="Auto")
        self.y_scale_combo = ttk.Combobox(
            header,
            textvariable=self.y_scale_var,
            values=["Auto", "Fixed 0-100"],
            state="readonly",
            width=10,
        )
        self.y_scale_combo.pack(side=tk.RIGHT, padx=(0, 4))
        self.y_scale_combo.bind("<<ComboboxSelected>>", self._on_y_scale_change)

        # Data Source label
        self.data_source_var = tk.StringVar(
            value=f"Data Source: {'Hardware' if self.mode == 'hardware' else 'Simulation'}"
        )
        self.data_source_label = tk.Label(
            header,
            textvariable=self.data_source_var,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.data_source_label.pack(side=tk.RIGHT)

        # Status line
        self.status_var = tk.StringVar(value="Analysis not yet run")
        self.status_label = tk.Label(
            self,
            textvariable=self.status_var,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        )
        self.status_label.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 8))

        # Summary cards
        cards = tk.Frame(self, bg=BG)
        cards.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 8))

        self.card_channels = self._make_card(cards, "Channels Analyzed", "0")
        self.card_busiest = self._make_card(cards, "Busiest Channel", "—")
        self.card_avg = self._make_card(cards, "Average Activity", "0.0%")
        self.card_recommended = self._make_card(cards, "Recommended Clear", "0")

        for c in (self.card_channels, self.card_busiest, self.card_avg, self.card_recommended):
            c.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        # Chart + table split
        middle = tk.PanedWindow(self, bg=BG, orient=tk.HORIZONTAL)
        middle.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Chart
        chart_frame = tk.Frame(middle, bg=CARD, bd=1, relief=tk.SOLID)
        middle.add(chart_frame, width=520)

        tk.Label(
            chart_frame,
            text="Channel Activity Comparison",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self.chart_canvas = None
        if HAS_MATPLOTLIB:
            self.fig = Figure(figsize=(5, 3.5), dpi=100)
            self.ax = self.fig.add_subplot(111)
            self.ax.set_xlabel("Channel")
            self.ax.set_ylabel("Avg Activity %")
            self.ax.set_ylim(0, 105)
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

        # Results table
        table_frame = tk.Frame(middle, bg=CARD, bd=1, relief=tk.SOLID)
        middle.add(table_frame)

        tk.Label(
            table_frame,
            text="Analysis Results",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=8, pady=(6, 2))

        cols = ("ch", "freq", "activity", "status", "recommendation")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=10)
        self.tree.heading("ch", text="Ch")
        self.tree.heading("freq", text="Freq MHz")
        self.tree.heading("activity", text="Activity %")
        self.tree.heading("status", text="Status")
        self.tree.heading("recommendation", text="Recommendation")
        self.tree.column("ch", width=45, anchor=tk.CENTER)
        self.tree.column("freq", width=75, anchor=tk.CENTER)
        self.tree.column("activity", width=80, anchor=tk.CENTER)
        self.tree.column("status", width=95, anchor=tk.CENTER)
        self.tree.column("recommendation", width=140, anchor=tk.CENTER)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)

        tree_scroll = ttk.Scrollbar(
            table_frame, orient=tk.VERTICAL, command=self.tree.yview
        )
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=tree_scroll.set)

        # Export button
        export_frame = tk.Frame(self, bg=BG)
        export_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))

        self.export_btn = tk.Button(
            export_frame,
            text="Export CSV",
            bg=ORANGE,
            fg="white",
            bd=0,
            padx=12,
            pady=4,
            command=self._export_csv,
            state=tk.DISABLED,
        )
        self.export_btn.pack(side=tk.RIGHT)

    # ------------------------------------------------------------------ card
    def _make_card(self, parent: tk.Widget, title: str, value: str) -> tk.Frame:
        card = tk.Frame(parent, bg=CARD, bd=1, relief=tk.SOLID)
        tk.Label(
            card,
            text=title,
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=10, pady=(8, 0))
        val_label = tk.Label(
            card,
            text=value,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
        )
        val_label.pack(anchor="w", padx=10, pady=(0, 8))
        card.value_label = val_label  # type: ignore[attr-defined]
        return card

    def _set_card(self, card: tk.Frame, value: str) -> None:
        card.value_label.config(text=value)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ excluded channels
    def set_excluded_channels(self, channels: set[int]) -> None:
        """Update excluded channels (from Blocker page) and refresh display."""
        self.excluded_channels = set(channels)
        self.blocker_manager.set_excluded(channels)
        if self.analysis_result is not None:
            self._refresh_display()

    def _on_y_scale_change(self, _event=None) -> None:
        mode = "fixed" if self.y_scale_var.get() == "Fixed 0-100" else "auto"
        self._y_scale.set_mode(mode)

    # ------------------------------------------------------------------ analysis
    def _start_analysis(self) -> None:
        if hasattr(self, "_analysis_running") and self._analysis_running:
            return
        self._analysis_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.status_var.set("Analyzing all 126 channels (4 cycles)...")
        self.export_btn.config(state=tk.DISABLED)

        backend: ScanBackend
        if self.mode == "hardware":
            try:
                backend = HardwareBackend()
            except Exception:
                backend = SimBackend()
                self.data_source_var.set(
                    "Data Source: Simulation (hardware unavailable)"
                )
        else:
            backend = SimBackend()

        engine = AnalysisEngine(backend=backend)
        engine.set_excluded_channels(self.blocker_manager.excluded_channels)

        def _run():
            result = engine.run(cycles=4, samples_per_channel=100)
            self.after(0, lambda: self._analysis_done(result))

        threading.Thread(target=_run, daemon=True).start()

    def _analysis_done(self, result) -> None:
        self.analysis_result = result
        self._analysis_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)
        self._y_scale.set_mode("fixed" if self.y_scale_var.get() == "Fixed 0-100" else "auto")

        self.status_var.set(
            f"Analysis complete - {result.channels_analyzed} channel(s) analyzed, "
            f"{result.cycles_run} scan cycle(s)"
        )

        self._set_card(self.card_channels, str(result.channels_analyzed))
        if result.busiest_channel:
            self._set_card(
                self.card_busiest,
                f"Ch {result.busiest_channel.channel} ({result.busiest_channel.freq_mhz:.0f} MHz)",
            )
        self._set_card(self.card_avg, f"{result.average_activity:.1f}%")
        self._set_card(self.card_recommended, str(len(result.recommended_clear)))

        self._refresh_table()
        self._refresh_chart()

    # ------------------------------------------------------------------ table / chart
    def _refresh_table(self) -> None:
        if self.analysis_result is None:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for ch in self.analysis_result.channels:
            tag = "excluded" if ch.recommendation == BLOCKED_EXCLUDED else ""
            self.tree.insert(
                "",
                tk.END,
                values=(
                    ch.channel,
                    f"{ch.freq_mhz:.0f}",
                    round(ch.avg_activity_percent, 1),
                    ch.status,
                    ch.recommendation,
                ),
                tags=(tag,) if tag else (),
            )
        self.tree.tag_configure("excluded", foreground=MUTED)

    def _refresh_chart(self) -> None:
        if not HAS_MATPLOTLIB or self.chart_canvas is None or self.analysis_result is None:
            return
        self.ax.clear()
        self.ax.set_xlabel("Channel")
        self.ax.set_ylabel("Avg Activity %")
        self.ax.set_ylim(0, 105)
        chans = [c.channel for c in self.analysis_result.channels]
        values = [c.avg_activity_percent for c in self.analysis_result.channels]
        colors = [
            "#9467bd" if c.channel in self.excluded_channels else self._bar_color(c.avg_activity_percent)
            for c in self.analysis_result.channels
        ]
        self.ax.bar(chans, values, color=colors, width=0.7)
        self._setup_xticks(self.ax)
        peak = max(values) if values else 0.0
        y_max = self._y_scale.compute(peak)
        self.ax.set_ylim(0, y_max)
        self.ax.set_ylabel(self._y_scale.label())
        self.chart_canvas.draw()

    @staticmethod
    def _bar_color(activity: float) -> str:
        if activity >= 75.0:
            return RED_ALERT
        if activity >= 50.0:
            return ORANGE
        return GREEN

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

    # ------------------------------------------------------------------ export
    def _export_csv(self) -> None:
        if self.analysis_result is None:
            return
        from tkinter import filedialog, messagebox

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            title="Export Analysis CSV",
        )
        if not path:
            return
        try:
            with open(path, "w", newline="") as f:
                f.write(self.analysis_result.to_csv())
            messagebox.showinfo("Export CSV", f"Saved to {path}")
        except Exception as exc:  # pragma: no cover - filesystem errors
            messagebox.showerror("Export CSV", f"Failed to save: {exc}")
