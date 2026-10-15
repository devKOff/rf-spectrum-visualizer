"""Main window for RF Spectrum Visualizer - three-section tabbed interface."""

import tkinter as tk
from tkinter import ttk, messagebox
import logging

from config import AppConfig
from services.data_service import DataService
from services.persistence_service import PersistenceService
from mitigation.blocklist_manager import BlocklistManager
from analysis.selector import ChannelSelector
from scanner.scanner_engine import SpectrumData
from radio import SimRadio, HardwareRadio, check_hardware_availability
from exports.report_generator import ReportGenerator
from ui.spectrum_page import SpectrumPage
from ui.analysis_page import AnalysisPage
from ui.blocker_page import BlockerPage
from exceptions import HardwareError, ScannerError


logger = logging.getLogger("rf_visualizer.gui")


class MainWindow:
    """Main application window with three tabs: Spectrum, Analysis, Blocker."""
    
    WIFI_CHANNELS = {
        1: 2412,
        6: 2437,
        11: 2462,
    }
    
    def __init__(self, config: AppConfig):
        self._config = config
        self._root = tk.Tk()
        self._root.title("RF Spectrum Visualizer - 2.4 GHz ISM Band")
        self._root.geometry("1400x900")
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Core services
        self._persistence = PersistenceService()
        self._blocklist = BlocklistManager(config.blocklist)
        self._spectrum_data = SpectrumData(config)
        self._data_service = DataService(config, self._blocklist)
        self._channel_selector = ChannelSelector(config.channel, config.thresholds, self._blocklist)
        self._report_gen = ReportGenerator(config, self._spectrum_data, self._blocklist, self._channel_selector)
        
        # Scanner state
        self._scanner = None
        self._radio = None
        self._running = False
        self._refresh_job = None
        
        # Setup logging
        self._setup_logging()
        
        # Build UI
        self._build_ui()
        self._update_ui_state()
        self._blocker_page.refresh_blocklist()
    
    def _setup_logging(self) -> None:
        from logging_config import setup_logging
        setup_logging(
            log_path=self._config.storage.log_path,
            level=logging.INFO,
            console_level=logging.WARNING,
        )
    
    def _build_ui(self) -> None:
        """Build the main UI layout."""
        self._create_menu()
        self._create_toolbar()
        self._create_notebook()
        self._create_status_bar()
    
    def _create_menu(self) -> None:
        menubar = tk.Menu(self._root)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export All Formats...", command=self._export_all_formats)
        file_menu.add_command(label="Export JSON...", command=self._export_json)
        file_menu.add_command(label="Export CSV...", command=self._export_csv)
        file_menu.add_command(label="Export PNG (Spectrum)...", command=lambda: self._export_png("spectrum"))
        file_menu.add_command(label="Export PNG (Waterfall)...", command=lambda: self._export_png("waterfall"))
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Clear History", command=self._clear_history)
        view_menu.add_command(label="Reset Peak Tracking", command=self._reset_peaks)
        menubar.add_cascade(label="View", menu=view_menu)
        
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Hardware Diagnostic", command=self._run_diagnostic)
        tools_menu.add_command(label="Run Simulation Scenario", command=self._run_simulation_dialog)
        tools_menu.add_command(label="Settings...", command=self._show_settings)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self._root.config(menu=menubar)
    
    def _create_toolbar(self) -> None:
        toolbar = ttk.Frame(self._root)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(toolbar, text="Backend:").pack(side=tk.LEFT, padx=2)
        self._backend_var = tk.StringVar(value=self._config.default_backend)
        backend_combo = ttk.Combobox(
            toolbar, textvariable=self._backend_var,
            values=["sim", "hardware"], width=10, state="readonly"
        )
        backend_combo.pack(side=tk.LEFT, padx=2)
        backend_combo.bind("<<ComboboxSelected>>", self._on_backend_change)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        self._start_btn = ttk.Button(toolbar, text="Start Scanning", command=self._start_scanning)
        self._start_btn.pack(side=tk.LEFT, padx=2)
        
        self._stop_btn = ttk.Button(toolbar, text="Stop", command=self._stop_scanning, state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        ttk.Label(toolbar, text="Channels:").pack(side=tk.LEFT, padx=2)
        self._start_ch_var = tk.IntVar(value=self._config.channel.start_channel)
        ttk.Spinbox(toolbar, from_=0, to=125, textvariable=self._start_ch_var, width=5).pack(side=tk.LEFT)
        ttk.Label(toolbar, text="-").pack(side=tk.LEFT)
        self._end_ch_var = tk.IntVar(value=self._config.channel.end_channel)
        ttk.Spinbox(toolbar, from_=0, to=125, textvariable=self._end_ch_var, width=5).pack(side=tk.LEFT)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        ttk.Label(toolbar, text="Window (s):").pack(side=tk.LEFT, padx=2)
        self._window_var = tk.DoubleVar(value=self._config.scan.measurement_window)
        ttk.Spinbox(toolbar, from_=0.1, to=10.0, increment=0.1, textvariable=self._window_var, width=5).pack(side=tk.LEFT)
        
        ttk.Label(toolbar, text="Interval (ms):").pack(side=tk.LEFT, padx=2)
        self._interval_var = tk.DoubleVar(value=self._config.scan.sampling_interval * 1000)
        ttk.Spinbox(toolbar, from_=1, to=1000, increment=1, textvariable=self._interval_var, width=6).pack(side=tk.LEFT)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        ttk.Button(toolbar, text="Export All", command=self._export_all_formats).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Export JSON", command=self._export_json).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Export CSV", command=self._export_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Export PNG", command=lambda: self._export_png("spectrum")).pack(side=tk.LEFT, padx=2)
    
    def _create_notebook(self) -> None:
        """Create the three-tab notebook."""
        self._notebook = ttk.Notebook(self._root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create pages
        self._spectrum_page = SpectrumPage(
            self._notebook, self._config, self._spectrum_data, self._channel_selector,
            self._blocklist, self._data_service, self._get_waterfall_data
        )
        self._analysis_page = AnalysisPage(
            self._notebook, self._config, self._spectrum_data, self._channel_selector,
            self._blocklist, self._data_service
        )
        self._blocker_page = BlockerPage(
            self._notebook, self._config, self._blocklist, self._channel_selector,
            self._data_service, self._refresh_all_pages
        )
        
        # Add tabs
        self._notebook.add(self._spectrum_page.frame, text="Spectrum")
        self._notebook.add(self._analysis_page.frame, text="Analysis")
        self._notebook.add(self._blocker_page.frame, text="Blocker")
        
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
    
    def _create_status_bar(self) -> None:
        self._status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self._root, textvariable=self._status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
    
    def _update_ui_state(self) -> None:
        """Update UI element states based on running state."""
        if self._running:
            self._start_btn.config(state=tk.DISABLED)
            self._stop_btn.config(state=tk.NORMAL)
            self._status_var.set(f"Scanning... ({self._spectrum_data.get_backend().upper()})")
        else:
            self._start_btn.config(state=tk.NORMAL)
            self._stop_btn.config(state=tk.DISABLED)
            self._status_var.set("Stopped")
    
    def _on_backend_change(self, event=None) -> None:
        if self._running:
            messagebox.showwarning("Cannot Change", "Stop scanning before changing backend")
            self._backend_var.set(self._config.default_backend)
            return
        self._config.default_backend = self._backend_var.get()
        self._persistence.update_backend(self._config.default_backend)
        logger.info(f"Backend changed to {self._config.default_backend}")
    
    def _on_tab_changed(self, event=None) -> None:
        """Refresh the active tab when switched."""
        tab_id = self._notebook.index(self._notebook.select())
        if tab_id == 0:  # Spectrum
            self._spectrum_page.refresh()
        elif tab_id == 1:  # Analysis
            self._analysis_page.refresh()
        elif tab_id == 2:  # Blocker
            self._blocker_page.refresh()
    
    def _refresh_all_pages(self) -> None:
        """Refresh all three pages."""
        self._spectrum_page.refresh()
        self._analysis_page.refresh()
        self._blocker_page.refresh()
    
    def _start_scanning(self) -> None:
        if self._running:
            return
        
        try:
            self._config.channel.start_channel = self._start_ch_var.get()
            self._config.channel.end_channel = self._end_ch_var.get()
            self._config.scan.measurement_window = self._window_var.get()
            self._config.scan.sampling_interval = self._interval_var.get() / 1000.0
            
            self._persistence.update_channel_config(
                self._config.channel.start_channel,
                self._config.channel.end_channel
            )
            self._persistence.update_scan_config(
                self._config.scan.measurement_window,
                self._config.scan.sampling_interval,
                self._config.scan.min_valid_samples
            )
            
            if self._config.default_backend == "hardware":
                self._radio = HardwareRadio(self._config.channel, self._config.scan, self._config.hardware)
                if not self._radio.is_available():
                    messagebox.showerror("Hardware Unavailable", "pyrf24 not installed or SPI unavailable")
                    return
            else:
                self._radio = SimRadio(self._config.channel, self._config.scan, self._config.sim)
            
            from scanner.scanner_engine import ScannerThread
            self._scanner = ScannerThread(
                self._config,
                self._spectrum_data,
                self._radio,
                on_observation=self._on_observation,
                on_error=self._on_scanner_error,
                on_scan_complete=self._on_scan_complete,
            )
            
            self._scanner.start()
            self._running = True
            self._update_ui_state()
            self._schedule_refresh()
            self._log_message(f"Started scanning with {self._config.default_backend} backend")
            
        except Exception as e:
            logger.error(f"Failed to start scanner: {e}")
            messagebox.showerror("Error", f"Failed to start scanning: {e}")
    
    def _stop_scanning(self) -> None:
        if not self._running:
            return
        
        if self._scanner:
            self._scanner.shutdown()
            self._scanner = None
        
        if self._radio:
            self._radio.cleanup()
            self._radio = None
        
        self._running = False
        self._update_ui_state()
        if self._refresh_job:
            self._root.after_cancel(self._refresh_job)
            self._refresh_job = None
        self._log_message("Scanning stopped")
    
    def _schedule_refresh(self) -> None:
        if not self._running:
            return
        self._refresh_job = self._root.after(self._config.gui.refresh_interval_ms, self._refresh_ui)
    
    def _refresh_ui(self) -> None:
        if not self._running:
            return
        
        self._spectrum_page.update()
        self._analysis_page.update()
        self._blocker_page.update()
        
        self._schedule_refresh()
    
    def _on_observation(self, obs) -> None:
        pass
    
    def _on_scanner_error(self, error: Exception) -> None:
        self._log_message(f"Scanner error: {error}", "ERROR")
    
    def _on_scan_complete(self) -> None:
        pass
    
    def _get_waterfall_data(self, max_age: float = 60.0):
        return self._spectrum_data.get_waterfall_data(max_age=max_age)
    
    def _export_csv(self) -> None:
        path = self._get_export_path(".csv", "Export CSV")
        if path:
            try:
                self._report_gen.export_csv_file(str(path))
                messagebox.showinfo("Export", f"CSV exported to {path}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))
    
    def _export_json(self) -> None:
        path = self._get_export_path(".json", "Export JSON")
        if path:
            try:
                self._report_gen.export_json_file(str(path))
                messagebox.showinfo("Export", f"JSON exported to {path}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))
    
    def _export_all_formats(self) -> None:
        path = self._get_export_path("", "Export All Formats (base filename)")
        if path:
            try:
                base_path = path.with_suffix("")
                results = self._report_gen.export_all_formats(base_path.stem)
                msg = "Exported:\n" + "\n".join(f"  {fmt}: {p}" for fmt, p in results.items())
                messagebox.showinfo("Export", msg)
            except Exception as e:
                messagebox.showerror("Export Error", str(e))
    
    def _export_png(self, plot_type: str) -> None:
        path = self._get_export_path(".png", f"Export {plot_type.capitalize()} PNG")
        if path:
            try:
                if plot_type == "spectrum":
                    self._spectrum_page.export_png(str(path))
                else:
                    self._spectrum_page.export_waterfall_png(str(path))
                messagebox.showinfo("Export", f"PNG exported to {path}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))
    
    def _get_export_path(self, extension: str, title: str):
        from tkinter import filedialog
        from pathlib import Path
        path = filedialog.asksaveasfilename(
            defaultextension=extension,
            filetypes=[("All files", "*.*")],
            title=title
        )
        return Path(path) if path else None
    
    def _clear_history(self) -> None:
        self._spectrum_data.clear()
        self._channel_selector.reset_peaks()
        self._refresh_all_pages()
        self._log_message("History cleared")
    
    def _reset_peaks(self) -> None:
        self._channel_selector.reset_peaks()
        self._log_message("Peak tracking reset")
    
    def _run_diagnostic(self) -> None:
        result = check_hardware_availability()
        msg = f"Platform: {result['platform']}\n"
        msg += f"pyrf24 installed: {result['pyrf24_installed']}\n"
        if result['pyrf24_version']:
            msg += f"pyrf24 version: {result['pyrf24_version']}\n"
        msg += f"SPI devices: {result['spi_devices'] or 'None found'}\n"
        msg += f"GPIO access: {result['gpio_access']}\n"
        if result['errors']:
            msg += "\nErrors:\n" + "\n".join(f"  - {e}" for e in result['errors'])
        
        messagebox.showinfo("Hardware Diagnostic", msg)
    
    def _run_simulation_dialog(self) -> None:
        dialog = tk.Toplevel(self._root)
        dialog.title("Run Simulation Scenario")
        dialog.geometry("400x350")
        dialog.transient(self._root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Select scenario:").pack(pady=10)
        
        from radio.sim_radio import ScenarioType
        scenario_var = tk.StringVar(value="mixed")
        for scenario in ScenarioType:
            ttk.Radiobutton(dialog, text=f"{scenario.value}: {SimRadio.SCENARIOS[scenario]['description']}", 
                           variable=scenario_var, value=scenario.value).pack(anchor=tk.W, padx=20, pady=2)
        
        def run_scenario():
            scenario = ScenarioType(scenario_var.get())
            dialog.destroy()
            self._run_simulation_scenario(scenario)
        
        ttk.Button(dialog, text="Run", command=run_scenario).pack(pady=10)
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(pady=5)
    
    def _run_simulation_scenario(self, scenario) -> None:
        if self._running:
            messagebox.showwarning("Busy", "Stop scanning first")
            return
        
        self._log_message(f"Running simulation scenario: {scenario.value}")
        
        radio = SimRadio(self._config.channel, self._config.scan, self._config.sim, scenario=scenario)
        radio.initialize()
        
        for channel in self._config.channel.channel_range():
            valid, positive, negative = radio.scan_channel(
                channel,
                self._config.scan.measurement_window,
                self._config.scan.sampling_interval,
            )
            
            if valid >= self._config.scan.min_valid_samples:
                activity = (positive / valid) * 100.0
                data_sufficient = True
            else:
                activity = None
                data_sufficient = False
            
            status = self._config.thresholds.classify(activity)
            if not data_sufficient:
                status = "INSUFFICIENT DATA"
            
            obs = ChannelObservation(
                timestamp=time.time(),
                channel=channel,
                frequency_mhz=2400 + channel,
                backend="sim",
                valid_samples=valid,
                rpd_positive=positive,
                rpd_negative=negative,
                activity_percentage=activity,
                status=status,
                data_sufficient=data_sufficient,
                measurement_window=self._config.scan.measurement_window,
                sampling_interval=self._config.scan.sampling_interval,
                error=None,
            )
            self._spectrum_data.update_observation(obs)
        
        radio.cleanup()
        self._refresh_all_pages()
        self._log_message(f"Simulation scenario {scenario.value} complete")
    
    def _show_settings(self) -> None:
        dialog = tk.Toplevel(self._root)
        dialog.title("Settings")
        dialog.geometry("500x500")
        dialog.transient(self._root)
        dialog.grab_set()
        
        # Create notebook for settings tabs
        nb = ttk.Notebook(dialog)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Thresholds tab
        thresh_frame = ttk.Frame(nb)
        nb.add(thresh_frame, text="Thresholds")
        
        ttk.Label(thresh_frame, text="Clear max (%):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        clear_var = tk.IntVar(value=self._config.thresholds.clear_max)
        ttk.Spinbox(thresh_frame, from_=0, to=100, textvariable=clear_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(thresh_frame, text="Moderate max (%):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        mod_var = tk.IntVar(value=self._config.thresholds.moderate_max)
        ttk.Spinbox(thresh_frame, from_=0, to=100, textvariable=mod_var, width=10).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(thresh_frame, text="Busy max (%):").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        busy_var = tk.IntVar(value=self._config.thresholds.busy_max)
        ttk.Spinbox(thresh_frame, from_=0, to=100, textvariable=busy_var, width=10).grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(thresh_frame, text="Heavy min (%):").grid(row=3, column=0, padx=5, pady=5, sticky=tk.W)
        heavy_var = tk.IntVar(value=self._config.thresholds.heavy_min)
        ttk.Spinbox(thresh_frame, from_=0, to=100, textvariable=heavy_var, width=10).grid(row=3, column=1, padx=5, pady=5)
        
        # Mitigation tab
        mit_frame = ttk.Frame(nb)
        nb.add(mit_frame, text="Mitigation")
        
        ttk.Label(mit_frame, text="Persistent threshold (%):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        persist_var = tk.DoubleVar(value=self._config.mitigation.persistent_threshold)
        ttk.Spinbox(mit_frame, from_=0, to=100, increment=0.1, textvariable=persist_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(mit_frame, text="Hysteresis (%):").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        hyst_var = tk.DoubleVar(value=self._config.mitigation.hysteresis)
        ttk.Spinbox(mit_frame, from_=0, to=50, increment=0.1, textvariable=hyst_var, width=10).grid(row=1, column=1, padx=5, pady=5)
        
        # Hardware tab
        hw_frame = ttk.Frame(nb)
        nb.add(hw_frame, text="Hardware")
        
        ttk.Label(hw_frame, text="CE Pin:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        ce_var = tk.IntVar(value=self._config.hardware.ce_pin)
        ttk.Spinbox(hw_frame, from_=0, to=27, textvariable=ce_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(hw_frame, text="CSN Pin:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        csn_var = tk.IntVar(value=self._config.hardware.csn_pin)
        ttk.Spinbox(hw_frame, from_=0, to=1, textvariable=csn_var, width=10).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(hw_frame, text="SPI Speed (Hz):").grid(row=2, column=0, padx=5, pady=5, sticky=tk.W)
        spi_var = tk.IntVar(value=self._config.hardware.spi_speed)
        ttk.Spinbox(hw_frame, from_=100000, to=16000000, increment=100000, textvariable=spi_var, width=15).grid(row=2, column=1, padx=5, pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def apply_settings():
            self._config.thresholds.clear_max = clear_var.get()
            self._config.thresholds.moderate_max = mod_var.get()
            self._config.thresholds.busy_max = busy_var.get()
            self._config.thresholds.heavy_min = heavy_var.get()
            self._config.mitigation.persistent_threshold = persist_var.get()
            self._config.mitigation.hysteresis = hyst_var.get()
            self._config.hardware.ce_pin = ce_var.get()
            self._config.hardware.csn_pin = csn_var.get()
            self._config.hardware.spi_speed = spi_var.get()
            self._persistence.save_config(self._config)
            self._channel_selector.persistent_threshold = self._config.mitigation.persistent_threshold
            self._channel_selector.hysteresis = self._config.mitigation.hysteresis
            self._refresh_all_pages()
            dialog.destroy()
        
        ttk.Button(btn_frame, text="Apply", command=apply_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
    
    def _show_about(self) -> None:
        messagebox.showinfo(
            "About RF Spectrum Visualizer",
            "RF Spectrum Visualizer\n"
            "2.4 GHz ISM Band Monitor for nRF24L01+\n\n"
            "Three Sections:\n"
            "  • Spectrum - Live spectrum display with waterfall\n"
            "  • Analysis - Channel rankings & recommendations\n"
            "  • Blocker - Software channel blocking & management\n\n"
            "Features:\n"
            "  • 126-channel scanning (0-125, freq = 2400 + channel)\n"
            "  • Persistent JSON blocklist\n"
            "  • Channel avoidance algorithm\n"
            "  • Deterministic simulation modes\n"
            "  • Hardware support (Raspberry Pi 3B+ + nRF24L01+)\n"
            "  • CSV/JSON/PNG export\n"
            "  • Real-time spectrum & waterfall\n\n"
            "IMPORTANT: 'BLOCKED IN SOFTWARE' prevents application\n"
            "selection only; it does NOT physically jam or block\n"
            "radio frequencies or disrupt external devices.\n\n"
            "Hardware: Raspberry Pi 3B+ + nRF24L01+\n"
            "Pins: CE=GPIO25, CSN=GPIO8 (SPI CE0)\n\n"
            "Note: nRF24L01+ is a narrowband transceiver.\n"
            "RPD observations are not calibrated power measurements."
        )
    
    def _log_message(self, message: str, level: str = "INFO") -> None:
        import time
        timestamp = time.strftime("%H:%M:%S")
        self._spectrum_page.log_message(f"[{timestamp}] {level}: {message}")
    
    def _on_close(self) -> None:
        self._stop_scanning()
        self._root.destroy()
    
    def run(self) -> None:
        self._root.mainloop()