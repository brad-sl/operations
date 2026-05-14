"""
Unit tests for config_loader.py and spend tracking in order_executor.py
"""

import pytest
import json
from pathlib import Path
from config_loader import ConfigLoader, TradingConfig
from order_executor import SpendTracker

def test_config_loader_valid():
    """Test loading valid config"""
    # Create temp config
    config_data = {
        "trading_pairs": ["BTC-USD"],
        "limits": {
            "daily_spend_usd": 1000,
            "max_position_size": {"BTC-USD": 0.05, "ETH-USD": 0.5},
            "max_daily_loss_usd": 200,
            "max_single_order_usd": 100
        },
        "settings": {
            "order_type": "limit",
            "sandbox_mode": True,
            "approval_required": True
        }
    }
    
    # Write temp file
    temp_path = Path("/tmp/test_config.json")
    with open(temp_path, 'w') as f:
        json.dump(config_data, f)
    
    # Load
    loader = ConfigLoader(str(temp_path))
    config = loader.get_config()
    
    assert config.trading_pairs == ["BTC-USD"]
    assert config.daily_spend_usd == 1000
    assert config.max_single_order_usd == 100
    assert config.sandbox_mode == True
    
    # Cleanup
    temp_path.unlink()

def test_config_validation():
    """Test config validation"""
    config_data = {
        "trading_pairs": [],  # INVALID: empty pairs
        "limits": {
            "daily_spend_usd": 1000,
            "max_position_size": {},
            "max_daily_loss_usd": 200,
            "max_single_order_usd": 100
        },
        "settings": {
            "order_type": "limit",
            "sandbox_mode": True,
            "approval_required": True
        }
    }
    
    temp_path = Path("/tmp/test_invalid_config.json")
    with open(temp_path, 'w') as f:
        json.dump(config_data, f)
    
    loader = ConfigLoader(str(temp_path))
    with pytest.raises(ValueError, match="No trading pairs"):
        loader.validate()
    
    temp_path.unlink()

def test_spend_tracker_budget():
    """Test daily budget tracking"""
    config = TradingConfig(
        trading_pairs=["BTC-USD"],
        daily_spend_usd=1000,
        max_single_order_usd=100,
        max_daily_loss_usd=200,
        position_limits={"BTC-USD": 0.05},
        order_type="limit",
        sandbox_mode=True,
        approval_required=True
    )
    
    tracker = SpendTracker(config)
    
    # Should be within budget
    assert tracker.within_daily_budget(500) == True
    tracker.daily_spend_usd += 500
    
    # Should still be within
    assert tracker.within_daily_budget(400) == True
    tracker.daily_spend_usd += 400
    
    # Should exceed budget
    assert tracker.within_daily_budget(200) == False

def test_position_limit():
    """Test position size limits"""
    config = TradingConfig(
        trading_pairs=["BTC-USD", "ETH-USD"],
        daily_spend_usd=1000,
        max_single_order_usd=100,
        max_daily_loss_usd=200,
        position_limits={"BTC-USD": 0.05, "ETH-USD": 0.5},
        order_type="limit",
        sandbox_mode=True,
        approval_required=True
    )
    
    tracker = SpendTracker(config)
    
    # BTC: 0.05 max
    assert tracker.within_position_limit("BTC-USD", 0.03) == True
    assert tracker.within_position_limit("BTC-USD", 0.05) == True
    assert tracker.within_position_limit("BTC-USD", 0.06) == False
    
    # ETH: 0.5 max
    assert tracker.within_position_limit("ETH-USD", 0.3) == True
    assert tracker.within_position_limit("ETH-USD", 0.5) == True
    assert tracker.within_position_limit("ETH-USD", 0.6) == False

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
