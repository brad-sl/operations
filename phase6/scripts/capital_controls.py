#!/usr/bin/env python3
"""
Capital / manual-trade user controls (CLI today, dashboard UI later).

Examples:
  python -m phase6.scripts.capital_controls status
  python -m phase6.scripts.capital_controls status --account-id 3176ac3f-...
  python -m phase6.scripts.capital_controls clear-cash-hold
  python -m phase6.scripts.capital_controls clear-cooldown --all
  python -m phase6.scripts.capital_controls clear-cooldown --pair OP-USD
  python -m phase6.scripts.capital_controls request-clear-cash-hold
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.capital_controls import (
    FLAG_CLEAR_CASH_HOLD,
    FLAG_CLEAR_COOLDOWN,
    JSON_CLEAR_COOLDOWN,
    CONTROLS_STATUS_JSON,
    clear_manual_cash_hold,
    clear_manual_sell_cooldown,
    get_controls_status_for_ui,
    write_controls_status,
)
from phase6.core.capital_controls_api import (
    api_clear_cash_hold,
    api_clear_cooldown,
    api_request_clear_cash_hold,
    api_request_clear_cooldown,
    get_capital_controls_status,
)
from phase6.core.capital_controls_store import primary_account_id


class _OfflineRunner:
    def __init__(self, state_file: str, account_id: str):
        self.state_file = state_file
        self.account_id = account_id
        self._manual_liquidation_cash_hold_usd = 0.0
        self._manual_sell_cooldown = {}


def _default_state() -> str:
    return str(ROOT / "data/state/phase6_runner_state.json")


def cmd_status(args: argparse.Namespace) -> int:
    aid = args.account_id or primary_account_id()
    status = get_capital_controls_status(aid)
    print(json.dumps(status, indent=2))
    if args.write_file:
        CONTROLS_STATUS_JSON.parent.mkdir(parents=True, exist_ok=True)
        CONTROLS_STATUS_JSON.write_text(json.dumps(status, indent=2))
    return 0


def cmd_clear_cash_hold(args: argparse.Namespace) -> int:
    aid = args.account_id or primary_account_id()
    result = api_clear_cash_hold(aid, source="cli_immediate")
    print(json.dumps(result, indent=2))
    return 0


def cmd_clear_cooldown(args: argparse.Namespace) -> int:
    aid = args.account_id or primary_account_id()
    if args.all:
        result = api_clear_cooldown(aid, clear_all=True, source="cli_immediate")
    elif args.pair:
        result = api_clear_cooldown(aid, pairs=args.pair, source="cli_immediate")
    else:
        print("Specify --all or --pair", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def cmd_request_clear_cash_hold(args: argparse.Namespace) -> int:
    aid = args.account_id or primary_account_id()
    result = api_request_clear_cash_hold(aid)
    print(json.dumps(result, indent=2))
    return 0


def cmd_request_clear_cooldown(args: argparse.Namespace) -> int:
    aid = args.account_id or primary_account_id()
    if args.all:
        result = api_request_clear_cooldown(aid, clear_all=True)
    elif args.pair:
        result = api_request_clear_cooldown(aid, pairs=args.pair)
    else:
        print("Specify --all or --pair", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 6 capital / manual-trade controls")
    p.add_argument("--state-file", default=_default_state(), help="phase6_runner_state.json path")
    p.add_argument(
        "--account-id",
        default=None,
        help="Portfolio / trader account id (default: env COINBASE_PORTFOLIO_UUID or 'default')",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="Show hold + cooldown (UI read model)")
    s.add_argument("--write-file", action="store_true", help="Also write capital_user_controls.json")
    s.set_defaults(func=cmd_status)

    sub.add_parser("clear-cash-hold", help="Clear hold immediately (state edit)").set_defaults(
        func=cmd_clear_cash_hold
    )

    cc = sub.add_parser("clear-cooldown", help="Clear rebuy cooldown immediately")
    cc.add_argument("--all", action="store_true")
    cc.add_argument("--pair", action="append")
    cc.set_defaults(func=cmd_clear_cooldown)

    sub.add_parser(
        "request-clear-cash-hold",
        help="Touch flag for live runner to clear on next cycle",
    ).set_defaults(func=cmd_request_clear_cash_hold)

    rc = sub.add_parser("request-clear-cooldown", help="Touch flag / JSON for live runner")
    rc.add_argument("--all", action="store_true")
    rc.add_argument("--pair", action="append")
    rc.set_defaults(func=cmd_request_clear_cooldown)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
