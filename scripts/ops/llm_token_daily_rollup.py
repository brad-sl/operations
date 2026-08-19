#!/usr/bin/env python3
"""
Daily LLM token rollup from ~/.hermes/logs/agent.log* (Phase1 cost telemetry).

Appends one JSON line per day to data/state/llm_token_daily.jsonl
and prints a one-line summary.

Usage:
  python3 scripts/ops/llm_token_daily_rollup.py
  python3 scripts/ops/llm_token_daily_rollup.py --days 14
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/brad/projects/crypto-trading-bot")
OUT = ROOT / "data/state/llm_token_daily.jsonl"
LATEST = ROOT / "data/state/llm_token_daily_latest.json"
LOG_DIR = Path.home() / ".hermes" / "logs"

PAT = re.compile(
    r"API call #\d+: model=(\S+) provider=(\S+) in=(\d+) out=(\d+) total=(\d+)"
)
DATE_PAT = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    by_day_model: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "total": 0})
    )
    files = sorted(LOG_DIR.glob("agent.log*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[:8]:
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        cur_day = None
        for line in text.splitlines():
            m = DATE_PAT.match(line)
            if m:
                cur_day = m.group(1)
            m = PAT.search(line)
            if not m or not cur_day:
                continue
            model, prov, inn, out, tot = (
                m.group(1),
                m.group(2),
                int(m.group(3)),
                int(m.group(4)),
                int(m.group(5)),
            )
            key = f"{prov}|{model}"
            b = by_day_model[cur_day][key]
            b["calls"] += 1
            b["in"] += inn
            b["out"] += out
            b["total"] += tot

    days = sorted(by_day_model.keys())[-args.days :]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # rewrite file for window (idempotent)
    lines_out = []
    for d in days:
        models = by_day_model[d]
        total = sum(v["total"] for v in models.values())
        calls = sum(v["calls"] for v in models.values())
        row = {
            "date": d,
            "calls": calls,
            "total_tokens": total,
            "models": {k: v for k, v in models.items()},
            "rolled_at": datetime.now(timezone.utc).isoformat(),
        }
        lines_out.append(json.dumps(row, separators=(",", ":")))
    OUT.write_text("\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")

    latest = {}
    if days:
        d = days[-1]
        models = by_day_model[d]
        latest = {
            "date": d,
            "calls": sum(v["calls"] for v in models.values()),
            "total_tokens": sum(v["total"] for v in models.values()),
            "top_model": max(models.items(), key=lambda x: x[1]["total"])[0] if models else None,
            "window_days": len(days),
            "path": str(OUT),
        }
    LATEST.write_text(json.dumps(latest, indent=2), encoding="utf-8")
    if latest:
        mt = latest["total_tokens"] / 1e6
        print(
            f"LLM_TOKENS {latest['date']}: calls={latest['calls']} total≈{mt:.2f}M "
            f"top={latest.get('top_model')} (window {len(days)}d → {OUT})"
        )
    else:
        print("LLM_TOKENS: no data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
