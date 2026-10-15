"""Tests for channel utilities."""

import pytest

from scanner.channel_utils import (
    channel_to_frequency,
    frequency_to_channel,
    validate_channel,
    validate_channel_list,
    get_all_channels,
    format_channel,
    parse_channel_input,
    get_wifi_overlap_channels,
)
from exceptions import InvalidChannelError


class TestChannelUtils:
    """Test channel utility functions."""
    
    def test_channel_to_frequency_valid(self):
        """Test channel to frequency conversion for valid channels."""
        assert channel_to_frequency(0) == 2400
        assert channel_to_frequency(1) == 2401
        assert channel_to_frequency(12) == 2412
        assert channel_to_frequency(37) == 2437
        assert channel_to_frequency(62) == 2462
        assert channel_to_frequency(125) == 2525
    
    def test_channel_to_frequency_invalid(self):
        """Test channel to frequency conversion for invalid channels."""
        with pytest.raises(InvalidChannelError):
            channel_to_frequency(-1)
        with pytest.raises(InvalidChannelError):
            channel_to_frequency(126)
    
    def test_frequency_to_channel_valid(self):
        """Test frequency to channel conversion for valid frequencies."""
        assert frequency_to_channel(2400) == 0
        assert frequency_to_channel(2412) == 12
        assert frequency_to_channel(2437) == 37
        assert frequency_to_channel(2462) == 62
        assert frequency_to_channel(2525) == 125
    
    def test_frequency_to_channel_invalid(self):
        """Test frequency to channel conversion for invalid frequencies."""
        with pytest.raises(InvalidChannelError):
            frequency_to_channel(2399)
        with pytest.raises(InvalidChannelError):
            frequency_to_channel(2526)
    
    def test_validate_channel_valid(self):
        """Test channel validation for valid channels."""
        for ch in range(0, 126):
            validate_channel(ch)  # Should not raise
    
    def test_validate_channel_invalid(self):
        """Test channel validation for invalid channels."""
        with pytest.raises(InvalidChannelError):
            validate_channel(-1)
        with pytest.raises(InvalidChannelError):
            validate_channel(126)
    
    def test_validate_channel_list_valid(self):
        """Test channel list validation for valid lists."""
        result = validate_channel_list([0, 12, 37, 62, 125])
        assert result == [0, 12, 37, 62, 125]
    
    def test_validate_channel_list_invalid(self):
        """Test channel list validation for invalid lists."""
        with pytest.raises(InvalidChannelError):
            validate_channel_list([0, 126])
        with pytest.raises(InvalidChannelError):
            validate_channel_list([-1, 12])
    
    def test_get_all_channels(self):
        """Test getting all channels."""
        channels = get_all_channels()
        assert len(channels) == 126
        assert channels[0].channel == 0
        assert channels[0].frequency_mhz == 2400
        assert channels[125].channel == 125
        assert channels[125].frequency_mhz == 2525
    
    def test_format_channel(self):
        """Test channel formatting."""
        assert format_channel(0) == "Ch   0 (2400 MHz)"
        assert format_channel(12) == "Ch  12 (2412 MHz)"
        assert format_channel(122) == "Ch 122 (2522 MHz)"
        assert format_channel(122, include_freq=False) == "Ch 122"
    
    def test_parse_channel_input(self):
        """Test parsing channel input from user text."""
        assert parse_channel_input("0") == 0
        assert parse_channel_input("122") == 122
        assert parse_channel_input("Ch 122") == 122
        assert parse_channel_input("CH 12") == 12
        assert parse_channel_input("2412 MHz") == 12
        assert parse_channel_input("2522 MHz") == 122
        assert parse_channel_input("  37  ") == 37
    
    def test_parse_channel_input_invalid(self):
        """Test parsing invalid channel input."""
        with pytest.raises(ValueError):
            parse_channel_input("abc")
        with pytest.raises(InvalidChannelError):
            parse_channel_input("126")
        with pytest.raises(InvalidChannelError):
            parse_channel_input("2526 MHz")
    
    def test_get_wifi_overlap_channels(self):
        """Test WiFi channel overlap information."""
        overlaps = get_wifi_overlap_channels()
        
        # Check WiFi channels 1, 6, 11 are included
        wifi_channels = {1: 2412, 6: 2437, 11: 2462}
        for wifi_ch, freq in wifi_channels.items():
            found = any(o[0] == freq - 2400 and o[1] == wifi_ch for o in overlaps)
            assert found, f"WiFi channel {wifi_ch} ({freq} MHz) not found in overlaps"
        
        # Check all returned channels are valid
        for nrf_ch, wifi_ch, freq in overlaps:
            assert 0 <= nrf_ch <= 125
            assert freq == 2400 + nrf_ch


if __name__ == "__main__":
    pytest.main([__file__, "-v"])