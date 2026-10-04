#!/usr/bin/env python3
"""Isolation: tryout eject fee audit — net vs gross, wiped greens, ledger backfill."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeEx:
    def __init__(self, fees_by_oid: dict):
        self.fees_by_oid = fees_by_oid

    def get_order_fill_details(self, order_id: str):
        f = self.fees_by_oid.get(str(order_id))
        if f is None:
            return {}
        return {
            "total_fees": f.get("fee", 0.2),
            "average_filled_price": f.get("px", 10.0),
            "filled_size": f.get("sz", 1.0),
            "status": "FILLED",
        }


class TestEjectFeeAudit(unittest.TestCase):
    def test_gross_green_net_red_wiped(self):
        from phase6.core.tryout_eject_fee_audit import resolve_row_fees

        row = {
            "pair": "LINK-USD",
            "side": "SELL",
            "qty": 1.79,
            "entry_price": 13.921,
            "exit_price": 14.10,
            "reason": "tryout_scale_window_eject",
            "order_id": "sell-1",
            "entry_order_id": "buy-1",
        }
        # ~$0.32 gross; RT fees $0.45 → net red
        ex = FakeEx(
            {
                "sell-1": {"fee": 0.227, "px": 14.1, "sz": 1.79},
                "buy-1": {"fee": 0.224, "px": 13.921, "sz": 1.79},
            }
        )
        out = resolve_row_fees(row, taker_rate=0.009, exchange=ex, fetch_live=True)
        self.assertGreater(float(out["pnl_gross_usd"]), 0)
        self.assertLess(float(out["pnl_net_usd"]), 0)
        self.assertTrue(out["gross_green_net_red"])
        self.assertTrue(out["fee_blind_green"])
        self.assertFalse(out["fee_aware_green"])
        self.assertEqual(out["sell_fee_source"], "exchange_sell")
        self.assertEqual(out["entry_fee_source"], "exchange_entry")

    def test_estimate_when_no_exchange(self):
        from phase6.core.tryout_eject_fee_audit import resolve_row_fees

        row = {
            "pair": "TIA-USD",
            "side": "SELL",
            "qty": 50.0,
            "entry_price": 0.5,
            "exit_price": 0.5,
            "reason": "tryout_scale_window_eject",
        }
        out = resolve_row_fees(row, taker_rate=0.009, fetch_live=False)
        # flat gross, fees still apply
        self.assertAlmostEqual(float(out["pnl_gross_usd"] or 0), 0.0, places=5)
        self.assertAlmostEqual(float(out["rt_fee_usd"]), 25.0 * 0.009 * 2, places=4)
        self.assertLess(float(out["pnl_net_usd"]), 0)
        self.assertTrue(str(out["sell_fee_source"]).startswith("est_"))

    def test_audit_cohort_and_backfill(self):
        from phase6.core.tryout_eject_fee_audit import (
            audit_eject_cohort,
            backfill_ledger_fees,
        )

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "trades.jsonl"
            rows = [
                {
                    "pair": "HYPE-USD",
                    "side": "SELL",
                    "qty": 0.281,
                    "entry_price": 88.92,
                    "exit_price": 87.65,
                    "reason": "tryout_scale_window_eject",
                    "order_id": "s1",
                    "timestamp": "2026-10-02T22:45:43Z",
                },
                {
                    "pair": "SOL-USD",
                    "side": "BUY",
                    "qty": 1,
                    "reason": "other",
                    "order_id": "b1",
                },
            ]
            p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            ex = FakeEx({"s1": {"fee": 0.22, "px": 87.65, "sz": 0.281}})
            payload = audit_eject_cohort(
                ledger_path=p, exchange=ex, fetch_live=True, taker_rate=0.009
            )
            self.assertEqual(payload["n_ejects"], 1)
            self.assertEqual(payload["scoreboard"]["fee_blind_green_n"], 0)
            # dry backfill
            bf = backfill_ledger_fees(payload, ledger_path=p, dry_run=True)
            self.assertTrue(bf["ok"])
            self.assertEqual(bf["n_touched"], 1)
            bf2 = backfill_ledger_fees(payload, ledger_path=p, dry_run=False)
            self.assertTrue(bf2["ok"])
            self.assertTrue(Path(bf2["backup"]).is_file())
            rewritten = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
            sell = next(r for r in rewritten if r.get("order_id") == "s1")
            self.assertEqual(sell.get("pnl_stamp"), "fee_audit_net_rt")
            self.assertIsNotNone(sell.get("rt_fee_usd"))
            self.assertLess(float(sell["pnl"]), float(sell.get("pnl_gross") or 0))

    def test_stamp_sell_pnl_adds_entry_fee(self):
        from phase6.core.trade_ledger import stamp_sell_pnl

        row = {
            "side": "SELL",
            "qty": 1.0,
            "entry_price": 100.0,
            "exit_price": 101.0,
            "fee_usd": 0.2,
            "entry_fee_usd": 0.2,
        }
        out = stamp_sell_pnl(row)
        # gross 1.0 - 0.4 RT = 0.6
        self.assertAlmostEqual(float(out["pnl"]), 0.6, places=5)
        self.assertEqual(out["pnl_stamp"], "entry_exit_qty_net_fees")
        self.assertAlmostEqual(float(out["fee_usd_applied"]), 0.4, places=5)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestEjectFeeAudit)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
