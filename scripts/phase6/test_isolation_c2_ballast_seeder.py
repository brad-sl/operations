#!/usr/bin/env python3
"""Isolation: C2 ballast seeder + shell freeze (no exchange)."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.c2_ballast_seeder import (  # noqa: E402
    filter_trade_plan_shell_freeze,
    propose_seed_actions,
    seed_trade_plan,
)


@dataclass
class FakePlan:
    actions: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""


def test_propose_btc_under_target():
    r = propose_seed_actions(
        current_allocs={"BTC-USD": 50.0, "PAXG-USD": 75.0},
        cash_usd=2000.0,
        runner=None,
        cfg={
            "live_apply": True,
            "shadow_only": False,
            "require_c2_live": False,  # isolation without depending on live C2 file
            "pairs_prefer": ["BTC-USD", "ETH-USD"],
            "role": "ballast_core",
            "default_target_w": 0.18,
            "default_flat_cap_usd": 75.0,
            "max_actions_per_plan": 1,
            "tag_reason": "c2_ballast_floor",
        },
    )
    assert r["actions"], f"expected seed action, got {r}"
    assert r["actions"][0]["pair"] == "BTC-USD"
    assert r["actions"][0]["usd"] >= 25.0
    assert r["actions"][0]["reason"] == "c2_ballast_floor"
    print("PASS propose_btc_under_target", r["actions"][0])


def test_seed_injects_when_live():
    plan = FakePlan(actions=[])
    cfg = {
        "live_apply": True,
        "shadow_only": False,
        "require_c2_live": False,
        "pairs_prefer": ["BTC-USD", "ETH-USD"],
        "role": "ballast_core",
        "default_target_w": 0.18,
        "default_flat_cap_usd": 75.0,
        "max_actions_per_plan": 1,
        "tag_reason": "c2_ballast_floor",
    }
    seed_trade_plan(
        plan,
        current_allocs={"BTC-USD": 40.0},
        cash_usd=2000.0,
        cfg=cfg,
    )
    assert any(a.get("pair") == "BTC-USD" and a.get("action") == "BUY" for a in plan.actions)
    print("PASS seed_injects_when_live", plan.actions)


def test_seed_shadow_no_inject():
    plan = FakePlan(actions=[])
    cfg = {
        "live_apply": False,
        "shadow_only": True,
        "require_c2_live": False,
        "pairs_prefer": ["BTC-USD"],
        "role": "ballast_core",
        "default_target_w": 0.18,
        "default_flat_cap_usd": 75.0,
        "max_actions_per_plan": 1,
    }
    seed_trade_plan(plan, current_allocs={"BTC-USD": 40.0}, cash_usd=2000.0, cfg=cfg)
    assert plan.actions == []
    print("PASS seed_shadow_no_inject")


def test_no_double_when_ballast_buy_present():
    plan = FakePlan(actions=[{"pair": "BTC-USD", "action": "BUY", "usd": 75.0, "reason": "signal"}])
    cfg = {
        "live_apply": True,
        "require_c2_live": False,
        "pairs_prefer": ["BTC-USD", "ETH-USD"],
        "role": "ballast_core",
        "default_target_w": 0.18,
        "default_flat_cap_usd": 75.0,
        "max_actions_per_plan": 1,
        "tag_reason": "c2_ballast_floor",
    }
    seed_trade_plan(plan, current_allocs={"BTC-USD": 40.0}, cash_usd=2000.0, cfg=cfg)
    buys = [a for a in plan.actions if a.get("action") == "BUY"]
    assert len(buys) == 1
    assert buys[0].get("reason") == "c2_ballast_floor"
    assert buys[0].get("c2_ballast_floor") is True
    print("PASS no_double_when_ballast_buy_present", buys[0])


def test_shell_freeze_drops_link():
    plan = FakePlan(
        actions=[
            {"pair": "LINK-USD", "action": "BUY", "usd": 25.0},
            {"pair": "BTC-USD", "action": "BUY", "usd": 75.0, "reason": "c2_ballast_floor"},
            {"pair": "SOL-USD", "action": "SELL", "usd": 10.0},
        ]
    )
    cfg = {
        "shell_freeze_live": True,
        "shell_freeze_allow_pairs": ["BTC-USD", "ETH-USD", "PAXG-USD"],
    }
    filter_trade_plan_shell_freeze(plan, cfg=cfg)
    pairs = [a.get("pair") for a in plan.actions]
    assert "LINK-USD" not in pairs
    assert "BTC-USD" in pairs
    assert "SOL-USD" in pairs  # sells kept
    print("PASS shell_freeze_drops_link", plan.actions)


def main() -> int:
    test_propose_btc_under_target()
    test_seed_injects_when_live()
    test_seed_shadow_no_inject()
    test_no_double_when_ballast_buy_present()
    test_shell_freeze_drops_link()
    print("ALL PASS test_isolation_c2_ballast_seeder")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
