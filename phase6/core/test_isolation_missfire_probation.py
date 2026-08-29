"""Isolation: miss-fire probation (launch → no explode → dig hole)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.missfire_probation import (  # noqa: E402
    annotate_swap,
    compute_pair_stats,
    evaluate_pair_missfire,
    probation_block_pairs,
)
from phase6.core.membership_potential_gate import evaluate_membership_swap  # noqa: E402


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _row(ts: datetime, pair: str, side: str, pnl: float, reason: str) -> dict:
    return {
        "timestamp": _iso(ts),
        "pair": pair,
        "side": side,
        "pnl": pnl,
        "reason": reason,
        "exit_reason": reason,
    }


def test_fast_hole_and_dig_hole() -> None:
    now = datetime.now(timezone.utc)
    t0 = now - timedelta(days=10)
    rows = []
    # RAVE-like: 2 fast SL, 1 slow, no TP, net red
    for i, hold_h in enumerate([0.1, 0.5, 12.0]):
        b = t0 + timedelta(days=i)
        s = b + timedelta(hours=hold_h)
        rows.append(_row(b, "RAVE-USD", "BUY", 0.0, "rebalance_buy"))
        rows.append(_row(s, "RAVE-USD", "SELL", -5.0, "stop_loss_exchange"))
    # AVAX-like dig hole: 3 slow SL, 0 TP
    for i in range(3):
        b = t0 + timedelta(days=i + 1)
        s = b + timedelta(hours=48)
        rows.append(_row(b, "AVAX-USD", "BUY", 0.0, "rebalance_buy"))
        rows.append(_row(s, "AVAX-USD", "SELL", -2.0, "stop_loss_exchange"))
    # Clean winner: TP path
    b = t0
    s = b + timedelta(hours=24)
    rows.append(_row(b, "ETH-USD", "BUY", 0.0, "rebalance_buy"))
    rows.append(_row(s, "ETH-USD", "SELL", 10.0, "take_profit_fixed_tp"))
    # Unknown new pair — no history
    smap = compute_pair_stats(rows, lookback_days=45.0, now=now)

    rave = evaluate_pair_missfire("RAVE-USD", stats_map=smap, enforce=True)
    assert rave.blocked, rave
    assert rave.class_ in ("fast_hole", "dig_hole"), rave

    avax = evaluate_pair_missfire("AVAX-USD", stats_map=smap, enforce=True)
    assert avax.blocked and avax.class_ == "dig_hole", avax

    eth = evaluate_pair_missfire("ETH-USD", stats_map=smap, enforce=True)
    assert not eth.blocked and eth.class_ == "sticky_exempt", eth

    new = evaluate_pair_missfire("ZRO-USD", stats_map=smap, enforce=True)
    assert not new.blocked, new

    blocked = probation_block_pairs(stats_map=smap, enforce=True)
    assert "RAVE-USD" in blocked and "AVAX-USD" in blocked
    assert "ETH-USD" not in blocked

    sw = annotate_swap({"add": "RAVE-USD", "remove": "ADA-USD", "reason": "test"}, stats_map=smap)
    assert sw.get("missfire_blocked") is True
    assert sw.get("missfire_probation_ok") is False


def test_membership_m4_blocks_rave_on_live_ledger() -> None:
    """Live ledger: RAVE should fail M4 if still miss-fire class."""
    from phase6.core.missfire_probation import evaluate_pair_missfire

    v = evaluate_pair_missfire("RAVE-USD", enforce=True)
    if not v.blocked:
        print("NOTE: live RAVE not blocked (ledger may have aged out) — skip M4 live assert")
        return
    # Build a swap that would otherwise pass M0–M3 with skip floors
    verdict = evaluate_membership_swap(
        add="RAVE-USD",
        remove="DOGE-USD",
        active=["BTC-USD", "ETH-USD", "DOGE-USD"],
        inbound_potential=0.8,
        outbound_potential=0.2,
        precomputed_delta=0.6,
        quote_vol_24h=5_000_000,
        ret_24h=0.02,
        mom_3d=0.03,
        mom_7d=0.05,
        discovery_upside_ok=True,
        held_usd_remove=0.0,
        skip_inbound_score_floor=True,
    )
    assert verdict.ok is False
    assert verdict.layer_failed == "M4"
    assert any(str(r).startswith("M4:") for r in verdict.reasons)


def test_buy_entry_blocks_missfire() -> None:
    from phase6.core.missfire_probation import evaluate_pair_missfire
    from phase6.core.regime_cash_policy import RegimeCashSnapshot, evaluate_buy_entry

    # Prefer a pair blocked by miss-fire but NOT on recovery buy_block (UNI/RAVE).
    candidate = None
    for p in ("OP-USD", "ADA-USD", "RAVE-USD"):
        v = evaluate_pair_missfire(p, enforce=True)
        if v.blocked:
            candidate = p
            break
    if not candidate:
        print("NOTE: no live miss-fire pair — skip buy-entry live assert")
        return
    snap = RegimeCashSnapshot(
        regime="bull",
        confidence=0.5,
        btc_return_pct=5.0,
        strategy_mode="deploy",
        allow_new_buys=True,
        target_max_util_pct=0.6,
        rebalance_cap_usd=100.0,
        min_cash_reserve_pct=0.2,
        entry={"min_sentiment": -1.0, "max_rsi": 100.0, "require_lockout_clear": False},
        exit={},
        label="test",
        detector={},
    )
    # Empty deny lists so missfire is the deciding reason (when candidate not UNI/RAVE)
    pol = {
        "enabled": True,
        "enforce": True,
        "buy_block_pairs": [],
        "pair_buy_blocklist": [],
        "operator_override": {},
    }
    d = evaluate_buy_entry(
        candidate,
        snap,
        sentiment=0.9,
        rsi=40.0,
        is_new_pair=True,
        policy=pol,
    )
    assert d.allowed is False, d
    # RAVE may still hit config blocks if collect reads trading_config; accept either gate
    joined = " ".join(d.reasons)
    assert ("missfire" in joined) or ("buy_block" in joined), d.reasons


def main() -> int:
    test_fast_hole_and_dig_hole()
    test_membership_m4_blocks_rave_on_live_ledger()
    test_buy_entry_blocks_missfire()
    print("missfire_probation isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
