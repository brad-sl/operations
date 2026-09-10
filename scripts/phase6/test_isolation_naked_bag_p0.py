#!/usr/bin/env python3
"""Isolation: A1 naked-bag P0 — post-fill available poll + fail-closed flatten."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.stop_loss_manager import StopLossManager  # noqa: E402


class TestNakedBagP0(unittest.TestCase):
    def setUp(self) -> None:
        self.ex = Mock()
        self.cfg = {
            "risk_management": {
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
                "adaptive_sl": False,
                "naked_bag_settle_timeout_s": 0.3,
            }
        }
        self.slm = StopLossManager(self.ex, self.cfg, mode="live", account_context=None)
        # mode=live => shadow_mode False
        self.slm.shadow_mode = False
        self.slm.default_sl_pct = 0.03

        self._patches = [
            patch("phase6.core.sl_risk_scorer.get_sl_risk", return_value={"level": "LOW"}),
            patch(
                "phase6.core.sl_preflight.settlement_poll_params",
                return_value={"timeout": 1.0, "order_id": "buy-1", "mode": "order_fill"},
            ),
            patch("phase6.core.sl_preflight.sanitize_reattach_order_id", side_effect=lambda *a, **k: a[2] if len(a) > 2 else k.get("order_id")),
            patch(
                "phase6.core.sl_preflight.resolve_sl_attach_size",
                side_effect=lambda exchange, pair, size, safety_ratio=0.98: (float(size), {}),
            ),
            patch("phase6.core.sl_preflight.cancel_open_stops_for_pair", return_value=0),
            patch("phase6.core.sl_preflight.poll_available_after_cancel", return_value=0.0),
            patch(
                "phase6.core.sl_preflight.fetch_verified_order_fill",
                return_value={
                    "fill_verified": True,
                    "average_filled_price": 100.0,
                    "filled_size": 1.0,
                },
            ),
            patch(
                "phase6.core.sl_preflight.resolve_stop_calc_base",
                return_value=(100.0, "entry"),
            ),
            patch(
                "phase6.core.sl_preflight.quantize_stop_bundle",
                return_value=(97.0, 96.5, "97.0", "96.5"),
            ),
            patch(
                "phase6.core.sl_preflight.ensure_stop_below_market",
                side_effect=lambda exchange, pair, sp, lp, mp, pct: (sp, lp),
            ),
            patch(
                "phase6.core.sl_floor_ratchet.apply_ratchet_to_stop_bundle",
                side_effect=lambda **kwargs: (
                    kwargs["proposed_stop"],
                    kwargs["proposed_limit"],
                    Mock(applied=False, reasons=[]),
                ),
            ),
            patch("phase6.core.protective_orders_registry.register_protective_order"),
            patch(
                "phase6.core.runner_capital_events._latest_registry_stop_for_pair",
                return_value={},
            ),
        ]
        for p in self._patches:
            p.start()

        self.ex.poll_for_settlement.return_value = {
            "order_id": "buy-1",
            "status": "FILLED",
            "filled_size": 1.0,
            "average_filled_price": 100.0,
        }
        self.ex.get_product_metadata.return_value = {
            "price_increment": 0.0001,
            "base_increment": 0.00000001,
        }
        self.ex.quantize_price.side_effect = lambda pair, price: f"{float(price):.4f}"
        self.ex.quantize_size.side_effect = lambda pair, size: f"{float(size):.8f}"
        self.ex.get_price.return_value = 100.0
        self.ex.place_stop_limit_sell.return_value = {
            "success": True,
            "order_id": "sl-1",
        }

    def tearDown(self) -> None:
        for p in self._patches:
            p.stop()

    def test_available_ok_attaches(self) -> None:
        self.ex.get_crypto_available.return_value = 1.0
        ok = self.slm.attach_stop_loss(
            pair="TEST-USD",
            entry_price=100.0,
            size=1.0,
            order_id="buy-1",
            fresh_buy=True,
        )
        self.assertTrue(ok)
        self.ex.place_stop_limit_sell.assert_called()
        self.ex.place_market_sell.assert_not_called()

    def test_available_delayed_then_attaches(self) -> None:
        # First two polls empty, then settled (timeout 0.3s → several short polls).
        self.ex.get_crypto_available.side_effect = [0.0, 0.0, 1.0] + [1.0] * 20
        ok = self.slm.attach_stop_loss(
            pair="TEST-USD",
            entry_price=100.0,
            size=1.0,
            order_id="buy-1",
            fresh_buy=True,
        )
        self.assertTrue(ok)
        self.assertGreaterEqual(self.ex.get_crypto_available.call_count, 2)
        self.ex.place_stop_limit_sell.assert_called()
        self.ex.place_market_sell.assert_not_called()

    def test_never_available_fail_closed_flatten(self) -> None:
        self.ex.get_crypto_available.return_value = 0.0
        self.ex.place_market_sell.return_value = {"success": True, "order_id": "sell-1"}
        ok = self.slm.attach_stop_loss(
            pair="TEST-USD",
            entry_price=100.0,
            size=1.0,
            order_id="buy-1",
            fresh_buy=True,
        )
        self.assertFalse(ok)
        self.ex.place_market_sell.assert_called()
        self.ex.place_stop_limit_sell.assert_not_called()

    def test_never_available_flatten_fails(self) -> None:
        self.ex.get_crypto_available.return_value = 0.0
        self.ex.place_market_sell.return_value = {"success": False, "error": "API"}
        ok = self.slm.attach_stop_loss(
            pair="TEST-USD",
            entry_price=100.0,
            size=1.0,
            order_id="buy-1",
            fresh_buy=True,
        )
        self.assertFalse(ok)
        self.ex.place_market_sell.assert_called()
        self.ex.place_stop_limit_sell.assert_not_called()


if __name__ == "__main__":
    unittest.main()
