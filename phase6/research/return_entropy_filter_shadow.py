#!/usr/bin/env python3
"""
Return-entropy filter shadow dig (offline).

Hypothesis (pre-registered — not a promote claim)
-------------------------------------------------
Normalized rolling Shannon entropy of daily simple returns is a **regime /
soft filter** feature. Low H_norm may mark concentrated return histograms;
high H_norm may mark flatter / noisier windows.

This is NOT:
  - a direction predictor
  - a validated Two-Sigma secret
  - a live seat/buy hook

Arms (frozen before run — no combo fishing)
-------------------------------------------
  BH              buy & hold pair
  ALWAYS_IN       long always (same as BH with fee on entry once)
  LOW_H_ONLY      long only while H_norm < structure_max (0.35)
  AVOID_HIGH_H    long while H_norm <= noise_min (0.70); flat when noise
  INVERSE_HIGH_H  long only while H_norm > noise_min  (control; thesis says worse)

Real Coinbase daily OHLCV from backtests/data/long only (no synthetic).
Fees applied. Success metrics follow offline-strategy-honesty vocabulary.

No live config / allocator writes.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.return_entropy_shadow import (  # noqa: E402
    EntropyConfig,
    rolling_entropy_series,
    simple_returns,
)

LONG_DIR = ROOT / "backtests" / "data" / "long"
REPORT_DIR = ROOT / "reports"
STATE_JSON = ROOT / "data" / "state" / "trials" / "TEST_RETURN_ENTROPY_FILTER_SHADOW.json"
OUT_JSON = REPORT_DIR / "RETURN_ENTROPY_FILTER_SHADOW_LATEST.json"
OUT_MD = REPORT_DIR / "RETURN_ENTROPY_FILTER_SHADOW_LATEST.md"

PAIRS = {
    "btc": "BTC-USD",
    "eth": "ETH-USD",
    "sol": "SOL-USD",
    "link": "LINK-USD",
    "avax": "AVAX-USD",
}

# Pre-registered (match live shadow board doctrine)
WINDOW = 30
N_BINS = 10
STRUCTURE_MAX = 0.35
NOISE_MIN = 0.70
# Daily simple returns: wider fixed grid than hourly board
FIXED_LO = -0.08
FIXED_HI = 0.08
EDGE_MODE = "fixed"
FEE_BPS = 5.0  # per side
SLIP_BPS = 2.0
MAX_HOLD_BARS = 60  # safety flat if stuck (not a TP story)


@dataclass
class Arm:
    arm_id: str
    description: str


ARMS = [
    Arm("BH", "Buy & hold from first valid bar"),
    Arm("LOW_H_ONLY", "Long only when H_norm < structure_max"),
    Arm("AVOID_HIGH_H", "Long when H_norm <= noise_min; flat in noise"),
    Arm("INVERSE_HIGH_H", "Long only when H_norm > noise_min (control)"),
]


def _load_closes(short: str) -> Tuple[List[str], List[float]]:
    path = LONG_DIR / f"ohlcv_daily_{short}.json"
    if not path.exists():
        raise FileNotFoundError(f"missing {path} — use real long daily cache only")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"empty ohlcv {path}")
    ts: List[str] = []
    closes: List[float] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        t = r.get("timestamp") or r.get("time") or r.get("date")
        c = r.get("close") or r.get("Close")
        if t is None or c is None:
            continue
        try:
            closes.append(float(c))
            ts.append(str(t)[:10])
        except (TypeError, ValueError):
            continue
    if len(closes) < WINDOW + 20:
        raise RuntimeError(f"short series {short}: {len(closes)}")
    return ts, closes


def _fee_frac() -> float:
    return (FEE_BPS + SLIP_BPS) / 10_000.0


def _classify_edge(mean_ret: float, mean_dbh: float, n: int, btc_ret: float) -> str:
    """offline-strategy-honesty vocabulary (simplified)."""
    if n == 0:
        return "unstable_or_no_edge"
    # Abs winners that lose hard to BH are not HIT_*_EDGE; keep abs tag only if ΔBH not awful
    if mean_ret >= 0.20 and mean_dbh >= 0.20:
        return "HIT_20_EDGE_BH"
    if mean_ret >= 0.10 and mean_dbh >= 0.10:
        return "HIT_10_EDGE_BH"
    if mean_ret >= 0.10 and mean_dbh >= 0:
        return "HIT_10_ABS"
    if mean_ret >= 0.10 and mean_dbh < 0:
        return "ATTENTION_ONLY"  # absolute green but lost to BH — not a filter win
    if mean_dbh > 0.05 and mean_ret < 0:
        return "EDGE_VS_BAGS_ONLY"
    if mean_ret <= 0 and mean_dbh <= 0:
        return "unstable_or_no_edge"
    if mean_ret > 0 and mean_ret < 0.05:
        return "ATTENTION_ONLY"
    if btc_ret < -0.30 and mean_ret < 0:
        return "unstable_or_no_edge"
    if mean_ret >= 0.05:
        return "ATTENTION_ONLY"
    return "unstable_or_no_edge"


def simulate_arm(
    arm_id: str,
    closes: List[float],
    h_series: List[Optional[float]],
) -> Dict[str, Any]:
    """
    Daily bar sim, next-open≈next-close (close-to-close) with fee on enter/exit.
    Position 0/1. Causal: decision at bar i uses h_series[i] (window ends at i).
    Fill at close[i] for simplicity (research; not fill realism claim).
    """
    fee = _fee_frac()
    n = len(closes)
    cash = 1.0
    units = 0.0
    entry_px = 0.0
    entry_i = -1
    trades = 0
    wins = 0
    losses = 0
    rets: List[float] = []
    equity_curve = []
    pos = 0
    peak = 1.0
    max_dd = 0.0

    # start after entropy warmup
    start = WINDOW
    for i in range(start, n):
        h = h_series[i]
        px = closes[i]
        if px <= 0:
            continue

        want_long = False
        if arm_id == "BH":
            want_long = True
        elif arm_id == "LOW_H_ONLY":
            want_long = h is not None and h < STRUCTURE_MAX
        elif arm_id == "AVOID_HIGH_H":
            want_long = h is not None and h <= NOISE_MIN
        elif arm_id == "INVERSE_HIGH_H":
            want_long = h is not None and h > NOISE_MIN
        else:
            want_long = False

        # force flat on max hold for non-BH
        if pos == 1 and arm_id != "BH" and entry_i >= 0 and (i - entry_i) >= MAX_HOLD_BARS:
            want_long = False

        if want_long and pos == 0:
            # buy
            spend = cash * (1.0 - fee)
            units = spend / px
            cash = 0.0
            entry_px = px
            entry_i = i
            pos = 1
            trades += 1
        elif (not want_long) and pos == 1:
            # sell
            gross = units * px
            cash = gross * (1.0 - fee)
            r = (px / entry_px) - 1.0 if entry_px > 0 else 0.0
            # fee-adjusted approx already in cash path; track raw move for WR
            rets.append(r)
            if r > 0:
                wins += 1
            else:
                losses += 1
            units = 0.0
            entry_px = 0.0
            entry_i = -1
            pos = 0

        eq = cash + units * px
        equity_curve.append(eq)
        peak = max(peak, eq)
        dd = (eq / peak) - 1.0
        max_dd = min(max_dd, dd)

    # mark final
    if pos == 1 and units > 0:
        px = closes[-1]
        cash = units * px * (1.0 - fee)
        r = (px / entry_px) - 1.0 if entry_px > 0 else 0.0
        rets.append(r)
        if r > 0:
            wins += 1
        else:
            losses += 1
        units = 0.0
        pos = 0
        eq = cash
        equity_curve.append(eq)
        peak = max(peak, eq)
        max_dd = min(max_dd, (eq / peak) - 1.0)

    final = cash if cash > 0 else (equity_curve[-1] if equity_curve else 1.0)
    total_ret = final - 1.0
    n_closed = len(rets)
    wr = (wins / n_closed) if n_closed else None
    mean_trade = (sum(rets) / n_closed) if n_closed else None
    # time in market
    # approximate from BH path length
    bars = max(n - start, 1)

    return {
        "arm_id": arm_id,
        "total_return": total_ret,
        "final_equity": final,
        "max_drawdown": max_dd,
        "n_trades": trades,
        "n_round_trips": n_closed,
        "wins": wins,
        "losses": losses,
        "win_rate": wr,
        "mean_trade_ret": mean_trade,
        "bars": bars,
        # WR is secondary — never primary promote metric
    }


def run_pair(short: str) -> Dict[str, Any]:
    ts, closes = _load_closes(short)
    rets = simple_returns(closes)
    # align entropy series to closes indices: returns[i] is move closes[i]→closes[i+1]
    # For decision on bar i (using past window of returns ending at move into i),
    # use returns[:i] window ending at returns[i-1].
    # Build h on returns, then map h_ret[j] onto close index j+1.
    h_on_rets = rolling_entropy_series(
        rets,
        window=WINDOW,
        n_bins=N_BINS,
        edge_mode=EDGE_MODE,
        fixed_lo=FIXED_LO,
        fixed_hi=FIXED_HI,
    )
    h_on_closes: List[Optional[float]] = [None] * len(closes)
    for j, h in enumerate(h_on_rets):
        # h_on_rets[j] uses rets[j-WINDOW+1:j+1] = moves ending at close[j+1]
        ci = j + 1
        if ci < len(h_on_closes):
            h_on_closes[ci] = h

    # label distribution (valid bars)
    labels = {"structure": 0, "mid": 0, "noise": 0, "insufficient": 0}
    for h in h_on_closes:
        if h is None:
            labels["insufficient"] += 1
        elif h < STRUCTURE_MAX:
            labels["structure"] += 1
        elif h > NOISE_MIN:
            labels["noise"] += 1
        else:
            labels["mid"] += 1

    arms_out = []
    bh_ret = None
    for arm in ARMS:
        s = simulate_arm(arm.arm_id, closes, h_on_closes)
        s["description"] = arm.description
        if arm.arm_id == "BH":
            bh_ret = s["total_return"]
        arms_out.append(s)

    for s in arms_out:
        s["delta_bh"] = (s["total_return"] - bh_ret) if bh_ret is not None else None

    return {
        "pair": PAIRS[short],
        "short": short,
        "n_bars": len(closes),
        "start": ts[0] if ts else None,
        "end": ts[-1] if ts else None,
        "label_counts": labels,
        "arms": arms_out,
        "bh_return": bh_ret,
    }


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_arm: Dict[str, List[Dict[str, Any]]] = {a.arm_id: [] for a in ARMS}
    for r in results:
        for a in r["arms"]:
            by_arm[a["arm_id"]].append(a)

    arm_summary = []
    btc_bh = None
    for r in results:
        if r["short"] == "btc":
            btc_bh = r.get("bh_return")

    for arm_id, rows in by_arm.items():
        rets = [x["total_return"] for x in rows]
        dbhs = [x["delta_bh"] for x in rows if x.get("delta_bh") is not None]
        n_tr = sum(x["n_round_trips"] for x in rows)
        mean_ret = sum(rets) / len(rets) if rets else 0.0
        mean_dbh = sum(dbhs) / len(dbhs) if dbhs else 0.0
        mean_dd = sum(x["max_drawdown"] for x in rows) / len(rows) if rows else 0.0
        # WR across pairs (secondary)
        wins = sum(x["wins"] for x in rows)
        losses = sum(x["losses"] for x in rows)
        wr = wins / (wins + losses) if (wins + losses) else None
        edge = _classify_edge(mean_ret, mean_dbh, n_tr, btc_bh if btc_bh is not None else 0.0)
        arm_summary.append(
            {
                "arm_id": arm_id,
                "mean_total_return": mean_ret,
                "mean_delta_bh": mean_dbh,
                "mean_max_dd": mean_dd,
                "total_round_trips": n_tr,
                "win_rate_secondary": wr,
                "edge_class": edge,
                "per_pair": [
                    {
                        "pair": results[i]["pair"],
                        "total_return": rows[i]["total_return"],
                        "delta_bh": rows[i]["delta_bh"],
                        "max_dd": rows[i]["max_drawdown"],
                        "n_rt": rows[i]["n_round_trips"],
                        "wr": rows[i]["win_rate"],
                    }
                    for i in range(len(rows))
                ],
            }
        )

    # plain english pick
    ranked = sorted(
        [a for a in arm_summary if a["arm_id"] != "BH"],
        key=lambda x: (x["mean_delta_bh"], x["mean_total_return"]),
        reverse=True,
    )
    best = ranked[0] if ranked else None
    plain = (
        "No promote. Entropy filter is a concentration feature dig only. "
        "Judge on mean return, ΔBH, max DD, turnover — not win rate."
    )
    if best:
        plain += (
            f" Best non-BH arm on this tape: {best['arm_id']} "
            f"mean_ret={best['mean_total_return']:.3f} "
            f"ΔBH={best['mean_delta_bh']:.3f} "
            f"class={best['edge_class']}."
        )
        if best["edge_class"] in ("unstable_or_no_edge", "EDGE_VS_BAGS_ONLY", "ATTENTION_ONLY"):
            plain += " Not a standard-opt candidate without long walk-forward + Brad go."
        if best["arm_id"] == "INVERSE_HIGH_H" and best["mean_delta_bh"] >= 0:
            plain += " NOTE: inverse control not worse — thesis weak on this sample."

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "plain_english": plain,
        "pre_registered": {
            "window": WINDOW,
            "n_bins": N_BINS,
            "structure_max": STRUCTURE_MAX,
            "noise_min": NOISE_MIN,
            "edge_mode": EDGE_MODE,
            "fixed_lo": FIXED_LO,
            "fixed_hi": FIXED_HI,
            "fee_bps": FEE_BPS,
            "slip_bps": SLIP_BPS,
            "max_hold_bars": MAX_HOLD_BARS,
        },
        "pairs": results,
        "arm_summary": arm_summary,
        "decision": "shadow_only_no_promote",
        "success_gate_note": (
            "Promote path requires: long-tape fixed-param walk-forward, "
            "mean abs return ≥ ~5% bar with costs, ΔBH≥0, DD not worse than BH "
            "in a way that fights the product, N_rt sufficient, inverse control "
            "worse, and explicit Brad go. WR alone is never enough."
        ),
    }


def write_md(doc: Dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Return entropy filter shadow (offline dig)",
        "",
        f"- **ts:** {doc.get('ts')}",
        f"- **decision:** `{doc.get('decision')}`",
        f"- **plain:** {doc.get('plain_english')}",
        f"- **knobs:** `{json.dumps(doc.get('pre_registered'))}`",
        "",
        "## Arm summary (mean across pairs)",
        "",
        "| arm | mean ret | mean ΔBH | mean maxDD | N rt | WR (2nd) | edge class |",
        "|-----|----------|----------|------------|------|----------|------------|",
    ]
    for a in doc.get("arm_summary") or []:
        wr = a.get("win_rate_secondary")
        wr_s = f"{wr:.2%}" if isinstance(wr, float) else "—"
        lines.append(
            f"| {a['arm_id']} | {a['mean_total_return']:.3f} | {a['mean_delta_bh']:.3f} | "
            f"{a['mean_max_dd']:.3f} | {a['total_round_trips']} | {wr_s} | {a['edge_class']} |"
        )
    lines += [
        "",
        "## Success metrics (what would count as a win)",
        "",
        "See `reports/RETURN_ENTROPY_SUCCESS_METRICS.md`.",
        "",
        "## Per pair BH",
        "",
    ]
    for p in doc.get("pairs") or []:
        lines.append(
            f"- **{p['pair']}** bars={p['n_bars']} {p.get('start')}→{p.get('end')} "
            f"BH={p.get('bh_return'):.3f} labels={p.get('label_counts')}"
        )
    lines += [
        "",
        "## Honesty",
        "- Real long daily OHLCV only.",
        "- Pre-registered arms/cutoffs — no post-hoc fishing in this script.",
        "- No live wiring / no auto-promote.",
        "",
    ]
    OUT_MD.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description="Return entropy filter offline shadow dig")
    ap.add_argument("--pair", action="append", default=[], help="short name e.g. btc (default all)")
    args = ap.parse_args()
    shorts = list(args.pair) if args.pair else list(PAIRS.keys())
    results = []
    for s in shorts:
        if s not in PAIRS:
            print(f"skip unknown {s}", file=sys.stderr)
            continue
        print(f"run {s}...")
        results.append(run_pair(s))
    doc = summarize(results)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=2, default=str))
    STATE_JSON.write_text(json.dumps(doc, indent=2, default=str))
    write_md(doc)
    print(doc["plain_english"])
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
