#!/usr/bin/env python3
"""Isolation: pair_lifecycle_by_class measure board."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.pair_lifecycle_by_class import (
    aggregate_group,
    build_lifecycle_rts,
    build_pair_lifecycle_by_class,
    pair_class,
)


def test_pair_class_defaults() -> None:
    assert pair_class("BTC-USD") == "mega"
    assert pair_class("LINK-USD") == "large"
    assert pair_class("SUI-USD") == "mid"
    assert pair_class("HYPE-USD") == "high_beta"
    assert pair_class("PAXG-USD") == "ballast"
    assert pair_class("USDT-USDC") == "stable"
    assert pair_class("ZZZ-USD") == "other"


def test_build_rts_and_aggregate() -> None:
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    buys = [
        {
            "side": "BUY",
            "pair": "LINK-USD",
            "timestamp": (now - timedelta(hours=20)).isoformat(),
            "entry_price": 10.0,
            "qty": 2.0,
            "order_id": "b1",
        },
        {
            "side": "BUY",
            "pair": "HYPE-USD",
            "timestamp": (now - timedelta(hours=10)).isoformat(),
            "entry_price": 20.0,
            "qty": 1.0,
            "order_id": "b2",
        },
        {
            "side": "BUY",
            "pair": "SUI-USD",
            "timestamp": (now - timedelta(hours=5)).isoformat(),
            "entry_price": 1.0,
            "qty": 25.0,
            "order_id": "b3",
        },
    ]
    sells = [
        {
            "side": "SELL",
            "pair": "LINK-USD",
            "timestamp": now.isoformat(),
            "exit_price": 10.6,
            "entry_price": 10.0,
            "qty": 2.0,
            "pnl": 1.2,
            "reason": "take_profit_trail",
            "order_id": "s1",
            "entry_order_id": "b1",
        },
        {
            "side": "SELL",
            "pair": "HYPE-USD",
            "timestamp": now.isoformat(),
            "exit_price": 19.0,
            "entry_price": 20.0,
            "qty": 1.0,
            "pnl": -1.0,
            "reason": "stop_loss_exchange",
            "order_id": "s2",
            "entry_order_id": "b2",
        },
        {
            "side": "SELL",
            "pair": "SUI-USD",
            "timestamp": now.isoformat(),
            "exit_price": 1.05,
            "entry_price": 1.0,
            "qty": 25.0,
            "pnl": 1.25,
            "reason": "take_profit_fixed_tp",
            "order_id": "s3",
            "entry_order_id": "b3",
        },
        # stable ignored
        {
            "side": "SELL",
            "pair": "USDT-USDC",
            "timestamp": now.isoformat(),
            "exit_price": 1.0,
            "pnl": 0.0,
            "reason": "rotation_exchange",
            "order_id": "s4",
        },
    ]
    ledger = buys + sells
    rts = build_lifecycle_rts(ledger, since=now - timedelta(days=2), until=now)
    assert len(rts) == 3, rts
    classes = {r["pair"]: r["class"] for r in rts}
    assert classes["LINK-USD"] == "large"
    assert classes["HYPE-USD"] == "high_beta"
    assert classes["SUI-USD"] == "mid"
    assert any(r["exit_bucket"] == "tp_profit" for r in rts)
    assert any(r["exit_bucket"] == "sl_exchange" for r in rts)
    by = aggregate_group(rts, key="class", min_n=1)
    keys = {c["key"] for c in by}
    assert "large" in keys and "high_beta" in keys and "mid" in keys


def test_end_to_end_write_temp() -> None:
    now = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
    rows = []
    for i, (pair, reason, pnl) in enumerate(
        [
            ("LINK-USD", "take_profit_trail", 2.0),
            ("LINK-USD", "stop_loss_exchange", -1.0),
            ("SOL-USD", "take_profit_fixed_tp", 1.5),
            ("SOL-USD", "stop_loss_exchange", -0.8),
            ("SUI-USD", "take_profit_trail", 0.5),
            ("SUI-USD", "rotation_exchange", 0.1),
            ("HYPE-USD", "stop_loss_exchange", -0.4),
            ("HYPE-USD", "take_profit_fixed_tp", 0.9),
            ("ETH-USD", "rotation_exchange", 0.2),
            ("BTC-USD", "stop_loss_exchange", -0.3),
        ]
    ):
        ts_buy = (now - timedelta(hours=12 + i)).isoformat()
        ts_sell = (now - timedelta(hours=i)).isoformat()
        rows.append(
            {
                "side": "BUY",
                "pair": pair,
                "timestamp": ts_buy,
                "entry_price": 10.0,
                "qty": 1.0,
                "order_id": f"b{i}",
            }
        )
        rows.append(
            {
                "side": "SELL",
                "pair": pair,
                "timestamp": ts_sell,
                "exit_price": 10.0 + pnl,
                "entry_price": 10.0,
                "qty": 1.0,
                "pnl": pnl,
                "reason": reason,
                "order_id": f"s{i}",
                "entry_order_id": f"b{i}",
            }
        )
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        ledger = tdir / "ledger.jsonl"
        with ledger.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        # redirect outputs via monkeypatch paths is heavy — call build with ledger only
        # and write=False then assert structure
        payload = build_pair_lifecycle_by_class(
            lookback_days=30,
            write=False,
            ledger_path=ledger,
            now=now,
        )
        assert payload["schema"] == "pair_lifecycle_by_class_v1"
        assert payload["measure_only"] is True
        assert payload["live_apply"] is False
        assert payload["edge_claim_allowed"] is False
        assert payload["n_rt"] == 10
        assert payload["by_class"]
        assert isinstance(payload["hypothesis_notes"], list)
        # no class should claim edge
        assert all(c.get("claim_level") != "edge" for c in payload["by_class"])


if __name__ == "__main__":
    test_pair_class_defaults()
    test_build_rts_and_aggregate()
    test_end_to_end_write_temp()
    print("pair_lifecycle_by_class isolation PASS")
