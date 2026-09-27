#!/usr/bin/env python3
"""CLI: deterministic no_agent ops auto-repair (venv wrappers + hung runner).

  .venv/bin/python3 scripts/phase6/run_ops_no_agent_auto_repair.py
  .venv/bin/python3 scripts/phase6/run_ops_no_agent_auto_repair.py --dry-run
  .venv/bin/python3 scripts/phase6/run_ops_no_agent_auto_repair.py --no-hung
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.ops_no_agent_auto_repair import (  # noqa: E402
    KILL,
    run_auto_repair,
)


def main() -> int:
    p = argparse.ArgumentParser(description="No-agent auto-repair for known ops classes")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-hung", action="store_true", help="Skip hung-runner check")
    p.add_argument("--no-verify", action="store_true", help="Skip wrapper smoke after rewrite")
    p.add_argument("--max-repairs", type=int, default=8)
    p.add_argument(
        "--kill",
        action="store_true",
        help=f"Touch kill switch {KILL}",
    )
    p.add_argument(
        "--unkill",
        action="store_true",
        help="Remove kill switch",
    )
    args = p.parse_args()
    if args.kill:
        KILL.parent.mkdir(parents=True, exist_ok=True)
        KILL.write_text("kill\n", encoding="utf-8")
        print(json.dumps({"kill": True, "path": str(KILL)}))
        return 0
    if args.unkill:
        if KILL.exists():
            KILL.unlink()
        print(json.dumps({"unkill": True}))
        return 0
    payload = run_auto_repair(
        dry_run=bool(args.dry_run),
        include_hung=not bool(args.no_hung),
        verify=not bool(args.no_verify),
        max_repairs=int(args.max_repairs),
    )
    print(json.dumps(payload, indent=2))
    failed = int((payload.get("summary") or {}).get("failed") or 0)
    return 1 if failed and not args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
