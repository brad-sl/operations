#!/usr/bin/env python3
"""Tryout decision discipline — Jev-process map for Phase 6 (Brad 2026-09-26).

Architecture (stolen cleanly from the HFT/Jev writeup, not the model):

  MARKET/FUNNEL STATE (deterministic code)
           ↓
  ATOMIC JUDGMENTS (independent scores from *our* sensors)
           ↓
  POLICY ENGINE (thresholds in config, not prose)
           ↓
  HARD RISK VETO (absolute; never model-owned)
           ↓
  ACTION + CALIBRATION TRIPLE

Jev-the-product is optional/future. This module is the **process discipline**
that raises P(profitable) by abstaining on bad setups and logging triples.

Default: live_apply=false → shadow only (log would_*). Money path unchanged
until Brad flips config + calibration N is honest.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger("phase6.core.tryout_decision_discipline")

SCHEMA = "tryout_decision_discipline_v1"
CONFIG_PATH = PROJECT_ROOT / "config" / "tryout_decision_discipline.json"
LATEST_PATH = STATE_DIR / "tryout_decision_discipline_latest.json"
TRIPLES_PATH = STATE_DIR / "tryout_decision_triples.jsonl"
PROFILES_PATH = STATE_DIR / "pair_funnel_profiles.json"

# Actions the policy may emit
ACT_STAND_DOWN = "STAND_DOWN"
ACT_OBSERVE = "OBSERVE"
ACT_SKIP_PAIR = "SKIP_PAIR"
ACT_BUY_REDUCED = "BUY_REDUCED"
ACT_BUY_FULL = "BUY_FULL"

_MONEY_ACTIONS = frozenset({ACT_BUY_FULL, ACT_BUY_REDUCED})


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("load %s failed: %s", path, exc)
    return default


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    raw = _load_json(path or CONFIG_PATH, None)
    if not isinstance(raw, dict):
        return {
            "schema": SCHEMA,
            "live_apply": False,
            "shadow_log": True,
            "thresholds": {
                "min_setup_score": 1.5,
                "min_setup_confidence": 0.55,
                "min_sent_clear_noul": 0.30,
                "max_toxic_source_noul": 0.50,
                "min_latch_fresh_noul": 0.40,
                "behavior_skip_labels": ["fast_tryout_exit", "sl_heavy"],
                "behavior_min_closed_rts": 5,
                "behavior_skip_confidence": 0.60,
                "reduced_shell_setup_score": 1.0,
                "reduced_shell_fraction": 0.5,
            },
            "fallback_ladder": {"rungs": []},
            "calibration": {"enabled": True},
        }
    return raw


def _thr(cfg: Dict[str, Any]) -> Dict[str, Any]:
    t = cfg.get("thresholds")
    return t if isinstance(t, dict) else {}


# --- judgment primitives (Noul / Choice / Score shaped, local math) ----------


@dataclass
class Judgment:
    id: str
    kind: str  # noul | choice | score
    value: Any
    confidence: float
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "value": self.value,
            "confidence": round(float(self.confidence), 4),
            "reason": self.reason,
        }


def _noul(jid: str, value: float, conf: float, reason: str = "") -> Judgment:
    return Judgment(id=jid, kind="noul", value=round(_clamp01(value), 4), confidence=_clamp01(conf), reason=reason)


def _choice(jid: str, pick: str, conf: float, reason: str = "") -> Judgment:
    return Judgment(id=jid, kind="choice", value=str(pick), confidence=_clamp01(conf), reason=reason)


def _score(jid: str, value: float, conf: float, reason: str = "") -> Judgment:
    return Judgment(id=jid, kind="score", value=round(float(value), 4), confidence=_clamp01(conf), reason=reason)


def _is_toxic_source(src: str) -> bool:
    s = str(src or "").lower()
    return any(tok in s for tok in ("free", "tee", "adanos", "rss", "shadow_only", "unaged"))


def _behavior_row(pair: str) -> Dict[str, Any]:
    raw = _load_json(PROFILES_PATH, {})
    pairs = raw.get("pairs") if isinstance(raw, dict) else None
    if not isinstance(pairs, dict):
        return {}
    row = pairs.get(str(pair).upper()) or pairs.get(pair)
    return row if isinstance(row, dict) else {}


def build_state_snapshot(
    *,
    pair: str,
    rsi: Any = None,
    rsi_max: float = 55.0,
    eng: Any = None,
    floor: float = 0.30,
    eng_source: str = "",
    strategy_mode: Any = None,
    allow_new_buys: Any = None,
    regime: Any = None,
    latch_age_min: Any = None,
    latch_ttl_min: Any = 180.0,
    seats_used_today: Any = None,
    seats_max_day: Any = None,
    open_tryout_seats: Any = None,
    max_open_tryout: Any = None,
    shell_usd: Any = None,
    kill: bool = False,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Deterministic funnel state — arithmetic stays here, not in a model."""
    pair_n = str(pair or "").strip().upper().replace("_", "-")
    beh = _behavior_row(pair_n)
    snap: Dict[str, Any] = {
        "pair": pair_n,
        "rsi": None if rsi is None else _f(rsi),
        "rsi_max": _f(rsi_max, 55.0),
        "eng": None if eng is None else _f(eng),
        "floor": _f(floor, 0.30),
        "eng_source": str(eng_source or ""),
        "strategy_mode": strategy_mode,
        "allow_new_buys": allow_new_buys,
        "regime": regime,
        "latch_age_min": None if latch_age_min is None else _f(latch_age_min),
        "latch_ttl_min": _f(latch_ttl_min, 180.0),
        "seats_used_today": None if seats_used_today is None else int(seats_used_today),
        "seats_max_day": None if seats_max_day is None else int(seats_max_day),
        "open_tryout_seats": None if open_tryout_seats is None else int(open_tryout_seats),
        "max_open_tryout": None if max_open_tryout is None else int(max_open_tryout),
        "shell_usd": None if shell_usd is None else _f(shell_usd),
        "kill": bool(kill),
        "pattern_hint": beh.get("pattern_hint"),
        "closed_rts": int(beh.get("n_closed_rts") or beh.get("closed_rts") or 0),
        "as_of": _utc_iso(),
    }
    if extra:
        for k, v in extra.items():
            if k not in snap and v is not None:
                snap[k] = v
    return snap


def evaluate_judgments(snap: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None) -> List[Judgment]:
    """Atomic battery — parallel-in-spirit, independent, no prose."""
    cfg = cfg or load_config()
    thr = _thr(cfg)
    floor = _f(snap.get("floor"), 0.30)
    rsi_max = _f(snap.get("rsi_max"), 55.0)
    rsi = snap.get("rsi")
    eng = snap.get("eng")
    src = str(snap.get("eng_source") or "")
    mode = str(snap.get("strategy_mode") or "").lower()
    allow = snap.get("allow_new_buys")

    out: List[Judgment] = []

    # regime_door — choice
    if snap.get("kill"):
        out.append(_choice("regime_door", "blocked", 0.99, "kill_switch"))
    elif allow is False or mode in ("usdc_park", "park", "cash", "blocked"):
        out.append(_choice("regime_door", "blocked", 0.95, f"mode={mode} allow={allow}"))
    elif mode in ("deploy", "transition", "recovery", "tryout"):
        out.append(_choice("regime_door", "open", 0.85, f"mode={mode}"))
    else:
        out.append(_choice("regime_door", "uncertain", 0.45, f"mode={mode or 'unknown'}"))

    # rsi_wash_depth — deeper wash = higher noul (better tryout timing)
    if rsi is None:
        out.append(_noul("rsi_wash_depth", 0.0, 0.2, "rsi_missing"))
    else:
        rf = _f(rsi)
        if rf > rsi_max:
            depth = 0.0
            conf = 0.9
            reason = f"rsi={rf:.1f}>max={rsi_max:g}"
        else:
            # map [0, rsi_max] → [1, 0.35]; floor at very deep wash
            depth = _clamp01(0.35 + 0.65 * (rsi_max - rf) / max(rsi_max, 1.0))
            conf = 0.8 if rf <= rsi_max else 0.5
            reason = f"rsi={rf:.1f} max={rsi_max:g}"
        out.append(_noul("rsi_wash_depth", depth, conf, reason))

    # sent_clear — eng vs floor
    if eng is None:
        out.append(_noul("sent_clear", 0.0, 0.2, "eng_missing"))
    else:
        ef = _f(eng)
        if ef >= floor:
            # how far above floor (cap ~2x floor as full)
            margin = (ef - floor) / max(floor, 1e-6)
            n = _clamp01(0.55 + 0.45 * min(margin, 1.0))
            out.append(_noul("sent_clear", n, 0.85, f"eng={ef:.3f} floor={floor:.2f}"))
        else:
            out.append(_noul("sent_clear", _clamp01(ef / max(floor, 1e-6) * 0.5), 0.85, f"eng={ef:.3f}<floor"))

    # eng_source_grade — toxic if free/tee
    if _is_toxic_source(src):
        out.append(_noul("eng_source_grade", 0.05, 0.95, f"toxic_src={src}"))
    elif not src:
        out.append(_noul("eng_source_grade", 0.4, 0.4, "src_unknown"))
    elif any(tok in src.lower() for tok in ("paid", "latch", "composer", "x_probe", "gate")):
        out.append(_noul("eng_source_grade", 0.9, 0.85, f"gate_src={src}"))
    else:
        out.append(_noul("eng_source_grade", 0.55, 0.5, f"src={src}"))

    # latch_fresh
    age = snap.get("latch_age_min")
    ttl = _f(snap.get("latch_ttl_min"), 180.0)
    if age is None:
        # unknown age: mild penalty, not hard fail (composer may have just held)
        out.append(_noul("latch_fresh", 0.55, 0.35, "latch_age_unknown"))
    else:
        af = _f(age)
        if ttl <= 0:
            fresh = 0.5
        else:
            fresh = _clamp01(1.0 - (af / ttl))
        out.append(_noul("latch_fresh", fresh, 0.75, f"age_min={af:.1f} ttl={ttl:g}"))

    # seat_headroom
    used = snap.get("seats_used_today")
    max_d = snap.get("seats_max_day")
    open_n = snap.get("open_tryout_seats")
    max_o = snap.get("max_open_tryout")
    head = 1.0
    conf_h = 0.4
    reasons = []
    if used is not None and max_d is not None and int(max_d) > 0:
        rem = max(0, int(max_d) - int(used))
        head = min(head, rem / float(max_d))
        conf_h = 0.8
        reasons.append(f"day {used}/{max_d}")
    if open_n is not None and max_o is not None and int(max_o) > 0:
        rem_o = max(0, int(max_o) - int(open_n))
        head = min(head, rem_o / float(max_o))
        conf_h = max(conf_h, 0.8)
        reasons.append(f"open {open_n}/{max_o}")
    if not reasons:
        reasons.append("seat_caps_unknown")
    out.append(_noul("seat_headroom", head, conf_h, ";".join(reasons)))

    # behavior_prior — only when closed RTs meet min N
    need_n = int(thr.get("behavior_min_closed_rts") or 5)
    closed = int(snap.get("closed_rts") or 0)
    hint = str(snap.get("pattern_hint") or "")
    skip_labels = [str(x) for x in (thr.get("behavior_skip_labels") or [])]
    if closed < need_n or not hint or hint in ("None", "no_strong_pattern"):
        out.append(_choice("behavior_prior", "insufficient_n", 0.3, f"closed_rts={closed}<{need_n}"))
    else:
        hit = [lab for lab in skip_labels if lab and lab in hint]
        if hit:
            out.append(_choice("behavior_prior", "skip_risk", 0.75, f"hint={hint}"))
        elif "ladder" in hint or "survivor" in hint:
            out.append(_choice("behavior_prior", "favor", 0.65, f"hint={hint}"))
        else:
            out.append(_choice("behavior_prior", "neutral", 0.5, f"hint={hint}"))

    # setup_quality — composite score 0–3 (Jev Score shape)
    # weights: sent, source, rsi depth, seat, regime
    jmap = {j.id: j for j in out}

    def _jv(jid: str, default: float = 0.0) -> float:
        jj = jmap.get(jid)
        if jj is None:
            return float(default)
        return _f(jj.value, default)

    sent_v = _jv("sent_clear", 0.0)
    src_v = _jv("eng_source_grade", 0.0)
    rsi_v = _jv("rsi_wash_depth", 0.0)
    seat_v = _jv("seat_headroom", 0.5)
    reg = jmap.get("regime_door")
    if reg is None:
        reg_ok = 0.0
    elif reg.value == "open":
        reg_ok = 1.0
    elif reg.value == "uncertain":
        reg_ok = 0.3
    else:
        reg_ok = 0.0
    # 0–3 score
    setup = 3.0 * (
        0.30 * sent_v + 0.25 * src_v + 0.20 * rsi_v + 0.15 * reg_ok + 0.10 * seat_v
    )
    confs = [j.confidence for j in out if j.id != "setup_quality"]
    setup_conf = sum(confs) / len(confs) if confs else 0.4
    # penalize if behavior skip
    beh_j = jmap.get("behavior_prior")
    if beh_j and beh_j.value == "skip_risk":
        setup *= 0.55
        setup_conf = min(setup_conf, 0.7)
    out.append(_score("setup_quality", setup, setup_conf, "weighted_atomic_mix"))

    return out


def compose_policy(
    snap: Dict[str, Any],
    judgments: Sequence[Judgment],
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Code-owned policy. Thresholds from config. Hard veto first."""
    cfg = cfg or load_config()
    thr = _thr(cfg) if isinstance(cfg, dict) else {}
    jmap = {j.id: j for j in judgments}

    def jval(jid: str, default: Any = None) -> Any:
        j = jmap.get(jid)
        return default if j is None else j.value

    def jconf(jid: str, default: float = 0.0) -> float:
        j = jmap.get(jid)
        return float(default if j is None else j.confidence)

    min_setup = _f(thr.get("min_setup_score"), 1.5)
    min_conf = _f(thr.get("min_setup_confidence"), 0.55)
    min_sent = _f(thr.get("min_sent_clear_noul"), 0.30)
    max_toxic = _f(thr.get("max_toxic_source_noul"), 0.50)
    # eng_source_grade is inverted toxic: low grade = toxic. Treat grade < (1-max_toxic) as toxic.
    min_src_grade = 1.0 - max_toxic
    min_latch = _f(thr.get("min_latch_fresh_noul"), 0.40)
    beh_skip_conf = _f(thr.get("behavior_skip_confidence"), 0.60)
    red_score = _f(thr.get("reduced_shell_setup_score"), 1.0)
    red_frac = _f(thr.get("reduced_shell_fraction"), 0.5)
    red_frac = _clamp01(red_frac) if red_frac > 0 else 0.5

    shell = _f(snap.get("shell_usd"), 25.0)
    rung = "full_shell"
    action = ACT_BUY_FULL
    size_frac = 1.0
    reasons: List[str] = []

    # --- hard ladder (first match) ---
    if snap.get("kill") or jval("regime_door") == "blocked":
        rung, action, size_frac = "kill_or_regime", ACT_STAND_DOWN, 0.0
        reasons.append("hard_block_kill_or_regime")
    elif _f(jval("eng_source_grade"), 1.0) < min_src_grade:
        rung, action, size_frac = "toxic_source", ACT_STAND_DOWN, 0.0
        reasons.append(f"toxic_or_weak_src grade={jval('eng_source_grade')}")
    elif _f(jval("sent_clear"), 0.0) < min_sent:
        rung, action, size_frac = "sent_not_clear", ACT_STAND_DOWN, 0.0
        reasons.append(f"sent_clear={jval('sent_clear')}<{min_sent}")
    elif _f(jval("seat_headroom"), 1.0) <= 0.0:
        rung, action, size_frac = "no_seat_headroom", ACT_STAND_DOWN, 0.0
        reasons.append("seat_headroom=0")
    elif (
        jval("behavior_prior") == "skip_risk"
        and jconf("behavior_prior") >= beh_skip_conf
    ):
        rung, action, size_frac = "behavior_skip", ACT_SKIP_PAIR, 0.0
        reasons.append(f"behavior_prior=skip_risk conf={jconf('behavior_prior'):.2f}")
    elif _f(jval("latch_fresh"), 1.0) < min_latch and jconf("latch_fresh") >= 0.5:
        rung, action, size_frac = "stale_latch", ACT_OBSERVE, 0.0
        reasons.append(f"latch_fresh={jval('latch_fresh')}<{min_latch}")
    else:
        setup = _f(jval("setup_quality"), 0.0)
        sconf = jconf("setup_quality")
        if setup < red_score or sconf < (min_conf * 0.85):
            rung, action, size_frac = "low_confidence", ACT_OBSERVE, 0.0
            reasons.append(f"setup={setup:.2f} conf={sconf:.2f} → observe")
        elif setup < min_setup or sconf < min_conf:
            rung, action, size_frac = "reduced_shell", ACT_BUY_REDUCED, red_frac
            reasons.append(f"setup={setup:.2f} conf={sconf:.2f} → reduced×{red_frac:g}")
        else:
            rung, action, size_frac = "full_shell", ACT_BUY_FULL, 1.0
            reasons.append(f"setup={setup:.2f} conf={sconf:.2f} → full")

    live_apply = bool(cfg.get("live_apply"))
    money_ok = action in _MONEY_ACTIONS
    # Shadow: never blocks money unless live_apply
    apply_block = bool(live_apply and not money_ok)
    apply_reduce = bool(live_apply and action == ACT_BUY_REDUCED)

    return {
        "rung": rung,
        "action": action,
        "size_frac": size_frac,
        "shell_usd_suggested": round(shell * size_frac, 2) if money_ok else 0.0,
        "reasons": reasons,
        "live_apply": live_apply,
        "apply_block": apply_block,
        "apply_reduce": apply_reduce,
        "would_block_if_live": (not money_ok),
        "would_reduce_if_live": action == ACT_BUY_REDUCED,
        "setup_quality": jval("setup_quality"),
        "setup_confidence": jconf("setup_quality"),
    }


def log_triple(
    *,
    snap: Dict[str, Any],
    judgments: Sequence[Judgment],
    policy: Dict[str, Any],
    decision_id: str = "",
    seat_status: str = "",
    extra: Optional[Dict[str, Any]] = None,
    write_latest: bool = True,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calibration triple: state + judgments + decision (+ optional seat status)."""
    cfg = cfg or load_config()
    cal_raw = cfg.get("calibration") if isinstance(cfg, dict) else None
    cal = cal_raw if isinstance(cal_raw, dict) else {}
    if cal.get("enabled") is False:
        return {"logged": False, "reason": "calibration_disabled"}

    triple = {
        "schema": "tryout_decision_triple_v1",
        "ts": _utc_iso(),
        "decision_id": decision_id or f"tdd-{_utc_iso()}",
        "pair": snap.get("pair"),
        "state": snap,
        "judgments": [j.as_dict() if isinstance(j, Judgment) else j for j in judgments],
        "policy": policy,
        "seat_status": seat_status or None,
        "outcome": None,  # filled later on exit
        "outcome_pending": True,
    }
    if extra:
        triple["extra"] = extra

    triples_path = PROJECT_ROOT / str(cal.get("path") or "data/state/tryout_decision_triples.jsonl")
    if not triples_path.is_absolute():
        triples_path = PROJECT_ROOT / triples_path
    try:
        _append_jsonl(triples_path, triple)
    except OSError as exc:
        logger.warning("triple log failed: %s", exc)
        return {"logged": False, "error": str(exc)}

    latest = {
        "schema": SCHEMA,
        "as_of": _utc_iso(),
        "live_apply": bool(cfg.get("live_apply")),
        "last_triple": {
            "decision_id": triple["decision_id"],
            "pair": triple["pair"],
            "action": policy.get("action"),
            "rung": policy.get("rung"),
            "setup_quality": policy.get("setup_quality"),
            "would_block_if_live": policy.get("would_block_if_live"),
            "reasons": policy.get("reasons"),
        },
        "plain_english": (
            f"discipline {triple['pair']} action={policy.get('action')} "
            f"rung={policy.get('rung')} setup={policy.get('setup_quality')} "
            f"live_apply={bool(cfg.get('live_apply'))} "
            f"would_block={policy.get('would_block_if_live')}"
        ),
        "config_path": str(CONFIG_PATH),
        "triples_path": str(triples_path),
    }
    if write_latest:
        try:
            _write_json(LATEST_PATH, latest)
        except OSError as exc:
            logger.warning("discipline latest write failed: %s", exc)
    return {"logged": True, "triple": triple, "latest": latest}


def attach_outcome(
    *,
    pair: str,
    outcome_class: str,
    exit_reason: str = "",
    decision_id: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Best-effort: mark most recent open triple for pair with exit outcome.

    Does not rewrite whole file (append outcome event). Full join is offline.
    """
    event = {
        "schema": "tryout_decision_outcome_v1",
        "ts": _utc_iso(),
        "pair": str(pair or "").upper(),
        "decision_id": decision_id,
        "outcome_class": outcome_class,
        "exit_reason": exit_reason,
        "meta": meta or {},
    }
    path = STATE_DIR / "tryout_decision_outcomes.jsonl"
    try:
        _append_jsonl(path, event)
        return {"ok": True, "event": event}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def evaluate_candidate(
    *,
    pair: str,
    rsi: Any = None,
    eng: Any = None,
    eng_source: str = "",
    floor: float = 0.30,
    rsi_max: float = 55.0,
    shell_usd: float = 25.0,
    regime: Optional[Dict[str, Any]] = None,
    latch_age_min: Any = None,
    latch_ttl_min: Any = 180.0,
    seats_used_today: Any = None,
    seats_max_day: Any = None,
    open_tryout_seats: Any = None,
    max_open_tryout: Any = None,
    kill: bool = False,
    decision_id: str = "",
    persist: bool = True,
    cfg: Optional[Dict[str, Any]] = None,
    extra_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One-shot: snapshot → judgments → policy → optional triple log."""
    cfg = cfg or load_config()
    reg = regime if isinstance(regime, dict) else {}
    snap = build_state_snapshot(
        pair=pair,
        rsi=rsi,
        rsi_max=rsi_max,
        eng=eng,
        floor=floor,
        eng_source=eng_source,
        strategy_mode=reg.get("strategy_mode"),
        allow_new_buys=reg.get("allow_new_buys"),
        regime=reg.get("regime"),
        latch_age_min=latch_age_min,
        latch_ttl_min=latch_ttl_min,
        seats_used_today=seats_used_today if seats_used_today is not None else reg.get("seats_used_today"),
        seats_max_day=seats_max_day if seats_max_day is not None else reg.get("max_new_seats_per_day"),
        open_tryout_seats=open_tryout_seats,
        max_open_tryout=max_open_tryout if max_open_tryout is not None else reg.get("max_open_tryout_seats"),
        shell_usd=shell_usd if shell_usd else reg.get("abs_cap_usd"),
        kill=kill,
        extra=extra_state,
    )
    judgments = evaluate_judgments(snap, cfg)
    policy = compose_policy(snap, judgments, cfg)
    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _utc_iso(),
        "state": snap,
        "judgments": [j.as_dict() for j in judgments],
        "policy": policy,
        "live_apply": bool(cfg.get("live_apply")),
        "shadow_log": bool(cfg.get("shadow_log", True)),
    }
    if persist and bool(cfg.get("shadow_log", True)):
        log_res = log_triple(
            snap=snap,
            judgments=judgments,
            policy=policy,
            decision_id=decision_id,
            cfg=cfg,
        )
        out["triple_log"] = {"logged": log_res.get("logged"), "decision_id": (log_res.get("triple") or {}).get("decision_id")}
        out["plain_english"] = (log_res.get("latest") or {}).get("plain_english") or (
            f"discipline {pair} {policy.get('action')} setup={policy.get('setup_quality')}"
        )
    else:
        out["plain_english"] = (
            f"discipline {pair} {policy.get('action')} setup={policy.get('setup_quality')} "
            f"(no persist)"
        )
    return out


def apply_to_composer_candidate(
    cand: Optional[Dict[str, Any]],
    *,
    regime: Optional[Dict[str, Any]] = None,
    kill: bool = False,
    shell_usd: float = 25.0,
    floor: float = 0.30,
    rsi_max: float = 55.0,
    persist: bool = True,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Composer hook. Returns discipline block + whether to skip seat dispatch."""
    cfg = cfg or load_config()
    if cand is None:
        return {
            "ran": False,
            "skip_seat": False,
            "reason": "no_candidate",
            "live_apply": bool(cfg.get("live_apply")),
        }
    pair = str(cand.get("pair") or "")
    res = evaluate_candidate(
        pair=pair,
        rsi=cand.get("rsi"),
        eng=cand.get("eng"),
        eng_source=str(cand.get("eng_source") or ""),
        floor=floor,
        rsi_max=rsi_max,
        shell_usd=shell_usd,
        regime=regime,
        kill=kill,
        persist=persist,
        cfg=cfg,
    )
    pol = res.get("policy") or {}
    skip = bool(pol.get("apply_block"))
    reduce = bool(pol.get("apply_reduce"))
    shell_out = shell_usd
    if reduce:
        shell_out = float(pol.get("shell_usd_suggested") or (shell_usd * 0.5))
    return {
        "ran": True,
        "skip_seat": skip,
        "reduce_shell": reduce,
        "shell_usd": shell_out,
        "live_apply": bool(cfg.get("live_apply")),
        "would_block_if_live": bool(pol.get("would_block_if_live")),
        "would_reduce_if_live": bool(pol.get("would_reduce_if_live")),
        "action": pol.get("action"),
        "rung": pol.get("rung"),
        "reasons": pol.get("reasons"),
        "setup_quality": pol.get("setup_quality"),
        "setup_confidence": pol.get("setup_confidence"),
        "result": res,
        "plain_english": res.get("plain_english"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo = evaluate_candidate(
        pair="LINK-USD",
        rsi=42.0,
        eng=0.40,
        eng_source="paid_x_probe",
        floor=0.30,
        rsi_max=55.0,
        shell_usd=25.0,
        regime={
            "strategy_mode": "deploy",
            "allow_new_buys": True,
            "regime": "flat",
            "max_new_seats_per_day": 6,
        },
        persist=True,
    )
    print(demo.get("plain_english"))
    print(json.dumps(demo.get("policy"), indent=2))
