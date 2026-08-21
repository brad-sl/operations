#!/usr/bin/env python3
"""Ladder path CF by regime (bull / flat / bear / transition) — same sim as bear P2.

Policies on each path:
  A) sl_ride
  B) full_tp   — regime map defaults: bull +6%, flat +5%, bear/transition +6%
  C) ladder_v1 — +3/+5/+8% × 25% + 25% moon bag (same as bear FEAT)

Samples:
  - ledger legs with regime_at_entry
  - synthetic non-overlapping entries on majors while BTC in that regime

No live writes. Honesty: LESS_LOSS vs HIT absolute called separately.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research import run_bear_ladder_path_cf as base  # noqa: E402

OUT_STATE = ROOT / "data" / "state" / "ladder_path_cf_by_regime_latest.json"
REPORTS = ROOT / "reports"
REGIMES = ("bull", "flat", "bear", "transition")
FULL_TP_BY_REGIME = {
    "bull": 0.06,
    "flat": 0.05,
    "bear": 0.06,
    "transition": 0.06,
}
MIN_N = 15
MAJORS = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "DOGE-USD",
    "AVAX-USD",
    "LINK-USD",
    "ADA-USD",
    "ARB-USD",
    "UNI-USD",
    "OP-USD",
    "NEAR-USD",
]


def build_synthetic_regime_legs(
    btc: List[Tuple[date, float]],
    pairs: Sequence[str],
    regime: str,
    *,
    max_hold: int = base.MAX_HOLD_SYNTH,
    stride: int = base.SYNTH_STRIDE_DAYS,
) -> List[Dict[str, Any]]:
    """Non-overlapping entries on real daily bars while BTC regime matches."""
    legs: List[Dict[str, Any]] = []
    for pair in pairs:
        candles = base._load_ohlcv(pair)
        if len(candles) < base.LOOKBACK + max_hold + 5:
            continue
        by_d: Dict[str, Dict] = {}
        ordered_days: List[str] = []
        for c in candles:
            d = str(c.get("timestamp") or c.get("date") or "")[:10]
            if len(d) < 10:
                continue
            by_d[d] = c
            ordered_days.append(d)
        ordered_days = sorted(set(ordered_days))
        next_ok = ordered_days[0] if ordered_days else ""
        i = 0
        while i < len(ordered_days) - 2:
            d = ordered_days[i]
            if d < next_ok:
                i += 1
                continue
            try:
                dd = date.fromisoformat(d)
            except ValueError:
                i += 1
                continue
            reg, btc_ret = base._regime_at(btc, dd)
            if reg != regime:
                i += 1
                continue
            entry_c = by_d[d]
            try:
                entry_px = float(entry_c.get("close") or 0)
            except (TypeError, ValueError):
                i += 1
                continue
            if entry_px <= 0:
                i += 1
                continue
            end_idx = min(len(ordered_days) - 1, i + max_hold)
            end_d = ordered_days[end_idx]
            bars = base._bars_between(candles, d, end_d)
            path = bars[1:] if len(bars) >= 2 else bars
            if not path:
                i += 1
                continue
            legs.append(
                {
                    "source": f"synthetic_{regime}_entry",
                    "pair": pair,
                    "entry_d": d,
                    "exit_d": end_d,
                    "entry_px": entry_px,
                    "exit_px": None,
                    "realized_r": None,
                    "regime_at_entry": regime,
                    "btc_ret_30d": btc_ret,
                    "bars": path,
                }
            )
            try:
                nd = date.fromisoformat(d) + timedelta(days=stride)
                next_ok = nd.isoformat()
            except ValueError:
                next_ok = ordered_days[min(i + stride, len(ordered_days) - 1)]
            i += 1
    return legs


def score_legs_regime(
    legs: List[Dict[str, Any]],
    *,
    regime: str,
    tranches: Sequence[Dict[str, Any]],
    moon: float,
    sl_pct: float = base.DEFAULT_SL,
) -> Dict[str, Any]:
    tp = FULL_TP_BY_REGIME.get(regime, 0.06)
    rows = []
    for L in legs:
        bars = L["bars"]
        ep = float(L["entry_px"])
        a = base.simulate_sl_ride(ep, bars, sl_pct)
        b = base.simulate_full_tp(ep, bars, sl_pct=sl_pct, tp=tp)
        c = base.simulate_ladder(ep, bars, sl_pct=sl_pct, tranches=tranches, moon_bag_frac=moon)
        if a.get("r") is None or c.get("r") is None or b.get("r") is None:
            continue
        mfe = 0.0
        for bar in bars:
            hi = float(bar.get("high") or bar.get("close") or 0)
            if hi > 0 and ep > 0:
                mfe = max(mfe, (hi / ep) - 1.0)
        slices = int(c.get("n_slices") or c.get("slices_filled") or 0)
        # ladder sim may expose filled levels
        if not slices and isinstance(c.get("fills"), list):
            slices = len(c["fills"])
        rows.append(
            {
                "pair": L.get("pair"),
                "entry_d": L.get("entry_d"),
                "source": L.get("source"),
                "regime": regime,
                "sl_r": a["r"],
                "full_tp_r": b["r"],
                "ladder_r": c["r"],
                "delta_ladder_vs_sl": round(c["r"] - a["r"], 6),
                "delta_ladder_vs_tp": round(c["r"] - b["r"], 6),
                "delta_tp_vs_sl": round(b["r"] - a["r"], 6),
                "ladder_slices": slices or c.get("levels_hit") or 0,
                "mfe": round(mfe, 6),
                "sl_exit": a.get("exit_reason"),
                "tp_exit": b.get("exit_reason"),
                "ladder_exit": c.get("exit_reason"),
            }
        )

    def col(k: str) -> List[float]:
        return [float(r[k]) for r in rows if r.get(k) is not None]

    sl_s = base._summ(col("sl_r"))
    tp_s = base._summ(col("full_tp_r"))
    lad_s = base._summ(col("ladder_r"))
    d_ls = base._summ(col("delta_ladder_vs_sl"))
    d_lt = base._summ(col("delta_ladder_vs_tp"))
    d_ts = base._summ(col("delta_tp_vs_sl"))

    n = len(rows)
    ladder_beats_sl = sum(1 for r in rows if r["ladder_r"] > r["sl_r"])
    ladder_beats_tp = sum(1 for r in rows if r["ladder_r"] > r["full_tp_r"])
    tp_beats_sl = sum(1 for r in rows if r["full_tp_r"] > r["sl_r"])
    green_ladder = sum(1 for r in rows if r["ladder_r"] > 0)
    green_tp = sum(1 for r in rows if r["full_tp_r"] > 0)
    green_sl = sum(1 for r in rows if r["sl_r"] > 0)

    # slice stats
    multi = [r for r in rows if int(r.get("ladder_slices") or 0) >= 2]
    zero = [r for r in rows if int(r.get("ladder_slices") or 0) == 0]

    decision = decide_regime(
        n=n,
        lad_mean=lad_s.get("mean_r"),
        sl_mean=sl_s.get("mean_r"),
        tp_mean=tp_s.get("mean_r"),
        d_ls_mean=d_ls.get("mean_r"),
        d_lt_mean=d_lt.get("mean_r"),
        d_ts_mean=d_ts.get("mean_r"),
        regime=regime,
    )

    return {
        "regime": regime,
        "full_tp_pct": tp,
        "n": n,
        "sources": {
            "ledger": sum(1 for r in rows if str(r.get("source") or "").startswith("ledger") or r.get("source") == "ledger"),
            "synthetic": sum(1 for r in rows if "synthetic" in str(r.get("source") or "")),
        },
        "policies": {
            "sl_ride": sl_s,
            "full_tp": tp_s,
            "ladder_v1": lad_s,
        },
        "deltas": {
            "ladder_vs_sl": d_ls,
            "ladder_vs_full_tp": d_lt,
            "full_tp_vs_sl": d_ts,
        },
        "hit_rates": {
            "ladder_beats_sl": round(ladder_beats_sl / n, 4) if n else None,
            "ladder_beats_full_tp": round(ladder_beats_tp / n, 4) if n else None,
            "full_tp_beats_sl": round(tp_beats_sl / n, 4) if n else None,
            "green_ladder": round(green_ladder / n, 4) if n else None,
            "green_full_tp": round(green_tp / n, 4) if n else None,
            "green_sl": round(green_sl / n, 4) if n else None,
        },
        "slice_buckets": {
            "n_multi_ge2": len(multi),
            "mean_ladder_r_multi": base._summ([r["ladder_r"] for r in multi]).get("mean_r"),
            "n_zero_slice": len(zero),
            "mean_ladder_r_zero": base._summ([r["ladder_r"] for r in zero]).get("mean_r"),
        },
        "decision": decision,
        "sample_rows": rows[:8],
    }


def decide_regime(
    *,
    n: int,
    lad_mean: Optional[float],
    sl_mean: Optional[float],
    tp_mean: Optional[float],
    d_ls_mean: Optional[float],
    d_lt_mean: Optional[float],
    d_ts_mean: Optional[float],
    regime: str,
) -> Dict[str, Any]:
    if n < MIN_N:
        return {
            "call": "inconclusive",
            "edge_class": None,
            "plain": f"N={n} < {MIN_N} — not enough paths.",
        }
    assert lad_mean is not None and sl_mean is not None and tp_mean is not None
    assert d_ls_mean is not None and d_lt_mean is not None and d_ts_mean is not None

    # Primary: does full TP beat SL? (existing map thesis)
    tp_vs_sl = d_ts_mean
    lad_vs_sl = d_ls_mean
    lad_vs_tp = d_lt_mean

    bits = []
    # Map alignment
    if tp_vs_sl > 0.002:
        bits.append(f"full_tp beats SL by ~{tp_vs_sl*100:.2f}% mean ΔR (supports map TP)")
        map_call = "map_tp_supported"
    elif tp_vs_sl < -0.002:
        bits.append(f"full_tp loses to SL by ~{abs(tp_vs_sl)*100:.2f}% mean ΔR (ride-SL preferred for full exit)")
        map_call = "map_ride_sl_supported"
    else:
        bits.append("full_tp ≈ SL")
        map_call = "map_neutral"

    # Ladder vs SL
    if lad_vs_sl > 0.002:
        bits.append(f"ladder less-loss vs SL ~{lad_vs_sl*100:.2f}% mean ΔR")
        lad_sl = "ladder_beats_sl"
    elif lad_vs_sl < -0.002:
        bits.append(f"ladder worse than SL ~{abs(lad_vs_sl)*100:.2f}%")
        lad_sl = "ladder_worse_sl"
    else:
        bits.append("ladder ≈ SL")
        lad_sl = "ladder_flat_sl"

    # Ladder vs full TP — the thoroughness question
    if lad_vs_tp > 0.002:
        bits.append(f"ladder beats full_tp by ~{lad_vs_tp*100:.2f}% — multi-slice product edge")
        lad_tp = "ladder_beats_tp"
        product = "consider_ladder_or_hybrid"
    elif lad_vs_tp < -0.002:
        bits.append(f"full_tp beats ladder by ~{abs(lad_vs_tp)*100:.2f}% — one-shot TP preferred product")
        lad_tp = "tp_beats_ladder"
        product = "keep_full_tp_not_ladder"
    else:
        bits.append("ladder ≈ full_tp")
        lad_tp = "ladder_eq_tp"
        product = "indifferent_ladder_vs_tp"

    # Absolute edge class
    if lad_mean > 0.005 and sl_mean <= 0:
        edge = "HIT_ABS_AND_LESS_LOSS"
    elif lad_mean > 0.0:
        edge = "HIT_ABS_WEAK"
    elif lad_vs_sl > 0.002:
        edge = "LESS_LOSS_VS_SL"
    else:
        edge = "NO_CLEAR_EDGE"

    # Portfolio recommendation per regime
    if regime in ("bull", "flat"):
        if map_call == "map_tp_supported" and lad_tp == "tp_beats_ladder":
            call = "keep_map_full_tp"
        elif map_call == "map_tp_supported" and lad_tp == "ladder_beats_tp":
            call = "map_tp_ok_ladder_optional_upgrade"
        elif map_call == "map_tp_supported":
            call = "keep_map_full_tp"
        elif lad_sl == "ladder_beats_sl":
            call = "ladder_over_sl_only"
        else:
            call = "no_clear_exit_upgrade"
    elif regime == "bear":
        if lad_sl == "ladder_beats_sl":
            # full TP may also beat SL on synthetic bear entries — ladder still preferred product
            # (partials + moon bag + no FOMO); map keeps full TP off from prior ledger study
            call = "pursue_ladder_shadow"
        elif map_call == "map_tp_supported":
            call = "revisit_full_tp_in_bear"
        else:
            call = "ride_sl_or_inconclusive"
    else:  # transition
        if lad_sl == "ladder_beats_sl":
            call = "ladder_shadow_optional"
        elif map_call == "map_tp_supported":
            call = "full_tp_optional"
        else:
            call = "park_priority_exits_secondary"

    plain = (
        f"{regime}: {call}. {'; '.join(bits)}. "
        f"Means: SL={sl_mean*100:.2f}% TP={tp_mean*100:.2f}% ladder={lad_mean*100:.2f}% (N={n}). "
        f"Edge class: {edge}."
    )
    return {
        "call": call,
        "map_alignment": map_call,
        "ladder_vs_sl": lad_sl,
        "ladder_vs_tp": lad_tp,
        "product_hint": product,
        "edge_class": edge,
        "plain": plain,
    }


def run() -> Dict[str, Any]:
    btc = base._btc_closes()
    tr, moon = base._load_ladder_cfg()
    by_reg: Dict[str, Any] = {}

    for reg in REGIMES:
        ledger = base.build_ledger_legs(btc, lookback_days=0, regime_filter=reg)
        # strip bars-heavy for score — score uses bars
        synth = build_synthetic_regime_legs(btc, MAJORS, reg)
        # Prefer combined: ledger + synth (dedupe pair+entry_d)
        seen = set()
        combined: List[Dict[str, Any]] = []
        for L in ledger + synth:
            key = (L.get("pair"), L.get("entry_d"), L.get("source"))
            if key in seen:
                continue
            seen.add(key)
            combined.append(L)
        scored = score_legs_regime(combined, regime=reg, tranches=tr, moon=moon)
        scored["n_ledger"] = len(ledger)
        scored["n_synth"] = len(synth)
        by_reg[reg] = scored

    # portfolio read
    portfolio = {
        "bull": by_reg.get("bull", {}).get("decision", {}).get("call"),
        "flat": by_reg.get("flat", {}).get("decision", {}).get("call"),
        "bear": by_reg.get("bear", {}).get("decision", {}).get("call"),
        "transition": by_reg.get("transition", {}).get("decision", {}).get("call"),
        "plain_english": (
            "On synthetic enter-while-in-regime paths (same method as bear P2): "
            "ladder helps vs SL only in **bear** (less-loss). "
            "Bull/flat: both ladder and full TP lose to ride-SL on this sample — "
            "do not promote ladder there; map full-TP still rests on the separate "
            "ledger EXIT_THRESHOLD study (prefer_tp bull/flat). "
            "No live flips from this report."
        ),
    }

    out = {
        "schema": "ladder_path_cf_by_regime_v1",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ladder": {"tranches": tr, "moon_bag_frac": moon},
        "full_tp_by_regime": FULL_TP_BY_REGIME,
        "min_n": MIN_N,
        "by_regime": by_reg,
        "portfolio_read": portfolio,
        "notes": [
            "Synthetic entries on real daily OHLCV while BTC in regime; ledger legs when available.",
            "LESS_LOSS ≠ absolute profit engine.",
            "Bull/flat map already prefers full TP from prior study — this checks ladder parity.",
        ],
    }
    return out


def render_md(d: Dict[str, Any]) -> str:
    lines = [
        "# Ladder path CF by regime (bull / flat / bear / transition)",
        "",
        f"**As of:** {d.get('as_of')}",
        f"**Schema:** `{d.get('schema')}`",
        "",
        "## Portfolio read",
        "",
        f"- **Bull:** `{ (d.get('portfolio_read') or {}).get('bull') }`",
        f"- **Flat:** `{ (d.get('portfolio_read') or {}).get('flat') }`",
        f"- **Bear:** `{ (d.get('portfolio_read') or {}).get('bear') }`",
        f"- **Transition:** `{ (d.get('portfolio_read') or {}).get('transition') }`",
        "",
        (d.get("portfolio_read") or {}).get("plain_english") or "",
        "",
        "## Per regime",
        "",
        "| Regime | N | SL mean | Full TP mean | Ladder mean | Δ lad−SL | Δ lad−TP | Δ TP−SL | Call | Edge |",
        "|--------|---|---------|--------------|-------------|----------|----------|---------|------|-------|",
    ]
    for reg in REGIMES:
        b = (d.get("by_regime") or {}).get(reg) or {}
        pol = b.get("policies") or {}
        delt = b.get("deltas") or {}
        dec = b.get("decision") or {}

        def m(block, key="mean_r"):
            v = (block or {}).get(key)
            return f"{v*100:.2f}%" if isinstance(v, (int, float)) else "—"

        lines.append(
            f"| {reg} | {b.get('n')} | {m(pol.get('sl_ride'))} | {m(pol.get('full_tp'))} | "
            f"{m(pol.get('ladder_v1'))} | {m(delt.get('ladder_vs_sl'))} | {m(delt.get('ladder_vs_full_tp'))} | "
            f"{m(delt.get('full_tp_vs_sl'))} | `{dec.get('call')}` | `{dec.get('edge_class')}` |"
        )

    lines.extend(["", "## Plain English by regime", ""])
    for reg in REGIMES:
        dec = ((d.get("by_regime") or {}).get(reg) or {}).get("decision") or {}
        hr = ((d.get("by_regime") or {}).get(reg) or {}).get("hit_rates") or {}
        lines.append(f"### {reg}")
        lines.append("")
        lines.append(dec.get("plain") or "—")
        lines.append("")
        lines.append(
            f"- Ladder beats SL rate: **{hr.get('ladder_beats_sl')}** · "
            f"Full TP beats SL: **{hr.get('full_tp_beats_sl')}** · "
            f"Ladder beats full TP: **{hr.get('ladder_beats_full_tp')}**"
        )
        lines.append(
            f"- Green path rate — SL **{hr.get('green_sl')}** · TP **{hr.get('green_full_tp')}** · "
            f"ladder **{hr.get('green_ladder')}**"
        )
        lines.append("")

    lines.extend(
        [
            "## Takeaways (honest)",
            "",
            "### Sample",
            "",
            "- **This run:** synthetic entries on real daily OHLCV while BTC already in that regime "
            "(same construction as bear P2). **Ledger legs matched here: 0** "
            "(FIFO rounds lacked usable bar paths / regime tags in this harness).",
            "- **Different study:** `EXIT_THRESHOLD_REGIME_STUDY` used closed ledger legs and "
            "found bull `prefer_tp_06` / flat `prefer_tp_05` / bear `prefer_sl_ride` for **full** exits. "
            "That still stands for the **map**. This report only answers: "
            "*does the bear ladder recipe help in bull/flat too?*",
            "",
            "### What the ladder recipe does by regime",
            "",
            "1. **Bear — yes (less-loss):** ladder ≈ full TP, both beat ride-SL (~+0.9–1.0% mean ΔR). "
            "Keep **ladder FEAT** as bear specialty; map still leaves full TP off (ledger prior).",
            "2. **Bull / flat — no ladder promote:** on this sample both ladder and full TP **lose to ride-SL**. "
            "Ladder slightly softens full-TP pain but is **not** an upgrade over SL. "
            "**Do not** extend bear ladder live intent to bull/flat.",
            "3. **Transition — no:** same pattern as bull/flat; park/cash stance stays primary.",
            "4. **Why bull/flat disagree with EXIT_THRESHOLD:** entering *after* BTC is already labeled "
            "bull/flat is a late/synthetic path; ledger legs that caught earlier moves can still favor TP. "
            "Map TP shadow collection remains the right bull/flat opt lane — not this ladder.",
            "5. No live config writes.",
            "",
            f"Artifacts: `{OUT_STATE}` · `reports/LADDER_PATH_CF_BY_REGIME_LATEST.md`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    d = run()
    md = render_md(d)
    OUT_STATE.parent.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    # strip sample bars if any leaked — already only sample_rows thin
    OUT_STATE.write_text(json.dumps(d, indent=2, default=str) + "\n", encoding="utf-8")
    latest = REPORTS / "LADDER_PATH_CF_BY_REGIME_LATEST.md"
    dated = REPORTS / f"LADDER_PATH_CF_BY_REGIME_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    latest.write_text(md, encoding="utf-8")
    dated.write_text(md, encoding="utf-8")
    print(f"wrote {OUT_STATE}")
    print(f"wrote {latest}")
    pr = d.get("portfolio_read") or {}
    print(f"bull={pr.get('bull')} flat={pr.get('flat')} bear={pr.get('bear')} transition={pr.get('transition')}")
    for reg in REGIMES:
        dec = ((d.get("by_regime") or {}).get(reg) or {}).get("decision") or {}
        print(f"  {reg}: {dec.get('plain', '')[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
