#!/usr/bin/env python3
"""CLI: regime climate vs weather measure board (no live knobs)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.regime_climate_weather import (  # noqa: E402
    LATEST_JSON,
    REPORT_MD,
    build_board,
    telegram_summary,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Climate/weather multi-horizon + dwell (measure-only)")
    ap.add_argument("--json", action="store_true", help="print full JSON")
    ap.add_argument("--tg", action="store_true", help="print short telegram card")
    ap.add_argument("--no-write", action="store_true", help="do not write state/report")
    args = ap.parse_args()

    board = build_board(write=not args.no_write)
    if args.tg:
        print(telegram_summary(board))
    elif args.json:
        print(json.dumps(board, indent=2, default=str))
    else:
        print(board.get("plain_english") or "")
        print(f"json={LATEST_JSON}")
        print(f"md={REPORT_MD}")
        snap = board.get("snapshot") or {}
        print("climate", (snap.get("climate") or {}).get("regime"), (snap.get("climate") or {}).get("btc_return_pct"))
        print("horizons", snap.get("weather_horizons"))
        print("structure", snap.get("weather_structure"))
        dwell = board.get("dwell") or {}
        if dwell.get("ok"):
            print("dwell_coarse", dwell.get("coarse_episodes"))
    return 0 if board.get("snapshot", {}).get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
