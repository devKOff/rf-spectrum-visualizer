"""Data service for RF Spectrum Visualizer - thread-safe spectrum data storage."""

import time
import threading
from typing import Optional, List, Dict, Any
from copy import deepcopy
from collections import deque

from config import AppConfig
from models.channel_record import ChannelObservation
from exceptions import ScannerError


class SpectrumData:
    """Thread-safe storage for spectrum observations and waterfall history."""
    
    def __init__(self, config: AppConfig):
        self._config = config
        self._lock = threading.RLock()
        self._current_observations: Dict[int, ChannelObservation] = {}
        self._rolling_history: Dict[int, deque] = {}
        self._waterfall_history: deque = deque(maxlen=config.storage.waterfall_history_size)
        self._scan_count = 0
        self._last_update = 0.0
        self._backend = "unknown"
    
    def set_backend(self, backend: str) -> None:
        with self._lock:
            self._backend = backend
    
    def get_backend(self) -> str:
        with self._lock:
            return self._backend
    
    def update_observation(self, obs: ChannelObservation) -> None:
        """Add or update a channel observation."""
        with self._lock:
            self._current_observations[obs.channel] = obs
            self._last_update = time.time()
            
            if obs.channel not in self._rolling_history:
                self._rolling_history[obs.channel] = deque(maxlen=self._config.storage.rolling_history_size)
            self._rolling_history[obs.channel].append(obs)
            
            self._waterfall_history.append(obs)
    
    def get_observation(self, channel: int) -> Optional[ChannelObservation]:
        """Get latest observation for a channel (thread-safe copy)."""
        with self._lock:
            obs = self._current_observations.get(channel)
            return deepcopy(obs) if obs else None
    
    def get_all_observations(self) -> Dict[int, ChannelObservation]:
        """Get all current observations (thread-safe copies)."""
        with self._lock:
            return {ch: deepcopy(obs) for ch, obs in self._current_observations.items()}
    
    def get_channels_in_range(self) -> List[int]:
        """Get list of channels in configured range."""
        return list(self._config.channel.channel_range())
    
    def get_rolling_history(self, channel: int) -> List[ChannelObservation]:
        """Get rolling history for a channel."""
        with self._lock:
            history = self._rolling_history.get(channel, deque())
            return [deepcopy(o) for o in history]
    
    def get_waterfall_data(
        self,
        max_age: Optional[float] = None,
        channels: Optional[List[int]] = None,
    ) -> List[ChannelObservation]:
        """Get waterfall history, optionally filtered."""
        with self._lock:
            data = list(self._waterfall_history)
        
        if max_age is not None:
            cutoff = time.time() - max_age
            data = [o for o in data if o.timestamp >= cutoff]
        
        if channels is not None:
            channel_set = set(channels)
            data = [o for o in data if o.channel in channel_set]
        
        return [deepcopy(o) for o in data]
    
    def get_scan_count(self) -> int:
        with self._lock:
            return self._scan_count
    
    def increment_scan_count(self) -> None:
        with self._lock:
            self._scan_count += 1
    
    def get_last_update(self) -> float:
        with self._lock:
            return self._last_update
    
    def clear(self) -> None:
        """Clear all stored data."""
        with self._lock:
            self._current_observations.clear()
            for h in self._rolling_history.values():
                h.clear()
            self._waterfall_history.clear()
            self._scan_count = 0
            self._last_update = 0.0
    
    def export_all(self) -> List[Dict[str, Any]]:
        """Export all current observations as dicts."""
        with self._lock:
            return [obs.to_dict() for obs in self._current_observations.values()]


class DataService:
    """High-level data service coordinating spectrum data and blocklist."""
    
    def __init__(self, config: AppConfig, blocklist_manager):
        self._config = config
        self._spectrum_data = SpectrumData(config)
        self._blocklist_manager = blocklist_manager
    
    @property
    def spectrum_data(self) -> SpectrumData:
        return self._spectrum_data
    
    @property
    def blocklist_manager(self):
        return self._blocklist_manager
    
    def get_observation(self, channel: int) -> Optional[ChannelObservation]:
        return self._spectrum_data.get_observation(channel)
    
    def get_all_observations(self) -> Dict[int, ChannelObservation]:
        return self._spectrum_data.get_all_observations()
    
    def get_channels_in_range(self) -> List[int]:
        return self._spectrum_data.get_channels_in_range()
    
    def is_channel_blocked(self, channel: int) -> bool:
        return self._blocklist_manager.is_blocked(channel)
    
    def get_blocked_channels(self) -> List[int]:
        return self._blocklist_manager.get_blocked_channels()
    
    def get_scan_count(self) -> int:
        return self._spectrum_data.get_scan_count()
    
    def get_backend(self) -> str:
        return self._spectrum_data.get_backend()
    
    def get_last_update(self) -> float:
        return self._spectrum_data.get_last_update()
    
    def clear_all_data(self) -> None:
        self._spectrum_data.clear()
    
    def get_waterfall_data(self, max_age: Optional[float] = None) -> List[ChannelObservation]:
        return self._spectrum_data.get_waterfall_data(max_age=max_age)