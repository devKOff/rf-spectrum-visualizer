"""Blocker page for RF Spectrum Visualizer - channel blocklist management."""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from config import AppConfig
from analysis.selector import ChannelSelector
from mitigation.blocklist_manager import BlocklistManager
from services.data_service import DataService
from scanner.scanner_engine import SpectrumData
from scanner.channel_utils import format_channel, parse_channel_input
from exceptions import InvalidChannelError, BlocklistError


class BlockerPage:
    """Blocker page - persistent JSON blocklist management and software channel blocking."""
    
    def __init__(
        self,
        parent: ttk.Frame,
        config: AppConfig,
        blocklist: BlocklistManager,
        channel_selector: ChannelSelector,
        data_service: DataService,
        refresh_callback: Callable[[], None],
    ):
        self._config = config
        self._blocklist = blocklist
        self._channel_selector = channel_selector
        self._data_service = data_service
        self._refresh_callback = refresh_callback
        
        self._create_ui(parent)
        self.refresh_blocklist()
    
    @property
    def frame(self) -> ttk.Frame:
        return self._frame
    
    def _create_ui(self, parent: ttk.Frame) -> None:
        """Create the blocker page UI."""
        self._frame = ttk.Frame(parent)
        
        # Create main paned window
        paned = ttk.PanedWindow(self._frame, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # Top: Blocklist controls
        controls_frame = ttk.LabelFrame(paned, text="Channel Blocklist Control")
        paned.add(controls_frame, weight=0)
        self._create_controls(controls_frame)
        
        # Middle: Blocked channels table
        table_frame = ttk.LabelFrame(paned, text="Blocked Channels (JSON Persistent)")
        paned.add(table_frame, weight=1)
        self._create_blocked_table(table_frame)
        
        # Bottom: Channel eligibility preview
        preview_frame = ttk.LabelFrame(paned, text="Channel Eligibility Preview (Current Scan)")
        paned.add(preview_frame, weight=1)
        self._create_eligibility_preview(preview_frame)
        
        # Info panel
        info_frame = ttk.LabelFrame(paned, text="Information")
        paned.add(info_frame, weight=0)
        self._create_info_panel(info_frame)
    
    def _create_controls(self, parent: ttk.Frame) -> None:
        """Create blocklist control panel."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Channel entry
        ttk.Label(frame, text="Channel:").pack(side=tk.LEFT, padx=2)
        self._block_ch_var = tk.StringVar()
        block_entry = ttk.Entry(frame, textvariable=self._block_ch_var, width=15)
        block_entry.pack(side=tk.LEFT, padx=2)
        block_entry.bind("<Return>", lambda e: self._block_channel())
        
        ttk.Button(frame, text="Block Channel", command=self._block_channel).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame, text="Unblock Channel", command=self._unblock_channel).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame, text="Check Channel", command=self._check_channel).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Reason entry
        ttk.Label(frame, text="Reason:").pack(side=tk.LEFT, padx=2)
        self._block_reason_var = tk.StringVar(value="User blocked")
        ttk.Entry(frame, textvariable=self._block_reason_var, width=25).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Status display
        self._block_status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self._block_status_var, foreground="blue").pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # Bulk actions
        ttk.Button(frame, text="Refresh Blocklist", command=self.refresh_blocklist).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame, text="Clear All Blocks", command=self._clear_all_blocks).pack(side=tk.LEFT, padx=2)
        
        # Import/Export
        ttk.Separator(frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(frame, text="Export Blocklist", command=self._export_blocklist).pack(side=tk.LEFT, padx=2)
        ttk.Button(frame, text="Import Blocklist", command=self._import_blocklist).pack(side=tk.LEFT, padx=2)
    
    def _create_blocked_table(self, parent: ttk.Frame) -> None:
        """Create the blocked channels table."""
        columns = ("channel", "frequency", "blocked_at", "reason")
        self._tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        
        self._tree.heading("channel", text="Ch", command=lambda: self._sort_table("channel"))
        self._tree.heading("frequency", text="Freq (MHz)", command=lambda: self._sort_table("frequency"))
        self._tree.heading("blocked_at", text="Blocked At (UTC)", command=lambda: self._sort_table("blocked_at"))
        self._tree.heading("reason", text="Reason", command=lambda: self._sort_table("reason"))
        
        self._tree.column("channel", width=50, anchor=tk.CENTER)
        self._tree.column("frequency", width=80, anchor=tk.CENTER)
        self._tree.column("blocked_at", width=200, anchor=tk.CENTER)
        self._tree.column("reason", width=250)
        
        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        self._tree.tag_configure("blocked", background="#ffcdd2")
        
        self._sort_column = "channel"
        self._sort_reverse = False
    
    def _create_eligibility_preview(self, parent: ttk.Frame) -> None:
        """Create channel eligibility preview table."""
        columns = ("channel", "frequency", "activity_pct", "status", "eligible", "blocked", "reason")
        self._preview_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        
        self._preview_tree.heading("channel", text="Ch", command=lambda: self._sort_preview("channel"))
        self._preview_tree.heading("frequency", text="Freq (MHz)", command=lambda: self._sort_preview("frequency"))
        self._preview_tree.heading("activity_pct", text="Activity (%)", command=lambda: self._sort_preview("activity_pct"))
        self._preview_tree.heading("status", text="Status", command=lambda: self._sort_preview("status"))
        self._preview_tree.heading("eligible", text="Eligible", command=lambda: self._sort_preview("eligible"))
        self._preview_tree.heading("blocked", text="Blocked", command=lambda: self._sort_preview("blocked"))
        self._preview_tree.heading("reason", text="Reason", command=lambda: self._sort_preview("reason"))
        
        self._preview_tree.column("channel", width=50, anchor=tk.CENTER)
        self._preview_tree.column("frequency", width=80, anchor=tk.CENTER)
        self._preview_tree.column("activity_pct", width=100, anchor=tk.CENTER)
        self._preview_tree.column("status", width=100, anchor=tk.CENTER)
        self._preview_tree.column("eligible", width=70, anchor=tk.CENTER)
        self._preview_tree.column("blocked", width=70, anchor=tk.CENTER)
        self._preview_tree.column("reason", width=180)
        
        vsb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self._preview_tree.yview)
        hsb = ttk.Scrollbar(parent, orient=tk.HORIZONTAL, command=self._preview_tree.xview)
        self._preview_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self._preview_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        
        # Tags for coloring
        self._preview_tree.tag_configure("clear", background="#e8f5e9")
        self._preview_tree.tag_configure("moderate", background="#fff3e0")
        self._preview_tree.tag_configure("busy", background="#ffebee")
        self._preview_tree.tag_configure("heavy", background="#fce4ec")
        self._preview_tree.tag_configure("insufficient", background="#f5f5f5")
        self._preview_tree.tag_configure("error", background="#ffcdd2")
        self._preview_tree.tag_configure("blocked", background="#ffcdd2")
        self._preview_tree.tag_configure("eligible", background="#e3f2fd")
        
        self._preview_sort_column = "channel"
        self._preview_sort_reverse = False
    
    def _create_info_panel(self, parent: ttk.Frame) -> None:
        """Create information panel with safety notice."""
        info_text = (
            "SOFTWARE CHANNEL BLOCKING\n"
            "==========================\n\n"
            "This blocklist provides SOFTWARE-LEVEL channel blocking only.\n\n"
            "⚠ IMPORTANT: 'BLOCKED IN SOFTWARE' prevents the application\n"
            "from selecting or recommending these channels. It does NOT:\n"
            "  • Physically jam or block radio frequencies\n"
            "  • Disrupt external devices or communications\n"
            "  • Transmit any blocking signals\n"
            "  • Affect the nRF24L01+ hardware operation\n\n"
            "Blocked channels are:\n"
            "  • Excluded from channel avoidance recommendations\n"
            "  • Marked as 'BLOCKED' in Spectrum and Analysis views\n"
            "  • Persisted to JSON file across application restarts\n\n"
            "Use cases:\n"
            "  • Reserve channels for specific protocols\n"
            "  • Avoid known interference sources\n"
            "  • Implement channel hopping exclusion lists\n\n"
            "Blocklist file: rf_spectrum_visualizer/blocklist.json"
        )
        
        self._info_text = tk.Text(parent, height=18, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9))
        self._info_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._info_text.config(state=tk.NORMAL)
        self._info_text.insert(tk.END, info_text)
        self._info_text.config(state=tk.DISABLED)
    
    def _sort_table(self, column: str) -> None:
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self.refresh_blocklist()
    
    def _sort_preview(self, column: str) -> None:
        if self._preview_sort_column == column:
            self._preview_sort_reverse = not self._preview_sort_reverse
        else:
            self._preview_sort_column = column
            self._preview_sort_reverse = False
        self.update_preview()
    
    def _block_channel(self) -> None:
        """Block the entered channel."""
        try:
            channel = parse_channel_input(self._block_ch_var.get())
        except ValueError as e:
            self._block_status_var.set(f"Error: {e}")
            return
        except InvalidChannelError as e:
            self._block_status_var.set(f"Error: {e}")
            return
        
        try:
            entry = self._blocklist.block_channel(channel, self._block_reason_var.get())
            self._block_status_var.set(f"Blocked {format_channel(channel)} - {entry.reason}")
            self.refresh_blocklist()
            if self._refresh_callback:
                self._refresh_callback()
        except (InvalidChannelError, BlocklistError) as e:
            self._block_status_var.set(f"Error: {e}")
    
    def _unblock_channel(self) -> None:
        """Unblock the entered channel."""
        try:
            channel = parse_channel_input(self._block_ch_var.get())
        except ValueError as e:
            self._block_status_var.set(f"Error: {e}")
            return
        except InvalidChannelError as e:
            self._block_status_var.set(f"Error: {e}")
            return
        
        try:
            if self._blocklist.unblock_channel(channel):
                self._block_status_var.set(f"Unblocked {format_channel(channel)}")
            else:
                self._block_status_var.set(f"{format_channel(channel)} was not blocked")
            self.refresh_blocklist()
            if self._refresh_callback:
                self._refresh_callback()
        except (InvalidChannelError, BlocklistError) as e:
            self._block_status_var.set(f"Error: {e}")
    
    def _check_channel(self) -> None:
        """Check channel block status."""
        try:
            channel = parse_channel_input(self._block_ch_var.get())
        except ValueError as e:
            self._block_status_var.set(f"Error: {e}")
            return
        except InvalidChannelError as e:
            self._block_status_var.set(f"Error: {e}")
            return
        
        blocked = self._blocklist.is_blocked(channel)
        entry = self._blocklist.get_entry(channel)
        
        if blocked:
            self._block_status_var.set(f"{format_channel(channel)} is BLOCKED (since {entry.blocked_at})")
        else:
            self._block_status_var.set(f"{format_channel(channel)} is NOT blocked")
    
    def _clear_all_blocks(self) -> None:
        """Clear all blocked channels."""
        if messagebox.askyesno("Confirm", "Clear all blocked channels?"):
            count = self._blocklist.clear()
            self._block_status_var.set(f"Cleared {count} blocked channels")
            self.refresh_blocklist()
            if self._refresh_callback:
                self._refresh_callback()
    
    def _export_blocklist(self) -> None:
        """Export blocklist to JSON file."""
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Export Blocklist"
        )
        if path:
            try:
                json_str = self._blocklist.export_json()
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                messagebox.showinfo("Export", f"Blocklist exported to {path}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))
    
    def _import_blocklist(self) -> None:
        """Import blocklist from JSON file."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Import Blocklist"
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    json_str = f.read()
                count = self._blocklist.import_json(json_str)
                self._block_status_var.set(f"Imported {count} blocklist entries")
                self.refresh_blocklist()
                if self._refresh_callback:
                    self._refresh_callback()
            except Exception as e:
                messagebox.showerror("Import Error", str(e))
    
    def refresh_blocklist(self) -> None:
        """Refresh the blocked channels table."""
        entries = self._blocklist.get_blocked_entries()
        
        # Sort
        if self._sort_column == "channel":
            entries.sort(key=lambda e: e.channel, reverse=self._sort_reverse)
        elif self._sort_column == "frequency":
            entries.sort(key=lambda e: e.frequency_mhz, reverse=self._sort_reverse)
        elif self._sort_column == "blocked_at":
            entries.sort(key=lambda e: e.blocked_at, reverse=self._sort_reverse)
        elif self._sort_column == "reason":
            entries.sort(key=lambda e: e.reason, reverse=self._sort_reverse)
        
        existing = set(self._tree.get_children())
        needed = set(str(e.channel) for e in entries)
        
        for entry in entries:
            iid = str(entry.channel)
            values = (
                entry.channel,
                entry.frequency_mhz,
                entry.blocked_at,
                entry.reason,
            )
            
            if iid in existing:
                self._tree.item(iid, values=values, tags=("blocked",))
            else:
                self._tree.insert("", tk.END, iid=iid, values=values, tags=("blocked",))
        
        for iid in existing - needed:
            self._tree.delete(iid)
        
        # Also update preview
        self.update_preview()
    
    def update_preview(self) -> None:
        """Update the eligibility preview table with current scan data."""
        from scanner.scanner_engine import ChannelObservation
        
        observations = self._data_service.get_all_observations()
        assessments = self._channel_selector.assess_all_channels(observations)
        
        # Sort
        if self._preview_sort_column == "channel":
            assessments.sort(key=lambda a: a.channel, reverse=self._preview_sort_reverse)
        elif self._preview_sort_column == "frequency":
            assessments.sort(key=lambda a: a.frequency_mhz, reverse=self._preview_sort_reverse)
        elif self._preview_sort_column == "activity_pct":
            assessments.sort(key=lambda a: a.activity_percentage or 101, reverse=self._preview_sort_reverse)
        elif self._preview_sort_column == "status":
            assessments.sort(key=lambda a: a.status, reverse=self._preview_sort_reverse)
        elif self._preview_sort_column == "eligible":
            assessments.sort(key=lambda a: a.eligible, reverse=self._preview_sort_reverse)
        elif self._preview_sort_column == "blocked":
            assessments.sort(key=lambda a: a.blocked, reverse=self._preview_sort_reverse)
        elif self._preview_sort_column == "reason":
            assessments.sort(key=lambda a: a.reason.value, reverse=self._preview_sort_reverse)
        
        existing = set(self._preview_tree.get_children())
        needed = set(str(a.channel) for a in assessments)
        
        for a in assessments:
            iid = str(a.channel)
            tag = self._get_status_tag(a)
            
            values = (
                a.channel,
                a.frequency_mhz,
                f"{a.activity_percentage:.1f}" if a.activity_percentage is not None else "N/A",
                a.status,
                "Yes" if a.eligible else "No",
                "Yes" if a.blocked else "No",
                a.reason.value,
            )
            
            if iid in existing:
                self._preview_tree.item(iid, values=values, tags=(tag,))
            else:
                self._preview_tree.insert("", tk.END, iid=iid, values=values, tags=(tag,))
        
        for iid in existing - needed:
            self._preview_tree.delete(iid)
    
    def _get_status_tag(self, assessment) -> str:
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
    
    def update(self) -> None:
        """Update the preview table."""
        self.update_preview()
    
    def refresh(self) -> None:
        """Full refresh of the page."""
        self.refresh_blocklist()
        self.update_preview()