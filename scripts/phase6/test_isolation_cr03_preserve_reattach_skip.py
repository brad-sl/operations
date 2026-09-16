#!/usr/bin/env python3
"""Isolation: CR-03 reattach must skip armed Preserve pairs (no crypto SL replace E1)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import phase6.core.preserve_hold as ph  # noqa: E402
from phase6.core.sl_preflight import cancel_open_stops_for_pair  # noqa: E402
from phase6.core.stop_loss_coordinator import StopLossCoordinator  # noqa: E402
from phase6.core.stop_loss_manager import StopLossManager  # noqa: E402


class TestCr03PreserveReattachSkip(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.state = Path(self._td.name)
        self._orig_state = ph.STATE_PATH
        ph.STATE_PATH = self.state / "st.json"
        st = ph.default_state()
        st.update(
            {
                "armed": True,
                "asset": "PAXG-USD",
                "arm_vwap": 4586.82,
                "e1_order_id": "e1-keep",
                "e1_stop_price": 3119.03,
            }
        )
        ph.save_state(st)

    def tearDown(self) -> None:
        ph.STATE_PATH = self._orig_state
        self._td.cleanup()

    def test_reattach_skips_preserve_pair(self) -> None:
        ex = MagicMock()
        ex.cancel_order = MagicMock(return_value=True)
        ex.get_open_stop_orders.return_value = [
            {"order_id": "e1-keep", "product_id": "PAXG-USD", "stop_price": 3119.03}
        ]
        ex.place_stop_limit_sell = MagicMock(
            return_value={"success": True, "order_id": "crypto-new"}
        )
        ex.quantize_size.side_effect = lambda p, q: q
        ex.quantize_price.side_effect = lambda p, q: str(q)
        ex.get_price.return_value = 4350.0

        slm = StopLossManager(ex, {"risk_management": {}}, mode="live")
        slm.attach_stop_loss = MagicMock(return_value=True)

        coord = StopLossCoordinator(slm, exchange_client=ex, config={})
        results = coord.reattach_protective_orders(
            {
                "PAXG-USD": {
                    "amount": 0.018,
                    "entry_price": 4055.92,
                    "current_price": 4350.0,
                },
                "BTC-USD": {
                    "amount": 0.001,
                    "entry_price": 100000.0,
                    "current_price": 100000.0,
                },
            }
        )
        self.assertEqual(results["PAXG-USD"]["status"], "skipped")
        self.assertEqual(results["PAXG-USD"]["reason"], "preserve_sleeve_e1")
        self.assertIn(
            results["BTC-USD"]["status"],
            ("attached", "failed", "skipped", "error"),
        )
        paxg_calls = [
            c
            for c in slm.attach_stop_loss.call_args_list
            if c.kwargs.get("pair") == "PAXG-USD"
            or (c.args and c.args[0] == "PAXG-USD")
        ]
        self.assertEqual(paxg_calls, [])

    def test_cancel_open_stops_skips_preserve(self) -> None:
        ex = MagicMock()
        ex.get_open_stop_orders.return_value = [
            {"order_id": "e1-keep", "stop_price": 3119.0}
        ]
        ex.cancel_order = MagicMock(return_value=True)
        n = cancel_open_stops_for_pair(ex, "PAXG-USD")
        self.assertEqual(n, 0)
        ex.cancel_order.assert_not_called()

    def test_attach_stop_loss_skips_preserve(self) -> None:
        ex = MagicMock()
        ex.place_stop_limit_sell = MagicMock(
            return_value={"success": True, "order_id": "x"}
        )
        slm = StopLossManager(ex, {"risk_management": {}}, mode="live")
        ok = slm.attach_stop_loss("PAXG-USD", entry_price=4055.0, size=0.018)
        self.assertFalse(ok)
        ex.place_stop_limit_sell.assert_not_called()

    def test_shallow_not_e1_class(self) -> None:
        self.assertTrue(ph.is_e1_class_stop_price(3119.0, 4586.82, -0.32))
        self.assertFalse(ph.is_e1_class_stop_price(3937.60, 4586.82, -0.32))
        st = ph.load_state()
        ex = MagicMock()
        ex.get_open_stop_orders.return_value = [
            {
                "order_id": "crypto-shallow",
                "product_id": "PAXG-USD",
                "stop_price": 3937.60,
            }
        ]
        # force tracked id to shallow for exact path
        st["e1_order_id"] = "crypto-shallow"
        ph.save_state(st)
        cfg = ph.load_preserve_config({"preserve_mode": {"enabled": True}})
        # patch holdings
        orig = ph._holding_qty
        ph._holding_qty = lambda *a, **k: (0.018, 0.018)  # type: ignore
        try:
            h = ph.inspect_e1_health(ex, cfg, st)
        finally:
            ph._holding_qty = orig  # type: ignore
        self.assertFalse(h["e1_open"])
        self.assertTrue(h["naked"])
        self.assertEqual(h.get("match_mode"), "shallow_crypto_only")


if __name__ == "__main__":
    unittest.main()
