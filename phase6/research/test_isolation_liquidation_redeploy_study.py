#!/usr/bin/env python3
"""Isolation: liquidation redeploy study pure helpers."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.run_liquidation_redeploy_study import build, load_rows, render_md  # noqa: E402


def main() -> int:
    # empty ledger path via monkeypatch load - build uses LEDGER constant; test render + empty cut
    cut = datetime(2099, 1, 1, tzinfo=timezone.utc)
    d = build(cut=cut)
    assert d["verdict"] in (
        "unreliable_as_default",
        "promising_needs_shadow",
        "insufficient_redeploy_sample_under_hold_policy",
        "keep_hold_only",
    )
    assert "NO-GO" in (d.get("go_no_go_live_partial") or "") or d["verdict"] != "unreliable_as_default"
    # with empty future cut, events empty
    assert d["large_free_capital_ge_50usd"]["n_events"] == 0
    md = render_md(d)
    assert "Liquidation" in md and "Verdict" in md

    # synthetic ledger file
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        ledger = td_path / "trades.jsonl"
        t0 = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
        rows = [
            {
                "timestamp": t0.isoformat().replace("+00:00", "Z"),
                "side": "SELL",
                "pair": "BTC-USD",
                "reason": "rotation_exchange",
                "qty": 1.0,
                "entry_price": 100.0,
                "pnl": 1.0,
            },
            {
                "timestamp": (t0 + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                "side": "BUY",
                "pair": "ETH-USD",
                "reason": "rebalance_buy",
                "qty": 1.0,
                "entry_price": 50.0,
                "pnl": 0.0,
            },
            {
                "timestamp": (t0 + timedelta(hours=10)).isoformat().replace("+00:00", "Z"),
                "side": "SELL",
                "pair": "ETH-USD",
                "reason": "stop_loss_exchange",
                "qty": 1.0,
                "entry_price": 50.0,
                "pnl": -5.0,
            },
        ]
        ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        # load_rows from path
        loaded = load_rows(ledger)
        assert len(loaded) == 3
        assert loaded[0]["usd"] == 100.0

    print("test_isolation_liquidation_redeploy_study: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
