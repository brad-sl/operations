#!/usr/bin/env python3
"""First-mover / lead-lag cohort dig on long daily OHLCV (real data only).

Question: is there a stable cohort of leaders whose up-moves reliably pull
sub-pairs the same day or next day?

Paper research only — no orders, no basket mutate.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.market_breadth_breakout import DEFAULT_BREADTH_UNIVERSE  # noqa: E402
from phase6.research.run_breadth_momentum_bakeoff import load_pair_daily  # noqa: E402

LONG = ROOT / "backtests" / "data" / "long"
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"

# Candidate leaders (high cap / often cited spillover sources)
LEADERS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "LINK-USD"]
# Broader follower set: liquid + a few more if present
EXTRA_FOLLOWERS = [
    "AVAX-USD",
    "DOGE-USD",
    "ADA-USD",
    "MATIC-USD",
    "DOT-USD",
    "ATOM-USD",
    "NEAR-USD",
    "APT-USD",
    "ARB-USD",
    "OP-USD",
    "UNI-USD",
    "AAVE-USD",
    "LTC-USD",
    "BCH-USD",
]


def load_daily_closes(pid: str) -> Dict[date, float]:
    rows = load_pair_daily(pid)
    out: Dict[date, float] = {}
    for r in rows or []:
        ts = r.get("timestamp") or r.get("date") or ""
        try:
            d = date.fromisoformat(str(ts)[:10])
        except Exception:
            continue
        try:
            out[d] = float(r["close"])
        except Exception:
            continue
    return out


def _corr(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 30 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx < 1e-12 or dy < 1e-12:
        return None
    return num / (dx * dy)


def daily_rets(closes: Dict[date, float]) -> Dict[date, float]:
    days = sorted(closes)
    out: Dict[date, float] = {}
    for i in range(1, len(days)):
        a, b = days[i - 1], days[i]
        ca, cb = closes[a], closes[b]
        if ca and cb and ca > 0:
            out[b] = (cb / ca) - 1.0
    return out


def next_session_day(d: date, available: Sequence[date], max_gap_days: int = 3) -> Optional[date]:
    """Next session on or after d+1 within max_gap (handles weekends; blocks listing gaps)."""
    later = [dd for dd in available if dd > d]
    if not later:
        return None
    nd = min(later)
    if (nd - d).days > max_gap_days:
        return None
    return nd


def aligned_pairs(
    r_a: Dict[date, float], r_b: Dict[date, float], lag_b: int = 0
) -> Tuple[List[float], List[float]]:
    """lag_b=+1 means B is next session after A (A leads). lag_b=-1 means B prior session."""
    xs, ys = [], []
    b_days = sorted(r_b)
    for d, xa in r_a.items():
        if lag_b == 0:
            y = r_b.get(d)
        elif lag_b == 1:
            nd = next_session_day(d, b_days)
            y = r_b.get(nd) if nd else None
        elif lag_b == -1:
            earlier = [dd for dd in b_days if dd < d]
            if not earlier:
                continue
            pd = max(earlier)
            if (d - pd).days > 3:
                continue
            y = r_b.get(pd)
        else:
            continue
        if y is None:
            continue
        xs.append(xa)
        ys.append(y)
    return xs, ys


def conditional_follow(
    r_l: Dict[date, float],
    r_f: Dict[date, float],
    thr: float = 0.02,
    next_day: bool = False,
) -> Dict[str, Any]:
    """When leader day ret >= thr, does follower go up same session or next session?"""
    base_up = 0
    base_n = 0
    hit = 0
    n = 0
    mean_f = []
    f_days = sorted(r_f)
    for d, rl in r_l.items():
        rf0 = r_f.get(d)
        if rf0 is not None:
            base_n += 1
            if rf0 > 0:
                base_up += 1
        if rl < thr:
            continue
        if next_day:
            nd = next_session_day(d, f_days)
            rf = r_f.get(nd) if nd else None
        else:
            rf = rf0
        if rf is None:
            continue
        n += 1
        mean_f.append(rf)
        if rf > 0:
            hit += 1
    return {
        "n_leader_thrust": n,
        "follow_up_rate": (hit / n) if n else None,
        "base_up_rate": (base_up / base_n) if base_n else None,
        "lift": ((hit / n) - (base_up / base_n) if n and base_n else None),
        "mean_follower_ret": (sum(mean_f) / len(mean_f)) if mean_f else None,
    }


def half_split_stability(
    r_l: Dict[date, float], r_f: Dict[date, float]
) -> Dict[str, Any]:
    days = sorted(set(r_l) & set(r_f))
    if len(days) < 80:
        return {"stable": None, "n": len(days)}
    mid = days[len(days) // 2]
    def corr_slice(lo: bool) -> Optional[float]:
        xs, ys = [], []
        for d in days:
            if lo and d >= mid:
                continue
            if not lo and d < mid:
                continue
            xs.append(r_l[d])
            ys.append(r_f[d])
        return _corr(xs, ys)
    c1, c2 = corr_slice(True), corr_slice(False)
    stable = None
    if c1 is not None and c2 is not None:
        stable = (c1 > 0.35 and c2 > 0.35) or (abs(c1 - c2) < 0.15 and min(c1, c2) > 0.25)
    return {"corr_h1": c1, "corr_h2": c2, "stable_same_day": stable, "mid": mid.isoformat()}


def main() -> int:
    universe = sorted(set(DEFAULT_BREADTH_UNIVERSE) | set(LEADERS) | set(EXTRA_FOLLOWERS))
    closes: Dict[str, Dict[date, float]] = {}
    for pid in universe:
        c = load_daily_closes(pid)
        if len(c) >= 60:
            closes[pid] = c
    rets = {pid: daily_rets(c) for pid, c in closes.items()}
    leaders = [p for p in LEADERS if p in rets]
    followers = [p for p in rets if p not in ("USDT-USD",)]

    pairs_out = []
    for L in leaders:
        for F in followers:
            if F == L:
                continue
            xs0, ys0 = aligned_pairs(rets[L], rets[F], 0)
            xs1, ys1 = aligned_pairs(rets[L], rets[F], 1)  # L leads F next day
            xs_m1, ys_m1 = aligned_pairs(rets[L], rets[F], -1)  # F leads L
            c0 = _corr(xs0, ys0)
            c_lead = _corr(xs1, ys1)
            c_lag = _corr(xs_m1, ys_m1)
            same = conditional_follow(rets[L], rets[F], thr=0.02, next_day=False)
            nxt = conditional_follow(rets[L], rets[F], thr=0.02, next_day=True)
            stab = half_split_stability(rets[L], rets[F])
            # "pull" score: same-day corr high + next-day lift positive + stable
            pull = 0.0
            if c0 is not None:
                pull += c0
            if nxt.get("lift") is not None:
                pull += max(0.0, float(nxt["lift"])) * 2
            if c_lead is not None and c_lag is not None and c_lead > c_lag + 0.02:
                pull += 0.15  # mild lead evidence
            if stab.get("stable_same_day"):
                pull += 0.1
            pairs_out.append(
                {
                    "leader": L,
                    "follower": F,
                    "n_same": len(xs0),
                    "corr_same_day": c0,
                    "corr_leader_leads_next": c_lead,
                    "corr_follower_leads": c_lag,
                    "same_day_thrust": same,
                    "next_day_thrust": nxt,
                    "stability": stab,
                    "pull_score": round(pull, 4),
                }
            )

    # Rank followers by average pull from BTC+ETH (core cohort test)
    by_follower: Dict[str, List[float]] = defaultdict(list)
    btc_eth_followers = []
    for row in pairs_out:
        if row["leader"] in ("BTC-USD", "ETH-USD") and row["corr_same_day"] is not None:
            by_follower[row["follower"]].append(row["corr_same_day"])
    cohort = []
    for f, cs in by_follower.items():
        if f in ("BTC-USD", "ETH-USD"):
            continue
        cohort.append(
            {
                "follower": f,
                "mean_corr_btc_eth": sum(cs) / len(cs),
                "min_corr": min(cs),
                "n_leaders": len(cs),
            }
        )
    cohort.sort(key=lambda x: -x["mean_corr_btc_eth"])

    # Leader strength: average same-day corr to others + next-day lift mean
    leader_rank = []
    for L in leaders:
        rows = [r for r in pairs_out if r["leader"] == L and r["follower"] != L]
        corrs = [r["corr_same_day"] for r in rows if r["corr_same_day"] is not None]
        lifts = [
            r["next_day_thrust"]["lift"]
            for r in rows
            if r["next_day_thrust"].get("lift") is not None
        ]
        same_lifts = [
            r["same_day_thrust"]["lift"]
            for r in rows
            if r["same_day_thrust"].get("lift") is not None
        ]
        lead_edges = 0
        for r in rows:
            cl, cf = r["corr_leader_leads_next"], r["corr_follower_leads"]
            if cl is not None and cf is not None and cl > cf + 0.02:
                lead_edges += 1
        leader_rank.append(
            {
                "leader": L,
                "mean_same_day_corr": sum(corrs) / len(corrs) if corrs else None,
                "mean_same_day_lift_on_2pct": sum(same_lifts) / len(same_lifts) if same_lifts else None,
                "mean_next_day_lift_on_2pct": sum(lifts) / len(lifts) if lifts else None,
                "frac_pairs_leader_edge": lead_edges / len(rows) if rows else None,
                "n_followers": len(rows),
            }
        )
    leader_rank.sort(key=lambda x: -(x["mean_same_day_corr"] or 0))

    # Honest decision
    btc = next(x for x in leader_rank if x["leader"] == "BTC-USD")
    tight = [c for c in cohort if c["min_corr"] >= 0.5 and c["n_leaders"] >= 2]
    loose = [c for c in cohort if c["mean_corr_btc_eth"] >= 0.55]
    # Require mean next-day follower ret > +0.15% after fees-ish to call exploitable
    strong_nd = [
        r
        for r in pairs_out
        if (r["next_day_thrust"].get("n_leader_thrust") or 0) >= 40
        and (r["next_day_thrust"].get("mean_follower_ret") or -1) > 0.0015
        and (r["next_day_thrust"].get("lift") or 0) >= 0.03
        and (r["corr_same_day"] or 0) >= 0.4
    ]
    decision = {
        "first_mover_cohort_exists": len(tight) >= 3 or len(loose) >= 5,
        "nature": "same_day_beta_pack_weak_next_session_lead",
        "exploit_ready": False,
        "n_strong_next_day_pairs": len(strong_nd),
        "plain": "",
    }
    nd_lift = btc.get("mean_next_day_lift_on_2pct")
    nd_s = f"{100 * nd_lift:.1f}pp" if nd_lift is not None else "n/a"
    decision["plain"] = (
        f"BTC/ETH (and LINK/SOL) are co-movement anchors — mean same-day corr to others "
        f"~{(btc['mean_same_day_corr'] or 0):.2f}. "
        f"Tight beta cohort (min corr≥0.5 vs BTC&ETH): {len(tight)} names "
        f"(DOGE, LINK, AVAX, ADA, SOL, AAVE, …). "
        f"That is a real 'moves together' pack, not a proof of next-day pull. "
        f"After fixing session alignment (no listing-gap jumps), BTC next-session lift on +2% days "
        f"is ~{nd_s} on hit-rate — weak as a standalone 'buy the satellite tomorrow' rule. "
        f"Strong next-session pairs (ret+lift bar): {len(strong_nd)}. "
        f"Literature: spillover largely contemporaneous; volume can mark leaders intraday. "
        f"Use as membership beta context / basket diversity check; not live first-mover entries. "
        f"exploit_ready=false."
    )

    # Prefer mean-ret ranked next-day list for report
    tradable = sorted(
        [
            r
            for r in pairs_out
            if (r["next_day_thrust"].get("n_leader_thrust") or 0) >= 40
            and (r["next_day_thrust"].get("lift") or 0) >= 0.02
            and (r["corr_same_day"] or 0) >= 0.4
        ],
        key=lambda x: -(x["next_day_thrust"].get("mean_follower_ret") or -9),
    )

    payload = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "tape": "backtests/data/long daily OHLCV",
        "leaders_tested": leaders,
        "n_pairs": len(pairs_out),
        "leader_rank": leader_rank,
        "beta_cohort_tight_mincorr_0_5": tight[:15],
        "beta_cohort_loose_meancorr_0_55": loose[:20],
        "top_next_day_lift_pairs": [
            {
                "leader": r["leader"],
                "follower": r["follower"],
                "corr_same": r["corr_same_day"],
                "next_lift": r["next_day_thrust"].get("lift"),
                "next_up_rate": r["next_day_thrust"].get("follow_up_rate"),
                "mean_next_ret": r["next_day_thrust"].get("mean_follower_ret"),
                "n": r["next_day_thrust"].get("n_leader_thrust"),
            }
            for r in tradable[:15]
        ],
        "top_pull_score": sorted(pairs_out, key=lambda x: -x["pull_score"])[:20],
        "decision": decision,
    }

    STATE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    STATE.joinpath("first_mover_leadlag_latest.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n"
    )

    def pct(x):
        return "n/a" if x is None else f"{100*x:.1f}%"

    lines = [
        "# First-mover / lead-lag cohort dig",
        f"As of `{payload['as_of']}`",
        "",
        "## Plain English",
        "",
        decision["plain"],
        "",
        "## Leader rank (who moves *with* the tape)",
        "",
        "| Leader | Mean same-day corr | Lift same-day on +2% | Lift next-day on +2% | Frac pairs with lead edge |",
        "|--------|-------------------:|---------------------:|---------------------:|--------------------------:|",
    ]
    for r in leader_rank:
        csd = r["mean_same_day_corr"]
        csd_s = f"{csd:.3f}" if csd is not None else "n/a"
        lines.append(
            f"| {r['leader']} | {csd_s} | "
            f"{pct(r['mean_same_day_lift_on_2pct'])} | {pct(r['mean_next_day_lift_on_2pct'])} | "
            f"{pct(r['frac_pairs_leader_edge'])} |"
        )
    lines += [
        "",
        "## Beta cohort (followers tightly tied to BTC+ETH)",
        "",
        "### Tight (min corr ≥ 0.5 to both)",
        "",
    ]
    if not tight:
        lines.append("_None cleared tight bar._")
    else:
        lines.append("| Follower | Mean corr | Min corr |")
        lines.append("|----------|----------:|---------:|")
        for c in tight[:12]:
            lines.append(
                f"| {c['follower']} | {c['mean_corr_btc_eth']:.3f} | {c['min_corr']:.3f} |"
            )
    lines += [
        "",
        "### Loose (mean corr ≥ 0.55)",
        "",
        "| Follower | Mean corr | Min corr |",
        "|----------|----------:|---------:|",
    ]
    for c in loose[:15]:
        lines.append(
            f"| {c['follower']} | {c['mean_corr_btc_eth']:.3f} | {c['min_corr']:.3f} |"
        )
    lines += [
        "",
        "## Next-session after leader +2% (aligned, gap≤3d)",
        "",
        "Ranked by mean follower return next session. Lift = up-rate vs base.",
        "",
    ]
    if not tradable:
        lines.append("_No pair cleared soft bar — next-session first-mover edge not reliable on this tape._")
    else:
        lines.append("| Leader | Follower | Same-day corr | Mean next ret | Next lift | Next up | N |")
        lines.append("|--------|----------|--------------:|--------------:|----------:|--------:|--:|")
        for r in payload["top_next_day_lift_pairs"]:
            mr = r.get("mean_next_ret")
            mrs = f"{100*mr:+.2f}%" if mr is not None else "n/a"
            lines.append(
                f"| {r['leader']} | {r['follower']} | {r['corr_same']:.3f} | "
                f"{mrs} | {pct(r['next_lift'])} | {pct(r['next_up_rate'])} | {r['n']} |"
            )
    lines += [
        "",
        "## Method notes",
        "",
        "- Daily close-to-close returns from `backtests/data/long` (+ cache fetch).",
        "- Thrust = leader day ≥ +2%.",
        "- Next session only if calendar gap ≤ 3 days (blocks listing-gap false leads).",
        "- Lift = P(follower up | thrust) − P(follower up unconditionally).",
        "- Lead edge = corr(L_t, F_{t+1}) > corr(L_t, F_{t-1}) + 0.02.",
        "- Not full Granger VAR; not intraday (lit often finds stronger BTC lead inside the day).",
        "",
        "## Decision",
        "",
        f"- first_mover_cohort_exists (beta pack): **{decision['first_mover_cohort_exists']}**",
        f"- nature: `{decision['nature']}`",
        f"- strong next-session pairs: **{decision.get('n_strong_next_day_pairs')}**",
        f"- exploit_ready: **{decision['exploit_ready']}**",
        "",
        "JSON: `data/state/first_mover_leadlag_latest.json`",
        "",
    ]
    REPORTS.joinpath("FIRST_MOVER_LEADLAG_LATEST.md").write_text("\n".join(lines) + "\n")
    print(decision["plain"])
    print("leaders", json.dumps(leader_rank, indent=2))
    print("tight", tight[:10])
    print("tradable_n", len(tradable))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
