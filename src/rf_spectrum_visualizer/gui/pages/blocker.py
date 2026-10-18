"""rf_spectrum_visualizer.gui.pages.blocker

Page 3: Blocker (software-level exclusion only).

Explanatory text (excludes a channel from Analysis recommendations; stays
visible in Live Spectrum; does NOT physically block RF or prevent
transmissions; saved to disk and restored on restart).
Channel spinbox with derived frequency.
Buttons: Add Exclusion / Remove Selected / Clear All.
Feedback line.
List "Excluded Channels (software-level exclusion)" like "5 - 2405 MHz".
Footnote about Analysis vs Live Spectrum.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from rf_spectrum_visualizer.blocker import BlockerManager
from rf_spectrum_visualizer.gui.theme import BG, CARD, GREEN, MUTED, ORANGE, RED, TEXT


class BlockerPage(ttk.Frame):
    """Blocker page with JSON-persisted software exclusions."""

    def __init__(self, parent: tk.Widget, blocker_manager: BlockerManager, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.configure(style="Card.TFrame")

        self.blocker_manager = blocker_manager

        self._build_ui()
        self._refresh_list()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        # Explanatory text
        explain = (
            "Software-level exclusion only.\n"
            "Excluding a channel removes it from Analysis recommendations, but it\n"
            "stays visible in Live Spectrum. This does NOT physically block RF or\n"
            "prevent transmissions. Exclusions are saved to disk and restored on\n"
            "restart.\n\n"
            "Analysis vs Live Spectrum: exclusion affects the Start Analysis page\n"
            "(recommendations only); Live Spectrum always shows all channels."
        )
        tk.Label(
            self,
            text=explain,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 9),
            justify=tk.LEFT,
            wraplength=700,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # Channel spinbox + frequency
        row = tk.Frame(self, bg=CARD)
        row.pack(anchor="w", padx=12, pady=(4, 8))

        tk.Label(row, text="Channel:", bg=CARD, fg=TEXT).pack(side=tk.LEFT)
        self.ch_var = tk.IntVar(value=0)
        self.ch_spin = tk.Spinbox(
            row,
            from_=0,
            to=125,
            width=5,
            textvariable=self.ch_var,
            command=self._on_channel_change,
        )
        self.ch_spin.pack(side=tk.LEFT, padx=(6, 10))

        self.freq_label = tk.Label(row, text="2400 MHz", bg=CARD, fg=MUTED)
        self.freq_label.pack(side=tk.LEFT)

        # Buttons
        btn_row = tk.Frame(self, bg=CARD)
        btn_row.pack(anchor="w", padx=12, pady=(0, 8))

        self.add_btn = tk.Button(
            btn_row,
            text="Add Exclusion",
            bg=GREEN,
            fg="white",
            bd=0,
            padx=12,
            pady=4,
            command=self._add_exclusion,
        )
        self.add_btn.pack(side=tk.LEFT, padx=2)

        self.remove_btn = tk.Button(
            btn_row,
            text="Remove Selected",
            bg=ORANGE,
            fg="white",
            bd=0,
            padx=12,
            pady=4,
            command=self._remove_selected,
        )
        self.remove_btn.pack(side=tk.LEFT, padx=2)

        self.clear_btn = tk.Button(
            btn_row,
            text="Clear All",
            bg=RED,
            fg="white",
            bd=0,
            padx=12,
            pady=4,
            command=self._clear_all,
        )
        self.clear_btn.pack(side=tk.LEFT, padx=2)

        # Feedback line
        self.feedback_var = tk.StringVar(value="")
        self.feedback_label = tk.Label(
            self,
            textvariable=self.feedback_var,
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 9, "italic"),
        )
        self.feedback_label.pack(anchor="w", padx=12, pady=(0, 8))

        # Excluded channels list
        tk.Label(
            self,
            text="Excluded Channels (software-level exclusion):",
            bg=CARD,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=12, pady=(4, 2))

        list_frame = tk.Frame(self, bg=CARD, bd=1, relief=tk.SOLID)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))

        self.listbox = tk.Listbox(
            list_frame,
            bg="#fafafa",
            fg=TEXT,
            font=("Consolas", 10),
            height=8,
            selectmode=tk.SINGLE,
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)
        list_scroll = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.listbox.yview
        )
        list_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.configure(yscrollcommand=list_scroll.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

    # ------------------------------------------------------------------ channel change
    def _on_channel_change(self) -> None:
        ch = self.ch_var.get()
        self.freq_label.config(text=f"{2400 + ch} MHz")

    # ------------------------------------------------------------------ list
    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for ch in sorted(self.blocker_manager.excluded_channels):
            self.listbox.insert(tk.END, f"{ch} - {2400 + ch} MHz")

    def _on_select(self, event) -> None:
        sel = self.listbox.curselection()
        if sel:
            text = self.listbox.get(sel[0])
            ch = int(text.split(" - ")[0])
            self.ch_var.set(ch)
            self.freq_label.config(text=f"{2400 + ch} MHz")

    # ------------------------------------------------------------------ actions
    def _set_feedback(self, message: str, color: str = TEXT) -> None:
        self.feedback_var.set(message)
        self.feedback_label.config(fg=color)

    def _add_exclusion(self) -> None:
        ch = self.ch_var.get()
        if self.blocker_manager.add(ch):
            self._set_feedback(f"Channel {ch} ({2400 + ch} MHz) excluded.", GREEN)
        else:
            self._set_feedback(f"Channel {ch} is already excluded.", MUTED)
        self._refresh_list()

    def _remove_selected(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            self._set_feedback("Select a channel to remove.", MUTED)
            return
        text = self.listbox.get(sel[0])
        ch = int(text.split(" - ")[0])
        if self.blocker_manager.remove(ch):
            self._set_feedback(f"Channel {ch} ({2400 + ch} MHz) removed.", GREEN)
        else:
            self._set_feedback(f"Channel {ch} was not excluded.", MUTED)
        self._refresh_list()

    def _clear_all(self) -> None:
        count = self.blocker_manager.clear()
        if count:
            self._set_feedback(f"Cleared {count} exclusion(s).", GREEN)
        else:
            self._set_feedback("No exclusions to clear.", MUTED)
        self._refresh_list()
