#!/usr/bin/env python3
"""Tryout scale-window board + operator eject.

  # board only
  PYTHONPATH=. python scripts/phase6/run_tryout_scale_window.py

  # dry eject named pairs
  PYTHONPATH=. python scripts/phase6/run_tryout_scale_window.py --eject TIA-USD LINK-USD --dry-run

  # live eject (Brad GO)
  PYTHONPATH=. python scripts/phase6/run_tryout_scale_window.py --eject TIA-USD LINK-USD --go --no-dry-run

Auto live_apply stays OFF in config until separate arm GO.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Tryout scale-window evaluate / eject")
    ap.add_argument("--eject", nargs="*", default=None, help="Pairs to eject (full shell)")
    ap.add_argument("--dry-run", action="store_true", default=None)
    ap.add_argument("--no-dry-run", action="store_true")
    ap.add_argument("--go", action="store_true", help="Operator intent for live money")
    ap.add_argument(
        "--require-would-eject",
        action="store_true",
        help="Skip pairs board does not mark window_closed",
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--telegram-board",
        action="store_true",
        help="Quiet TG body only if n_would_eject>0 (12h fp dedupe; never money)",
    )
    ap.add_argument(
        "--force-telegram",
        action="store_true",
        help="Bypass 12h fingerprint dedupe for board card (still measure-only)",
    )
    args = ap.parse_args()

    from phase6.core import tryout_scale_window as tw

    if args.telegram_board:
        body = tw.board_telegram_summary(force=bool(args.force_telegram))
        if body:
            print(body)
        return 0

    if args.eject is not None:
        dry = True
        if args.no_dry_run:
            dry = False
        elif args.dry_run:
            dry = True
        if not dry and not args.go:
            print("REFUSE live eject without --go (pass --dry-run to plan)")
            return 2
        pairs = list(args.eject) if args.eject else []
        if not pairs:
            board = tw.evaluate_open_tryouts()
            pairs = list(board.get("would_eject_pairs") or [])
            if not pairs:
                print("No would_eject pairs and none named.")
                if args.json:
                    print(json.dumps(board, indent=2, default=str))
                return 0
        summary = tw.eject_pairs(
            pairs,
            dry_run=dry,
            go=bool(args.go),
            require_would_eject=bool(args.require_would_eject),
        )
        if args.json:
            print(json.dumps(summary, indent=2, default=str))
        else:
            print(
                f"eject dry={summary.get('dry_run')} go={summary.get('go')} "
                f"n_ok={summary.get('n_ok')}/{summary.get('n')}"
            )
            for r in summary.get("results") or []:
                j = r.get("judgment") or {}
                pe = r.get("protected_exit") or {}
                print(
                    f"  {r.get('pair')} ok={r.get('success')} "
                    f"path={j.get('scale_path')} status={j.get('status')} "
                    f"oid={pe.get('order_id') or r.get('error') or r.get('skipped')}"
                )
                if j.get("reasons"):
                    print(f"    reasons: {j.get('reasons')}")
            print(f"receipt: {tw.EJECT_RESULT_PATH}")
        return 0 if int(summary.get("n_ok") or 0) == int(summary.get("n") or 0) else 1

    board = tw.evaluate_open_tryouts()
    if args.json:
        print(json.dumps(board, indent=2, default=str))
    else:
        print(board.get("plain"))
        for r in board.get("rows") or []:
            print(
                f"  {r.get('pair')} path={r.get('scale_path')} status={r.get('status')} "
                f"phase={r.get('phase')} hold_h={r.get('hold_hours')} "
                f"would_eject={r.get('would_eject')} reasons={r.get('reasons')}"
            )
        print(f"board: {tw.LATEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
