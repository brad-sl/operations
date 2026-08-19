#!/usr/bin/env python3
"""
STOCH-RSI-PARALLEL trial health check (no_agent friendly).

Exit 0 + quiet if healthy.
Exit 1 + human message if trial integrity is degraded (stdout = alert body).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

TRIAL_ID = "STOCH-RSI-PARALLEL-20260721"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "trials" / f"{TRIAL_ID}.json"
RSI_CACHE = PROJECT_ROOT / "data" / "state" / "rsi_cache.json"
HISTORY = PROJECT_ROOT / "data" / "state" / "rsi_indicator_history.jsonl"

MIN_PAIRS = 9  # full basket is 11; allow brief holes (e.g. OP history warm-up)
MAX_CACHE_AGE_MIN = 45
MIN_STOCH_FRAC = 0.9


def _parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def main() -> int:
    now = datetime.now(timezone.utc)
    issues: list[str] = []
    facts: dict = {"trial_id": TRIAL_ID, "checked_at": now.isoformat()}

    trial = {}
    if STATE_PATH.exists():
        trial = json.loads(STATE_PATH.read_text())
        facts["trial_status"] = trial.get("status")
        # Terminal / unexpected statuses: still measure plumbing, flag status
        if trial.get("status") in ("CLOSED", "KILLED"):
            # Silent OK — trial over; don't spam
            return 0
        if trial.get("status") not in ("RUNNING", "LAUNCHED", "ACTIVE", "DEGRADED", "INSTRUMENTED"):
            issues.append(f"trial status is {trial.get('status')!r} (expected RUNNING/DEGRADED)")
    else:
        issues.append(f"missing trial state {STATE_PATH}")

    if not RSI_CACHE.exists():
        issues.append("rsi_cache.json missing")
        cache = {}
    else:
        cache = json.loads(RSI_CACHE.read_text())
    rsi = cache.get("rsi") or {}
    pairs = list(rsi.keys())
    with_stoch = [
        p for p, v in rsi.items()
        if isinstance(v, dict) and v.get("stoch_k") is not None
    ]
    ts = _parse_ts(str(cache.get("timestamp") or ""))
    age_min = (now - ts).total_seconds() / 60.0 if ts else 9999.0

    facts["pairs"] = len(pairs)
    facts["pairs_with_stoch"] = len(with_stoch)
    facts["cache_age_min"] = round(age_min, 1)
    facts["cache_source_sample"] = None
    if pairs and isinstance(rsi[pairs[0]], dict):
        facts["cache_source_sample"] = rsi[pairs[0]].get("source")
        facts["candle_count_sample"] = rsi[pairs[0]].get("candle_count")

    if len(pairs) < MIN_PAIRS:
        issues.append(f"pair coverage {len(pairs)} < {MIN_PAIRS}")
    if len(with_stoch) < int(MIN_PAIRS * MIN_STOCH_FRAC):
        issues.append(f"stoch coverage {len(with_stoch)}/{len(pairs)} below threshold")
    if age_min > MAX_CACHE_AGE_MIN:
        issues.append(f"rsi_cache age {age_min:.0f}m > {MAX_CACHE_AGE_MIN}m")

    # Recent history lines with stoch
    hist_stoch_lines = 0
    hist_total = 0
    if HISTORY.exists():
        for line in HISTORY.read_text().splitlines()[-50:]:
            line = line.strip()
            if not line:
                continue
            hist_total += 1
            try:
                row = json.loads(line)
            except Exception:
                continue
            pairs_map = row.get("pairs") or {}
            if any(
                isinstance(v, dict) and v.get("stoch_k") is not None
                for v in pairs_map.values()
            ):
                hist_stoch_lines += 1
    facts["history_tail_lines"] = hist_total
    facts["history_tail_with_stoch"] = hist_stoch_lines
    if hist_total >= 5 and hist_stoch_lines < 3:
        issues.append("indicator history tail lacks Stoch (refresher not appending stoch?)")

    ok = not issues
    # Stale open (past final_at) before apply so it counts as a fail
    if STATE_PATH.exists():
        try:
            from phase6.research.trial_cycle import scan_stale

            stale = scan_stale(grace_hours=48.0)
            mine = [s for s in stale if s.get("trial_id") == TRIAL_ID]
            if mine:
                issues.append(f"stale_open: {mine[0].get('reason')}")
                facts["stale"] = mine[0]
                ok = False
        except Exception as e:
            facts["stale_scan_error"] = str(e)

    # Product-loop persistence: consecutive fails → DEGRADED → KILLED
    if STATE_PATH.exists():
        try:
            from phase6.research.trial_cycle import apply_health_result

            kill_n = int((trial or {}).get("kill_after_consecutive_health_fails") or 3)
            updated = apply_health_result(
                TRIAL_ID, ok=ok, issues=issues, facts=facts, kill_after_consecutive=kill_n
            )
            facts["trial_status_after"] = updated.get("status")
            facts["consecutive_health_fails"] = updated.get("consecutive_health_fails")
        except Exception as e:
            # Fallback write if trial_cycle import fails
            issues.append(f"trial_cycle apply failed: {e}")
            ok = False
            trial["last_health"] = {
                "at": now.isoformat(),
                "ok": ok,
                "facts": facts,
                "issues": issues,
            }
            STATE_PATH.write_text(json.dumps(trial, indent=2) + "\n")

    if ok:
        # Silent success for no_agent crons (empty stdout = no Telegram spam)
        return 0

    print(f"STOCH TRIAL HEALTH FAIL — {TRIAL_ID}")
    print(json.dumps(facts, indent=2))
    print("Issues:")
    for i in issues:
        print(f"  - {i}")
    print(
        "Fix: run `python3 /home/brad/projects/crypto-trading-bot/scripts/refresh_rsi_prices.py` "
        "via hermes wrapper `~/.hermes/scripts/refresh_rsi_prices.py` (must stay thin wrapper)."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
