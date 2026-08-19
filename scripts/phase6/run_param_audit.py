#!/usr/bin/env python3
"""P6-PARAM-AUDIT CLI — parameter confidence vs exchange-verified fills."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.param_audit import run_param_audit, resolve_account_id_from_exchange
from phase6.core.exchange_client import CoinbaseExchangeClient
from phase6.core.trading_log_store import migrate_legacy_jsonl_to_account_store


def main() -> int:
    p = argparse.ArgumentParser(description="Audit verified fills against Phase 6 config parameters")
    p.add_argument("--account-id", default=None, help="Override account partition (default: portfolio UUID or env)")
    p.add_argument("--no-migrate", action="store_true", help="Skip legacy JSONL → account verified store migration")
    p.add_argument("--migrate-only", action="store_true", help="Only migrate legacy verified rows")
    args = p.parse_args()

    account_id = args.account_id
    if not account_id:
        try:
            ex = CoinbaseExchangeClient(mode="live")
            account_id = resolve_account_id_from_exchange(ex)
        except Exception:
            account_id = None

    if args.migrate_only:
        result = migrate_legacy_jsonl_to_account_store(account_id)
        print(json.dumps(result, indent=2))
        return 0

    result = run_param_audit(
        account_id,
        migrate_legacy=not args.no_migrate,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())