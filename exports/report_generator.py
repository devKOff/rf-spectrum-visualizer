"""Report generation and export module for RF Spectrum Visualizer."""

import json
import csv
import time
from typing import List, Dict, Any, Optional, TextIO
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict

from config import AppConfig
from scanner.scanner_engine import SpectrumData, ChannelObservation
from mitigation.blocklist_manager import BlocklistManager
from analysis.selector import ChannelSelector, ChannelEligibility
from scanner.channel_utils import get_all_channels


class ReportGenerator:
    """Generate and export comprehensive scan reports."""
    
    def __init__(
        self,
        config: AppConfig,
        spectrum_data: SpectrumData,
        blocklist: BlocklistManager,
        channel_selector: ChannelSelector,
    ):
        self._config = config
        self._spectrum_data = spectrum_data
        self._blocklist = blocklist
        self._channel_selector = channel_selector
        self._export_dir = Path(config.storage.export_dir)
        self._export_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_full_report(self) -> Dict[str, Any]:
        """Generate a comprehensive report with all data."""
        observations = self._spectrum_data.get_all_observations()
        assessments = self._channel_selector.assess_all_channels(observations)
        blocked_channels = self._blocklist.get_blocked_channels()
        recommendations = self._channel_selector.get_recommendations(observations, count=10)
        
        return {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "backend": self._spectrum_data.get_backend(),
                "scan_count": self._spectrum_data.get_scan_count(),
                "channel_range": [
                    self._config.channel.start_channel,
                    self._config.channel.end_channel
                ],
                "measurement_window": self._config.scan.measurement_window,
                "sampling_interval": self._config.scan.sampling_interval,
                "thresholds": {
                    "clear_max": self._config.thresholds.clear_max,
                    "moderate_max": self._config.thresholds.moderate_max,
                    "busy_max": self._config.thresholds.busy_max,
                    "heavy_min": self._config.thresholds.heavy_min,
                },
                "persistent_threshold": self._channel_selector.persistent_threshold,
                "hysteresis": self._channel_selector.hysteresis,
            },
            "blocklist": {
                "blocked_channels": blocked_channels,
                "count": len(blocked_channels),
                "entries": [entry.to_dict() for entry in self._blocklist.get_blocked_entries()],
            },
            "channel_assessments": [a.to_dict() for a in assessments],
            "recommendations": [r.to_dict() for r in recommendations],
            "summary": self._generate_summary(assessments, blocked_channels, recommendations),
        }
    
    def _generate_summary(
        self,
        assessments: List[ChannelEligibility],
        blocked_channels: List[int],
        recommendations: List[ChannelEligibility],
    ) -> Dict[str, Any]:
        """Generate summary statistics."""
        total = len(assessments)
        eligible = sum(1 for a in assessments if a.eligible)
        blocked = len(blocked_channels)
        insufficient = sum(1 for a in assessments if a.reason.value == "insufficient_data")
        errors = sum(1 for a in assessments if a.reason.value == "sensor_error")
        high_activity = sum(1 for a in assessments if a.reason.value in ("high_activity", "persistent_high_activity"))
        
        activities = [a.activity_percentage for a in assessments if a.activity_percentage is not None]
        
        return {
            "total_channels": total,
            "eligible_channels": eligible,
            "blocked_channels": blocked,
            "insufficient_data": insufficient,
            "sensor_errors": errors,
            "high_activity": high_activity,
            "activity_stats": {
                "min": min(activities) if activities else None,
                "max": max(activities) if activities else None,
                "avg": sum(activities) / len(activities) if activities else None,
                "median": sorted(activities)[len(activities)//2] if activities else None,
            },
            "top_recommendation": recommendations[0].to_dict() if recommendations else None,
            "recommendation_count": len(recommendations),
        }
    
    def export_json(self, output: TextIO) -> None:
        """Export full report as JSON."""
        report = self.generate_full_report()
        json.dump(report, output, indent=2, separators=(',', ': '))
        output.write('\n')
    
    def export_json_file(self, filename: Optional[str] = None) -> Path:
        """Export full report to JSON file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backend = self._spectrum_data.get_backend()
            filename = f"report_{backend}_{timestamp}.json"
        
        filepath = self._export_dir / filename
        with open(filepath, 'w', encoding='utf-8') as f:
            self.export_json(f)
        
        return filepath
    
    def export_csv(self, output: TextIO) -> None:
        """Export channel data as CSV."""
        observations = self._spectrum_data.get_all_observations()
        assessments = self._channel_selector.assess_all_channels(observations)
        
        fieldnames = [
            "channel", "frequency_mhz", "activity_percentage", "status",
            "data_sufficient", "valid_samples", "rpd_positive", "rpd_negative",
            "eligible", "eligibility_reason", "blocked", "blocked_at", "block_reason",
            "measurement_window", "sampling_interval", "backend", "timestamp",
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        blocked_entries = {e.channel: e for e in self._blocklist.get_blocked_entries()}
        
        for assessment in assessments:
            obs = observations.get(assessment.channel)
            blocked_entry = blocked_entries.get(assessment.channel)
            
            row = {
                "channel": assessment.channel,
                "frequency_mhz": assessment.frequency_mhz,
                "activity_percentage": assessment.activity_percentage,
                "status": assessment.status,
                "data_sufficient": assessment.data_sufficient,
                "valid_samples": obs.valid_samples if obs else 0,
                "rpd_positive": obs.rpd_positive if obs else 0,
                "rpd_negative": obs.rpd_negative if obs else 0,
                "eligible": assessment.eligible,
                "eligibility_reason": assessment.reason.value,
                "blocked": assessment.blocked,
                "blocked_at": blocked_entry.blocked_at if blocked_entry else "",
                "block_reason": blocked_entry.reason if blocked_entry else "",
                "measurement_window": obs.measurement_window if obs else self._config.scan.measurement_window,
                "sampling_interval": obs.sampling_interval if obs else self._config.scan.sampling_interval,
                "backend": obs.backend if obs else self._spectrum_data.get_backend(),
                "timestamp": obs.iso_timestamp if obs else "",
            }
            writer.writerow(row)
    
    def export_csv_file(self, filename: Optional[str] = None) -> Path:
        """Export channel data to CSV file."""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backend = self._spectrum_data.get_backend()
            filename = f"channels_{backend}_{timestamp}.csv"
        
        filepath = self._export_dir / filename
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            self.export_csv(f)
        
        return filepath
    
    def export_blocklist_json(self, output: TextIO) -> None:
        """Export only blocklist as JSON."""
        output.write(self._blocklist.export_json())
        output.write('\n')
    
    def export_blocklist_csv(self, output: TextIO) -> None:
        """Export only blocklist as CSV."""
        entries = self._blocklist.get_blocked_entries()
        
        fieldnames = ["channel", "frequency_mhz", "blocked_at", "reason"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for entry in entries:
            writer.writerow(entry.to_dict())
    
    def export_waterfall_csv(self, output: TextIO, max_age: Optional[float] = None) -> None:
        """Export waterfall history as CSV."""
        data = self._spectrum_data.get_waterfall_data(max_age=max_age)
        
        fieldnames = [
            "timestamp", "channel", "frequency_mhz", "activity_percentage",
            "status", "backend", "valid_samples", "rpd_positive",
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for obs in data:
            writer.writerow({
                "timestamp": obs.iso_timestamp,
                "channel": obs.channel,
                "frequency_mhz": obs.frequency_mhz,
                "activity_percentage": obs.activity_percentage,
                "status": obs.status,
                "backend": obs.backend,
                "valid_samples": obs.valid_samples,
                "rpd_positive": obs.rpd_positive,
            })
    
    def export_all_formats(self, base_filename: Optional[str] = None) -> Dict[str, Path]:
        """Export all formats at once."""
        if base_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backend = self._spectrum_data.get_backend()
            base_filename = f"full_report_{backend}_{timestamp}"
        
        results = {}
        
        json_path = self._export_dir / f"{base_filename}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            self.export_json(f)
        results["json"] = json_path
        
        csv_path = self._export_dir / f"{base_filename}_channels.csv"
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            self.export_csv(f)
        results["csv"] = csv_path
        
        blocklist_json = self._export_dir / f"{base_filename}_blocklist.json"
        with open(blocklist_json, 'w', encoding='utf-8') as f:
            self.export_blocklist_json(f)
        results["blocklist_json"] = blocklist_json
        
        blocklist_csv = self._export_dir / f"{base_filename}_blocklist.csv"
        with open(blocklist_csv, 'w', newline='', encoding='utf-8') as f:
            self.export_blocklist_csv(f)
        results["blocklist_csv"] = blocklist_csv
        
        waterfall_csv = self._export_dir / f"{base_filename}_waterfall.csv"
        with open(waterfall_csv, 'w', newline='', encoding='utf-8') as f:
            self.export_waterfall_csv(f)
        results["waterfall_csv"] = waterfall_csv
        
        return results