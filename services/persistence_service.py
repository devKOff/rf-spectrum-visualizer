"""Persistence service for RF Spectrum Visualizer - configuration and settings management."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from config import AppConfig, ChannelConfig, ScanConfig, ThresholdConfig, MitigationConfig, BlocklistConfig, StorageConfig, GUIConfig, SimConfig, HardwareConfig


class PersistenceService:
    """Manages persistent configuration and settings."""
    
    DEFAULT_CONFIG_PATH = "rf_spectrum_visualizer/config.json"
    
    def __init__(self, config_path: Optional[str] = None):
        self._config_path = Path(config_path or self.DEFAULT_CONFIG_PATH)
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load_or_create()
    
    def _load_or_create(self) -> AppConfig:
        """Load config from file or create default."""
        if self._config_path.exists():
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return self._dict_to_config(data)
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return AppConfig()
    
    def _dict_to_config(self, data: Dict[str, Any]) -> AppConfig:
        """Convert dictionary to AppConfig object."""
        channel_data = data.get("channel", {})
        scan_data = data.get("scan", {})
        thresholds_data = data.get("thresholds", {})
        mitigation_data = data.get("mitigation", {})
        blocklist_data = data.get("blocklist", {})
        storage_data = data.get("storage", {})
        gui_data = data.get("gui", {})
        sim_data = data.get("sim", {})
        hardware_data = data.get("hardware", {})
        
        return AppConfig(
            channel=ChannelConfig(
                start_channel=channel_data.get("start_channel", 0),
                end_channel=channel_data.get("end_channel", 125),
            ),
            scan=ScanConfig(
                measurement_window=scan_data.get("measurement_window", 1.0),
                sampling_interval=scan_data.get("sampling_interval", 0.01),
                min_valid_samples=scan_data.get("min_valid_samples", 10),
            ),
            thresholds=ThresholdConfig(
                clear_max=thresholds_data.get("clear_max", 24),
                moderate_max=thresholds_data.get("moderate_max", 49),
                busy_max=thresholds_data.get("busy_max", 74),
                heavy_min=thresholds_data.get("heavy_min", 75),
            ),
            mitigation=MitigationConfig(
                persistent_threshold=mitigation_data.get("persistent_threshold", 75.0),
                persistence_duration=mitigation_data.get("persistence_duration", 10.0),
                consecutive_windows=mitigation_data.get("consecutive_windows", 3),
                alert_cooldown=mitigation_data.get("alert_cooldown", 30.0),
                hysteresis=mitigation_data.get("hysteresis", 5.0),
                armed=mitigation_data.get("armed", False),
            ),
            blocklist=BlocklistConfig(
                file_path=blocklist_data.get("file_path", "rf_spectrum_visualizer/blocklist.json"),
                atomic_writes=blocklist_data.get("atomic_writes", True),
            ),
            storage=StorageConfig(
                rolling_history_size=storage_data.get("rolling_history_size", 100),
                waterfall_history_size=storage_data.get("waterfall_history_size", 200),
                log_path=storage_data.get("log_path", "rf_spectrum_visualizer/logs/countermeasures.jsonl"),
                export_dir=storage_data.get("export_dir", "rf_spectrum_visualizer/exports"),
            ),
            gui=GUIConfig(
                refresh_interval_ms=gui_data.get("refresh_interval_ms", 500),
                spectrum_max_channels=gui_data.get("spectrum_max_channels", 126),
                waterfall_time_window=gui_data.get("waterfall_time_window", 60.0),
            ),
            sim=SimConfig(
                seed=sim_data.get("seed"),
                deterministic=sim_data.get("deterministic", True),
            ),
            hardware=HardwareConfig(
                ce_pin=hardware_data.get("ce_pin", 25),
                csn_pin=hardware_data.get("csn_pin", 0),
                spi_speed=hardware_data.get("spi_speed", 4_000_000),
            ),
            default_backend=data.get("default_backend", "sim"),
        )
    
    def _config_to_dict(self, config: AppConfig) -> Dict[str, Any]:
        """Convert AppConfig object to dictionary."""
        return {
            "channel": {
                "start_channel": config.channel.start_channel,
                "end_channel": config.channel.end_channel,
            },
            "scan": {
                "measurement_window": config.scan.measurement_window,
                "sampling_interval": config.scan.sampling_interval,
                "min_valid_samples": config.scan.min_valid_samples,
            },
            "thresholds": {
                "clear_max": config.thresholds.clear_max,
                "moderate_max": config.thresholds.moderate_max,
                "busy_max": config.thresholds.busy_max,
                "heavy_min": config.thresholds.heavy_min,
            },
            "mitigation": {
                "persistent_threshold": config.mitigation.persistent_threshold,
                "persistence_duration": config.mitigation.persistence_duration,
                "consecutive_windows": config.mitigation.consecutive_windows,
                "alert_cooldown": config.mitigation.alert_cooldown,
                "hysteresis": config.mitigation.hysteresis,
                "armed": config.mitigation.armed,
            },
            "blocklist": {
                "file_path": config.blocklist.file_path,
                "atomic_writes": config.blocklist.atomic_writes,
            },
            "storage": {
                "rolling_history_size": config.storage.rolling_history_size,
                "waterfall_history_size": config.storage.waterfall_history_size,
                "log_path": config.storage.log_path,
                "export_dir": config.storage.export_dir,
            },
            "gui": {
                "refresh_interval_ms": config.gui.refresh_interval_ms,
                "spectrum_max_channels": config.gui.spectrum_max_channels,
                "waterfall_time_window": config.gui.waterfall_time_window,
            },
            "sim": {
                "seed": config.sim.seed,
                "deterministic": config.sim.deterministic,
            },
            "hardware": {
                "ce_pin": config.hardware.ce_pin,
                "csn_pin": config.hardware.csn_pin,
                "spi_speed": config.hardware.spi_speed,
            },
            "default_backend": config.default_backend,
        }
    
    @property
    def config(self) -> AppConfig:
        return self._config
    
    def save_config(self, config: Optional[AppConfig] = None) -> None:
        """Save configuration to file."""
        if config is not None:
            self._config = config
        
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_to_dict(self._config), f, indent=2)
        except OSError as e:
            raise OSError(f"Failed to save config: {e}")
    
    def update_channel_config(self, start_channel: int, end_channel: int) -> None:
        """Update channel range configuration."""
        self._config.channel.start_channel = start_channel
        self._config.channel.end_channel = end_channel
        self.save_config()
    
    def update_scan_config(self, measurement_window: float, sampling_interval: float, min_valid_samples: int) -> None:
        """Update scan timing configuration."""
        self._config.scan.measurement_window = measurement_window
        self._config.scan.sampling_interval = sampling_interval
        self._config.scan.min_valid_samples = min_valid_samples
        self.save_config()
    
    def update_thresholds(self, clear_max: int, moderate_max: int, busy_max: int, heavy_min: int) -> None:
        """Update activity classification thresholds."""
        self._config.thresholds.clear_max = clear_max
        self._config.thresholds.moderate_max = moderate_max
        self._config.thresholds.busy_max = busy_max
        self._config.thresholds.heavy_min = heavy_min
        self.save_config()
    
    def update_mitigation(self, persistent_threshold: float, hysteresis: float, armed: bool) -> None:
        """Update mitigation configuration."""
        self._config.mitigation.persistent_threshold = persistent_threshold
        self._config.mitigation.hysteresis = hysteresis
        self._config.mitigation.armed = armed
        self.save_config()
    
    def update_backend(self, backend: str) -> None:
        """Update default backend."""
        if backend not in ("hardware", "sim"):
            raise ValueError("backend must be 'hardware' or 'sim'")
        self._config.default_backend = backend
        self.save_config()
    
    def update_hardware_config(self, ce_pin: int, csn_pin: int, spi_speed: int) -> None:
        """Update hardware configuration."""
        self._config.hardware.ce_pin = ce_pin
        self._config.hardware.csn_pin = csn_pin
        self._config.hardware.spi_speed = spi_speed
        self.save_config()
    
    def update_sim_config(self, seed: Optional[int], deterministic: bool) -> None:
        """Update simulation configuration."""
        self._config.sim.seed = seed
        self._config.sim.deterministic = deterministic
        self.save_config()
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults."""
        self._config = AppConfig()
        self.save_config()