#!/usr/bin/env python3
"""CLI: plain-language one-paragraph summaries on selected dose cards (shadow).

Phase 2 after selection is locked. Does not replace live TG dose.
Default dry-run (mock). Pass --live for OpenRouter economical chat.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.daily_dose_jev_ranker import try_held_pairs  # noqa: E402
from phase6.core.daily_dose_novice_summary import (  # noqa: E402
    DEFAULT_MODEL,
    NoviceSummaryConfig,
    summarize_from_edited,
)
from phase6.core.paths import DAILY_DOSE_EDITED  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Daily Dose plain summary (shadow editorial)")
    ap.add_argument("--input", type=Path, default=DAILY_DOSE_EDITED)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--model", default=DEFAULT_MODEL, help="OpenRouter model id")
    ap.add_argument(
        "--live",
        action="store_true",
        help="Call economical LLM via OpenRouter (default is dry-run mock)",
    )
    ap.add_argument("--held", action="store_true", help="Include live held pairs in context")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--print-post", action="store_true", help="Print full post with footer disclaimer")
    args = ap.parse_args()

    cfg = NoviceSummaryConfig(
        model=args.model,
        dry_run=not args.live,
        max_cards=args.top,
    )
    held = try_held_pairs() if args.held else []
    payload = summarize_from_edited(args.input, cfg=cfg, held=held)
    if not payload.get("ok"):
        print(f"PlainSummary FAIL {payload.get('error')}", file=sys.stderr)
        return 2

    ok_n = sum(1 for x in (payload.get("items") or []) if (x.get("summary_meta") or {}).get("ok"))
    print(
        f"PlainSummary OK n={payload.get('n_items')} ok={ok_n} dry={payload.get('dry_run')} "
        f"model={payload.get('model')} → {cfg.latest_path}",
        file=sys.stderr if args.print_post and not args.json else sys.stdout,
    )
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    if args.print_post:
        print(payload.get("post_text") or "")
        return 0
    for i, it in enumerate(payload.get("items") or [], 1):
        print(f"{i}. {it.get('title', '')[:100]}")
        print(f"   {it.get('plain_summary') or it.get('novice_summary', '')}")
        print()
    print(payload.get("disclaimer") or "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
