"""Configuration module for RF Spectrum Visualizer."""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ChannelConfig:
    """Channel scanning configuration."""
    start_channel: int = 0
    end_channel: int = 125
    
    MIN_CHANNEL: int = 0
    MAX_CHANNEL: int = 125
    
    def __post_init__(self):
        if not (self.MIN_CHANNEL <= self.start_channel <= self.MAX_CHANNEL):
            raise ValueError(f"start_channel must be between {self.MIN_CHANNEL} and {self.MAX_CHANNEL}")
        if not (self.MIN_CHANNEL <= self.end_channel <= self.MAX_CHANNEL):
            raise ValueError(f"end_channel must be between {self.MIN_CHANNEL} and {self.MAX_CHANNEL}")
        if self.start_channel > self.end_channel:
            raise ValueError("start_channel must be <= end_channel")
    
    @property
    def channel_count(self) -> int:
        return self.end_channel - self.start_channel + 1
    
    def channel_range(self) -> range:
        return range(self.start_channel, self.end_channel + 1)
    
    def contains(self, channel: int) -> bool:
        return self.MIN_CHANNEL <= channel <= self.MAX_CHANNEL
    
    def validate_channel(self, channel: int) -> None:
        if not self.contains(channel):
            from exceptions import InvalidChannelError
            raise InvalidChannelError(channel, self.MIN_CHANNEL, self.MAX_CHANNEL)


@dataclass
class ScanConfig:
    """Scanning timing configuration."""
    measurement_window: float = 1.0
    sampling_interval: float = 0.01
    min_valid_samples: int = 10
    
    def __post_init__(self):
        if self.measurement_window <= 0:
            raise ValueError("measurement_window must be positive")
        if self.sampling_interval <= 0:
            raise ValueError("sampling_interval must be positive")
        if self.min_valid_samples < 1:
            raise ValueError("min_valid_samples must be >= 1")
    
    @property
    def expected_samples_per_channel(self) -> int:
        return int(self.measurement_window / self.sampling_interval)


@dataclass
class ThresholdConfig:
    """Activity classification thresholds."""
    clear_max: int = 24
    moderate_max: int = 49
    busy_max: int = 74
    heavy_min: int = 75
    
    def __post_init__(self):
        if not (0 <= self.clear_max < self.moderate_max < self.busy_max < self.heavy_min <= 100):
            raise ValueError("Thresholds must be ordered: 0 <= clear < moderate < busy < heavy <= 100")
    
    def classify(self, percentage: Optional[float]) -> str:
        if percentage is None:
            return "INSUFFICIENT DATA"
        if percentage <= self.clear_max:
            return "Clear"
        if percentage <= self.moderate_max:
            return "Moderate"
        if percentage <= self.busy_max:
            return "Busy"
        return "Heavy Load"


@dataclass
class MitigationConfig:
    """Mitigation and alert configuration."""
    persistent_threshold: float = 75.0
    persistence_duration: float = 10.0
    consecutive_windows: int = 3
    alert_cooldown: float = 30.0
    hysteresis: float = 5.0
    armed: bool = False
    
    def __post_init__(self):
        if not (0 <= self.persistent_threshold <= 100):
            raise ValueError("persistent_threshold must be 0-100")
        if self.persistence_duration <= 0:
            raise ValueError("persistence_duration must be positive")
        if self.consecutive_windows < 1:
            raise ValueError("consecutive_windows must be >= 1")
        if self.alert_cooldown < 0:
            raise ValueError("alert_cooldown must be non-negative")
        if not (0 <= self.hysteresis <= 50):
            raise ValueError("hysteresis must be 0-50")


@dataclass
class BlocklistConfig:
    """Blocklist persistence configuration."""
    file_path: str = "rf_spectrum_visualizer/blocklist.json"
    atomic_writes: bool = True
    
    def __post_init__(self):
        Path(self.file_path).parent.mkdir(parents=True, exist_ok=True)


@dataclass
class StorageConfig:
    """Data storage configuration."""
    rolling_history_size: int = 100
    waterfall_history_size: int = 200
    log_path: str = "rf_spectrum_visualizer/logs/countermeasures.jsonl"
    export_dir: str = "rf_spectrum_visualizer/exports"
    
    def __post_init__(self):
        if self.rolling_history_size < 1:
            raise ValueError("rolling_history_size must be >= 1")
        if self.waterfall_history_size < 1:
            raise ValueError("waterfall_history_size must be >= 1")
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.export_dir).mkdir(parents=True, exist_ok=True)


@dataclass
class GUIConfig:
    """GUI configuration."""
    refresh_interval_ms: int = 500
    spectrum_max_channels: int = 126
    waterfall_time_window: float = 60.0
    waterfall_history_size: int = 200
    
    def __post_init__(self):
        if self.refresh_interval_ms < 100:
            raise ValueError("refresh_interval_ms must be >= 100")
        if self.spectrum_max_channels < 1:
            raise ValueError("spectrum_max_channels must be >= 1")
        if self.waterfall_history_size < 1:
            raise ValueError("waterfall_history_size must be >= 1")


@dataclass
class SimConfig:
    """Simulation configuration."""
    seed: Optional[int] = None
    deterministic: bool = True
    
    def __post_init__(self):
        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError("seed must be an integer or None")


@dataclass
class HardwareConfig:
    """Hardware radio configuration."""
    ce_pin: int = 25
    csn_pin: int = 0
    spi_speed: int = 4_000_000
    
    def __post_init__(self):
        if not (0 <= self.ce_pin <= 27):
            raise ValueError("ce_pin must be a valid GPIO pin (0-27)")
        if self.csn_pin not in (0, 1):
            raise ValueError("csn_pin must be 0 (CE0) or 1 (CE1)")
        if self.spi_speed < 100000 or self.spi_speed > 16000000:
            raise ValueError("spi_speed must be between 100kHz and 16MHz")


@dataclass
class AppConfig:
    """Main application configuration."""
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    scan: ScanConfig = field(default_factory=ScanConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    mitigation: MitigationConfig = field(default_factory=MitigationConfig)
    blocklist: BlocklistConfig = field(default_factory=BlocklistConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    gui: GUIConfig = field(default_factory=GUIConfig)
    sim: SimConfig = field(default_factory=SimConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    default_backend: str = "sim"
    
    def __post_init__(self):
        if self.default_backend not in ("hardware", "sim"):
            raise ValueError("default_backend must be 'hardware' or 'sim'")


DEFAULT_CONFIG = AppConfig()