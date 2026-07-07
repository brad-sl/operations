"""
ANALYST-OPT R1: Canonical scenario knobs and cross-path mapping.

Single object built from scenario pack JSON; maps to BacktestConfig (Path A),
ARCH-4 harness params (Path B), and live config overlay hints (Path C).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from phase6.backtest.backtest_engine import BacktestConfig
from phase6.core.allocator import AllocatorConfig


@dataclass
class ScenarioKnobs:
    scenario_id: str
    initial_capital: float = 1000.0
    rebalance_frequency_days: int = 7
    rebalance_cap_usd: float = 200.0
    enable_pair_expansion: bool = False
    candidate_universe: List[str] = field(default_factory=list)
    engine: str = "simple"  # simple | arch4 (R1b)
    allocator_strategy: str = "rotation"  # rotation | rebalance

    @classmethod
    def from_scenario(cls, scenario: dict) -> "ScenarioKnobs":
        bt = scenario.get("backtest") or {}
        arch = scenario.get("arch4") or {}
        return cls(
            scenario_id=scenario["id"],
            initial_capital=float(bt.get("initial_capital", 1000)),
            rebalance_frequency_days=int(bt.get("rebalance_frequency_days", 7)),
            rebalance_cap_usd=float(bt.get("rebalance_cap_usd", 200)),
            enable_pair_expansion=bool(bt.get("enable_pair_expansion", False)),
            candidate_universe=list(bt.get("candidate_universe") or []),
            engine=str(scenario.get("engine") or arch.get("engine") or "simple"),
            allocator_strategy=str(arch.get("strategy") or "rotation"),
        )

    def to_backtest_config(self, start: date, end: date) -> BacktestConfig:
        return BacktestConfig(
            start_date=start,
            end_date=end,
            initial_capital=self.initial_capital,
            enable_pair_expansion=self.enable_pair_expansion,
            candidate_universe=list(self.candidate_universe),
            rebalance_frequency_days=self.rebalance_frequency_days,
            rebalance_cap_usd=self.rebalance_cap_usd,
        )

    def to_arch4_params(self) -> Dict[str, Any]:
        return {
            "initial_capital": self.initial_capital,
            "rebal_freq": self.rebalance_frequency_days,
            "use_rotation": self.allocator_strategy == "rotation",
            "min_move_usd": max(25.0, min(self.rebalance_cap_usd * 0.25, 150.0)),
        }

    def to_allocator_config(self) -> AllocatorConfig:
        p = self.to_arch4_params()
        return AllocatorConfig(
            min_move_usd=float(p["min_move_usd"]),
            rebalance_freq_days=max(1, self.rebalance_frequency_days),
        )

    def to_live_config_overlay(self) -> Dict[str, Any]:
        """Keys that would be patched in trading_config_phase6.json for shadow trials."""
        return {
            "global_settings.rebalance_cap_usd": self.rebalance_cap_usd,
            "global_settings.total_capital": self.initial_capital,
            "phase_6_specific.expansion_rules.max_pairs": (
                len(self.candidate_universe) + 5 if self.enable_pair_expansion else 5
            ),
            "_scenario_meta.rebalance_frequency_days": self.rebalance_frequency_days,
            "_scenario_meta.note": "Live uses scheduler.daily_rebalance_times; stride is not 1:1 — see gap matrix.",
        }

    def gap_flags(self) -> List[str]:
        flags: List[str] = []
        if self.engine == "simple":
            flags.append("PATH_A_STUB_SENTIMENT_RSI")
        if self.enable_pair_expansion:
            flags.append("EXPANSION_LOGIC_DIVERGES_A_vs_B_vs_C")
        flags.append("REBALANCE_CLOCK_vs_DAY_STRIDE")
        if self.rebalance_cap_usd != self.to_arch4_params()["min_move_usd"]:
            flags.append("REBALANCE_CAP_vs_MIN_MOVE_PARTIAL_MAP")
        return flags


def parity_report(pack: dict) -> Dict[str, Any]:
    """Build per-scenario parity metadata for isolation test / analyst brief."""
    from datetime import datetime

    rows = []
    for sc in pack.get("scenarios", []):
        knobs = ScenarioKnobs.from_scenario(sc)
        rows.append(
            {
                "scenario_id": knobs.scenario_id,
                "engine": knobs.engine,
                "arch4_params": knobs.to_arch4_params(),
                "live_overlay_keys": list(knobs.to_live_config_overlay().keys()),
                "gap_flags": knobs.gap_flags(),
            }
        )
    return {
        "pack_id": pack.get("pack_id"),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scenarios": rows,
    }