#!/usr/bin/env python3
"""Isolation: cash/stable BUYs must not consume quality-tryout daily seats."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.regime_cash_policy import (  # noqa: E402
    _is_non_tryout_seat_pair,
    count_new_seat_buys_today,
)


def _buy(pair: str, ts: str, notional: float = 75.0) -> dict:
    return {
        "side": "BUY",
        "pair": pair,
        "timestamp": ts,
        "notional_usd": notional,
        "qty": 1.0,
        "price": notional,
    }


class UsdtNotTryoutSeat(unittest.TestCase):
    def setUp(self) -> None:
        # Day-clear short-circuits count to 0; park it so stable-skip is testable.
        self._clear = ROOT / "data" / "state" / "quality_tryout_day_clear.json"
        self._clear_bak = None
        if self._clear.exists():
            self._clear_bak = self._clear.read_text(encoding="utf-8")
            self._clear.write_text(
                json.dumps({"clear": False, "date": "1970-01-01", "note": "isolation park"}),
                encoding="utf-8",
            )

    def tearDown(self) -> None:
        if self._clear_bak is not None:
            self._clear.write_text(self._clear_bak, encoding="utf-8")

    def test_stable_pair_classifier(self) -> None:
        self.assertTrue(_is_non_tryout_seat_pair("USDT-USD"))
        self.assertTrue(_is_non_tryout_seat_pair("USDT-USDC"))
        self.assertTrue(_is_non_tryout_seat_pair("USDC-USD"))
        self.assertTrue(_is_non_tryout_seat_pair("USD"))
        self.assertFalse(_is_non_tryout_seat_pair("LINK-USD"))
        self.assertFalse(_is_non_tryout_seat_pair("ADA-USD"))
        self.assertFalse(_is_non_tryout_seat_pair("BTC-USD"))

    def test_count_skips_usdt_keeps_crypto(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        ts = f"{today}T12:00:00+00:00"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ledger.jsonl"
            rows = [
                _buy("USDT-USDC", ts, 75.21),
                _buy("USDT-USD", ts, 78.85),
                _buy("LINK-USD", ts, 74.98),
                _buy("ADA-USD", f"{today}T13:00:00+00:00", 75.0),
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            n = count_new_seat_buys_today(ledger_path=path)
            self.assertEqual(n, 2, f"expected LINK+ADA only, got {n}")

    def test_only_stables_zero(self) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        ts = f"{today}T04:00:00+00:00"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ledger.jsonl"
            rows = [
                _buy("USDT-USDC", ts, 75.21),
                _buy("USDT-USD", f"{today}T16:00:00+00:00", 78.85),
            ]
            path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            n = count_new_seat_buys_today(ledger_path=path)
            self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()
