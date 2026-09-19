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


def plan_live_steps(
    decisions: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    board: Optional[Dict[str, Any]] = None,
    cfg: Optional[Dict[str, Any]] = None,
    decision: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build apply plan from shadow would_scale rows. Never places orders."""
    now = now or _utc_now()
    c = cfg or shadow.load_cfg()
    d = decision if isinstance(decision, dict) else load_decision()
    armed = is_live_armed(d)
    b = board
    if b is None and decisions is None:
        # fresh shadow evaluate (no write side effects beyond normal cycle — caller may pass board)
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
                or ["ready_for_apply_when_go"],
                detail={
                    "shadow_reasons": row.get("reasons"),
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
        "n_planned": sum(1 for p in plans if p.status == "planned"),
        "n_blocked": sum(1 for p in plans if p.status == "blocked"),
        "plans": [p.to_dict() for p in plans],
        "note": (
            "Plan only. apply_live_steps(..., go=True, dry_run=False) required for money. "
            "Cron must never call apply."
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
    args = p.parse_args(list(argv) if argv is not None else None)

    do_plan = args.plan or not args.apply
    board = shadow.run_cycle()
    plan = plan_live_steps(board=board)
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
