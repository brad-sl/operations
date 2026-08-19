#!/usr/bin/env python3
"""Isolation: liquidation redeploy shadow pure logic."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.liquidation_redeploy_shadow import (  # noqa: E402
    Candidate,
    evaluate_shadow,
    record_from_disposition_event,
    record_from_ledger_sell_row,
    size_usd,
)


def main() -> int:
    assert size_usd(50) == 0.0  # below min 100
    assert size_usd(400) == 75.0  # 25%=100 capped to 75
    assert size_usd(200) == 50.0

    cands = [
        Candidate("ETH-USD", score=0.5, rsi=40.0, sentiment=0.4),
        Candidate("BTC-USD", score=0.9, rsi=40.0, sentiment=0.4),  # same as sell blocked
        Candidate("SOL-USD", score=0.2, rsi=40.0, sentiment=0.4),  # low score
        Candidate("LINK-USD", score=0.55, rsi=70.0, sentiment=0.4),  # rsi gate
    ]
    gates = {"max_rsi": 55.0, "min_sentiment": 0.25, "min_sentiment_new_pair": 0.35}

    d = evaluate_shadow(
        sell_pair="BTC-USD",
        sell_reason="rotation_exchange",
        proceeds_usd=1992.0,
        regime="flat",
        allow_new_buys=True,
        entry_gates=gates,
        candidates=cands,
    )
    assert d.fire is True
    assert d.candidate_pair == "ETH-USD"
    assert d.size_usd == 75.0

    d2 = evaluate_shadow(
        sell_pair="BTC-USD",
        sell_reason="stop_loss_exchange",
        proceeds_usd=500.0,
        regime="flat",
        allow_new_buys=True,
        entry_gates=gates,
        candidates=cands,
    )
    assert d2.fire is False and "deny" in (d2.skip_reason or "")

    d3 = evaluate_shadow(
        sell_pair="BTC-USD",
        sell_reason="rotation_exchange",
        proceeds_usd=500.0,
        regime="bear",
        allow_new_buys=False,
        entry_gates=gates,
        candidates=cands,
    )
    assert d3.fire is False and d3.skip_reason == "regime_blocks_new_buys"

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "shadow.jsonl"
        # force path via record_free_capital_shadow
        from phase6.core.liquidation_redeploy_shadow import record_free_capital_shadow

        rec = record_free_capital_shadow(
            sell_pair="BTC-USD",
            sell_reason="rotation_exchange",
            proceeds_usd=1992.0,
            source="iso_test",
            log_path=log,
        )
        assert rec["orders_placed"] == 0
        assert log.exists() and log.read_text().strip()
        assert "live_auto" in log.read_text()

        # disposition helper
        rows = record_from_disposition_event(
            {
                "ts": "2026-08-16T16:06:00Z",
                "event_type": "manual_liquidation_to_cash",
                "pairs_sold": ["BTC-USD"],
                "delta_cash": 1992.0,
                "action": "hold_cash_block_rebuy",
            }
        )
        # disposition writes default path — just ensure no throw and list
        assert isinstance(rows, list)

        # stop denied
        from phase6.core.liquidation_redeploy_shadow import record_free_capital_shadow as r2

        r_stop = r2(
            sell_pair="ETH-USD",
            sell_reason="stop_loss_exchange",
            proceeds_usd=200.0,
            source="iso_stop",
            log_path=log,
        )
        assert r_stop["decision"]["fire"] is False

    print("test_isolation_liquidation_redeploy_shadow: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
