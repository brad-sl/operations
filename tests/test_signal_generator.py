"""
Unit Tests for Signal Generator — Module 5

Tests cover:
- Signal generation logic (BUY/SELL/HOLD)
- Confidence scoring
- Edge cases (extreme RSI/sentiment values)
- Checkpointing functionality
- Error handling
"""

import pytest
import json
import os
from pathlib import Path
from datetime import datetime
import sys

# Add module to path
sys.path.insert(0, '/home/brad/.openclaw/workspace/operations/crypto-bot')

from signal_generator import Signal, SignalGenerator


class TestSignal:
    """Test Signal dataclass."""

    def test_signal_creation(self):
        """Test creating a Signal object."""
        sig = Signal(
            timestamp="2026-03-23T11:00:00Z",
            rsi=65.5,
            sentiment=0.7,
            combined_score=0.65,
            signal="BUY",
            confidence=0.85,
            reasoning="Test signal",
        )
        assert sig.signal == "BUY"
        assert sig.confidence == 0.85
        assert sig.rsi == 65.5

    def test_signal_dataclass_to_dict(self):
        """Test converting Signal to dict (for checkpointing)."""
        sig = Signal(
            timestamp="2026-03-23T11:00:00Z",
            rsi=70.0,
            sentiment=0.8,
            combined_score=0.72,
            signal="BUY",
            confidence=0.9,
            reasoning="Strong buy signal",
        )
        sig_dict = {
            "timestamp": sig.timestamp,
            "rsi": sig.rsi,
            "sentiment": sig.sentiment,
            "combined_score": sig.combined_score,
            "signal": sig.signal,
            "confidence": sig.confidence,
            "reasoning": sig.reasoning,
        }
        assert sig_dict["signal"] == "BUY"
        assert isinstance(sig_dict, dict)


class TestSignalGenerator:
    """Test SignalGenerator class."""

    def test_initialization_valid(self):
        """Test initializing with valid data."""
        rsi_data = [50, 60, 70]
        sentiment_data = [0.2, 0.3, 0.4]
        gen = SignalGenerator(rsi_data, sentiment_data)
        assert len(gen.rsi_data) == 3
        assert len(gen.sentiment_data) == 3

    def test_initialization_mismatched_lengths(self):
        """Test that mismatched lengths raise ValueError."""
        rsi_data = [50, 60, 70]
        sentiment_data = [0.2, 0.3]  # Only 2 values
        with pytest.raises(ValueError, match="must have equal length"):
            SignalGenerator(rsi_data, sentiment_data)

    def test_initialization_empty_data(self):
        """Test that empty data raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            SignalGenerator([], [])

    def test_generate_signal_buy(self):
        """Test generating a BUY signal."""
        gen = SignalGenerator([85], [0.95])
        sig = gen.generate_signal(rsi=85, sentiment=0.95)
        
        assert sig.signal == "BUY"
        assert sig.rsi == 85
        assert sig.sentiment == 0.95
        assert sig.confidence > 0.6
        assert "BUY" in sig.reasoning

    def test_generate_signal_sell(self):
        """Test generating a SELL signal."""
        gen = SignalGenerator([20], [-0.8])
        sig = gen.generate_signal(rsi=20, sentiment=-0.8)
        
        assert sig.signal == "SELL"
        assert sig.rsi == 20
        assert sig.sentiment == -0.8
        assert sig.confidence > 0.6
        assert "SELL" in sig.reasoning

    def test_generate_signal_hold(self):
        """Test generating a HOLD signal."""
        gen = SignalGenerator([50], [0.0])
        sig = gen.generate_signal(rsi=50, sentiment=0.0)
        
        assert sig.signal == "HOLD"
        assert sig.confidence == 0.0
        assert "HOLD" in sig.reasoning

    def test_generate_signal_edge_rsi_overbought(self):
        """Test RSI overbought edge case (>80)."""
        gen = SignalGenerator([90], [0.5])
        sig = gen.generate_signal(rsi=90, sentiment=0.5)
        
        assert sig.signal == "BUY"
        assert sig.confidence >= 0.6

    def test_generate_signal_edge_rsi_oversold(self):
        """Test RSI oversold edge case (<20)."""
        gen = SignalGenerator([10], [-0.5])
        sig = gen.generate_signal(rsi=10, sentiment=-0.5)
        
        assert sig.signal == "SELL"
        assert sig.confidence >= 0.6

    def test_generate_signal_confidence_cap(self):
        """Test that confidence is capped at 1.0."""
        gen = SignalGenerator([100], [1.0])
        sig = gen.generate_signal(rsi=100, sentiment=1.0)
        
        assert sig.confidence <= 1.0

    def test_generate_signal_timestamp_format(self):
        """Test that timestamp is ISO 8601 UTC."""
        gen = SignalGenerator([50], [0.0])
        sig = gen.generate_signal(rsi=50, sentiment=0.0)
        
        # Should end with 'Z' for UTC
        assert sig.timestamp.endswith("Z")
        # Should be parseable as ISO format
        datetime.fromisoformat(sig.timestamp.replace("Z", "+00:00"))

    def test_generate_all_signals(self):
        """Test generating multiple signals."""
        rsi_values = [30, 50, 70, 80, 40]
        sentiment_values = [-0.5, 0.0, 0.5, 0.8, -0.3]
        gen = SignalGenerator(rsi_values, sentiment_values)
        
        signals = gen.generate_all_signals()
        
        assert len(signals) == 5
        assert all(isinstance(s, Signal) for s in signals)
        assert all(s.signal in ["BUY", "SELL", "HOLD"] for s in signals)

    def test_generate_all_signals_large_dataset(self):
        """Test generating signals for 100+ data points."""
        rsi_values = [50 + 10 * (i % 5) for i in range(100)]
        sentiment_values = [0.3 * (i % 7) - 0.9 for i in range(100)]
        gen = SignalGenerator(rsi_values, sentiment_values)
        
        signals = gen.generate_all_signals()
        
        assert len(signals) == 100
        # Verify distribution (not all same signal)
        signal_types = set(s.signal for s in signals)
        assert len(signal_types) > 1  # Should have multiple types


class TestCheckpointing:
    """Test checkpointing functionality."""

    def test_checkpoint_files_created(self, tmp_path):
        """Test that checkpoint files are created."""
        # Set checkpoint output directory
        os.environ["CHECKPOINT_OUTPUT_DIR"] = str(tmp_path)
        os.environ["SESSION_ID"] = "test-signal-gen-checkpoint"
        
        rsi_values = [50, 60, 70, 80, 90]
        sentiment_values = [0.2, 0.3, 0.4, 0.5, 0.6]
        gen = SignalGenerator(rsi_values, sentiment_values)
        
        signals = gen.generate_all_signals()
        
        # Verify checkpoint files exist
        state_file = Path(gen.checkpointer.output_dir) / "STATE.json"
        manifest_file = Path(gen.checkpointer.output_dir) / "MANIFEST.json"
        recovery_file = Path(gen.checkpointer.output_dir) / "RECOVERY.md"
        
        assert state_file.exists(), f"STATE.json not found at {state_file}"
        assert manifest_file.exists(), f"MANIFEST.json not found at {manifest_file}"
        assert recovery_file.exists(), f"RECOVERY.md not found at {recovery_file}"

    def test_state_json_structure(self, tmp_path):
        """Test STATE.json has correct structure."""
        os.environ["CHECKPOINT_OUTPUT_DIR"] = str(tmp_path)
        os.environ["SESSION_ID"] = "test-state-structure"
        
        rsi_values = [50, 60, 70]
        sentiment_values = [0.2, 0.3, 0.4]
        gen = SignalGenerator(rsi_values, sentiment_values)
        
        signals = gen.generate_all_signals()
        
        state_file = Path(gen.checkpointer.output_dir) / "STATE.json"
        with open(state_file) as f:
            state = json.load(f)
        
        # Check required keys
        assert "sessionId" in state
        assert "agent" in state
        assert "progress" in state
        assert "status" in state
        assert state["agent"] == "signal_generator"
        assert state["progress"]["total"] == 3
        assert state["progress"]["completed"] == 3

    def test_manifest_json_structure(self, tmp_path):
        """Test MANIFEST.json has correct structure."""
        os.environ["CHECKPOINT_OUTPUT_DIR"] = str(tmp_path)
        os.environ["SESSION_ID"] = "test-manifest-structure"
        
        rsi_values = [50, 60, 70]
        sentiment_values = [0.2, 0.3, 0.4]
        gen = SignalGenerator(rsi_values, sentiment_values)
        
        signals = gen.generate_all_signals()
        
        manifest_file = Path(gen.checkpointer.output_dir) / "MANIFEST.json"
        with open(manifest_file) as f:
            manifest = json.load(f)
        
        # Check required keys
        assert "sessionId" in manifest
        assert "agent" in manifest
        assert "outputs" in manifest
        assert "summary" in manifest
        assert len(manifest["outputs"]["completed"]) == 3


class TestSignalSummary:
    """Test signal summary statistics."""

    def test_get_signal_summary_empty(self):
        """Test summary for empty signal list."""
        gen = SignalGenerator([50], [0.0])
        summary = gen.get_signal_summary([])
        
        assert summary["total"] == 0
        assert summary["buy"] == 0
        assert summary["sell"] == 0
        assert summary["hold"] == 0

    def test_get_signal_summary_mixed(self):
        """Test summary with mixed signals."""
        rsi_values = [85, 15, 50, 90, 10]
        sentiment_values = [0.95, -0.95, 0.0, 0.99, -0.99]
        gen = SignalGenerator(rsi_values, sentiment_values)
        signals = gen.generate_all_signals()
        
        summary = gen.get_signal_summary(signals)
        
        assert summary["total"] == 5
        assert summary["buy"] > 0
        assert summary["sell"] > 0
        assert summary["hold"] >= 0
        assert summary["avg_confidence"] >= 0
        assert summary["avg_confidence"] <= 1.0

    def test_get_signal_summary_all_buy(self):
        """Test summary when all signals are BUY."""
        rsi_values = [80, 85, 90]
        sentiment_values = [0.8, 0.9, 0.95]
        gen = SignalGenerator(rsi_values, sentiment_values)
        signals = gen.generate_all_signals()
        
        summary = gen.get_signal_summary(signals)
        
        assert summary["buy"] == 3
        assert summary["sell"] == 0
        assert summary["hold"] == 0
        assert summary["buy_percentage"] == 100.0

    def test_get_signal_summary_all_sell(self):
        """Test summary when all signals are SELL."""
        rsi_values = [10, 15, 20]
        sentiment_values = [-0.9, -0.95, -0.98]
        gen = SignalGenerator(rsi_values, sentiment_values)
        signals = gen.generate_all_signals()
        
        summary = gen.get_signal_summary(signals)
        
        assert summary["sell"] == 3
        assert summary["buy"] == 0
        assert summary["hold"] == 0
        assert summary["sell_percentage"] == 100.0


class TestErrorHandling:
    """Test error handling."""

    def test_non_numeric_rsi_data(self):
        """Test that non-numeric RSI data raises error."""
        with pytest.raises((TypeError, ValueError)):
            gen = SignalGenerator(["not", "numeric"], [0.1, 0.2])
            gen.generate_all_signals()

    def test_recovery_point_tracking(self):
        """Test recovery point information."""
        gen = SignalGenerator([50, 60, 70], [0.1, 0.2, 0.3])
        signals = gen.generate_all_signals()
        
        recovery = gen.checkpointer.get_recovery_point()
        assert "currentProgress" in recovery
        assert "nextTaskIndex" in recovery
        assert recovery["canResume"] == True


# Fixtures for common test data
@pytest.fixture
def sample_rsi_data():
    """Sample RSI data for testing."""
    return [25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80]


@pytest.fixture
def sample_sentiment_data():
    """Sample sentiment data for testing."""
    return [-0.5, -0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]


@pytest.fixture
def sample_generator(sample_rsi_data, sample_sentiment_data):
    """Sample generator for testing."""
    return SignalGenerator(sample_rsi_data, sample_sentiment_data)


class TestWithFixtures:
    """Tests using fixtures."""

    def test_generator_with_fixtures(self, sample_generator):
        """Test generator with fixture data."""
        signals = sample_generator.generate_all_signals()
        assert len(signals) == 12

    def test_summary_with_fixtures(self, sample_generator):
        """Test summary generation with fixture data."""
        signals = sample_generator.generate_all_signals()
        summary = sample_generator.get_signal_summary(signals)
        assert summary["total"] == 12
