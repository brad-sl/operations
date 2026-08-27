#!/usr/bin/env python3
"""Isolation: protected_market_exit cancel→poll→sell→reattach SSOT."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails = []

    from phase6.core.protected_market_exit import (
        cancel_stops_and_resolve_base,
        protected_market_exit,
        reattach_stop_after_exit,
    )

    # --- no exchange ---
    r = protected_market_exit(None, "BTC-USD", frac=0.5)
    if r.get("error") != "no_exchange_or_pair":
        fails.append(f"no_exchange expected: {r}")
    else:
        print("no_exchange OK")

    # --- cancel then sell order + lag fallback ---
    cancel_order = []
    sell_order = []

    def _cancel(ex, pair):
        cancel_order.append(("cancel", pair))
        return 1

    def _sell(pair, qty):
        sell_order.append(("sell", pair, qty, list(cancel_order)))
        return {"success": True, "order_id": "oid-pe"}

    ex = MagicMock()
    # free dust after cancel → should fall back to qty_full_hint
    ex.get_crypto_available.return_value = 0.0001
    ex.quantize_size.side_effect = lambda p, q: float(q)
    ex.place_market_sell.side_effect = _sell
    ex.get_order_fill_details.return_value = {
        "average_filled_price": 80000.0,
        "filled_size": 0.003,
    }
    ex.get_price.return_value = 80000.0

    with patch(
        "phase6.core.sl_preflight.cancel_open_stops_for_pair", side_effect=_cancel
    ), patch(
        "phase6.core.sl_preflight.poll_available_after_cancel", return_value=True
    ), patch(
        "phase6.core.protected_market_exit.reattach_stop_after_exit",
        return_value={"ok": True, "size": 0.003, "action": "reattach"},
    ), patch(
        "phase6.core.trade_ledger.TradeLedger"
    ) as TL:
        TL.return_value.log_trade = MagicMock()
        pe = protected_market_exit(
            ex,
            "BTC-USD",
            frac=0.5,
            qty_full_hint=0.006,
            entry_price=78600.0,
            mark_price=80000.0,
            reason="lifecycle_dual_peak:test",
            signal_source="lifecycle_dual_peak",
            ledger=True,
            reattach_sl=True,
        )
        if not cancel_order:
            fails.append("cancel never called")
        elif not sell_order:
            fails.append(f"sell never called pe={pe}")
        elif not sell_order[0][3]:
            fails.append("sell before cancel")
        elif not pe.get("success"):
            fails.append(f"expected success pe={pe}")
        elif not pe.get("used_hint_fallback"):
            fails.append(f"expected qty_full fallback when free dust: {pe}")
        elif abs(float(pe.get("qty") or 0) - 0.003) > 1e-9:
            fails.append(f"expected half of 0.006=0.003 got qty={pe.get('qty')}")
        elif not pe.get("sl_reattach", {}).get("ok"):
            fails.append(f"expected reattach ok: {pe}")
        else:
            print("cancel_before_sell + lag_fallback OK")

    # --- sell fail after cancel → reattach ---
    ex2 = MagicMock()
    ex2.get_crypto_available.return_value = 0.01
    ex2.quantize_size.side_effect = lambda p, q: float(q)
    ex2.place_market_sell.return_value = {"success": False, "error": "INSUFFICIENT_FUND"}
    reattach_calls = []

    def _reattach(*a, **k):
        reattach_calls.append(k)
        return {"ok": True, "action": "reattach", "size": 0.01}

    with patch(
        "phase6.core.sl_preflight.cancel_open_stops_for_pair", return_value=1
    ), patch(
        "phase6.core.sl_preflight.poll_available_after_cancel", return_value=True
    ), patch(
        "phase6.core.protected_market_exit.reattach_stop_after_exit",
        side_effect=_reattach,
    ):
        pe2 = protected_market_exit(
            ex2,
            "ETH-USD",
            frac=0.5,
            qty_full_hint=0.01,
            entry_price=3000.0,
            reattach_sl=True,
            ledger=False,
        )
        if pe2.get("success"):
            fails.append(f"fail path should not succeed: {pe2}")
        elif not reattach_calls:
            fails.append("sell fail must reattach SL")
        elif not pe2.get("sl_reattach_after_fail", {}).get("ok"):
            fails.append(f"missing sl_reattach_after_fail: {pe2}")
        else:
            print("fail_after_cancel_reattach OK")

    # --- dry_run ---
    with patch(
        "phase6.core.sl_preflight.cancel_open_stops_for_pair", return_value=0
    ), patch(
        "phase6.core.sl_preflight.poll_available_after_cancel", return_value=True
    ):
        ex3 = MagicMock()
        ex3.get_crypto_available.return_value = 1.0
        ex3.quantize_size.side_effect = lambda p, q: float(q)
        pe3 = protected_market_exit(ex3, "SOL-USD", frac=1.0, dry_run=True, ledger=False)
        if not (pe3.get("success") and pe3.get("note") == "dry_run_no_order"):
            fails.append(f"dry_run: {pe3}")
        elif ex3.place_market_sell.called:
            fails.append("dry_run must not sell")
        else:
            print("dry_run OK")

    # --- resolve base helper ---
    with patch(
        "phase6.core.sl_preflight.cancel_open_stops_for_pair", return_value=2
    ), patch(
        "phase6.core.sl_preflight.poll_available_after_cancel", return_value=True
    ):
        ex4 = MagicMock()
        ex4.get_crypto_available.return_value = 5.0
        res = cancel_stops_and_resolve_base(ex4, "LINK-USD", qty_full_hint=5.0)
        if int(res.get("cancelled") or 0) != 2 or float(res.get("base_qty") or 0) != 5.0:
            fails.append(f"resolve base: {res}")
        else:
            print("cancel_stops_and_resolve_base OK")

    # --- reattach wrapper entry ---
    r0 = reattach_stop_after_exit(None, "X-USD", entry_price=1.0)
    if r0.get("error") != "no_exchange_or_pair":
        fails.append(f"reattach no_ex: {r0}")
    else:
        print("reattach_stop_after_exit no_ex OK")

    print("\n==== RESULTS ====")
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
