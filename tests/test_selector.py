"""Tests for channel selector (analysis/avoidance)."""

import pytest
import tempfile
import os

from config import ChannelConfig, ThresholdConfig, BlocklistConfig
from mitigation.blocklist_manager import BlocklistManager
from analysis.selector import ChannelSelector, ChannelEligibility, EligibilityReason
from scanner.scanner_engine import ChannelObservation


class TestChannelSelector:
    """Test ChannelSelector functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return ChannelConfig(start_channel=0, end_channel=125)
    
    @pytest.fixture
    def thresholds(self):
        """Create test thresholds."""
        return ThresholdConfig(clear_max=24, moderate_max=49, busy_max=74, heavy_min=75)
    
    @pytest.fixture
    def blocklist(self):
        """Create test blocklist with temporary file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('[]')
            temp_path = f.name
        
        config = BlocklistConfig(file_path=temp_path)
        bl = BlocklistManager(config)
        
        yield bl
        
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    @pytest.fixture
    def selector(self, config, thresholds, blocklist):
        """Create test channel selector."""
        return ChannelSelector(
            config,
            thresholds,
            blocklist,
            persistent_threshold=75.0,
            hysteresis=5.0,
        )
    
    def make_observation(self, channel: int, activity: float = None, data_sufficient: bool = True, error: str = None):
        """Create a test observation."""
        return ChannelObservation(
            timestamp=1000000.0,
            channel=channel,
            frequency_mhz=2400 + channel,
            backend="sim",
            valid_samples=100 if data_sufficient else 5,
            rpd_positive=int(100 * (activity / 100)) if activity is not None else 0,
            rpd_negative=100 - int(100 * (activity / 100)) if activity is not None else 100,
            activity_percentage=activity,
            status="Clear" if activity is None or activity <= 24 else "Heavy Load",
            data_sufficient=data_sufficient,
            measurement_window=1.0,
            sampling_interval=0.01,
            error=error,
        )
    
    def test_assess_channel_no_observation(self, selector):
        """Test assessing channel with no observation."""
        result = selector.assess_channel(50, None)
        
        assert result.channel == 50
        assert result.frequency_mhz == 2450
        assert result.eligible is False
        assert result.reason == EligibilityReason.INSUFFICIENT_DATA
        assert result.data_sufficient is False
    
    def test_assess_channel_blocked(self, selector, blocklist):
        """Test assessing blocked channel."""
        blocklist.block_channel(50, "Test")
        obs = self.make_observation(50, activity=10.0)
        
        result = selector.assess_channel(50, obs)
        
        assert result.channel == 50
        assert result.eligible is False
        assert result.reason == EligibilityReason.BLOCKED
        assert result.blocked is True
    
    def test_assess_channel_sensor_error(self, selector):
        """Test assessing channel with sensor error."""
        obs = self.make_observation(50, activity=10.0, error="Sensor failed")
        
        result = selector.assess_channel(50, obs)
        
        assert result.eligible is False
        assert result.reason == EligibilityReason.SENSOR_ERROR
    
    def test_assess_channel_insufficient_data(self, selector):
        """Test assessing channel with insufficient data."""
        obs = self.make_observation(50, activity=10.0, data_sufficient=False)
        
        result = selector.assess_channel(50, obs)
        
        assert result.eligible is False
        assert result.reason == EligibilityReason.INSUFFICIENT_DATA
        assert result.data_sufficient is False
    
    def test_assess_channel_high_activity(self, selector):
        """Test assessing channel with high activity (above persistent threshold)."""
        obs = self.make_observation(50, activity=80.0)
        
        result = selector.assess_channel(50, obs)
        
        assert result.eligible is False
        assert result.reason == EligibilityReason.HIGH_ACTIVITY
        assert result.activity_percentage == 80.0
    
    def test_assess_channel_persistent_high_activity(self, selector):
        """Test assessing channel with persistent high activity."""
        obs = self.make_observation(50, activity=80.0)
        
        # First assessment - HIGH_ACTIVITY
        result1 = selector.assess_channel(50, obs)
        assert result1.reason == EligibilityReason.HIGH_ACTIVITY
        
        # Second assessment - still HIGH_ACTIVITY
        result2 = selector.assess_channel(50, obs)
        assert result2.reason == EligibilityReason.HIGH_ACTIVITY
        
        # Third assessment - PERSISTENT_HIGH_ACTIVITY
        result3 = selector.assess_channel(50, obs)
        assert result3.reason == EligibilityReason.PERSISTENT_HIGH_ACTIVITY
    
    def test_assess_channel_eligible(self, selector):
        """Test assessing eligible channel (low activity)."""
        obs = self.make_observation(50, activity=10.0)
        
        result = selector.assess_channel(50, obs)
        
        assert result.eligible is True
        assert result.reason == EligibilityReason.ELIGIBLE
        assert result.activity_percentage == 10.0
    
    def test_assess_channel_hysteresis(self, selector):
        """Test hysteresis behavior near threshold."""
        # Activity just below persistent threshold - should be HIGH_ACTIVITY due to hysteresis
        obs = self.make_observation(50, activity=72.0)  # persistent_threshold=75, hysteresis=5, so 70-75 is hysteresis zone
        
        result = selector.assess_channel(50, obs)
        assert result.reason == EligibilityReason.HIGH_ACTIVITY
        assert not result.eligible
        
        # Activity well below hysteresis zone - should be eligible
        obs2 = self.make_observation(50, activity=60.0)
        result2 = selector.assess_channel(50, obs2)
        assert result2.reason == EligibilityReason.ELIGIBLE
        assert result2.eligible
    
    def test_get_eligible_channels(self, selector):
        """Test getting all eligible channels."""
        # Create observations for all channels
        observations = {}
        for ch in range(0, 126):
            if ch in (10, 20, 30):
                observations[ch] = self.make_observation(ch, activity=80.0)  # High activity
            elif ch in (5, 15):
                observations[ch] = self.make_observation(ch, data_sufficient=False)  # Insufficient
            else:
                observations[ch] = self.make_observation(ch, activity=5.0)  # Clear
        
        eligible = selector.get_eligible_channels(observations)
        
        # All channels except blocked, high activity, and insufficient data
        assert len(eligible) == 126 - 3 - 2  # 121 eligible
        assert all(e.eligible for e in eligible)
        # Should be sorted by activity (lowest first)
        activities = [e.activity_percentage for e in eligible]
        assert activities == sorted(activities)
    
    def test_recommend_channel(self, selector):
        """Test recommending best channel."""
        observations = {}
        for ch in range(0, 126):
            if ch == 50:
                observations[ch] = self.make_observation(ch, activity=5.0)  # Best
            elif ch == 51:
                observations[ch] = self.make_observation(ch, activity=10.0)  # Second best
            else:
                observations[ch] = self.make_observation(ch, activity=50.0)  # Moderate
        
        best = selector.recommend_channel(observations)
        
        assert best is not None
        assert best.channel == 50
        assert best.activity_percentage == 5.0
    
    def test_recommend_channel_with_exclude(self, selector):
        """Test recommending with excluded channels."""
        observations = {}
        for ch in range(0, 126):
            if ch == 50:
                observations[ch] = self.make_observation(ch, activity=5.0)
            else:
                observations[ch] = self.make_observation(ch, activity=50.0)
        
        # Exclude the best channel
        best = selector.recommend_channel(observations, exclude_channels={50})
        
        assert best is not None
        assert best.channel != 50
    
    def test_get_recommendations(self, selector):
        """Test getting multiple recommendations."""
        observations = {}
        for ch in range(0, 126):
            observations[ch] = self.make_observation(ch, activity=float(ch % 20))
        
        recommendations = selector.get_recommendations(observations, count=5)
        
        assert len(recommendations) == 5
        assert all(r.eligible for r in recommendations)
        # Should be sorted by activity
        activities = [r.activity_percentage for r in recommendations]
        assert activities == sorted(activities)
    
    def test_get_channel_ranking(self, selector):
        """Test getting channel rankings."""
        observations = {}
        for ch in range(0, 126):
            observations[ch] = self.make_observation(ch, activity=float(ch % 30))
        
        ranking = selector.get_channel_ranking(observations)
        
        assert len(ranking) == 126
        # Should be sorted by activity (lowest first)
        activities = [r[1] for r in ranking]
        assert activities == sorted(activities)
    
    def test_get_blocked_channels(self, selector, blocklist):
        """Test getting blocked channels through selector."""
        blocklist.block_channel(122)
        blocklist.block_channel(10)
        
        blocked = selector.get_blocked_channels()
        assert blocked == [10, 122]
    
    def test_peak_tracking(self, selector):
        """Test peak activity tracking."""
        # First scan - activity 20%
        obs1 = self.make_observation(50, activity=20.0)
        selector.assess_channel(50, obs1)
        assert selector.get_peak_activity(50) == 20.0
        
        # Second scan - activity 50%
        obs2 = self.make_observation(50, activity=50.0)
        selector.assess_channel(50, obs2)
        assert selector.get_peak_activity(50) == 50.0
        
        # Third scan - activity 30% (lower than peak)
        obs3 = self.make_observation(50, activity=30.0)
        selector.assess_channel(50, obs3)
        assert selector.get_peak_activity(50) == 50.0
    
    def test_reset_peaks(self, selector):
        """Test resetting peak tracking."""
        obs = self.make_observation(50, activity=50.0)
        selector.assess_channel(50, obs)
        assert selector.get_peak_activity(50) == 50.0
        
        selector.reset_peaks()
        assert selector.get_peak_activity(50) == 0.0
    
    def test_export_assessment(self, selector):
        """Test exporting assessment as dicts."""
        # Create observations for a limited range to match the test
        # The selector assesses all channels in its configured range (0-125)
        # So we need to provide observations for all of them or accept that it assesses all
        observations = {}
        for ch in range(0, 126):
            observations[ch] = self.make_observation(ch, activity=10.0)
        
        exported = selector.export_assessment(observations)
        
        # Should assess all 126 channels
        assert len(exported) == 126
        assert exported[0]["channel"] == 0
        assert exported[0]["eligible"] is True
        assert exported[1]["channel"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])