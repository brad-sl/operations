#!/usr/bin/env python3
"""CLI: P2 promote + graduation chart (measure-only)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.promote_graduation_chart import build_chart, short_board  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", action="store_true", help="print full JSON")
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--no-crumb", action="store_true", help="skip daily crumb append")
    args = p.parse_args(argv)

    payload = build_chart(
        write=not args.no_write,
        append_history=not args.no_crumb and not args.no_write,
    )
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(short_board(payload))
        if payload.get("wrote"):
            print("wrote", payload["wrote"].get("json"))
            print("wrote", payload["wrote"].get("md"))
            for k, v in (payload.get("charts") or {}).items():
                print("chart", k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
