#!/usr/bin/env python3
"""Rebuild bank/trail CF + Sunday decision packet. Measure-only. No live apply."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.bank_trail_while_green_cf import run_cf  # noqa: E402
from phase6.core.bank_trail_while_green_decision import (  # noqa: E402
    DEFAULT_OUT_JSON,
    evaluate_decision,
    format_tg_card,
    load_decision_cfg,
    write_decision_outputs,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bank/trail Sunday review (measure-only)")
    ap.add_argument("--since", default="2026-08-06T00:00:00+00:00")
    ap.add_argument("--cfg-shadow", default=None)
    ap.add_argument("--cfg-decision", default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--tg-card", action="store_true", help="Print short TG card only")
    ap.add_argument("--load-latest", action="store_true", help="Skip CF rebuild; use latest JSON")
    ap.add_argument("--json-stdout", action="store_true")
    args = ap.parse_args()

    decision_cfg = load_decision_cfg(Path(args.cfg_decision) if args.cfg_decision else None)

    if args.load_latest:
        cf_path = ROOT / "data" / "state" / "bank_trail_while_green_cf_latest.json"
        cf_payload = json.loads(cf_path.read_text(encoding="utf-8"))
    else:
        since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        cfg = Path(args.cfg_shadow) if args.cfg_shadow else None
        cf_payload = run_cf(since=since, cfg_path=cfg, write=not args.no_write)

    shadow_cfg = None
    scp = Path(args.cfg_shadow) if args.cfg_shadow else ROOT / "config" / "bank_trail_while_green_shadow.json"
    if scp.exists():
        shadow_cfg = json.loads(scp.read_text(encoding="utf-8"))

    decision = evaluate_decision(cf_payload, decision_cfg=decision_cfg, shadow_cfg=shadow_cfg)
    decision["cf_report"] = str(ROOT / "reports" / "BANK_TRAIL_WHILE_GREEN_CF_LATEST.md")
    decision["cf_state"] = str(ROOT / "data" / "state" / "bank_trail_while_green_cf_latest.json")

    if not args.no_write:
        paths = write_decision_outputs(decision, cf_summary=cf_payload.get("summary") or {})
        decision["wrote"] = paths
    else:
        # still allow card from memory
        if DEFAULT_OUT_JSON.exists() and args.load_latest:
            pass

    if args.tg_card:
        print(format_tg_card(decision), end="")
        return 0

    # fact-pack header for agent inject (must be non-empty)
    print("BANK_TRAIL_WHILE_GREEN_SUNDAY_REVIEW fact pack ready (measure-only).")
    print(f"VERDICT: {decision.get('verdict')}")
    print(f"PLAIN: {decision.get('plain')}")
    print(f"STATE: {decision.get('wrote', {}).get('json') or DEFAULT_OUT_JSON}")
    print(f"REPORT: {decision.get('wrote', {}).get('md') or ROOT / 'reports/BANK_TRAIL_WHILE_GREEN_SUNDAY_REVIEW_LATEST.md'}")
    print(f"CF_REPORT: {decision.get('cf_report')}")
    print(
        f"n_legs={decision.get('n_legs')} would_arm={decision.get('n_would_arm_legs')} "
        f"winner={decision.get('winner_would_arm_only')} recommend={decision.get('recommend_arm')}"
    )
    fails = decision.get("failures") or []
    print(f"failures: {', '.join(fails) if fails else '(none)'}")
    print(f"next: {decision.get('next_action')}")
    print("Read STATE + REPORT + CF_REPORT. No knobs / no orders / no live_apply flip.")
    print("Letter GO from Brad required before any live gap-fill design.")
    if args.json_stdout:
        print(json.dumps(decision, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
