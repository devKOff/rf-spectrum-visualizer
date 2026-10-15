"""Spectrum page for RF Spectrum Visualizer - live spectrum display with waterfall."""

import tkinter as tk
from tkinter import ttk
import time
import threading
from collections import deque
from typing import Optional, List, Dict, Callable

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

from config import AppConfig
from analysis.selector import ChannelSelector
from mitigation.blocklist_manager import BlocklistManager
from services.data_service import DataService
from scanner.scanner_engine import ChannelObservation, SpectrumData
from models.channel_record import ChannelObservation as ChannelRecord
from scanner.channel_utils import format_channel


class SpectrumPage:
    """Spectrum page - live spectrum bar graph and waterfall display."""
    
    WIFI_CHANNELS = {
        1: 2412,
        6: 2437,
        11: 2462,
    }
    
    def __init__(
        self,
        parent: ttk.Frame,
        config: AppConfig,
        spectrum_data: SpectrumData,
        channel_selector: ChannelSelector,
        blocklist: BlocklistManager,
        data_service: DataService,
        get_waterfall_data: Callable[[float], List[ChannelObservation]],
    ):
        self._config = config
        self._spectrum_data = spectrum_data
        self._channel_selector = channel_selector
        self._blocklist = blocklist
        self._data_service = data_service
        self._get_waterfall_data = get_waterfall_data
        
        self._waterfall_data: deque = deque(maxlen=config.gui.waterfall_history_size)
        self._waterfall_timestamps: deque = deque(maxlen=config.gui.waterfall_history_size)
        
        self._create_ui(parent)
    
    @property
    def frame(self) -> ttk.Frame:
        return self._frame
    
    def _create_ui(self, parent: ttk.Frame) -> None:
        """Create the spectrum page UI."""
        self._frame = ttk.Frame(parent)
        
        # Create main paned window
        paned = ttk.PanedWindow(self._frame, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # Top: Channel table
        table_frame = ttk.LabelFrame(paned, text="Channel Activity (126 channels, 0-125)")
        paned.add(table_frame, weight=1)
        self._create_channel_table(table_frame)
        
        # Middle: Live spectrum
        spectrum_frame = ttk.LabelFrame(paned, text="Live Spectrum")
        paned.add(spectrum_frame, weight=1)
        self._create_spectrum_graph(spectrum_frame)
        
        # Bottom: Waterfall
        waterfall_frame = ttk.LabelFrame(paned, text="Waterfall (Time vs Frequency)")
        paned.add(waterfall_frame, weight=1)
        self._create_waterfall_graph(waterfall_frame)
        
        # Log/alerts panel
        alerts_frame = ttk.LabelFrame(paned, text="Alerts & Diagnostics")
        paned.add(alerts_frame, weight=0)
        self._create_alerts_panel(alerts_frame)
    
    def _create_channel_table(self, parent: ttk.Frame) -> None:
        """Create the channel activity table."""
        # Filter controls
        filter_frame = ttk.Frame(parent)
        filter_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=2)
        
        ttk.Label(filter_frame, text="Search:").pack(side=tk.LEFT, padx=2)
        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_frame, textvariable=self._search_var, width=15)
        search_entry.pack(side=tk.LEFT, padx=2)
        search_entry.bind("<KeyRelease>", self._on_search_change)
        
        ttk.Label(filter_frame, text="Status:").pack(side=tk.LEFT, padx=2)
        self._status_filter_var = tk.StringVar(value="All")
        status_combo = ttk.Combobox(
            filter_frame, textvariable=self._status_filter_var,
            values=["All", "Clear", "Moderate", "Busy", "Heavy Load", "INSUFFICIENT DATA", "SENSOR_ERROR", "BLOCKED"],
            width=15, state="readonly"
        )
        status_combo.pack(side=tk.LEFT, padx=2)
        status_combo.bind("<<ComboboxSelected>>", self._on_status_filter_change)
        
        ttk.Button(filter_frame, text="Clear Filters", command=self._clear_filters).pack(side=tk.LEFT, padx=5)
        
        # Table
        columns = ("channel", "frequency", "activity_bar", "activity_pct", "status", "samples", "rpd_pos", "sufficient", "eligible", "blocked")
        self._tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        
        self._tree.heading("channel", text="Ch", command=lambda: self._sort_table("channel"))
        self._tree.heading("frequency", text="Freq (MHz)", command=lambda: self._sort_table("frequency"))
        self._tree.heading("activity_bar", text="Activity")
        self._tree.heading("activity_pct", text="%", command=lambda: self._sort_table("activity_pct"))
        self._tree.heading("status", text="Status", command=lambda: self._sort_table("status"))
        self._tree.heading("samples", text="Samples")
        self._tree.heading("rpd_pos", text="RPD+")
        self._tree.heading("sufficient", text="Data OK")
        self._tree.heading("eligible", text="Eligible")
        self._tree.heading("blocked", text="Blocked")
        
        self._tree.column("channel", width=40, anchor=tk.CENTER)
        self._tree.column("frequency", width=70, anchor=tk.CENTER)
        self._tree.column("activity_bar", width=150)
        self._tree.column("activity_pct", width=50, anchor=tk.CENTER)
        self._tree.column("status", width=100, anchor=tk.CENTER)
        self._tree.column("samples", width=60, anchor=tk.CENTER)
        self._tree.column("rpd_pos", width=50, anchor=tk.CENTER)
        self._tree.column("sufficient", width=60, anchor=tk.CENTER)
        self._tree.column("eligible", width=60, anchor=tk.CENTER)
        self._tree.column("blocked", width=60, anchor=tk.CENTER)
        
        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self._tree.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")
        hsb.grid(row=2, column=0, sticky="ew")
        
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        # Tags for coloring
        self._tree.tag_configure("clear", background="#e8f5e9")
        self._tree.tag_configure("moderate", background="#fff3e0")
        self._tree.tag_configure("busy", background="#ffebee")
        self._tree.tag_configure("heavy", background="#fce4ec")
        self._tree.tag_configure("insufficient", background="#f5f5f5")
        self._tree.tag_configure("error", background="#ffcdd2")
        self._tree.tag_configure("blocked", background="#ffcdd2")
        self._tree.tag_configure("eligible", background="#e3f2fd")
        
        self._sort_column = "channel"
        self._sort_reverse = False
        self._search_filter = ""
        self._status_filter = "All"
    
    def _create_spectrum_graph(self, parent: ttk.Frame) -> None:
        """Create the live spectrum bar graph."""
        self._spec_fig = Figure(figsize=(10, 3), dpi=100)
        self._spec_ax = self._spec_fig.add_subplot(111)
        self._spec_canvas = FigureCanvasTkAgg(self._spec_fig, parent)
        self._spec_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        self._spec_ax.set_xlabel("Channel (nRF24)")
        self._spec_ax.set_ylabel("Activity (%)")
        self._spec_ax.set_ylim(0, 100)
        self._spec_ax.grid(True, alpha=0.3)
        
        self._spec_bars = None
    
    def _create_waterfall_graph(self, parent: ttk.Frame) -> None:
        """Create the waterfall visualization."""
        self._wf_fig = Figure(figsize=(10, 3), dpi=100)
        self._wf_ax = self._wf_fig.add_subplot(111)
        self._wf_canvas = FigureCanvasTkAgg(self._wf_fig, parent)
        self._wf_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        self._wf_ax.set_xlabel("Channel (nRF24)")
        self._wf_ax.set_ylabel("Time (s ago)")
        self._wf_ax.grid(True, alpha=0.3)
        
        self._wf_image = None
        self._wf_cmap = LinearSegmentedColormap.from_list(
            "rf_cmap", ["#000000", "#0000ff", "#00ffff", "#ffff00", "#ff0000"]
        )
    
    def _create_alerts_panel(self, parent: ttk.Frame) -> None:
        """Create alerts and diagnostics panel."""
        self._alerts_text = tk.Text(parent, height=6, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._alerts_text.yview)
        self._alerts_text.configure(yscrollcommand=vsb.set)
        
        self._alerts_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        self.log_message("RF Spectrum Visualizer ready. Select backend and press Start.")
    
    def _on_search_change(self, event=None) -> None:
        self._search_filter = self._search_var.get().lower()
        self.update_table()
    
    def _on_status_filter_change(self, event=None) -> None:
        self._status_filter = self._status_filter_var.get()
        self.update_table()
    
    def _clear_filters(self) -> None:
        self._search_var.set("")
        self._status_filter_var.set("All")
        self._search_filter = ""
        self._status_filter = "All"
        self.update_table()
    
    def _sort_table(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self.update_table()
    
    def update_table(self) -> None:
        """Update the channel table with current observations."""
        observations = self._spectrum_data.get_all_observations()
        channels = self._spectrum_data.get_channels_in_range()
        
        # Apply filters
        filtered_channels = []
        for ch in channels:
            if self._search_filter and self._search_filter not in str(ch) and self._search_filter not in str(2400+ch):
                continue
            
            obs = observations.get(ch)
            status = obs.status if obs else "Pending"
            blocked = self._blocklist.is_blocked(ch)
            
            if self._status_filter != "All":
                if self._status_filter == "BLOCKED" and not blocked:
                    continue
                if self._status_filter != "BLOCKED" and status != self._status_filter:
                    continue
            
            filtered_channels.append(ch)
        
        # Sort
        if self._sort_column == "channel":
            filtered_channels.sort(reverse=self._sort_reverse)
        elif self._sort_column == "frequency":
            filtered_channels.sort(key=lambda c: 2400+c, reverse=self._sort_reverse)
        elif self._sort_column == "activity_pct":
            filtered_channels.sort(
                key=lambda c: observations.get(c).activity_percentage if observations.get(c) and observations.get(c).activity_percentage is not None else -1,
                reverse=self._sort_reverse
            )
        elif self._sort_column == "status":
            filtered_channels.sort(
                key=lambda c: observations.get(c).status if observations.get(c) else "",
                reverse=self._sort_reverse
            )
        
        existing = set(self._tree.get_children())
        needed = set(str(ch) for ch in filtered_channels)
        
        for ch in filtered_channels:
            obs = observations.get(ch)
            blocked = self._blocklist.is_blocked(ch)
            assessment = self._channel_selector.assess_channel(ch, obs)
            
            iid = str(ch)
            if obs:
                activity_str = f"{obs.activity_percentage:.1f}%" if obs.activity_percentage is not None else "N/A"
                bar = self._make_activity_bar(obs.activity_percentage)
                tag = self._get_status_tag(obs, blocked, assessment.eligible)
                values = (
                    ch, obs.frequency_mhz, bar, activity_str,
                    obs.status, obs.valid_samples, obs.rpd_positive,
                    "Yes" if obs.data_sufficient else "No",
                    "Yes" if assessment.eligible else "No",
                    "Yes" if blocked else "No",
                )
            else:
                values = (ch, 2400+ch, "", "N/A", "Pending", 0, 0, "No", "No", "Yes" if blocked else "No")
                tag = "blocked" if blocked else "insufficient"
            
            if iid in existing:
                self._tree.item(iid, values=values, tags=(tag,))
            else:
                self._tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
        
        for iid in existing - needed:
            self._tree.delete(iid)
    
    def _make_activity_bar(self, pct: Optional[float]) -> str:
        width = 20
        if pct is None:
            return "?" * width
        filled = int(pct / 100 * width)
        return "█" * filled + "░" * (width - filled)
    
    def _get_status_tag(self, obs: ChannelObservation, blocked: bool, eligible: bool) -> str:
        if blocked:
            return "blocked"
        if obs.error:
            return "error"
        if not obs.data_sufficient:
            return "insufficient"
        if eligible:
            return "eligible"
        status = obs.status.lower().replace(" ", "")
        if status in ("clear", "moderate", "busy", "heavyload"):
            return status
        return ""
    
    def update(self) -> None:
        """Update spectrum graph and waterfall."""
        self.update_table()
        self.update_spectrum_graph()
        self.update_waterfall()
    
    def update_spectrum_graph(self) -> None:
        """Update the live spectrum bar graph."""
        observations = self._spectrum_data.get_all_observations()
        channels = self._spectrum_data.get_channels_in_range()
        
        self._spec_ax.clear()
        self._spec_ax.set_xlabel("Channel (nRF24)")
        self._spec_ax.set_ylabel("Activity (%)")
        self._spec_ax.set_ylim(0, 100)
        self._spec_ax.grid(True, alpha=0.3)
        self._spec_ax.set_title(f"Live Spectrum - {self._spectrum_data.get_backend().upper()}")
        
        activities = []
        colors = []
        for ch in channels:
            obs = observations.get(ch)
            blocked = self._blocklist.is_blocked(ch)
            
            if obs and obs.activity_percentage is not None:
                activities.append(obs.activity_percentage)
            else:
                activities.append(0)
            
            if blocked:
                colors.append("#b71c1c")
            elif obs and obs.status == "Heavy Load":
                colors.append("#ef5350")
            elif obs and obs.status == "Busy":
                colors.append("#ffa726")
            elif obs and obs.status == "Moderate":
                colors.append("#ffca28")
            elif obs and obs.status == "Clear":
                colors.append("#66bb6a")
            else:
                colors.append("#9e9e9e")
        
        bars = self._spec_ax.bar(channels, activities, color=colors, width=0.8, edgecolor="white", linewidth=0.5)
        self._spec_bars = bars
        
        # WiFi channel markers
        for wifi_ch, freq in self.WIFI_CHANNELS.items():
            nrf_ch = freq - 2400
            if self._config.channel.start_channel <= nrf_ch <= self._config.channel.end_channel:
                self._spec_ax.axvline(x=nrf_ch, color="blue", linestyle="--", alpha=0.5, linewidth=1)
                self._spec_ax.text(nrf_ch, 102, f"WiFi {wifi_ch}", rotation=90, va="bottom", ha="center", fontsize=8, color="blue")
        
        # Threshold lines
        for threshold, label, color in [
            (self._config.thresholds.clear_max, "Clear", "green"),
            (self._config.thresholds.moderate_max, "Moderate", "orange"),
            (self._config.thresholds.busy_max, "Busy", "red"),
        ]:
            self._spec_ax.axhline(y=threshold, color=color, linestyle=":", alpha=0.5, linewidth=1)
        
        self._spec_fig.tight_layout()
        self._spec_canvas.draw_idle()
    
    def update_waterfall(self) -> None:
        """Update the waterfall visualization."""
        observations = self._spectrum_data.get_all_observations()
        channels = self._spectrum_data.get_channels_in_range()
        
        now = time.time()
        row = []
        for ch in channels:
            obs = observations.get(ch)
            row.append(obs.activity_percentage if obs and obs.activity_percentage is not None else 0)
        self._waterfall_data.append(row)
        self._waterfall_timestamps.append(now)
        
        if len(self._waterfall_data) < 2:
            return
        
        self._wf_ax.clear()
        self._wf_ax.set_xlabel("Channel (nRF24)")
        self._wf_ax.set_ylabel("Time (s ago)")
        
        data = np.array(list(self._waterfall_data))
        times = np.array(list(self._waterfall_timestamps))
        time_diffs = now - times
        
        im = self._wf_ax.imshow(
            data.T,
            aspect="auto",
            origin="lower",
            extent=[0, max(time_diffs) if len(time_diffs) > 0 else 60, channels[0], channels[-1]],
            cmap=self._wf_cmap,
            vmin=0,
            vmax=100,
        )
        
        self._wf_ax.set_ylim(channels[0] - 0.5, channels[-1] + 0.5)
        self._wf_fig.colorbar(im, ax=self._wf_ax, label="Activity (%)")
        self._wf_fig.tight_layout()
        self._wf_canvas.draw_idle()
    
    def log_message(self, message: str) -> None:
        """Log a message to the alerts panel."""
        self._alerts_text.config(state=tk.NORMAL)
        self._alerts_text.insert(tk.END, f"{message}\n")
        self._alerts_text.see(tk.END)
        self._alerts_text.config(state=tk.DISABLED)
    
    def refresh(self) -> None:
        """Full refresh of the page."""
        self.update()
    
    def export_png(self, path: str) -> None:
        """Export spectrum graph as PNG."""
        self._spec_fig.savefig(path, dpi=150, bbox_inches="tight")
    
    def export_waterfall_png(self, path: str) -> None:
        """Export waterfall as PNG."""
        self._wf_fig.savefig(path, dpi=150, bbox_inches="tight")