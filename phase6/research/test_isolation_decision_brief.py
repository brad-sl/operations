"""Isolation: decision_brief is plain-English go/no-go, not ops dump."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.decision_brief import format_decision_brief


def main() -> int:
    body = format_decision_brief(
        basket=["BTC-USD", "ETH-USD", "LINK-USD"],
        full_count=3,
        last_rebalance="2026-08-25",
        poly={"risk_on_bias": 0.5, "num_markets": 10},
        sl_risks={
            "BTC-USD": {"level": "HIGH"},
            "ETH-USD": {"level": "LOW"},
            "LINK-USD": {"level": "HIGH"},
        },
        signals=[
            {"pair": "LINK-USD", "signal": "BUY", "reason": "Positive sentiment", "sl_level": "HIGH"},
            {"pair": "BTC-USD", "signal": "HOLD", "reason": "No strong signal", "sl_level": "HIGH"},
        ],
        opt_brief={
            "production_since_go_live_return_pct": 12.5,
            "production_end_equity_usd": 2500.0,
            "production_trade_count": 100,
            "production_live_rebalances": 20,
            "production_deposit_adjusted": True,
            "deployment_hint": "hold — no scenario beat production on overlap with real data",
            "regime_cash": {
                "regime": "bull",
                "strategy_mode": "deploy",
                "allow_new_buys": True,
                "target_max_util_pct": 0.85,
            },
            "trend_repair": {
                "health": "soft_downtrend",
                "window_return_pct": -4.0,
                "recent_return_pct": -1.5,
                "primary_layer": "edge_or_entries",
                "recommendations": [{"tier": 0, "action": "preserve_gate_integrity"}],
            },
        },
        same_session={"count_2h": 4, "pairs_2h": ["LINK-USD", "UNI-USD"]},
        same_session_3d={"count_2h": 0, "pairs_2h": []},
        proposals=[],
        next_focus="Run regime scorecard; keep shadow+drift before any live config promotion.",
        phase2_check={
            "schema": "phase2_stabilize_check_v1",
            "tiles": {"d7": -6.5, "d14": -4.7, "d30": -5.5, "slope": -0.1, "health": "soft_down"},
            "bars": {
                "14D >= -2%": False,
                "slope >= -0.03/d": False,
                ">=1 clean TP/rotation green in last 7d": True,
                "no UNI/RAVE reopen since Phase1": True,
                "code wire PASS": True,
            },
            "phase2_ready": False,
            "verdict": "NO-GO phase2 exit bar not met",
        },
    )
    assert "BOTTOM LINE:" in body
    assert "=== Do now ===" in body
    assert "=== Book ===" in body
    assert "=== Stance" in body
    assert "=== Phase 2 stabilize ===" in body
    assert "=== What's next ===" in body
    # No raw ops dump markers
    for banned in (
        "Signals:",
        "REGIME-CASH:",
        "TREND-REPAIR:",
        "Same-session SL",
        "risk_on_bias",
        "FULL |",
    ):
        assert banned not in body, f"banned ops jargon leaked: {banned}"
    assert "Equity $" in body
    assert "LINK" in body  # selective buy surfaced
    assert "HOLD" in body or "SELECTIVE" in body
    print("decision_brief isolation PASS")
    print("--- sample ---")
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
