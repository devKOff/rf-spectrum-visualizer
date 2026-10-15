"""Tests for export functionality."""

import pytest
import json
import csv
import io
import tempfile
import os

from config import AppConfig, ChannelConfig, ScanConfig, ThresholdConfig, BlocklistConfig
from scanner.scanner_engine import SpectrumData, ChannelObservation
from mitigation.blocklist_manager import BlocklistManager
from analysis.selector import ChannelSelector
from exports.report_generator import ReportGenerator


class TestExports:
    """Test export functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return AppConfig(
            channel=ChannelConfig(start_channel=0, end_channel=5),
            scan=ScanConfig(measurement_window=1.0, sampling_interval=0.01),
            thresholds=ThresholdConfig(),
        )
    
    @pytest.fixture
    def spectrum_data(self, config):
        """Create SpectrumData with test observations."""
        sd = SpectrumData(config)
        sd.set_backend("sim")
        
        # Add observations for all channels
        for ch in range(0, 6):
            if ch == 2:
                activity = 80.0  # High activity
                status = "Heavy Load"
            elif ch == 4:
                activity = None  # Insufficient data
                status = "INSUFFICIENT DATA"
            else:
                activity = float(ch * 5)
                status = "Clear"
            
            obs = ChannelObservation(
                timestamp=1000000.0 + ch,
                channel=ch,
                frequency_mhz=2400 + ch,
                backend="sim",
                valid_samples=100 if activity is not None else 5,
                rpd_positive=int(activity) if activity is not None else 0,
                rpd_negative=100 - int(activity) if activity is not None else 100,
                activity_percentage=activity,
                status=status,
                data_sufficient=activity is not None,
                measurement_window=1.0,
                sampling_interval=0.01,
            )
            sd.update_observation(obs)
        
        return sd
    
    @pytest.fixture
    def blocklist(self):
        """Create blocklist with some blocked channels using temporary file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('[]')
            temp_path = f.name
        
        config = BlocklistConfig(file_path=temp_path)
        bl = BlocklistManager(config)
        bl.block_channel(5, "Reserved")  # Block channel 5 instead of 2
        # Channel 2 will have high activity but not be blocked
        
        yield bl
        
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    @pytest.fixture
    def selector(self, config, blocklist):
        """Create channel selector."""
        return ChannelSelector(config.channel, config.thresholds, blocklist)
    
    @pytest.fixture
    def report_gen(self, config, spectrum_data, blocklist, selector):
        """Create report generator with temporary export directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config.storage.export_dir = tmpdir
            yield ReportGenerator(config, spectrum_data, blocklist, selector)
    
    def test_generate_full_report(self, report_gen):
        """Test generating full report."""
        report = report_gen.generate_full_report()
        
        assert "metadata" in report
        assert "blocklist" in report
        assert "channel_assessments" in report
        assert "recommendations" in report
        assert "summary" in report
        
        # Check metadata
        assert report["metadata"]["backend"] == "sim"
        assert report["metadata"]["channel_range"] == [0, 5]
        
        # Check blocklist
        assert report["blocklist"]["count"] == 1
        assert set(report["blocklist"]["blocked_channels"]) == {5}
        
        # Check assessments
        assert len(report["channel_assessments"]) == 6
        
        # Check recommendations (should exclude blocked and high activity)
        # Channel 2 has high activity (80%), channel 4 has insufficient data, channel 5 is blocked
        # Eligible: 0, 1, 3
        recs = report["recommendations"]
        assert len(recs) == 3
        rec_channels = {r["channel"] for r in recs}
        assert rec_channels == {0, 1, 3}
    
    def test_export_json(self, report_gen):
        """Test JSON export."""
        output = io.StringIO()
        report_gen.export_json(output)
        
        json_str = output.getvalue()
        data = json.loads(json_str)
        
        assert "metadata" in data
        assert "blocklist" in data
    
    def test_export_json_file(self, report_gen):
        """Test JSON file export."""
        path = report_gen.export_json_file("test_report.json")
        
        assert path.exists()
        assert path.suffix == ".json"
        
        with open(path) as f:
            data = json.load(f)
        
        assert "metadata" in data
    
    def test_export_csv(self, report_gen):
        """Test CSV export."""
        output = io.StringIO()
        report_gen.export_csv(output)
        
        csv_str = output.getvalue()
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        
        assert len(rows) == 6  # 6 channels
        
        # Check required fields
        required_fields = [
            "channel", "frequency_mhz", "activity_percentage", "status",
            "data_sufficient", "valid_samples", "rpd_positive", "rpd_negative",
            "eligible", "eligibility_reason", "blocked", "blocked_at", "block_reason",
        ]
        for field in required_fields:
            assert field in reader.fieldnames
        
        # Check specific rows
        row_dict = {int(r["channel"]): r for r in rows}
        
        # Channel 2: high activity (not blocked)
        assert row_dict[2]["blocked"] == "False"
        assert row_dict[2]["eligible"] == "False"
        assert row_dict[2]["eligibility_reason"] == "high_activity"
        
        # Channel 5: blocked, but low activity
        assert row_dict[5]["blocked"] == "True"
        assert row_dict[5]["block_reason"] == "Reserved"
        
        # Channel 4: insufficient data
        assert row_dict[4]["data_sufficient"] == "False"
        assert row_dict[4]["activity_percentage"] == ""
    
    def test_export_csv_file(self, report_gen):
        """Test CSV file export."""
        path = report_gen.export_csv_file("test_channels.csv")
        
        assert path.exists()
        assert path.suffix == ".csv"
        
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        assert len(rows) == 6
    
    def test_export_blocklist_json(self, report_gen):
        """Test blocklist JSON export."""
        output = io.StringIO()
        report_gen.export_blocklist_json(output)
        
        json_str = output.getvalue()
        data = json.loads(json_str)
        
        assert "blocklist" in data
        assert len(data["blocklist"]) == 1
    
    def test_export_blocklist_csv(self, report_gen):
        """Test blocklist CSV export."""
        output = io.StringIO()
        report_gen.export_blocklist_csv(output)
        
        csv_str = output.getvalue()
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        
        assert len(rows) == 1
        assert reader.fieldnames == ["channel", "frequency_mhz", "blocked_at", "reason"]
    
    def test_export_waterfall_csv(self, report_gen, spectrum_data):
        """Test waterfall CSV export."""
        output = io.StringIO()
        report_gen.export_waterfall_csv(output)
        
        csv_str = output.getvalue()
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        
        assert len(rows) == 6  # One per channel
        assert reader.fieldnames == [
            "timestamp", "channel", "frequency_mhz", "activity_percentage",
            "status", "backend", "valid_samples", "rpd_positive",
        ]
    
    def test_export_all_formats(self, report_gen):
        """Test exporting all formats at once."""
        results = report_gen.export_all_formats("test_full")
        
        expected_formats = ["json", "csv", "blocklist_json", "blocklist_csv", "waterfall_csv"]
        for fmt in expected_formats:
            assert fmt in results
            assert results[fmt].exists()
    
    def test_summary_generation(self, report_gen):
        """Test summary statistics generation."""
        report = report_gen.generate_full_report()
        summary = report["summary"]
        
        assert summary["total_channels"] == 6
        assert summary["eligible_channels"] == 3  # 0, 1, 3
        assert summary["blocked_channels"] == 1   # 5
        assert summary["insufficient_data"] == 1  # 4
        assert summary["sensor_errors"] == 0
        assert summary["high_activity"] == 1      # 2
        
        # Activity stats
        assert summary["activity_stats"]["min"] == 0.0
        assert summary["activity_stats"]["max"] == 80.0
        assert summary["activity_stats"]["avg"] > 0
        
        # Top recommendation
        assert summary["top_recommendation"] is not None
        assert summary["top_recommendation"]["channel"] == 0
        assert summary["recommendation_count"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])