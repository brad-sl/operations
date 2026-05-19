#!/usr/bin/env python3
"""
Final test suite for refactored Phase 6 (non-interactive, config-driven).
"""

import json
import pytest
import re
import subprocess
import tempfile
from pathlib import Path

from phase6 import (
    ConfigLoader,
    TradingConfig,
    TradingMode,
    Scenario,
    Phase6Initializer,
    AccountAnalyzer,
)


def extract_json_from_output(output):
    """Extract JSON from subprocess output (may have log lines before/after)."""
    # Find first { and last }
    start = output.find('{')
    end = output.rfind('}') + 1
    if start >= 0 and end > start:
        return json.loads(output[start:end])
    raise ValueError("No JSON found in output")


class TestConfigLoader:
    """Test configuration loading."""

    def test_load_valid_config(self):
        """Test loading valid config."""
        config = ConfigLoader.load('config/trading_config_phase6.json')
        
        assert config.global_settings.total_capital == 1000
        assert len(config.global_settings.pairs) > 0
        assert config.risk_management.stop_loss_pct == 2.0
        assert config.phase_6_specific.expansion_rules.max_pairs == 12

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file."""
        with pytest.raises(FileNotFoundError):
            ConfigLoader.load('nonexistent/path.json')

    def test_load_invalid_json(self):
        """Test loading invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            f.flush()
            
            with pytest.raises(ValueError, match="Invalid JSON"):
                ConfigLoader.load(f.name)
            
            Path(f.name).unlink()


class TestAccountAnalyzer:
    """Test scenario detection."""

    def test_fresh_start(self):
        """Test FRESH_START scenario detection."""
        balances = {'USD': 1000, 'USDC': 500}
        scenario = AccountAnalyzer.detect_scenario(balances)
        assert scenario == Scenario.FRESH_START

    def test_takeover_2(self):
        """Test TAKEOVER_2 scenario detection."""
        balances = {'BTC': 0.5, 'ETH': 2}
        scenario = AccountAnalyzer.detect_scenario(balances)
        assert scenario == Scenario.TAKEOVER_2

    def test_takeover_1(self):
        """Test TAKEOVER_1 scenario detection."""
        balances = {'USD': 500, 'BTC': 0.2, 'ETH': 1}
        scenario = AccountAnalyzer.detect_scenario(balances)
        assert scenario == Scenario.TAKEOVER_1

    def test_ready_to_start(self):
        """Test READY_TO_START scenario detection."""
        balances = {}
        scenario = AccountAnalyzer.detect_scenario(balances)
        assert scenario == Scenario.READY_TO_START

    def test_bank_your_wins(self):
        """Test BANK_YOUR_WINS scenario detection."""
        balances = {'USDC': 2000, 'USD': 800, 'BTC': 0.1, 'ETH': 1}
        scenario = AccountAnalyzer.detect_scenario(balances)
        assert scenario == Scenario.BANK_YOUR_WINS


class TestPhase6Initializer:
    """Test Phase 6 initialization."""

    @pytest.fixture
    def config(self):
        """Load test config."""
        return ConfigLoader.load('config/trading_config_phase6.json')

    def test_fresh_start_initialization(self, config):
        """Test FRESH_START initialization."""
        balances = {'USD': 1000, 'USDC': 0}
        
        init = Phase6Initializer(config, TradingMode.PAPER_TRADE, balances)
        state = init.detect_and_initialize()
        
        assert state['scenario'] == 'fresh_start'
        assert state['status'] == 'READY_TO_TRADE'
        assert state['mode'] == 'PAPER_TRADE'
        assert state['trading_balance'] == 1000
        assert state['deploy_budget'] == 800.0
        assert state['reserve_usd'] == 200.0

    def test_takeover_2_initialization(self, config):
        """Test TAKEOVER_2 initialization."""
        balances = {'BTC': 0.5, 'ETH': 2}
        
        init = Phase6Initializer(config, TradingMode.LIVE, balances)
        state = init.detect_and_initialize()
        
        assert state['scenario'] == 'takeover_2'
        assert state['status'] == 'READY_TO_TRADE'
        assert state['mode'] == 'LIVE'

    def test_ready_to_start_initialization(self, config):
        """Test READY_TO_START initialization."""
        balances = {}
        
        init = Phase6Initializer(config, TradingMode.PAPER_TRADE, balances)
        state = init.detect_and_initialize()
        
        assert state['scenario'] == 'ready_to_start'
        assert state['status'] == 'AWAITING_FUNDING'


class TestNonInteractiveStartup:
    """Test non-interactive startup scenarios."""

    def test_can_start_without_stdin(self):
        """Verify startup with no stdin (safe for background processes)."""
        result = subprocess.run(
            ['python3', 'phase6.py', '--config', 'config/trading_config_phase6.json',
             '--mode', 'PAPER_TRADE', '--mock-balances', '{"USD": 2000}'],
            input='',
            capture_output=True,
            timeout=2,
            text=True,
            cwd='/home/brad/.openclaw/workspace/coding-products/crypto-bot'
        )
        
        assert result.returncode == 0
        output = extract_json_from_output(result.stdout)
        assert output['status'] == 'READY_TO_TRADE'

    def test_env_var_mode_override(self):
        """Test PHASE_MODE env var override."""
        import os
        
        env = os.environ.copy()
        env['PHASE_MODE'] = 'LIVE'
        
        result = subprocess.run(
            ['python3', 'phase6.py', '--config', 'config/trading_config_phase6.json',
             '--mock-balances', '{"USD": 500}'],
            input='',
            capture_output=True,
            timeout=2,
            text=True,
            env=env,
            cwd='/home/brad/.openclaw/workspace/coding-products/crypto-bot'
        )
        
        assert result.returncode == 0
        output = extract_json_from_output(result.stdout)
        assert output['mode'] == 'LIVE'

    def test_command_line_args(self):
        """Test command-line argument parsing."""
        result = subprocess.run(
            ['python3', 'phase6.py', '--help'],
            capture_output=True,
            timeout=2,
            text=True,
            cwd='/home/brad/.openclaw/workspace/coding-products/crypto-bot'
        )
        
        assert result.returncode == 0
        assert '--config' in result.stdout
        assert '--mode' in result.stdout
        assert 'PAPER_TRADE' in result.stdout
        assert 'LIVE' in result.stdout


if __name__ == '__main__':
    pytest.main(['-v', __file__])
