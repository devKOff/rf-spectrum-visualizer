"""Custom exceptions for RF Spectrum Visualizer."""

from typing import Optional


class RFSystemError(Exception):
    """Base exception for RF Spectrum Visualizer errors."""
    
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class BlocklistError(RFSystemError):
    """Raised when blocklist operations fail."""
    pass


class RadioInitError(RFSystemError):
    """Raised when radio initialization fails."""
    pass


class InvalidChannelError(RFSystemError):
    """Raised when channel number is out of valid range [0, 125]."""
    
    def __init__(self, channel: int, min_channel: int = 0, max_channel: int = 125):
        self.channel = channel
        self.min_channel = min_channel
        self.max_channel = max_channel
        message = f"Channel {channel} out of range [{min_channel}, {max_channel}]"
        super().__init__(message, {"channel": channel, "min": min_channel, "max": max_channel})


class ConfigurationError(RFSystemError):
    """Raised for invalid configuration."""
    pass


class ScannerError(RFSystemError):
    """Raised for scanner thread errors."""
    pass


class ScannerNotRunningError(ScannerError):
    """Raised when scanner operation requires running scanner."""
    pass


class ScannerAlreadyRunningError(ScannerError):
    """Raised when attempting to start an already running scanner."""
    pass


class ExportError(RFSystemError):
    """Raised when export operations fail."""
    pass


class InsufficientDataError(RFSystemError):
    """Raised when insufficient samples for calculation."""
    pass


class BackendError(RFSystemError):
    """Raised for backend-related errors."""
    pass


class SimulationError(BackendError):
    """Raised for simulation backend errors."""
    pass


class HardwareError(BackendError):
    """Raised when hardware operations fail."""
    pass


class SPIError(HardwareError):
    """Raised when SPI communication fails."""
    pass


class RadioNotFoundError(HardwareError):
    """Raised when radio hardware is not detected."""
    pass