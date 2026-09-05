#!/usr/bin/env python3
"""Isolation tests for trade_comparison_standard (real ledger + fixtures)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.trade_comparison_standard import (  # noqa: E402
    compare_pairs,
    exit_class,
    is_clean_buy,
    load_ledger_rows,
    paper_rule_candidates,
    sensor_preflight_ledger,
    summarize_pair,
    would_block_buy,
)


def _ts(h_offset: float = 0.0) -> str:
    base = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(hours=h_offset)).isoformat().replace("+00:00", "Z")


def test_noise_buy_filter() -> None:
    assert is_clean_buy({"side": "BUY", "reason": "phase6_fresh_start", "entry_price": 0, "qty": 1}) is False
    assert is_clean_buy({"side": "BUY", "reason": "rebalance_buy", "entry_price": 10, "qty": 1, "order_id": "x"}) is True
    assert is_clean_buy({"side": "SELL", "reason": "x"}) is False
    print("PASS noise_buy_filter")


def test_exit_class() -> None:
    assert exit_class("stop_loss_exchange") == "stop_loss"
    assert exit_class("take_profit_fixed_tp") == "take_profit"
    assert exit_class("dust_sweep_after_sl") == "dust"
    assert exit_class("operator_trim_link_30pct_to_cash") == "operator"
    print("PASS exit_class")


def test_fixture_leaks_and_rules() -> None:
    rows = [
        {
            "pair": "AAA-USD",
            "side": "BUY",
            "timestamp": _ts(0),
            "qty": 10,
            "entry_price": 10.0,
            "reason": "rebalance_buy",
            "order_id": "b1",
            "indicators_at_trade": {"rsi": 40},
        },
        {
            "pair": "AAA-USD",
            "side": "SELL",
            "timestamp": _ts(24),
            "qty": 10,
            "entry_price": 10.0,
            "exit_price": 9.7,
            "pnl": -3.0,
            "pnl_pct": -0.03,
            "exit_reason": "stop_loss_exchange",
            "order_id": "s1",
        },
        # reentry 12h after SL — leak
        {
            "pair": "AAA-USD",
            "side": "BUY",
            "timestamp": _ts(36),
            "qty": 20,
            "entry_price": 10.0,
            "reason": "rebalance_buy",
            "order_id": "b2",
            "indicators_at_trade": {"rsi": 52},
        },
        {
            "pair": "AAA-USD",
            "side": "SELL",
            "timestamp": _ts(60),
            "qty": 20,
            "entry_price": 10.0,
            "exit_price": 10.6,
            "pnl": 12.0,
            "pnl_pct": 0.06,
            "exit_reason": "take_profit_fixed_tp",
            "order_id": "s2",
        },
        # post-TP large rebuy 10h later
        {
            "pair": "AAA-USD",
            "side": "BUY",
            "timestamp": _ts(70),
            "qty": 100,
            "entry_price": 10.0,
            "reason": "rebalance_buy",
            "order_id": "b3",
            "indicators_at_trade": {"rsi": 58},
        },
    ]
    sb = summarize_pair("AAA-USD", rows, sl_cooldown_h=48, tp_cooldown_h=48, large_usd=150, elevated_rsi=55)
    assert sb.n_clean_buys == 3
    assert sb.n_sells == 2
    assert abs(sb.realized_pnl_usd - 9.0) < 1e-9
    assert sb.leak_hits.get("post_sl_reentry_Nh", 0) >= 1
    assert sb.leak_hits.get("post_tp_rebuy_Nh", 0) >= 1
    assert sb.leak_hits.get("elevated_rsi_large_ticket", 0) >= 1
    rules = paper_rule_candidates(sb)
    ids = {r["id"] for r in rules}
    assert "cooldown_after_sl" in ids
    assert "cooldown_after_tp" in ids
    # would-block
    buy_ts = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(hours=70)
    wb = would_block_buy(pair="AAA-USD", buy_ts=buy_ts, usd=1000, rsi=58, recent_sells=[
        {
            "ts": datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(hours=60),
            "reason": "take_profit_fixed_tp",
        }
    ])
    assert wb["block"] is True
    assert wb["live"] is False
    print("PASS fixture_leaks_and_rules", sb.leak_hits, "realized", sb.realized_pnl_usd)


def test_sensor_and_live_ledger_link() -> None:
    rows = load_ledger_rows(pair="LINK-USD")
    pre = sensor_preflight_ledger(rows)
    assert pre.get("outcome_class") in (
        "sensor_ok",
        "sensor_thin",
        "sensor_degenerate",
        "sensor_broken",
    )
    if pre.get("ok"):
        sb = summarize_pair("LINK-USD", rows)
        assert sb.n_sells >= 1
        assert "realized_pnl_usd" in sb.to_dict()
        print(
            "PASS live_ledger_link",
            "sells",
            sb.n_sells,
            "pnl",
            sb.realized_pnl_usd,
            "leaks",
            sb.leak_hits,
        )
    else:
        print("PASS sensor_non_ok_labeled", pre)
    # multipair compare should not crash on real ledger
    cmp = compare_pairs(["LINK-USD", "BTC-USD", "ETH-USD"])
    assert cmp.get("schema") == "trade_comparison_standard_v1"
    assert cmp.get("n_pairs") == 3
    print("PASS multipair_compare", cmp.get("realized_pnl_sum"), cmp.get("leak_totals"))


def main() -> int:
    test_noise_buy_filter()
    test_exit_class()
    test_fixture_leaks_and_rules()
    test_sensor_and_live_ledger_link()
    print("ALL PASS test_isolation_trade_comparison_standard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
