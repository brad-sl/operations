#!/usr/bin/env python3
"""NEEDLE Stage 0 isolation: util truth, post-TP washout release, db dual-write."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def test_crypto_util_excludes_usdc_and_paxg():
    from phase6.core import park_ballast_shadow as pbs

    live = {
        "total_usd": 2287.02,
        "cash_usd": 200.0,
        "balances": [
            {"currency": "USD", "balance": 200.0},
            {"currency": "USDC", "balance": 2008.49},
        ],
        "positions": [
            {
                "pair": "PAXG-USD",
                "value_usd": 78.53,
                "sleeve": "preserve",
            }
        ],
    }
    with patch.object(pbs, "_load_json", return_value=live):
        util = pbs.crypto_util_pct_from_live()
    assert util is not None
    assert abs(util - 0.0) < 1e-9, util


def test_crypto_util_counts_only_basket_crypto():
    from phase6.core import park_ballast_shadow as pbs

    live = {
        "total_usd": 1000.0,
        "cash_usd": 100.0,
        "positions": [
            {"pair": "BTC-USD", "value_usd": 400.0},
            {"pair": "PAXG-USD", "value_usd": 50.0},
            {"pair": "USDC-USD", "value_usd": 450.0},
        ],
    }
    with patch.object(pbs, "_load_json", return_value=live):
        util = pbs.crypto_util_pct_from_live()
    assert abs(util - 0.40) < 1e-9, util


def test_post_tp_washout_releases_and_keeps_sl():
    from phase6.core import runner_capital_events as rce

    now = datetime.now(timezone.utc).timestamp()
    blocks = {
        "LINK-USD": {
            "blocked": True,
            "reason": "post_tp_rebuy_block",
            "block_hours": 24.0,
            "hours_remaining": 10.0,  # elapsed 14h
        },
        "ETH-USD": {
            "blocked": True,
            "reason": "post_sl_rebuy_block",
            "block_hours": 72.0,
            "hours_remaining": 60.0,
        },
        "SOL-USD": {
            "blocked": True,
            "reason": "post_tp_rebuy_block",
            "block_hours": 24.0,
            "hours_remaining": 23.0,  # elapsed 1h < 2h floor
        },
    }
    rsi = {"LINK-USD": 37.05, "ETH-USD": 32.0, "SOL-USD": 34.0}
    with patch.object(
        rce,
        "_post_tp_washout_cfg",
        return_value={"enabled": True, "min_hours_floor": 2.0, "rsi_wash_max": 40.0},
    ):
        out = rce._apply_post_tp_washout_early_release(blocks, now=now, rsi_map=rsi)
    assert "LINK-USD" not in out, out
    assert "ETH-USD" in out, "SL block must remain"
    assert "SOL-USD" in out, "too-fresh TP block must remain"


def test_post_tp_washout_skips_high_rsi():
    from phase6.core import runner_capital_events as rce

    now = datetime.now(timezone.utc).timestamp()
    blocks = {
        "BTC-USD": {
            "blocked": True,
            "reason": "post_tp_rebuy_block",
            "block_hours": 24.0,
            "hours_remaining": 5.0,
        }
    }
    with patch.object(
        rce,
        "_post_tp_washout_cfg",
        return_value={"enabled": True, "min_hours_floor": 2.0, "rsi_wash_max": 40.0},
    ):
        out = rce._apply_post_tp_washout_early_release(
            blocks, now=now, rsi_map={"BTC-USD": 55.0}
        )
    assert "BTC-USD" in out


def test_dual_write_dedupes_order_id():
    from phase6.core.trade_ledger import TradeLedger

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "data").mkdir()
        (root / "trades").mkdir()
        db = root / "data" / "phase6.db"
        con = sqlite3.connect(str(db))
        con.execute(
            """CREATE TABLE trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, pair TEXT, side TEXT, amount REAL, price REAL,
                pnl REAL, status TEXT, exit_price REAL, pnl_pct REAL, source TEXT
            )"""
        )
        con.commit()
        con.close()
        ledger = TradeLedger(base_dir=root)
        t = {
            "timestamp": "2026-09-30T04:00:00Z",
            "pair": "LINK-USD",
            "side": "BUY",
            "qty": 1.76,
            "entry_price": 14.16,
            "order_id": "abc-123-unique",
            "mode": "live",
            "pnl": 0,
            "pnl_pct": 0,
            "signal_source": "test",
        }
        ledger._dual_write_phase6_db(t)
        ledger._dual_write_phase6_db(t)
        con = sqlite3.connect(str(db))
        n = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        con.close()
        assert n == 1, n


if __name__ == "__main__":
    test_crypto_util_excludes_usdc_and_paxg()
    test_crypto_util_counts_only_basket_crypto()
    test_post_tp_washout_releases_and_keeps_sl()
    test_post_tp_washout_skips_high_rsi()
    test_dual_write_dedupes_order_id()
    print("test_isolation_needle_stage02: OK")
