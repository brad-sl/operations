#!/usr/bin/env python3
"""Ensure 11/11 basket RSI + sentiment coverage (real data). Run before twice-daily brief or on demand."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv/bin/python3"
if not PY.is_file():
    PY = Path(sys.executable)


def run(rel: str, timeout: int = 240) -> int:
    script = ROOT / rel
    print(f"\n>> {rel}")
    r = subprocess.run([str(PY), str(script)], cwd=str(ROOT), timeout=timeout)
    return r.returncode


def main() -> int:
    steps = [
        ("scripts/refresh_rsi_prices.py", 120),
        ("fetch_x_sentiment.py", 240),
        ("phase6/scripts/refresh_sentiment.py", 240),
    ]
    for rel, to in steps:
        rc = run(rel, to)
        if rc != 0:
            print(f"WARN: {rel} exit {rc}")

    sys.path.insert(0, str(ROOT))
    from phase6.core.basket_signal_coverage import (
        assess_pair_signal_coverage,
        persist_sentiment_observations_to_db,
    )

    persist_sentiment_observations_to_db()
    rep = assess_pair_signal_coverage()
    print(f"\n=== Coverage: {rep['full_count']}/{rep['basket_size']} FULL ===")
    for pair, row in rep["per_pair"].items():
        if row["status"] != "FULL":
            print(f"  {pair}: {row['status']} posts={row['x_posts']} sent={row['sentiment_effective']:.4f}")
    if rep["complete"]:
        print("PASS: 11/11 full basket signal coverage.")
        return 0
    print(f"Partial: missing sentiment fetch for {rep['missing_sentiment_fetch']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())