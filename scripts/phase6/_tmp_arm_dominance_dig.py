#!/usr/bin/env python3
"""One-shot dig: rel_btc_stable vs risk_adj_mom dominance / regime splits."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import mean, median

ROOT = Path("/home/brad/projects/crypto-trading-bot")
CF = ROOT / "data/state/basket_swap_shadow_counterfactual_latest.json"
BOARD = ROOT / "data/state/basket_swap_confidence_board_latest.json"
DECISION = ROOT / "data/state/basket_swap_brad_decision.json"
# REGIME = ROOT / "data/state/phase6_runner_state.json" # not used here
OUT = ROOT / "data/state/arm_dominance_dig_latest.json"

HMAP = {"1d": "24h", "3d": "72h", "7d": "168h", "14d": "336h"}
FOCUS_ARMS = ["rel_btc_stable", "risk_adj_mom"]


def _parse_ts(s: str | None):
    if not s:
        return None
    t = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _num(x, default=None):
    try:
        if x is None:
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def main() -> None:
    o = json.loads(CF.read_text())
    raw_rows = o.get("unique_results") or o.get("results") or []

    # Normalize rows
    norm = []
    for r in raw_rows:
        ts = _parse_ts(r.get("ts"))
        arm = str(r.get("arm") or "")
        horizons = r.get("horizons") or {}
        item = {
            "ts": ts,
            "arm": arm,
            "add": r.get("add"),
            "remove": r.get("remove"),
         }
        # Extract relevant horizon data
        for canon_h, raw_h_key in HMAP.items():
            hh = horizons.get(raw_h_key) or {}
            if hh.get("status") and hh.get("status") != "ok":
                item[f"ex_{canon_h}"] = None
                item[f"btc_{canon_h}"] = None
            else:
                item[f"ex_{canon_h}"] = _num(hh.get("excess_pct"))
                item[f"btc_{canon_h}"] = _num(hh.get("btc_ret_pct"))
                item[f"add_{canon_h}"] = _num(hh.get("add_ret_pct"))
                item[f"rem_{canon_h}"] = _num(hh.get("rem_ret_pct"))
        # Add 'to_now' metrics for correlation analysis
        item["excess_to_now"] = _num(r.get("excess_to_now"))
        item["ret_btc_to_now"] = _num(r.get("ret_btc_to_now"))
        norm.append(item)

    # --- Overall performance summary ---
    summary = {}
    all_arms = FOCUS_ARMS + ["baseline_hybrid", "anti_pump", "dual_agree"]
    for a in all_arms:
        s = {"n": 0}
        for h in HMAP:
            xs = [r[f"ex_{h}"] for r in norm if r["arm"] == a and r.get(f"ex_{h}") is not None]
            s[h] = {
                "n": len(xs),
                "mean_ex": round(mean(xs), 4) if xs else None,
                "med_ex": round(median(xs), 4) if xs else None,
                "hit": round(mean([1 if x > 0 else 0 for x in xs]), 4) if xs else None,
            }
        s["n"] = len([r for r in norm if r["arm"] == a])
        summary[a] = s

    # --- Rolling daily leadership (ex_7d) ---
    by_day = defaultdict(lambda: defaultdict(list))
    for r in norm:
        if r["arm"] not in FOCUS_ARMS or r["ts"] is None or r.get("ex_7d") is None:
            continue
        day = r["ts"].astimezone(timezone.utc).date().isoformat()
        by_day[day][r["arm"]].append(r["ex_7d"])

    lead_series = []
    for d in sorted(by_day):
        cell = {"day": d}
        for a in FOCUS_ARMS:
            xs = by_day[d][a]
            cell[a] = mean(xs) if xs else None
            cell[f"{a}_n"] = len(xs)
        a_ex = cell.get("rel_btc_stable")
        b_ex = cell.get("risk_adj_mom")
        if a_ex is None and b_ex is None:
            leader = None
        elif a_ex is None:
            leader = "risk_adj_mom"
        elif b_ex is None:
            leader = "rel_btc_stable"
        else:
            leader = "rel_btc_stable" if a_ex >= b_ex else "risk_adj_mom"
            cell["gap_rel_minus_ram"] = round(a_ex - b_ex, 4)
        cell["leader"] = leader
        lead_series.append(cell)

    # Compress consecutive leadership into runs
    runs = []
    for cell in lead_series:
        if not cell.get("leader"):
            continue
        if not runs or runs[-1]["leader"] != cell["leader"]:
            runs.append(
                {
                    "leader": cell["leader"],
                    "start": cell["day"],
                    "end": cell["day"],
                    "days": 1,
                    "gaps": [cell.get("gap_rel_minus_ram")],
                }
            )
        else:
            runs[-1]["end"] = cell["day"]
            runs[-1]["days"] += 1
            runs[-1]["gaps"].append(cell.get("gap_rel_minus_ram"))
    for run in runs:
        gs = [g for g in run["gaps"] if g is not None]
        run["mean_gap"] = round(mean(gs), 4) if gs else None
        del run["gaps"]

    # --- Weekly leadership (ex_7d) ---
    weekly = defaultdict(lambda: defaultdict(list))
    for r in norm:
        if r["arm"] not in FOCUS_ARMS or r["ts"] is None or r.get("ex_7d") is None:
            continue
        iso = r["ts"].astimezone(timezone.utc).isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        weekly[key][r["arm"]].append(r["ex_7d"])
    week_board = []
    for w in sorted(weekly):
        row = {"week": w}
        for a in FOCUS_ARMS:
            xs = weekly[w][a]
            row[f"{a}_n"] = len(xs)
            row[f"{a}_ex7"] = round(mean(xs), 4) if xs else None
        ra, rb = row.get("rel_btc_stable_ex7"), row.get("risk_adj_mom_ex7")
        if ra is None and rb is None:
            row["leader"] = None
        elif ra is None:
            row["leader"] = "risk_adj_mom"
        elif rb is None:
            row["leader"] = "rel_btc_stable"
        else:
            row["leader"] = "rel_btc_stable" if ra >= rb else "risk_adj_mom"
            row["gap"] = round(ra - rb, 4)
        week_board.append(row)

    # --- Two-slice stability (ex_7d) ---
    timed_for_slice = [r for r in norm if r["arm"] in FOCUS_ARMS and r["ts"] is not None and r.get("ex_7d") is not None]
    timed_for_slice.sort(key=lambda r: r["ts"])
    slices = {}
    if timed_for_slice:
        mid_ts = timed_for_slice[len(timed_for_slice) // 2]["ts"]
        for name, subset in (
            ("early", [r for r in timed_for_slice if r["ts"] <= mid_ts]),
            ("late", [r for r in timed_for_slice if r["ts"] > mid_ts]),
        ):
            slices[name] = {}
            for a in FOCUS_ARMS:
                xs = [r["ex_7d"] for r in subset if r["arm"] == a]
                slices[name][a] = {
                    "n": len(xs),
                    "mean_ex7": round(mean(xs), 4) if xs else None,
                    "hit": round(mean([1 if x > 0 else 0 for x in xs]), 4) if xs else None,
                    "t0": subset[0]["ts"].isoformat() if subset else None,
                    "t1": subset[-1]["ts"].isoformat() if subset else None,
                }
            ra = slices[name]["rel_btc_stable"].get("mean_ex7")
            rb = slices[name]["risk_adj_mom"].get("mean_ex7")
            if ra is not None and rb is not None:
                slices[name]["leader"] = "rel_btc_stable" if ra >= rb else "risk_adj_mom"
                slices[name]["gap"] = round(ra - rb, 4)

    # --- Paired same-day proposals (ex_7d) ---
    day_arms_paired = defaultdict(dict)
    for r in norm:
        if r["arm"] not in FOCUS_ARMS or r["ts"] is None or r.get("ex_7d") is None:
            continue
        d = r["ts"].astimezone(timezone.utc).date().isoformat()
        day_arms_paired[d].setdefault(r["arm"], []).append(r["ex_7d"])
    both_days = 0
    rel_wins = 0
    ram_wins = 0
    gaps = []
    for d, m in sorted(day_arms_paired.items()):
        if "rel_btc_stable" in m and "risk_adj_mom" in m:
            both_days += 1
            a_ex = mean(m["rel_btc_stable"])
            b_ex = mean(m["risk_adj_mom"])
            g = a_ex - b_ex
            gaps.append(g)
            if a_ex >= b_ex:
                rel_wins += 1
            else:
                ram_wins += 1
    paired_summary = {
        "days_both_fired": both_days,
        "rel_wins": rel_wins,
        "ram_wins": ram_wins,
        "mean_gap_rel_minus_ram": round(mean(gaps), 4) if gaps else None,
        "med_gap": round(median(gaps), 4) if gaps else None,
        "rel_win_rate": round(rel_wins / both_days, 4) if both_days else None,
    }

    # --- BTC 7d tape conditioning ---
    btc_regime_map = {}
    btc_path = ROOT / "data/ohlcv/BTC-USD_1d_coinbase.json"
    if btc_path.exists():
        try:
            btc_data = json.loads(btc_path.read_text())
            candles = btc_data if isinstance(btc_data, list) else btc_data.get("candles") or []
            closes_by_date = {}
            for c in candles:
                if isinstance(c, dict):
                    ts = _parse_ts(str(c.get("time") or c.get("ts") or ""))
                    cl = _num(c.get("close") or c.get("c"))
                elif isinstance(c, (list, tuple)) and len(c) >= 5:
                    ts = _parse_ts(str(c[0])) if isinstance(c[0], str) else datetime.fromtimestamp(float(c[0])/1000 if c[0] > 1e12 else float(c[0]), tz=timezone.utc)
                    cl = _num(c[4])
                else: continue
                if ts and cl is not None: closes_by_date[ts.date().isoformat()] = cl
            
            sorted_dates = sorted(closes_by_date.keys())
            for i, d in enumerate(sorted_dates):
                if i < 6: continue # Need 7 days of data
                prev_d = sorted_dates[i-6] # This looks back 6 to get 7th day
                prev_close = closes_by_date.get(prev_d)
                current_close = closes_by_date.get(d)
                if prev_close and current_close:
                    ret7 = (current_close / prev_close - 1.0) * 100.0
                    if ret7 >= 2.0: label = "btc_up"
                    elif ret7 <= -2.0: label = "btc_down"
                    else: label = "btc_chop"
                    btc_regime_map[d] = {"btc_ret_7d": round(ret7, 4), "btc_tape": label}
        except Exception as e:
            print(f"Error loading BTC data: {e}")

    cond_perf_by_btc_tape = defaultdict(lambda: defaultdict(list))
    for r in norm:
        if r["arm"] not in FOCUS_ARMS or r["ts"] is None or r.get("ex_7d") is None:
            continue
        d = r["ts"].astimezone(timezone.utc).date().isoformat()
        tape_label = (btc_regime_map.get(d) or {}).get("btc_tape") or "unknown"
        cond_perf_by_btc_tape[tape_label][r["arm"]].append(r["ex_7d"])
    
    cond_board = {}
    for lab in sorted(k for k in cond_perf_by_btc_tape if not k.startswith("_")):
        cond_board[lab] = {}
        for a in FOCUS_ARMS:
            xs = cond_perf_by_btc_tape[lab][a]
            cond_board[lab][a] = {
                "n": len(xs),
                "mean_ex7": round(mean(xs), 4) if xs else None,
                "hit": round(mean([1 if x > 0 else 0 for x in xs]), 4) if xs else None,
            }
        ra = cond_board[lab]["rel_btc_stable"].get("mean_ex7")
        rb = cond_board[lab]["risk_adj_mom"].get("mean_ex7")
        if ra is None and rb is None:
            cond_board[lab]["leader"] = None
        elif ra is None:
            cond_board[lab]["leader"] = "risk_adj_mom"
        elif rb is None:
            cond_board[lab]["leader"] = "rel_btc_stable"
        else:
            cond_board[lab]["leader"] = "rel_btc_stable" if ra >= rb else "risk_adj_mom"
            cond_board[lab]["gap"] = round(ra - rb, 4)

    # --- Correlation-ish: excess_to_now vs ret_btc_to_now ---
    corr_analysis = {}
    for a in FOCUS_ARMS:
        xs = [(r["ret_btc_to_now"], r["excess_to_now"]) for r in norm 
              if r["arm"] == a and r["ret_btc_to_now"] is not None and r["excess_to_now"] is not None]
        if len(xs) < 5:
            corr_analysis[a] = {"n": len(xs), "status": "thin data"}
            continue
        bx = [x[0] for x in xs]; ex = [x[1] for x in xs]
        mb, me = mean(bx), mean(ex)
        nume = sum((b - mb) * (e - me) for b, e in xs)
        den = (sum((b - mb) ** 2 for b in bx) * sum((e - me) ** 2 for e in ex)) ** 0.5
        corr = nume / den if den else None
        up = [e for b, e in xs if b >= 2]; dn = [e for b, e in xs if b <= -2]; ch = [e for b, e in xs if -2 < b < 2]
        corr_analysis[a] = {
            "n": len(xs),
            "corr": round(corr, 3) if corr is not None else None,
            "when_btc_up_path_mean_ex": round(mean(up), 3) if up else None, "n_up": len(up),
            "when_btc_down_path_mean_ex": round(mean(dn), 3) if dn else None, "n_dn": len(dn),
            "when_btc_chop_path_mean_ex": round(mean(ch), 3) if ch else None, "n_chop": len(ch),
        }

    # --- Verdict logic ---
    weekly_leaders = [w["leader"] for w in week_board if w.get("leader")]
    flip_count_weekly = sum(1 for i in range(1, len(weekly_leaders)) if weekly_leaders[i] != weekly_leaders[i - 1])
    late_slice_leader = (slices.get("late") or {}).get("leader")
    early_slice_leader = (slices.get("early") or {}).get("leader")
    cond_leaders = {k: v.get("leader") for k, v in cond_board.items()}

    # Get HC status for rel_btc_stable from board
    hc_rel_btc_stable = False
    board_data = json.loads(BOARD.read_text()) if BOARD.exists() else {}
    for arm_data in board_data.get("arms", []):
        if arm_data.get("arm") == "rel_btc_stable":
            hc_rel_btc_stable = arm_data.get("high_confidence", False)
            break

    decision_data = json.loads(DECISION.read_text()) if DECISION.exists() else {}

    verdict = {
        "plain_english": None,
        "dominant_now": late_slice_leader or decision_data.get("preferred_arm"),
        "should_become_sole_dominant": False,
        "reason_codes": [],
        "alternating_evidence": False,
        "weekly_flip_count": flip_count_weekly,
        "early_slice_leader": early_slice_leader,
        "late_slice_leader": late_slice_leader,
        "paired_days": paired_summary,
        "btc_tape_conditioned_leaders": cond_leaders,
        "hc_rel_btc_stable": hc_rel_btc_stable,
    }

    # Check for alternating evidence
    if flip_count_weekly >= 2 or (early_slice_leader and late_slice_leader and early_slice_leader != late_slice_leader):
        verdict["alternating_evidence"] = True
        verdict["reason_codes"].append("lead_flips_across_slices_or_weeks")
        verdict["plain_english"] = (
            "Lead flips across time/slices/weeks, indicating regime-sensitive rotation. "
            "Treat as two strong shadow arms, not a single champion. "
            "Keep dual collection; paper-primary should follow the current HC leader without deleting the other."
        )
    
    # If not alternating, check if one is consistently dominant
    elif late_slice_leader == early_slice_leader and late_slice_leader is not None:
        if late_slice_leader == "rel_btc_stable" and (paired_summary.get("rel_win_rate") or 0) >= 0.6 and hc_rel_btc_stable:
            verdict["plain_english"] = (
                "rel_btc_stable shows consistent leadership across slices and paired days, "
                "and has high confidence. It should remain the paper-primary. "
                "However, not enough evidence to declare it *sole* dominant or to enable live swaps."
            )
            verdict["reason_codes"].append("rel_btc_stable_consistent_lead_and_hc")
        elif late_slice_leader == "risk_adj_mom": # Consistent, but maybe not HC or paired win rate
            verdict["plain_english"] = (
                "risk_adj_mom shows consistent leadership across slices. "
                "Further analysis needed if it should become paper-primary (e.g., check HC, paired win rate)."
            )
            verdict["reason_codes"].append("risk_adj_mom_consistent_lead")
        else:
            verdict["plain_english"] = (
                "Leadership is consistent within slices, but other factors (HC, paired days) are not decisive. "
                "Keep preferred_arm as operator attention pointer only."
            )
            verdict["reason_codes"].append("consistent_but_not_decisive")
    else:
        verdict["plain_english"] = (
            "Insufficient stable separation to declare a permanent dominant arm due to mixed signals or thin data. "
            "Keep preferred_arm as operator attention pointer only."
        )
        verdict["reason_codes"].append("insufficient_separation")

    # If conditioned leaders disagree across BTC tapes, note it
    btc_tape_leaders = [cond_leaders.get(x) for x in ("btc_up", "btc_down", "btc_chop") if cond_leaders.get(x)]
    if len(set(btc_tape_leaders)) > 1:
        verdict["reason_codes"].append("btc_tape_conditional_leader_disagrees")
        verdict["plain_english"] = (
            (verdict["plain_english"] or "")
            + " BTC tape split changes which arm leads — classic regime-conditional edge, "
            "not one arm forever. This reinforces the need for continued dual collection." # Additive to previous verdict
        ).strip()


    out = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "cf_as_of": o.get("as_of"),
        "summary_by_arm": summary,
        "weekly_board": week_board,
        "lead_runs_daily": runs,
        "two_slice": slices,
        "btc_tape_conditioned": cond_board,
        "paired_days": paired_summary,
        "corr_analysis": corr_analysis,
        "board_status": board_data.get("status"),
        "preferred_arm": decision_data.get("preferred_arm"),
        "live_membership_swaps": decision_data.get("live_membership_swaps"),
        "verdict": verdict,
        "honesty": [
            "L1 CF excess is ADD vs REMOVE forward path — no stops, no fees, not live book PnL.",
            "Dominance here is shadow-selector leadership, not proven live alpha.",
            "Do not promote live_membership_swaps from this dig alone.",
        ],
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print("\nVERDICT:", json.dumps(verdict, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
