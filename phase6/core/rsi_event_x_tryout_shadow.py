#!/usr/bin/env python3
"""
RSI-event → single-pair X → tryout shadow (measure only).

Problem
-------
Clocked X (2×/day) + 15m half-life leaves tryout doors with washed RSI
but aged-out eng=0 between slots. Operator luck stack: window → $75 → TP.

Doctrine (Brad 2026-09-15)
--------------------------
Shadow-only event path:
  1. Universe = **production tryout-eligible SSOT** (same doors live can seat)
     — prefer tryout_readiness.eligible ∩ scoreboard.eligible; not full basket; not tier-A ballast
  2. Trigger = RSI in wash band + eng aged-out / below tryout floor
  3. Rank candidates; keep top K (default 2) as would-query / would-tryout
  4. Estimate would_pass from *cached* last X raw (no paid API by default)
  5. Simulate evaluate_buy_entry with hypothetical eng=floor if would_pass
     + surface production_live_gate (actual eng) for apples-to-apples
  6. Never place orders, never mutate config, never wire live buy path

Edge class: ATTENTION_ONLY_sensor_clock — not HIT abs / not promote.
Live wire needs Brad GO + spend caps + isolation green.

Artifacts
---------
  data/state/rsi_event_x_tryout_shadow_latest.json
  data/state/rsi_event_x_tryout_shadow_events.jsonl
  reports/RSI_EVENT_X_TRYOUT_SHADOW_LATEST.md
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

SCHEMA = "rsi_event_x_tryout_shadow_v1"
LATEST = STATE_DIR / "rsi_event_x_tryout_shadow_latest.json"
EVENTS = STATE_DIR / "rsi_event_x_tryout_shadow_events.jsonl"
MD_REPORT = PROJECT_ROOT / "reports" / "RSI_EVENT_X_TRYOUT_SHADOW_LATEST.md"
RSI_CACHE = STATE_DIR / "rsi_cache.json"
X_CACHE = STATE_DIR / "x_sentiment_cache.json"
SCOREBOARD = STATE_DIR / "recovery_tryout_scoreboard_latest.json"
READINESS = STATE_DIR / "tryout_readiness_latest.json"

# Frozen defaults (shadow). Live GO can tighten further.
DEFAULT_RSI_WASH_MAX = 40.0  # stricter than tryout max_rsi 55
DEFAULT_RSI_WASH_MIN = 0.0
DEFAULT_TOP_K = 2
DEFAULT_TRYOUT_FLOOR = 0.30
DEFAULT_X_FRESH_MAX_MIN = 180.0  # cached X usable for would_pass estimate
DEFAULT_ENG_AGED_OUT_MAX = 0.05  # treat ~0 as aged-out dust


@dataclass
class ShadowConfig:
    rsi_wash_max: float = DEFAULT_RSI_WASH_MAX
    rsi_wash_min: float = DEFAULT_RSI_WASH_MIN
    top_k: int = DEFAULT_TOP_K
    tryout_floor: float = DEFAULT_TRYOUT_FLOOR
    x_fresh_max_min: float = DEFAULT_X_FRESH_MAX_MIN
    eng_aged_out_max: float = DEFAULT_ENG_AGED_OUT_MAX
    # Hard fences — never flip in this module
    place_orders: bool = False
    mutate_config: bool = False
    spend_x: bool = False  # default off: no paid API
    pairs_override: Tuple[str, ...] = ()


@dataclass
class PairCandidate:
    pair: str
    rsi: Optional[float] = None
    eng_sent: Optional[float] = None
    eng_source: Optional[str] = None
    eng_age_min: Optional[float] = None
    x_raw: Optional[float] = None
    x_age_min: Optional[float] = None
    x_posts: Optional[int] = None
    tryout_eligible: bool = False
    buy_blocked: bool = False
    block_reasons: List[str] = field(default_factory=list)
    trigger_rsi_wash: bool = False
    trigger_eng_stale: bool = False
    would_query_x: bool = False
    would_pass_floor_est: Optional[bool] = None  # None = unknown (no usable fresh X)
    last_x_clears_floor: Optional[bool] = None  # age-agnostic hint from last raw
    would_buy_if_pass: Optional[bool] = None
    buy_sim_reasons: List[str] = field(default_factory=list)
    rank_score: float = 0.0
    selected_top_k: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Pure helpers (isolation-tested; no I/O)
# ---------------------------------------------------------------------------


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def age_minutes(ts: Any, now: Optional[datetime] = None) -> Optional[float]:
    dt = _parse_ts(ts)
    if dt is None:
        return None
    now = now or _utc_now()
    return max(0.0, (now - dt).total_seconds() / 60.0)


def is_rsi_wash(
    rsi: Optional[float],
    *,
    wash_min: float = DEFAULT_RSI_WASH_MIN,
    wash_max: float = DEFAULT_RSI_WASH_MAX,
) -> bool:
    if rsi is None:
        return False
    try:
        r = float(rsi)
    except (TypeError, ValueError):
        return False
    return wash_min <= r <= wash_max


def is_eng_stale_for_event(
    eng: Optional[float],
    *,
    floor: float = DEFAULT_TRYOUT_FLOOR,
    aged_out_max: float = DEFAULT_ENG_AGED_OUT_MAX,
    age_min: Optional[float] = None,
    fresh_max_min: float = 20.0,
) -> bool:
    """True when eng cannot clear a tryout door (missing, dust, or under floor + not fresh)."""
    if eng is None:
        return True
    try:
        e = float(eng)
    except (TypeError, ValueError):
        return True
    if abs(e) <= aged_out_max:
        return True
    if e >= floor:
        # Already clearing — no need to spend X (not an event gap)
        return False
    # Under floor: stale if aged or unknown age
    if age_min is None:
        return True
    return age_min >= fresh_max_min


def rank_score_for_candidate(
    *,
    rsi: Optional[float],
    tryout_eligible: bool,
    buy_blocked: bool,
    would_pass_floor_est: Optional[bool],
    wash_max: float = DEFAULT_RSI_WASH_MAX,
) -> float:
    """
    Higher = more interesting event candidate.
    Prefer deeper wash, eligible, unblocked, and (if known) X that would clear floor.
    """
    if not tryout_eligible or buy_blocked:
        return -1e9
    if rsi is None:
        return -1e6
    # Deeper wash scores higher (RSI 20 > RSI 39)
    depth = max(0.0, float(wash_max) - float(rsi))
    score = 100.0 + depth * 2.0
    if would_pass_floor_est is True:
        score += 25.0
    elif would_pass_floor_est is False:
        score -= 15.0  # still may query, but rank lower
    # slight prefer mid-wash over absolute zero (dead tape) — keep small
    if float(rsi) < 15.0:
        score -= 5.0
    return score


def select_top_k(
    candidates: Sequence[PairCandidate],
    *,
    k: int = DEFAULT_TOP_K,
) -> List[PairCandidate]:
    """Mark would_query on top-k triggerable rows; return selected list (new objects not required)."""
    k = max(0, int(k))
    pool = [
        c
        for c in candidates
        if c.tryout_eligible
        and not c.buy_blocked
        and c.trigger_rsi_wash
        and c.trigger_eng_stale
    ]
    pool_sorted = sorted(pool, key=lambda c: (-c.rank_score, c.pair))
    selected = pool_sorted[:k]
    sel_pairs = {c.pair for c in selected}
    for c in candidates:
        if c.pair in sel_pairs:
            c.selected_top_k = True
            c.would_query_x = True
        else:
            c.selected_top_k = False
            # keep would_query false unless already set
            if not (c.trigger_rsi_wash and c.trigger_eng_stale and c.tryout_eligible and not c.buy_blocked):
                c.would_query_x = False
            elif c.pair not in sel_pairs:
                c.would_query_x = False
    return selected


def estimate_would_pass_floor(
    x_raw: Optional[float],
    *,
    floor: float,
    x_age_min: Optional[float],
    x_fresh_max_min: float,
) -> Optional[bool]:
    """None = unknown (no fresh-enough cached X)."""
    if x_raw is None:
        return None
    if x_age_min is None or x_age_min > x_fresh_max_min:
        return None
    try:
        return float(x_raw) >= float(floor)
    except (TypeError, ValueError):
        return None


def evaluate_candidate_pure(
    *,
    pair: str,
    rsi: Optional[float],
    eng_sent: Optional[float],
    eng_age_min: Optional[float],
    x_raw: Optional[float],
    x_age_min: Optional[float],
    tryout_eligible: bool,
    buy_blocked: bool,
    block_reasons: Optional[Sequence[str]] = None,
    cfg: Optional[ShadowConfig] = None,
) -> PairCandidate:
    cfg = cfg or ShadowConfig()
    p = _norm_pair(pair)
    c = PairCandidate(
        pair=p,
        rsi=float(rsi) if rsi is not None else None,
        eng_sent=float(eng_sent) if eng_sent is not None else None,
        eng_age_min=eng_age_min,
        x_raw=float(x_raw) if x_raw is not None else None,
        x_age_min=x_age_min,
        tryout_eligible=bool(tryout_eligible),
        buy_blocked=bool(buy_blocked),
        block_reasons=list(block_reasons or []),
    )
    c.trigger_rsi_wash = is_rsi_wash(
        c.rsi, wash_min=cfg.rsi_wash_min, wash_max=cfg.rsi_wash_max
    )
    c.trigger_eng_stale = is_eng_stale_for_event(
        c.eng_sent,
        floor=cfg.tryout_floor,
        aged_out_max=cfg.eng_aged_out_max,
        age_min=c.eng_age_min,
    )
    c.would_pass_floor_est = estimate_would_pass_floor(
        c.x_raw,
        floor=cfg.tryout_floor,
        x_age_min=c.x_age_min,
        x_fresh_max_min=cfg.x_fresh_max_min,
    )
    if c.x_raw is not None:
        try:
            c.last_x_clears_floor = float(c.x_raw) >= float(cfg.tryout_floor)
        except (TypeError, ValueError):
            c.last_x_clears_floor = None
    c.rank_score = rank_score_for_candidate(
        rsi=c.rsi,
        tryout_eligible=c.tryout_eligible,
        buy_blocked=c.buy_blocked,
        would_pass_floor_est=(
            c.would_pass_floor_est
            if c.would_pass_floor_est is not None
            else c.last_x_clears_floor
        ),
        wash_max=cfg.rsi_wash_max,
    )
    # would_buy only meaningful if we assume X clears floor — still other gates
    if not c.tryout_eligible:
        c.notes.append("not_tryout_eligible")
    if c.buy_blocked:
        c.notes.append("buy_blocked")
    if c.trigger_rsi_wash and c.trigger_eng_stale and c.tryout_eligible and not c.buy_blocked:
        c.notes.append("event_gap_candidate")
    return c


# ---------------------------------------------------------------------------
# I/O loaders
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_rsi_map(path: Path = RSI_CACHE) -> Dict[str, float]:
    raw = _read_json(path)
    out: Dict[str, float] = {}
    if not isinstance(raw, dict):
        return out
    block = raw.get("rsi") if isinstance(raw.get("rsi"), dict) else raw
    if not isinstance(block, dict):
        return out
    for k, v in block.items():
        p = _norm_pair(k)
        try:
            if isinstance(v, dict):
                out[p] = float(v.get("rsi"))
            else:
                out[p] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def load_x_pair_details(
    path: Path = X_CACHE, *, now: Optional[datetime] = None
) -> Dict[str, Dict[str, Any]]:
    """pair -> {raw, age_min, posts, ts}"""
    now = now or _utc_now()
    raw = _read_json(path)
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(raw, dict):
        return out
    # shapes: {scores: {}}, {pairs: {}}, or flat pair keys with {sentiment, timestamp, post_count}
    pairs_block = None
    for key in ("pairs", "scores", "x", "data"):
        if isinstance(raw.get(key), dict):
            pairs_block = raw[key]
            break
    if pairs_block is None:
        pairs_block = {
            k: v
            for k, v in raw.items()
            if isinstance(k, str) and ("-USD" in k.upper() or k.upper().endswith("USD"))
        }
    global_ts = raw.get("updated_at") or raw.get("as_of") or raw.get("timestamp")
    for k, v in (pairs_block or {}).items():
        p = _norm_pair(k)
        score = None
        posts = None
        ts = global_ts
        if isinstance(v, (int, float)):
            score = float(v)
        elif isinstance(v, dict):
            for sk in (
                "raw",
                "sentiment",
                "score",
                "sentiment_score",
                "x_raw",
                "value",
            ):
                if isinstance(v.get(sk), (int, float)):
                    score = float(v[sk])
                    break
            posts = (
                v.get("posts")
                or v.get("n_posts")
                or v.get("post_count")
                or v.get("count")
            )
            ts = v.get("updated_at") or v.get("ts") or v.get("timestamp") or ts
        if score is None:
            continue
        out[p] = {
            "raw": score,
            "age_min": age_minutes(ts, now=now),
            "posts": int(posts) if isinstance(posts, (int, float)) else None,
            "ts": ts,
        }
    return out


def _iter_readiness_pair_rows(tr: Any) -> Iterable[Tuple[str, Dict[str, Any]]]:
    """tryout_readiness pairs may be dict OR list of row dicts."""
    if not isinstance(tr, dict):
        return []
    pairs = tr.get("pairs")
    rows: List[Tuple[str, Dict[str, Any]]] = []
    if isinstance(pairs, dict):
        for k, v in pairs.items():
            if isinstance(v, dict):
                rows.append((_norm_pair(k), v))
    elif isinstance(pairs, list):
        for v in pairs:
            if not isinstance(v, dict):
                continue
            p = _norm_pair(str(v.get("pair") or v.get("symbol") or ""))
            if p:
                rows.append((p, v))
    return rows


def load_eng_pair_details(
    *, now: Optional[datetime] = None
) -> Dict[str, Dict[str, Any]]:
    """Best-effort eng scores from tryout readiness rows."""
    now = now or _utc_now()
    out: Dict[str, Dict[str, Any]] = {}
    tr = _read_json(READINESS)
    as_of_age = age_minutes(tr.get("as_of_utc") or tr.get("as_of"), now=now) if isinstance(tr, dict) else None
    for p, v in _iter_readiness_pair_rows(tr):
        eng = None
        for sk in ("eng_sent", "sentiment", "sent", "aged_sent", "score"):
            if isinstance(v.get(sk), (int, float)):
                eng = float(v[sk])
                break
        age = None
        for ak in ("sent_age_min", "eng_age_min", "age_min"):
            if isinstance(v.get(ak), (int, float)):
                age = float(v[ak])
                break
        if age is None:
            age = as_of_age
        src = v.get("sent_source") or v.get("source") or "tryout_readiness"
        out[p] = {
            "eng": eng,
            "age_min": age,
            "source": str(src) if src else None,
            "buy_block": bool(v.get("buy_block") or v.get("blocked")),
            "reasons": list(v.get("deny_reasons") or v.get("reasons") or [])[:6],
            "deploy_ready": v.get("deploy_ready"),
            "entry_ok": v.get("entry_ok") if v.get("entry_ok") is not None else v.get("allowed"),
            # supplemental last X from readiness board (may differ from cache file)
            "x_raw_board": float(v["x_raw"]) if isinstance(v.get("x_raw"), (int, float)) else None,
            "x_posts_board": int(v["x_posts"]) if isinstance(v.get("x_posts"), (int, float)) else None,
        }
    return out


def _norm_pair_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for p in raw:
        n = _norm_pair(str(p or ""))
        if n and n not in out:
            out.append(n)
    return out


def production_tryout_eligible_sources() -> Dict[str, Any]:
    """
    Apples-to-apples SSOT for doors production can open under quality_tryout.

    Prefer intersection of:
      - tryout_readiness.eligible_tryout_pairs  (ops / gate board)
      - recovery_tryout_scoreboard.eligible_tryout_pairs  (v2 qualify + thaw)
    Fallbacks keep shadow alive if one artifact is missing.
    Never expands to full basket or tier-A ballast.
    """
    tr = _read_json(READINESS)
    sb = _read_json(SCOREBOARD)
    tr_elig = _norm_pair_list(tr.get("eligible_tryout_pairs") if isinstance(tr, dict) else None)
    sb_elig = _norm_pair_list(sb.get("eligible_tryout_pairs") if isinstance(sb, dict) else None)

    policy_elig: List[str] = []
    policy_err: Optional[str] = None
    try:
        from phase6.core.regime_cash_policy import (
            _recovery_rec,
            load_policy,
            recovery_tryout_pairs_effective,
        )

        pol = load_policy()
        rec = _recovery_rec(pol) or {}
        policy_elig = sorted(recovery_tryout_pairs_effective(rec)) if isinstance(rec, dict) else []
    except Exception as e:
        policy_err = f"{type(e).__name__}:{e}"

    source = "empty"
    universe: List[str] = []
    if tr_elig and sb_elig:
        inter = sorted(set(tr_elig) & set(sb_elig))
        if inter:
            universe = inter
            source = "readiness_intersect_scoreboard"
        else:
            # both present but empty intersect → fail closed to empty with note
            universe = []
            source = "empty_intersect_fail_closed"
    elif tr_elig:
        universe = sorted(tr_elig)
        source = "tryout_readiness_only"
    elif sb_elig:
        universe = sorted(sb_elig)
        source = "scoreboard_only"
    elif policy_elig:
        universe = sorted(policy_elig)
        source = "policy_effective_fallback"

    only_tr = sorted(set(tr_elig) - set(sb_elig)) if tr_elig and sb_elig else []
    only_sb = sorted(set(sb_elig) - set(tr_elig)) if tr_elig and sb_elig else []
    parity_ok = bool(tr_elig) and bool(sb_elig) and not only_tr and not only_sb

    return {
        "universe": universe,
        "source": source,
        "parity_ok": parity_ok,
        "tryout_readiness_eligible": tr_elig,
        "scoreboard_eligible": sb_elig,
        "policy_effective_eligible": policy_elig,
        "only_in_readiness": only_tr,
        "only_in_scoreboard": only_sb,
        "policy_err": policy_err,
        "note": (
            "Production tryout doors only — same eligible set live quality_tryout "
            "can seat (v2 + thaw). Not tier-A ballast, not full basket, not tier-C "
            "outside thaw/force_eligible."
        ),
    }


def load_tryout_universe(cfg: ShadowConfig) -> List[str]:
    if cfg.pairs_override:
        return [_norm_pair(p) for p in cfg.pairs_override]
    meta = production_tryout_eligible_sources()
    return list(meta.get("universe") or [])


def load_tryout_universe_with_meta(cfg: ShadowConfig) -> Tuple[List[str], Dict[str, Any]]:
    """Universe + parity meta for board honesty / R1 mirror."""
    if cfg.pairs_override:
        u = [_norm_pair(p) for p in cfg.pairs_override]
        return u, {
            "universe": u,
            "source": "pairs_override",
            "parity_ok": None,
            "note": "operator override — not pure production mirror",
        }
    meta = production_tryout_eligible_sources()
    return list(meta.get("universe") or []), meta


def _simulate_buy_if_x_clears(
    pair: str,
    *,
    rsi: Optional[float],
    floor: float,
) -> Tuple[Optional[bool], List[str]]:
    """
    Call evaluate_buy_entry with sentiment=floor (hypothetical clear).
    Returns (allowed, reasons). On import/runtime failure → (None, [err]).
    """
    try:
        from phase6.core.regime_cash_policy import (
            evaluate_buy_entry,
            load_policy,
            resolve_regime_cash,
        )

        pol = load_policy()
        # Live process tax / missfire still apply — honesty over green paint
        snap = resolve_regime_cash(policy=pol)
        dec = evaluate_buy_entry(
            pair,
            snap,
            sentiment=float(floor),
            rsi=rsi,
            is_new_pair=True,
            policy=pol,
        )
        return bool(dec.allowed), list(dec.reasons or [])[:8]
    except Exception as e:
        return None, [f"buy_sim_error:{type(e).__name__}:{e}"]

# ---------------------------------------------------------------------------
# Board builder
# ---------------------------------------------------------------------------


def _production_live_gate(
    pair: str,
    *,
    eng_sent: Optional[float],
    rsi: Optional[float],
) -> Dict[str, Any]:
    """
    Live evaluate_buy_entry with *actual* eng (not hypothetical floor).
    Surfaces same-day / seats / latch / sent so shadow is comparable to prod.
    """
    try:
        from phase6.core.regime_cash_policy import (
            evaluate_buy_entry,
            load_policy,
            resolve_regime_cash,
        )

        pol = load_policy()
        snap = resolve_regime_cash(policy=pol)
        dec = evaluate_buy_entry(
            pair,
            snap,
            sentiment=eng_sent,
            rsi=rsi,
            is_new_pair=True,
            policy=pol,
        )
        return {
            "allowed": bool(dec.allowed),
            "reasons": list(dec.reasons or [])[:8],
        }
    except Exception as e:
        return {"allowed": None, "reasons": [f"live_gate_err:{type(e).__name__}:{e}"]}


def build_shadow_board(
    cfg: Optional[ShadowConfig] = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    cfg = cfg or ShadowConfig()
    assert cfg.place_orders is False
    assert cfg.mutate_config is False
    now = now or _utc_now()

    universe, univ_meta = load_tryout_universe_with_meta(cfg)
    rsi_map = load_rsi_map()
    x_map = load_x_pair_details(now=now)
    eng_map = load_eng_pair_details(now=now)

    # hard blocks from policy
    blocks: set = set()
    try:
        from phase6.core.regime_cash_policy import collect_buy_block_pairs, load_policy

        blocks = set(collect_buy_block_pairs(load_policy()))
    except Exception:
        blocks = set()

    candidates: List[PairCandidate] = []
    for pair in universe:
        eng_row = eng_map.get(pair) or {}
        x_row = x_map.get(pair) or {}
        blocked = pair in blocks or bool(eng_row.get("buy_block"))
        reasons = list(eng_row.get("reasons") or [])
        if pair in blocks:
            reasons = [f"buy_block_pairs {pair}"] + reasons
        x_raw = x_row.get("raw")
        x_age = x_row.get("age_min")
        x_posts = x_row.get("posts")
        # Prefer cache; fall back to readiness board x_raw (age unknown → stale)
        if x_raw is None and eng_row.get("x_raw_board") is not None:
            x_raw = eng_row.get("x_raw_board")
            x_age = None  # force unknown / not fresh for pass_est honesty
            x_posts = eng_row.get("x_posts_board")
        c = evaluate_candidate_pure(
            pair=pair,
            rsi=rsi_map.get(pair),
            eng_sent=eng_row.get("eng"),
            eng_age_min=eng_row.get("age_min"),
            x_raw=x_raw,
            x_age_min=x_age,
            tryout_eligible=True,  # universe already production tryout doors
            buy_blocked=blocked,
            block_reasons=reasons,
            cfg=cfg,
        )
        c.eng_source = eng_row.get("source")
        c.x_posts = x_posts if x_posts is not None else x_row.get("posts")
        # production live gate (actual eng) — apples-to-apples vs runner
        live = _production_live_gate(pair, eng_sent=c.eng_sent, rsi=c.rsi)
        c.notes.append(
            f"prod_live={'ok' if live.get('allowed') else 'block'}:{','.join(live.get('reasons') or [])[:120]}"
        )
        candidates.append(c)
        # stash live gate on dict after to_dict via side channel
        c.buy_sim_reasons  # keep attr touch for linters
        setattr(c, "_prod_live_gate", live)

    selected = select_top_k(candidates, k=cfg.top_k)

    # buy sim only for selected top-k (cheap; still no orders)
    for c in candidates:
        if not c.selected_top_k:
            c.would_buy_if_pass = False
            continue
        # Fresh miss OR last known raw clearly under floor → do not pretend buy path
        if c.would_pass_floor_est is False or c.last_x_clears_floor is False:
            c.would_buy_if_pass = False
            why = []
            if c.would_pass_floor_est is False:
                why.append("fresh_x_below_floor")
            if c.last_x_clears_floor is False:
                why.append("last_x_below_floor")
            c.buy_sim_reasons = why
            c.notes.append("x_hint_would_not_clear")
            continue
        # Assume X clears (est True or unknown with no bearish last_x)
        allowed, reasons = _simulate_buy_if_x_clears(
            c.pair, rsi=c.rsi, floor=cfg.tryout_floor
        )
        c.would_buy_if_pass = allowed
        c.buy_sim_reasons = reasons
        if allowed is True:
            c.notes.append("gates_clear_if_x_passes")
        elif allowed is False:
            c.notes.append("other_gates_block_even_if_x_passes")

    def _cand_dict(c: PairCandidate) -> Dict[str, Any]:
        d = c.to_dict()
        live = getattr(c, "_prod_live_gate", None)
        if isinstance(live, dict):
            d["production_live_gate"] = live
        return d

    selected_dicts = [_cand_dict(c) for c in candidates if c.selected_top_k]
    trigger_n = sum(
        1
        for c in candidates
        if c.trigger_rsi_wash and c.trigger_eng_stale and c.tryout_eligible and not c.buy_blocked
    )
    would_buy_n = sum(1 for c in candidates if c.would_buy_if_pass is True)
    prod_ok_n = sum(
        1
        for c in candidates
        if isinstance(getattr(c, "_prod_live_gate", None), dict)
        and getattr(c, "_prod_live_gate").get("allowed") is True
    )

    plain = _plain_english(
        universe=universe,
        trigger_n=trigger_n,
        selected=selected_dicts,
        would_buy_n=would_buy_n,
        cfg=cfg,
    )
    if univ_meta.get("parity_ok") is False:
        plain += (
            f" | universe parity DRIFT readiness≠scoreboard "
            f"only_tr={univ_meta.get('only_in_readiness')} "
            f"only_sb={univ_meta.get('only_in_scoreboard')}"
        )
    plain += f" | prod_entry_ok_now={prod_ok_n}/{len(candidates)}"

    board = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "edge_class": "ATTENTION_ONLY_sensor_clock",
        "live_gate": "OFF",
        "place_orders": False,
        "spend_x": bool(cfg.spend_x),
        "cfg": {
            "rsi_wash_min": cfg.rsi_wash_min,
            "rsi_wash_max": cfg.rsi_wash_max,
            "top_k": cfg.top_k,
            "tryout_floor": cfg.tryout_floor,
            "x_fresh_max_min": cfg.x_fresh_max_min,
            "eng_aged_out_max": cfg.eng_aged_out_max,
        },
        "universe": universe,
        "universe_meta": univ_meta,
        "n_universe": len(universe),
        "n_trigger_pool": trigger_n,
        "n_selected_top_k": len(selected_dicts),
        "n_would_buy_if_x_pass": would_buy_n,
        "n_production_entry_ok": prod_ok_n,
        "selected": selected_dicts,
        "candidates": [
            _cand_dict(c)
            for c in sorted(candidates, key=lambda x: (-x.rank_score, x.pair))
        ],
        "plain_english": plain,
        "honesty": [
            "Shadow only — no orders, no config mutation, no paid X by default.",
            "would_pass_floor_est uses cached X only; stale cache → unknown.",
            "would_buy_if_pass assumes eng=tryout_floor after a successful X clear.",
            "Universe = production tryout-eligible SSOT (readiness ∩ scoreboard when both present).",
            "production_live_gate = evaluate_buy_entry with actual eng (same-day/seats/sent).",
            "Top-K cap avoids multi-pair X spend if many RSI-wash together.",
            "Does not claim edge; measures clock-gap opportunities only.",
        ],
    }
    return board


def _plain_english(
    *,
    universe: Sequence[str],
    trigger_n: int,
    selected: Sequence[Mapping[str, Any]],
    would_buy_n: int,
    cfg: ShadowConfig,
) -> str:
    if not universe:
        return "No tryout-eligible universe — shadow idle."
    if trigger_n == 0:
        return (
            f"Universe {len(universe)} tryout doors; none in RSI≤{cfg.rsi_wash_max:.0f} "
            f"+ stale eng gap. Clock path still owns the next window."
        )
    bits = []
    for s in selected:
        pair = s.get("pair")
        rsi = s.get("rsi")
        x = s.get("x_raw")
        wp = s.get("would_pass_floor_est")
        wb = s.get("would_buy_if_pass")
        bits.append(
            f"{pair} RSI={rsi if rsi is not None else 'n/a'} "
            f"x_raw={x if x is not None else 'n/a'} "
            f"pass_est={wp} last_x_ok={s.get('last_x_clears_floor')} buy_if_pass={wb}"
        )
    head = f"{trigger_n} event-gap door(s); top {cfg.top_k} → " + ("; ".join(bits) if bits else "none selected")
    tail = f" Would-buy-if-X-clears: {would_buy_n}. Live gate OFF."
    return head + tail


def write_artifacts(board: Mapping[str, Any]) -> Dict[str, str]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(board, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    event = {
        "ts": board.get("as_of"),
        "n_trigger_pool": board.get("n_trigger_pool"),
        "n_selected": board.get("n_selected_top_k"),
        "n_would_buy": board.get("n_would_buy_if_x_pass"),
        "selected": [s.get("pair") for s in (board.get("selected") or [])],
        "live_gate": "OFF",
    }
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, default=str) + "\n")
    md = _render_md(board)
    MD_REPORT.write_text(md, encoding="utf-8")
    return {
        "latest": str(LATEST),
        "events": str(EVENTS),
        "report": str(MD_REPORT),
    }


def _render_md(board: Mapping[str, Any]) -> str:
    um = board.get("universe_meta") or {}
    lines = [
        f"# RSI-event X tryout shadow",
        f"",
        f"- as_of: `{board.get('as_of')}`",
        f"- edge_class: `{board.get('edge_class')}`",
        f"- live_gate: **{board.get('live_gate')}** · spend_x={board.get('spend_x')}",
        f"- universe: {board.get('n_universe')} tryout doors · source=`{um.get('source')}` · parity_ok={um.get('parity_ok')}",
        f"- trigger pool (RSI wash + stale eng): **{board.get('n_trigger_pool')}**",
        f"- selected top-K: **{board.get('n_selected_top_k')}**",
        f"- would-buy if X clears floor: **{board.get('n_would_buy_if_x_pass')}**",
        f"- production entry_ok now (actual eng): **{board.get('n_production_entry_ok')}**",
        f"",
        f"## Plain English",
        f"",
        str(board.get("plain_english") or ""),
        f"",
        f"## Universe (production mirror)",
        f"",
        f"- doors: `{', '.join(board.get('universe') or []) or 'none'}`",
        f"- readiness: `{', '.join(um.get('tryout_readiness_eligible') or []) or '—'}`",
        f"- scoreboard: `{', '.join(um.get('scoreboard_eligible') or []) or '—'}`",
        f"- only_readiness: `{um.get('only_in_readiness') or []}`",
        f"- only_scoreboard: `{um.get('only_in_scoreboard') or []}`",
        f"",
        f"## Selected",
        f"",
    ]
    sel = board.get("selected") or []
    if not sel:
        lines.append("_none_")
    else:
        lines.append("| pair | RSI | eng | x_raw | pass_est | buy_if_pass | prod_live | reasons |")
        lines.append("|---|---:|---:|---:|---|---|---|---|")
        for s in sel:
            reasons = ",".join((s.get("buy_sim_reasons") or [])[:3]) or "—"
            pl = s.get("production_live_gate") or {}
            pl_s = f"{pl.get('allowed')}"
            pr = pl.get("reasons") or []
            if pr:
                pl_s += f" ({','.join(list(pr)[:2])})"
            lines.append(
                f"| {s.get('pair')} | {s.get('rsi')} | {s.get('eng_sent')} | "
                f"{s.get('x_raw')} | {s.get('would_pass_floor_est')} | "
                f"{s.get('would_buy_if_pass')} | {pl_s} | `{reasons}` |"
            )
    lines.extend(
        [
            f"",
            f"## Honesty",
            f"",
        ]
    )
    for h in board.get("honesty") or []:
        lines.append(f"- {h}")
    lines.append("")
    return "\n".join(lines) + "\n"


def run_shadow(cfg: Optional[ShadowConfig] = None) -> Dict[str, Any]:
    board = build_shadow_board(cfg)
    paths = write_artifacts(board)
    board = dict(board)
    board["artifacts"] = paths
    return board


def telegram_summary(board: Mapping[str, Any]) -> str:
    """Short body; empty if nothing selected (quiet-ok cron)."""
    n = int(board.get("n_selected_top_k") or 0)
    if n <= 0:
        return ""
    sel = board.get("selected") or []
    parts = []
    for s in sel:
        parts.append(
            f"{s.get('pair')} RSI={s.get('rsi')} "
            f"pass={s.get('would_pass_floor_est')} buy={s.get('would_buy_if_pass')}"
        )
    return (
        f"RSI-event X shadow top{n}: "
        + "; ".join(parts)
        + " · live_gate=OFF · no orders"
    )
