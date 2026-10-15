"""Channel selection algorithm for RF Spectrum Visualizer."""

from typing import List, Optional, Dict, Tuple, Set
from dataclasses import dataclass
from enum import Enum

from config import ChannelConfig, ThresholdConfig
from models.blocklist_model import BlocklistModel
from scanner.scanner_engine import ChannelObservation
from scanner.channel_utils import validate_channel
from exceptions import InvalidChannelError


class EligibilityReason(Enum):
    """Reason for channel eligibility status."""
    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    INSUFFICIENT_DATA = "insufficient_data"
    SENSOR_ERROR = "sensor_error"
    HIGH_ACTIVITY = "high_activity"
    PERSISTENT_HIGH_ACTIVITY = "persistent_high_activity"


@dataclass
class ChannelEligibility:
    """Channel eligibility assessment."""
    channel: int
    frequency_mhz: int
    eligible: bool
    reason: EligibilityReason
    activity_percentage: Optional[float]
    status: str
    data_sufficient: bool
    blocked: bool
    
    def to_dict(self) -> dict:
        return {
            "channel": self.channel,
            "frequency_mhz": self.frequency_mhz,
            "eligible": self.eligible,
            "reason": self.reason.value,
            "activity_percentage": self.activity_percentage,
            "status": self.status,
            "data_sufficient": self.data_sufficient,
            "blocked": self.blocked,
        }


class ChannelSelector:
    """Channel selection and recommendation engine."""
    
    def __init__(
        self,
        channel_config: ChannelConfig,
        threshold_config: ThresholdConfig,
        blocklist_manager: BlocklistModel,
        persistent_threshold: float = 75.0,
        hysteresis: float = 5.0,
    ):
        self._channel_config = channel_config
        self._threshold_config = threshold_config
        self._blocklist = blocklist_manager
        self._persistent_threshold = persistent_threshold
        self._hysteresis = hysteresis
        self._channel_peaks: Dict[int, float] = {}
        self._consecutive_high: Dict[int, int] = {}
    
    @property
    def persistent_threshold(self) -> float:
        return self._persistent_threshold
    
    @persistent_threshold.setter
    def persistent_threshold(self, value: float) -> None:
        if not 0 <= value <= 100:
            raise ValueError("persistent_threshold must be 0-100")
        self._persistent_threshold = value
    
    @property
    def hysteresis(self) -> float:
        return self._hysteresis
    
    @hysteresis.setter
    def hysteresis(self, value: float) -> None:
        if not 0 <= value <= 50:
            raise ValueError("hysteresis must be 0-50")
        self._hysteresis = value
    
    def assess_channel(
        self,
        channel: int,
        observation: Optional[ChannelObservation],
    ) -> ChannelEligibility:
        """Assess eligibility of a single channel.
        
        Args:
            channel: Channel number
            observation: Latest observation or None
            
        Returns:
            ChannelEligibility assessment
        """
        validate_channel(channel)
        blocked = self._blocklist.is_blocked(channel)
        
        if observation is None:
            return ChannelEligibility(
                channel=channel,
                frequency_mhz=2400 + channel,
                eligible=False,
                reason=EligibilityReason.INSUFFICIENT_DATA,
                activity_percentage=None,
                status="UNKNOWN",
                data_sufficient=False,
                blocked=blocked,
            )
        
        if blocked:
            return ChannelEligibility(
                channel=channel,
                frequency_mhz=observation.frequency_mhz,
                eligible=False,
                reason=EligibilityReason.BLOCKED,
                activity_percentage=observation.activity_percentage,
                status=observation.status,
                data_sufficient=observation.data_sufficient,
                blocked=True,
            )
        
        if observation.error:
            return ChannelEligibility(
                channel=channel,
                frequency_mhz=observation.frequency_mhz,
                eligible=False,
                reason=EligibilityReason.SENSOR_ERROR,
                activity_percentage=observation.activity_percentage,
                status=observation.status,
                data_sufficient=observation.data_sufficient,
                blocked=False,
            )
        
        if not observation.data_sufficient:
            return ChannelEligibility(
                channel=channel,
                frequency_mhz=observation.frequency_mhz,
                eligible=False,
                reason=EligibilityReason.INSUFFICIENT_DATA,
                activity_percentage=observation.activity_percentage,
                status=observation.status,
                data_sufficient=False,
                blocked=False,
            )
        
        if observation.activity_percentage is None:
            return ChannelEligibility(
                channel=channel,
                frequency_mhz=observation.frequency_mhz,
                eligible=False,
                reason=EligibilityReason.INSUFFICIENT_DATA,
                activity_percentage=None,
                status=observation.status,
                data_sufficient=observation.data_sufficient,
                blocked=False,
            )
        
        activity = observation.activity_percentage
        
        self._channel_peaks[channel] = max(
            self._channel_peaks.get(channel, 0.0),
            activity
        )
        
        if activity >= self._persistent_threshold:
            self._consecutive_high[channel] = self._consecutive_high.get(channel, 0) + 1
            if self._consecutive_high[channel] >= 3:
                return ChannelEligibility(
                    channel=channel,
                    frequency_mhz=observation.frequency_mhz,
                    eligible=False,
                    reason=EligibilityReason.PERSISTENT_HIGH_ACTIVITY,
                    activity_percentage=activity,
                    status=observation.status,
                    data_sufficient=True,
                    blocked=False,
                )
        else:
            self._consecutive_high[channel] = 0
        
        if activity >= self._persistent_threshold - self._hysteresis:
            return ChannelEligibility(
                channel=channel,
                frequency_mhz=observation.frequency_mhz,
                eligible=False,
                reason=EligibilityReason.HIGH_ACTIVITY,
                activity_percentage=activity,
                status=observation.status,
                data_sufficient=True,
                blocked=False,
            )
        
        return ChannelEligibility(
            channel=channel,
            frequency_mhz=observation.frequency_mhz,
            eligible=True,
            reason=EligibilityReason.ELIGIBLE,
            activity_percentage=activity,
            status=observation.status,
            data_sufficient=True,
            blocked=False,
        )
    
    def assess_all_channels(
        self,
        observations: Dict[int, ChannelObservation],
    ) -> List[ChannelEligibility]:
        """Assess eligibility for all channels in range.
        
        Args:
            observations: Dictionary of channel observations
            
        Returns:
            List of ChannelEligibility for all channels
        """
        results = []
        for channel in self._channel_config.channel_range():
            obs = observations.get(channel)
            results.append(self.assess_channel(channel, obs))
        return results
    
    def get_eligible_channels(
        self,
        observations: Dict[int, ChannelObservation],
    ) -> List[ChannelEligibility]:
        """Get all eligible channels sorted by activity (lowest first).
        
        Args:
            observations: Dictionary of channel observations
            
        Returns:
            List of eligible ChannelEligibility sorted by activity
        """
        all_assessments = self.assess_all_channels(observations)
        eligible = [a for a in all_assessments if a.eligible]
        eligible.sort(key=lambda x: x.activity_percentage or 0)
        return eligible
    
    def recommend_channel(
        self,
        observations: Dict[int, ChannelObservation],
        exclude_channels: Optional[Set[int]] = None,
    ) -> Optional[ChannelEligibility]:
        """Recommend the best channel (lowest activity, not blocked, sufficient data).
        
        Args:
            observations: Dictionary of channel observations
            exclude_channels: Additional channels to exclude
            
        Returns:
            Best ChannelEligibility or None if no eligible channels
        """
        exclude = exclude_channels or set()
        eligible = self.get_eligible_channels(observations)
        
        for assessment in eligible:
            if assessment.channel not in exclude:
                return assessment
        
        return None
    
    def get_recommendations(
        self,
        observations: Dict[int, ChannelObservation],
        count: int = 5,
        exclude_channels: Optional[Set[int]] = None,
    ) -> List[ChannelEligibility]:
        """Get top N recommended channels.
        
        Args:
            observations: Dictionary of channel observations
            count: Number of recommendations
            exclude_channels: Additional channels to exclude
            
        Returns:
            List of top ChannelEligibility assessments
        """
        exclude = exclude_channels or set()
        eligible = self.get_eligible_channels(observations)
        
        recommendations = []
        for assessment in eligible:
            if assessment.channel not in exclude:
                recommendations.append(assessment)
                if len(recommendations) >= count:
                    break
        
        return recommendations
    
    def get_channel_ranking(
        self,
        observations: Dict[int, ChannelObservation],
    ) -> List[Tuple[int, float, str]]:
        """Get all channels ranked by activity.
        
        Args:
            observations: Dictionary of channel observations
            
        Returns:
            List of (channel, activity_percentage, status) tuples sorted by activity
        """
        assessments = self.assess_all_channels(observations)
        ranked = []
        for a in assessments:
            activity = a.activity_percentage if a.activity_percentage is not None else 101.0
            ranked.append((a.channel, activity, a.status))
        ranked.sort(key=lambda x: x[1])
        return ranked
    
    def get_blocked_channels(self) -> List[int]:
        """Get list of currently blocked channels.
        
        Returns:
            Sorted list of blocked channel numbers
        """
        return self._blocklist.get_blocked_channels()
    
    def get_peak_activity(self, channel: int) -> float:
        """Get peak observed activity for a channel.
        
        Args:
            channel: Channel number
            
        Returns:
            Peak activity percentage
        """
        validate_channel(channel)
        return self._channel_peaks.get(channel, 0.0)
    
    def reset_peaks(self) -> None:
        """Reset peak activity tracking."""
        self._channel_peaks.clear()
        self._consecutive_high.clear()
    
    def export_assessment(
        self,
        observations: Dict[int, ChannelObservation],
    ) -> List[dict]:
        """Export full channel assessment as list of dicts.
        
        Args:
            observations: Dictionary of channel observations
            
        Returns:
            List of assessment dictionaries
        """
        return [a.to_dict() for a in self.assess_all_channels(observations)]