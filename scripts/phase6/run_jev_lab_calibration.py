#!/usr/bin/env python3
"""Jev L4 calibration rollup — measure-only.

  python3 scripts/phase6/run_jev_lab_calibration.py
  python3 scripts/phase6/run_jev_lab_calibration.py --lookback-days 7 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase6.core.jev_lab_calibration import CalibrationConfig, run_calibration, telegram_summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Jev lab L4 calibration (measure-only)")
    ap.add_argument("--lookback-days", type=float, default=7.0)
    ap.add_argument("--min-n", type=int, default=20, help="Min n_ok before any non-N claim")
    ap.add_argument("--crumbs", type=Path, default=None)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--no-refresh-ohlcv", action="store_true")
    ap.add_argument("--force-ohlcv-refresh", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--tg", action="store_true", help="Print short telegram line")
    args = ap.parse_args()

    cfg = CalibrationConfig(
        lookback_days=float(args.lookback_days),
        min_n_claim=int(args.min_n),
        write=not args.no_write,
        refresh_ohlcv=not args.no_refresh_ohlcv,
        force_ohlcv_refresh=bool(args.force_ohlcv_refresh),
    )
    if args.crumbs is not None:
        cfg.crumbs_path = Path(args.crumbs)

    summary = run_calibration(cfg)
    if args.tg:
        print(telegram_summary(summary))
    elif args.json:
        # drop large sample for stdout
        out = dict(summary)
        out.pop("rows_sample", None)
        print(json.dumps(out, indent=2))
    else:
        print(summary.get("plain_english") or json.dumps(summary, indent=2)[:2000])
        print(f"wrote={cfg.latest_path if cfg.write else 'no-write'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
