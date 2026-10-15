"""Analysis page for RF Spectrum Visualizer - channel rankings and recommendations."""

import tkinter as tk
from tkinter import ttk
from typing import Dict

from config import AppConfig
from analysis.selector import ChannelSelector, ChannelEligibility
from mitigation.blocklist_manager import BlocklistManager
from services.data_service import DataService
from scanner.scanner_engine import ChannelObservation, SpectrumData
from scanner.channel_utils import format_channel


class AnalysisPage:
    """Analysis page - summary cards, channel rankings, and recommendations."""
    
    def __init__(
        self,
        parent: ttk.Frame,
        config: AppConfig,
        spectrum_data: SpectrumData,
        channel_selector: ChannelSelector,
        blocklist: BlocklistManager,
        data_service: DataService,
    ):
        self._config = config
        self._spectrum_data = spectrum_data
        self._channel_selector = channel_selector
        self._blocklist = blocklist
        self._data_service = data_service
        
        self._create_ui(parent)
    
    @property
    def frame(self) -> ttk.Frame:
        return self._frame
    
    def _create_ui(self, parent: ttk.Frame) -> None:
        """Create the analysis page UI."""
        self._frame = ttk.Frame(parent)
        
        # Create main paned window
        paned = ttk.PanedWindow(self._frame, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # Top: Summary cards
        summary_frame = ttk.LabelFrame(paned, text="Channel Summary")
        paned.add(summary_frame, weight=0)
        self._create_summary_cards(summary_frame)
        
        # Middle: Channel rankings table
        rankings_frame = ttk.LabelFrame(paned, text="Channel Rankings (All 126 Channels)")
        paned.add(rankings_frame, weight=2)
        self._create_rankings_table(rankings_frame)
        
        # Bottom: Recommendations
        rec_frame = ttk.LabelFrame(paned, text="Least-Active Eligible Channel Recommendations")
        paned.add(rec_frame, weight=1)
        self._create_recommendations_panel(rec_frame)
    
    def _create_summary_cards(self, parent: ttk.Frame) -> None:
        """Create summary cards showing key statistics."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Create card widgets
        self._cards = {}
        card_data = [
            ("total", "Total Channels", "0"),
            ("eligible", "Eligible", "0"),
            ("blocked", "Blocked", "0"),
            ("clear", "Clear", "0"),
            ("moderate", "Moderate", "0"),
            ("busy", "Busy/Heavy", "0"),
            ("insufficient", "Insufficient Data", "0"),
            ("errors", "Sensor Errors", "0"),
        ]
        
        for i, (key, label, value) in enumerate(card_data):
            card = ttk.Frame(frame, relief=tk.RAISED, borderwidth=1)
            card.grid(row=0, column=i, padx=5, pady=5, sticky="nsew")
            frame.grid_columnconfigure(i, weight=1)
            
            ttk.Label(card, text=label, font=("Arial", 9)).pack(pady=(5, 0))
            value_label = ttk.Label(card, text=value, font=("Arial", 16, "bold"))
            value_label.pack(pady=(0, 5))
            self._cards[key] = value_label
    
    def _create_rankings_table(self, parent: ttk.Frame) -> None:
        """Create the channel rankings table."""
        # Filter controls
        filter_frame = ttk.Frame(parent)
        filter_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=2)
        
        ttk.Label(filter_frame, text="Show:").pack(side=tk.LEFT, padx=2)
        self._rank_filter_var = tk.StringVar(value="All")
        rank_combo = ttk.Combobox(
            filter_frame, textvariable=self._rank_filter_var,
            values=["All", "Eligible Only", "Blocked Only", "High Activity"],
            width=15, state="readonly"
        )
        rank_combo.pack(side=tk.LEFT, padx=2)
        rank_combo.bind("<<ComboboxSelected>>", lambda e: self.update())
        
        ttk.Button(filter_frame, text="Refresh", command=self.update).pack(side=tk.LEFT, padx=5)
        
        # Table
        columns = ("rank", "channel", "frequency", "activity_pct", "status", "eligible", "blocked", "reason", "peak_pct")
        self._tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        
        self._tree.heading("rank", text="Rank", command=lambda: self._sort_rank("rank"))
        self._tree.heading("channel", text="Ch", command=lambda: self._sort_rank("channel"))
        self._tree.heading("frequency", text="Freq (MHz)", command=lambda: self._sort_rank("frequency"))
        self._tree.heading("activity_pct", text="Activity (%)", command=lambda: self._sort_rank("activity_pct"))
        self._tree.heading("status", text="Status", command=lambda: self._sort_rank("status"))
        self._tree.heading("eligible", text="Eligible", command=lambda: self._sort_rank("eligible"))
        self._tree.heading("blocked", text="Blocked", command=lambda: self._sort_rank("blocked"))
        self._tree.heading("reason", text="Reason", command=lambda: self._sort_rank("reason"))
        self._tree.heading("peak_pct", text="Peak (%)", command=lambda: self._sort_rank("peak_pct"))
        
        self._tree.column("rank", width=50, anchor=tk.CENTER)
        self._tree.column("channel", width=50, anchor=tk.CENTER)
        self._tree.column("frequency", width=80, anchor=tk.CENTER)
        self._tree.column("activity_pct", width=100, anchor=tk.CENTER)
        self._tree.column("status", width=100, anchor=tk.CENTER)
        self._tree.column("eligible", width=70, anchor=tk.CENTER)
        self._tree.column("blocked", width=70, anchor=tk.CENTER)
        self._tree.column("reason", width=180)
        self._tree.column("peak_pct", width=70, anchor=tk.CENTER)
        
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
        
        self._sort_column = "rank"
        self._sort_reverse = False
    
    def _create_recommendations_panel(self, parent: ttk.Frame) -> None:
        """Create recommendations display panel."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._rec_text = tk.Text(frame, height=12, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10))
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._rec_text.yview)
        self._rec_text.configure(yscrollcommand=vsb.set)
        
        self._rec_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        self.update_recommendations()
    
    def _sort_rank(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self.update()
    
    def update(self) -> None:
        """Update the analysis page with current data."""
        observations = self._spectrum_data.get_all_observations()
        assessments = self._channel_selector.assess_all_channels(observations)
        blocked_channels = self._blocklist.get_blocked_channels()
        
        # Update summary cards
        self._update_summary_cards(assessments)
        
        # Update rankings table
        self._update_rankings_table(assessments)
        
        # Update recommendations
        self.update_recommendations()
    
    def _update_summary_cards(self, assessments: list) -> None:
        """Update summary card values."""
        total = len(assessments)
        eligible = sum(1 for a in assessments if a.eligible)
        blocked = sum(1 for a in assessments if a.blocked)
        clear = sum(1 for a in assessments if a.status == "Clear")
        moderate = sum(1 for a in assessments if a.status == "Moderate")
        busy_heavy = sum(1 for a in assessments if a.status in ("Busy", "Heavy Load"))
        insufficient = sum(1 for a in assessments if a.status == "INSUFFICIENT DATA")
        errors = sum(1 for a in assessments if a.status == "SENSOR_ERROR")
        
        self._cards["total"].config(text=str(total))
        self._cards["eligible"].config(text=str(eligible))
        self._cards["blocked"].config(text=str(blocked))
        self._cards["clear"].config(text=str(clear))
        self._cards["moderate"].config(text=str(moderate))
        self._cards["busy"].config(text=str(busy_heavy))
        self._cards["insufficient"].config(text=str(insufficient))
        self._cards["errors"].config(text=str(errors))
    
    def _update_rankings_table(self, assessments: list) -> None:
        """Update the rankings table."""
        filter_mode = self._rank_filter_var.get()
        
        # Filter assessments
        filtered = []
        for a in assessments:
            if filter_mode == "Eligible Only" and not a.eligible:
                continue
            elif filter_mode == "Blocked Only" and not a.blocked:
                continue
            elif filter_mode == "High Activity" and (a.activity_percentage is None or a.activity_percentage < 50):
                continue
            filtered.append(a)
        
        # Sort
        if self._sort_column == "rank":
            # Already ranked by activity (lowest first)
            pass
        elif self._sort_column == "channel":
            filtered.sort(key=lambda a: a.channel, reverse=self._sort_reverse)
        elif self._sort_column == "frequency":
            filtered.sort(key=lambda a: a.frequency_mhz, reverse=self._sort_reverse)
        elif self._sort_column == "activity_pct":
            filtered.sort(key=lambda a: a.activity_percentage or 101, reverse=self._sort_reverse)
        elif self._sort_column == "status":
            filtered.sort(key=lambda a: a.status, reverse=self._sort_reverse)
        elif self._sort_column == "eligible":
            filtered.sort(key=lambda a: a.eligible, reverse=self._sort_reverse)
        elif self._sort_column == "blocked":
            filtered.sort(key=lambda a: a.blocked, reverse=self._sort_reverse)
        elif self._sort_column == "reason":
            filtered.sort(key=lambda a: a.reason.value, reverse=self._sort_reverse)
        elif self._sort_column == "peak_pct":
            filtered.sort(key=lambda a: self._channel_selector.get_peak_activity(a.channel), reverse=self._sort_reverse)
        
        existing = set(self._tree.get_children())
        needed = set(str(a.channel) for a in filtered)
        
        for i, a in enumerate(filtered, 1):
            iid = str(a.channel)
            peak = self._channel_selector.get_peak_activity(a.channel)
            
            tag = self._get_status_tag(a)
            
            values = (
                i, a.channel, a.frequency_mhz,
                f"{a.activity_percentage:.1f}" if a.activity_percentage is not None else "N/A",
                a.status,
                "Yes" if a.eligible else "No",
                "Yes" if a.blocked else "No",
                a.reason.value,
                f"{peak:.1f}",
            )
            
            if iid in existing:
                self._tree.item(iid, values=values, tags=(tag,))
            else:
                self._tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
        
        for iid in existing - needed:
            self._tree.delete(iid)
    
    def _get_status_tag(self, assessment: ChannelEligibility) -> str:
        if assessment.blocked:
            return "blocked"
        if assessment.status == "SENSOR_ERROR":
            return "error"
        if not assessment.data_sufficient:
            return "insufficient"
        if assessment.eligible:
            return "eligible"
        status = assessment.status.lower().replace(" ", "")
        if status in ("clear", "moderate", "busy", "heavyload"):
            return status
        return ""
    
    def update_recommendations(self) -> None:
        """Update the recommendations panel."""
        observations = self._spectrum_data.get_all_observations()
        recommendations = self._channel_selector.get_recommendations(observations, count=10)
        blocked_channels = self._blocklist.get_blocked_channels()
        
        self._rec_text.config(state=tk.NORMAL)
        self._rec_text.delete(1.0, tk.END)
        
        if not recommendations:
            self._rec_text.insert(tk.END, "NO ELIGIBLE CHANNELS\n")
            self._rec_text.insert(tk.END, "All channels are blocked or have high activity.\n")
        else:
            self._rec_text.insert(tk.END, "RECOMMENDED CHANNELS (lowest activity first):\n")
            self._rec_text.insert(tk.END, "=" * 60 + "\n\n")
            for i, rec in enumerate(recommendations, 1):
                peak = self._channel_selector.get_peak_activity(rec.channel)
                self._rec_text.insert(tk.END, 
                    f"{i:2d}. {format_channel(rec.channel)}  "
                    f"Current: {rec.activity_percentage:.1f}%  "
                    f"Peak: {peak:.1f}%  "
                    f"Status: {rec.status}\n"
                )
            
            if blocked_channels:
                self._rec_text.insert(tk.END, f"\nBLOCKED CHANNELS: {blocked_channels}\n")
                self._rec_text.insert(tk.END, "These channels are excluded from recommendations.\n")
        
        self._rec_text.config(state=tk.DISABLED)
    
    def refresh(self) -> None:
        """Full refresh of the page."""
        self.update()