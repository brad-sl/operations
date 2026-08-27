#!/usr/bin/env python3
"""Isolation: seat graduation funnel (seat→signal→fill→outcome)."""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import phase6.core.basket_pick_metrics as bpm  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="grad_iso_"))
    ledger = tmp / "picks.jsonl"
    dec = tmp / "decision.jsonl"
    audit = tmp / "run_phase.jsonl"
    trades = tmp / "trades.jsonl"

    t0 = datetime(2026, 8, 25, 18, 0, 0, tzinfo=timezone.utc)
    t_sig = t0 + timedelta(hours=22)
    t_block = t0 + timedelta(hours=22, minutes=1)

    # Pick: PENGU seated
    pick = {
        "pick_id": "test-pengu",
        "promoted_at": t0.isoformat(),
        "source": "manual_operator",
        "add_pair": "PENGU-USD",
        "remove_pair": "RAVE-USD",
        "status": "open",
        "marks": {},
        "baseline_add": {"price": 0.03},
    }
    ledger.write_text(json.dumps(pick) + "\n")

    # Signal in decision context
    dec.write_text(
        json.dumps(
            {
                "id": f"rebalance_{t_sig.strftime('%Y%m%dT%H%M%S')}Z_test",
                "ts": t_sig.isoformat(),
                "proposals": [
                    {"pair": "PENGU-USD", "action": "ROTATE_IN", "score": 0.7},
                ],
                "tilted_plan": {
                    "actions": [
                        {"pair": "PENGU-USD", "side": "BUY", "usd": 711.0},
                    ]
                },
            }
        )
        + "\n"
    )

    # Run-phase block, no fill
    audit.write_text(
        json.dumps(
            {
                "ts": t_block.isoformat(),
                "results": [
                    {
                        "pair": "PENGU-USD",
                        "original_usd": 100.0,
                        "dropped": True,
                        "blocked": True,
                        "phase_name": "distribution",
                        "snapshot": {"off_peak_pct": 0.16, "phase_name": "distribution"},
                    }
                ],
            }
        )
        + "\n"
    )
    trades.write_text("")  # no fills

    # Point module paths at temp
    bpm.LEDGER_PATH = ledger
    bpm.DECISION_CTX_PATH = dec
    bpm.RUN_PHASE_AUDIT_PATH = audit
    bpm.TRADES_PATH = trades
    bpm.GRAD_LATEST_PATH = tmp / "grad_latest.json"
    bpm.GRAD_REPORT_PATH = tmp / "grad_report.md"
    bpm.SUMMARY_PATH = tmp / "summary.json"

    out = bpm.refresh_graduation(path=ledger)
    assert out["funnel"]["n_seated"] == 1, out
    assert out["funnel"]["n_signaled"] == 1, out
    assert out["funnel"]["n_blocked_no_fill"] == 1, out
    assert out["funnel"]["n_filled"] == 0, out
    assert out["picks"][0]["stage"] == "blocked_no_fill", out["picks"][0]

    # Add a winning fill episode on a second pick
    t1 = datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)
    pick2 = {
        "pick_id": "test-win",
        "promoted_at": t1.isoformat(),
        "source": "test",
        "add_pair": "TEST-USD",
        "remove_pair": None,
        "status": "open",
        "marks": {},
        "baseline_add": {"price": 1.0},
    }
    with ledger.open("a") as f:
        f.write(json.dumps(pick2) + "\n")
    with dec.open("a") as f:
        f.write(
            json.dumps(
                {
                    "ts": (t1 + timedelta(hours=1)).isoformat(),
                    "proposals": [{"pair": "TEST-USD", "action": "ROTATE_IN", "score": 0.5}],
                    "tilted_plan": {"actions": [{"pair": "TEST-USD", "side": "BUY", "usd": 50}]},
                }
            )
            + "\n"
        )
    with trades.open("a") as f:
        f.write(
            json.dumps(
                {
                    "timestamp": (t1 + timedelta(hours=2)).isoformat(),
                    "pair": "TEST-USD",
                    "side": "BUY",
                    "qty": 50,
                    "entry_price": 1.0,
                }
            )
            + "\n"
        )
        f.write(
            json.dumps(
                {
                    "timestamp": (t1 + timedelta(days=1)).isoformat(),
                    "pair": "TEST-USD",
                    "side": "SELL",
                    "qty": 50,
                    "exit_price": 1.1,
                    "pnl": 5.0,
                    "pnl_pct": 0.1,
                }
            )
            + "\n"
        )

    out2 = bpm.refresh_graduation(path=ledger)
    stages = {p["add_pair"]: p["stage"] for p in out2["picks"]}
    assert stages.get("PENGU-USD") == "blocked_no_fill", stages
    assert stages.get("TEST-USD") == "filled_win", stages
    assert out2["funnel"]["n_filled_win"] == 1, out2["funnel"]
    assert out2["funnel"]["rate_win_given_seat"] == 0.5, out2["funnel"]
    assert bpm.GRAD_LATEST_PATH.exists()
    assert bpm.GRAD_REPORT_PATH.exists()
    print("OK isolation basket_seat_graduation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
