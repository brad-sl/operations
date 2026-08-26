#!/usr/bin/env python3
"""Isolation: SL fill entry must not use stale-low registry when stop sits above it."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace


def test_stale_registry_prefers_ledger_buy():
    from phase6.core.exchange_fill_reconciler import (
        _registry_entry_consistent_with_stop,
        resolve_sl_fill_entry,
    )

    assert not _registry_entry_consistent_with_stop(10.018, 11.28)
    assert _registry_entry_consistent_with_stop(11.6038, 11.28)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ledger_path = root / "trades.jsonl"
        # Aug 24 open lot buy
        ledger_path.write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-24T16:00:30Z",
                    "pair": "LINK-USD",
                    "side": "BUY",
                    "entry_price": 11.603782489823198,
                    "qty": 164.59,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        reg_path = root / "registry.jsonl"
        reg_path.write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-25T16:06:16Z",
                    "pair": "LINK-USD",
                    "sl_order_id": "a97b033b-test",
                    "entry_price": 10.018835057728468,
                    "stop_price": 11.28,
                    "qty": 90.72,
                    "status": "open",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        import phase6.core.exchange_fill_reconciler as fr
        import phase6.core.protective_orders_registry as por

        old_reg = por.REGISTRY_PATH
        por.REGISTRY_PATH = reg_path
        try:
            ledger = SimpleNamespace(jsonl_path=ledger_path)
            # monkey: _entry_from_ledger_buys reads ledger.jsonl_path
            entry, src = resolve_sl_fill_entry(
                pair="LINK-USD",
                fill_ts="2026-08-25T16:06:16Z",
                fill_px=11.27674537037037,
                ledger=ledger,  # type: ignore[arg-type]
                sl_order_id="a97b033b-test",
                stop_px=11.28,
            )
        finally:
            por.REGISTRY_PATH = old_reg

    assert entry is not None
    assert abs(float(entry) - 11.603782489823198) < 1e-6, (entry, src)
    assert "ledger" in src or src == "ledger_last_buy_over_stale_registry", src
    pnl_pct = (11.27674537037037 - float(entry)) / float(entry)
    assert pnl_pct < 0, pnl_pct  # real lot was a stop-out loss
    assert abs(pnl_pct - (-0.02817)) < 0.002, pnl_pct
    print(f"OK entry={entry} src={src} pnl_pct={pnl_pct:.4f}")


def test_consistent_registry_kept():
    from phase6.core.exchange_fill_reconciler import resolve_sl_fill_entry

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ledger_path = root / "trades.jsonl"
        ledger_path.write_text(
            json.dumps(
                {
                    "timestamp": "2026-08-23T04:00:00Z",
                    "pair": "UNI-USD",
                    "side": "BUY",
                    "entry_price": 4.57095,
                    "qty": 200,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        reg_path = root / "registry.jsonl"
        reg_path.write_text(
            json.dumps(
                {
                    "pair": "UNI-USD",
                    "sl_order_id": "uni-sl",
                    "entry_price": 4.57095,
                    "stop_price": 4.4689,
                    "status": "open",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        import phase6.core.protective_orders_registry as por

        old = por.REGISTRY_PATH
        por.REGISTRY_PATH = reg_path
        try:
            ledger = SimpleNamespace(jsonl_path=ledger_path)
            entry, src = resolve_sl_fill_entry(
                pair="UNI-USD",
                fill_ts="2026-08-23T18:05:12Z",
                fill_px=4.4689,
                ledger=ledger,  # type: ignore[arg-type]
                sl_order_id="uni-sl",
                stop_px=4.4689,
            )
        finally:
            por.REGISTRY_PATH = old
    assert abs(float(entry) - 4.57095) < 1e-6
    assert src in ("protective_registry", "ledger_last_buy"), src
    print(f"OK consistent entry={entry} src={src}")


if __name__ == "__main__":
    test_stale_registry_prefers_ledger_buy()
    test_consistent_registry_kept()
    print("sl fill entry resolve isolation PASS")
