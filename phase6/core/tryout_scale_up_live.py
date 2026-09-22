"""Tryout mid-flight scale-up — LIVE PATH (Brad GO option B, 2026-09-19).

Purpose
-------
Close the functional gap: shadow can say would_scale, but nothing could buy the step.
This module is the **order path** for one mid-flight add.

Standing rules (hard)
---------------------
• Default OFF. Cron shadow cycle NEVER calls apply.
• Armed only when `data/state/tryout_scale_up_brad_decision.json` has live_apply=true
  (explicit Brad GO). Config JSON live_apply is ignored for arming.
• CF bar default ON (n≥cf_min_scored + edge class not NO_CLEAR). Waive only via
  decision.cf_bar.require=false + note (still ATTENTION_ONLY product language).
• Dry-run unless apply(..., go=True) AND dry_run=False.
• One step per lot (open_lots registry). Daily caps. Max step_usd from shadow cfg.
• Buys go through OrderExecutor.execute_buy (limit-first fence / SL attach stack).
• Does NOT mint new tryout seats, does NOT bypass buy_block / post-SL for *new* names
  (this is add-to-open-tryout only).
• Kill file: data/state/tryout_scale_up_live_KILL → refuse all applies.

This is plumbing proof, not edge claim. CF green still ATTENTION_ONLY until GO.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.paths import PROJECT_ROOT
from phase6.core import tryout_scale_up_shadow as shadow

logger = logging.getLogger(__name__)

SCHEMA = "tryout_scale_up_live_v1"
STATE_DIR = PROJECT_ROOT / "data" / "state"
KILL_PATH = STATE_DIR / "tryout_scale_up_live_KILL"
DAILY_PATH = STATE_DIR / "tryout_scale_up_live_daily.json"
LATEST_PLAN_PATH = STATE_DIR / "tryout_scale_up_live_plan_latest.json"
CRUMBS_PATH = STATE_DIR / "tryout_scale_up_live_crumbs.jsonl"
APPROVAL_SEEN_PATH = STATE_DIR / "tryout_scale_up_live_approval_seen.json"
APPROVAL_DEDUPE_HOURS = 12.0

# Safety defaults — tighter than shadow band; never exceed shadow step
LIVE_SAFETY: Dict[str, Any] = {
    "max_steps_per_utc_day": 1,
    "max_usd_per_utc_day": 50.0,
    "max_step_usd": 25.0,
    "min_step_usd": 15.0,
    "require_cf_bar": True,
    "allow_pairs": None,  # None = any would_scale; or list pin
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or _utc_now()
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        logger.debug("load %s: %s", path, e)
    return default


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")


def _append_crumb(row: Dict[str, Any]) -> None:
    CRUMBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CRUMBS_PATH.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def kill_switch_on() -> bool:
    return KILL_PATH.exists()


def load_decision() -> Dict[str, Any]:
    return shadow.ensure_decision_artifact()


def is_live_armed(decision: Optional[Dict[str, Any]] = None) -> bool:
    """True only when Brad decision file explicitly sets live_apply."""
    d: Dict[str, Any] = decision if isinstance(decision, dict) else load_decision()
    if kill_switch_on():
        return False
    return d.get("live_apply") is True


def _waive_usage(decision: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """C-waive budget: max_waived_steps vs waived_steps_used on decision.cf_bar."""
    d: Dict[str, Any] = decision if isinstance(decision, dict) else load_decision()
    raw_bar = d.get("cf_bar")
    bar: Dict[str, Any] = raw_bar if isinstance(raw_bar, dict) else {}
    max_w = int(bar.get("max_waived_steps") or 0)
    used = int(bar.get("waived_steps_used") or 0)
    return {"max": max_w, "used": used, "remaining": max(0, max_w - used)}


def record_waived_step(pair: str, step_usd: float) -> Dict[str, Any]:
    """Bump cf_bar.waived_steps_used after a real (non-dry) waived apply."""
    path = shadow.DECISION_PATH
    raw = _load_json(path, {})
    if not isinstance(raw, dict):
        raw = {}
    bar_raw = raw.get("cf_bar")
    bar: Dict[str, Any] = dict(bar_raw) if isinstance(bar_raw, dict) else {}
    used = int(bar.get("waived_steps_used") or 0) + 1
    bar["waived_steps_used"] = used
    hist_raw = bar.get("waive_events")
    hist: List[Any] = list(hist_raw) if isinstance(hist_raw, list) else []
    hist.append(
        {
            "at": _utc_iso(),
            "pair": shadow._norm_pair(pair),
            "step_usd": float(step_usd),
            "used_after": used,
        }
    )
    bar["waive_events"] = hist[-20:]
    raw["cf_bar"] = bar
    raw["as_of"] = _utc_iso()
    _write_json(path, raw)
    return bar


def cf_bar_cleared(
    cf: Optional[Dict[str, Any]] = None,
    decision: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return {ok, reason, waived}.

    C 2026-09-19: require=false allows a **budgeted** waive (max_waived_steps).
    Exhausted budget → fail until CF n clears or Brad raises budget.
    """
    d: Dict[str, Any] = decision if isinstance(decision, dict) else load_decision()
    c: Dict[str, Any] = cfg if isinstance(cfg, dict) else shadow.load_cfg()
    raw_bar = d.get("cf_bar")
    bar: Dict[str, Any] = raw_bar if isinstance(raw_bar, dict) else {}
    require = bar.get("require")
    if require is None:
        require = LIVE_SAFETY["require_cf_bar"]
    require = bool(require)
    if not require:
        usage = _waive_usage(d)
        if usage["max"] <= 0:
            return {
                "ok": False,
                "waived": False,
                "reason": "cf_bar.require=false but max_waived_steps=0",
            }
        if usage["remaining"] <= 0:
            return {
                "ok": False,
                "waived": False,
                "reason": (
                    f"cf_waive_budget_exhausted used={usage['used']}/{usage['max']}"
                ),
            }
        return {
            "ok": True,
            "waived": True,
            "reason": (
                f"cf_bar.waive remaining={usage['remaining']}/{usage['max']} "
                f"(Brad C GO; not edge)"
            ),
            "waive_usage": usage,
        }
    cf_map: Dict[str, Any] = cf if isinstance(cf, dict) else {}
    n = int(cf_map.get("n") or cf_map.get("n_scored") or 0)
    min_n = int(bar.get("min_scored") or c.get("cf_min_scored") or 8)
    edge = str(cf_map.get("edge_class") or "")
    if n < min_n:
        return {
            "ok": False,
            "waived": False,
            "reason": f"cf_n={n}<min_scored={min_n}",
        }
    if edge.startswith("NO_CLEAR") or edge == "INSUFFICIENT_N":
        return {
            "ok": False,
            "waived": False,
            "reason": f"cf_edge={edge}",
        }
    return {"ok": True, "waived": False, "reason": f"cf_ok n={n} edge={edge}"}


def _utc_day_key(now: Optional[datetime] = None) -> str:
    d = now or _utc_now()
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d")


def load_daily(now: Optional[datetime] = None) -> Dict[str, Any]:
    day = _utc_day_key(now)
    raw = _load_json(DAILY_PATH, {})
    if not isinstance(raw, dict) or raw.get("utc_day") != day:
        return {
            "schema": SCHEMA,
            "utc_day": day,
            "n_steps": 0,
            "usd_spent": 0.0,
            "pairs": [],
            "events": [],
        }
    return raw


def _save_daily(daily: Dict[str, Any]) -> None:
    _write_json(DAILY_PATH, daily)


@dataclass
class LiveScalePlan:
    pair: str
    step_usd: float
    held_usd: float
    total_after_usd: float
    unrealized_r: float
    hold_hours: Optional[float]
    phase: Optional[int]
    structure_ok: Optional[bool]
    status: str  # planned | blocked | skip
    reasons: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _signal_bar_reasons(row: Dict[str, Any], cfg: Dict[str, Any]) -> List[str]:
    """Kindling checks on a candidate row (phase/structure/R/hold/dwell).

    Used so live plan does not trust measure-profile would_scale alone.
    """
    reasons: List[str] = []
    hold_h = row.get("hold_hours")
    min_h = _f(cfg.get("min_hold_hours"), 2.0)
    if hold_h is None:
        reasons.append("hold_hours_unknown")
    elif float(hold_h) < min_h:
        reasons.append(f"hold_hours={float(hold_h):.2f}<{min_h}")

    r = _f(row.get("unrealized_r"))
    rmin = _f(cfg.get("min_unrealized_r"), 0.008)
    rmax = _f(cfg.get("max_unrealized_r"), 0.035)
    if r < rmin:
        reasons.append(f"r={r:.4f}<min {rmin}")
    if r > rmax:
        reasons.append(f"r={r:.4f}>max {rmax} (bank_zone_or_extended)")

    allow = {int(x) for x in (cfg.get("require_phase_in") or [1, 2])}
    phase = row.get("phase")
    if phase is None:
        reasons.append("phase_unknown")
    elif int(phase) not in allow:
        reasons.append(f"phase={phase} not in {sorted(allow)}")

    dwell_n = int(cfg.get("phase_dwell_bars") or 0)
    if dwell_n > 0:
        d_ok = row.get("phase_dwell_ok")
        detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
        if d_ok is None and isinstance(detail, dict):
            ps = detail.get("phase_struct") if isinstance(detail.get("phase_struct"), dict) else {}
            d_ok = ps.get("phase_dwell_ok")
            if d_ok is None and ps.get("phase_history"):
                hist = list(ps.get("phase_history") or [])
                d_ok = bool(hist) and all(int(p) in allow for p in hist)
        # Isolation rows often omit dwell meta: fail closed only when history present
        if d_ok is False:
            reasons.append("phase_dwell_fail")
        elif d_ok is None and row.get("phase_history"):
            hist = list(row.get("phase_history") or [])
            if not (hist and all(int(p) in allow for p in hist)):
                reasons.append("phase_dwell_fail")
        # else: no dwell evidence in row → tip phase already checked; dwell deferred

    if bool(cfg.get("require_structure_ok", True)):
        sk = row.get("structure_ok")
        if sk is None:
            reasons.append("structure_unknown")
        elif not sk:
            reasons.append("structure_not_ok")
    return reasons


def plan_live_steps(
    decisions: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    board: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    decision: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build apply plan under **live_signal** kindling bar. Never places orders.

    Default cfg is live_signal (not measure B-loosen). Measure would_scale is only
    a candidate pool hint; each row must still clear signal-bar gates.
    """
    now = now or _utc_now()
    # Default live plan = live_signal kindling bar. Tests may pass measure/explicit cfg.
    if isinstance(cfg, dict):
        ap = cfg.get("active_profile")
        if ap in ("measure", "live_signal"):
            c = dict(cfg)
        else:
            c = shadow.apply_profile(dict(cfg), "live_signal")
    else:
        c = shadow.load_live_signal_cfg()
    d = decision if isinstance(decision, dict) else load_decision()
    armed = is_live_armed(d)
    b = board
    if b is None and decisions is None:
        # fresh shadow evaluate (measure cycle for CF crumbs)
        b = shadow.run_cycle()
    if decisions is None:
        decisions = list((b or {}).get("decisions") or [])
    cf = (b or {}).get("cf") if isinstance(b, dict) else None
    if cf is None:
        scores = shadow._load_score_history()
        cf = shadow._cf_summary(scores, c)
    cf_gate = cf_bar_cleared(cf, d, c)
    daily = load_daily(now)
    safety = dict(LIVE_SAFETY)
    # decision may override safety caps (never raise above code max without explicit keys)
    raw_ds = d.get("live_safety")
    ds: Dict[str, Any] = raw_ds if isinstance(raw_ds, dict) else {}
    for k in (
        "max_steps_per_utc_day",
        "max_usd_per_utc_day",
        "max_step_usd",
        "min_step_usd",
        "allow_pairs",
    ):
        if k in ds and ds.get(k) is not None:
            safety[k] = ds[k]

    max_step = min(_f(c.get("step_usd"), 25.0), _f(safety.get("max_step_usd"), 25.0))
    min_step = _f(safety.get("min_step_usd"), 15.0)
    max_total = _f(c.get("max_total_after_step_usd"), 100.0)
    allow = safety.get("allow_pairs")
    allow_set = None
    if isinstance(allow, (list, tuple, set)):
        allow_set = {shadow._norm_pair(x) for x in allow}

    plans: List[LiveScalePlan] = []
    planned_usd = 0.0
    planned_n = 0
    signal_blocked_n = 0

    for row in decisions:
        if not isinstance(row, dict):
            continue
        pair = shadow._norm_pair(row.get("pair") or "")
        status = str(row.get("status") or "")
        reasons_shadow = list(row.get("reasons") or [])
        # B paper CF leg already registered → still eligible for C live plan
        paper_leg = (
            status == "skip"
            and any("paper_scaled" in str(x) for x in reasons_shadow)
        ) or (
            status == "skip"
            and "already_paper_scaled_cf_leg" in reasons_shadow
        )
        if status != "would_scale" and not paper_leg:
            continue
        reasons: List[str] = []

        # --- Kindling / signal bar (always; cfg may be measure only in tests) ---
        sig_reasons = _signal_bar_reasons(row, c)
        if sig_reasons:
            signal_blocked_n += 1
            reasons.extend(f"signal_bar:{x}" for x in sig_reasons)

        held = _f(row.get("held_usd"))
        # paper leg may have step_usd=0 on skip row — pull from registry/cfg
        step = _f(row.get("step_usd"), 0.0)
        if step < min_step - 1e-9:
            open_reg0 = shadow._load_json(shadow.OPEN_LOTS_PATH, {"lots": {}})
            lots0 = open_reg0.get("lots") if isinstance(open_reg0, dict) else {}
            meta0 = (lots0 or {}).get(pair) if isinstance(lots0, dict) else {}
            if isinstance(meta0, dict):
                step = _f(meta0.get("step_usd"), max_step)
            if step < min_step - 1e-9:
                step = max_step
        step = min(step, max_step)
        if step < min_step - 1e-9:
            reasons.append(f"step={step:.2f}<min_step={min_step}")
        if allow_set is not None and pair not in allow_set:
            reasons.append("pair_not_in_allow_pairs")
        total_after = held + step
        if total_after > max_total + 1e-6:
            reasons.append(f"total_after={total_after:.0f}>max={max_total}")
        # daily headroom
        if daily["n_steps"] + planned_n >= int(safety["max_steps_per_utc_day"]):
            reasons.append("daily_max_steps")
        if daily["usd_spent"] + planned_usd + step > _f(safety["max_usd_per_utc_day"]) + 1e-6:
            reasons.append("daily_max_usd")
        if pair in (daily.get("pairs") or []):
            reasons.append("already_scaled_today")
        # open lot already live-scaled (paper CF leg alone is OK for live C apply)
        open_reg = shadow._load_json(shadow.OPEN_LOTS_PATH, {"lots": {}})
        lots = open_reg.get("lots") if isinstance(open_reg, dict) else {}
        if isinstance(lots, dict) and pair in lots:
            meta = lots[pair] if isinstance(lots[pair], dict) else {}
            if meta.get("live_scaled") or meta.get("status") == "live_open":
                reasons.append("already_live_scaled_this_lot")
            # paper_open / paper_scaled: allow live plan (C seed) — do not block
        if not armed:
            reasons.append("live_apply_not_armed")
        if not cf_gate["ok"]:
            reasons.append(f"cf_bar:{cf_gate['reason']}")
        if kill_switch_on():
            reasons.append("kill_switch")

        st = "blocked" if reasons else "planned"
        if st == "planned":
            planned_n += 1
            planned_usd += step
        plans.append(
            LiveScalePlan(
                pair=pair,
                step_usd=round(step, 2),
                held_usd=held,
                total_after_usd=round(total_after, 2),
                unrealized_r=_f(row.get("unrealized_r")),
                hold_hours=row.get("hold_hours"),
                phase=row.get("phase") if isinstance(row.get("phase"), int) else None,
                structure_ok=row.get("structure_ok")
                if isinstance(row.get("structure_ok"), bool)
                else None,
                status=st,
                reasons=reasons
                or ["ready_for_apply_when_go", "live_signal_bar"],
                detail={
                    "shadow_reasons": row.get("reasons"),
                    "signal_bar_profile": c.get("active_profile"),
                    "signal_bar_reasons": sig_reasons,
                    "phase_dwell_ok": row.get("phase_dwell_ok"),
                    "phase_struct": (
                        (row.get("detail") or {}).get("phase_struct")
                        if isinstance(row.get("detail"), dict)
                        else None
                    ),
                    "cf_gate": cf_gate,
                    "armed": armed,
                },
            )
        )

    payload = {
        "schema": SCHEMA,
        "as_of": _utc_iso(now),
        "live_armed": armed,
        "kill": kill_switch_on(),
        "signal_bar_profile": c.get("active_profile"),
        "signal_bar_gates": {
            k: c.get(k)
            for k in (
                "min_hold_hours",
                "min_unrealized_r",
                "max_unrealized_r",
                "require_phase_in",
                "require_structure_ok",
                "phase_dwell_bars",
            )
        },
        "cf_gate": cf_gate,
        "cf": cf,
        "daily": {
            "utc_day": daily.get("utc_day"),
            "n_steps": daily.get("n_steps"),
            "usd_spent": daily.get("usd_spent"),
            "pairs": daily.get("pairs"),
        },
        "safety": safety,
        "n_would_scale": sum(
            1
            for r in decisions
            if isinstance(r, dict)
            and (
                r.get("status") == "would_scale"
                or "already_paper_scaled_cf_leg" in list(r.get("reasons") or [])
            )
        ),
        "n_signal_blocked": signal_blocked_n,
        "n_planned": sum(1 for p in plans if p.status == "planned"),
        "n_blocked": sum(1 for p in plans if p.status == "blocked"),
        "plans": [p.to_dict() for p in plans],
        "note": (
            "Plan only under signal bar (default live_signal). "
            "apply_live_steps(..., go=True, dry_run=False) required for money. "
            "Cron must never call apply. Measure would_scale ≠ automatic planned."
        ),
    }
    _write_json(LATEST_PLAN_PATH, payload)
    return payload


def _build_executor(shadow_mode: bool = True):
    """Construct OrderExecutor; default shadow so isolation never hits venue."""
    from phase6.core.order_executor import OrderExecutor

    mode = "shadow" if shadow_mode else "live"
    ex = None
    try:
        from phase6.core.exchange_client import CoinbaseExchangeClient

        ex = CoinbaseExchangeClient(mode=mode)
    except Exception as e:
        logger.warning("CoinbaseExchangeClient init failed: %s", e)
        raise
    slm = None
    try:
        from phase6.core.stop_loss_manager import StopLossManager

        cfg = {"risk_management": {"stop_loss_pct": 0.03}}
        try:
            cfg_path = PROJECT_ROOT / "config" / "trading_config_phase6.json"
            if cfg_path.exists():
                loaded = json.loads(cfg_path.read_text())
                if isinstance(loaded, dict):
                    cfg = loaded
        except Exception:
            pass
        slm = StopLossManager(ex, cfg, mode=mode)
    except Exception as e:
        logger.debug("SLM init skip: %s", e)
    return OrderExecutor(ex, slm, mode=mode)


def apply_live_steps(
    plan_payload: Optional[Dict[str, Any]] = None,
    *,
    dry_run: bool = True,
    go: bool = False,
    executor: Any = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Execute planned steps.

    Money moves only when: go=True AND dry_run=False AND live_armed AND not kill
    AND each row status=planned. Default is dry_run report.
    """
    now = now or _utc_now()
    decision = load_decision()
    armed = is_live_armed(decision)
    payload = plan_payload or plan_live_steps(decision=decision, now=now)
    results: List[Dict[str, Any]] = []
    daily = load_daily(now)

    money = bool(go) and (not dry_run) and armed and (not kill_switch_on())
    if go and dry_run:
        mode = "dry_run_go"  # operator preview with GO intent, still no money
    elif money:
        mode = "live"
    else:
        mode = "dry_run"

    for row in payload.get("plans") or []:
        if not isinstance(row, dict):
            continue
        pair = shadow._norm_pair(row.get("pair") or "")
        step = _f(row.get("step_usd"))
        st = str(row.get("status") or "")
        out: Dict[str, Any] = {
            "pair": pair,
            "step_usd": step,
            "plan_status": st,
            "mode": mode,
            "applied": False,
            "order_id": None,
            "error": None,
        }
        if st != "planned":
            out["error"] = f"not_planned:{st}"
            results.append(out)
            continue
        if not money:
            out["applied"] = False
            out["error"] = None
            out["would_apply"] = True
            out["note"] = (
                "dry_run — would call OrderExecutor.execute_buy "
                f"{pair} ${step:.2f} reason=tryout_scale_up_mid_flight"
            )
            results.append(out)
            _append_crumb({"kind": "dry_would_apply", "ts": _utc_iso(now), **out})
            continue

        # LIVE money path
        try:
            ex = executor if executor is not None else _build_executor(shadow_mode=False)
            # refuse if executor is still shadow
            if getattr(ex, "shadow_mode", False):
                out["error"] = "executor_shadow_mode_refused_for_live"
                results.append(out)
                continue
            buy = ex.execute_buy(pair, step)
            ok = bool(buy.get("success")) if isinstance(buy, dict) else False
            out["order_id"] = (buy or {}).get("order_id") if isinstance(buy, dict) else None
            out["buy_result"] = {
                k: (buy or {}).get(k)
                for k in (
                    "success",
                    "order_id",
                    "entry_price",
                    "size",
                    "sl_attached",
                    "execution_style",
                    "fill_status",
                )
            } if isinstance(buy, dict) else {}
            out["applied"] = ok
            if not ok:
                out["error"] = str((buy or {}).get("error") or "execute_buy_failed")
            else:
                # mark lot scaled for CF scoring
                dec = shadow.ScaleDecision(
                    pair=pair,
                    status="would_scale",
                    held_usd=_f(row.get("held_usd")),
                    unrealized_r=_f(row.get("unrealized_r")),
                    hold_hours=row.get("hold_hours"),
                    phase=row.get("phase"),
                    structure_ok=row.get("structure_ok"),
                    step_usd=step,
                    reasons=["live_mid_flight_step"],
                    detail={
                        "lot": {},
                        "entry_price": (buy or {}).get("entry_price"),
                        "mark": (buy or {}).get("entry_price"),
                        "live": True,
                    },
                )
                shadow._mark_open_lot_scaled(pair, dec, now)
                # stamp live status on registry
                reg = shadow._load_json(shadow.OPEN_LOTS_PATH, {"lots": {}})
                lots = reg.get("lots") if isinstance(reg, dict) else {}
                if isinstance(lots, dict) and pair in lots:
                    lots[pair]["status"] = "live_open"
                    lots[pair]["live_scaled"] = True
                    lots[pair]["scaled"] = True
                    lots[pair]["live_order_id"] = out["order_id"]
                    lots[pair]["live_applied_at"] = _utc_iso(now)
                    reg["lots"] = lots
                    shadow._write_json(shadow.OPEN_LOTS_PATH, reg)
                # C: consume waive budget if this plan was under waive
                if (payload.get("cf_gate") or {}).get("waived"):
                    try:
                        out["waive_bar"] = record_waived_step(pair, step)
                    except Exception as e:
                        out["waive_record_error"] = str(e)
                daily["n_steps"] = int(daily.get("n_steps") or 0) + 1
                daily["usd_spent"] = _f(daily.get("usd_spent")) + step
                pairs = list(daily.get("pairs") or [])
                if pair not in pairs:
                    pairs.append(pair)
                daily["pairs"] = pairs
                ev = list(daily.get("events") or [])
                ev.append(
                    {
                        "ts": _utc_iso(now),
                        "pair": pair,
                        "step_usd": step,
                        "order_id": out["order_id"],
                    }
                )
                daily["events"] = ev[-20:]
                _save_daily(daily)
            _append_crumb({"kind": "live_apply", "ts": _utc_iso(now), **out})
        except Exception as e:
            out["error"] = str(e)
            logger.exception("live scale apply failed %s", pair)
            _append_crumb({"kind": "live_apply_error", "ts": _utc_iso(now), **out})
        results.append(out)

    summary = {
        "schema": SCHEMA,
        "as_of": _utc_iso(now),
        "mode": mode,
        "go": go,
        "dry_run": dry_run,
        "live_armed": armed,
        "kill": kill_switch_on(),
        "money_moved": money and any(r.get("applied") for r in results),
        "n_results": len(results),
        "n_applied": sum(1 for r in results if r.get("applied")),
        "results": results,
        "daily": load_daily(now),
        "plan_path": str(LATEST_PLAN_PATH),
        "note": (
            "Money only if go and not dry_run and decision.live_apply and no KILL. "
            "Default dry_run."
        ),
    }
    _write_json(STATE_DIR / "tryout_scale_up_live_apply_latest.json", summary)
    return summary


def _plan_rows(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Plan payload uses key `plans` (not `steps`)."""
    if not isinstance(plan, dict):
        return []
    rows = plan.get("plans")
    if not isinstance(rows, list):
        rows = plan.get("steps")  # legacy alias
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def approval_fingerprint(plan: Dict[str, Any]) -> str:
    """Stable key for planned steps (pair + rounded step) so same plan doesn't re-page."""
    parts: List[str] = []
    for row in _plan_rows(plan):
        if row.get("status") != "planned":
            continue
        pair = shadow._norm_pair(row.get("pair") or "")
        if not pair:
            continue
        step = round(_f(row.get("step_usd")), 2)
        parts.append(f"{pair}:{step:.2f}")
    return "|".join(sorted(parts))


def _load_approval_seen() -> Dict[str, Any]:
    raw = _load_json(APPROVAL_SEEN_PATH, {"fingerprints": {}})
    if not isinstance(raw, dict):
        return {"fingerprints": {}}
    fps = raw.get("fingerprints")
    if not isinstance(fps, dict):
        raw["fingerprints"] = {}
    return raw


def _should_send_approval(
    fingerprint: str,
    *,
    now: Optional[datetime] = None,
    dedupe_hours: float = APPROVAL_DEDUPE_HOURS,
    mark: bool = True,
) -> bool:
    """True once per fingerprint within dedupe window."""
    fp = str(fingerprint or "").strip()
    if not fp:
        return False
    now_dt = now or _utc_now()
    seen = _load_approval_seen()
    fps = seen.get("fingerprints") if isinstance(seen.get("fingerprints"), dict) else {}
    last_raw = str(fps.get(fp) or "")
    last = None
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except Exception:
            last = None
    if last is not None and (now_dt - last).total_seconds() < float(dedupe_hours) * 3600.0:
        return False
    if mark:
        fps[fp] = _utc_iso(now_dt)
        # prune old
        horizon = max(float(dedupe_hours), 24.0) * 3600.0 * 7.0
        keep: Dict[str, str] = {}
        for k, v in fps.items():
            try:
                t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if (now_dt - t).total_seconds() <= horizon:
                    keep[str(k)] = str(v)
            except Exception:
                continue
        seen["fingerprints"] = keep
        seen["updated_at"] = _utc_iso(now_dt)
        _write_json(APPROVAL_SEEN_PATH, seen)
    return True


def _phase_label(phase: Any) -> str:
    try:
        p = int(phase)
    except (TypeError, ValueError):
        return "?"
    return {
        1: "ignition",
        2: "early_trend",
        3: "extension",
        4: "exhaustion",
        5: "distribution",
    }.get(p, str(p))


def _row_decision_factors(row: Dict[str, Any], plan: Dict[str, Any]) -> List[str]:
    """Plain decision factors for one planned scale-up row."""
    factors: List[str] = []
    gates = plan.get("signal_bar_gates") if isinstance(plan.get("signal_bar_gates"), dict) else {}
    detail = row.get("detail") if isinstance(row.get("detail"), dict) else {}
    ps = detail.get("phase_struct") if isinstance(detail.get("phase_struct"), dict) else {}

    phase = row.get("phase")
    factors.append(f"phase {phase} ({_phase_label(phase)})")
    allow = gates.get("require_phase_in") or [1, 2]
    factors.append(f"phase allow {list(allow)}")

    dwell_n = int(gates.get("phase_dwell_bars") or 0)
    d_ok = row.get("phase_dwell_ok")
    if d_ok is None and isinstance(detail, dict):
        d_ok = detail.get("phase_dwell_ok")
    if d_ok is None:
        d_ok = ps.get("phase_dwell_ok")
    if dwell_n > 0:
        if d_ok is True:
            factors.append(f"dwell {dwell_n}d OK")
        elif d_ok is False:
            factors.append(f"dwell {dwell_n}d FAIL")
        else:
            factors.append(f"dwell {dwell_n}d (tip-only / no hist)")
    else:
        factors.append("dwell off (measure)")

    sk = row.get("structure_ok")
    if sk is True:
        factors.append("structure_ok")
    elif sk is False:
        factors.append("structure NOT ok")
    else:
        factors.append("structure unknown")

    r = row.get("unrealized_r")
    rmin = _f(gates.get("min_unrealized_r"), 0.008)
    rmax = _f(gates.get("max_unrealized_r"), 0.035)
    if r is None:
        factors.append("r unknown")
    else:
        factors.append(
            f"r {float(r)*100:.1f}% band [{rmin*100:.1f}%…{rmax*100:.1f}%]"
        )

    hold = row.get("hold_hours")
    min_h = _f(gates.get("min_hold_hours"), 2.0)
    if hold is None:
        factors.append("hold unknown")
    else:
        factors.append(f"hold {float(hold):.1f}h ≥ {min_h:.0f}h")

    profile = plan.get("signal_bar_profile") or detail.get("signal_bar_profile") or "?"
    factors.append(f"bar={profile}")

    held = _f(row.get("held_usd"))
    step = _f(row.get("step_usd"))
    factors.append(f"size held ${held:.0f} + ${step:.0f} → ${held+step:.0f}")
    return factors


def build_scale_up_recommendation(
    plan: Dict[str, Any],
    steps: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Recommendation packet for approval TG (money still OFF until Brad GO).

    Labels:
      GO_KINDLING — live_signal cleared + CF not waived (still needs explicit GO)
      HOLD_PATH_PROOF — planned but CF waived / ATTENTION_ONLY (optional spend only)
      HOLD — missing structure/phase honesty or soft flags
      NO_GO — should not page (caller usually filters these out)
    """
    rows = list(steps) if steps is not None else [
        r for r in _plan_rows(plan) if isinstance(r, dict) and r.get("status") == "planned"
    ]
    cf = plan.get("cf_gate") if isinstance(plan.get("cf_gate"), dict) else {}
    gates = plan.get("signal_bar_gates") if isinstance(plan.get("signal_bar_gates"), dict) else {}
    profile = str(plan.get("signal_bar_profile") or "")

    if not rows:
        return {
            "label": "NO_GO",
            "headline": "NO-GO — nothing planned",
            "why": "No planned scale-up steps under live signal bar.",
            "factors": [],
            "per_pair": {},
        }

    per_pair: Dict[str, List[str]] = {}
    soft_flags: List[str] = []
    hard_flags: List[str] = []

    for row in rows:
        pair = shadow._norm_pair(row.get("pair") or "") or "?"
        facts = _row_decision_factors(row, plan)
        per_pair[pair] = facts

        phase = row.get("phase")
        try:
            phase_i = int(phase) if phase is not None else None
        except (TypeError, ValueError):
            phase_i = None
        allow = {int(x) for x in (gates.get("require_phase_in") or [1, 2])}
        if phase_i is None:
            hard_flags.append(f"{pair}: phase unknown")
        elif phase_i not in allow and profile == "live_signal":
            hard_flags.append(f"{pair}: phase {phase_i} outside kindling allow")
        if phase_i is not None and phase_i >= 4:
            soft_flags.append(f"{pair}: late phase {phase_i} ({_phase_label(phase_i)})")

        sk = row.get("structure_ok")
        if sk is False:
            hard_flags.append(f"{pair}: structure not ok")
        elif sk is None and bool(gates.get("require_structure_ok", True)):
            soft_flags.append(f"{pair}: structure unknown")

        r = row.get("unrealized_r")
        if r is not None:
            rf = float(r)
            if rf < 0:
                soft_flags.append(f"{pair}: mild red r={rf*100:.1f}%")
            if rf > _f(gates.get("max_unrealized_r"), 0.035):
                soft_flags.append(f"{pair}: extended / bank-zone r")

    if cf.get("waived"):
        soft_flags.append("CF waived — ATTENTION_ONLY (no edge claim)")
    elif not cf.get("ok", True):
        hard_flags.append(f"CF bar blocked: {cf.get('reason')}")

    if profile and profile != "live_signal":
        soft_flags.append(f"plan profile={profile} (prefer live_signal for kindling)")

    # Flatten factors for card (first pair primary; multi-pair listed)
    factor_lines: List[str] = []
    for pair, facts in per_pair.items():
        factor_lines.append(f"{pair}: " + " · ".join(facts))
    factor_lines.extend(f"flag: {x}" for x in soft_flags)
    factor_lines.extend(f"block: {x}" for x in hard_flags)

    if hard_flags:
        label = "NO_GO"
        headline = "NO-GO — do not spend"
        why = "; ".join(hard_flags[:3])
    elif cf.get("waived") or soft_flags:
        label = "HOLD_PATH_PROOF"
        headline = "HOLD — path-proof optional only"
        why = (
            "Live signal bar cleared for a plan, but CF is waived and/or soft flags "
            "mean this is not certified 'run continuing' edge. Default = hold the "
            "tryout; GO only if you explicitly want another kindling stick for path N."
        )
        if soft_flags:
            why = why + " Soft: " + "; ".join(soft_flags[:4])
    else:
        label = "GO_KINDLING"
        headline = "GO kindling (still needs your GO)"
        why = (
            "live_signal bar cleared (phase early, structure ok, green R band, hold) "
            "and CF not waived. Money still OFF until you reply GO / run apply CLI."
        )

    return {
        "label": label,
        "headline": headline,
        "why": why,
        "factors": factor_lines,
        "per_pair": per_pair,
        "soft_flags": soft_flags,
        "hard_flags": hard_flags,
        "cf_waived": bool(cf.get("waived")),
        "signal_bar_profile": profile or None,
    }


def approval_telegram_summary(
    plan: Dict[str, Any],
    *,
    force: bool = False,
    mark_sent: bool = True,
    dedupe_hours: float = APPROVAL_DEDUPE_HOURS,
) -> str:
    """Operator TG body only when path is armed and n_planned > 0.

    Includes RECOMMEND + decision factors. Empty when: not armed, kill on,
    no planned steps, or same fingerprint within dedupe window.
    Never places orders. Cron must only call plan path.
    """
    if not isinstance(plan, dict):
        return ""
    if kill_switch_on():
        return ""
    if not plan.get("live_armed"):
        return ""
    n_plan = int(plan.get("n_planned") or 0)
    if n_plan <= 0:
        return ""
    steps = [r for r in _plan_rows(plan) if r.get("status") == "planned"]
    if not steps:
        return ""
    fp = approval_fingerprint(plan)
    if not force and not _should_send_approval(fp, dedupe_hours=dedupe_hours, mark=mark_sent):
        return ""

    cf = plan.get("cf_gate") if isinstance(plan.get("cf_gate"), dict) else {}
    decision = load_decision()
    waive = _waive_usage(decision)
    rec = build_scale_up_recommendation(plan, steps)

    lines = [
        "SCALE-UP APPROVAL (money still OFF until you GO)",
        f"armed · planned {n_plan} · fp={fp}",
        f"RECOMMEND: {rec.get('headline')}",
        f"Why: {rec.get('why')}",
        "Factors:",
    ]
    for fact in list(rec.get("factors") or [])[:12]:
        lines.append(f"  · {fact}")
    lines.append("Plans:")
    for row in steps:
        pair = shadow._norm_pair(row.get("pair") or "")
        step = _f(row.get("step_usd"))
        held = _f(row.get("held_usd"))
        r = row.get("unrealized_r")
        r_s = f"{float(r)*100:.1f}%" if r is not None else "?"
        phase = row.get("phase")
        hold = row.get("hold_hours")
        hold_s = f"{float(hold):.1f}h" if hold is not None else "?"
        sk = row.get("structure_ok")
        sk_s = "struct✓" if sk is True else ("struct✗" if sk is False else "struct?")
        lines.append(
            f"• {pair} +${step:.0f} (held ${held:.0f} · r {r_s} · "
            f"phase {phase}/{_phase_label(phase)} · hold {hold_s} · {sk_s})"
        )
    if cf.get("waived"):
        rem = int(waive.get("remaining") or 0)
        used = int(waive.get("used") or 0)
        mx = int(waive.get("max") or 0)
        lines.append(f"CF: waived ({used}/{mx} used · {rem} left) — ATTENTION_ONLY")
    else:
        lines.append(f"CF: {cf.get('reason') or 'ok'}")
    profile = plan.get("signal_bar_profile") or rec.get("signal_bar_profile")
    if profile:
        lines.append(f"signal_bar: {profile}")
    safety = plan.get("safety") if isinstance(plan.get("safety"), dict) else {}
    lines.append(
        f"caps: {safety.get('max_steps_per_utc_day', 1)} step/day · "
        f"${safety.get('max_step_usd', 25)} step · ${safety.get('max_usd_per_utc_day', 50)}/day"
    )
    if rec.get("label") == "GO_KINDLING":
        lines.append("If you agree → reply GO + pair, or run:")
    elif rec.get("label") == "HOLD_PATH_PROOF":
        lines.append("Default HOLD. Override only if you want path-proof spend → GO + pair:")
    else:
        lines.append("Do not apply. Diagnostic only:")
    lines.append(
        "cd /home/brad/projects/crypto-trading-bot && "
        "PYTHONPATH=. .venv/bin/python3 scripts/phase6/run_tryout_scale_up_live.py "
        "--apply --go --no-dry-run"
    )
    lines.append("Kill: touch data/state/tryout_scale_up_live_KILL")
    body = "\n".join(lines)
    _append_crumb(
        {
            "kind": "approval_ping",
            "ts": _utc_iso(),
            "fingerprint": fp,
            "n_planned": n_plan,
            "forced": bool(force),
            "recommend": rec.get("label"),
            "recommend_headline": rec.get("headline"),
            "factors": list(rec.get("factors") or [])[:12],
        }
    )
    return body


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="Tryout scale-up LIVE path (default dry-run; cron must not --go)"
    )
    p.add_argument(
        "--plan",
        action="store_true",
        help="Build plan from fresh shadow cycle (default if no flags)",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Run apply path (still dry-run unless --go and not --dry-run false)",
    )
    p.add_argument(
        "--go",
        action="store_true",
        help="Operator intent flag; money still needs dry_run off + live_apply armed",
    )
    p.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="No orders (default)",
    )
    p.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Allow money when combined with --go and decision.live_apply",
    )
    p.add_argument(
        "--shadow-executor",
        action="store_true",
        help="Force OrderExecutor shadow_mode even on apply (isolation / safe rehearse)",
    )
    p.add_argument(
        "--telegram",
        action="store_true",
        help="Print approval card only when n_planned>0 (empty otherwise for quiet cron)",
    )
    p.add_argument(
        "--quiet-ok",
        action="store_true",
        help="Same quiet contract as --telegram (empty stdout when nothing to approve)",
    )
    p.add_argument(
        "--force-approval",
        action="store_true",
        help="Bypass 12h fingerprint dedupe for approval card (still plan-only)",
    )
    p.add_argument("--json", action="store_true", help="Dump plan JSON (and apply if requested)")
    args = p.parse_args(list(argv) if argv is not None else None)

    do_plan = args.plan or not args.apply or args.telegram or args.quiet_ok
    board = shadow.run_cycle()
    plan = plan_live_steps(board=board)

    quiet = bool(args.telegram or args.quiet_ok)
    if quiet and not args.apply:
        body = approval_telegram_summary(
            plan,
            force=bool(args.force_approval),
            mark_sent=True,
        )
        if body:
            print(body)
        return 0

    if args.json or not quiet:
        print(json.dumps({"plan": plan}, indent=2, default=str))

    if args.apply or args.go:
        ex = None
        if args.shadow_executor or args.dry_run or not args.go:
            ex = _build_executor(shadow_mode=True)
        summary = apply_live_steps(
            plan,
            dry_run=args.dry_run,
            go=args.go,
            executor=ex,
        )
        print(json.dumps({"apply": summary}, indent=2, default=str))
        if summary.get("money_moved"):
            return 0
        if args.go and not args.dry_run and not summary.get("live_armed"):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
