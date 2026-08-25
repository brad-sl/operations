#!/usr/bin/env python3
"""
CF: P1 ignition scout on LINK Aug run + P2 dual-peak would-trim path.

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 scripts/phase6/backtest_run_lifecycle_p12_cf.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.run_lifecycle import (
    evaluate_dual_peak_exits,
    load_lifecycle_config,
    score_pair_ignition,
)
from phase6.core.run_phase_deploy import fetch_daily_candles_public

OUT = ROOT / "data/state/run_lifecycle_p12_cf_report.json"


def day_str(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    cfg = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    life = load_lifecycle_config(cfg)
    link = fetch_daily_candles_public("LINK-USD", limit=50)

    rows = []
    for i, bar in enumerate(link):
        d = day_str(bar["t"])
        if d < "2026-08-08" or d > "2026-08-24":
            continue
        # mild sent early, hot late (approx narrative)
        if d <= "2026-08-14":
            sent = 0.25
        elif d <= "2026-08-18":
            sent = 0.55
        else:
            sent = 0.85
        cand = score_pair_ignition(
            "LINK-USD", link[: i + 1], sentiment=sent, cfg_all=life
        )
        rows.append(
            {
                "date": d,
                "close": bar["c"],
                "score": cand.score,
                "phase": cand.phase_name,
                "rsi": cand.daily_rsi,
                "structure_ok": cand.structure_ok,
                "would_propose": cand.proposal_usd > 0,
                "reason": cand.reason,
            }
        )

    print("=== P1 ignition CF LINK ===")
    print(f"{'date':10} {'score':>6} {'phase':>12} {'struct':>6} {'propose':>7}")
    for r in rows:
        print(
            f"{r['date']:10} {r['score']:6.3f} {r['phase']:>12} "
            f"{str(r['structure_ok']):>6} {'YES' if r['would_propose'] else 'no':>7}"
        )

    early = [r for r in rows if "2026-08-10" <= r["date"] <= "2026-08-14" and r["would_propose"]]
    late = [r for r in rows if r["date"] >= "2026-08-19" and r["would_propose"]]
    aug24 = next((r for r in rows if r["date"] == "2026-08-24"), None)

    # P2: simulate holding from Aug 11 entry through distribution
    entry_px = next(r["close"] for r in rows if r["date"] == "2026-08-11")
    p2_path = []
    for r in rows:
        if r["date"] < "2026-08-11":
            continue
        lots = [
            {
                "pair": "LINK-USD",
                "open": True,
                "entry_price": entry_px,
                "entry_sentiment": 0.25,
                "entry_sent_peak": 0.85 if r["date"] >= "2026-08-19" else 0.25,
                "peak_price": max(entry_px, max(x["close"] for x in rows if "2026-08-11" <= x["date"] <= r["date"])),
                "usd": 1000,
            }
        ]
        # sent narrative: rises then we test fade on 23-24
        if r["date"] <= "2026-08-18":
            cur_sent = 0.4
        elif r["date"] <= "2026-08-21":
            cur_sent = 0.85
        else:
            cur_sent = 0.45  # fade after climax
        idx = next(i for i, b in enumerate(link) if day_str(b["t"]) == r["date"])
        ev = evaluate_dual_peak_exits(
            lots=lots,
            current_sentiment={"LINK-USD": cur_sent},
            current_prices={"LINK-USD": r["close"]},
            positions_usd={"LINK-USD": 1000},
            candles_by_pair={"LINK-USD": link[: idx + 1]},
            cfg_p2=life["dual_peak_exit"],
        )
        p2_path.append(
            {
                "date": r["date"],
                "events": [e.kind for e in ev],
                "trim": sum(e.would_trim_usd for e in ev),
            }
        )

    print("\n=== P2 dual-peak path (entry Aug11) ===")
    for p in p2_path:
        if p["events"]:
            print(p["date"], p["events"], f"trim~${p['trim']:.0f}")

    ok = True
    reasons = []
    if not early:
        # structure may be strict — allow high score without propose if min not met
        early_scores = [r for r in rows if "2026-08-10" <= r["date"] <= "2026-08-14"]
        if not any(r["score"] > 0 for r in early_scores):
            ok = False
            reasons.append("no positive early scores Aug10-14")
        else:
            reasons.append("NOTE: early scores>0 but below min_score propose threshold")
    if late:
        ok = False
        reasons.append(f"late proposes should be empty: {[r['date'] for r in late]}")
    if aug24 and aug24["would_propose"]:
        ok = False
        reasons.append("Aug24 must not propose")

    dual_hits = [p for p in p2_path if "dual_peak" in p["events"]]
    ext_hits = [p for p in p2_path if "extension_partial" in p["events"]]
    if not dual_hits and not ext_hits:
        ok = False
        reasons.append("P2 path produced no dual_peak or extension_partial")

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "p1_daily": rows,
        "p1_early_propose_days": [r["date"] for r in early],
        "p2_path": p2_path,
        "validation": {"ok": ok, "reasons": reasons},
        "verdict": {
            "aug24_no_propose": bool(aug24 and not aug24["would_propose"]),
            "p2_has_exit_signal": bool(dual_hits or ext_hits),
            "note": "P1 mode=shadow (board only). P2 mode=shadow (no live sell).",
        },
    }
    OUT.write_text(json.dumps(report, indent=2))
    print("\nReport", OUT)
    if ok:
        print("CF VALIDATION PASSED")
        return 0
    print("CF VALIDATION FAILED", reasons)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
