#!/usr/bin/env python3
"""Isolation: post-SL reentry episode builder (synthetic ledger + real optional)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.phase6.run_post_sl_reentry_eff import (  # noqa: E402
    build_episodes,
    load_rows,
    summarize,
)


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def test_synthetic_rebuy_and_second_sl() -> None:
    rows = [
        {
            "timestamp": "2026-08-01T00:00:00Z",
            "pair": "AAA-USD",
            "side": "SELL",
            "reason": "stop_loss_exchange",
            "qty": 10,
            "exit_price": 2.0,
            "pnl": -5.0,
        },
        {
            "timestamp": "2026-08-01T10:00:00Z",  # 10h < 72
            "pair": "AAA-USD",
            "side": "buy",
            "reason": "rebalance_buy",
            "qty": 10,
            "entry_price": 2.1,
            "usd_value": 21.0,
        },
        {
            "timestamp": "2026-08-02T10:00:00Z",
            "pair": "AAA-USD",
            "side": "SELL",
            "reason": "stop_loss_exchange",
            "qty": 10,
            "exit_price": 1.9,
            "pnl": -3.0,
        },
        # no rebuy
        {
            "timestamp": "2026-08-01T00:00:00Z",
            "pair": "BBB-USD",
            "side": "SELL",
            "reason": "stop_loss_exchange",
            "qty": 5,
            "exit_price": 10.0,
            "pnl": -2.0,
        },
        # dust SL ignored in core
        {
            "timestamp": "2026-08-01T00:00:00Z",
            "pair": "CCC-USD",
            "side": "SELL",
            "reason": "stop_loss_exchange",
            "qty": 0.01,
            "exit_price": 1.0,
            "pnl": -0.01,
        },
    ]
    with tempfile.TemporaryDirectory() as td:
        led = Path(td) / "t.jsonl"
        _write_ledger(led, rows)
        loaded = load_rows(led)
        eps = build_episodes(loaded)
        # 2 AAA SL legs + BBB + dust CCC
        assert len(eps) == 4
        aaa = [e for e in eps if e.pair == "AAA-USD" and e.rebuy][0]
        assert aaa.rebuy is True
        assert aaa.rebuy_within_24h is True
        assert aaa.second_sl is True
        assert aaa.second_sl_pnl_usd == -3.0
        bbb = [e for e in eps if e.pair == "BBB-USD"][0]
        assert bbb.rebuy is False
        ccc = [e for e in eps if e.pair == "CCC-USD"][0]
        assert ccc.dust_sl is True
        # Pad synthetic re-entries so summarize path exercises tighten branch without claiming live N
        extra = []
        for i in range(16):
            extra += [
                {
                    "timestamp": f"2026-07-{(i%28)+1:02d}T00:00:00Z",
                    "pair": f"X{i}-USD",
                    "side": "SELL",
                    "reason": "stop_loss_exchange",
                    "qty": 10,
                    "exit_price": 5.0,
                    "pnl": -4.0,
                },
                {
                    "timestamp": f"2026-07-{(i%28)+1:02d}T12:00:00Z",
                    "pair": f"X{i}-USD",
                    "side": "buy",
                    "reason": "rebalance_buy",
                    "qty": 10,
                    "entry_price": 5.0,
                    "usd_value": 50.0,
                },
                {
                    "timestamp": f"2026-07-{(i%28)+1:02d}T20:00:00Z",
                    "pair": f"X{i}-USD",
                    "side": "SELL",
                    "reason": "stop_loss_exchange",
                    "qty": 10,
                    "exit_price": 4.5,
                    "pnl": -5.0,
                },
            ]
        _write_ledger(led, rows + extra)
        rep = summarize(build_episodes(load_rows(led)), min_n=15)
        assert rep["counts"]["reentry_episodes"] >= 15
        assert rep["enum"] in {"tighten", "inconclusive", "hold_ok", "gap_in_code"}
        assert rep["rates_of_reentry"]["second_sl_rate"] is not None
        print("PASS synthetic episode + summarize")
        print(" synthetic enum", rep["enum"], "n_re", rep["counts"]["reentry_episodes"],
              "second", rep["rates_of_reentry"]["second_sl_rate"])


def test_real_ledger_smoke() -> None:
    led = ROOT / "trades" / "phase6_trades.jsonl"
    if not led.exists():
        print("SKIP real ledger missing")
        return
    eps = build_episodes(load_rows(led))
    rep = summarize(eps, min_n=15)
    assert "enum" in rep
    assert rep["counts"]["sl_episodes_core_non_dust"] >= 1
    print("PASS real ledger smoke")
    print(" real enum", rep["enum"], "n_sl", rep["counts"]["sl_episodes_core_non_dust"],
          "n_re", rep["counts"]["reentry_episodes"],
          "rebuy72", rep["rates_of_core_sl"]["rebuy_within_72h"],
          "second", rep["rates_of_reentry"]["second_sl_rate"])


if __name__ == "__main__":
    test_synthetic_rebuy_and_second_sl()
    test_real_ledger_smoke()
    print("ALL POST_SL REENTRY ISOLATION CHECKS PASSED")
