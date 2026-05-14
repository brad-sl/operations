"""
Configuration loader for Crypto Trading Bot

Loads trading_config.json and provides validated access to:
- Trading pairs
- Position limits per pair
- Daily spend/loss limits
- Settings (order type, sandbox mode, approval required)
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass

# Phase 4 Constants
MIN_POSITION_HOLD_MINUTES = 5  # Minimum hold time before exit allowed
RSI_CONFIRMATION_BARS = 2      # RSI must cross threshold for 2 consecutive cycles
NOTIONAL_ALLOCATION = {
    'BTC-USD': 500.0,  # $500 fractional BTC
    'XRP-USD': 500.0,  # $500 fractional XRP
}

@dataclass
class TradingConfig:
    """Validated trading configuration."""
    trading_pairs: List[str]
    daily_spend_usd: float
    max_single_order_usd: float
    max_daily_loss_usd: float
    position_limits: Dict[str, float]  # pair -> max size
    order_type: str
    sandbox_mode: bool
    approval_required: bool
    
    # Coinbase fee rates (Tier: Advanced 1 = 0.25% maker, 0.40% taker)
    # Source: https://help.coinbase.com/en/exchange/trading-and-funding/exchange-fees
    # Note: Actual rates are volume-tiered. Use API /fees endpoint for real-time rates.
    COINBASE_MAKER_FEE_RATE: float = 0.0025  # 0.25% for maker orders (limit orders)
    COINBASE_TAKER_FEE_RATE: float = 0.0040  # 0.40% for taker orders (market orders)

class ConfigLoader:
    """Loads and validates trading_config.json"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent / "trading_config.json"
        else:
            config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        self.config_path = config_path
        self._config = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Load and parse trading_config.json"""
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def get_config(self) -> TradingConfig:
        """Get validated configuration as dataclass"""
        return TradingConfig(
            trading_pairs=self._config["trading_pairs"],
            daily_spend_usd=self._config["limits"]["daily_spend_usd"],
            max_single_order_usd=self._config["limits"]["max_single_order_usd"],
            max_daily_loss_usd=self._config["limits"]["max_daily_loss_usd"],
            position_limits=self._config["limits"]["max_position_size"],
            order_type=self._config["settings"]["order_type"],
            sandbox_mode=self._config["settings"]["sandbox_mode"],
            approval_required=self._config["settings"]["approval_required"],
        )
    
    def validate(self) -> bool:
        """Validate config structure and values"""
        try:
            config = self.get_config()
            assert len(config.trading_pairs) > 0, "No trading pairs configured"
            assert config.daily_spend_usd > 0, "Daily spend limit must be positive"
            assert config.max_single_order_usd > 0, "Max single order must be positive"
            assert config.sandbox_mode or config.approval_required, "Live mode requires approval"
            return True
        except (AssertionError, KeyError, TypeError) as e:
            raise ValueError(f"Config validation failed: {e}")

# Usage example:
# loader = ConfigLoader()
# config = loader.get_config()
# print(config.daily_spend_usd)  # 1000.0
