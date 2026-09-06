"""Goldilocks swap-rank shadow — timing urgency overlay on basket membership ranking.

Brad framing (2026-09-05):
  Coil + break-confirm + early structure is a *timing/urgency* signal that can
  re-rank swap ADD candidates higher when a name is primed — not a replacement
  for membership quality (M0–M3, missfire, CF excess) and not a live deploy gate.

Shadow only. No orders. No config apply. No evaluate_buy_entry wire.

Collection window: ~14d crumbs → mid/final report of measurable ADD−REMOVE excess
vs baseline ranking (cycler/energy) and vs control (no swap).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from phase6.core.paths import PROJECT_ROOT, load_trading_basket

logger = logging.getLogger("phase6.goldilocks_swap")

SCHEMA = "goldilocks_swap_shadow_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "goldilocks_swap_shadow_latest.json"
CRUMBS_PATH = PROJECT_ROOT / "data" / "state" / "goldilocks_swap_shadow_crumbs.jsonl"
REPORT_PATH = PROJECT_ROOT / "reports" / "GOLDILOCKS_SWAP_SHADOW_LATEST.md"
DECISION_PATH = PROJECT_ROOT / "data" / "state" / "goldilocks_swap_brad_decision.json"
ARTIFACT_PATH = PROJECT_ROOT / "data" / "state" / "goldilocks_swap_shadow_20260905.json"

# Sticky cores never ranked as REMOVE via this arm
STICKY = frozenset({"BTC-USD", "ETH-USD", "PAXG-USD", "PAXG-USDC", "USDC-USD", "USD-USD"})

# Urgency weights (sum to ~1.0 for components that fire)
W_COIL = 0.20
W_CONFIRM = 0.30
W_STRUCTURE = 0.25
W_PHASE_EARLY = 0.15
W_NOT_LATE = 0.10

# Rank inject: goldilocks_urgency * boost_scale added to base opportunity score [0,1]
DEFAULT_BOOST_SCALE = 0.35
MIN_URGENCY_TO_TAG = 0.45  # "primed" badge threshold
COLLECTION_DAYS = 14
FEE_RT = 0.002  # rough RT for paper excess haircut


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if not s:
        return ""
    if "-" not in s:
        s = f"{s}-USD"
    return s


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_universe() -> Tuple[List[str], List[str], List[str]]:
    """active basket, opportunity extras, full score universe (deduped)."""
    active = [_norm_pair(p) for p in load_trading_basket()]
    active = [p for p in active if p]
    opp: List[str] = []
    try:
        cfg = _load_json(PROJECT_ROOT / "config" / "trading_config_phase6.json") or {}
        p6 = cfg.get("phase_6_specific") or {}
        opp = [_norm_pair(x) for x in (p6.get("opportunity_pool") or []) if _norm_pair(x)]
    except Exception:
        opp = []
    # ADD candidates = opp not in active (plus allow scoring active for internal rank)
    active_set = set(active)
    extras = [p for p in opp if p not in active_set]
    universe = list(dict.fromkeys(active + extras + list(STICKY)))
    return active, extras, universe


def _ohlc_from_candles(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, List[float]]]:
    if not rows or len(rows) < 30:
        return None
    o, h, l, c, v = [], [], [], [], []
    for r in rows:
        try:
            o.append(float(r.get("o") if "o" in r else r.get("open")))
            h.append(float(r.get("h") if "h" in r else r.get("high")))
            l.append(float(r.get("l") if "l" in r else r.get("low")))
            c.append(float(r.get("c") if "c" in r else r.get("close")))
            v.append(float(r.get("v") if "v" in r else r.get("volume") or 0.0))
        except (TypeError, ValueError):
            return None
    return {"o": o, "h": h, "l": l, "c": c, "v": v}


def _btc_regime(closes: Sequence[float]) -> str:
    if len(closes) < 31 or closes[-31] <= 0:
        return "flat"
    r30 = closes[-1] / closes[-31] - 1.0
    if r30 >= 0.15:
        return "bull"
    if r30 <= -0.10:
        return "bear"
    if abs(r30) < 0.08:
        return "flat"
    return "transition"


@dataclass
class GoldilocksScore:
    pair: str
    urgency: float = 0.0
    primed: bool = False
    coil: bool = False
    confirm_up: bool = False
    s1: bool = False
    s2: bool = False
    s3: bool = False
    structure_ok: bool = False
    structure_late: bool = False
    phase: int = 0
    phase_name: str = ""
    fib_pos: Optional[float] = None
    regime: str = ""
    reasons: List[str] = field(default_factory=list)
    ok_data: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def score_pair_goldilocks(
    pair: str,
    *,
    candles: Optional[Sequence[Dict[str, Any]]] = None,
    regime: Optional[str] = None,
) -> GoldilocksScore:
    """Combine squeeze stack + run structure + run phase into urgency [0,1]."""
    p = _norm_pair(pair)
    out = GoldilocksScore(pair=p)
    try:
        from phase6.core.run_phase_deploy import (
            classify_run_phase,
            fetch_daily_candles_public,
            normalize_candles,
        )
        from phase6.core.run_lifecycle import classify_structure
        from phase6.research.squeeze_regime_breakout import evaluate_bar
    except Exception as e:
        out.reasons = [f"import_fail:{e}"]
        return out

    raw = list(candles) if candles is not None else []
    if not raw:
        try:
            raw = fetch_daily_candles_public(p, limit=90)
        except Exception as e:
            out.reasons = [f"candle_fail:{e}"]
            return out
    try:
        rows = normalize_candles(raw)
    except Exception as e:
        out.reasons = [f"normalize_fail:{e}"]
        return out

    oh = _ohlc_from_candles(rows)
    if not oh:
        out.reasons = ["insufficient_ohlc"]
        return out
    out.ok_data = True
    i = len(oh["c"]) - 1
    reg = regime or _btc_regime(oh["c"])  # placeholder; caller should pass BTC regime
    # Prefer external BTC regime when scoring alts
    try:
        sig = evaluate_bar(
            opens=oh["o"],
            highs=oh["h"],
            lows=oh["l"],
            closes=oh["c"],
            volumes=oh["v"],
            i=i,
            regime=reg,
        )
        out.coil = bool(sig.compression_recent or sig.compression_on)
        out.confirm_up = bool(sig.confirm_up)
        out.s1 = bool(sig.s1_up)
        out.s2 = bool(sig.s2_up)
        out.s3 = bool(sig.s3_up)
        out.regime = reg
        out.reasons.extend(list(sig.reasons)[:6])
    except Exception as e:
        out.reasons.append(f"squeeze_err:{e}")

    try:
        st = classify_structure(rows, pair=p)
        out.structure_ok = bool(st.structure_ok_for_entry)
        out.structure_late = bool(st.structure_late)
        out.fib_pos = st.fib_pos
        out.reasons.extend(list(st.notes)[:4])
    except Exception as e:
        out.reasons.append(f"structure_err:{e}")

    try:
        ph = classify_run_phase(rows, pair=p)
        out.phase = int(getattr(ph, "phase", 0) or 0)
        out.phase_name = str(getattr(ph, "phase_name", "") or getattr(ph, "name", "") or "")
        if not out.phase_name and hasattr(ph, "to_dict"):
            d = ph.to_dict()
            out.phase_name = str(d.get("phase_name") or d.get("phase") or "")
            out.phase = int(d.get("phase") or out.phase)
    except Exception as e:
        out.reasons.append(f"phase_err:{e}")

    # Urgency composite
    u = 0.0
    if out.coil:
        u += W_COIL
    if out.confirm_up:
        u += W_CONFIRM
    if out.s3:
        u += 0.05  # small full-stack bonus
    if out.structure_ok and not out.structure_late:
        u += W_STRUCTURE
    if out.phase in (1, 2):  # ignition / early trend
        u += W_PHASE_EARLY
    if not out.structure_late and out.phase < 3:
        u += W_NOT_LATE
    # Penalties
    if out.structure_late or out.phase >= 3:
        u *= 0.35
        out.reasons.append("late_penalty")
    if reg == "bear":
        u *= 0.25
        out.reasons.append("bear_haircut")

    out.urgency = max(0.0, min(1.0, u))
    out.primed = out.urgency >= MIN_URGENCY_TO_TAG and out.ok_data and not out.structure_late
    if out.primed:
        out.reasons.append("primed")
    return out


def _base_energy_score(pair: str, candles: Sequence[Dict[str, Any]]) -> float:
    """Simple 0–1 opportunity proxy (mom + vol expand) — baseline rank without goldilocks."""
    try:
        from phase6.core.run_phase_deploy import normalize_candles

        rows = normalize_candles(list(candles))
    except Exception:
        rows = list(candles)
    if len(rows) < 10:
        return 0.0
    closes = [float(r["c"]) for r in rows]
    vols = [float(r.get("v") or 0) for r in rows]
    if closes[-8] <= 0:
        return 0.0
    mom = closes[-1] / closes[-8] - 1.0  # ~1w
    mom_s = max(0.0, min(1.0, (mom + 0.05) / 0.25))  # -5%→0, +20%→1
    v_sma = sum(vols[-21:-1]) / max(1, len(vols[-21:-1])) if len(vols) > 21 else sum(vols[:-1]) / max(1, len(vols) - 1)
    v_r = (vols[-1] / v_sma) if v_sma > 0 else 1.0
    vol_s = max(0.0, min(1.0, (v_r - 0.8) / 1.5))
    return 0.55 * mom_s + 0.45 * vol_s


@dataclass
class RankedCandidate:
    pair: str
    role: str  # active | add_candidate
    base_score: float
    goldilocks_urgency: float
    boosted_score: float
    primed: bool
    goldilocks: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def rank_universe(
    *,
    boost_scale: float = DEFAULT_BOOST_SCALE,
    candle_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Score active + opp; inject goldilocks urgency into rank for ADD path."""
    active, extras, universe = load_universe()
    candle_map = candle_map or {}

    # BTC regime once
    btc_rows = candle_map.get("BTC-USD")
    if not btc_rows:
        try:
            from phase6.core.run_phase_deploy import fetch_daily_candles_public

            btc_rows = fetch_daily_candles_public("BTC-USD", limit=90)
            candle_map["BTC-USD"] = btc_rows
        except Exception:
            btc_rows = []
    regime = "flat"
    try:
        from phase6.core.run_phase_deploy import normalize_candles

        bc = normalize_candles(btc_rows)
        closes = [float(r["c"]) for r in bc]
        regime = _btc_regime(closes)
    except Exception:
        pass

    ranked: List[RankedCandidate] = []
    g_scores: Dict[str, GoldilocksScore] = {}

    for p in universe:
        if p in ("USDC-USD", "USD-USD"):
            continue
        rows = candle_map.get(p)
        if rows is None:
            try:
                from phase6.core.run_phase_deploy import fetch_daily_candles_public

                rows = fetch_daily_candles_public(p, limit=90)
                candle_map[p] = rows
            except Exception as e:
                g = GoldilocksScore(pair=p, reasons=[f"fetch:{e}"])
                g_scores[p] = g
                continue
        g = score_pair_goldilocks(p, candles=rows, regime=regime)
        g_scores[p] = g
        base = _base_energy_score(p, rows)
        boosted = min(1.0, base + float(boost_scale) * float(g.urgency))
        role = "active" if p in active else "add_candidate"
        ranked.append(
            RankedCandidate(
                pair=p,
                role=role,
                base_score=round(base, 4),
                goldilocks_urgency=round(g.urgency, 4),
                boosted_score=round(boosted, 4),
                primed=bool(g.primed),
                goldilocks=g.to_dict(),
            )
        )

    ranked.sort(key=lambda r: (-r.boosted_score, -r.goldilocks_urgency, r.pair))
    active_set = set(active)
    sticky = set(STICKY)

    # Propose paper swaps: weakest active (non-sticky, low boosted) → strongest primed ADD
    # Primed actives are protected from REMOVE (urgency = hold priority, not eject)
    actives = [
        r
        for r in ranked
        if r.pair in active_set and r.pair not in sticky and not r.primed
    ]
    adds = [r for r in ranked if r.role == "add_candidate"]
    actives_by_base = sorted(actives, key=lambda r: (r.base_score, r.boosted_score))
    actives_by_boost = sorted(actives, key=lambda r: (r.boosted_score, r.base_score))
    adds_by_base = sorted(adds, key=lambda r: (-r.base_score, -r.boosted_score))
    adds_by_boost = sorted(adds, key=lambda r: (-r.boosted_score, -r.goldilocks_urgency))

    baseline_swap = None
    goldilocks_swap = None
    if actives_by_base and adds_by_base:
        rm, ad = actives_by_base[0], adds_by_base[0]
        if ad.base_score - rm.base_score >= 0.05:
            baseline_swap = {
                "remove": rm.pair,
                "add": ad.pair,
                "arm": "baseline_energy",
                "delta": round(ad.base_score - rm.base_score, 4),
                "remove_score": rm.base_score,
                "add_score": ad.base_score,
            }
    if actives_by_boost and adds_by_boost:
        # Prefer primed ADDs when available
        primed_adds = [a for a in adds_by_boost if a.primed] or adds_by_boost
        rm, ad = actives_by_boost[0], primed_adds[0]
        # Require meaningful urgency inject OR primed ADD to count as goldilocks arm
        g_delta = ad.boosted_score - rm.boosted_score
        if g_delta >= 0.05:
            goldilocks_swap = {
                "remove": rm.pair,
                "add": ad.pair,
                "arm": "goldilocks_boost",
                "delta": round(g_delta, 4),
                "remove_score": rm.boosted_score,
                "add_score": ad.boosted_score,
                "add_urgency": ad.goldilocks_urgency,
                "add_primed": ad.primed,
                "differs_from_baseline": bool(
                    baseline_swap
                    and (
                        baseline_swap.get("remove") != rm.pair
                        or baseline_swap.get("add") != ad.pair
                    )
                )
                if baseline_swap
                else True,
            }

    primed_list = [r.pair for r in ranked if r.primed]
    return {
        "schema": SCHEMA,
        "as_of": _utc_now().isoformat(),
        "regime": regime,
        "boost_scale": boost_scale,
        "collection_days_target": COLLECTION_DAYS,
        "active_n": len(active),
        "add_candidates_n": len(extras),
        "primed_pairs": primed_list,
        "ranked": [r.to_dict() for r in ranked],
        "baseline_swap": baseline_swap,
        "goldilocks_swap": goldilocks_swap,
        "plain_english": _plain(regime, primed_list, baseline_swap, goldilocks_swap),
        "live_apply": False,
        "note": (
            "Shadow only. Goldilocks = timing urgency rank inject on top of base energy. "
            "Does not replace M0–M3 / missfire / dual_agree. No membership apply."
        ),
    }


def _plain(
    regime: str,
    primed: List[str],
    base_sw: Optional[Dict[str, Any]],
    g_sw: Optional[Dict[str, Any]],
) -> str:
    bits = [f"regime={regime}", f"primed={','.join(primed) or 'none'}"]
    if base_sw:
        bits.append(f"base_swap {base_sw['remove']}→{base_sw['add']} Δ{base_sw['delta']}")
    else:
        bits.append("base_swap=none")
    if g_sw:
        bits.append(
            f"g_swap {g_sw['remove']}→{g_sw['add']} urg={g_sw.get('add_urgency')} "
            f"differs={g_sw.get('differs_from_baseline')}"
        )
    else:
        bits.append("g_swap=none")
    return " · ".join(bits)


def _mark_fwd_excess(
    add: str,
    remove: str,
    *,
    candle_map: Dict[str, List[Dict[str, Any]]],
    horizons: Sequence[int] = (1, 3, 7),
) -> Dict[str, Any]:
    """If we have future bars in cache (historical backfill), score excess. Live crumbs leave null."""
    out: Dict[str, Any] = {"add": add, "remove": remove, "horizons": {}}
    # Live daily run cannot see future — always null; filled by delayed scorer
    for h in horizons:
        out["horizons"][str(h)] = None
    out["note"] = "forward filled by score_open_crumbs after horizon elapses"
    return out


def append_crumb(board: Dict[str, Any]) -> None:
    CRUMBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    g = board.get("goldilocks_swap")
    b = board.get("baseline_swap")
    row = {
        "ts": board.get("as_of"),
        "schema": SCHEMA,
        "regime": board.get("regime"),
        "primed": board.get("primed_pairs"),
        "baseline_swap": b,
        "goldilocks_swap": g,
        "scored_fwd": False,
        "fwd": {},
    }
    with CRUMBS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _close_on_or_after(rows: List[Dict[str, Any]], ts_iso: str, days: int) -> Optional[float]:
    """Find close ~days after crumb ts (daily bars)."""
    try:
        from phase6.core.run_phase_deploy import normalize_candles

        rows = normalize_candles(rows)
    except Exception:
        pass
    if not rows:
        return None
    try:
        t0 = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
    except Exception:
        return None
    target = t0 + timedelta(days=days)
    # rows have 't' unix
    best = None
    best_dt = None
    for r in rows:
        t = r.get("t")
        try:
            dt = datetime.fromtimestamp(float(t), tz=timezone.utc)
        except Exception:
            continue
        if dt.date() >= target.date():
            if best_dt is None or dt < best_dt:
                best_dt = dt
                best = float(r["c"])
            if dt.date() == target.date():
                return float(r["c"])
    return best


def _close_at_crumb(rows: List[Dict[str, Any]], ts_iso: str) -> Optional[float]:
    try:
        from phase6.core.run_phase_deploy import normalize_candles

        rows = normalize_candles(rows)
    except Exception:
        pass
    try:
        t0 = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00"))
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
    except Exception:
        return None
    # last close on/before crumb day
    best = None
    for r in rows:
        t = r.get("t")
        try:
            dt = datetime.fromtimestamp(float(t), tz=timezone.utc)
        except Exception:
            continue
        if dt.date() <= t0.date():
            best = float(r["c"])
    return best


def score_open_crumbs(*, max_rows: int = 500) -> Dict[str, Any]:
    """Backfill 1d/3d/7d ADD−REMOVE excess on crumbs old enough. Shadow CF."""
    if not CRUMBS_PATH.exists():
        return {"n": 0, "note": "no crumbs"}
    lines = CRUMBS_PATH.read_text(encoding="utf-8").strip().splitlines()[-max_rows:]
    rows_in = []
    for line in lines:
        try:
            rows_in.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    from phase6.core.run_phase_deploy import fetch_daily_candles_public

    cache: Dict[str, List] = {}
    updated = []
    stats = {
        "goldilocks": {h: [] for h in ("1", "3", "7")},
        "baseline": {h: [] for h in ("1", "3", "7")},
        "when_differs": {h: [] for h in ("1", "3", "7")},
    }

    def get_px(pair: str) -> List:
        if pair not in cache:
            try:
                cache[pair] = fetch_daily_candles_public(pair, limit=120)
            except Exception:
                cache[pair] = []
        return cache[pair]

    out_lines = []
    for row in rows_in:
        ts = row.get("ts") or ""
        fwd = dict(row.get("fwd") or {})
        for arm_key, label in (("goldilocks_swap", "goldilocks"), ("baseline_swap", "baseline")):
            sw = row.get(arm_key)
            if not isinstance(sw, dict):
                continue
            add, rem = sw.get("add"), sw.get("remove")
            if not add or not rem:
                continue
            arm_fwd = dict(fwd.get(label) or {})
            for h in (1, 3, 7):
                hk = str(h)
                if arm_fwd.get(hk) is not None:
                    # already scored
                    try:
                        stats[label][hk].append(float(arm_fwd[hk]["excess_net"]))
                        if label == "goldilocks" and row.get("goldilocks_swap", {}).get(
                            "differs_from_baseline"
                        ):
                            stats["when_differs"][hk].append(float(arm_fwd[hk]["excess_net"]))
                    except Exception:
                        pass
                    continue
                # need age
                try:
                    t0 = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if t0.tzinfo is None:
                        t0 = t0.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                age = (_utc_now() - t0).total_seconds() / 86400.0
                if age < h + 0.2:
                    continue
                a_rows, r_rows = get_px(str(add)), get_px(str(rem))
                a0 = _close_at_crumb(a_rows, str(ts))
                r0 = _close_at_crumb(r_rows, str(ts))
                a1 = _close_on_or_after(a_rows, str(ts), h)
                r1 = _close_on_or_after(r_rows, str(ts), h)
                if not all(x and x > 0 for x in (a0, r0, a1, r1)):
                    continue
                ret_a = a1 / a0 - 1.0
                ret_r = r1 / r0 - 1.0
                excess = ret_a - ret_r
                excess_net = excess - FEE_RT
                arm_fwd[hk] = {
                    "ret_add": round(ret_a, 6),
                    "ret_remove": round(ret_r, 6),
                    "excess": round(excess, 6),
                    "excess_net": round(excess_net, 6),
                }
                stats[label][hk].append(excess_net)
                if label == "goldilocks" and sw.get("differs_from_baseline"):
                    stats["when_differs"][hk].append(excess_net)
            fwd[label] = arm_fwd
        row["fwd"] = fwd
        row["scored_fwd"] = bool(fwd)
        out_lines.append(row)
        updated.append(row)

    # rewrite crumbs file (bounded)
    CRUMBS_PATH.write_text(
        "".join(json.dumps(r, default=str) + "\n" for r in out_lines),
        encoding="utf-8",
    )

    def _summ(xs: List[float]) -> Dict[str, Any]:
        if not xs:
            return {"n": 0, "mean": None, "hit": None}
        return {
            "n": len(xs),
            "mean": round(sum(xs) / len(xs), 6),
            "hit": round(sum(1 for x in xs if x > 0) / len(xs), 4),
        }

    summary = {
        "as_of": _utc_now().isoformat(),
        "goldilocks": {h: _summ(stats["goldilocks"][h]) for h in ("1", "3", "7")},
        "baseline": {h: _summ(stats["baseline"][h]) for h in ("1", "3", "7")},
        "when_differs": {h: _summ(stats["when_differs"][h]) for h in ("1", "3", "7")},
        "n_crumbs": len(out_lines),
        "advantage_claim": _advantage_claim(stats),
    }
    return summary


def _advantage_claim(stats: Dict[str, Any]) -> str:
    g7 = stats["goldilocks"]["7"]
    b7 = stats["baseline"]["7"]
    d7 = stats["when_differs"]["7"]
    if len(g7) < 8:
        return f"inconclusive_sparse N_g7={len(g7)} need≥8 (prefer≥12 over 14d)"
    g_m = sum(g7) / len(g7)
    b_m = sum(b7) / len(b7) if b7 else 0.0
    if g_m > 0 and g_m > b_m + 0.005:
        return "ATTENTION_ONLY_timing_boost — goldilocks 7d excess > baseline; not promote"
    if g_m <= 0:
        return "no_edge_goldilocks_7d_mean≤0"
    return "no_clear_advantage_vs_baseline"


def _render_md(board: Dict[str, Any], cf: Optional[Dict[str, Any]] = None) -> str:
    lines = [
        "# Goldilocks swap-rank shadow",
        "",
        f"_as_of {board.get('as_of')} · regime={board.get('regime')} · **shadow only**_",
        "",
        board.get("plain_english") or "",
        "",
        "## What this is",
        "",
        "- **Not** a new membership quality gate (M0–M3 / missfire stay).",
        "- **Is** a timing urgency score that *boosts rank* of primed ADD candidates.",
        "- Live apply = **false**. Paper CF over ~14d crumbs.",
        "",
        "## Primed now",
        "",
    ]
    primed = board.get("primed_pairs") or []
    if primed:
        for p in primed:
            lines.append(f"- **{p}**")
    else:
        lines.append("- _(none)_")
    lines += ["", "## Paper swaps", ""]
    for label, key in (("Baseline energy", "baseline_swap"), ("Goldilocks boost", "goldilocks_swap")):
        sw = board.get(key)
        if sw:
            lines.append(
                f"- **{label}:** `{sw.get('remove')}` → `{sw.get('add')}` "
                f"Δ={sw.get('delta')} urg={sw.get('add_urgency', '—')}"
            )
        else:
            lines.append(f"- **{label}:** none")
    lines += ["", "## Top boosted ranks", "", "| pair | role | base | urgency | boosted | primed |", "|------|------|------|---------|---------|--------|"]
    for r in (board.get("ranked") or [])[:16]:
        lines.append(
            f"| {r.get('pair')} | {r.get('role')} | {r.get('base_score')} | "
            f"{r.get('goldilocks_urgency')} | {r.get('boosted_score')} | {r.get('primed')} |"
        )
    if cf:
        lines += ["", "## Rolling CF (scored crumbs)", ""]
        for arm in ("goldilocks", "baseline", "when_differs"):
            block = cf.get(arm) or {}
            lines.append(f"**{arm}**")
            for h in ("1", "3", "7"):
                s = block.get(h) or {}
                lines.append(
                    f"- {h}d: n={s.get('n')} mean_excess_net={s.get('mean')} hit={s.get('hit')}"
                )
            lines.append("")
        lines.append(f"**Claim:** {cf.get('advantage_claim')}")
        lines.append("")
    lines += [
        "## 14-day success bar (pre-registered)",
        "",
        "1. ≥8 scored goldilocks swaps at 7d (prefer ≥12).",
        "2. mean 7d ADD−REMOVE excess_net > 0 **and** > baseline by ≥0.5pp when arms differ.",
        "3. Still **ATTENTION_ONLY** until multipair stability — no auto-promote, no live rank wire.",
        "4. Fail → drop or redesign weights; do not fish cutoffs on same crumbs.",
        "",
    ]
    return "\n".join(lines) + "\n"


def run_shadow_cycle(*, write_crumb: bool = True, score_fwd: bool = True) -> Dict[str, Any]:
    board = rank_universe()
    if write_crumb:
        append_crumb(board)
    cf = score_open_crumbs() if score_fwd else {}
    board["cf_summary"] = cf
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(board, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(_render_md(board, cf), encoding="utf-8")
    return board


def ensure_decision_stub() -> None:
    if DECISION_PATH.exists():
        return
    DECISION_PATH.write_text(
        json.dumps(
            {
                "schema": "goldilocks_swap_brad_decision_v1",
                "as_of": _utc_now().isoformat(),
                "live_rank_inject": False,
                "live_membership": False,
                "shadow_collect_days": COLLECTION_DAYS,
                "started": _utc_now().date().isoformat(),
                "revisit_after": (_utc_now() + timedelta(days=COLLECTION_DAYS)).date().isoformat(),
                "note": "Brad GO 2026-09-05: shadow 14d. No live wire until revisit + advantage bar.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


__all__ = [
    "score_pair_goldilocks",
    "rank_universe",
    "run_shadow_cycle",
    "score_open_crumbs",
    "GoldilocksScore",
]
