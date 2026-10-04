#!/usr/bin/env python3
"""Isolation: stamp_sell_pnl fills null SELL pnl from entry/exit/qty (W-EJECT-PNL-STAMP)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    fails = []
    from phase6.core.trade_ledger import stamp_sell_pnl

    # scale-window style eject: prices present, pnl missing
    row = {
        "pair": "LINK-USD",
        "side": "SELL",
        "qty": 1.79,
        "entry_price": 13.921,
        "exit_price": 14.10,
        "reason": "tryout_scale_window_eject",
    }
    out = stamp_sell_pnl(dict(row))
    exp = round((14.10 - 13.921) * 1.79, 6)
    if out.get("pnl") is None:
        fails.append(f"pnl still null: {out}")
    elif abs(float(out["pnl"]) - exp) > 1e-6:
        fails.append(f"pnl wrong got={out.get('pnl')} exp={exp}")
    elif out.get("pnl_stamp") != "entry_exit_qty_gross":
        fails.append(f"stamp tag: {out.get('pnl_stamp')}")
    elif out.get("pnl_usd") is None or out.get("realized_pnl") is None:
        fails.append(f"aliases missing: {out}")
    else:
        print(f"eject_gross OK pnl={out['pnl']} pct={out.get('pnl_pct')}")

    # fees net
    row2 = dict(row)
    row2["fee_usd"] = 0.05
    out2 = stamp_sell_pnl(row2)
    exp2 = round(exp - 0.05, 6)
    if abs(float(out2.get("pnl") or 0) - exp2) > 1e-6:
        fails.append(f"net fees: got={out2.get('pnl')} exp={exp2}")
    elif out2.get("pnl_stamp") != "entry_exit_qty_net_fees":
        fails.append(f"fee stamp: {out2.get('pnl_stamp')}")
    else:
        print(f"eject_net_fees OK pnl={out2['pnl']}")

    # do not overwrite existing pnl
    row3 = dict(row)
    row3["pnl"] = 1.23
    out3 = stamp_sell_pnl(row3)
    if float(out3.get("pnl") or 0) != 1.23:
        fails.append(f"overwrite existing: {out3}")
    else:
        print("preserve_existing OK")

    # BUY untouched
    buy = stamp_sell_pnl({"side": "BUY", "entry_price": 10, "exit_price": 11, "qty": 1})
    if buy.get("pnl") is not None:
        fails.append(f"BUY got pnl: {buy}")
    else:
        print("buy_skip OK")

    # missing exit → mark, no invent
    miss = stamp_sell_pnl(
        {"side": "SELL", "entry_price": 10.0, "qty": 1.0, "reason": "x"}
    )
    if miss.get("pnl") is not None:
        fails.append(f"missing exit invented pnl: {miss}")
    elif miss.get("pnl_stamp") != "missing_entry_exit_or_qty":
        fails.append(f"missing tag: {miss}")
    else:
        print("missing_exit OK")

    # SOL eject fixture from live ledger shape
    sol = stamp_sell_pnl(
        {
            "pair": "SOL-USD",
            "side": "SELL",
            "qty": 0.20862018,
            "entry_price": 119.83,
            "exit_price": 121.61,
            "reason": "tryout_scale_window_eject",
        }
    )
    exp_sol = round((121.61 - 119.83) * 0.20862018, 6)
    if abs(float(sol.get("pnl") or 0) - exp_sol) > 1e-5:
        fails.append(f"sol pnl: {sol.get('pnl')} exp={exp_sol}")
    else:
        print(f"sol_eject_fixture OK pnl={sol['pnl']}")

    print("\n==== RESULTS ====")
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
