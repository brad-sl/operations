#!/usr/bin/env python3
"""Thin CLI ingress for phase6 domain actions.

Default dry_run. No live orders from this entrypoint in v1.

Examples:
  python3 -m phase6.ingress.cli action book_rebalance
  python3 -m phase6.ingress.cli action book_rebalance --json-legs '[{"pair":"ADA-USD","action":"BUY","usd":75,"quality_tryout":true}]'
  python3 scripts/phase6/run_book_rebalance_action.py
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.domain.actions.book_rebalance import BookRebalanceAction, handler_from_action
from phase6.domain.dispatcher import ActionDispatcher, make_noop_handler
from phase6.domain.types import ActionRequest


def _build_dispatcher() -> ActionDispatcher:
    d = ActionDispatcher()
    d.register("noop", make_noop_handler())
    d.register("book_rebalance", handler_from_action(BookRebalanceAction()))
    return d


def cmd_action(args: argparse.Namespace) -> int:
    params: Dict[str, Any] = {
        "dry_run": not bool(args.go),
        "allow_new_tryout_seats": bool(args.allow_new_tryout_seats),
        "reattach_protectives": not bool(args.skip_protectives),
        "spend_x_for_candidates": False,
    }
    if args.live_state:
        params["live_state_path"] = args.live_state
    if args.json_legs:
        params["plan_legs"] = json.loads(args.json_legs)
    elif args.legs_file:
        params["plan_legs"] = json.loads(Path(args.legs_file).read_text(encoding="utf-8"))

    key = args.idempotency_key or f"cli-{args.action}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    req = ActionRequest(
        action=args.action,  # type: ignore[arg-type]
        tenant_id=args.tenant,
        idempotency_key=key,
        params=params,
        actor=args.actor,
    )
    disp = _build_dispatcher()
    receipt = disp.dispatch(req)
    print(json.dumps(receipt.to_dict(), indent=2))
    return 0 if receipt.ok else 1


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase6 action CLI (dry_run default)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("action", help="Dispatch a named action")
    a.add_argument(
        "action",
        choices=["book_rebalance", "noop"],
        help="Action name",
    )
    a.add_argument("--tenant", default="default")
    a.add_argument("--actor", default="cli")
    a.add_argument("--idempotency-key", default="")
    a.add_argument(
        "--go",
        action="store_true",
        help="Leave dry_run (v1 still places no orders; only flips receipt flag)",
    )
    a.add_argument(
        "--allow-new-tryout-seats",
        action="store_true",
        help="DANGEROUS — override refuse filter (tests/debug only)",
    )
    a.add_argument("--skip-protectives", action="store_true")
    a.add_argument("--live-state", default="")
    a.add_argument("--json-legs", default="", help="JSON array of plan legs")
    a.add_argument("--legs-file", default="")
    a.set_defaults(func=cmd_action)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
