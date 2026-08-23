#!/usr/bin/env python3
"""
Basket membership swap shadow counterfactual + parallel selection arms.

Purpose
-------
Track whether discovery/pool-cycling swaps would have beaten "stay on remove"
using real Coinbase public hourly candles. Never mutates config, never places
orders. Parallel *arms* propose paper swaps with alternate ranking rules so we
can compare selection mechanisms without live promote.

North star
----------
Less loss + better path. N small ⇒ inconclusive. Do not claim 20%/mo edge.

Research phase (Brad)
---------------------
Broad brush first: does *any* membership selection rule reliably locate better
opportunities than stay-on-remove / no-swap? Refine quality (tighter filters,
fees, SL path) only after a rule family clears the CF gate.
"""
from __future__ import annotations

import json
import time
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from phase6.core.paths import PROJECT_ROOT, load_trading_basket
from phase6.core.membership_potential_gate import evaluate_membership_swap

STATE_DIR = PROJECT_ROOT / "data" / "state"
ARMS_DIR = STATE_DIR / "basket_select_arms"
PROPOSALS_JSONL = STATE_DIR / "pool_cycling_proposals.jsonl"
PICKS_JSONL = STATE_DIR / "basket_pick_metrics.jsonl"
CF_LATEST = STATE_DIR / "basket_swap_shadow_counterfactual_latest.json"
CF_ARMS_LATEST = STATE_DIR / "basket_select_arms_cf_latest.json"
CF_MD = PROJECT_ROOT / "reports" / "BASKET_SWAP_SHADOW_CF_LATEST.md"
ARMS_MD = PROJECT_ROOT / "reports" / "BASKET_SELECT_ARMS_SHADOW_LATEST.md"
BOARD_MD = PROJECT_ROOT / "reports" / "BASKET_SWAP_CONFIDENCE_BOARD_LATEST.md"
BOARD_JSON = STATE_DIR / "basket_swap_confidence_board_latest.json"
DUAL_AGREE_DIR = ARMS_DIR / "dual_agree"
DUAL_AGREE_JSONL = DUAL_AGREE_DIR / "proposals.jsonl"
DUAL_AGREE_LATEST = STATE_DIR / "basket_dual_agree_latest.json"
DISCOVERY_LATEST = STATE_DIR / "discovery_pipeline_latest.json"
CONTENDERS_JSON = STATE_DIR / "pair_discovery_contenders.json"
POOL_LATEST = STATE_DIR / "pool_cycling_latest.json"

PUBLIC = "https://api.exchange.coinbase.com"
UA = {"User-Agent": "phase6-basket-swap-cf/1.1 (shadow)"}

HORIZONS_H = (6, 24, 72, 168, 336)  # 6h,1d,3d,7d,14d

# Confidence / decide gates (baseline arm)
MIN_N_FOR_DECIDE = 12
MIN_7D_N = 8
MODIFY_IF_MEAN_EXCESS_7D_LT = 0.0
MODIFY_IF_HIT_RATE_7D_LT = 0.45

# High-confidence arm gates (Brad / skill phase6-breadth-and-membership-edge)
HC_MIN_7D_N = 12
HC_MIN_EXCESS_7D = 0.0
HC_MIN_HIT_7D = 0.45
# Dual-agree co-leaders (paper only)
DUAL_AGREE_ARMS = ("anti_pump", "risk_adj_mom")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_ts(t: Any) -> Optional[datetime]:
    if not t:
        return None
    s = str(t).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def mean(xs: Iterable[Optional[float]]) -> Optional[float]:
    vals = [float(x) for x in xs if x is not None]
    return None if not vals else sum(vals) / len(vals)


# ---------------------------------------------------------------------------
# Candles
# ---------------------------------------------------------------------------

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def fetch_candles(
    pid: str,
    start: datetime,
    end: datetime,
    gran: int = 3600,
    sess: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    sess = sess or _session()
    out: List[list] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(seconds=gran * 280), end)
        params = {
            "granularity": gran,
            "start": cursor.isoformat().replace("+00:00", "Z"),
            "end": chunk_end.isoformat().replace("+00:00", "Z"),
        }
        try:
            r = sess.get(f"{PUBLIC}/products/{pid}/candles", params=params, timeout=25)
        except Exception as e:
            return {"ok": False, "error": str(e)[:160], "candles": []}
        if r.status_code != 200:
            return {
                "ok": False,
                "error": f"{pid} {r.status_code} {r.text[:120]}",
                "candles": [],
            }
        rows = sorted(r.json() or [], key=lambda x: x[0])
        out.extend(rows)
        cursor = chunk_end
        time.sleep(0.08)
    by = {int(c[0]): c for c in out}
    return {"ok": True, "candles": [by[k] for k in sorted(by)]}


def fetch_stats(pid: str, sess: Optional[requests.Session] = None) -> Dict[str, Any]:
    sess = sess or _session()
    out: Dict[str, Any] = {"product_id": pid, "ok": False}
    try:
        st = sess.get(f"{PUBLIC}/products/{pid}/stats", timeout=15)
        if st.status_code != 200:
            out["error"] = f"stats {st.status_code}"
            return out
        sd = st.json()
        last = float(sd.get("last") or 0)
        open_ = float(sd.get("open") or 0)
        high = float(sd.get("high") or 0)
        low = float(sd.get("low") or 0)
        vol = float(sd.get("volume") or 0)
        mid = (high + low) / 2.0 if high and low else last
        out.update(
            {
                "ok": True,
                "last": last,
                "open_24h": open_,
                "high_24h": high,
                "low_24h": low,
                "volume_base_24h": vol,
                "volume_quote_24h_est": vol * mid if mid else None,
                "ret_24h": ((last - open_) / open_) if open_ else None,
            }
        )
    except Exception as e:
        out["error"] = str(e)[:160]
    return out


def price_at_or_after(candles: Sequence[list], ts: datetime) -> Tuple[Optional[float], Optional[datetime]]:
    t = int(ts.timestamp())
    for c in candles:
        if int(c[0]) >= t:
            return float(c[4]), datetime.fromtimestamp(int(c[0]), tz=timezone.utc)
    if candles:
        c = candles[-1]
        return float(c[4]), datetime.fromtimestamp(int(c[0]), tz=timezone.utc)
    return None, None


def price_at_or_before(candles: Sequence[list], ts: datetime) -> Tuple[Optional[float], Optional[datetime]]:
    t = int(ts.timestamp())
    prev = None
    for c in candles:
        if int(c[0]) <= t:
            prev = c
        else:
            break
    if prev is None:
        return None, None
    return float(prev[4]), datetime.fromtimestamp(int(prev[0]), tz=timezone.utc)


def ret_pct(p0: Optional[float], p1: Optional[float]) -> Optional[float]:
    if p0 is None or p1 is None or p0 == 0:
        return None
    return (p1 / p0 - 1.0) * 100.0


def features_from_candles(candles: Sequence[list], now: datetime) -> Dict[str, Optional[float]]:
    """Simple multi-horizon features ending at now."""
    if not candles:
        return {}
    p_now, _ = price_at_or_before(list(candles), now)
    out: Dict[str, Optional[float]] = {"price": p_now}
    for h, key in [(24, "ret_24h"), (72, "ret_3d"), (168, "ret_7d"), (336, "ret_14d")]:
        p0, _ = price_at_or_after(list(candles), now - timedelta(hours=h))
        out[key] = None if p0 is None or p_now is None else (p_now / p0 - 1.0)
    # realized vol proxy: stdev of hourly rets last 72h
    t_cut = int((now - timedelta(hours=72)).timestamp())
    closes = [float(c[4]) for c in candles if int(c[0]) >= t_cut]
    rets = []
    for i in range(1, len(closes)):
        if closes[i - 1]:
            rets.append(closes[i] / closes[i - 1] - 1.0)
    if len(rets) >= 10:
        m = sum(rets) / len(rets)
        var = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
        out["vol_72h"] = var ** 0.5
        out["sharpe_like_3d"] = (out.get("ret_3d") or 0.0) / out["vol_72h"] if out["vol_72h"] else None
    else:
        out["vol_72h"] = None
        out["sharpe_like_3d"] = None
    # max run-up 3d (pump detector): high/low range vs open
    t3 = int((now - timedelta(hours=72)).timestamp())
    window = [c for c in candles if int(c[0]) >= t3]
    if window:
        hi = max(float(c[2]) for c in window)
        lo = min(float(c[1]) for c in window)
        o0 = float(window[0][3])
        out["range_3d"] = (hi - lo) / o0 if o0 else None
        out["runup_3d"] = (hi / o0 - 1.0) if o0 else None
    return out


# ---------------------------------------------------------------------------
# Load historical swaps (baseline log)
# ---------------------------------------------------------------------------

def load_baseline_swaps() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if PROPOSALS_JSONL.exists():
        for line in PROPOSALS_JSONL.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_ts(r.get("ts"))
            for s in r.get("swaps") or []:
                if not s.get("add") or not s.get("remove") or not ts:
                    continue
                rows.append(
                    {
                        "ts": ts,
                        "remove": s["remove"],
                        "add": s["add"],
                        "delta": s.get("delta"),
                        "add_score": s.get("add_score"),
                        "remove_score": s.get("remove_score"),
                        "source": "shadow_proposal",
                        "arm": "baseline_hybrid",
                        "pick_id": None,
                    }
                )
    if PICKS_JSONL.exists():
        for line in PICKS_JSONL.read_text().splitlines():
            if not line.strip():
                continue
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = parse_ts(p.get("promoted_at"))
            if not ts or not p.get("add_pair") or not p.get("remove_pair"):
                continue
            rows.append(
                {
                    "ts": ts,
                    "remove": p["remove_pair"],
                    "add": p["add_pair"],
                    "delta": p.get("delta"),
                    "add_score": p.get("add_score"),
                    "remove_score": p.get("remove_score"),
                    "source": "live_promote",
                    "arm": "baseline_hybrid",
                    "pick_id": p.get("pick_id"),
                }
            )
    # arm proposal ledgers
    if ARMS_DIR.exists():
        for arm_dir in sorted(ARMS_DIR.iterdir()):
            if not arm_dir.is_dir():
                continue
            prop = arm_dir / "proposals.jsonl"
            if not prop.exists():
                continue
            for line in prop.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    s = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if s.get("status") in {"superseded", "superseded_pump_brake", "void"}:
                    continue
                ts = parse_ts(s.get("ts"))
                if not ts or not s.get("add") or not s.get("remove"):
                    continue
                rows.append(
                    {
                        "ts": ts,
                        "remove": s["remove"],
                        "add": s["add"],
                        "delta": s.get("delta"),
                        "add_score": s.get("add_score"),
                        "remove_score": s.get("remove_score"),
                        "source": "arm_proposal",
                        "arm": arm_dir.name,
                        "pick_id": s.get("proposal_id"),
                        "reason": s.get("reason"),
                    }
                )
    rows.sort(key=lambda x: x["ts"])
    return rows


def dedupe_swaps(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prefer live_promote, then first shadow, per (date, remove, add, arm)."""
    best: "OrderedDict[Tuple, Dict[str, Any]]" = OrderedDict()
    rank = {"live_promote": 0, "shadow_proposal": 1, "arm_proposal": 2}
    for r in rows:
        key = (r["ts"].date().isoformat(), r["remove"], r["add"], r.get("arm") or "baseline_hybrid")
        if key not in best:
            best[key] = r
            continue
        cur = best[key]
        if rank.get(r["source"], 9) < rank.get(cur["source"], 9):
            best[key] = r
    return list(best.values())


# ---------------------------------------------------------------------------
# Counterfactual engine
# ---------------------------------------------------------------------------

def evaluate_swaps(
    swaps: Sequence[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or _utc_now()
    if not swaps:
        return {
            "schema": "basket_swap_shadow_counterfactual_v1",
            "as_of": _iso(now),
            "results": [],
            "by_arm": {},
            "aggregate_by_arm": {},
            "decide": {"status": "no_data"},
        }

    pairs = sorted({s["add"] for s in swaps} | {s["remove"] for s in swaps} | {"BTC-USD"})
    start_all = min(s["ts"] for s in swaps) - timedelta(hours=6)
    sess = _session()
    cache: Dict[str, Dict[str, Any]] = {}
    for pid in pairs:
        cache[pid] = fetch_candles(pid, start_all, now + timedelta(hours=1), gran=3600, sess=sess)

    results: List[Dict[str, Any]] = []
    for s in swaps:
        t0 = s["ts"]
        age_h = (now - t0).total_seconds() / 3600.0
        add_c = cache.get(s["add"], {}).get("candles") or []
        rem_c = cache.get(s["remove"], {}).get("candles") or []
        btc_c = cache.get("BTC-USD", {}).get("candles") or []
        p_add0, _ = price_at_or_after(add_c, t0)
        p_rem0, _ = price_at_or_after(rem_c, t0)
        p_btc0, _ = price_at_or_after(btc_c, t0)
        p_add1, _ = price_at_or_before(add_c, now)
        p_rem1, _ = price_at_or_before(rem_c, now)
        p_btc1, _ = price_at_or_before(btc_c, now)
        ra_now = ret_pct(p_add0, p_add1)
        rr_now = ret_pct(p_rem0, p_rem1)
        row: Dict[str, Any] = {
            "ts": _iso(t0),
            "remove": s["remove"],
            "add": s["add"],
            "delta": s.get("delta"),
            "add_score": s.get("add_score"),
            "remove_score": s.get("remove_score"),
            "source": s.get("source"),
            "arm": s.get("arm") or "baseline_hybrid",
            "pick_id": s.get("pick_id"),
            "age_hours": round(age_h, 2),
            "ret_add_to_now": ra_now,
            "ret_rem_to_now": rr_now,
            "excess_to_now": None if ra_now is None or rr_now is None else ra_now - rr_now,
            "ret_btc_to_now": ret_pct(p_btc0, p_btc1),
            "horizons": {},
            "product_ok": bool(add_c and rem_c),
        }
        for h in HORIZONS_H:
            t1 = t0 + timedelta(hours=h)
            key = f"{h}h"
            if t1 > now + timedelta(minutes=30):
                row["horizons"][key] = {"status": "not_elapsed"}
                continue
            pa, _ = price_at_or_before(add_c, t1)
            pr, _ = price_at_or_before(rem_c, t1)
            pb, _ = price_at_or_before(btc_c, t1)
            ra, rr = ret_pct(p_add0, pa), ret_pct(p_rem0, pr)
            row["horizons"][key] = {
                "status": "ok" if ra is not None and rr is not None else "missing_price",
                "add_ret_pct": None if ra is None else round(ra, 3),
                "rem_ret_pct": None if rr is None else round(rr, 3),
                "excess_pct": None if ra is None or rr is None else round(ra - rr, 3),
                "btc_ret_pct": None
                if ret_pct(p_btc0, pb) is None
                else round(ret_pct(p_btc0, pb), 3),  # type: ignore[arg-type]
            }
        results.append(row)

    unique = dedupe_swaps(
        [
            {
                **{k: r[k] for k in r if k != "ts"},
                "ts": parse_ts(r["ts"]),
            }
            for r in results
        ]
    )
    # re-attach evaluated horizons from results by key
    eval_by_key = {
        (
            parse_ts(r["ts"]).date().isoformat(),  # type: ignore[union-attr]
            r["remove"],
            r["add"],
            r.get("arm") or "baseline_hybrid",
        ): r
        for r in results
    }
    unique_eval = []
    for u in unique:
        k = (u["ts"].date().isoformat(), u["remove"], u["add"], u.get("arm") or "baseline_hybrid")
        unique_eval.append(eval_by_key.get(k) or {**u, "ts": _iso(u["ts"])})

    def agg_for(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for hkey, label in [("24h", "1d"), ("72h", "3d"), ("168h", "7d"), ("336h", "14d")]:
            mats = [
                r["horizons"].get(hkey) or {}
                for r in rows
                if (r.get("horizons") or {}).get(hkey, {}).get("status") == "ok"
            ]
            if not mats:
                out[label] = {"n": 0}
                continue
            ex = [m.get("excess_pct") for m in mats]
            ad = [m.get("add_ret_pct") for m in mats]
            out[label] = {
                "n": len(mats),
                "mean_add_pct": mean(ad),
                "mean_rem_pct": mean([m.get("rem_ret_pct") for m in mats]),
                "mean_excess_pct": mean(ex),
                "hit_excess_gt0": sum(1 for x in ex if x is not None and x > 0) / len(mats),
                "hit_add_gt0": sum(1 for x in ad if x is not None and x > 0) / len(mats),
            }
        # paper sleeve age>=6h
        sleeve = [r for r in rows if r.get("excess_to_now") is not None and (r.get("age_hours") or 0) >= 6]
        if sleeve:
            nav_a = sum(100 * (1 + (r["ret_add_to_now"] or 0) / 100) for r in sleeve)
            nav_r = sum(100 * (1 + (r["ret_rem_to_now"] or 0) / 100) for r in sleeve)
            out["paper_sleeve_to_now"] = {
                "n": len(sleeve),
                "nav_add": nav_a,
                "nav_rem": nav_r,
                "delta_usd": nav_a - nav_r,
                "mean_excess_pct": mean([r.get("excess_to_now") for r in sleeve]),
            }
        return out

    by_arm: Dict[str, List[Dict[str, Any]]] = {}
    for r in unique_eval:
        by_arm.setdefault(r.get("arm") or "baseline_hybrid", []).append(r)

    aggregate_by_arm = {arm: agg_for(rs) for arm, rs in by_arm.items()}

    # Decide on baseline only
    base_agg = aggregate_by_arm.get("baseline_hybrid") or {}
    d7 = base_agg.get("7d") or {}
    d3 = base_agg.get("3d") or {}
    decide = _decide_baseline(d7, d3, base_agg)

    return {
        "schema": "basket_swap_shadow_counterfactual_v1",
        "as_of": _iso(now),
        "method": {
            "prices": "Coinbase public hourly candles",
            "assumption": "Equal notional ADD vs REMOVE from proposal ts; no fees/SL/full-account path",
            "anti_bleed": True,
            "mutates_config": False,
            "places_orders": False,
        },
        "results": results,
        "unique_results": unique_eval,
        "by_arm_counts": {k: len(v) for k, v in by_arm.items()},
        "aggregate_by_arm": aggregate_by_arm,
        "decide": decide,
        "candle_errors": {
            pid: cache[pid].get("error")
            for pid in cache
            if not cache[pid].get("ok")
        },
    }


def _decide_baseline(d7: Dict[str, Any], d3: Dict[str, Any], base_agg: Dict[str, Any]) -> Dict[str, Any]:
    n7 = int(d7.get("n") or 0)
    n3 = int(d3.get("n") or 0)
    if n7 < MIN_7D_N and n3 < MIN_N_FOR_DECIDE:
        return {
            "status": "keep_shadow_collecting",
            "plain_english": (
                f"Not enough matured swaps yet (7d N={n7}, need ≥{MIN_7D_N}; "
                f"3d N={n3}, need ≥{MIN_N_FOR_DECIDE}). Keep shadow; do not modify selector."
            ),
            "recommend_modify_selector": False,
            "recommend_live_promote": False,
            "n_7d": n7,
            "n_3d": n3,
        }
    # Prefer 7d when available
    use = d7 if n7 >= MIN_7D_N else d3
    label = "7d" if n7 >= MIN_7D_N else "3d"
    mex = use.get("mean_excess_pct")
    hit = use.get("hit_excess_gt0")
    if mex is None:
        return {
            "status": "inconclusive",
            "plain_english": "Prices missing; cannot decide.",
            "recommend_modify_selector": False,
            "recommend_live_promote": False,
        }
    if mex < MODIFY_IF_MEAN_EXCESS_7D_LT and (hit is None or hit < MODIFY_IF_HIT_RATE_7D_LT):
        return {
            "status": "modify_selector",
            "plain_english": (
                f"Baseline {label}: mean excess {mex:+.2f}% hit={None if hit is None else round(hit*100)}% "
                f"on N={use.get('n')}. Selection mechanism underperforms stay-on-remove — "
                f"prefer parallel arms / tighten pump brakes before any live promote."
            ),
            "recommend_modify_selector": True,
            "recommend_live_promote": False,
            "mean_excess_pct": mex,
            "hit_rate": hit,
            "horizon": label,
            "n": use.get("n"),
        }
    if mex > 2.0 and hit is not None and hit >= 0.55 and int(use.get("n") or 0) >= MIN_7D_N:
        return {
            "status": "baseline_ok_shadow_only",
            "plain_english": (
                f"Baseline {label} modestly positive (excess {mex:+.2f}%, hit {hit*100:.0f}%, N={use.get('n')}). "
                f"Still shadow-first; promote only flat ejects with forward 3d excess > 0."
            ),
            "recommend_modify_selector": False,
            "recommend_live_promote": False,
            "mean_excess_pct": mex,
            "hit_rate": hit,
            "horizon": label,
            "n": use.get("n"),
        }
    return {
        "status": "marginal_keep_shadow",
        "plain_english": (
            f"Baseline {label}: excess {mex:+.2f}% hit={None if hit is None else round(hit*100)}% N={use.get('n')}. "
            f"Keep shadow; no live batch promote."
        ),
        "recommend_modify_selector": False,
        "recommend_live_promote": False,
        "mean_excess_pct": mex,
        "hit_rate": hit,
        "horizon": label,
        "n": use.get("n"),
    }


# ---------------------------------------------------------------------------
# Parallel selection arms (paper proposals only)
# ---------------------------------------------------------------------------

@dataclass
class ArmSpec:
    name: str
    title: str
    prior: str  # honest prior language
    # None of these are "high probability of success" until CF says so


ARMS: List[ArmSpec] = [
    ArmSpec(
        name="baseline_hybrid",
        title="Current discovery + hybrid RSI/sent/mom cycler",
        prior="Live scorer. Recent CF mean excess negative — control to beat.",
    ),
    ArmSpec(
        name="anti_pump",
        title="Anti-pump / de-chase",
        prior=(
            "Medium prior vs baseline for less loss: block hot 24h/3d extensions "
            "(RAVE-class). Not proven; may miss real breakouts."
        ),
    ),
    ArmSpec(
        name="risk_adj_mom",
        title="Risk-adjusted momentum (ret/vol)",
        prior=(
            "Literature-aligned TSMOM-ish sleeve pick. Medium prior on longer horizons; "
            "weak on 1–3d crypto noise. Not high-confidence."
        ),
    ),
    ArmSpec(
        name="rel_btc_stable",
        title="Beat BTC + stability gate",
        prior=(
            "Only add if 7d excess vs BTC > 0 and not extended. Conservative; "
            "may propose fewer swaps. Medium-low activity prior."
        ),
    ),
    ArmSpec(
        name="control_no_swap",
        title="Never swap (hold membership)",
        prior="Structural control. Recent window beat baseline sleeve — default until another arm wins.",
    ),
    ArmSpec(
        name="dual_agree",
        title="Dual agree (anti_pump ∩ risk_adj_mom)",
        prior=(
            "Intersection of co-leaders: only paper swaps where both anti_pump and "
            "risk_adj_mom nominate the same remove→add on the same day. Higher bar, "
            "fewer swaps. Shadow only until HC gates clear."
        ),
    ),
]


def _load_arm_proposal_rows(arm_name: str) -> List[Dict[str, Any]]:
    path = ARMS_DIR / arm_name / "proposals.jsonl"
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            s = json.loads(line)
        except json.JSONDecodeError:
            continue
        if s.get("status") in {"superseded", "superseded_pump_brake", "void"}:
            continue
        ts = parse_ts(s.get("ts"))
        if not ts or not s.get("add") or not s.get("remove"):
            continue
        rows.append({**s, "ts": ts, "arm": arm_name})
    return rows


def _dual_agree_existing_keys() -> set:
    keys = set()
    if not DUAL_AGREE_JSONL.exists():
        return keys
    for line in DUAL_AGREE_JSONL.read_text().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = parse_ts(e.get("ts"))
        if ts and e.get("remove") and e.get("add"):
            keys.add((ts.date().isoformat(), e["remove"], e["add"]))
    return keys


def record_dual_agree_swaps(
    arms_prop: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Paper dual-agree log: remove→add only when both co-leader arms nominate it
    on the same calendar day. Backfills from arm ledgers + new proposals this run.
    Never places orders.
    """
    now = now or _utc_now()
    DUAL_AGREE_DIR.mkdir(parents=True, exist_ok=True)

    by_arm: Dict[str, List[Dict[str, Any]]] = {
        a: _load_arm_proposal_rows(a) for a in DUAL_AGREE_ARMS
    }
    if arms_prop:
        for arm_name in DUAL_AGREE_ARMS:
            for w in arms_prop.get("written") or []:
                if w.get("arm") != arm_name:
                    continue
                ts = parse_ts(w.get("ts")) or now
                by_arm.setdefault(arm_name, []).append({**w, "ts": ts, "arm": arm_name})
            for s in ((arms_prop.get("arms") or {}).get(arm_name) or {}).get("swaps") or []:
                if not s.get("add") or not s.get("remove"):
                    continue
                ts = parse_ts(s.get("ts")) or now
                by_arm.setdefault(arm_name, []).append(
                    {**s, "ts": ts, "arm": arm_name, "proposal_id": s.get("proposal_id")}
                )

    hits: Dict[Tuple[str, str, str], Dict[str, Dict[str, Any]]] = {}
    for arm_name, rows in by_arm.items():
        for r in rows:
            ts = r["ts"] if isinstance(r["ts"], datetime) else parse_ts(r["ts"])
            if not ts:
                continue
            key = (ts.date().isoformat(), str(r["remove"]), str(r["add"]))
            hits.setdefault(key, {})[arm_name] = r

    existing = _dual_agree_existing_keys()
    written: List[Dict[str, Any]] = []
    for key, arm_map in sorted(hits.items()):
        if not all(a in arm_map for a in DUAL_AGREE_ARMS):
            continue
        if key in existing:
            continue
        day, rem, add = key
        ts_candidates = []
        for a in DUAL_AGREE_ARMS:
            t = arm_map[a]["ts"]
            ts_candidates.append(t if isinstance(t, datetime) else parse_ts(t))
        ts_candidates = [t for t in ts_candidates if t is not None]
        ts_use = max(ts_candidates) if ts_candidates else now
        a0 = arm_map[DUAL_AGREE_ARMS[0]]
        a1 = arm_map[DUAL_AGREE_ARMS[1]]
        rec = {
            "proposal_id": str(uuid.uuid4())[:12],
            "ts": _iso(ts_use),
            "arm": "dual_agree",
            "remove": rem,
            "add": add,
            "delta": None,
            "add_score": None,
            "remove_score": None,
            "reason": (
                f"dual_agree: {DUAL_AGREE_ARMS[0]}∩{DUAL_AGREE_ARMS[1]} "
                f"{rem}→{add} day={day}"
            ),
            "agree_arms": list(DUAL_AGREE_ARMS),
            "source_ids": {
                DUAL_AGREE_ARMS[0]: a0.get("proposal_id"),
                DUAL_AGREE_ARMS[1]: a1.get("proposal_id"),
            },
            "membership_boundary": "heightened_potential_M0-M3; deploy_ready_not_required",
            "live_promote": False,
        }
        with DUAL_AGREE_JSONL.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        written.append(rec)
        existing.add(key)

    ledger_n = 0
    if DUAL_AGREE_JSONL.exists():
        ledger_n = sum(1 for line in DUAL_AGREE_JSONL.read_text().splitlines() if line.strip())

    live_pair: Optional[Dict[str, Any]] = None
    if arms_prop:
        sw: Dict[str, Tuple[Any, Any]] = {}
        for a in DUAL_AGREE_ARMS:
            swaps = ((arms_prop.get("arms") or {}).get(a) or {}).get("swaps") or []
            if swaps:
                sw[a] = (swaps[0].get("remove"), swaps[0].get("add"))
        if len(sw) == 2 and sw[DUAL_AGREE_ARMS[0]] == sw[DUAL_AGREE_ARMS[1]]:
            live_pair = {
                "remove": sw[DUAL_AGREE_ARMS[0]][0],
                "add": sw[DUAL_AGREE_ARMS[0]][1],
                "agreed": True,
            }
        elif len(sw) == 2:
            live_pair = {
                "anti_pump": {"remove": sw["anti_pump"][0], "add": sw["anti_pump"][1]},
                "risk_adj_mom": {
                    "remove": sw["risk_adj_mom"][0],
                    "add": sw["risk_adj_mom"][1],
                },
                "agreed": False,
            }

    latest = {
        "ts": _iso(now),
        "agree_arms": list(DUAL_AGREE_ARMS),
        "new_agreements": written,
        "total_ledger_n": ledger_n,
        "this_run": live_pair,
        "note": (
            "Shadow only. dual_agree = same-day remove→add nominated by both co-leader arms. "
            "No live basket swaps."
        ),
    }
    DUAL_AGREE_LATEST.write_text(json.dumps(latest, indent=2, default=str) + "\n")
    (DUAL_AGREE_DIR / "latest.json").write_text(json.dumps(latest, indent=2, default=str) + "\n")
    return latest


def build_confidence_board(cf: Dict[str, Any]) -> Dict[str, Any]:
    """Regenerate HC board from current CF aggregates. No p-values at thin N."""
    as_of = cf.get("as_of") or _iso(_utc_now())
    decide_base = cf.get("decide") or {}
    arms_out: List[Dict[str, Any]] = []
    any_hc = False
    sleeve_pos: List[str] = []

    for arm_name, agg in sorted((cf.get("aggregate_by_arm") or {}).items()):
        d1 = agg.get("1d") or {}
        d3 = agg.get("3d") or {}
        d7 = agg.get("7d") or {}
        ps = agg.get("paper_sleeve_to_now") or {}
        n7 = int(d7.get("n") or 0)
        ex7 = d7.get("mean_excess_pct")
        hit7 = d7.get("hit_excess_gt0")
        sleeve = ps.get("delta_usd")
        n7_ok = n7 >= HC_MIN_7D_N
        ex7_ok = ex7 is not None and float(ex7) > HC_MIN_EXCESS_7D
        hit7_ok = hit7 is not None and float(hit7) >= HC_MIN_HIT_7D
        sleeve_ok = sleeve is not None and float(sleeve) > 0
        hc = bool(n7_ok and ex7_ok and hit7_ok and sleeve_ok)
        if hc:
            any_hc = True
        if sleeve_ok:
            sleeve_pos.append(arm_name)
        missing = []
        if not n7_ok:
            missing.append("n7")
        if not ex7_ok:
            missing.append("ex7")
        if not hit7_ok:
            missing.append("hit7")
        if not sleeve_ok:
            missing.append("sleeve")
        arms_out.append(
            {
                "arm": arm_name,
                "n1": int(d1.get("n") or 0),
                "ex1": d1.get("mean_excess_pct"),
                "hit1": d1.get("hit_excess_gt0"),
                "n3": int(d3.get("n") or 0),
                "ex3": d3.get("mean_excess_pct"),
                "hit3": d3.get("hit_excess_gt0"),
                "n7": n7,
                "ex7": ex7,
                "hit7": hit7,
                "sleeve_delta": sleeve,
                "sleeve_n": ps.get("n"),
                "gates": {
                    "n7_ok": n7_ok,
                    "ex7_ok": ex7_ok,
                    "hit7_ok": hit7_ok,
                    "sleeve_ok": sleeve_ok,
                },
                "high_confidence": hc,
                "missing": missing,
            }
        )

    def _sort_key(a: Dict[str, Any]) -> Tuple:
        return (
            0 if a["high_confidence"] else 1,
            -(float(a["sleeve_delta"]) if a["sleeve_delta"] is not None else -1e18),
            -(float(a["ex3"]) if a["ex3"] is not None else -1e18),
        )

    ranked = sorted(arms_out, key=_sort_key)
    leaders = [
        a["arm"]
        for a in ranked
        if (a.get("sleeve_delta") or 0) > 0 and (a.get("ex3") or 0) > 0
    ][:3]

    if any_hc:
        pe = (
            f"High-confidence arm(s) present: "
            f"{[a['arm'] for a in arms_out if a['high_confidence']]}. "
            "Still not live — Brad review required before any promote."
        )
        status = "high_confidence_shadow"
    elif leaders:
        pe = (
            f"No selection arm is high-confidence yet (need 7d N≥{HC_MIN_7D_N}, "
            f"excess>0, hit≥{int(HC_MIN_HIT_7D*100)}%, sleeve>$0). "
            f"Sleeve+3d leaders: {leaders}. "
            f"Baseline: {decide_base.get('status')} — {decide_base.get('plain_english')} "
            "Keep shadow; no live batch promote."
        )
        status = "keep_shadow_collecting"
    else:
        pe = (
            f"No arm clears HC gates. Baseline: {decide_base.get('status')} — "
            f"{decide_base.get('plain_english')} Keep shadow; no live batch promote."
        )
        status = "keep_shadow_collecting"

    board = {
        "as_of": as_of,
        "decide_baseline": decide_base,
        "high_confidence_definition": {
            "n7_min": HC_MIN_7D_N,
            "ex7_gt": HC_MIN_EXCESS_7D,
            "hit7_min": HC_MIN_HIT_7D,
            "sleeve_delta_gt": 0.0,
            "note": "Operational bar only; no p-values until N7≥12 + two-slice stability.",
        },
        "any_arm_high_confidence": any_hc,
        "status": status,
        "arms": arms_out,
        "sleeve_positive": sleeve_pos,
        "leaders_sleeve_and_3d": leaders,
        "plain_english": pe,
        "dual_agree_arms": list(DUAL_AGREE_ARMS),
    }

    def _cell(n: Any, ex: Any, hit: Any) -> str:
        if not n:
            return "N=0"
        hs = "" if hit is None else f" hit={int(float(hit)*100)}%"
        return f"N={n} {float(ex):+.2f}%{hs}" if ex is not None else f"N={n}"

    lines = [
        "# Basket swap — winner-picking confidence board",
        f"As of `{as_of}`",
        "",
        "## Plain English",
        "",
        pe,
        "",
        "## Decision point (when we stop saying “keep collecting”)",
        "",
        "**Promote-to-Brad-review (still not live)** when **any arm** hits all of:",
        "",
        f"1. **7d N ≥ {HC_MIN_7D_N}** matured ADD-vs-REMOVE swaps",
        "2. **7d mean excess > 0%** (add beats remove on average)",
        f"3. **7d hit rate ≥ {int(HC_MIN_HIT_7D*100)}%**",
        "4. **Paper sleeve $ to-now > $0** vs stay-on-remove",
        "",
        f"**Modify / drop arm family** when 7d N ≥ {HC_MIN_7D_N} **and** mean excess < 0 "
        "**and** hit < 45% (or sleeve deeply negative).",
        "",
        "**Statistical significance:** we do **not** claim p-values yet. "
        "At thin 7d N, a t-test is underpowered. Operational bar above is the decision point.",
        "",
        f"**Any arm high-confidence right now?** **{'YES' if any_hc else 'NO'}**",
        "",
        "## Scoreboard (from current CF)",
        "",
        "| Arm | 1d | 3d | 7d | Sleeve Δ$ | HC? | Missing |",
        "|-----|----|----|----|-----------|-----|---------|",
    ]
    for a in ranked:
        sd = a["sleeve_delta"]
        sd_s = "n/a" if sd is None else f"${float(sd):+.2f}"
        miss = ",".join(a["missing"]) if a["missing"] else "—"
        lines.append(
            f"| `{a['arm']}` | {_cell(a['n1'], a['ex1'], a['hit1'])} | "
            f"{_cell(a['n3'], a['ex3'], a['hit3'])} | "
            f"{_cell(a['n7'], a['ex7'], a['hit7'])} | {sd_s} | "
            f"{'yes' if a['high_confidence'] else 'no'} | {miss} |"
        )

    lines += ["", "## Read of current tape", ""]
    for a in ranked[:6]:
        bits = []
        if a.get("ex3") is not None and a["n3"]:
            bits.append(f"3d excess {float(a['ex3']):+.2f}% (N={a['n3']})")
        if a.get("sleeve_delta") is not None:
            bits.append(f"sleeve ${float(a['sleeve_delta']):+.0f}")
        if a.get("n7"):
            bits.append(f"7d N={a['n7']}")
        else:
            bits.append("7d immature")
        lines.append(
            f"- **`{a['arm']}`:** {'; '.join(bits)} → missing {a['missing'] or 'none'}."
        )

    lines += [
        "",
        "Bottom line: **decision point not reached** unless HC=yes above. "
        "Continue shadow proposals + CF. **No live basket swaps.**",
        "",
        f"Co-leader dual-agree log: `{DUAL_AGREE_JSONL}` "
        f"(arms: {', '.join(DUAL_AGREE_ARMS)}).",
        "",
        "CF: `reports/BASKET_SWAP_SHADOW_CF_LATEST.md`",
        "JSON: `data/state/basket_swap_confidence_board_latest.json`",
        "",
    ]
    BOARD_MD.parent.mkdir(parents=True, exist_ok=True)
    BOARD_MD.write_text("\n".join(lines) + "\n")
    BOARD_JSON.write_text(json.dumps(board, indent=2, default=str) + "\n")
    return board


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _candidate_universe() -> Tuple[List[str], List[str], Dict[str, Any]]:
    """active pairs, outside candidates, meta."""
    active = list(load_trading_basket() or [])
    meta: Dict[str, Any] = {"active_source": "load_trading_basket"}
    outside: List[str] = []
    cont = _load_json(CONTENDERS_JSON) or {}
    # contenders formats vary
    raw = cont.get("contenders") or cont.get("promote_eligible") or []
    if isinstance(raw, list):
        for c in raw:
            if isinstance(c, str):
                outside.append(c)
            elif isinstance(c, dict) and c.get("product_id"):
                outside.append(c["product_id"])
    disc = _load_json(DISCOVERY_LATEST) or {}
    stages = disc.get("stages") or {}
    elig = (stages.get("discovery") or {}).get("promote_eligible_after_brake") or []
    for p in elig:
        if p not in outside:
            outside.append(p)
    pool = _load_json(POOL_LATEST) or {}
    for p in pool.get("outside_active") or pool.get("outside") or []:
        if p not in outside and p not in active:
            outside.append(p)
    # sticky never eject
    sticky = {"BTC-USD", "ETH-USD"}
    return active, outside, {**meta, "sticky": list(sticky)}


def propose_arm_swaps(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Generate at most one paper swap per arm from current market features."""
    now = now or _utc_now()
    active, outside, meta = _candidate_universe()
    sticky = set(meta.get("sticky") or ["BTC-USD", "ETH-USD"])
    sess = _session()
    universe = sorted(set(active) | set(outside) | {"BTC-USD"})
    # need ~14d history
    start = now - timedelta(days=16)
    cache: Dict[str, List[list]] = {}
    stats: Dict[str, Dict[str, Any]] = {}
    for pid in universe:
        c = fetch_candles(pid, start, now + timedelta(hours=1), gran=3600, sess=sess)
        cache[pid] = c.get("candles") or []
        stats[pid] = fetch_stats(pid, sess=sess)
        time.sleep(0.05)

    feats = {pid: features_from_candles(cache[pid], now) for pid in universe}
    btc_r7 = feats.get("BTC-USD", {}).get("ret_7d")

    # holdings for flat-eject preference
    held: Dict[str, float] = {}
    try:
        from phase6.core.pool_cycling import load_holdings_usd

        held = load_holdings_usd() or {}
    except Exception:
        held = {}

    def is_flat(pid: str) -> bool:
        return float(held.get(pid) or 0.0) < 40.0

    cont_rows = (_load_json(CONTENDERS_JSON) or {}).get("contenders") or []
    cont_quality = {
        c.get("product_id"): c.get("quality_score")
        for c in cont_rows
        if isinstance(c, dict) and c.get("product_id")
    }

    def annotate_membership(swap: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Attach M0–M3 heightened-potential verdict (deploy-ready never required)."""
        if not swap or not swap.get("add") or not swap.get("remove"):
            return swap
        add_p = str(swap["add"])
        rem_p = str(swap["remove"])
        f_add = feats.get(add_p) or {}
        st_add = stats.get(add_p) or {}
        add_score = swap.get("add_score")
        rem_score = swap.get("remove_score")
        q_add = cont_quality.get(add_p)
        inbound_pot = q_add if q_add is not None else add_score
        outbound_pot = rem_score
        r24 = st_add.get("ret_24h")
        if r24 is None:
            r24 = f_add.get("ret_24h")
        verdict = evaluate_membership_swap(
            add=add_p,
            remove=rem_p,
            active=active,
            inbound_potential=None if inbound_pot is None else float(inbound_pot),
            outbound_potential=None if outbound_pot is None else float(outbound_pot),
            precomputed_delta=swap.get("delta"),
            quote_vol_24h=st_add.get("volume_quote_24h_est"),
            ret_24h=r24,
            mom_3d=f_add.get("ret_3d"),
            mom_7d=f_add.get("ret_7d"),
            runup_3d=f_add.get("runup_3d"),
            held_usd_remove=float(held.get(rem_p) or swap.get("remove_held_usd") or 0.0),
            sticky=sticky,
            skip_inbound_score_floor=(q_add is None and add_score is not None),
        )
        swap = dict(swap)
        swap["membership_potential"] = verdict.to_dict()
        swap["membership_potential_ok"] = bool(verdict.ok)
        swap["require_deploy_ready"] = False
        if not verdict.ok:
            swap["reason"] = (swap.get("reason") or "") + (
                f" | membership_gate={verdict.layer_failed}:{','.join(verdict.reasons[:4])}"
            )
        else:
            swap["reason"] = (swap.get("reason") or "") + " | membership_gate=ok(potential_not_deploy)"
        return swap

    def ext_ok_anti_pump(f: Dict[str, Optional[float]], st: Dict[str, Any]) -> bool:
        r24 = st.get("ret_24h")
        if r24 is None:
            r24 = f.get("ret_24h")
        r3 = f.get("ret_3d")
        run = f.get("runup_3d")
        if r24 is not None and r24 > 0.15:  # >15% 24h
            return False
        if r3 is not None and r3 > 0.25:
            return False
        if run is not None and run > 0.35:
            return False
        if r24 is not None and r24 < -0.08:  # dumping
            return False
        return True

    def score_anti_pump(pid: str) -> Optional[float]:
        f, st = feats.get(pid, {}), stats.get(pid, {})
        if not cache.get(pid):
            return None
        if not ext_ok_anti_pump(f, st):
            return None
        r7 = f.get("ret_7d") or 0.0
        r3 = f.get("ret_3d") or 0.0
        volq = st.get("volume_quote_24h_est") or 0.0
        if volq < 1_500_000:
            return None
        # prefer mild positive 7d, penalize choppy high vol
        vol = f.get("vol_72h") or 0.02
        return float(r7 * 0.6 + r3 * 0.3 - vol * 2.0)

    def score_risk_adj(pid: str) -> Optional[float]:
        f, st = feats.get(pid, {}), stats.get(pid, {})
        if not cache.get(pid):
            return None
        volq = st.get("volume_quote_24h_est") or 0.0
        if volq < 2_000_000:
            return None
        # Same extension brake as anti_pump (CAP/RAVE-class) — Sharpe on a 3d melt-up lies
        if not ext_ok_anti_pump(f, st):
            return None
        sh = f.get("sharpe_like_3d")
        r7 = f.get("ret_7d")
        if sh is None and r7 is None:
            return None
        base = float(sh if sh is not None else 0.0) + float(r7 or 0.0) * 2.0
        return base

    def score_rel_btc(pid: str) -> Optional[float]:
        f, st = feats.get(pid, {}), stats.get(pid, {})
        if not cache.get(pid) or btc_r7 is None:
            return None
        r7 = f.get("ret_7d")
        if r7 is None:
            return None
        excess = r7 - btc_r7
        if excess <= 0:
            return None
        r24 = st.get("ret_24h") if st.get("ret_24h") is not None else f.get("ret_24h")
        if r24 is not None and abs(r24) > 0.12:
            return None
        if not ext_ok_anti_pump(f, st):
            return None
        volq = st.get("volume_quote_24h_est") or 0.0
        if volq < 2_000_000:
            return None
        return float(excess)

    scorers = {
        "anti_pump": score_anti_pump,
        "risk_adj_mom": score_risk_adj,
        "rel_btc_stable": score_rel_btc,
    }

    # baseline: use latest pool cycling swap if any, else none new here
    proposals: Dict[str, Any] = {"ts": _iso(now), "arms": {}}

    # control
    proposals["arms"]["control_no_swap"] = {
        "swaps": [],
        "note": "Structural control — never proposes membership changes.",
    }

    # baseline from pool latest
    base_swaps = []
    pool = _load_json(POOL_LATEST) or {}
    for s in pool.get("swaps") or []:
        if s.get("add") and s.get("remove"):
            base_swaps.append(
                {
                    "remove": s["remove"],
                    "add": s["add"],
                    "delta": s.get("delta"),
                    "add_score": s.get("add_score"),
                    "remove_score": s.get("remove_score"),
                    "reason": s.get("reason") or "pool_cycling_latest",
                }
            )
    # also discovery proposed file
    prop_file = _load_json(STATE_DIR / "pool_cycling_proposed_pairs.json") or {}
    if not base_swaps:
        for s in prop_file.get("swaps") or []:
            if s.get("add") and s.get("remove"):
                base_swaps.append(
                    {
                        "remove": s["remove"],
                        "add": s["add"],
                        "delta": s.get("delta"),
                        "add_score": s.get("add_score"),
                        "remove_score": s.get("remove_score"),
                        "reason": s.get("reason") or "proposed_pairs_file",
                    }
                )
    proposals["arms"]["baseline_hybrid"] = {
        "swaps": [annotate_membership(s) for s in base_swaps[:1] if s],
        "note": (
            "Mirrors latest pool cycler proposal (not re-scored here). "
            "Tagged with membership heightened-potential gate (not deploy-ready)."
        ),
    }

    active_ejectable = [p for p in active if p not in sticky]
    for arm_name, scorer in scorers.items():
        add_scores: List[Tuple[str, float]] = []
        for pid in outside:
            if pid in active:
                continue
            sc = scorer(pid)
            if sc is not None:
                add_scores.append((pid, sc))
        rem_scores: List[Tuple[str, float]] = []
        for pid in active_ejectable:
            sc = scorer(pid)
            # low score = weak; if None treat as very weak for eject ranking only if flat
            if sc is None:
                if is_flat(pid):
                    rem_scores.append((pid, -999.0))
                continue
            rem_scores.append((pid, sc))
        add_scores.sort(key=lambda x: x[1], reverse=True)
        rem_scores.sort(key=lambda x: x[1])  # weakest first
        swap = None
        if add_scores and rem_scores:
            add_p, add_s = add_scores[0]
            # prefer flat weak
            rem_p, rem_s = None, None
            for cand, sc in rem_scores:
                if is_flat(cand):
                    rem_p, rem_s = cand, sc
                    break
            if rem_p is None:
                rem_p, rem_s = rem_scores[0]
            # require add meaningfully stronger
            if rem_s is not None and add_s - rem_s >= 0.02:
                # for -999 weak, always allow if add ok
                if rem_s == -999.0 or add_s > rem_s:
                    swap = {
                        "remove": rem_p,
                        "add": add_p,
                        "delta": None if rem_s == -999.0 else round(add_s - rem_s, 4),
                        "add_score": round(add_s, 4),
                        "remove_score": None if rem_s == -999.0 else round(rem_s, 4),
                        "reason": f"{arm_name}: add={add_p} score={add_s:.4f} eject={rem_p} score={rem_s}",
                        "remove_held_usd": float(held.get(rem_p) or 0.0),
                    }
                    swap = annotate_membership(swap)
        proposals["arms"][arm_name] = {
            "swaps": [swap] if swap else [],
            "top_adds": [{"pair": p, "score": round(s, 4)} for p, s in add_scores[:5]],
            "weak_active": [{"pair": p, "score": round(s, 4)} for p, s in rem_scores[:5]],
            "note": next(a.prior for a in ARMS if a.name == arm_name),
            "membership_boundary": "heightened_potential_M0-M3; deploy_ready_not_required",
        }

    # persist arm proposals (append if new unique day+pair)
    ARMS_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for arm_name, payload in proposals["arms"].items():
        if arm_name == "control_no_swap":
            continue
        arm_dir = ARMS_DIR / arm_name
        arm_dir.mkdir(parents=True, exist_ok=True)
        path = arm_dir / "proposals.jsonl"
        existing_keys = set()
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                ts = parse_ts(e.get("ts"))
                if ts:
                    existing_keys.add((ts.date().isoformat(), e.get("remove"), e.get("add")))
        for s in payload.get("swaps") or []:
            key = (now.date().isoformat(), s.get("remove"), s.get("add"))
            if key in existing_keys:
                continue
            rec = {
                "proposal_id": str(uuid.uuid4())[:12],
                "ts": _iso(now),
                "arm": arm_name,
                **s,
            }
            with path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            written.append(rec)
            existing_keys.add(key)
        (arm_dir / "latest.json").write_text(json.dumps(payload, indent=2) + "\n")

    proposals["written"] = written
    proposals["holdings_snapshot"] = {k: held.get(k) for k in active}
    proposals["meta"] = meta
    (STATE_DIR / "basket_select_arms_latest.json").write_text(json.dumps(proposals, indent=2) + "\n")
    return proposals


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def write_reports(cf: Dict[str, Any], arms_prop: Optional[Dict[str, Any]] = None) -> None:
    CF_LATEST.parent.mkdir(parents=True, exist_ok=True)
    CF_LATEST.write_text(json.dumps(cf, indent=2, default=str) + "\n")
    CF_ARMS_LATEST.write_text(json.dumps(cf.get("aggregate_by_arm") or {}, indent=2, default=str) + "\n")

    lines = [
        "# Basket swap shadow counterfactual",
        f"As of `{cf.get('as_of')}`",
        "",
        "Real Coinbase hourly candles. Equal-notional ADD vs REMOVE. **No live promote / no orders.**",
        "",
        "## Decision gate (baseline)",
        "",
        f"**{(cf.get('decide') or {}).get('status')}** — {(cf.get('decide') or {}).get('plain_english')}",
        "",
        "## Aggregate by arm",
        "",
    ]
    for arm, agg in sorted((cf.get("aggregate_by_arm") or {}).items()):
        lines.append(f"### `{arm}`")
        for label in ("1d", "3d", "7d", "14d"):
            a = agg.get(label) or {}
            if not a.get("n"):
                lines.append(f"- {label}: N=0")
                continue
            lines.append(
                f"- {label}: N={a['n']} mean excess **{a.get('mean_excess_pct'):+.2f}%** "
                f"(add {a.get('mean_add_pct'):+.2f} / rem {a.get('mean_rem_pct'):+.2f}) "
                f"hit {None if a.get('hit_excess_gt0') is None else round(a['hit_excess_gt0']*100)}%"
            )
        ps = agg.get("paper_sleeve_to_now")
        if ps:
            lines.append(
                f"- paper sleeve: N={ps['n']} ADD ${ps['nav_add']:.2f} vs REM ${ps['nav_rem']:.2f} "
                f"Δ ${ps['delta_usd']:+.2f}"
            )
        lines.append("")

    lines += ["## Unique swaps (recent)", ""]
    for r in (cf.get("unique_results") or [])[-20:]:
        lines.append(
            f"- `{r.get('arm')}` {str(r.get('ts'))[:19]} {r.get('remove')}→{r.get('add')} "
            f"excess_to_now={None if r.get('excess_to_now') is None else round(r['excess_to_now'],2)}"
        )
    CF_MD.parent.mkdir(parents=True, exist_ok=True)
    CF_MD.write_text("\n".join(lines) + "\n")

    alines = [
        "# Basket select arms (shadow parallel)",
        f"As of `{cf.get('as_of')}`",
        "",
        "No arm is pre-certified as high-probability. Priors are medium at best until CF N matures.",
        "",
    ]
    for arm in ARMS:
        alines.append(f"## `{arm.name}` — {arm.title}")
        alines.append(f"Prior: {arm.prior}")
        agg = (cf.get("aggregate_by_arm") or {}).get(arm.name) or {}
        d3 = agg.get("3d") or {}
        d7 = agg.get("7d") or {}
        alines.append(
            f"- CF 3d: N={d3.get('n',0)} excess={d3.get('mean_excess_pct')} | "
            f"7d: N={d7.get('n',0)} excess={d7.get('mean_excess_pct')}"
        )
        if arms_prop and arm.name in (arms_prop.get("arms") or {}):
            sw = (arms_prop["arms"][arm.name].get("swaps") or [])
            if sw:
                s = sw[0]
                alines.append(f"- Latest paper swap: {s.get('remove')} → {s.get('add')} ({s.get('reason','')[:120]})")
            else:
                alines.append("- Latest paper swap: *(none)*")
        alines.append("")
    ARMS_MD.write_text("\n".join(alines) + "\n")
    build_confidence_board(cf)


def run_full(propose: bool = True) -> Dict[str, Any]:
    arms_prop = propose_arm_swaps() if propose else None
    # Intersection log before CF so dual_agree ledger is in load_baseline_swaps()
    dual = record_dual_agree_swaps(arms_prop)
    swaps = load_baseline_swaps()
    unique = dedupe_swaps(swaps)
    cf = evaluate_swaps(unique)
    write_reports(cf, arms_prop)
    board = build_confidence_board(cf)
    return {
        "cf": cf,
        "arms_prop": arms_prop,
        "dual_agree": dual,
        "confidence_board": board,
    }


def plain_english_summary(bundle: Dict[str, Any]) -> str:
    cf = bundle.get("cf") or {}
    decide = cf.get("decide") or {}
    board = bundle.get("confidence_board") or {}
    dual = bundle.get("dual_agree") or {}
    lines = [
        "Basket select shadow CF",
        f"Gate: {decide.get('status')} — {decide.get('plain_english')}",
        f"HC board: {board.get('status')} · any_HC={board.get('any_arm_high_confidence')} "
        f"· leaders={board.get('leaders_sleeve_and_3d')}",
        "",
        "Arm scoreboard (mean excess when matured):",
    ]
    for arm, agg in sorted((cf.get("aggregate_by_arm") or {}).items()):
        d1 = agg.get("1d") or {}
        d3 = agg.get("3d") or {}
        ps = agg.get("paper_sleeve_to_now") or {}
        lines.append(
            f"  {arm}: 1d N={d1.get('n',0)} ex={_fmt(d1.get('mean_excess_pct'))} | "
            f"3d N={d3.get('n',0)} ex={_fmt(d3.get('mean_excess_pct'))} | "
            f"sleeveΔ={_fmt(ps.get('delta_usd'), money=True)}"
        )
    arms_prop = bundle.get("arms_prop") or {}
    written = arms_prop.get("written") or []
    if written:
        lines.append("")
        lines.append("New paper proposals this run:")
        for w in written:
            lines.append(f"  [{w.get('arm')}] {w.get('remove')} → {w.get('add')}")
    new_da = dual.get("new_agreements") or []
    if new_da or dual.get("this_run") is not None:
        lines.append("")
        lines.append(
            f"Dual-agree ({'+'.join(dual.get('agree_arms') or DUAL_AGREE_ARMS)}): "
            f"ledger_n={dual.get('total_ledger_n')} new={len(new_da)}"
        )
        tr = dual.get("this_run")
        if isinstance(tr, dict) and tr.get("agreed"):
            lines.append(f"  this_run AGREED {tr.get('remove')} → {tr.get('add')}")
        elif isinstance(tr, dict) and tr.get("agreed") is False:
            lines.append("  this_run diverged (co-leaders disagree on pair)")
        for w in new_da[:8]:
            lines.append(f"  [dual_agree] {w.get('remove')} → {w.get('add')}")
    lines.append("")
    lines.append("Anti-bleed: config untouched, no orders.")
    return "\n".join(lines)


def _fmt(x: Any, money: bool = False) -> str:
    if x is None:
        return "n/a"
    try:
        v = float(x)
    except Exception:
        return str(x)
    if money:
        return f"${v:+.2f}"
    return f"{v:+.2f}%"
