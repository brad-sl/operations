#!/usr/bin/env python3
"""Isolation: ANALYST-005/007 sl_preflight + coordinator order_id wiring."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.sl_preflight import (
    settlement_poll_params,
    quantize_stop_bundle,
    sanitize_reattach_order_id,
    resolve_stop_calc_base,
    ensure_stop_below_market,
)


class _Ex:
    def get_product_metadata(self, pair):
        return {"price_increment": 0.01, "base_increment": 0.0001}

    def quantize_price(self, pair, price):
        from decimal import Decimal, ROUND_DOWN

        return str(Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def test_settlement_params():
    p = settlement_poll_params("SOL-USD", order_id="ord-1", risk_level="LOW")
    assert p["timeout"] == 20.0 and p["order_id"] == "ord-1"
    p2 = settlement_poll_params("BTC-USD", risk_level="LOW")
    assert p2["timeout"] == 2.5
    print("[ANALYST-005] settlement_poll_params OK")


def test_quantize_stop_bundle():
    ex = _Ex()
    stop, limit, _, _ = quantize_stop_bundle(ex, "SOL-USD", 100.0, 97.0, 96.5)
    assert stop < 100.0 and limit < stop
    print("[ANALYST-007] quantize_stop_bundle OK")


def test_sanitize_stale_reattach_order_id():
    class _Client:
        def get_order_fill_details(self, order_id):
            return {"filled_size": 0, "status": None}

    assert sanitize_reattach_order_id(_Client(), "OP-USD", "4d0bc7f7-stale") is None
    assert sanitize_reattach_order_id(_Client(), "OP-USD", None) is None

    class _Filled:
        def get_order_fill_details(self, order_id):
            return {"filled_size": 1.0, "status": "FILLED"}

    assert sanitize_reattach_order_id(_Filled(), "OP-USD", "ord") is None
    print("[SL-REATTACH] sanitize_reattach_order_id OK")


def test_anchor_rebase_stale_entry():
    base, reason = resolve_stop_calc_base("SOL-USD", 82.0, 141.0, 82.5)
    assert reason == "market_rebase" and abs(base - 82.5) < 0.01
    ex = _Ex()
    stop, limit = ensure_stop_below_market(ex, "SOL-USD", 136.0, 135.0, 82.5, 0.03)
    assert stop < 82.5 and limit < stop
    print("[SL-ANCHOR-REBASE] stale entry OK")


def test_manager_sanitizes_filled_order_id_before_attach():
    """Stale filled buy order_id must not reach settlement poll (integration wiring)."""
    poll_calls = []

    class _Ex:
        def get_product_metadata(self, pair):
            return {"price_increment": 0.01, "base_increment": 0.0001}

        def quantize_price(self, pair, price):
            return str(round(float(price), 2))

        def get_price(self, pair):
            return 100.0

        def get_order_fill_details(self, order_id):
            return {"filled_size": 1.0, "status": "FILLED"}

        def poll_for_settlement(self, pair, timeout=5.0, order_id=None):
            poll_calls.append({"order_id": order_id, "timeout": timeout})
            return True

        def get_crypto_available(self, asset):
            return 1.0

        def quantize_size(self, pair, size):
            return float(size)

        def place_stop_limit_sell(self, **kwargs):
            return True

    from phase6.core.stop_loss_manager import StopLossManager

    mgr = StopLossManager(_Ex(), {"risk_management": {}}, mode="live")
    ok = mgr.attach_stop_loss("BTC-USD", 100.0, 0.5, order_id="filled-buy-oid")
    assert ok is True
    assert not any(c.get("order_id") == "filled-buy-oid" for c in poll_calls)
    print("[SL-MANAGER] sanitize before poll OK")


def test_place_stop_limit_sell_no_nested_settlement_poll():
    """place_stop_limit_sell must not call poll_for_settlement (ENG-S3-02)."""
    from phase6.core.exchange_client import CoinbaseExchangeClient

    polls = []

    class _Real:
        def _request(self, method, path, body=None):
            return {"success": True, "success_response": {"order_id": "sl-1"}}

    c = CoinbaseExchangeClient(mode="live")
    c.real_client = _Real()  # type: ignore[assignment]
    c.poll_for_settlement = lambda *a, **k: polls.append(1) or True
    ok = c.place_stop_limit_sell("BTC-USD", 0.01, 50000.0, 49500.0)
    assert ok is True
    assert polls == [], "place_stop_limit_sell must not poll_for_settlement"
    print("[ENG-S3-02c] place_stop_limit_sell no nested poll — OK")


if __name__ == "__main__":
    test_settlement_params()
    test_quantize_stop_bundle()
    test_sanitize_stale_reattach_order_id()
    test_anchor_rebase_stale_entry()
    test_manager_sanitizes_filled_order_id_before_attach()
    test_place_stop_limit_sell_no_nested_settlement_poll()
    print("[SL PREFLIGHT ISOLATION] PASSED")