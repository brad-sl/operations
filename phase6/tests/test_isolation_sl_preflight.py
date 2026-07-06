#!/usr/bin/env python3
"""Isolation: ANALYST-005/007 sl_preflight + coordinator order_id wiring."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phase6.core.sl_preflight import settlement_poll_params, quantize_stop_bundle


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


if __name__ == "__main__":
    test_settlement_params()
    test_quantize_stop_bundle()
    print("[SL PREFLIGHT ISOLATION] PASSED")