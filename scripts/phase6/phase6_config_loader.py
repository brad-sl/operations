import logging
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any

logger = logging.getLogger(__name__)

class Scenario(Enum):
    FRESH_START = "FRESH_START"
    TAKEOVER_1 = "TAKEOVER_1"
    TAKEOVER_2 = "TAKEOVER_2"
    READY_TO_START = "READY_TO_START"
    BANK_YOUR_WINS = "BANK_YOUR_WINS"

@dataclass
class ScenarioConfig:
    reserve_pct: float
    deploy_pct: float
    self_fund_pct: float  # For TAKEOVER_2
    sl_pct: float  # Default SL from entry/current
    tp_pct: float  # Default TP
    min_reserve_usd: float

SCENARIO_CONFIGS: Dict[Scenario, ScenarioConfig] = {
    Scenario.FRESH_START: ScenarioConfig(
        reserve_pct=0.20,
        deploy_pct=0.80,
        self_fund_pct=0.0,
        sl_pct=-0.05,
        tp_pct=0.10,
        min_reserve_usd=100.0
    ),
    Scenario.TAKEOVER_1: ScenarioConfig(
        reserve_pct=0.20,
        deploy_pct=0.60,  # Less aggressive due to existing positions
        self_fund_pct=0.0,
        sl_pct=-0.05,
        tp_pct=0.10,
        min_reserve_usd=100.0
    ),
    Scenario.TAKEOVER_2: ScenarioConfig(
        reserve_pct=0.20,
        deploy_pct=0.80,
        self_fund_pct=0.20,
        sl_pct=-0.05,
        tp_pct=0.10,
        min_reserve_usd=100.0
    ),
    Scenario.READY_TO_START: ScenarioConfig(
        reserve_pct=0.20,
        deploy_pct=0.80,
        self_fund_pct=0.0,
        sl_pct=-0.05,
        tp_pct=0.10,
        min_reserve_usd=100.0
    ),
    Scenario.BANK_YOUR_WINS: ScenarioConfig(
        reserve_pct=0.20,
        deploy_pct=0.80,
        self_fund_pct=0.0,
        sl_pct=-0.05,
        tp_pct=0.10,
        min_reserve_usd=500.0  # Higher for advanced
    )
}

def load_scenario_config(scenario: Scenario) -> ScenarioConfig:
    """Load config for given scenario."""
    if scenario not in SCENARIO_CONFIGS:
        raise ValueError(f"Unknown scenario: {scenario}")
    config = SCENARIO_CONFIGS[scenario]
    logger.info(f"Loaded config for {scenario.value}: reserve={config.reserve_pct}, deploy={config.deploy_pct}")
    return config
