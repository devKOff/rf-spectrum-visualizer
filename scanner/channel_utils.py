"""Channel utilities for RF Spectrum Visualizer."""

from typing import Optional, List, Tuple
from dataclasses import dataclass

from config import ChannelConfig
from exceptions import InvalidChannelError


CHANNEL_MIN = 0
CHANNEL_MAX = 125
BASE_FREQUENCY_MHZ = 2400


@dataclass(frozen=True)
class ChannelInfo:
    """Immutable channel information."""
    channel: int
    frequency_mhz: int
    
    def __post_init__(self):
        if not (CHANNEL_MIN <= self.channel <= CHANNEL_MAX):
            raise ValueError(f"Channel must be in [{CHANNEL_MIN}, {CHANNEL_MAX}]")
        if self.frequency_mhz != BASE_FREQUENCY_MHZ + self.channel:
            raise ValueError(f"Frequency must be {BASE_FREQUENCY_MHZ} + channel")


def channel_to_frequency(channel: int) -> int:
    """Convert channel number to frequency in MHz.
    
    Args:
        channel: nRF24L01+ channel number (0-125)
        
    Returns:
        Frequency in MHz (2400 + channel)
        
    Raises:
        InvalidChannelError: If channel is out of range
    """
    if not (CHANNEL_MIN <= channel <= CHANNEL_MAX):
        raise InvalidChannelError(channel)
    return BASE_FREQUENCY_MHZ + channel


def frequency_to_channel(frequency_mhz: int) -> int:
    """Convert frequency in MHz to channel number.
    
    Args:
        frequency_mhz: Frequency in MHz
        
    Returns:
        Channel number (0-125)
        
    Raises:
        InvalidChannelError: If frequency doesn't correspond to a valid channel
    """
    channel = frequency_mhz - BASE_FREQUENCY_MHZ
    if not (CHANNEL_MIN <= channel <= CHANNEL_MAX):
        raise InvalidChannelError(channel)
    return channel


def validate_channel(channel: int) -> None:
    """Validate channel is in range [0, 125].
    
    Args:
        channel: Channel number to validate
        
    Raises:
        InvalidChannelError: If channel is out of range
    """
    if not (CHANNEL_MIN <= channel <= CHANNEL_MAX):
        raise InvalidChannelError(channel)


def validate_channel_list(channels: List[int]) -> List[int]:
    """Validate and return only valid channels from a list.
    
    Args:
        channels: List of channel numbers
        
    Returns:
        List of valid channel numbers
        
    Raises:
        InvalidChannelError: If any channel is out of range
    """
    invalid = [ch for ch in channels if not (CHANNEL_MIN <= ch <= CHANNEL_MAX)]
    if invalid:
        raise InvalidChannelError(invalid[0])
    return channels


def get_all_channels() -> List[ChannelInfo]:
    """Get all 126 channels with their frequencies.
    
    Returns:
        List of ChannelInfo for channels 0-125
    """
    return [ChannelInfo(ch, channel_to_frequency(ch)) for ch in range(CHANNEL_MIN, CHANNEL_MAX + 1)]


def get_channels_in_range(config: ChannelConfig) -> List[ChannelInfo]:
    """Get channels within configured range.
    
    Args:
        config: ChannelConfig defining the range
        
    Returns:
        List of ChannelInfo for channels in range
    """
    return [ChannelInfo(ch, channel_to_frequency(ch)) for ch in config.channel_range()]


def format_channel(channel: int, include_freq: bool = True) -> str:
    """Format channel for display.
    
    Args:
        channel: Channel number
        include_freq: Whether to include frequency
        
    Returns:
        Formatted string
    """
    if include_freq:
        return f"Ch {channel:3d} ({channel_to_frequency(channel):4d} MHz)"
    return f"Ch {channel:3d}"


def parse_channel_input(text: str) -> int:
    """Parse channel input from user text.
    
    Args:
        text: User input string (e.g., "122", "Ch 122", "2522 MHz")
        
    Returns:
        Channel number
        
    Raises:
        ValueError: If input cannot be parsed
        InvalidChannelError: If parsed channel is out of range
    """
    text = text.strip().upper()
    
    if text.startswith("CH"):
        text = text[2:].strip()
    
    if text.endswith("MHZ"):
        try:
            freq = int(text[:-3].strip())
            return frequency_to_channel(freq)
        except ValueError:
            raise ValueError(f"Cannot parse frequency from: {text}")
    
    try:
        channel = int(text)
        validate_channel(channel)
        return channel
    except ValueError as e:
        if "out of range" in str(e).lower():
            raise
        raise ValueError(f"Invalid channel number: {text}")


def get_wifi_overlap_channels() -> List[Tuple[int, int, str]]:
    """Get WiFi channel overlap information for 2.4 GHz band.
    
    Returns:
        List of (nrf_channel, wifi_channel, wifi_frequency) tuples
    """
    wifi_channels = {
        1: 2412,
        2: 2417,
        3: 2422,
        4: 2427,
        5: 2432,
        6: 2437,
        7: 2442,
        8: 2447,
        9: 2452,
        10: 2457,
        11: 2462,
        12: 2467,
        13: 2472,
        14: 2484,
    }
    
    result = []
    for wifi_ch, freq in wifi_channels.items():
        nrf_ch = freq - BASE_FREQUENCY_MHZ
        if CHANNEL_MIN <= nrf_ch <= CHANNEL_MAX:
            result.append((nrf_ch, wifi_ch, freq))
    
    return result