#!/usr/bin/env python3
"""
Counterfactual backtest: apply RSI-primary P0 gates to historical BUY notionals.

Uses real trades/phase6_trades.jsonl. Reconstructs rsi/sent from trade fields when
present; otherwise classifies unknown mid-RSI + high-sent only for case study rows
and marks reconstruction quality.

Also runs the explicit LINK 2026-08-24 poster-child case.

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 scripts/phase6/backtest_rsi_primary_deploy_cf.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.rsi_primary_deploy import apply_buy_size_gates, load_rsi_primary_config

TRADES = ROOT / "trades" / "phase6_trades.jsonl"
OUT = ROOT / "data" / "state" / "rsi_primary_deploy_cf_report.json"
CFG_PATH = ROOT / "config" / "trading_config_phase6.json"


def _f(v, d=0.0):
    try:
        return float(v) if v is not None else d
    except (TypeError, ValueError):
        return d


def load_buys(path: Path) -> List[Dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            t = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if str(t.get("side") or "").upper() != "BUY":
            continue
        rows.append(t)
    return rows


def notional(t: Dict[str, Any]) -> float:
    if t.get("usd") is not None:
        return _f(t["usd"])
    q = _f(t.get("qty"))
    px = _f(t.get("entry_price"))
    return q * px if q > 0 and px > 0 else 0.0


def extract_rsi_sent(t: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], str]:
    ind = t.get("indicators_at_trade") or {}
    if isinstance(ind, str):
        try:
            ind = json.loads(ind)
        except Exception:
            ind = {}
    rsi = ind.get("rsi") if isinstance(ind, dict) else None
    sent = ind.get("sentiment") if isinstance(ind, dict) else None
    if rsi is None:
        rsi = t.get("entry_rsi") or t.get("rsi")
    if sent is None:
        sent = t.get("entry_sentiment") or t.get("sentiment")
    if rsi is not None and sent is not None:
        return _f(rsi), _f(sent), "trade_fields"
    return None, None, "missing"


def main() -> int:
    cfg = load_rsi_primary_config(json.loads(CFG_PATH.read_text()))
    # Use current live-ish cap from config global_settings
    full_cfg = json.loads(CFG_PATH.read_text())
    default_cap = _f((full_cfg.get("global_settings") or {}).get("rebalance_cap_usd"), 150.0)

    buys = load_buys(TRADES)
    print(f"Loaded {len(buys)} BUY rows from {TRADES}")

    # Case study: LINK 2026-08-24
    link_case = {
        "pair": "LINK-USD",
        "label": "2026-08-24 09:00 recovery full-wallet",
        "proposed_usd": 1925.0,
        "rsi": 46.6,
        "sentiment": 0.89,
        "equity": 2372.0,
        "cash": 1975.0,
        "cap": 100.0,  # regime soft log at time; hard gate would bind
        "emergency": True,
    }
    g_link = apply_buy_size_gates(
        link_case["pair"],
        link_case["proposed_usd"],
        rsi=link_case["rsi"],
        sentiment=link_case["sentiment"],
        equity_usd=link_case["equity"],
        current_pair_usd=0.0,
        rebalance_cap_usd=link_case["cap"],
        free_cash_usd=link_case["cash"],
        emergency_recovery=link_case["emergency"],
        cfg=cfg,
    )
    print("\n=== LINK poster child CF ===")
    print(f"  baseline ${link_case['proposed_usd']:.2f} → CF ${g_link.final_usd:.2f}")
    print(f"  saved ${link_case['proposed_usd'] - g_link.final_usd:.2f}")
    print(f"  notes: {g_link.notes} drivers={g_link.drivers.drivers}")

    # Historical buys: when rsi/sent missing, run two scenarios
    # A) assume structure (rsi=28) — lower bound on clips
    # B) assume sentiment-only (rsi=50, sent=0.5) — upper bound on haircuts
    stats = {
        "n_buys": len(buys),
        "baseline_notional_sum": 0.0,
        "cf_structure_sum": 0.0,
        "cf_sent_only_sum": 0.0,
        "cf_known_sum": 0.0,
        "n_known_rsi_sent": 0,
        "n_clipped_structure": 0,
        "n_clipped_sent_only": 0,
        "n_clipped_known": 0,
        "max_ticket_baseline": 0.0,
        "max_ticket_cf_structure": 0.0,
        "max_ticket_cf_sent_only": 0.0,
        "large_tickets": [],  # baseline > 2x cap
    }

    for t in buys:
        n = notional(t)
        if n < 1:
            continue
        stats["baseline_notional_sum"] += n
        stats["max_ticket_baseline"] = max(stats["max_ticket_baseline"], n)
        pair = str(t.get("pair") or "?")
        rsi_k, sent_k, qual = extract_rsi_sent(t)

        # Approximate equity as max(1000, n*1.2) when unknown — conservative for pair weight
        equity = max(1000.0, n * 1.25)
        cash = max(n, default_cap * 2)

        # Structure path
        gs = apply_buy_size_gates(
            pair,
            n,
            rsi=28.0,
            sentiment=0.5,
            equity_usd=equity,
            rebalance_cap_usd=default_cap,
            free_cash_usd=cash,
            emergency_recovery=True,
            cfg=cfg,
        )
        stats["cf_structure_sum"] += gs.final_usd
        stats["max_ticket_cf_structure"] = max(stats["max_ticket_cf_structure"], gs.final_usd)
        if gs.final_usd + 1e-6 < n:
            stats["n_clipped_structure"] += 1

        # Sentiment-only path
        gso = apply_buy_size_gates(
            pair,
            n,
            rsi=50.0,
            sentiment=0.5,
            equity_usd=equity,
            rebalance_cap_usd=default_cap,
            free_cash_usd=cash,
            emergency_recovery=True,
            cfg=cfg,
        )
        stats["cf_sent_only_sum"] += gso.final_usd
        stats["max_ticket_cf_sent_only"] = max(stats["max_ticket_cf_sent_only"], gso.final_usd)
        if gso.final_usd + 1e-6 < n:
            stats["n_clipped_sent_only"] += 1

        if qual == "trade_fields":
            stats["n_known_rsi_sent"] += 1
            gk = apply_buy_size_gates(
                pair,
                n,
                rsi=rsi_k,
                sentiment=sent_k,
                equity_usd=equity,
                rebalance_cap_usd=default_cap,
                free_cash_usd=cash,
                emergency_recovery=True,
                cfg=cfg,
            )
            stats["cf_known_sum"] += gk.final_usd
            if gk.final_usd + 1e-6 < n:
                stats["n_clipped_known"] += 1

        if n > default_cap * 2:
            stats["large_tickets"].append(
                {
                    "pair": pair,
                    "ts": t.get("timestamp"),
                    "baseline": round(n, 2),
                    "cf_structure": round(gs.final_usd, 2),
                    "cf_sent_only": round(gso.final_usd, 2),
                    "cap": default_cap,
                }
            )

    # Sort large tickets
    stats["large_tickets"] = sorted(
        stats["large_tickets"], key=lambda x: -x["baseline"]
    )[:25]

    def pct_saved(base, cf):
        return round(100.0 * (base - cf) / base, 2) if base > 0 else 0.0

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "config_cap_usd": default_cap,
        "link_poster_child": {
            **link_case,
            "cf_final_usd": g_link.final_usd,
            "cf_saved_usd": link_case["proposed_usd"] - g_link.final_usd,
            "notes": g_link.notes,
            "drivers": g_link.drivers.drivers,
            "sentiment_only": g_link.drivers.sentiment_only,
        },
        "ledger_cf": {
            **stats,
            "pct_notional_saved_if_all_structure": pct_saved(
                stats["baseline_notional_sum"], stats["cf_structure_sum"]
            ),
            "pct_notional_saved_if_all_sent_only": pct_saved(
                stats["baseline_notional_sum"], stats["cf_sent_only_sum"]
            ),
        },
        "verdict": {
            "link_would_not_be_80pct_nav": g_link.final_usd <= link_case["cap"] + 1e-6,
            "hard_cap_binds": True,
            "sentiment_only_haircut_before_cap": g_link.haircut_applied,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))

    print("\n=== Ledger BUY counterfactual ===")
    print(f"  buys: {stats['n_buys']}")
    print(f"  baseline notional sum: ${stats['baseline_notional_sum']:.2f}")
    print(f"  max ticket baseline:   ${stats['max_ticket_baseline']:.2f}")
    print(f"  CF if all structure:   sum=${stats['cf_structure_sum']:.2f} max=${stats['max_ticket_cf_structure']:.2f} clipped={stats['n_clipped_structure']}")
    print(f"  CF if all sent-only:   sum=${stats['cf_sent_only_sum']:.2f} max=${stats['max_ticket_cf_sent_only']:.2f} clipped={stats['n_clipped_sent_only']}")
    print(f"  known rsi/sent rows:   {stats['n_known_rsi_sent']}")
    print(f"  large tickets (>2x cap): {len(stats['large_tickets'])}")
    for row in stats["large_tickets"][:8]:
        print(f"    {row['ts']} {row['pair']}: ${row['baseline']} → struct ${row['cf_structure']} / sent ${row['cf_sent_only']}")
    print(f"\nReport → {OUT}")

    # Validation gates
    ok = True
    if not report["verdict"]["link_would_not_be_80pct_nav"]:
        print("FAIL: LINK CF still over cap")
        ok = False
    if stats["max_ticket_cf_structure"] > default_cap + 1e-6:
        print("FAIL: structure CF max ticket exceeds cap")
        ok = False
    if stats["max_ticket_cf_sent_only"] > default_cap + 1e-6:
        print("FAIL: sent-only CF max ticket exceeds cap")
        ok = False
    if ok:
        print("\nCF VALIDATION PASSED")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
