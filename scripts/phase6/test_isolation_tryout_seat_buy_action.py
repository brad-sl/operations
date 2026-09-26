#!/usr/bin/env python3
"""Isolation: TryoutSeatBuyAction + shell resolve + composer candidate select."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_event_tryout_seat_composer import select_buy_candidate  # noqa: E402
from phase6.domain.actions.tryout_seat_buy import (  # noqa: E402
    TryoutSeatBuyAction,
    handler_from_action,
    held_pairs_from_live_state,
    plan_tryout_seat,
    resolve_shell_usd,
)
from phase6.domain.dispatcher import ActionDispatcher, InMemoryIdempotency  # noqa: E402
from phase6.domain.types import ActionRequest  # noqa: E402


class FakeSnap:
    def __init__(self, allow: bool = True, mode: str = "deploy"):
        self.allow_new_buys = allow
        self.strategy_mode = mode
        self.entry = {
            "min_sentiment": 0.0,
            "min_sentiment_new_pair": 0.0,
            "max_rsi": 100.0,
            "require_lockout_clear": False,
        }
        self.regime = "flat"


class FakeDec:
    def __init__(self, allowed: bool, reasons=None):
        self.allowed = allowed
        self.reasons = list(reasons or [])


class FakeExecutor:
    def __init__(self, shadow_mode: bool = False, succeed: bool = True):
        self.shadow_mode = shadow_mode
        self.succeed = succeed
        self.calls = []

    def execute_buy(self, pair, usd, **kwargs):
        self.calls.append((pair, usd, kwargs))
        if self.succeed:
            return {"success": True, "order_id": "oid-test-1", "entry_price": 1.0, "size": 1.0}
        return {"success": False, "error": "venue_reject"}


class TestShellResolve(unittest.TestCase):
    def test_abs_cap_wins(self):
        self.assertEqual(resolve_shell_usd(abs_cap_usd=25, max_shell_usd=75), 25.0)

    def test_hard_cap(self):
        self.assertEqual(resolve_shell_usd(abs_cap_usd=100, max_shell_usd=75), 75.0)

    def test_override_tightens(self):
        self.assertEqual(
            resolve_shell_usd(abs_cap_usd=25, max_shell_usd=75, override_usd=10), 10.0
        )


class TestHeldParse(unittest.TestCase):
    def test_list_positions(self):
        live = {
            "positions": [
                {"pair": "ETH-USD", "qty": 0.5, "usd_value": 1000},
                {"pair": "USDT-USDC", "qty": 100, "usd_value": 100},
            ]
        }
        held = held_pairs_from_live_state(live)
        self.assertIn("ETH-USD", held)
        self.assertNotIn("USDT-USDC", held)


class TestPlanTryoutSeat(unittest.TestCase):
    def test_held_skip(self):
        plan = plan_tryout_seat(
            "ETH-USD",
            sentiment=0.5,
            rsi=30,
            held_pairs={"ETH-USD"},
            snap=FakeSnap(),
            policy={"_isolation_skip_process_tax": True},
            isolation_skip_process_tax=True,
        )
        self.assertEqual(plan.status, "skipped_held")

    @patch("phase6.domain.actions.tryout_seat_buy.kill_switch_on", return_value=False)
    @patch("phase6.core.regime_cash_policy.evaluate_buy_entry")
    @patch("phase6.core.regime_cash_policy.recovery_quality_tryout_cfg")
    @patch("phase6.core.regime_cash_policy._recovery_rec")
    @patch("phase6.core.regime_cash_policy.load_policy")
    def test_planned_when_entry_ok(self, load_pol, rec, qt, eval_buy, _ks):
        load_pol.return_value = {}
        rec.return_value = {"new_alt_policy": "quality_tryout"}
        qt.return_value = {
            "abs_cap_usd": 25.0,
            "min_sentiment": 0.30,
            "max_rsi": 55.0,
            "max_new_seats_per_day": 4,
        }
        eval_buy.return_value = FakeDec(True, ["ok"])
        plan = plan_tryout_seat(
            "LINK-USD",
            sentiment=0.40,
            rsi=28,
            held_pairs=set(),
            snap=FakeSnap(),
            policy={},
            isolation_skip_process_tax=True,
        )
        self.assertEqual(plan.status, "planned")
        self.assertEqual(plan.shell_usd, 25.0)

    @patch("phase6.domain.actions.tryout_seat_buy.kill_switch_on", return_value=False)
    @patch("phase6.core.regime_cash_policy.evaluate_buy_entry")
    @patch("phase6.core.regime_cash_policy.recovery_quality_tryout_cfg")
    @patch("phase6.core.regime_cash_policy._recovery_rec")
    @patch("phase6.core.regime_cash_policy.load_policy")
    def test_blocked_when_entry_fails(self, load_pol, rec, qt, eval_buy, _ks):
        load_pol.return_value = {}
        rec.return_value = {"new_alt_policy": "quality_tryout"}
        qt.return_value = {"abs_cap_usd": 25.0, "min_sentiment": 0.30, "max_rsi": 55.0}
        eval_buy.return_value = FakeDec(False, ["sentiment 0.10 < min 0.30"])
        plan = plan_tryout_seat(
            "LINK-USD",
            sentiment=0.10,
            rsi=28,
            held_pairs=set(),
            snap=FakeSnap(),
            isolation_skip_process_tax=True,
        )
        self.assertEqual(plan.status, "blocked")


class TestActionDryAndLive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tdir = Path(self.tmp.name)
        self.live = self.tdir / "live.json"
        self.live.write_text(
            json.dumps({"positions": [{"pair": "ETH-USD", "qty": 1.0, "usd_value": 2000}]}),
            encoding="utf-8",
        )
        self.receipts = self.tdir / "receipts"
        self.latest = self.tdir / "latest.json"
        self.events = self.tdir / "events.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _act(self, executor_factory=None):
        return TryoutSeatBuyAction(
            live_state_path=self.live,
            receipt_dir=self.receipts,
            latest_path=self.latest,
            events_path=self.events,
            write_receipt=True,
            executor_factory=executor_factory,
        )

    @patch("phase6.domain.actions.tryout_seat_buy.plan_tryout_seat")
    def test_dry_would_buy(self, plan_fn):
        from phase6.domain.actions.tryout_seat_buy import SeatPlan

        plan_fn.return_value = SeatPlan(
            pair="LINK-USD",
            shell_usd=25.0,
            status="planned",
            reasons=["ready"],
            sentiment=0.4,
            rsi=30,
        )
        act = self._act()
        d = ActionDispatcher(idempotency=InMemoryIdempotency())
        d.register("tryout_seat_buy", handler_from_action(act))
        r = d.dispatch(
            ActionRequest(
                action="tryout_seat_buy",
                tenant_id="default",
                idempotency_key="dry1",
                params={
                    "pair": "LINK-USD",
                    "sentiment": 0.4,
                    "rsi": 30,
                    "dry_run": True,
                    "go": False,
                },
            )
        )
        self.assertTrue(r.ok)
        self.assertEqual(r.status, "dry_run")
        self.assertEqual((r.artifacts or {}).get("plan", {}).get("status"), "dry_would_buy")
        self.assertFalse((r.artifacts or {}).get("applied"))

    @patch("phase6.domain.actions.tryout_seat_buy.plan_tryout_seat")
    def test_live_fill_with_fake_executor(self, plan_fn):
        from phase6.domain.actions.tryout_seat_buy import SeatPlan

        plan_fn.return_value = SeatPlan(
            pair="LINK-USD",
            shell_usd=25.0,
            status="planned",
            reasons=["ready"],
            sentiment=0.4,
            rsi=30,
        )
        ex = FakeExecutor(shadow_mode=False, succeed=True)
        act = self._act(executor_factory=lambda shadow: ex)
        d = ActionDispatcher(idempotency=InMemoryIdempotency())
        d.register("tryout_seat_buy", handler_from_action(act))
        r = d.dispatch(
            ActionRequest(
                action="tryout_seat_buy",
                tenant_id="default",
                idempotency_key="live1",
                params={
                    "pair": "LINK-USD",
                    "sentiment": 0.4,
                    "rsi": 30,
                    "dry_run": False,
                    "go": True,
                    "executor": ex,
                },
            )
        )
        self.assertTrue(r.ok)
        self.assertEqual(r.status, "ok")
        self.assertTrue((r.artifacts or {}).get("applied"))
        self.assertEqual(len(ex.calls), 1)
        self.assertEqual(ex.calls[0][0], "LINK-USD")
        self.assertEqual(ex.calls[0][1], 25.0)

    @patch("phase6.domain.actions.tryout_seat_buy.plan_tryout_seat")
    def test_go_without_live_stays_dry(self, plan_fn):
        from phase6.domain.actions.tryout_seat_buy import SeatPlan

        plan_fn.return_value = SeatPlan(
            pair="LINK-USD", shell_usd=25.0, status="planned", reasons=["ready"]
        )
        ex = FakeExecutor()
        act = self._act()
        d = ActionDispatcher()
        d.register("tryout_seat_buy", handler_from_action(act))
        r = d.dispatch(
            ActionRequest(
                action="tryout_seat_buy",
                tenant_id="default",
                idempotency_key="go-dry",
                params={
                    "pair": "LINK-USD",
                    "sentiment": 0.4,
                    "dry_run": True,
                    "go": True,
                    "executor": ex,
                },
            )
        )
        self.assertEqual(r.status, "dry_run")
        self.assertEqual(len(ex.calls), 0)

    def test_idempotent_replay(self):
        from phase6.domain.actions.tryout_seat_buy import SeatPlan

        with patch(
            "phase6.domain.actions.tryout_seat_buy.plan_tryout_seat",
            return_value=SeatPlan(
                pair="ADA-USD", shell_usd=25.0, status="planned", reasons=["ready"]
            ),
        ):
            act = self._act()
            d = ActionDispatcher(idempotency=InMemoryIdempotency())
            d.register("tryout_seat_buy", handler_from_action(act))
            req = ActionRequest(
                action="tryout_seat_buy",
                tenant_id="default",
                idempotency_key="same-key",
                params={"pair": "ADA-USD", "sentiment": 0.5, "dry_run": True},
            )
            r1 = d.dispatch(req)
            r2 = d.dispatch(req)
            self.assertTrue(r1.ok)
            self.assertTrue(r2.replayed)


class TestComposerSelect(unittest.TestCase):
    def test_picks_deeper_wash_clearing_floor(self):
        rows = [
            {"pair": "AAA-USD", "rsi": 38, "fetched_raw": 0.35},
            {"pair": "BBB-USD", "rsi": 22, "fetched_raw": 0.32},
            {"pair": "CCC-USD", "rsi": 20, "fetched_raw": 0.10},  # under floor
        ]
        c = select_buy_candidate(rows, floor=0.30)
        self.assertIsNotNone(c)
        self.assertEqual(c["pair"], "BBB-USD")

    def test_override_pair(self):
        rows = [
            {"pair": "AAA-USD", "rsi": 20, "fetched_raw": 0.5},
            {"pair": "BBB-USD", "rsi": 25, "fetched_raw": 0.5},
        ]
        c = select_buy_candidate(rows, floor=0.30, pair_override="BBB-USD")
        self.assertEqual(c["pair"], "BBB-USD")

    def test_none_when_no_clear(self):
        rows = [{"pair": "AAA-USD", "rsi": 20, "fetched_raw": 0.1}]
        self.assertIsNone(select_buy_candidate(rows, floor=0.30))


if __name__ == "__main__":
    unittest.main()
