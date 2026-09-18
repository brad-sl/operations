#!/usr/bin/env python3
"""Isolation: domain dispatcher + BookRebalanceAction refuse new seats."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.domain.actions.book_rebalance import (  # noqa: E402
    BookRebalanceAction,
    handler_from_action,
    held_pairs_from_live_state,
)
from phase6.domain.dispatcher import ActionDispatcher, InMemoryIdempotency, make_noop_handler  # noqa: E402
from phase6.domain.types import (  # noqa: E402
    ActionRequest,
    BookLeg,
    classify_leg,
    filter_book_legs,
)


class TestClassifyAndFilter(unittest.TestCase):
    def test_tryout_buy_refused(self):
        held = {"ETH-USD", "SOL-USD"}
        legs = [
            classify_leg(
                {"pair": "ADA-USD", "action": "BUY", "usd": 75, "quality_tryout": True},
                held_pairs=held,
            ),
            classify_leg(
                {"pair": "ETH-USD", "action": "SELL", "usd": 40, "reason": "trim_overweight"},
                held_pairs=held,
            ),
            classify_leg(
                {"pair": "SOL-USD", "action": "BUY", "usd": 25, "reason": "weight_fix"},
                held_pairs=held,
            ),
        ]
        self.assertEqual(legs[0].kind, "new_tryout_seat")
        self.assertEqual(legs[1].kind, "trim")
        self.assertEqual(legs[2].kind, "weight_fix")
        keep, refused, reasons = filter_book_legs(legs)
        self.assertEqual(len(refused), 1)
        self.assertEqual(refused[0].pair, "ADA-USD")
        self.assertEqual(len(keep), 2)
        self.assertTrue(any("book_rebalance_refuses_new_seats:ADA-USD" == r for r in reasons))

    def test_non_held_buy_fail_closed(self):
        leg = classify_leg({"pair": "HYPE-USD", "action": "BUY", "usd": 75}, held_pairs={"ETH-USD"})
        self.assertEqual(leg.kind, "new_tryout_seat")

    def test_opportunity_refused(self):
        leg = classify_leg(
            {"pair": "ZEC-USD", "action": "BUY", "usd": 100, "reason": "opportunity_rotate_in"},
            held_pairs=set(),
        )
        self.assertIn(leg.kind, ("opportunity_entry", "new_tryout_seat"))
        keep, refused, _ = filter_book_legs([leg])
        self.assertEqual(keep, [])
        self.assertEqual(len(refused), 1)

    def test_stable_cash_path_kept(self):
        leg = classify_leg(
            {"pair": "USDT-USDC", "action": "BUY", "usd": 200},
            held_pairs=set(),
        )
        self.assertEqual(leg.kind, "cash_path")
        keep, refused, _ = filter_book_legs([leg])
        self.assertEqual(len(keep), 1)
        self.assertEqual(refused, [])


class TestDispatcherIdempotency(unittest.TestCase):
    def test_noop_and_replay(self):
        d = ActionDispatcher(idempotency=InMemoryIdempotency())
        d.register("noop", make_noop_handler())
        req = ActionRequest(
            action="noop",
            tenant_id="default",
            idempotency_key="k1",
            params={},
        )
        r1 = d.dispatch(req)
        r2 = d.dispatch(req)
        self.assertTrue(r1.ok)
        self.assertEqual(r1.status, "noop")
        self.assertTrue(r2.replayed)
        self.assertEqual(r2.idempotency_key, "k1")

    def test_tenant_namespace_isolation(self):
        idem = InMemoryIdempotency()
        d = ActionDispatcher(idempotency=idem)
        d.register("noop", make_noop_handler())
        d.dispatch(
            ActionRequest(action="noop", tenant_id="t1", idempotency_key="same", params={})
        )
        r = d.dispatch(
            ActionRequest(action="noop", tenant_id="t2", idempotency_key="same", params={})
        )
        self.assertFalse(r.replayed)  # different tenant


class TestBookRebalanceAction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tdir = Path(self.tmp.name)
        self.live = self.tdir / "live.json"
        self.live.write_text(
            json.dumps(
                {
                    "positions": [
                        {"pair": "ETH-USD", "qty": 0.5, "usd_value": 1000},
                        {"pair": "SOL-USD", "qty": 2.0, "usd_value": 300},
                        {"pair": "USDT-USDC", "qty": 500, "usd_value": 500},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.receipts = self.tdir / "receipts"

    def tearDown(self):
        self.tmp.cleanup()

    def test_held_pairs_parse(self):
        live = json.loads(self.live.read_text(encoding="utf-8"))
        held = held_pairs_from_live_state(live)
        self.assertIn("ETH-USD", held)
        self.assertIn("SOL-USD", held)

    def test_strips_tryout_leg_dry_run(self):
        act = BookRebalanceAction(
            live_state_path=self.live,
            receipt_dir=self.receipts,
            write_receipt=True,
        )
        d = ActionDispatcher()
        d.register("book_rebalance", handler_from_action(act))
        legs = [
            {"pair": "ADA-USD", "action": "BUY", "usd": 75, "quality_tryout": True, "reason": "tryout"},
            {"pair": "ETH-USD", "action": "SELL", "usd": 50, "reason": "trim"},
            {"pair": "LINK-USD", "action": "BUY", "usd": 75, "is_tryout": True},
        ]
        req = ActionRequest(
            action="book_rebalance",
            tenant_id="default",
            idempotency_key="test-br-1",
            params={
                "dry_run": True,
                "plan_legs": legs,
                "live_state_path": str(self.live),
            },
            actor="test",
        )
        r = d.dispatch(req)
        self.assertTrue(r.ok)
        self.assertEqual(r.status, "dry_run")
        refused_pairs = {x["pair"] for x in r.artifacts["legs_refused"]}
        self.assertEqual(refused_pairs, {"ADA-USD", "LINK-USD"})
        keep_pairs = {x["pair"] for x in r.artifacts["legs_keep"]}
        self.assertEqual(keep_pairs, {"ETH-USD"})
        self.assertTrue(r.artifacts["book_rebalance_refuses_new_seats"])
        self.assertEqual(r.artifacts["orders"], [])
        self.assertIn("ETH-USD", r.artifacts["x_candidates"])
        self.assertNotIn("ADA-USD", r.artifacts["x_candidates"])  # refused not in plan keep
        # receipt written
        latest = self.receipts / "default" / "book_rebalance_latest.json"
        self.assertTrue(latest.is_file())

    def test_idempotent_double_dispatch(self):
        act = BookRebalanceAction(
            live_state_path=self.live,
            receipt_dir=self.receipts,
            write_receipt=False,
        )
        d = ActionDispatcher()
        d.register("book_rebalance", handler_from_action(act))
        req = ActionRequest(
            action="book_rebalance",
            tenant_id="default",
            idempotency_key="dup-key",
            params={"dry_run": True, "plan_legs": [], "live_state_path": str(self.live)},
        )
        a = d.dispatch(req)
        b = d.dispatch(req)
        self.assertTrue(b.replayed)
        self.assertEqual(a.idempotency_key, b.idempotency_key)


if __name__ == "__main__":
    unittest.main()
