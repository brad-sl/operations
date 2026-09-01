#!/usr/bin/env python3
"""CLI: limit-first Phase D pilot board / kill control."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.limit_first_buy_pilot import (  # noqa: E402
    KILL_SWITCH,
    kill_switch_active,
    load_entry_execution_from_disk,
    load_pilot_state,
    telegram_pilot_summary,
    write_pilot_report,
)
from phase6.core.runtime_knobs import limit_first_enabled  # noqa: E402
from phase6.core.limit_first_buy_pilot import merge_live_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Limit-first Phase D pilot board")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet-ok", action="store_true")
    ap.add_argument("--kill", action="store_true", help="Touch kill switch (force market)")
    ap.add_argument("--unkill", action="store_true", help="Remove kill switch")
    args = ap.parse_args()
    if args.kill:
        KILL_SWITCH.parent.mkdir(parents=True, exist_ok=True)
        KILL_SWITCH.write_text("kill\n")
        print(f"KILL ON → {KILL_SWITCH}")
        write_pilot_report()
        return 0
    if args.unkill:
        if KILL_SWITCH.exists():
            KILL_SWITCH.unlink()
        print("KILL OFF")
        write_pilot_report()
        return 0

    write_pilot_report()
    st = load_pilot_state()
    ee = load_entry_execution_from_disk()
    enabled = limit_first_enabled(merge_live_config({"entry_execution": ee}))
    payload = {
        "enabled": enabled,
        "kill": kill_switch_active(),
        "entry_execution": ee,
        "state": st,
    }
    body = telegram_pilot_summary()
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return 0
    if args.quiet_ok:
        if body:
            print(body)
        return 0
    print(
        body
        or f"limit-first D pilot enabled={enabled} kill={kill_switch_active()} "
        f"attempts={st.get('limit_attempts')} day={st.get('utc_day')}"
    )
    print("report: reports/LIMIT_FIRST_BUY_PILOT_LATEST.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
