#!/usr/bin/env python3
"""CLI: TryoutSeatBuyAction — one-pair $shell tryout (default dry_run).

  python3 scripts/phase6/run_tryout_seat_buy.py --pair ETH-USD --sentiment 0.35 --rsi 32
  python3 scripts/phase6/run_tryout_seat_buy.py --pair ETH-USD --sentiment 0.35 --rsi 32 --go
      # still dry unless --live (money = --go AND --live)
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.domain.actions.tryout_seat_buy import (  # noqa: E402
    TryoutSeatBuyAction,
    handler_from_action,
)
from phase6.domain.dispatcher import ActionDispatcher  # noqa: E402
from phase6.domain.types import ActionRequest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="TryoutSeatBuyAction (dry default, one pair)")
    ap.add_argument("--pair", required=True)
    ap.add_argument("--sentiment", type=float, required=True, help="Gate-grade eng (paid X / latch)")
    ap.add_argument("--rsi", type=float, default=None)
    ap.add_argument("--eng-source", default="cli")
    ap.add_argument("--shell-usd", type=float, default=None)
    ap.add_argument("--max-shell-usd", type=float, default=75.0)
    ap.add_argument("--tenant", default="default")
    ap.add_argument("--go", action="store_true", help="GO intent (still dry without --live)")
    ap.add_argument(
        "--live",
        action="store_true",
        help="Allow money path when combined with --go (dry_run=False)",
    )
    ap.add_argument("--idempotency-key", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    money = bool(args.go) and bool(args.live)
    key = args.idempotency_key or (
        f"tryout-seat-{args.pair}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid.uuid4().hex[:8]}"
    )
    params = {
        "pair": args.pair,
        "sentiment": float(args.sentiment),
        "rsi": float(args.rsi) if args.rsi is not None else None,
        "eng_source": args.eng_source,
        "max_shell_usd": float(args.max_shell_usd),
        "dry_run": not money,
        "go": bool(args.go),
    }
    if args.shell_usd is not None:
        params["shell_usd"] = float(args.shell_usd)

    req = ActionRequest(
        action="tryout_seat_buy",
        tenant_id=args.tenant,
        idempotency_key=key,
        params=params,
        actor="cli",
    )
    d = ActionDispatcher()
    d.register("tryout_seat_buy", handler_from_action(TryoutSeatBuyAction()))
    r = d.dispatch(req)
    # Count live fills toward approval → autonomous ladder
    if money:
        try:
            from phase6.core.rsi_event_tryout_seat_policy import record_manual_go

            arts = r.artifacts or {}
            plan = arts.get("plan") or {}
            if str(plan.get("status") or "") == "filled":
                record_manual_go(
                    pair=str(plan.get("pair") or args.pair),
                    shell_usd=float(plan.get("shell_usd") or 0),
                    receipt_id=str(key),
                    note="cli_live_fill",
                    source="cli_go_live",
                )
        except Exception as e:
            print(f"[warn] record_manual_go: {e}", file=sys.stderr)
    if args.json:
        print(json.dumps(r.to_dict(), indent=2, default=str))
    else:
        arts = r.artifacts or {}
        plan = arts.get("plan") or {}
        print(
            f"ok={r.ok} status={r.status} pair={plan.get('pair')} "
            f"shell=${plan.get('shell_usd')} applied={arts.get('applied')} "
            f"money={arts.get('money')}"
        )
        print("reasons:", "; ".join(r.reasons[:6]))
        print("effects:", "; ".join(r.effects[:8]))
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
