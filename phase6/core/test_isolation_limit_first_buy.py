#!/usr/bin/env python3
"""Isolation: limit-first policy + dark executor path (no network orders).

Asserts:
  - default config → enabled=False → market path
  - pricing / wait / cancel helpers
  - place_limit_buy exists on client; shadow logs limit intent
  - execute_buy with flag OFF never calls place_limit_buy
  - execute_buy with flag ON + mock fill path uses limit (no real API)
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_policy_default_off() -> None:
    from phase6.core.limit_first_buy import policy_from_config
    from phase6.core.runtime_knobs import limit_first_enabled

    p = policy_from_config(None)
    assert p.enabled is False
    assert p.market_fallback is False
    assert p.fill_wait_s == 45.0
    assert p.post_only is True
    assert limit_first_enabled({}) is False
    assert limit_first_enabled({"entry_execution": {"mode": "limit_first"}}) is False
    on = policy_from_config(
        {
            "entry_execution": {
                "mode": "limit_first_v1",
                "limit_first": {"enabled": True, "market_fallback": False},
            }
        }
    )
    assert on.enabled is True
    assert on.market_fallback is False


def test_limit_price_and_base() -> None:
    from phase6.core.limit_first_buy import base_size_from_usd, limit_price_from_refs

    px = limit_price_from_refs(bid=100.0, ask=101.0, last=100.5, price_ref="bid")
    assert px == 100.0
    mid = limit_price_from_refs(bid=100.0, ask=102.0, last=None, price_ref="mid")
    assert mid == 101.0
    b = base_size_from_usd(50.0, 100.0)
    assert b is not None and abs(b - 0.5) < 1e-9


def test_wait_timeout_and_cancel() -> None:
    from phase6.core.limit_first_buy import cancel_and_recheck, wait_for_limit_fill

    class FakeEx:
        def __init__(self) -> None:
            self.n = 0
            self.cancelled = False

        def get_order_fill_details(self, oid: str) -> Dict[str, Any]:
            self.n += 1
            return {"status": "OPEN", "filled_size": 0.0, "average_filled_price": 0.0}

        def cancel_order(self, oid: str) -> bool:
            self.cancelled = True
            return True

    ex = FakeEx()
    # Fake clock: one poll then timeout
    t = {"m": 0.0}

    def mono() -> float:
        return t["m"]

    def sleep(s: float) -> None:
        t["m"] += float(s)

    out = wait_for_limit_fill(
        ex, "oid1", fill_wait_s=5.0, poll_interval_s=2.0, sleep_fn=sleep, monotonic_fn=mono
    )
    assert out["timed_out"] is True
    assert out["polls"] >= 2
    chk = cancel_and_recheck(ex, "oid1")
    assert chk["cancelled"] is True


def test_client_has_place_limit_buy_shadow() -> None:
    from phase6.core.exchange_client import CoinbaseExchangeClient

    ex = CoinbaseExchangeClient(mode="shadow")
    assert hasattr(ex, "place_limit_buy")
    assert hasattr(ex, "get_order")
    assert hasattr(ex, "get_best_bid_ask")
    r = ex.place_limit_buy("BTC-USD", 0.001, 50000.0, post_only=True)
    assert r.get("success") is True
    assert r.get("order_id") == "shadow_limit_buy"
    assert any(x.get("type") == "limit_buy" for x in getattr(ex, "_order_log", []))


def test_executor_default_market_never_limit() -> None:
    """Flag off: live-mode path must call place_market_buy only."""
    from phase6.core.order_executor import OrderExecutor

    calls: List[str] = []

    class Ex:
        shadow_mode = False

        def place_market_buy(self, pair: str, usd: float) -> Dict[str, Any]:
            calls.append("market")
            return {"success": True, "order_id": "m1"}

        def place_limit_buy(self, *a: Any, **k: Any) -> Dict[str, Any]:
            calls.append("limit")
            return {"success": True, "order_id": "l1"}

        def quantize_size(self, pair: str, size: float) -> str:
            return str(size)

    class SL:
        config = {}

        def attach_stop_loss(self, *a: Any, **k: Any) -> bool:
            return False

        def attach_take_profit(self, *a: Any, **k: Any) -> bool:
            return False

    # Patch fill fetch to avoid network
    import phase6.core.order_executor as oe_mod
    import phase6.core.sl_preflight as slp

    def fake_fill(ex: Any, oid: str) -> Dict[str, Any]:
        return {
            "average_filled_price": 100.0,
            "filled_size": 0.5,
            "fill_verified": True,
        }

    orig = slp.fetch_verified_order_fill
    slp.fetch_verified_order_fill = fake_fill  # type: ignore
    try:
        ex = Ex()
        exe = OrderExecutor(exchange=ex, stop_loss_manager=SL(), mode="live")
        r = exe.execute_buy("BTC-USD", 50.0, record_ledger=False, config_dict={})
        assert "limit" not in calls
        assert "market" in calls
        assert r.get("execution_style") == "market_ioc"
        assert r.get("success") is True
    finally:
        slp.fetch_verified_order_fill = orig  # type: ignore


def test_executor_limit_on_uses_limit_skip_unfilled() -> None:
    from phase6.core.order_executor import OrderExecutor

    calls: List[str] = []

    class Ex:
        shadow_mode = False

        def get_best_bid_ask(self, pair: str) -> Dict[str, Any]:
            return {"bid": 100.0, "ask": 101.0, "last": 100.5}

        def place_market_buy(self, pair: str, usd: float) -> Dict[str, Any]:
            calls.append("market")
            return {"success": True, "order_id": "m1"}

        def place_limit_buy(self, pair: str, base: float, px: float, *, post_only: bool = True):
            calls.append("limit")
            return {"success": True, "order_id": "l1", "post_only": post_only}

        def get_order_fill_details(self, oid: str) -> Dict[str, Any]:
            return {"status": "OPEN", "filled_size": 0.0, "average_filled_price": 0.0}

        def cancel_order(self, oid: str) -> bool:
            calls.append("cancel")
            return True

        def quantize_size(self, pair: str, size: float) -> str:
            return f"{size:.8f}"

        def quantize_price(self, pair: str, px: float) -> str:
            return f"{px:.2f}"

    class SL:
        config = {
            "entry_execution": {
                "mode": "limit_first_v1",
                "limit_first": {
                    "enabled": True,
                    "fill_wait_s": 0.01,
                    "poll_interval_s": 0.001,
                    "market_fallback": False,
                },
            }
        }

        def attach_stop_loss(self, *a: Any, **k: Any) -> bool:
            calls.append("sl")
            return True

    import phase6.core.sl_preflight as slp

    orig = slp.fetch_verified_order_fill

    def fake_fill(ex: Any, oid: str) -> Dict[str, Any]:
        return {"average_filled_price": 0.0, "filled_size": 0.0, "fill_verified": False}

    slp.fetch_verified_order_fill = fake_fill  # type: ignore
    try:
        exe = OrderExecutor(exchange=Ex(), stop_loss_manager=SL(), mode="live")
        r = exe.execute_buy(
            "BTC-USD",
            50.0,
            record_ledger=False,
            config_dict=SL.config,
        )
        assert "limit" in calls
        assert "market" not in calls  # skip, no fallback
        assert r.get("success") is False
        assert r.get("error") == "limit_unfilled_skip"
        assert "sl" not in calls  # no SL on empty fill
    finally:
        slp.fetch_verified_order_fill = orig  # type: ignore


def test_executor_elevated_abort() -> None:
    from phase6.core.order_executor import OrderExecutor

    class Ex:
        shadow_mode = False

        def place_limit_buy(self, *a: Any, **k: Any) -> Dict[str, Any]:
            raise AssertionError("should abort before place")

        def place_market_buy(self, *a: Any, **k: Any) -> Dict[str, Any]:
            raise AssertionError("should abort before market")

    cfg = {
        "entry_execution": {
            "mode": "limit_first",
            "limit_first": {"enabled": True, "elevated_tape": "abort"},
        }
    }
    exe = OrderExecutor(exchange=Ex(), stop_loss_manager=None, mode="live")
    r = exe.execute_buy(
        "ETH-USD", 40.0, record_ledger=False, config_dict=cfg, elevated_tape=True
    )
    assert r.get("success") is False
    assert r.get("error") == "elevated_tape_abort"


def test_module_source_default_is_market() -> None:
    """Sanity: execute_buy source still references place_market_buy."""
    from phase6.core import order_executor as m

    src = inspect.getsource(m.OrderExecutor.execute_buy)
    assert "place_market_buy" in src or "_finalize_buy_fill" in src
    assert "limit_first" in src


def main() -> None:
    test_policy_default_off()
    test_limit_price_and_base()
    test_wait_timeout_and_cancel()
    test_client_has_place_limit_buy_shadow()
    test_executor_default_market_never_limit()
    test_executor_limit_on_uses_limit_skip_unfilled()
    test_executor_elevated_abort()
    test_module_source_default_is_market()
    print("PASS test_isolation_limit_first_buy")


if __name__ == "__main__":
    main()
