#!/usr/bin/env python3
"""CLI — Luck ladder R1 knife filter shadow (measure only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.knife_filter_shadow import (  # noqa: E402
    KnifeConfig,
    run_knife_filter_shadow,
    telegram_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Knife filter shadow R1")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--tg", action="store_true", help="print TG one-liner")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--pair", action="append", default=[])
    args = ap.parse_args()
    cfg = KnifeConfig(live_gate=False, paid_x=False)
    summary = run_knife_filter_shadow(
        cfg=cfg,
        pairs=args.pair or None,
        write=not args.no_write,
    )
    if args.tg:
        print(telegram_summary(summary))
    elif args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(summary.get("plain_english") or "")
        table = summary.get("arm_table") or {}
        for arm, t in table.items():
            print(
                f"  {arm}: allow={t.get('n_allow')} sl_rate={t.get('sl_rate')} "
                f"mean_r_net={t.get('mean_r_net')} [{t.get('claim')}]"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
