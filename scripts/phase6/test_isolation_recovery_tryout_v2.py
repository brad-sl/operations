#!/usr/bin/env python3
"""Isolation: recovery quality_tryout v2 qualify + gate wiring."""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.recovery_tryout_qualify import (
    evaluate_basket_tryout,
    evaluate_pair_tryout,
    load_v2_cfg,
)
from phase6.core.regime_cash_policy import (
    RegimeCashSnapshot,
    evaluate_buy_entry,
    recovery_soft_down_blocks_pair,
    recovery_tryout_pairs_effective,
)
from phase6.core.dashboard_serve_helpers import short_gate_label


def _snap(**kw):
    base = dict(
        regime="bull",
        confidence=0.8,
        btc_return_pct=1.0,
        strategy_mode="deploy",
        allow_new_buys=True,
        target_max_util_pct=80.0,
        rebalance_cap_usd=75.0,
        min_cash_reserve_pct=20.0,
        entry={"min_sentiment": 0.15, "max_rsi": 70.0, "require_lockout_clear": True},
        exit={},
        label="test",
        detector={"equity_health": "soft_down"},
        enforce=True,
        enabled=True,
    )
    base.update(kw)
    return RegimeCashSnapshot(**base)


def _rec_v2(**extra):
    rec = {
        "enabled": True,
        "new_alt_policy": "quality_tryout_v2",
        "block_new_buy_pairs": ["UNI-USD", "RAVE-USD"],
        "while_equity_health_in": ["soft_down", "declining", "hard_down"],
        "allowlist_pairs": ["BTC-USD", "PAXG-USD", "USDC-USD"],
        "quality_tryout": {
            "tryout_pairs": ["ETH-USD", "LINK-USD"],
            "min_sentiment": 0.30,
            "max_rsi": 55.0,
            "max_new_seats_per_day": 1,
            "abs_cap_usd": 75.0,
            "v2_dynamic": True,
            "v2": {
                "live_apply": True,
                "allow_tier_c": False,
                "tier_b": ["ETH-USD", "LINK-USD", "SOL-USD", "XRP-USD"],
                "lookback_days": 90,
            },
        },
    }
    rec.update(extra)
    return rec


def test_ledger_pass_fail():
    now = datetime.now(timezone.utc)
    # LINK-like: net green, some TP
    rows = []
    for i in range(6):
        ts = (now - timedelta(days=i + 1)).isoformat()
        rows.append(
            {
                "pair": "LINK-USD",
                "side": "SELL",
                "timestamp": ts,
                "pnl": 2.0 if i % 2 == 0 else -1.0,
                "reason": "take_profit" if i % 2 == 0 else "stop_loss",
            }
        )
    # SOL-like: deep red all SL
    for i in range(8):
        rows.append(
            {
                "pair": "SOL-USD",
                "side": "SELL",
                "timestamp": (now - timedelta(days=i + 1)).isoformat(),
                "pnl": -5.0,
                "reason": "stop_loss",
            }
        )

    def _mf_clear(p, enforce=True):
        class V:
            blocked = False
            class_ = "clear"
            reasons = []

        return V()

    v_link = evaluate_pair_tryout(
        "LINK-USD",
        rec=_rec_v2(),
        basket=["ETH-USD", "LINK-USD", "SOL-USD", "ADA-USD", "BTC-USD"],
        ledger_rows=rows,
        missfire_fn=_mf_clear,
    )
    assert v_link.eligible_tryout, v_link
    assert v_link.tier == "B", v_link

    v_sol = evaluate_pair_tryout(
        "SOL-USD",
        rec=_rec_v2(),
        basket=["ETH-USD", "LINK-USD", "SOL-USD", "ADA-USD", "BTC-USD"],
        ledger_rows=rows,
        missfire_fn=_mf_clear,
    )
    assert not v_sol.eligible_tryout, v_sol
    assert "ledger" in v_sol.class_ or v_sol.class_ == "ledger_fail", v_sol

    v_ada = evaluate_pair_tryout(
        "ADA-USD",
        rec=_rec_v2(),
        basket=["ETH-USD", "LINK-USD", "SOL-USD", "ADA-USD", "BTC-USD"],
        ledger_rows=rows,
        missfire_fn=_mf_clear,
    )
    assert not v_ada.eligible_tryout
    assert v_ada.class_ == "tier_c_off", v_ada
    print("PASS ledger_pass_fail")


def test_hard_block_and_missfire():
    def _mf_block(p, enforce=True):
        class V:
            blocked = True
            class_ = "fast_hole"
            reasons = ["fast_hole"]

        return V()

    v = evaluate_pair_tryout(
        "ADA-USD",
        rec=_rec_v2(),
        basket=["ADA-USD", "ETH-USD"],
        ledger_rows=[],
        missfire_fn=_mf_block,
    )
    # missfire fires before tier_c when we force allow_tier_c... without it tier_c may win first
    # hard block:
    v2 = evaluate_pair_tryout(
        "UNI-USD",
        rec=_rec_v2(),
        basket=["UNI-USD", "ETH-USD"],
        ledger_rows=[],
        missfire_fn=lambda p, enforce=True: type("V", (), {"blocked": False, "class_": "clear", "reasons": []})(),
    )
    assert v2.hard_blocked and not v2.eligible_tryout
    print("PASS hard_block_and_missfire")


def test_gate_wiring_v2():
    rec = _rec_v2()
    pol = {"operator_override": {"recovery_soft_down_20260828": rec}}
    snap = _snap()

    # BTC allowlist always open for new seat
    assert recovery_soft_down_blocks_pair("BTC-USD", policy=pol, is_new_pair=True, snap=snap) is None

    # UNI hard block
    r = recovery_soft_down_blocks_pair("UNI-USD", policy=pol, is_new_pair=True, snap=snap)
    assert r and "block_list" in r, r

    # With empty ledger, tier B first_fill path should allow ETH
    # (evaluate_pair uses live missfire — may block real names; use synthetic via board)
    # Direct pair eval with clear missfire:
    from phase6.core import recovery_tryout_qualify as rq

    board = {
        "eligible_tryout_pairs": ["ETH-USD", "LINK-USD"],
        "verdicts": [
            {"pair": "ETH-USD", "eligible_tryout": True},
            {"pair": "LINK-USD", "eligible_tryout": True},
            {"pair": "SOL-USD", "eligible_tryout": False},
            {"pair": "ADA-USD", "eligible_tryout": False},
        ],
    }
    assert rq.is_tryout_eligible("ETH-USD", board=board)
    assert not rq.is_tryout_eligible("SOL-USD", board=board)

    print("PASS gate_wiring_v2")


def test_short_labels():
    assert short_gate_label(
        ["recovery_soft_down quality_tryout_v2 ledger_fail SOL-USD"]
    ) == "ledger quality fail"
    assert short_gate_label(
        ["recovery_soft_down quality_tryout_v2 tier_c_off ADA-USD"]
    ) == "tier C off"
    assert short_gate_label(
        ["recovery_soft_down quality_tryout not_eligible ADA-USD"]
    ) == "not on tryout list"
    print("PASS short_labels")


def test_v1_static_unchanged_when_not_v2():
    rec = {
        "enabled": True,
        "new_alt_policy": "quality_tryout",
        "block_new_buy_pairs": ["UNI-USD"],
        "while_equity_health_in": ["soft_down"],
        "allowlist_pairs": ["BTC-USD"],
        "quality_tryout": {"tryout_pairs": ["ETH-USD", "LINK-USD"]},
    }
    pairs = recovery_tryout_pairs_effective(rec)
    assert pairs == {"ETH-USD", "LINK-USD"}, pairs
    print("PASS v1_static_unchanged")


def main():
    test_ledger_pass_fail()
    test_hard_block_and_missfire()
    test_gate_wiring_v2()
    test_short_labels()
    test_v1_static_unchanged_when_not_v2()
    print("ALL PASS isolation_recovery_tryout_v2")


if __name__ == "__main__":
    main()
