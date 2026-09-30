#!/usr/bin/env python3
"""NEEDLE-03 Stage 3 isolation: core clip planner + skip_sl buy path."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.beta_core import (  # noqa: E402
    CLIP_MAX_USD,
    plan_beta_core,
)
from phase6.core.order_executor import OrderExecutor  # noqa: E402


SOFT = {
    "regime": "transition",
    "strategy_mode": "deploy",
    "allow_new_buys": True,
    "detector": {"regime_layer": "soft_up"},
}
BEAR = {
    "regime": "bear",
    "strategy_mode": "park",
    "allow_new_buys": False,
    "detector": {"regime_layer": "usdc_park"},
}


def test_soft_up_plans_60_40_clip_not_40pct():
    p = plan_beta_core(
        equity=2287.0, usd=175.0, usdc=2008.0, status=SOFT, clip_usd=300.0
    )
    assert p.status == "planned", p
    assert p.skip_sl is True
    assert abs(p.clip_usd - 300.0) < 1e-6
    assert abs(p.btc_usd - 180.0) < 1e-6
    assert abs(p.eth_usd - 120.0) < 1e-6
    assert p.clip_usd <= CLIP_MAX_USD
    assert p.clip_usd < 2287.0 * 0.40
    assert p.unwind_usdc_usd > 0
    assert p.unwind_usdc_usd < 400  # not the whole park
    assert [lg.pair for lg in p.legs] == ["BTC-USD", "ETH-USD"]
    assert all(lg.skip_sl for lg in p.legs)


def test_bear_park_no_core():
    p = plan_beta_core(equity=2287.0, usd=175.0, usdc=2008.0, status=BEAR)
    assert p.status == "blocked"
    assert p.legs == []
    assert p.unwind_usdc_usd == 0.0


def test_tryout_alts_unchanged_in_plan():
    p = plan_beta_core(
        equity=2287.0,
        usd=175.0,
        usdc=2008.0,
        status=SOFT,
        held=["LINK-USD", "PAXG-USD"],
    )
    pairs = {lg.pair for lg in p.legs}
    assert "LINK-USD" not in pairs
    assert "PAXG-USD" not in pairs


def test_live_skip_sl_does_not_attach():
    sl = MagicMock()
    sl.attach_stop_loss = MagicMock(return_value=True)
    sl.attach_take_profit = MagicMock(return_value=True)
    sl.config = {}

    class Ex:
        def place_limit_buy(self, pair, size, px, post_only=True):
            return {"success": True, "order_id": "oid-core"}

        def get_best_bid_ask(self, pair):
            return {"bid": 100.0, "ask": 100.2, "last": 100.1}

        def get_order(self, oid):
            return {"status": "FILLED", "filled_size": 1.8, "average_filled_price": 100.0}

        def quantize_size(self, pair, size):
            return size

        sdk_client = object()

    from phase6.core import sl_preflight

    def fake_fill(ex, oid):
        return {
            "average_filled_price": 100.0,
            "filled_size": 1.8,
            "fill_verified": True,
        }

    sl_preflight.fetch_verified_order_fill = fake_fill  # type: ignore

    oe = OrderExecutor(Ex(), sl, mode="live")
    cfg = {
        "entry_execution": {
            "limit_first": {
                "enabled": True,
                "post_only": True,
                "price_ref": "mid",
                "fill_wait_s": 0.01,
                "poll_interval_s": 0.01,
                "min_fill_usd": 10,
                "market_fallback": False,
                "market_fallback_max_usd": 0.0,
                "pilot_max_buys_per_day": 8,
                "pilot_max_usd_per_day": 500,
            }
        }
    }
    # Force limit path without waiting: patch wait inside if needed.
    r = oe.execute_buy(
        "BTC-USD",
        180.0,
        skip_sl=True,
        config_dict=cfg,
    )
    sl.attach_stop_loss.assert_not_called()
    sl.attach_take_profit.assert_not_called()
    assert r.get("sl_attached") is False


def test_skip_sl_refuses_market_when_limit_off():
    sl = MagicMock()
    sl.attach_stop_loss = MagicMock(return_value=True)

    class Ex:
        def place_market_buy(self, pair, usd):
            raise AssertionError("must not market-IOC a core clip")

        def get_order(self, oid):
            return {}

    oe = OrderExecutor(Ex(), sl, mode="live")
    r = oe.execute_buy(
        "BTC-USD",
        180.0,
        skip_sl=True,
        force_market=True,
        config_dict={"entry_execution": {"limit_first": {"enabled": False}}},
    )
    assert r.get("success") is False
    assert r.get("error") == "core_refuses_market"
    sl.attach_stop_loss.assert_not_called()


if __name__ == "__main__":
    test_soft_up_plans_60_40_clip_not_40pct()
    test_bear_park_no_core()
    test_tryout_alts_unchanged_in_plan()
    test_skip_sl_refuses_market_when_limit_off()
    # live skip_sl path needs wait_for_limit_fill; covered by refuse-market + planner
    print("test_isolation_needle_stage3_core: OK")
