#!/usr/bin/env python3
"""
Counterfactual: run-phase deploy gate on LINK Aug 2026 run + optional ledger BUYs.

Validates P0 thesis: late-run NEW buys blocked; early ignition/trend allowed.

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 scripts/phase6/backtest_run_phase_deploy_cf.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.run_phase_deploy import (
    apply_run_phase_buy_gate,
    classify_run_phase,
    fetch_daily_candles_public,
    load_run_phase_config,
)

OUT = ROOT / "data" / "state" / "run_phase_deploy_cf_report.json"
CFG = ROOT / "config" / "trading_config_phase6.json"


def day_str(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    cfg = load_run_phase_config(json.loads(CFG.read_text()))
    link = fetch_daily_candles_public("LINK-USD", limit=50)

    rows: List[Dict[str, Any]] = []
    for i, bar in enumerate(link):
        d = day_str(bar["t"])
        if d < "2026-08-08" or d > "2026-08-24":
            continue
        snap = classify_run_phase(link, pair="LINK-USD", cfg=cfg, as_of_index=i)
        # hypothetical recovery-style full wallet
        g_new = apply_run_phase_buy_gate(
            "LINK-USD", 1925.0, snap, current_pair_usd=0.0, cfg=cfg
        )
        g_cap = apply_run_phase_buy_gate(
            "LINK-USD", 150.0, snap, current_pair_usd=0.0, cfg=cfg
        )
        rows.append(
            {
                "date": d,
                "close": round(bar["c"], 4),
                "phase": snap.phase,
                "phase_name": snap.phase_name,
                "daily_rsi": None if snap.daily_rsi is None else round(snap.daily_rsi, 2),
                "pct_from_low_10d": None
                if snap.pct_from_low_10d is None
                else round(snap.pct_from_low_10d, 4),
                "vol_ratio": None if snap.vol_ratio is None else round(snap.vol_ratio, 2),
                "days_since_ignition": snap.days_since_ignition,
                "off_peak_pct": None
                if snap.off_peak_pct is None
                else round(snap.off_peak_pct, 4),
                "new_buy_1925_allowed": not g_new.blocked and g_new.final_usd > 0,
                "new_buy_1925_final": g_new.final_usd,
                "new_buy_150_allowed": not g_cap.blocked and g_cap.final_usd > 0,
                "notes": snap.notes,
            }
        )

    print("=== LINK run-phase CF (daily) ===")
    print(
        f"{'date':10} {'close':>8} {'phase':>12} {'rsi':>6} {'pct10':>7} {'buy1925':>8} {'buy150':>7}"
    )
    for r in rows:
        print(
            f"{r['date']:10} {r['close']:8.4f} {r['phase_name']:>12} "
            f"{str(r['daily_rsi']):>6} {str(r['pct_from_low_10d']):>7} "
            f"{'ALLOW' if r['new_buy_1925_allowed'] else 'BLOCK':>8} "
            f"{'ALLOW' if r['new_buy_150_allowed'] else 'BLOCK':>7}"
        )

    by_date = {r["date"]: r for r in rows}
    # Validation gates
    ok = True
    reasons = []

    # Aug 24 poster child — must BLOCK
    r24 = by_date.get("2026-08-24")
    if not r24:
        ok = False
        reasons.append("missing 2026-08-24")
    elif r24["new_buy_1925_allowed"] or r24["new_buy_150_allowed"]:
        ok = False
        reasons.append(f"Aug24 must block, got {r24}")
    elif r24["phase"] < 3:
        ok = False
        reasons.append(f"Aug24 phase expected >=3 got {r24['phase_name']}")

    # Climax window Aug 19-22 should block
    for d in ("2026-08-19", "2026-08-20", "2026-08-21", "2026-08-22"):
        rd = by_date.get(d)
        if rd and rd["new_buy_150_allowed"]:
            ok = False
            reasons.append(f"{d} should block late-run buy")

    # Early window: at least one day Aug 10-14 allows
    early_allow = [
        by_date[d]
        for d in ("2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14")
        if d in by_date and by_date[d]["new_buy_150_allowed"]
    ]
    if not early_allow:
        # soft fail → hard: we want SOME early entry capacity
        ok = False
        reasons.append("no ALLOW days in Aug 10-14 — gate too tight / ignition miss")

    # Count phase timeline
    phase_counts: Dict[str, int] = {}
    for r in rows:
        phase_counts[r["phase_name"]] = phase_counts.get(r["phase_name"], 0) + 1

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "pair": "LINK-USD",
        "window": "2026-08-08..2026-08-24",
        "config": {
            "block_new_phase_ge": cfg.get("block_new_phase_ge"),
            "ext_from_low_10d": cfg.get("ext_from_low_10d"),
            "ext_rsi": cfg.get("ext_rsi"),
            "exhaust_rsi": cfg.get("exhaust_rsi"),
        },
        "daily": rows,
        "phase_counts": phase_counts,
        "early_allow_days": [r["date"] for r in early_allow],
        "aug24": r24,
        "validation": {"ok": ok, "reasons": reasons},
        "verdict": {
            "would_block_aug24_recovery_buy": bool(r24 and not r24["new_buy_1925_allowed"]),
            "early_entry_window_exists": len(early_allow) > 0,
            "note": "P0 blocks late NEW buys; does not auto-enter ignition (signal work = P1).",
        },
    }

    # Optional: sample other majors on latest bar
    latest_others = {}
    for p in ("BTC-USD", "ETH-USD", "SOL-USD"):
        try:
            cdl = fetch_daily_candles_public(p, limit=40)
            snap = classify_run_phase(cdl, pair=p, cfg=cfg)
            g = apply_run_phase_buy_gate(p, 150.0, snap, current_pair_usd=0.0, cfg=cfg)
            latest_others[p] = {
                "phase": snap.phase_name,
                "rsi": snap.daily_rsi,
                "pct10": snap.pct_from_low_10d,
                "new_buy_150": not g.blocked,
            }
        except Exception as e:
            latest_others[p] = {"error": str(e)}
    report["latest_others"] = latest_others

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print("\nphase_counts", phase_counts)
    print("early_allow", report["early_allow_days"])
    print("latest_others", json.dumps(latest_others, indent=2))
    print(f"\nReport → {OUT}")

    if ok:
        print("\nCF VALIDATION PASSED")
        return 0
    print("\nCF VALIDATION FAILED:")
    for r in reasons:
        print(" -", r)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
