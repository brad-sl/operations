#!/usr/bin/env python3
"""Isolation: CR-03 must not cancel a full post-buy stop and rearm free-dust.

LINK 2026-09-19: post-buy SL ~1.95 @ 12.089 → CR-03 canceled → avail=0.04 →
micro stop 0.03 filled + naked bag until dust sweep.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.sl_preflight import (  # noqa: E402
    extract_stop_base_size_from_order,
    open_stop_covers_position,
    resolve_sl_attach_size,
)
from phase6.core.stop_loss_coordinator import StopLossCoordinator  # noqa: E402


class TestCr03NoDustReattach(unittest.TestCase):
    def test_extract_base_size_nested_oc(self) -> None:
        order = {
            "order_id": "s1",
            "order_configuration": {
                "stop_limit_stop_limit_gtc": {
                    "base_size": "1.95",
                    "stop_price": "12.089",
                }
            },
        }
        self.assertAlmostEqual(extract_stop_base_size_from_order(order), 1.95)

    def test_open_stop_covers_full_bag(self) -> None:
        ex = MagicMock()
        ex.get_open_stop_orders.return_value = [
            {
                "order_id": "good-sl",
                "base_size": 1.95,
                "stop_price": 12.089,
            }
        ]
        cov = open_stop_covers_position(ex, "LINK-USD", 1.99, min_cover_frac=0.90)
        self.assertTrue(cov["covers"])
        self.assertAlmostEqual(cov["covered_size"], 1.95)

    def test_open_stop_under_covers_dust(self) -> None:
        ex = MagicMock()
        ex.get_open_stop_orders.return_value = [
            {"order_id": "dust-sl", "base_size": 0.03, "stop_price": 12.089}
        ]
        cov = open_stop_covers_position(ex, "LINK-USD", 1.99, min_cover_frac=0.90)
        self.assertFalse(cov["covers"])

    def test_resolve_refuses_avail_dust_vs_bag(self) -> None:
        ex = MagicMock()
        ex.get_crypto_available.return_value = 0.04
        ex.get_holdings_verified.return_value = {"positions": {"LINK": 1.99}}
        ex.quantize_size.side_effect = lambda p, q: float(q)
        size, meta = resolve_sl_attach_size(ex, "LINK-USD", 1.99, safety_ratio=0.98)
        self.assertEqual(size, 0.0)
        self.assertTrue(meta.get("refused_dust_attach"))
        self.assertEqual(meta.get("skip_reason"), "avail_dust_vs_bag")

    def test_resolve_still_caps_normal_avail(self) -> None:
        """Healthy free balance still caps to avail * safety_ratio."""
        ex = MagicMock()
        ex.get_crypto_available.return_value = 1.99
        ex.get_holdings_verified.return_value = {"positions": {"LINK": 1.99}}
        ex.quantize_size.side_effect = lambda p, q: float(q)
        size, meta = resolve_sl_attach_size(ex, "LINK-USD", 1.99, safety_ratio=0.98)
        self.assertAlmostEqual(size, 1.99 * 0.98, places=6)
        self.assertTrue(meta.get("capped"))
        self.assertFalse(meta.get("refused_dust_attach"))

    def test_reattach_skips_when_already_covered(self) -> None:
        ex = MagicMock()
        ex.get_open_stop_orders.return_value = [
            {
                "order_id": "post-buy-sl",
                "base_size": 1.95,
                "stop_price": 12.089,
                "order_configuration": {
                    "stop_limit_stop_limit_gtc": {"base_size": "1.95", "stop_price": "12.089"}
                },
            }
        ]
        ex.cancel_order = MagicMock(return_value=True)
        ex.quantize_size.side_effect = lambda p, q: float(q)

        slm = MagicMock()
        slm.attach_stop_loss = MagicMock(return_value=True)
        slm.mode = "live"
        slm.exchange = ex

        coord = StopLossCoordinator(slm, exchange_client=ex, config={"mode": "live"})
        results = coord.reattach_protective_orders(
            {
                "LINK-USD": {
                    "amount": 1.99,
                    "entry_price": 12.515,
                    "current_price": 12.50,
                }
            }
        )
        self.assertEqual(results["LINK-USD"]["status"], "skipped")
        self.assertEqual(results["LINK-USD"]["reason"], "already_covered")
        slm.attach_stop_loss.assert_not_called()
        ex.cancel_order.assert_not_called()

    def test_reattach_proceeds_when_under_covered(self) -> None:
        """No open stop / dust only → still attempts attach (may fail on size)."""
        ex = MagicMock()
        # First call: cover check (under). Later calls during attach path unused here
        # because slm.attach is mocked.
        ex.get_open_stop_orders.return_value = []
        ex.cancel_order = MagicMock(return_value=True)
        ex.quantize_size.side_effect = lambda p, q: float(q)
        ex.get_crypto_available.return_value = 1.99

        slm = MagicMock()
        slm.attach_stop_loss = MagicMock(return_value=True)
        slm.verify_protective_stop = MagicMock(
            return_value={"verified": True, "status": "ok"}
        )
        slm.mode = "live"
        slm.exchange = ex

        coord = StopLossCoordinator(slm, exchange_client=ex, config={"mode": "live"})
        # Seed ledger-style entry via position dict only
        results = coord.reattach_protective_orders(
            {
                "LINK-USD": {
                    "amount": 1.99,
                    "entry_price": 12.515,
                    "current_price": 12.50,
                }
            }
        )
        self.assertEqual(results["LINK-USD"]["status"], "attached")
        slm.attach_stop_loss.assert_called_once()


if __name__ == "__main__":
    unittest.main()
