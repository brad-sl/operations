#!/usr/bin/env python3
"""CLI: preferred-arm auto membership status / dry / kill helpers.

  python3 scripts/phase6/run_preferred_arm_auto_membership.py
  python3 scripts/phase6/run_preferred_arm_auto_membership.py --dry-from-latest-cf
  python3 scripts/phase6/run_preferred_arm_auto_membership.py --enable
  python3 scripts/phase6/run_preferred_arm_auto_membership.py --disable
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.preferred_arm_auto_membership import (  # noqa: E402
    CRUMBS,
    DECISION,
    KILL,
    RECEIPT,
    load_policy,
    try_auto_from_bundle,
)


def _load(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def main() -> int:
    ap = argparse.ArgumentParser(description="Preferred-arm auto membership controls")
    ap.add_argument("--enable", action="store_true")
    ap.add_argument("--disable", action="store_true")
    ap.add_argument("--kill", action="store_true", help=f"touch {KILL.name}")
    ap.add_argument("--unkill", action="store_true", help=f"remove {KILL.name}")
    ap.add_argument(
        "--dry-from-latest-cf",
        action="store_true",
        help="Re-run auto logic dry against last CF bundle if present in log parse — else run_full propose dry",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.kill:
        KILL.parent.mkdir(parents=True, exist_ok=True)
        KILL.write_text("kill\n")
        print(f"KILL on: {KILL}")
        return 0
    if args.unkill:
        if KILL.exists():
            KILL.unlink()
        print("KILL off")
        return 0

    d = _load(DECISION)
    if args.enable or args.disable:
        pam = d.get("preferred_arm_auto_membership")
        if not isinstance(pam, dict):
            pam = {}
        pam["enabled"] = bool(args.enable)
        pam["max_per_day"] = int(pam.get("max_per_day") or 1)
        pam["note"] = (
            "Preferred-arm auto membership (Brad GO path A). "
            "dual_agree manual. live_membership_swaps stays false."
        )
        d["preferred_arm_auto_membership"] = pam
        DECISION.write_text(json.dumps(d, indent=2, default=str) + "\n")
        print(f"enabled={pam['enabled']}")
        return 0

    policy = load_policy(d)
    receipt = _load(RECEIPT) if RECEIPT.exists() else {}
    out = {
        "policy": policy,
        "kill": KILL.exists(),
        "preferred_arm": d.get("preferred_arm"),
        "live_membership_swaps": d.get("live_membership_swaps"),
        "last_receipt": receipt,
        "crumbs_exists": CRUMBS.exists(),
    }

    if args.dry_from_latest_cf:
        from phase6.core.basket_swap_shadow_cf import run_full

        bundle = run_full(propose=True)
        auto = try_auto_from_bundle(bundle, dry_run=True, brad=d)
        out["dry_auto"] = auto

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print(
            f"preferred_arm_auto enabled={policy.get('enabled')} "
            f"kill={KILL.exists()} arm={d.get('preferred_arm')} "
            f"live_swaps={d.get('live_membership_swaps')} "
            f"max/day={policy.get('max_per_day')}"
        )
        if receipt:
            print(
                f"last: status={receipt.get('status')} "
                f"{receipt.get('remove')}→{receipt.get('add')} "
                f"reason={receipt.get('reason')}"
            )
        if "dry_auto" in out:
            a = out["dry_auto"]
            print(
                f"dry: status={a.get('status')} {a.get('remove')}→{a.get('add')} "
                f"reason={a.get('reason')}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
