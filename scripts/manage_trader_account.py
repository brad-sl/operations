#!/usr/bin/env python3
"""CLI for per-account trader options (config/trader_accounts.json)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase6.core.trader_account_config import (
    TRADER_ACCOUNTS_PATH,
    live_usdc_park_settings,
    resolve_account_config,
    set_live_usdc_park_enabled,
)
from phase6.core.usdc_park_transitions import get_transition_status


def cmd_show(account_id: str) -> int:
    cfg = resolve_account_config(account_id)
    print(json.dumps(cfg, indent=2))
    return 0


def cmd_park_toggle(account_id: str, enabled: bool) -> int:
    park = set_live_usdc_park_enabled(account_id, enabled)
    print(f"account={account_id} live_usdc_park.enabled={park.get('enabled')}")
    print(f"saved → {TRADER_ACCOUNTS_PATH}")
    return 0


def cmd_park_status(account_id: str) -> int:
    print(json.dumps(get_transition_status(account_id), indent=2))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Trader account config")
    sub = p.add_subparsers(dest="cmd", required=True)
    show = sub.add_parser("show")
    show.add_argument("account_id")
    park = sub.add_parser("usdc-park")
    park.add_argument("account_id")
    park.add_argument("on", choices=["on", "off"])
    pst = sub.add_parser("park-status")
    pst.add_argument("account_id")

    args = p.parse_args()
    if args.cmd == "show":
        return cmd_show(args.account_id)
    if args.cmd == "usdc-park":
        return cmd_park_toggle(args.account_id, args.on == "on")
    if args.cmd == "park-status":
        return cmd_park_status(args.account_id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())