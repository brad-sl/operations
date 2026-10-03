#!/usr/bin/env python3
"""CLI: Membership Manager (self-regulating bag seats).

  python3 scripts/phase6/run_membership_manager.py
  python3 scripts/phase6/run_membership_manager.py --dry-run
  python3 scripts/phase6/run_membership_manager.py --status
  python3 scripts/phase6/run_membership_manager.py --telegram
  python3 scripts/phase6/run_membership_manager.py --enable
  python3 scripts/phase6/run_membership_manager.py --disable
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.membership_manager import (  # noqa: E402
    CFG_PATH,
    KILL,
    RECEIPT,
    dashboard_payload,
    load_config,
    run_membership_manager,
    telegram_notice,
    _load_json,
    _write_json,
)


def _set_enabled(on: bool) -> dict:
    from datetime import datetime, timezone

    cfg = _load_json(CFG_PATH, {}) or {}
    if not isinstance(cfg, dict):
        cfg = {}
    cfg["enabled"] = bool(on)
    cfg["live_apply"] = bool(on)
    cfg["updated"] = datetime.now(timezone.utc).isoformat()
    _write_json(CFG_PATH, cfg)
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser(description="Membership Manager — self-regulating seats")
    ap.add_argument("--dry-run", action="store_true", help="Propose only; no promote apply")
    ap.add_argument("--status", action="store_true", help="Print dashboard payload + latest receipt")
    ap.add_argument("--telegram", action="store_true", help="Print TG notice line if any")
    ap.add_argument("--enable", action="store_true", help="Set config enabled+live_apply true")
    ap.add_argument("--disable", action="store_true", help="Set config enabled false")
    ap.add_argument("--json", action="store_true", help="Machine JSON only")
    args = ap.parse_args()

    if args.enable:
        cfg = _set_enabled(True)
        print(json.dumps({"ok": True, "enabled": True, "cfg": cfg.get("enabled")}, indent=2))
        return 0
    if args.disable:
        cfg = _set_enabled(False)
        print(json.dumps({"ok": True, "enabled": False}, indent=2))
        return 0

    if args.status:
        payload = dashboard_payload()
        receipt = _load_json(RECEIPT, {}) or {}
        out = {"dashboard": payload, "receipt": receipt, "kill_exists": KILL.exists()}
        print(json.dumps(out, indent=2, default=str))
        return 0

    result = run_membership_manager(dry_run=bool(args.dry_run))
    print(json.dumps(result, indent=2, default=str))
    if args.telegram:
        msg = telegram_notice(result)
        print("---TELEGRAM---")
        if msg:
            print(msg.replace("\\n", "\n"))
        else:
            print("(silent)")
    if result.get("status") == "error":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
