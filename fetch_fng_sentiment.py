#!/usr/bin/env python3
"""Fetch Alternative.me Crypto Fear & Greed → data/state/fng_cache.json ($0)."""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from phase6.core.paths import FNG_CACHE, PROJECT_ROOT, STATE_DIR

URL = "https://api.alternative.me/fng/?limit=1"
UA = "phase6-free-sentiment/1.0 (+local research)"


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode())
    row = (raw.get("data") or [None])[0]
    if not row:
        print("FNG: empty response", file=sys.stderr)
        return 1
    value = float(row["value"])
    # map 0..100 → [-1, +1]
    score = (value - 50.0) / 50.0
    score = max(-1.0, min(1.0, score))
    damped = 0.15 * score  # Tier C only — never dominate
    out = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "alternative.me",
        "value": value,
        "classification": row.get("value_classification"),
        "fng_timestamp": row.get("timestamp"),
        "score_raw": round(score, 4),
        "score_damped": round(damped, 4),
        "meta": {"url": URL},
    }
    FNG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    FNG_CACHE.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(
        f"FNG OK value={value} ({out['classification']}) "
        f"raw={out['score_raw']} damped={out['score_damped']} → {FNG_CACHE}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
