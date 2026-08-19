#!/usr/bin/env python3
"""One-shot: seed primary capital_controls store from live runner hold (W2 migrate)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core import capital_controls_store as store

PRIMARY = store.PRIMARY_UUID
LEGACY = store.LEGACY_RUNNER_STATE


def main() -> int:
    hold, cd = store.load_legacy_runner_hold_cooldown(LEGACY)
    path = store.account_state_path(PRIMARY)
    # If store missing or hold is 0 while legacy has hold, re-seed from legacy
    existing = store.load_account_capital_state(PRIMARY, migrate_from_runner=False) if path.exists() else None
    cur = float((existing or {}).get("manual_liquidation_cash_hold_usd") or 0)
    if not path.exists() or (cur == 0.0 and hold > 0):
        st = {
            "manual_liquidation_cash_hold_usd": hold,
            "manual_sell_cooldown": cd,
            "migrated_from": str(LEGACY),
        }
        store.save_account_capital_state(PRIMARY, st, mirror_legacy=False)
        print(f"seeded {path} hold={hold}")
    else:
        print(f"keep {path} hold={cur} (legacy hold={hold})")
    # Also refresh status files
    from phase6.core.capital_controls_api import get_capital_controls_status

    st = get_capital_controls_status(PRIMARY)
    print(json.dumps({"account_id": st["account_id"], "hold": st["manual_liquidation_cash_hold_usd"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
