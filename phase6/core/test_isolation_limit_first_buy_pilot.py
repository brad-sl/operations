#!/usr/bin/env python3
"""Isolation: Phase D pilot caps, kill, TradeExecutor delegate."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_pilot_caps(tmp_path: Path) -> None:
    import phase6.core.limit_first_buy_pilot as p
    from phase6.core.limit_first_buy import LimitFirstPolicy

    tmp_path.mkdir(parents=True, exist_ok=True)
    p.PILOT_STATE = tmp_path / "st.json"
    p.PILOT_EVENTS = tmp_path / "ev.jsonl"
    p.PILOT_REPORT = tmp_path / "r.md"
    p.KILL_SWITCH = tmp_path / "KILL"
    p.STATE_DIR = tmp_path

    pol = LimitFirstPolicy(enabled=True, pilot_max_buys_per_day=2, pilot_max_usd_per_day=100)
    ok, reason = p.pilot_allows_limit(40, pol)
    assert ok and reason == "ok"
    p.record_limit_attempt(pair="BTC-USD", usd_amount=40, outcome="attempted")
    p.record_limit_attempt(pair="ETH-USD", usd_amount=40, outcome="attempted")
    ok2, r2 = p.pilot_allows_limit(40, pol)
    assert not ok2 and r2 == "pilot_max_buys"

    p.PILOT_STATE.unlink(missing_ok=True)
    p.record_limit_attempt(pair="X", usd_amount=90, outcome="attempted")
    ok3, r3 = p.pilot_allows_limit(20, pol)
    assert not ok3 and r3 == "pilot_max_usd"


def test_kill_switch(tmp_path: Path) -> None:
    import phase6.core.limit_first_buy_pilot as p
    from phase6.core.limit_first_buy import LimitFirstPolicy

    tmp_path.mkdir(parents=True, exist_ok=True)
    p.PILOT_STATE = tmp_path / "st.json"
    p.PILOT_EVENTS = tmp_path / "ev.jsonl"
    p.KILL_SWITCH = tmp_path / "KILL"
    p.STATE_DIR = tmp_path
    p.KILL_SWITCH.write_text("x")
    ok, r = p.pilot_allows_limit(10, LimitFirstPolicy(enabled=True))
    assert not ok and r == "kill_switch"


def test_policy_dual_fence() -> None:
    from phase6.core.limit_first_buy import policy_from_config

    assert policy_from_config(
        {"entry_execution": {"mode": "limit_first_v1", "limit_first": {"enabled": True}}}
    ).enabled is True
    assert policy_from_config(
        {"entry_execution": {"mode": "market_ioc", "limit_first": {"enabled": True}}}
    ).enabled is False


def test_trade_executor_delegates(tmp_path: Path) -> None:
    from trading.executor import TradeExecutor
    from trading.client import ShadowTradingClient

    tmp_path.mkdir(parents=True, exist_ok=True)
    calls = []

    class FakeOE:
        def execute_buy(self, pair, usd, **kw):
            calls.append((pair, usd, kw))
            return {"success": True, "execution_style": "limit_post_only", "pair": pair}

    import phase6.core.limit_first_buy_pilot as pilot

    orig = pilot.load_entry_execution_from_disk
    try:
        pilot.load_entry_execution_from_disk = lambda: {  # type: ignore
            "mode": "limit_first_v1",
            "limit_first": {"enabled": True, "market_fallback": False},
        }

        te = TradeExecutor(
            client=ShadowTradingClient(initial_capital=1000),
            order_executor=FakeOE(),
            config_dict={},
        )
        r = te.execute_buy("BTC-USD", 50.0)
        assert r.get("execution_style") == "limit_post_only"
        assert calls and calls[0][0] == "BTC-USD"

        r2 = te.execute_buy("ETH-USD", 25.0, force_market=True)
        assert r2.get("success") is True
        assert len(calls) == 1
    finally:
        pilot.load_entry_execution_from_disk = orig


def test_order_executor_over_cap_goes_market(tmp_path: Path) -> None:
    import phase6.core.limit_first_buy_pilot as p
    from phase6.core.order_executor import OrderExecutor

    tmp_path.mkdir(parents=True, exist_ok=True)
    p.PILOT_STATE = tmp_path / "st.json"
    p.PILOT_EVENTS = tmp_path / "ev.jsonl"
    p.PILOT_REPORT = tmp_path / "r.md"
    p.KILL_SWITCH = tmp_path / "no_kill"
    p.STATE_DIR = tmp_path
    orig = p.load_entry_execution_from_disk
    try:
        p.load_entry_execution_from_disk = lambda: {  # type: ignore
            "mode": "limit_first_v1",
            "limit_first": {
                "enabled": True,
                "pilot_max_buys_per_day": 0,
                "pilot_max_usd_per_day": 30,
                "market_fallback": False,
                "post_only": True,
            },
        }

        class Ex:
            def place_market_buy(self, pair, usd):
                return {"success": True, "order_id": "m1"}

            def place_limit_buy(self, *a, **k):
                raise AssertionError("should not limit when over cap")

            def get_best_bid_ask(self, pair):
                return {"bid": 100.0, "ask": 101.0, "last": 100.5}

            def get_price(self, pair):
                return 100.0

        class SL:
            config = {
                "entry_execution": {
                    "mode": "limit_first_v1",
                    "limit_first": {
                        "enabled": True,
                        "pilot_max_usd_per_day": 30,
                        "market_fallback": False,
                    },
                }
            }

            def attach_stop_loss(self, *a, **k):
                return False

        p.record_limit_attempt(pair="A", usd_amount=30, outcome="attempted")

        oe = OrderExecutor(Ex(), SL(), mode="live", logger=__import__("logging").getLogger("t"))
        oe._finalize_buy_fill = lambda *a, **k: {  # type: ignore
            "success": True,
            "order_id": "m1",
            "entry_price": 100.0,
            "size": 0.3,
            "qty": 0.3,
            "sl_attached": False,
            "tp_attached": False,
            "execution_style": k.get("execution_style", "market_ioc"),
            "fill_status": "full",
        }
        r = oe.execute_buy("BTC-USD", 50.0, record_ledger=False, config_dict=SL.config)
        assert r.get("success")
        assert r.get("execution_style") == "market_ioc"
    finally:
        p.load_entry_execution_from_disk = orig
        # restore module paths so A/B tests don't hit tmp
        from phase6.core.paths import STATE_DIR, PROJECT_ROOT

        p.STATE_DIR = STATE_DIR
        p.PILOT_STATE = STATE_DIR / "limit_first_buy_pilot_state.json"
        p.PILOT_EVENTS = STATE_DIR / "limit_first_buy_pilot_events.jsonl"
        p.PILOT_REPORT = PROJECT_ROOT / "reports" / "LIMIT_FIRST_BUY_PILOT_LATEST.md"
        p.KILL_SWITCH = STATE_DIR / "limit_first_buy_KILL"


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        test_pilot_caps(base / "caps")
        test_kill_switch(base / "kill")
        test_policy_dual_fence()
        test_trade_executor_delegates(base / "te")
        test_order_executor_over_cap_goes_market(base / "oc")
    # Keep original A/B isolation green
    from phase6.core.test_isolation_limit_first_buy import main as ab_main

    ab_main()
    print("PASS test_isolation_limit_first_buy_pilot")


if __name__ == "__main__":
    main()
