#!/usr/bin/env python3
"""Isolation: A2 full episode identity (bag_id across ledger / ratchet / peaks)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestEpisodeIdentityA2(unittest.TestCase):
    def test_make_bag_id_canonical(self) -> None:
        from phase6.core.episode_identity import bag_ids_conflict, make_bag_id

        self.assertEqual(make_bag_id("link-usd", " buy-1 "), "LINK-USD:buy-1")
        self.assertIsNone(make_bag_id("LINK-USD", ""))
        self.assertTrue(bag_ids_conflict("LINK-USD:old", "LINK-USD:new"))
        self.assertFalse(bag_ids_conflict("LINK-USD:old", None))
        self.assertFalse(bag_ids_conflict(None, "LINK-USD:new"))

    def test_ledger_buy_and_sell_carry_bag_id(self) -> None:
        from phase6.core.exchange_fill_reconciler import (
            build_ledger_row_from_market_buy,
            build_ledger_row_from_market_sell,
        )
        from phase6.core.trade_ledger import TradeLedger

        buy_order = {
            "order_id": "buy-abc",
            "product_id": "LINK-USD",
            "side": "BUY",
            "status": "FILLED",
            "order_type": "LIMIT",
            "client_order_id": "phase6-abc",
            "average_filled_price": "12.5",
            "filled_size": "8.0",
        }
        buy = build_ledger_row_from_market_buy(buy_order, exchange=None, backfill=True)
        assert buy is not None
        self.assertEqual(buy["bag_id"], "LINK-USD:buy-abc")
        self.assertEqual(buy["buy_order_id"], "buy-abc")

        with tempfile.TemporaryDirectory() as td:
            tdir = Path(td)
            ledger = TradeLedger(base_dir=tdir)
            # force trades under temp
            ledger.trades_dir = tdir / "trades"
            ledger.trades_dir.mkdir(parents=True, exist_ok=True)
            ledger.jsonl_path = ledger.trades_dir / "phase6_trades.jsonl"
            ledger.log_trade(dict(buy))
            rows = [
                json.loads(l)
                for l in ledger.jsonl_path.read_text().splitlines()
                if l.strip()
            ]
            self.assertEqual(rows[0]["bag_id"], "LINK-USD:buy-abc")

            import phase6.core.protective_orders_registry as reg

            reg_path = tdir / "reg.jsonl"
            with patch.object(reg, "REGISTRY_PATH", reg_path):
                reg.register_protective_order(
                    pair="LINK-USD",
                    sl_order_id="sl-1",
                    entry_price=12.5,
                    qty=8.0,
                    stop_price=12.1,
                    buy_order_id="buy-abc",
                )
                sell_order = {
                    "order_id": "sell-1",
                    "product_id": "LINK-USD",
                    "side": "SELL",
                    "status": "FILLED",
                    "order_type": "MARKET",
                    "order_data_source": "ORDER_DATA_SOURCE_TRADING_PROXY",
                    "average_filled_price": "12.8",
                    "filled_size": "8.0",
                    "created_time": "2026-09-11T20:00:00Z",
                }
                sell = build_ledger_row_from_market_sell(
                    sell_order, exchange=None, ledger=ledger, backfill=True
                )
                assert sell is not None
                self.assertEqual(sell["bag_id"], "LINK-USD:buy-abc")

    def test_ratchet_rejects_mismatched_bag_id(self) -> None:
        from phase6.core.sl_floor_ratchet import (
            apply_ratchet_to_stop_bundle,
            usable_existing_stop_for_ratchet,
        )

        # Same entry px, prior bag stop high — must ignore when bag_ids conflict
        gated = usable_existing_stop_for_ratchet(
            existing_stop=12.228,
            entry=12.55,
            mark=13.0,
            registry_entry=12.55,  # entry matches!
            fresh_buy=False,
            continuous_bag=True,  # would keep without bag_id
            registry_bag_id="LINK-USD:old-buy",
            current_bag_id="LINK-USD:new-buy",
        )
        self.assertIsNone(gated)

        stop, limit, dec = apply_ratchet_to_stop_bundle(
            pair="LINK-USD",
            entry=12.55,
            mark=13.0,
            proposed_stop=12.55 * 0.97,
            proposed_limit=12.55 * 0.97 * 0.995,
            existing_stop=12.228,
            fresh_buy=False,
            continuous_bag=True,
            registry_entry=12.55,
            registry_bag_id="LINK-USD:old-buy",
            current_bag_id="LINK-USD:new-buy",
        )
        # Should not inherit 12.228 floor solely from continuous+entry match
        # (gated to None by bag conflict → uses proposed genesis ~12.1735)
        self.assertAlmostEqual(stop, 12.55 * 0.97, places=5, msg=(stop, dec))

        # Matching bag_ids may keep existing on continuous bag
        stop2, _, dec2 = apply_ratchet_to_stop_bundle(
            pair="LINK-USD",
            entry=12.55,
            mark=13.5,
            proposed_stop=12.55 * 0.97,
            proposed_limit=12.0,
            existing_stop=12.228,
            fresh_buy=False,
            continuous_bag=True,
            registry_entry=12.55,
            registry_bag_id="LINK-USD:same",
            current_bag_id="LINK-USD:same",
        )
        self.assertGreaterEqual(stop2, 12.228 - 1e-6, (stop2, dec2))

    def test_peak_reset_on_bag_id_change_same_entry(self) -> None:
        """UNI-class: same entry px, different bag → must not keep old peak_r."""
        from phase6.core.shadow_tp import PositionMark, sanitize_peak_r_for_lots

        marks = [
            PositionMark(
                pair="UNI-USD",
                usd=80.0,
                qty=17.5,
                mark_px=4.57,
                entry_px=4.57,
                entry_source="ledger_lot",
                r=-0.003,
                bag_id="UNI-USD:new-buy",
            )
        ]
        peak_r = {"UNI-USD": 0.1123}
        peak_lot = {
            "UNI-USD": {
                "entry_px": 4.57,  # SAME entry — old entry_tol alone would keep peak
                "qty": 17.5,
                "bag_id": "UNI-USD:old-buy",
            }
        }
        out_r, out_lot, events = sanitize_peak_r_for_lots(marks, peak_r, peak_lot)
        self.assertLess(out_r["UNI-USD"], 0.01, out_r)
        self.assertEqual(out_lot["UNI-USD"].get("bag_id"), "UNI-USD:new-buy")
        reasons = [e.get("reason") for e in events if e.get("action") == "reset_peak"]
        self.assertIn("bag_id_changed", reasons)

    def test_peak_keeps_same_bag(self) -> None:
        from phase6.core.shadow_tp import PositionMark, sanitize_peak_r_for_lots

        marks = [
            PositionMark(
                pair="SOL-USD",
                usd=100.0,
                qty=0.5,
                mark_px=160.0,
                entry_px=150.0,
                entry_source="ledger_lot",
                r=0.0667,
                bag_id="SOL-USD:b1",
            )
        ]
        peak_r = {"SOL-USD": 0.08}
        peak_lot = {
            "SOL-USD": {"entry_px": 150.0, "qty": 0.5, "bag_id": "SOL-USD:b1"}
        }
        out_r, out_lot, events = sanitize_peak_r_for_lots(marks, peak_r, peak_lot)
        self.assertGreaterEqual(out_r["SOL-USD"], 0.08 - 1e-9)
        resets = [e for e in events if e.get("action") == "reset_peak"]
        self.assertEqual(resets, [])
        self.assertEqual(out_lot["SOL-USD"].get("bag_id"), "SOL-USD:b1")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestEpisodeIdentityA2)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
