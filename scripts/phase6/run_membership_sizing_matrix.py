#!/usr/bin/env python3
"""CLI: membership sizing matrix SSOT.

  python scripts/phase6/run_membership_sizing_matrix.py
  python scripts/phase6/run_membership_sizing_matrix.py --pair BTC-USD
  python scripts/phase6/run_membership_sizing_matrix.py --filter block_max
  python scripts/phase6/run_membership_sizing_matrix.py --filter inconsistent
  python scripts/phase6/run_membership_sizing_matrix.py --check
  python scripts/phase6/run_membership_sizing_matrix.py --regime
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Membership × sizing matrix SSOT")
    ap.add_argument("--pair", help="Single pair card (e.g. BTC-USD)")
    ap.add_argument(
        "--filter",
        action="append",
        default=[],
        help="block_max | inconsistent | class=X | role=X | scale_path=X | basket",
    )
    ap.add_argument("--check", action="store_true", help="Exit 1 if inconsistencies")
    ap.add_argument("--regime", action="store_true", help="Print regime sheet only")
    ap.add_argument("--json", action="store_true", help="Full JSON out")
    ap.add_argument("--no-persist", action="store_true")
    ap.add_argument("--telegram", action="store_true", help="Plain one-liner for TG")
    args = ap.parse_args()

    from phase6.core.membership_sizing_matrix import (
        build_matrix,
        filter_rows,
        pair_card,
        load_regime_sheet,
    )

    if args.regime:
        sheet = load_regime_sheet()
        print(json.dumps(sheet, indent=2, default=str))
        return 0

    m = build_matrix(persist=not args.no_persist)

    if args.pair:
        card = pair_card(args.pair, m)
        if args.json:
            print(json.dumps(card, indent=2, default=str))
        else:
            print(card.get("plain_english") or json.dumps(card, default=str))
            if card.get("found") and not args.telegram:
                r = card.get("row") or {}
                print(
                    f"  law: eject={r.get('can_eject_scale_window')} "
                    f"ff_haircut={r.get('first_fill_haircut')} "
                    f"remove={r.get('membership_remove')} "
                    f"pyramid={r.get('pyramid_allowed')}"
                )
                if r.get("budgets"):
                    print(f"  budgets: {json.dumps(r.get('budgets'), default=str)}")
                if r.get("inconsistencies"):
                    print(f"  INCONSISTENT: {r.get('inconsistencies')}")
        if args.check and (card.get("row") or {}).get("inconsistencies"):
            return 1
        return 0

    # filters
    kw: dict = {}
    for f in args.filter or []:
        f = str(f).strip().lower()
        if f in ("block_max", "block-max"):
            kw["block_max"] = True
        elif f in ("inconsistent", "inconsistencies"):
            kw["inconsistent_only"] = True
        elif f in ("basket", "in_basket"):
            kw["in_basket"] = True
        elif f.startswith("class="):
            kw["class_"] = f.split("=", 1)[1]
        elif f.startswith("role="):
            kw["role"] = f.split("=", 1)[1]
        elif f.startswith("scale_path=") or f.startswith("scale="):
            kw["scale_path"] = f.split("=", 1)[1]
        else:
            print(f"unknown filter: {f}", file=sys.stderr)

    rows = filter_rows(m, **kw) if kw else list(m.get("rows") or [])

    if args.telegram:
        print(m.get("plain_english") or "")
        n = m.get("counts") or {}
        if n.get("n_inconsistent"):
            print(f"INCONSISTENT n={n.get('n_inconsistent')}")
        return 1 if (args.check and n.get("n_inconsistent")) else 0

    if args.json:
        out = dict(m)
        out["rows"] = rows
        print(json.dumps(out, indent=2, default=str))
    else:
        print(m.get("plain_english") or "")
        print(
            f"{'pair':12} {'class':16} {'role':16} {'scale':16} "
            f"{'held':>8} {'max_add':>8} block_reason"
        )
        for r in rows:
            print(
                f"{str(r.get('pair')):12} {str(r.get('class')):16} "
                f"{str(r.get('role')):16} {str(r.get('scale_path_law')):16} "
                f"{float(r.get('held_usd') or 0):8.2f} "
                f"{str(r.get('max_add_usd') if r.get('max_add_usd') is not None else '—'):>8} "
                f"{r.get('block_reason')}"
                + (
                    f"  !!{r.get('inconsistencies')}"
                    if r.get("inconsistencies")
                    else ""
                )
            )
        print()
        rs = m.get("regime_sheet") or {}
        live = rs.get("live_add_risk") or {}
        print(
            f"regime_live={rs.get('live_regime')} pyramid={live.get('allow_pyramid')} "
            f"k_profit={live.get('k_profit')} h_add={live.get('h_add')} "
            f"target_w={live.get('target_pair_weight')} cash_frac={live.get('cash_frac')}"
        )
        if m.get("inconsistencies"):
            print(f"inconsistencies: {json.dumps(m.get('inconsistencies'), default=str)}")

    n_bad = len(m.get("inconsistencies") or [])
    if args.check and n_bad:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
