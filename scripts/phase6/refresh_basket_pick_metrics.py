#!/usr/bin/env python3
"""Refresh basket pick mark-to-market metrics (1d/3d/7d/14d/30d). Safe, no trading."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from phase6.core.basket_pick_metrics import (  # noqa: E402
    refresh_graduation,
    refresh_open_picks,
    summarize,
)


def main() -> int:
    out = refresh_open_picks()  # marks + graduation
    # If marks path short-circuited somehow, still refresh graduation
    if not out.get("graduation"):
        out["graduation"] = refresh_graduation()
    print(json.dumps(out.get("summary") or summarize(), indent=2))
    print(f"marks_updated={out.get('updated')}")
    g = (out.get("graduation") or {}).get("funnel") or {}
    print(
        "graduation "
        f"seated={g.get('n_seated')} signaled={g.get('n_signaled')} "
        f"filled={g.get('n_filled')} win_seat={g.get('rate_win_given_seat')} "
        f"blocked={g.get('n_blocked_no_fill')}"
    )
    pe = (out.get("graduation") or {}).get("plain_english")
    if pe:
        print(pe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
