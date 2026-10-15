"""Channel observation data model for RF Spectrum Visualizer."""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum


class ChannelStatus(Enum):
    """Channel activity classification."""
    NORMAL = "NORMAL"
    ELEVATED_ACTIVITY = "ELEVATED_ACTIVITY"
    PERSISTENT_HIGH_ACTIVITY = "PERSISTENT_HIGH_ACTIVITY"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    SENSOR_ERROR = "SENSOR_ERROR"
    BLOCKED = "BLOCKED"


@dataclass
class ChannelObservation:
    """Single channel observation record."""
    timestamp: float
    channel: int
    frequency_mhz: int
    backend: str
    valid_samples: int
    rpd_positive: int
    rpd_negative: int
    activity_percentage: Optional[float]
    status: str
    data_sufficient: bool
    measurement_window: float
    sampling_interval: float
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "channel": self.channel,
            "frequency_mhz": self.frequency_mhz,
            "backend": self.backend,
            "valid_samples": self.valid_samples,
            "rpd_positive": self.rpd_positive,
            "rpd_negative": self.rpd_negative,
            "activity_percentage": self.activity_percentage,
            "status": self.status,
            "data_sufficient": self.data_sufficient,
            "measurement_window": self.measurement_window,
            "sampling_interval": self.sampling_interval,
            "error": self.error,
        }
    
    @property
    def iso_timestamp(self) -> str:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class ChannelInfo:
    """Immutable channel information."""
    channel: int
    frequency_mhz: int
    
    def __post_init__(self):
        if not (0 <= self.channel <= 125):
            raise ValueError(f"Channel must be in [0, 125]")
        if self.frequency_mhz != 2400 + self.channel:
            raise ValueError(f"Frequency must be 2400 + channel")