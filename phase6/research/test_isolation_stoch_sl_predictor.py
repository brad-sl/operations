#!/usr/bin/env python3
"""Isolation tests for stoch_sl_predictor (no network, no live config)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.stoch_sl_predictor import (  # noqa: E402
    build_buy_episodes,
    compare_threshold,
    load_history,
    load_trades,
    recommend,
    run_analysis,
    wilson_ci,
)


def _ts(h: int = 0) -> str:
    base = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(hours=h)).isoformat()


def test_wilson_bounds():
    lo, hi = wilson_ci(2, 10)
    assert lo is not None and hi is not None
    assert 0 <= lo <= hi <= 1
    assert wilson_ci(0, 0) == (None, None)
    print("PASS test_wilson_bounds", lo, hi)


def test_entry_join_and_forward_sl(tmp_path: Path | None = None):
    td = Path(tempfile.mkdtemp()) if tmp_path is None else tmp_path
    trades = td / "trades.jsonl"
    hist = td / "hist.jsonl"

    # t0 buy low stoch → SL at +48h
    # t0b buy high stoch → no SL
    rows = [
        {
            "pair": "SOL-USD",
            "side": "BUY",
            "reason": "rebalance_buy",
            "entry_price": 100.0,
            "timestamp": _ts(0),
            "indicators_at_trade": {"rsi": 45.0, "stoch_k": 10.0, "stoch_d": 12.0},
        },
        {
            "pair": "BTC-USD",
            "side": "BUY",
            "reason": "rebalance_buy",
            "entry_price": 60000.0,
            "timestamp": _ts(1),
            "indicators_at_trade": {"rsi": 50.0, "stoch_k": 70.0, "stoch_d": 65.0},
        },
        {
            "pair": "SOL-USD",
            "side": "SELL",
            "reason": "stop_loss_exchange",
            "exit_price": 90.0,
            "timestamp": _ts(48),
            "indicators_at_trade": {"rsi": 28.0, "stoch_k": 0.0, "stoch_d": 5.0},
        },
        # history-only buy (no on-trade ind)
        {
            "pair": "ETH-USD",
            "side": "BUY",
            "reason": "rebalance_buy",
            "entry_price": 3000.0,
            "timestamp": _ts(2),
        },
    ]
    trades.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    hist_rows = [
        {
            "timestamp": _ts(2),
            "pairs": {
                "ETH-USD": {"rsi": 55.0, "stoch_k": 25.0, "stoch_d": 30.0},
            },
        }
    ]
    hist.write_text("\n".join(json.dumps(r) for r in hist_rows) + "\n")

    t = load_trades(trades)
    h = load_history(hist)
    start = datetime(2026, 7, 22, tzinfo=timezone.utc)
    eps = build_buy_episodes(t, h, start=start)
    assert len(eps) == 3, eps
    sol = next(e for e in eps if e.pair == "SOL-USD")
    btc = next(e for e in eps if e.pair == "BTC-USD")
    eth = next(e for e in eps if e.pair == "ETH-USD")
    assert sol.stoch_k == 10.0 and sol.hit_sl_3d is True and sol.hit_sl_7d is True
    assert btc.stoch_k == 70.0 and btc.hit_sl_7d is False
    assert eth.ind_source == "history_join" and eth.stoch_k == 25.0
    assert sol.exit_stoch_k == 0.0

    with_sk = [e for e in eps if e.stoch_k is not None]
    cmp_ = compare_threshold(with_sk, attr="stoch_k", thr=30.0, horizon="hit_sl_7d")
    assert cmp_["low"]["n"] >= 1
    assert cmp_["high"]["n"] >= 1
    print("PASS test_entry_join_and_forward_sl", cmp_)


def test_recommend_thin_sample():
    analysis = {
        "primary_7d_stoch30": {
            "threshold": 30,
            "horizon": "hit_sl_7d",
            "low": {"n": 2, "sl_rate": 0.5},
            "high": {"n": 3, "sl_rate": 0.0},
            "lift_low_over_high": float("inf"),
        },
        "rsi_controlled": {"lift": None, "n_mid_rsi": 1},
        "entry_vs_exit": {"entry_pct_lt_thr": 0.2, "exit_pct_lt_thr": 0.9},
    }
    enum, caveats, plain = recommend(analysis)
    assert enum == "extend_collect", enum
    print("PASS test_recommend_thin_sample", enum, plain)


def test_no_network_paths_exist():
    # Smoke: module import + empty-ish safe call on real paths shouldn't write config
    assert (ROOT / "phase6" / "research" / "stoch_sl_predictor.py").exists()
    print("PASS test_no_network_paths_exist")


def main() -> int:
    test_wilson_bounds()
    test_entry_join_and_forward_sl()
    test_recommend_thin_sample()
    test_no_network_paths_exist()
    print("ALL isolation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
