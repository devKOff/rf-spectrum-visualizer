"""Base radio interface for RF Spectrum Visualizer."""

from abc import ABC, abstractmethod
from typing import Tuple, Optional


class BaseRadio(ABC):
    """Abstract base class for radio backends."""
    
    @abstractmethod
    def initialize(self) -> bool:
        """Initialize the radio hardware or simulation.
        
        Returns:
            True if initialization successful
        """
        pass
    
    @abstractmethod
    def is_initialized(self) -> bool:
        """Check if radio is initialized.
        
        Returns:
            True if initialized
        """
        pass
    
    @abstractmethod
    def set_channel(self, channel: int) -> None:
        """Set the radio channel.
        
        Args:
            channel: Channel number (0-125)
        """
        pass
    
    @abstractmethod
    def get_channel(self) -> int:
        """Get the current channel.
        
        Returns:
            Current channel number
        """
        pass
    
    @abstractmethod
    def read_rpd(self) -> bool:
        """Read RPD (Received Power Detector) status.
        
        Returns:
            True if signal detected, False otherwise
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """Clean up radio resources."""
        pass