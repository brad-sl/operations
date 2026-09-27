#!/usr/bin/env python3
"""CLI: pair funnel stage dwell (measure-only).

  python3 scripts/phase6/run_pair_funnel_dwell.py
  python3 scripts/phase6/run_pair_funnel_dwell.py --json
  python3 scripts/phase6/run_pair_funnel_dwell.py --pair LINK-USD
  python3 scripts/phase6/run_pair_funnel_dwell.py --monthly
  python3 scripts/phase6/run_pair_funnel_dwell.py --monthly --json

Stages SSOT: config/pair_funnel_stages.json
Prediction stays OFF until Brad GO + enough closed RTs.
Monthly = Pair × stage visit-count table (long-term data ping).
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
    ap = argparse.ArgumentParser(description="Pair funnel dwell tick (measure-only)")
    ap.add_argument("--json", action="store_true", help="Full JSON payload")
    ap.add_argument("--pair", default="", help="Show one pair profile")
    ap.add_argument("--no-write", action="store_true", help="Dry tick (no disk write)")
    ap.add_argument(
        "--monthly",
        action="store_true",
        help="Emit Pair×stage visit-count monthly summary (TG-friendly)",
    )
    ap.add_argument(
        "--month",
        default="",
        help="Override month key YYYY-MM for --monthly (default: current UTC)",
    )
    args = ap.parse_args()

    from phase6.core.pair_funnel_dwell import (
        build_monthly_summary,
        load_profiles,
        load_stages_config,
        run_tick,
    )

    # Always refresh crumbs before monthly so open ages are current
    out = run_tick(write=not args.no_write)

    if args.monthly:
        mon = build_monthly_summary(
            write=not args.no_write,
            month_key=args.month or None,
        )
        if args.json:
            slim = {
                k: v
                for k, v in mon.items()
                if k not in ("markdown",)  # md is long; table + rows enough
            }
            print(json.dumps(slim, indent=2, default=str))
            return 0
        # stdout = deliverable card (no_agent cron)
        print(mon.get("plain_english") or mon.get("table") or "ok")
        return 0

    if args.pair:
        from phase6.core.pair_funnel_dwell import _norm_pair

        p = _norm_pair(args.pair)
        prof = (load_profiles().get("pairs") or {}).get(p) or {}
        open_rows = [
            o for o in (out.get("open_summary") or []) if o.get("pair") == p
        ]
        packet = {
            "pair": p,
            "open": open_rows[0] if open_rows else None,
            "profile": prof,
            "stages_config": load_stages_config().get("config_path"),
            "predict_enabled": out.get("predict_enabled"),
        }
        print(json.dumps(packet, indent=2, default=str))
        return 0
    if args.json:
        slim = {k: v for k, v in out.items() if k not in ("state", "profiles")}
        slim["profiles_top"] = out.get("top_profiles")
        print(json.dumps(slim, indent=2, default=str))
        return 0
    print(out.get("plain_english") or "ok")
    for o in out.get("open_summary") or []:
        print(f"  open {o.get('pair')} {o.get('stage')} age_h={o.get('age_h')}")
    for r in (out.get("top_profiles") or [])[:8]:
        print(
            f"  prof {r.get('pair')} closed={r.get('closed_rts')} "
            f"tryout_mean_h={r.get('tryout_open_mean_h')} hint={r.get('pattern_hint')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
