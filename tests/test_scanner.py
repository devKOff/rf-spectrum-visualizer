"""Tests for scanner engine."""

import pytest
import time
import threading

from config import AppConfig, ChannelConfig, ScanConfig
from scanner.scanner_engine import ScannerThread, SpectrumData
from radio.sim_radio import SimRadio, ScenarioType
from models.channel_record import ChannelObservation


class TestScannerEngine:
    """Test ScannerThread and SpectrumData functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration with limited channel range for speed."""
        return AppConfig(
            channel=ChannelConfig(start_channel=0, end_channel=10),
            scan=ScanConfig(measurement_window=0.1, sampling_interval=0.01, min_valid_samples=5),
        )
    
    @pytest.fixture
    def spectrum_data(self, config):
        """Create SpectrumData instance."""
        return SpectrumData(config)
    
    @pytest.fixture
    def sim_radio(self, config):
        """Create SimRadio instance."""
        radio = SimRadio(config.channel, config.scan, scenario=ScenarioType.QUIET)
        radio.initialize()
        yield radio
        radio.cleanup()
    
    def test_spectrum_data_update_and_get(self, spectrum_data):
        """Test updating and retrieving observations."""
        obs = ChannelObservation(
            timestamp=time.time(),
            channel=5,
            frequency_mhz=2405,
            backend="sim",
            valid_samples=100,
            rpd_positive=10,
            rpd_negative=90,
            activity_percentage=10.0,
            status="Clear",
            data_sufficient=True,
            measurement_window=1.0,
            sampling_interval=0.01,
        )
        
        spectrum_data.update_observation(obs)
        
        retrieved = spectrum_data.get_observation(5)
        assert retrieved is not None
        assert retrieved.channel == 5
        assert retrieved.activity_percentage == 10.0
        assert retrieved.rpd_positive == 10
        
        # Non-existent channel
        assert spectrum_data.get_observation(99) is None
    
    def test_spectrum_data_get_all(self, spectrum_data):
        """Test getting all observations."""
        for ch in [0, 5, 10]:
            obs = ChannelObservation(
                timestamp=time.time(),
                channel=ch,
                frequency_mhz=2400 + ch,
                backend="sim",
                valid_samples=100,
                rpd_positive=ch,
                rpd_negative=100 - ch,
                activity_percentage=float(ch),
                status="Clear",
                data_sufficient=True,
                measurement_window=1.0,
                sampling_interval=0.01,
            )
            spectrum_data.update_observation(obs)
        
        all_obs = spectrum_data.get_all_observations()
        assert len(all_obs) == 3
        assert set(all_obs.keys()) == {0, 5, 10}
    
    def test_spectrum_data_channels_in_range(self, spectrum_data, config):
        """Test getting channels in configured range."""
        channels = spectrum_data.get_channels_in_range()
        assert channels == list(range(0, 11))
    
    def test_spectrum_data_scan_count(self, spectrum_data):
        """Test scan count tracking."""
        assert spectrum_data.get_scan_count() == 0
        spectrum_data.increment_scan_count()
        assert spectrum_data.get_scan_count() == 1
        spectrum_data.increment_scan_count()
        assert spectrum_data.get_scan_count() == 2
    
    def test_spectrum_data_backend(self, spectrum_data):
        """Test backend tracking."""
        assert spectrum_data.get_backend() == "unknown"
        spectrum_data.set_backend("sim")
        assert spectrum_data.get_backend() == "sim"
        spectrum_data.set_backend("hardware")
        assert spectrum_data.get_backend() == "hardware"
    
    def test_spectrum_data_clear(self, spectrum_data):
        """Test clearing all data."""
        obs = ChannelObservation(
            timestamp=time.time(),
            channel=5,
            frequency_mhz=2405,
            backend="sim",
            valid_samples=100,
            rpd_positive=10,
            rpd_negative=90,
            activity_percentage=10.0,
            status="Clear",
            data_sufficient=True,
            measurement_window=1.0,
            sampling_interval=0.01,
        )
        spectrum_data.update_observation(obs)
        spectrum_data.increment_scan_count()
        
        spectrum_data.clear()
        
        assert spectrum_data.get_observation(5) is None
        assert spectrum_data.get_scan_count() == 0
    
    def test_scanner_thread_start_stop(self, config, spectrum_data, sim_radio):
        """Test scanner thread start and stop."""
        scanner = ScannerThread(config, spectrum_data, sim_radio)
        
        assert not scanner.is_running()
        
        scanner.start()
        assert scanner.is_running()
        
        # Wait for at least one scan
        time.sleep(0.5)
        
        scanner.stop()
        assert not scanner.is_running()
    
    def test_scanner_thread_updates_spectrum_data(self, config, spectrum_data, sim_radio):
        """Test that scanner updates spectrum data."""
        scanner = ScannerThread(config, spectrum_data, sim_radio)
        scanner.start()
        
        # Wait for scan to complete
        time.sleep(0.5)
        
        scanner.stop()
        
        # Should have observations for all channels in range
        observations = spectrum_data.get_all_observations()
        assert len(observations) == 11  # channels 0-10
        
        # All should have data_sufficient=True for QUIET scenario
        for ch in range(0, 11):
            assert ch in observations
            assert observations[ch].data_sufficient is True
            assert observations[ch].status == "Clear"
    
    def test_scanner_thread_scan_complete_callback(self, config, spectrum_data, sim_radio):
        """Test scan complete callback."""
        callback_called = threading.Event()
        
        def on_scan_complete():
            callback_called.set()
        
        scanner = ScannerThread(config, spectrum_data, sim_radio, on_scan_complete=on_scan_complete)
        scanner.start()
        
        # Wait for callback
        assert callback_called.wait(timeout=2.0)
        
        scanner.stop()
    
    def test_scanner_thread_observation_callback(self, config, spectrum_data, sim_radio):
        """Test observation callback."""
        observations_received = []
        
        def on_observation(obs):
            observations_received.append(obs)
        
        scanner = ScannerThread(config, spectrum_data, sim_radio, on_observation=on_observation)
        scanner.start()
        
        time.sleep(0.5)
        scanner.stop()
        
        # Should have received observations for all channels
        assert len(observations_received) >= 11
    
    def test_scanner_thread_error_callback(self, config, spectrum_data):
        """Test error callback."""
        errors_received = []
        
        def on_error(error):
            errors_received.append(error)
        
        # Use a radio that will fail
        class FailingRadio:
            def initialize(self): return True
            def is_initialized(self): return True
            def cleanup(self): pass
            def scan_channel(self, channel, duration, interval):
                raise Exception("Test error")
        
        scanner = ScannerThread(config, spectrum_data, FailingRadio(), on_error=on_error)
        scanner.start()
        
        time.sleep(0.5)
        scanner.stop()
        
        assert len(errors_received) > 0
    
    def test_scanner_thread_double_start_raises(self, config, spectrum_data, sim_radio):
        """Test that starting twice raises error."""
        scanner = ScannerThread(config, spectrum_data, sim_radio)
        scanner.start()
        
        with pytest.raises(Exception):  # ScannerAlreadyRunningError
            scanner.start()
        
        scanner.stop()
    
    def test_scanner_thread_backend_change_while_running_raises(self, config, spectrum_data, sim_radio):
        """Test that changing backend while running raises error."""
        scanner = ScannerThread(config, spectrum_data, sim_radio)
        scanner.start()
        
        with pytest.raises(Exception):  # ScannerError
            scanner.backend = "hardware"
        
        scanner.stop()
    
    def test_spectrum_data_export_all(self, spectrum_data):
        """Test exporting all observations."""
        for ch in [0, 5, 10]:
            obs = ChannelObservation(
                timestamp=time.time(),
                channel=ch,
                frequency_mhz=2400 + ch,
                backend="sim",
                valid_samples=100,
                rpd_positive=ch,
                rpd_negative=100 - ch,
                activity_percentage=float(ch),
                status="Clear",
                data_sufficient=True,
                measurement_window=1.0,
                sampling_interval=0.01,
            )
            spectrum_data.update_observation(obs)
        
        exported = spectrum_data.export_all()
        assert len(exported) == 3
        assert all("channel" in e for e in exported)
        assert all("activity_percentage" in e for e in exported)
    
    def test_spectrum_data_waterfall(self, spectrum_data):
        """Test waterfall history."""
        now = time.time()
        for i in range(5):
            obs = ChannelObservation(
                timestamp=now - i,
                channel=i,
                frequency_mhz=2400 + i,
                backend="sim",
                valid_samples=100,
                rpd_positive=10,
                rpd_negative=90,
                activity_percentage=10.0,
                status="Clear",
                data_sufficient=True,
                measurement_window=1.0,
                sampling_interval=0.01,
            )
            spectrum_data.update_observation(obs)
        
        # Get all waterfall data
        waterfall = spectrum_data.get_waterfall_data()
        assert len(waterfall) == 5
        
        # Get waterfall data with max_age filter
        recent = spectrum_data.get_waterfall_data(max_age=2.5)
        assert len(recent) == 3  # Only last 3 (ages 0, 1, 2)
        
        # Get waterfall data with channel filter
        ch_filtered = spectrum_data.get_waterfall_data(channels=[0, 1])
        assert len(ch_filtered) == 2
        assert all(o.channel in (0, 1) for o in ch_filtered)
    
    def test_spectrum_data_rolling_history(self, spectrum_data):
        """Test rolling history per channel."""
        now = time.time()
        for i in range(10):
            obs = ChannelObservation(
                timestamp=now + i * 0.1,
                channel=5,
                frequency_mhz=2405,
                backend="sim",
                valid_samples=100,
                rpd_positive=10 + i,
                rpd_negative=90 - i,
                activity_percentage=10.0 + i,
                status="Clear",
                data_sufficient=True,
                measurement_window=1.0,
                sampling_interval=0.01,
            )
            spectrum_data.update_observation(obs)
        
        history = spectrum_data.get_rolling_history(5)
        assert len(history) == 10
        
        # History should be in order
        activities = [o.activity_percentage for o in history]
        assert activities == sorted(activities)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])