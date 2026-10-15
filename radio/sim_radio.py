"""Deterministic simulation backend for RF Spectrum Visualizer."""

import random
import time
import threading
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

from config import ChannelConfig, ScanConfig, SimConfig
from exceptions import SimulationError, InvalidChannelError
from radio.base_radio import BaseRadio


class ScenarioType(Enum):
    """Predefined simulation scenarios."""
    QUIET = "quiet"
    SINGLE_BUSY = "single_busy"
    SPIKES = "spikes"
    CHANNEL_122_HIGH = "channel_122_high"
    CHANNEL_122_LOW = "channel_122_low"
    WIFI_LIKE = "wifi_like"
    FREQUENCY_HOPPING = "frequency_hopping"
    SENSOR_ERRORS = "sensor_errors"
    MIXED = "mixed"
    BURST = "burst"
    HIGH_ACTIVITY = "high_activity"


@dataclass
class ChannelModel:
    """Model for a single channel's activity behavior."""
    channel: int
    base_probability: float = 0.05
    scenario: ScenarioType = ScenarioType.QUIET
    burst_probability: float = 0.0
    burst_duration: float = 0.5
    hop_channels: List[int] = field(default_factory=list)
    hop_interval: float = 0.1
    failure_rate: float = 0.0
    _last_burst_time: float = 0.0
    _in_burst: bool = False
    _hop_index: int = 0
    _last_hop_time: float = 0.0
    
    def get_rpd_probability(self, current_time: float, rng: random.Random) -> float:
        """Get current RPD probability for this channel."""
        if rng.random() < self.failure_rate:
            return -1.0
        
        prob = self.base_probability
        
        if self.scenario == ScenarioType.BURST:
            if self._in_burst:
                if current_time - self._last_burst_time >= self.burst_duration:
                    self._in_burst = False
                else:
                    prob = 0.9
            elif rng.random() < self.burst_probability:
                self._in_burst = True
                self._last_burst_time = current_time
                prob = 0.9
        
        elif self.scenario == ScenarioType.FREQUENCY_HOPPING:
            if current_time - self._last_hop_time >= self.hop_interval:
                self._hop_index = (self._hop_index + 1) % len(self.hop_channels)
                self._last_hop_time = current_time
            if self.channel == self.hop_channels[self._hop_index]:
                prob = 0.8
        
        elif self.scenario == ScenarioType.WIFI_LIKE:
            wifi_channels = {1: 12, 6: 37, 11: 62}
            if self.channel in wifi_channels.values():
                prob = 0.7 + 0.2 * rng.random()
        
        elif self.scenario == ScenarioType.SPIKES:
            if rng.random() < 0.01:
                prob = 0.95
        
        elif self.scenario == ScenarioType.CHANNEL_122_HIGH:
            if self.channel == 122:
                prob = 0.85
        
        elif self.scenario == ScenarioType.CHANNEL_122_LOW:
            if self.channel == 122:
                prob = 0.02
        
        return max(0.0, min(1.0, prob))
    
    def reset(self) -> None:
        """Reset internal state."""
        self._last_burst_time = 0.0
        self._in_burst = False
        self._hop_index = 0
        self._last_hop_time = 0.0


class SimRadio(BaseRadio):
    """Deterministic simulated nRF24L01+ radio for testing and development."""
    
    SCENARIOS: Dict[ScenarioType, Dict[str, Any]] = {
        ScenarioType.QUIET: {
            "description": "All channels quiet (<5% activity)",
            "base_prob_range": (0.01, 0.05),
        },
        ScenarioType.SINGLE_BUSY: {
            "description": "One channel at 80%, rest quiet",
            "base_prob_range": (0.01, 0.05),
            "busy_channel": 76,
            "busy_prob": 0.8,
        },
        ScenarioType.SPIKES: {
            "description": "Random spikes across channels",
            "base_prob_range": (0.01, 0.05),
            "spike_prob": 0.01,
            "spike_intensity": 0.95,
        },
        ScenarioType.CHANNEL_122_HIGH: {
            "description": "Channel 122 consistently high (85%)",
            "base_prob_range": (0.01, 0.05),
            "channel_122_prob": 0.85,
        },
        ScenarioType.CHANNEL_122_LOW: {
            "description": "Channel 122 consistently low (2%)",
            "base_prob_range": (0.01, 0.05),
            "channel_122_prob": 0.02,
        },
        ScenarioType.WIFI_LIKE: {
            "description": "WiFi channels 1,6,11 (nRF 12,37,62) active",
            "base_prob_range": (0.01, 0.05),
            "wifi_channels": [12, 37, 62],
            "wifi_prob": 0.7,
        },
        ScenarioType.FREQUENCY_HOPPING: {
            "description": "Frequency hopping pattern on some channels",
            "base_prob_range": (0.01, 0.05),
            "hop_channels": [2, 12, 22, 32, 42],
            "hop_interval": 0.2,
        },
        ScenarioType.SENSOR_ERRORS: {
            "description": "Random sensor failures (1% of reads)",
            "base_prob_range": (0.01, 0.05),
            "failure_rate": 0.01,
        },
        ScenarioType.MIXED: {
            "description": "Realistic mixed environment",
            "base_prob_range": (0.02, 0.15),
            "wifi_channels": [12, 37, 62],
            "wifi_prob": 0.65,
            "nrf_common": [76, 77, 78],
            "nrf_prob": 0.4,
            "burst_channels": [10, 20, 30, 40, 50],
            "burst_prob": 0.02,
        },
        ScenarioType.BURST: {
            "description": "Burst activity on some channels",
            "base_prob_range": (0.01, 0.05),
            "burst_channels": [10, 20, 30, 40, 50],
            "burst_prob": 0.05,
        },
        ScenarioType.HIGH_ACTIVITY: {
            "description": "High activity channels",
            "base_prob_range": (0.3, 0.5),
        },
    }
    
    def __init__(
        self,
        channel_config: ChannelConfig,
        scan_config: ScanConfig,
        sim_config: Optional[SimConfig] = None,
        scenario: ScenarioType = ScenarioType.MIXED,
        channel_models: Optional[Dict[int, ChannelModel]] = None,
    ):
        self._channel_config = channel_config
        self._scan_config = scan_config
        self._sim_config = sim_config or SimConfig()
        self._scenario = scenario
        self._rng = random.Random(self._sim_config.seed)
        self._current_channel = channel_config.start_channel
        self._initialized = False
        self._lock = threading.RLock()
        self._channel_models = channel_models or self._create_models()
        self._simulated_time = 0.0
        self._scan_count = 0
    
    def _create_models(self) -> Dict[int, ChannelModel]:
        """Create channel models based on scenario."""
        models = {}
        scenario_info = self.SCENARIOS[self._scenario]
        base_min, base_max = scenario_info.get("base_prob_range", (0.02, 0.1))
        
        for ch in self._channel_config.channel_range():
            base_prob = base_min + (base_max - base_min) * self._rng.random()
            pattern = self._scenario
            
            burst_prob = 0.0
            burst_duration = 0.3 + 0.5 * self._rng.random()
            hop_channels = []
            hop_interval = 0.2
            failure_rate = 0.0
            
            if self._scenario == ScenarioType.SINGLE_BUSY:
                if ch == scenario_info.get("busy_channel", 76):
                    base_prob = scenario_info.get("busy_prob", 0.8)
            
            elif self._scenario == ScenarioType.SPIKES:
                pass
            
            elif self._scenario == ScenarioType.CHANNEL_122_HIGH:
                if ch == 122:
                    pattern = ScenarioType.CHANNEL_122_HIGH
                    base_prob = scenario_info.get("channel_122_prob", 0.85)
            
            elif self._scenario == ScenarioType.CHANNEL_122_LOW:
                if ch == 122:
                    pattern = ScenarioType.CHANNEL_122_LOW
                    base_prob = scenario_info.get("channel_122_prob", 0.02)
            
            elif self._scenario == ScenarioType.WIFI_LIKE:
                wifi_chs = scenario_info.get("wifi_channels", [12, 37, 62])
                wifi_prob = scenario_info.get("wifi_prob", 0.7)
                if ch in wifi_chs:
                    pattern = ScenarioType.WIFI_LIKE
                    base_prob = wifi_prob
            
            elif self._scenario == ScenarioType.FREQUENCY_HOPPING:
                hop_chs = scenario_info.get("hop_channels", [2, 12, 22, 32, 42])
                hop_interval = scenario_info.get("hop_interval", 0.2)
                if ch in hop_chs:
                    pattern = ScenarioType.FREQUENCY_HOPPING
                    hop_channels = hop_chs
            
            elif self._scenario == ScenarioType.SENSOR_ERRORS:
                failure_rate = scenario_info.get("failure_rate", 0.01)
            
            elif self._scenario == ScenarioType.MIXED:
                wifi_chs = scenario_info.get("wifi_channels", [12, 37, 62])
                wifi_prob = scenario_info.get("wifi_prob", 0.65)
                nrf_chs = scenario_info.get("nrf_common", [76, 77, 78])
                nrf_prob = scenario_info.get("nrf_prob", 0.4)
                burst_chs = scenario_info.get("burst_channels", [10, 20, 30, 40, 50])
                burst_prob = scenario_info.get("burst_prob", 0.02)
                
                if ch in wifi_chs:
                    pattern = ScenarioType.WIFI_LIKE
                    base_prob = wifi_prob
                elif ch in nrf_chs:
                    pattern = ScenarioType.HIGH_ACTIVITY
                    base_prob = nrf_prob
                elif ch in burst_chs:
                    pattern = ScenarioType.BURST
                    base_prob = 0.1
                    burst_prob = 0.02
            
            models[ch] = ChannelModel(
                channel=ch,
                base_probability=base_prob,
                scenario=pattern,
                burst_probability=burst_prob,
                burst_duration=burst_duration,
                hop_channels=hop_channels,
                hop_interval=hop_interval,
                failure_rate=failure_rate,
            )
        
        return models
    
    def initialize(self) -> bool:
        """Initialize the simulated radio."""
        with self._lock:
            self._initialized = True
            self._current_channel = self._channel_config.start_channel
            self._simulated_time = 0.0
            self._scan_count = 0
            for model in self._channel_models.values():
                model.reset()
            return True
    
    def is_initialized(self) -> bool:
        return self._initialized
    
    def set_channel(self, channel: int) -> None:
        """Set the current channel."""
        with self._lock:
            if not (0 <= channel <= 125):
                raise InvalidChannelError(channel)
            self._current_channel = channel
    
    def get_channel(self) -> int:
        """Get the current channel."""
        with self._lock:
            return self._current_channel
    
    def read_rpd(self) -> bool:
        """Read RPD (Received Power Detector) status.
        
        Returns:
            True if signal detected, False otherwise
            
        Raises:
            SimulationError: If radio not initialized or sensor failure
        """
        with self._lock:
            if not self._initialized:
                raise SimulationError("Radio not initialized")
            
            model = self._channel_models.get(self._current_channel)
            if not model:
                return False
            
            prob = model.get_rpd_probability(self._simulated_time, self._rng)
            if prob < 0:
                raise SimulationError(f"Sensor failure on channel {self._current_channel}")
            
            self._simulated_time += self._scan_config.sampling_interval
            return self._rng.random() < prob
    
    def scan_channel(
        self,
        channel: int,
        duration: Optional[float] = None,
        interval: Optional[float] = None,
    ) -> Tuple[int, int, int]:
        """Scan a channel for RPD activity.
        
        Args:
            channel: Channel to scan
            duration: Measurement window (seconds)
            interval: Sampling interval (seconds)
            
        Returns:
            Tuple of (valid_samples, rpd_positive, rpd_negative)
        """
        with self._lock:
            if not self._initialized:
                raise SimulationError("Radio not initialized")
            
            duration = self._scan_config.measurement_window if duration is None else duration
            interval = self._scan_config.sampling_interval if interval is None else interval
            
            self.set_channel(channel)
            samples = int(duration / interval)
            valid = 0
            positive = 0
            negative = 0
            
            for _ in range(samples):
                try:
                    rpd = self.read_rpd()
                    valid += 1
                    if rpd:
                        positive += 1
                    else:
                        negative += 1
                except SimulationError:
                    pass
            
            self._scan_count += 1
            return valid, positive, negative
    
    def cleanup(self) -> None:
        """Clean up resources."""
        with self._lock:
            self._initialized = False
    
    def get_channel_model(self, channel: int) -> Optional[ChannelModel]:
        """Get the channel model for inspection."""
        with self._lock:
            return self._channel_models.get(channel)
    
    def set_seed(self, seed: int) -> None:
        """Set random seed for reproducibility."""
        with self._lock:
            self._rng.seed(seed)
            self._simulated_time = 0.0
            for model in self._channel_models.values():
                model.reset()
    
    def get_simulated_time(self) -> float:
        """Get current simulated time."""
        with self._lock:
            return self._simulated_time
    
    def get_scan_count(self) -> int:
        """Get number of scans performed."""
        with self._lock:
            return self._scan_count
    
    @classmethod
    def create_scenario(cls, scenario: ScenarioType, seed: Optional[int] = None) -> 'SimRadio':
        """Create a SimRadio with a specific scenario.
        
        Args:
            scenario: Scenario type
            seed: Random seed for reproducibility
            
        Returns:
            Configured SimRadio instance
        """
        config = ChannelConfig()
        scan_config = ScanConfig()
        sim_config = SimConfig(seed=seed, deterministic=True)
        return cls(config, scan_config, sim_config, scenario=scenario)
    
    def get_scenario_info(self) -> Dict[str, Any]:
        """Get information about current scenario."""
        return {
            "scenario": self._scenario.value,
            "description": self.SCENARIOS[self._scenario]["description"],
            "seed": self._sim_config.seed,
            "deterministic": self._sim_config.deterministic,
        }