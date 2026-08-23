#!/usr/bin/env python3
"""CLI: Tier-1 vol + velocity risk scalar shadow (no live size change)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.vol_risk_scalar_shadow import (  # noqa: E402
    plain_english_summary,
    run_vol_risk_scalar_shadow,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Vol+velocity risk scalar shadow")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--quiet-ok",
        action="store_true",
        help="Silent stdout when ok (still writes state/report)",
    )
    args = p.parse_args()
    out = run_vol_risk_scalar_shadow()
    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("ok") else 1
    text = plain_english_summary(out)
    if args.quiet_ok and out.get("ok"):
        return 0
    print(text)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
