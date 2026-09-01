"""
Configuration loader for Crypto Trading Bot

Loads canonical trading_config_phase6.json (via paths) and provides validated access to:
- Trading pairs
- Position limits per pair
- Daily spend/loss limits
- Settings (order type, sandbox mode, approval required)


See docs/DATA_FLOW_AND_LOCATIONS.md and phase6/core/paths.py for paths and rules."""

import json
from pathlib import Path
from .paths import PROJECT_ROOT, TRADING_CONFIG_PHASE6
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

    # SCALING-1000 T0-02: feature flag (default false = legacy Brad path)
    # When true: use AccountContext injection + per-account paths
    # Brad live ALWAYS runs with this=False until T1+ gates.
    MULTI_TENANT_ENABLED: bool = False
    
    # STALE defaults (look like Advanced 1). Live book is often Intro 2 (0.4% maker / 0.8% taker).
    # Prefer data/state/fee_tier_snapshot_latest.json from phase6.core.fee_tier_snapshot.
    # Do NOT treat these constants as live truth for EV or audits (2026-08-31 fills dig).
    COINBASE_MAKER_FEE_RATE: float = 0.0025  # STALE placeholder — use fee_tier_snapshot
    COINBASE_TAKER_FEE_RATE: float = 0.0040  # STALE placeholder — use fee_tier_snapshot

class ConfigLoader:
    """Loads and validates trading_config.json"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            # Prefer canonical per DATA_FLOW_AND_LOCATIONS.md
            candidates = [
                PROJECT_ROOT / "trading_config_phase6.json",
                PROJECT_ROOT / "config" / "trading_config_phase6.json",
                Path(__file__).parent / "trading_config.json",  # legacy fallback
            ]
            config_path = next((p for p in candidates if p.exists()), candidates[0])
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
        """Get validated configuration as dataclass (mapped from Phase 6 config format)"""
        gs = self._config.get("global_settings", {})
        rm = self._config.get("risk_management", {})
        p6 = self._config.get("phase_6_specific", {})

        pairs = gs.get("pairs", [])

        # Map from Phase 6 config structure (see trading_config_phase6.json)
        total_cap = float(gs.get("total_capital", 1000.0))
        rebal_cap = float(gs.get("rebalance_cap_usd", 150.0))
        max_daily_loss_pct = float(rm.get("max_daily_loss_pct", 0.02))
        max_daily_loss_usd = total_cap * max_daily_loss_pct
        stop_loss_pct = float(rm.get("stop_loss_pct", 0.03))
        # position limits can be derived or extended; use per-pair or default to rebal size
        pos_limits = {p: rebal_cap for p in pairs} if pairs else {}
        sandbox = gs.get("sandbox_mode", True)
        multi_tenant = bool(
            gs.get("multi_tenant_enabled",
                   gs.get("MULTI_TENANT_ENABLED", False))
        )
        return TradingConfig(
            trading_pairs=pairs or [],
            daily_spend_usd=total_cap,
            max_single_order_usd=rebal_cap,
            max_daily_loss_usd=max_daily_loss_usd,
            position_limits=pos_limits,
            # Hardcoded market: Phase 6 path is market IOC until entry_execution.limit_first
            # is explicitly enabled (default OFF). Not read from JSON today.
            order_type="market",
            sandbox_mode=sandbox,
            approval_required=gs.get("approval_required", False),
            MULTI_TENANT_ENABLED=multi_tenant,
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
