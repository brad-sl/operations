#!/usr/bin/env python3
"""CLI: trade comparison dig (multipair process scoreboard).

Paper only — no orders, no config writes.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.trade_comparison_standard import (  # noqa: E402
    compare_pairs,
    load_ledger_rows,
    render_markdown_report,
    sensor_preflight_ledger,
    summarize_pair,
)

STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"

DEFAULT_PAIRS = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "DOGE-USD",
    "LINK-USD",
    "AVAX-USD",
    "UNI-USD",
    "ADA-USD",
    "ZEC-USD",
    "STX-USD",
    "NEAR-USD",
    "PENGU-USD",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Trade comparison standard dig (paper)")
    ap.add_argument("--pairs", default=",".join(DEFAULT_PAIRS), help="Comma pairs")
    ap.add_argument("--pair", default="", help="Single pair override")
    ap.add_argument("--sl-cooldown-h", type=float, default=48.0)
    ap.add_argument("--tp-cooldown-h", type=float, default=48.0)
    ap.add_argument("--large-usd", type=float, default=150.0)
    ap.add_argument("--elevated-rsi", type=float, default=55.0)
    ap.add_argument("--out-json", default="")
    ap.add_argument("--out-md", default="")
    args = ap.parse_args(argv)

    pairs = [p.strip() for p in (args.pair or args.pairs).split(",") if p.strip()]
    rows = load_ledger_rows()
    # restrict to requested pairs present in ledger
    present = sorted({str(r.get("pair") or "") for r in rows if r.get("pair")})
    pairs = [p for p in pairs if p in present] or [p for p in pairs]
    # if still empty, use all present non-stable
    if not any(p in present for p in pairs):
        pairs = [p for p in present if p.endswith("-USD") and p not in ("USDC-USD", "USD-USD")]

    pre = sensor_preflight_ledger([r for r in rows if str(r.get("pair") or "") in set(pairs)])
    if not pre.get("ok"):
        payload = {
            "schema": "trade_comparison_standard_v1",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "sensor_preflight": pre,
            "edge_class": pre.get("outcome_class"),
            "note": "Do not score — fix sensor first",
        }
        print(json.dumps(payload, indent=2))
        return 2

    cmp = compare_pairs(
        pairs,
        rows,
        sl_cooldown_h=args.sl_cooldown_h,
        tp_cooldown_h=args.tp_cooldown_h,
        large_usd=args.large_usd,
        elevated_rsi=args.elevated_rsi,
    )
    cmp["sensor_preflight"] = pre

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_json = Path(args.out_json) if args.out_json else STATE / "trade_comparison_dig_latest.json"
    out_md = Path(args.out_md) if args.out_md else REPORTS / f"TRADE_COMPARISON_DIG_{day}.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(cmp, indent=2, default=str) + "\n")
    md = render_markdown_report(cmp, title=f"Trade comparison dig ({day})")
    # LINK deep-link if present
    if "LINK-USD" in pairs:
        link_path = REPORTS / "LINK_TIMING_DIG_2026-09-04.md"
        if link_path.exists():
            md += f"\n## Related pair dig\n\n- LINK detail: `{link_path}`\n"
    out_md.write_text(md)
    # also mirror latest md
    (REPORTS / "TRADE_COMPARISON_DIG_LATEST.md").write_text(md)

    # plain-english stdout
    print("TRADE_COMPARISON_DIG")
    print(f"sensor={pre.get('outcome_class')} pairs={cmp.get('n_pairs')} sum_pnl={cmp.get('realized_pnl_sum')}")
    print(f"leak_totals={cmp.get('leak_totals')}")
    print(f"worst_to_best={cmp.get('pairs_worst_to_best')}")
    print(f"json={out_json}")
    print(f"md={out_md}")
    # top rules
    rules = cmp.get("paper_rules") or []
    print(f"paper_rules_n={len(rules)}")
    for r in rules[:12]:
        print(f"  - {r.get('id')} [{r.get('pair_scope')}] hits={r.get('hits')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
