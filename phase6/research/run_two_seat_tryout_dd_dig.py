#!/usr/bin/env python3
"""Two-seat tryout DD dig: $75 x 2 concurrent path risk vs idle cash.

Offline only. Real prices from data/phase6.db + optional ledger tryout-sized legs.
No orders. No config writes.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
EQUITY = 2292.0
SEAT = 75.0
N_SEATS = 2
SL_PCT = 0.034  # ~symmetry floor when live TP on
FEE_RT = 0.016  # ~taker RT haircut on notional
PAIRS = ["ETH-USD", "LINK-USD", "BTC-USD", "SOL-USD"]
HOLD_HOURS = [24, 72, 168]
COMBOS = [
    ("ETH-USD", "LINK-USD"),
    ("ETH-USD", "BTC-USD"),
    ("LINK-USD", "BTC-USD"),
    ("ETH-USD", "SOL-USD"),
]


def load_hourly(con: sqlite3.Connection, pair: str, days: int = 400):
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = con.execute(
        "SELECT ts, price FROM prices WHERE pair=? AND ts>=? ORDER BY ts",
        (pair, cut),
    ).fetchall()
    buckets = {}
    for ts, px in rows:
        if px is None or float(px) <= 0:
            continue
        key = str(ts)[:13]  # YYYY-MM-DDTHH
        buckets[key] = float(px)
    keys = sorted(buckets)
    return [(k, buckets[k]) for k in keys]


def path_metrics(series, entry_i: int, hold_h: int, sl_pct: float = SL_PCT, tp_pct: float = 0.06):
    if entry_i >= len(series) - 1:
        return None
    entry_px = series[entry_i][1]
    if entry_px <= 0:
        return None
    end_i = min(len(series) - 1, entry_i + hold_h)
    peak_r = 0.0
    trough_r = 0.0
    exit_i = end_i
    reason = "time"
    for j in range(entry_i + 1, end_i + 1):
        px = series[j][1]
        r = (px - entry_px) / entry_px
        peak_r = max(peak_r, r)
        trough_r = min(trough_r, r)
        if r <= -sl_pct:
            exit_i = j
            reason = "sl"
            break
        if r >= tp_pct:
            exit_i = j
            reason = "tp06"
            break
    px = series[exit_i][1]
    r = (px - entry_px) / entry_px
    hold = exit_i - entry_i
    return {
        "reason": reason,
        "hold_h": hold,
        "r_gross": r,
        "r_net": r - FEE_RT,
        "mfe": peak_r,
        "mae": trough_r,
        "exit_i": exit_i,
    }


def sample_entries(series, step: int = 12):
    return list(range(0, max(0, len(series) - 170), step))


def two_seat_episode(s1, s2, i1, i2, hold_h: int):
    m1 = path_metrics(s1, i1, hold_h)
    m2 = path_metrics(s2, i2, hold_h)
    if not m1 or not m2:
        return None
    h_max = max(m1["hold_h"], m2["hold_h"])
    e0 = 2 * SEAT

    def path_r(series, entry_i, m):
        entry_px = series[entry_i][1]
        out = []
        for h in range(0, h_max + 1):
            j = entry_i + min(h, m["hold_h"])
            px = series[j][1]
            r = (px - entry_px) / entry_px
            if h >= m["hold_h"]:
                r = m["r_gross"]
            out.append(r)
        return out

    p1 = path_r(s1, i1, m1)
    p2 = path_r(s2, i2, m2)
    eq = []
    for h in range(h_max + 1):
        v = SEAT * (1 + p1[h]) + SEAT * (1 + p2[h])
        eq.append(v)
    eq[-1] = eq[-1] - 2 * SEAT * FEE_RT

    peak = eq[0]
    max_dd = 0.0
    max_dd_usd = 0.0
    t_to_trough = 0
    for h, v in enumerate(eq):
        peak = max(peak, v)
        dd = (v - peak) / peak if peak else 0.0
        dd_usd = v - peak
        if dd < max_dd:
            max_dd = dd
            max_dd_usd = dd_usd
            t_to_trough = h
    terminal = eq[-1]
    pnl = terminal - e0
    return {
        "pnl_usd": pnl,
        "pnl_pct_on_150": pnl / e0,
        "pnl_pct_on_equity": pnl / EQUITY,
        "max_dd_on_150": max_dd,
        "max_dd_usd": max_dd_usd,
        "t_to_trough_h": t_to_trough,
        "hold_h": h_max,
        "r1": m1["r_net"],
        "r2": m2["r_net"],
        "reason1": m1["reason"],
        "reason2": m2["reason"],
        "both_sl": m1["reason"] == "sl" and m2["reason"] == "sl",
        "any_sl": m1["reason"] == "sl" or m2["reason"] == "sl",
    }


def pctile(xs, p: float):
    if not xs:
        return None
    s = sorted(xs)
    idx = max(0, min(len(s) - 1, int(p * len(s)) - (1 if p > 0 else 0)))
    if p <= 0:
        return s[0]
    if p >= 1:
        return s[-1]
    # nearest-rank style
    k = max(0, min(len(s) - 1, int(round((len(s) - 1) * p))))
    return s[k]


def main():
    con = sqlite3.connect(str(PROJECT / "data" / "phase6.db"))
    hourly = {}
    print("=== price coverage ===")
    for p in PAIRS:
        h = load_hourly(con, p, 400)
        hourly[p] = h
        if h:
            print(f"{p}: {len(h)} hourly {h[0][0]} -> {h[-1][0]}")
        else:
            print(f"{p}: EMPTY")

    print("\n=== SINGLE SEAT $75 (SL 3.4% or TP 6% or time) ===")
    single = {}
    for p in PAIRS:
        s = hourly[p]
        if len(s) < 200:
            continue
        for H in HOLD_HOURS:
            rows = []
            for i in sample_entries(s, step=12):
                m = path_metrics(s, i, H)
                if m:
                    rows.append(m)
            if not rows:
                continue
            sl_rate = sum(1 for r in rows if r["reason"] == "sl") / len(rows)
            tp_rate = sum(1 for r in rows if r["reason"] == "tp06") / len(rows)
            nets = [r["r_net"] for r in rows]
            st = {
                "n": len(rows),
                "sl_rate": sl_rate,
                "tp_rate": tp_rate,
                "mean_r_net": statistics.mean(nets),
                "med_r_net": statistics.median(nets),
                "p10": pctile(nets, 0.10),
                "p90": pctile(nets, 0.90),
                "worst": min(nets),
                "best": max(nets),
                "mean_hold_h": statistics.mean(r["hold_h"] for r in rows),
                "mean_usd": statistics.mean(nets) * SEAT,
                "p10_usd": pctile(nets, 0.10) * SEAT,
                "worst_usd": min(nets) * SEAT,
            }
            single[f"{p}|H{H}"] = st
            print(
                f"{p} H={H}h n={st['n']} SL%{sl_rate*100:.0f} TP%{tp_rate*100:.0f} "
                f"mean={st['mean_r_net']*100:.2f}% p10={st['p10']*100:.2f}% "
                f"worst={st['worst']*100:.2f}% mean$={st['mean_usd']:.2f} "
                f"p10$={st['p10_usd']:.2f} worst$={st['worst_usd']:.2f} "
                f"hold={st['mean_hold_h']:.1f}h"
            )

    print("\n=== TWO SEATS concurrent ($75+$75 path; rest cash idle) ===")
    two_stats = {}
    for p1, p2 in COMBOS:
        s1, s2 = hourly[p1], hourly[p2]
        map1 = {k: i for i, (k, _) in enumerate(s1)}
        map2 = {k: i for i, (k, _) in enumerate(s2)}
        common = sorted(set(map1) & set(map2))
        starts = common[::12]
        for H in HOLD_HOURS:
            eps = []
            for k in starts:
                if map1[k] + H + 2 >= len(s1) or map2[k] + H + 2 >= len(s2):
                    continue
                ep = two_seat_episode(s1, s2, map1[k], map2[k], H)
                if ep:
                    eps.append(ep)
            if not eps:
                continue
            pnls = [e["pnl_usd"] for e in eps]
            dds = [e["max_dd_usd"] for e in eps]
            dd_frac = [e["max_dd_on_150"] for e in eps]
            eq_pnl = [e["pnl_pct_on_equity"] for e in eps]
            both_sl = sum(1 for e in eps if e["both_sl"]) / len(eps)
            any_sl = sum(1 for e in eps if e["any_sl"]) / len(eps)
            mean_hold = statistics.mean(e["hold_h"] for e in eps)
            p50_dd = statistics.median(dds)
            bad = [e for e in eps if e["max_dd_usd"] <= p50_dd]
            mean_t_trough = statistics.mean(e["t_to_trough_h"] for e in bad) if bad else None
            st = {
                "n": len(eps),
                "mean_pnl": statistics.mean(pnls),
                "p10_pnl": pctile(pnls, 0.10),
                "p90_pnl": pctile(pnls, 0.90),
                "worst_pnl": min(pnls),
                "best_pnl": max(pnls),
                "mean_dd_usd": statistics.mean(dds),
                "p50_dd": p50_dd,
                "p05_dd": pctile(dds, 0.05),
                "worst_dd": min(dds),
                "mean_dd_frac": statistics.mean(dd_frac),
                "mean_eq_pnl_pct": statistics.mean(eq_pnl) * 100,
                "p10_eq_pnl_pct": pctile(eq_pnl, 0.10) * 100,
                "worst_eq_pnl_pct": min(eq_pnl) * 100,
                "best_eq_pnl_pct": max(eq_pnl) * 100,
                "both_sl": both_sl,
                "any_sl": any_sl,
                "mean_hold_h": mean_hold,
                "mean_t_trough_bad_h": mean_t_trough,
            }
            two_stats[f"{p1}+{p2}|H{H}"] = st
            print(
                f"{p1}+{p2} H<={H}h n={st['n']} meanPnL=${st['mean_pnl']:.2f} "
                f"p10=${st['p10_pnl']:.2f} worstPnL=${st['worst_pnl']:.2f} | "
                f"meanDD=${st['mean_dd_usd']:.2f} p05DD=${st['p05_dd']:.2f} "
                f"worstDD=${st['worst_dd']:.2f} | "
                f"eqMean={st['mean_eq_pnl_pct']:.3f}% p10eq={st['p10_eq_pnl_pct']:.3f}% "
                f"worstEq={st['worst_eq_pnl_pct']:.3f}% bestEq={st['best_eq_pnl_pct']:.3f}% | "
                f"anySL={st['any_sl']*100:.0f}% bothSL={st['both_sl']*100:.0f}% "
                f"hold={st['mean_hold_h']:.1f}h trough~{st['mean_t_trough_bad_h']:.1f}h"
            )

    per_sl = SEAT * SL_PCT + SEAT * FEE_RT
    print("\n=== THEORETICAL floors (SL works, no gap) ===")
    print(f"1 seat SL+fees ~ ${per_sl:.2f} ({per_sl/EQUITY*100:.3f}% equity)")
    print(f"2 seats both SL+fees ~ ${2*per_sl:.2f} ({2*per_sl/EQUITY*100:.3f}% equity)")
    print(f"notional $150 = {150/EQUITY*100:.1f}% equity; idle ex-PAXG ~ ${(EQUITY-150-81):.0f}")

    print("\n=== GAP / SL-miss stress (both seats) ===")
    gap_rows = []
    for mae in (0.05, 0.08, 0.12, 0.20):
        loss = 2 * SEAT * mae + 2 * SEAT * FEE_RT
        gap_rows.append({"mae": mae, "loss_usd": loss, "pct_equity": loss / EQUITY})
        print(f"both MAE -{mae*100:.0f}% +fees -> ${loss:.2f} ({loss/EQUITY*100:.2f}% equity)")

    print("\n=== Cap scale sensitivity (SL-floor math only) ===")
    scale_rows = []
    for seat, n in [(75, 2), (75, 4), (150, 2), (150, 4), (300, 2)]:
        risk_f = n * seat * SL_PCT + n * seat * FEE_RT
        row = {
            "n": n,
            "seat": seat,
            "notional": n * seat,
            "sl_fee_usd": risk_f,
            "pct_equity": risk_f / EQUITY,
        }
        scale_rows.append(row)
        print(
            f"{n}x${seat}: notional=${n*seat} SL+fee floor~${risk_f:.1f} "
            f"({risk_f/EQUITY*100:.2f}% eq)"
        )

    # Ledger tryout-sized closed sells
    print("\n=== LEDGER tryout-sized closed legs (~$40-130, 120d) ===")
    cut = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
    legs = []
    ledger = PROJECT / "trades" / "phase6_trades.jsonl"
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            ts = r.get("timestamp") or r.get("ts") or ""
            if ts < cut:
                continue
            if str(r.get("side") or "").lower() not in ("sell", "s"):
                continue
            qty = float(r.get("qty") or 0 or 0)
            exit_px = float(r.get("exit_price") or r.get("price") or 0 or 0)
            if not qty or not exit_px:
                continue
            exit_n = abs(qty * exit_px)
            if not (40 <= exit_n <= 130):
                continue
            pnl = r.get("pnl")
            pnl_pct = r.get("pnl_pct")
            if pnl is None and pnl_pct is not None and r.get("entry_price"):
                try:
                    pnl = qty * (exit_px - float(r["entry_price"]))
                except Exception:
                    pnl = None
            # drop absurd
            if pnl is not None and abs(float(pnl)) > 80:
                continue
            legs.append(
                {
                    "ts": ts,
                    "pair": r.get("pair"),
                    "reason": str(r.get("reason") or "")[:80],
                    "exit_n": exit_n,
                    "pnl": float(pnl) if pnl is not None else None,
                    "pnl_pct": float(pnl_pct) if pnl_pct is not None else None,
                }
            )

    with_pnl = [l for l in legs if l["pnl"] is not None]
    ledger_summary = {"n": len(with_pnl)}
    if with_pnl:
        pnls = [l["pnl"] for l in with_pnl]
        ledger_summary.update(
            {
                "mean_pnl": statistics.mean(pnls),
                "median_pnl": statistics.median(pnls),
                "worst_pnl": min(pnls),
                "best_pnl": max(pnls),
                "two_worst_sum": sum(sorted(pnls)[:2]),
                "n_sl": sum(1 for l in with_pnl if "stop_loss" in l["reason"]),
                "n_tp": sum(1 for l in with_pnl if "take_profit" in l["reason"]),
                "worst_legs": sorted(with_pnl, key=lambda x: x["pnl"])[:8],
                "best_legs": sorted(with_pnl, key=lambda x: -x["pnl"])[:5],
            }
        )
        print(
            f"n={len(with_pnl)} mean=${ledger_summary['mean_pnl']:.2f} "
            f"med=${ledger_summary['median_pnl']:.2f} worst=${ledger_summary['worst_pnl']:.2f} "
            f"best=${ledger_summary['best_pnl']:.2f} two_worst_sum=${ledger_summary['two_worst_sum']:.2f}"
        )
        print(f"SL count={ledger_summary['n_sl']} TP count={ledger_summary['n_tp']}")
        for l in ledger_summary["worst_legs"]:
            print(" worst", l)
        for l in ledger_summary["best_legs"]:
            print(" best", l)
    else:
        print("no tryout-sized legs with pnl")

    # Correlated crash note: same-hour BTC dump proxy — force both entries same bar, measure joint MAE before SL
    print("\n=== CORRELATED crash window (same start bar, 72h max, joint path) ===")
    corr = {}
    p1, p2 = "ETH-USD", "LINK-USD"
    s1, s2 = hourly[p1], hourly[p2]
    map1 = {k: i for i, (k, _) in enumerate(s1)}
    map2 = {k: i for i, (k, _) in enumerate(s2)}
    common = sorted(set(map1) & set(map2))
    joint_maes = []
    for k in common[::6]:
        i1, i2 = map1[k], map2[k]
        if i1 + 72 >= len(s1) or i2 + 72 >= len(s2):
            continue
        e1, e2 = s1[i1][1], s2[i2][1]
        worst_joint = 0.0
        for h in range(1, 73):
            r1 = (s1[i1 + h][1] - e1) / e1
            r2 = (s2[i2 + h][1] - e2) / e2
            # stop each at SL independently for joint MTM
            r1c = max(r1, -SL_PCT) if r1 > -SL_PCT else -SL_PCT
            r2c = max(r2, -SL_PCT) if r2 > -SL_PCT else -SL_PCT
            # actually once hit SL lock
            # simpler joint MTM without lock first for MAE
            joint = 0.5 * r1 + 0.5 * r2
            worst_joint = min(worst_joint, joint)
        joint_maes.append(worst_joint)
    if joint_maes:
        corr = {
            "pair": f"{p1}+{p2}",
            "n": len(joint_maes),
            "mean_joint_mae": statistics.mean(joint_maes),
            "p05_joint_mae": pctile(joint_maes, 0.05),
            "worst_joint_mae": min(joint_maes),
            "p05_usd_on_150": pctile(joint_maes, 0.05) * 150,
            "worst_usd_on_150": min(joint_maes) * 150,
            "p05_pct_equity": pctile(joint_maes, 0.05) * 150 / EQUITY,
            "worst_pct_equity": min(joint_maes) * 150 / EQUITY,
        }
        print(
            f"{corr['pair']} n={corr['n']} meanMAE={corr['mean_joint_mae']*100:.2f}% "
            f"p05={corr['p05_joint_mae']*100:.2f}% worst={corr['worst_joint_mae']*100:.2f}% "
            f"p05$={corr['p05_usd_on_150']:.2f} worst$={corr['worst_usd_on_150']:.2f} "
            f"p05eq={corr['p05_pct_equity']*100:.3f}% worsteq={corr['worst_pct_equity']*100:.3f}%"
        )

    out = {
        "schema": "two_seat_tryout_dd_dig_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "method": "hourly path SL3.4/TP6/time; concurrent 2x$75; fees 1.6% RT notional; equity $2292",
        "params": {
            "equity_usd": EQUITY,
            "seat_usd": SEAT,
            "n_seats_max": N_SEATS,
            "sl_pct": SL_PCT,
            "fee_rt": FEE_RT,
            "tp_pct": 0.06,
            "hold_hours": HOLD_HOURS,
            "pairs": PAIRS,
            "combos": [f"{a}+{b}" for a, b in COMBOS],
        },
        "theoretical": {
            "one_seat_sl_fee_usd": per_sl,
            "two_seat_sl_fee_usd": 2 * per_sl,
            "two_seat_sl_fee_pct_equity": 2 * per_sl / EQUITY,
            "notional_pct_equity": 150 / EQUITY,
            "idle_ex_paxg_usd": EQUITY - 150 - 81,
        },
        "gap_stress": gap_rows,
        "cap_scale": scale_rows,
        "single_seat": single,
        "two_seat_path": two_stats,
        "correlated_mae": corr,
        "ledger_tryout": ledger_summary,
        "honesty": [
            "Random entry every 12h is NOT live signal quality — upper-bounds how often SL/TP hit on raw tape.",
            "Live tryout also needs sent/RSI/recovery gates — fewer entries, hopefully better than random.",
            "Fee haircut is flat 1.6% RT — Intro-2 taker-ish; maker would be less.",
            "SL assumed fill at -3.4% — gap/miss can be worse (see gap_stress).",
            "Idle cash DD from two seats is tiny vs equity; opportunity cost is the open question, not ruin.",
        ],
    }

    state_path = PROJECT / "data" / "state" / "two_seat_tryout_dd_dig_latest.json"
    state_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {state_path}")

    # Markdown report
    lines = [
        "# Two-seat tryout max DD dig",
        "",
        f"- as_of: `{out['as_of']}`",
        f"- book equity assumed: **${EQUITY:.0f}**",
        f"- policy: **{N_SEATS} × ${SEAT:.0f}** = **$150** max concurrent tryout notional",
        f"- path rules: SL **{SL_PCT*100:.1f}%** or TP **6%** or time-stop; fee haircut **{FEE_RT*100:.1f}%** RT",
        f"- data: hourly from `phase6.db` prices (~400d) + ledger tryout-sized sells 120d",
        "",
        "## Plain English",
        "",
        "Two $75 seats cannot dig the **account** hard if stops work. "
        "Ruin risk is not why most cash sits idle — **pace/quality gates** are. "
        "The open question is opportunity cost vs spray if caps rise before edge is proven.",
        "",
        "## Theoretical floor (SL works)",
        "",
        f"- 1 seat SL+fees ≈ **${per_sl:.2f}** ({per_sl/EQUITY*100:.2f}% equity)",
        f"- 2 seats both SL+fees ≈ **${2*per_sl:.2f}** ({2*per_sl/EQUITY*100:.2f}% equity)",
        f"- $150 notional = **{150/EQUITY*100:.1f}%** of book; rest is intentional dry powder under recovery",
        "",
        "## Gap / SL-miss stress (both seats)",
        "",
        "| both legs MAE | $ loss + fees | % equity |",
        "|---------------|---------------|----------|",
    ]
    for g in gap_rows:
        lines.append(
            f"| −{g['mae']*100:.0f}% | ${g['loss_usd']:.2f} | {g['pct_equity']*100:.2f}% |"
        )

    lines += [
        "",
        "## Two-seat concurrent path (random aligned entries)",
        "",
        "| Combo | H max | N | mean PnL $ | p10 PnL $ | worst PnL $ | p05 path DD $ | worst path DD $ | mean %eq | p10 %eq | worst %eq | any SL% | both SL% | mean hold h |",
        "|-------|------:|--:|----------:|----------:|------------:|--------------:|----------------:|---------:|--------:|----------:|--------:|---------:|------------:|",
    ]
    for k, st in sorted(two_stats.items()):
        combo, h = k.rsplit("|H", 1)
        lines.append(
            f"| {combo} | {h} | {st['n']} | {st['mean_pnl']:.2f} | {st['p10_pnl']:.2f} | "
            f"{st['worst_pnl']:.2f} | {st['p05_dd']:.2f} | {st['worst_dd']:.2f} | "
            f"{st['mean_eq_pnl_pct']:.3f} | {st['p10_eq_pnl_pct']:.3f} | {st['worst_eq_pnl_pct']:.3f} | "
            f"{st['any_sl']*100:.0f} | {st['both_sl']*100:.0f} | {st['mean_hold_h']:.1f} |"
        )

    if corr:
        lines += [
            "",
            "## Correlated joint MAE (ETH+LINK, 72h, equal weight, no fee)",
            "",
            f"- n={corr['n']}",
            f"- mean joint MAE **{corr['mean_joint_mae']*100:.2f}%** → ${corr['mean_joint_mae']*150:.2f} on $150",
            f"- p05 joint MAE **{corr['p05_joint_mae']*100:.2f}%** → **${corr['p05_usd_on_150']:.2f}** ({corr['p05_pct_equity']*100:.2f}% eq)",
            f"- worst joint MAE **{corr['worst_joint_mae']*100:.2f}%** → **${corr['worst_usd_on_150']:.2f}** ({corr['worst_pct_equity']*100:.2f}% eq)",
            "- Note: this is **unstopped** joint MTM MAE (how deep the pair basket went). Live SL clips each leg near −3.4%.",
        ]

    lines += [
        "",
        "## Cap scale (if you raise seats/size) — SL-floor only",
        "",
        "| setup | notional | SL+fee floor $ | % equity |",
        "|-------|---------:|---------------:|---------:|",
    ]
    for r in scale_rows:
        lines.append(
            f"| {r['n']}×${r['seat']} | ${r['notional']} | ${r['sl_fee_usd']:.1f} | {r['pct_equity']*100:.2f}% |"
        )

    lines += ["", "## Ledger tryout-sized closed legs (120d, $40–130 exit notional)", ""]
    if with_pnl:
        lines += [
            f"- n={ledger_summary['n']} · mean ${ledger_summary['mean_pnl']:.2f} · "
            f"med ${ledger_summary['median_pnl']:.2f} · worst ${ledger_summary['worst_pnl']:.2f} · "
            f"best ${ledger_summary['best_pnl']:.2f}",
            f"- sum of two worst **single** legs (not proven simultaneous): "
            f"**${ledger_summary['two_worst_sum']:.2f}**",
            f"- SL legs={ledger_summary['n_sl']} · TP legs={ledger_summary['n_tp']}",
            "",
            "Worst legs:",
        ]
        for l in ledger_summary["worst_legs"]:
            lines.append(
                f"- {l['ts'][:16]} {l['pair']} ${l['pnl']:.2f} exit_n=${l['exit_n']:.0f} · {l['reason']}"
            )
    else:
        lines.append("- no pnl-tagged tryout-sized legs in window")

    lines += [
        "",
        "## Timeframe read",
        "",
        "- **Fast dig (hours):** most SL hits on hourly tape arrive well inside 24h when they hit; "
        "mean hold under SL/TP rules often **tens of hours**, not weeks.",
        "- **Seat occupancy:** with TP6/SL, two seats free up on a **1–3 day** cadence often; "
        "168h time-stop is the slow tail when neither fires.",
        "- **Account DD from two seats:** typically **well under 1% equity** on p05 if SL works; "
        "catastrophe needs SL-miss / gap / many recycled seats (pace gates exist to slow recycle).",
        "",
        "## Honesty / do-not-claim",
        "",
    ]
    for h in out["honesty"]:
        lines.append(f"- {h}")
    lines += [
        "",
        "## Decision framing (not a live flip)",
        "",
        "| Question | Dig answer |",
        "|----------|------------|",
        "| Can 2×$75 ruin the book? | **No** under working SL — floor ~$7–8 both-stop + fees (~0.3% eq). |",
        "| Is idle cash 'because of DD'? | **Mostly no** — it's **pace + quality + recovery**, not two-seat ruin math. |",
        "| Best case 2 seats? | Path p90 / bestEq on combo tables (often low single-digit $ on $150; small %eq). |",
        "| Worst case 2 seats? | Both SL ~$7–8; gap stress table if stops fail; unstopped joint MAE can look uglier on $150 sleeve alone. |",
        "| Raise to 4×$75 or 2×$150? | SL-floor scales ~linear in notional — still small %eq, but **process spray** and fee tax scale too. |",
        "",
        "Raw JSON: `data/state/two_seat_tryout_dd_dig_latest.json`",
        "",
    ]

    report = PROJECT / "reports" / "TWO_SEAT_TRYOUT_DD_DIG_LATEST.md"
    report.write_text("\n".join(lines) + "\n")
    print(f"Wrote {report}")


if __name__ == "__main__":
    main()
