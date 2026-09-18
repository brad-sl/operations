#!/usr/bin/env python3
"""One-call dry_run BookRebalanceAction against live snapshot.

Default: dry_run, refuse new tryout seats, no orders, no X spend.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.domain.actions.book_rebalance import BookRebalanceAction, handler_from_action
from phase6.domain.dispatcher import ActionDispatcher
from phase6.domain.types import ActionRequest


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--tenant", default="default")
    p.add_argument("--legs-file", default="", help="Optional JSON list of plan legs")
    p.add_argument("--json-legs", default="")
    p.add_argument("--live-state", default="")
    p.add_argument("--idempotency-key", default="")
    p.add_argument("--go", action="store_true", help="Mark non-dry_run (still no orders in v1)")
    args = p.parse_args()

    params = {
        "dry_run": not args.go,
        "allow_new_tryout_seats": False,
        "spend_x_for_candidates": False,
        "reattach_protectives": True,
    }
    if args.live_state:
        params["live_state_path"] = args.live_state
    if args.json_legs:
        params["plan_legs"] = json.loads(args.json_legs)
    elif args.legs_file:
        params["plan_legs"] = json.loads(Path(args.legs_file).read_text(encoding="utf-8"))

    key = args.idempotency_key or (
        f"book_rebalance-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    )
    req = ActionRequest(
        action="book_rebalance",
        tenant_id=args.tenant,
        idempotency_key=key,
        params=params,
        actor="cli",
    )
    d = ActionDispatcher()
    d.register("book_rebalance", handler_from_action(BookRebalanceAction()))
    r = d.dispatch(req)
    print(json.dumps(r.to_dict(), indent=2))
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
