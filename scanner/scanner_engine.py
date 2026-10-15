"""Scanner core: SpectrumData and ScannerThread for RF Spectrum Visualizer."""

import time
import threading
import logging
from typing import Optional, List, Dict, Any, Callable
from copy import deepcopy
from collections import deque

from config import AppConfig
from exceptions import (
    ScannerError,
    ScannerNotRunningError,
    ScannerAlreadyRunningError,
    InsufficientDataError,
)
from radio import SimRadio, HardwareRadio
from scanner.channel_utils import validate_channel
from models.channel_record import ChannelObservation

logger = logging.getLogger("rf_visualizer.scanner")


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


class ScannerThread:
    """Background scanner worker thread."""
    
    def __init__(
        self,
        config: AppConfig,
        spectrum_data: SpectrumData,
        radio: Optional[Any] = None,
        on_observation: Optional[Callable[[ChannelObservation], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_scan_complete: Optional[Callable[[], None]] = None,
    ):
        self._config = config
        self._spectrum_data = spectrum_data
        self._radio = radio
        self._on_observation = on_observation
        self._on_error = on_error
        self._on_scan_complete = on_scan_complete
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        self._backend = config.default_backend
    
    @property
    def backend(self) -> str:
        return self._backend
    
    @backend.setter
    def backend(self, value: str) -> None:
        if value not in ("hardware", "sim"):
            raise ValueError("backend must be 'hardware' or 'sim'")
        with self._lock:
            if self._running:
                raise ScannerError("Cannot change backend while scanner is running")
            self._backend = value
            self._radio = None
    
    def _create_radio(self):
        """Create radio instance for current backend."""
        if self._backend == "sim":
            return SimRadio(self._config.channel, self._config.scan, self._config.sim)
        else:
            radio = HardwareRadio(self._config.channel, self._config.scan, self._config.hardware)
            if not radio.is_available():
                raise ScannerError("Hardware backend not available (pyrf24 missing or SPI unavailable)")
            return radio
    
    def start(self) -> None:
        """Start the scanner thread."""
        with self._lock:
            if self._running:
                raise ScannerAlreadyRunningError("Scanner is already running")
            
            if self._radio is None:
                self._radio = self._create_radio()
            
            if not self._radio.is_initialized():
                self._radio.initialize()
            
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True, name="ScannerThread")
            self._thread.start()
            logger.info(f"Scanner started with {self._backend} backend")
    
    def stop(self, timeout: float = 5.0) -> bool:
        """Stop the scanner thread."""
        with self._lock:
            if not self._running:
                return True
            
            self._stop_event.set()
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("Scanner thread did not stop within timeout")
                return False
        
        with self._lock:
            self._running = False
            if self._radio:
                self._radio.cleanup()
                self._radio = None
        
        logger.info("Scanner stopped")
        return True
    
    def shutdown(self) -> None:
        """Force shutdown."""
        self.stop(timeout=2.0)
        with self._lock:
            self._running = False
            self._stop_event.set()
    
    def is_running(self) -> bool:
        with self._lock:
            return self._running
    
    def _run(self) -> None:
        """Main scanner loop."""
        try:
            self._spectrum_data.set_backend(self._backend)
            
            while not self._stop_event.is_set():
                for channel in self._config.channel.channel_range():
                    if self._stop_event.is_set():
                        break
                    
                    try:
                        validate_channel(channel)
                        valid, positive, negative = self._radio.scan_channel(
                            channel,
                            self._config.scan.measurement_window,
                            self._config.scan.sampling_interval,
                        )
                        
                        if valid >= self._config.scan.min_valid_samples:
                            activity = (positive / valid) * 100.0
                            data_sufficient = True
                            error = None
                        else:
                            activity = None
                            data_sufficient = False
                            error = f"Insufficient samples: {valid}/{self._config.scan.min_valid_samples}"
                        
                        status = self._config.thresholds.classify(activity)
                        if not data_sufficient:
                            status = "INSUFFICIENT DATA"
                        
                        obs = ChannelObservation(
                            timestamp=time.time(),
                            channel=channel,
                            frequency_mhz=2400 + channel,
                            backend=self._backend,
                            valid_samples=valid,
                            rpd_positive=positive,
                            rpd_negative=negative,
                            activity_percentage=activity,
                            status=status,
                            data_sufficient=data_sufficient,
                            measurement_window=self._config.scan.measurement_window,
                            sampling_interval=self._config.scan.sampling_interval,
                            error=error,
                        )
                        
                        self._spectrum_data.update_observation(obs)
                        
                        if self._on_observation:
                            self._on_observation(obs)
                    
                    except Exception as e:
                        logger.error(f"Error scanning channel {channel}: {e}")
                        if self._on_error:
                            self._on_error(e)
                        
                        obs = ChannelObservation(
                            timestamp=time.time(),
                            channel=channel,
                            frequency_mhz=2400 + channel,
                            backend=self._backend,
                            valid_samples=0,
                            rpd_positive=0,
                            rpd_negative=0,
                            activity_percentage=None,
                            status="SENSOR_ERROR",
                            data_sufficient=False,
                            measurement_window=self._config.scan.measurement_window,
                            sampling_interval=self._config.scan.sampling_interval,
                            error=str(e),
                        )
                        self._spectrum_data.update_observation(obs)
                
                self._spectrum_data.increment_scan_count()
                
                if self._on_scan_complete:
                    self._on_scan_complete()
                
                if not (self._config.channel.start_channel == self._config.channel.end_channel):
                    time.sleep(0.1)
        
        except Exception as e:
            logger.error(f"Scanner thread error: {e}")
            if self._on_error:
                self._on_error(e)
        finally:
            with self._lock:
                self._running = False