#!/usr/bin/env python3
"""
Fix B — ARCH-4 C2 ballast seeder (Brad GO runway C 2026-10-28).

Problem: C2 injects matrix max_add / add-risk floor, but RotationStrategy only
emits BUY on ROTATE_IN ≥ min_buy. BTC/ETH often sit HOLD@0.5 → TradePlan empty
while powder idles and shells (LINK) still win the allocator.

Fix: when C2 live + seeder live, if would_allow_under_target_step opens a floor
step on BTC/ETH, inject one BUY ≤ step tagged c2_ballast_floor before gates.

Does not sell bags. Does not raise flat cap. Kill:
  data/state/c2_ballast_seeder_KILL
Config:
  config/c2_ballast_seeder.json
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.ballast_under_target_floor import (
    effective_live_apply as c2_live,
    would_allow_under_target_step,
)
from phase6.core.paths import CONFIG_DIR, STATE_DIR

logger = logging.getLogger(__name__)

SCHEMA = "c2_ballast_seeder_v1"
CONFIG_PATH = CONFIG_DIR / "c2_ballast_seeder.json"
KILL_PATH = STATE_DIR / "c2_ballast_seeder_KILL"
LATEST_PATH = STATE_DIR / "c2_ballast_seeder_latest.json"

DEFAULT_CFG: Dict[str, Any] = {
    "schema": SCHEMA,
    "live_apply": False,
    "shadow_only": True,
    "pairs_prefer": ["BTC-USD", "ETH-USD"],
    "role": "ballast_core",
    "default_target_w": 0.18,
    "default_flat_cap_usd": 75.0,
    "max_actions_per_plan": 1,
    "require_c2_live": True,
    "tag_reason": "c2_ballast_floor",
    "note": "Inject BUY when C2 floor would allow and plan lacks ballast BUY",
}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _norm_pair(pair: str) -> str:
    p = str(pair or "").strip().upper().replace("_", "-")
    if not p:
        return ""
    if "-" not in p:
        p = f"{p}-USD"
    return p


def kill_file_on(path: Optional[Path] = None) -> bool:
    try:
        return (path or KILL_PATH).is_file()
    except Exception:
        return False


def load_config() -> Dict[str, Any]:
    cfg = DEFAULT_CFG.copy()
    try:
        if CONFIG_PATH.is_file():
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg.update(raw)
    except Exception as e:
        logger.warning("c2_ballast_seeder config load failed: %s", e)
    return cfg


def is_live_apply(cfg: Optional[Dict[str, Any]] = None) -> bool:
    c = cfg or load_config()
    if kill_file_on():
        return False
    if not bool(c.get("live_apply")):
        return False
    if bool(c.get("require_c2_live", True)) and not c2_live():
        return False
    return True


def _held_map(current_allocs: Optional[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for k, v in (current_allocs or {}).items():
        pn = _norm_pair(str(k))
        if not pn:
            continue
        if isinstance(v, dict):
            usd = None
            for key in ("value_usd", "usd_value", "usd", "notional_usd", "value"):
                if v.get(key) is not None:
                    usd = _f(v.get(key), 0.0)
                    break
            out[pn] = float(usd or 0.0)
        else:
            out[pn] = _f(v, 0.0)
    return out


def _plan_has_ballast_buy(plan: Any, pairs: Sequence[str]) -> bool:
    actions = list(getattr(plan, "actions", None) or [])
    want = {_norm_pair(p) for p in pairs}
    for a in actions:
        if not isinstance(a, dict):
            continue
        act = str(a.get("action") or a.get("side") or "").upper()
        if act != "BUY":
            continue
        if _norm_pair(str(a.get("pair") or "")) in want:
            return True
    return False


def _equity_and_cap(runner: Any, held: Dict[str, float], cash_usd: float) -> Tuple[float, float]:
    eq = cash_usd + sum(held.values())
    cap = 75.0
    try:
        rc = STATE_DIR / "regime_cash_status.json"
        if rc.is_file():
            o = json.loads(rc.read_text(encoding="utf-8"))
            if isinstance(o, dict) and o.get("rebalance_cap_usd") is not None:
                cap = _f(o.get("rebalance_cap_usd"), 75.0)
    except Exception:
        pass
    try:
        live_p = STATE_DIR / "phase6_live_state.json"
        if live_p.is_file():
            live = json.loads(live_p.read_text(encoding="utf-8"))
            eq2 = _f(live.get("total_usd") or live.get("equity_usd"), 0.0)
            if eq2 > eq:
                eq = eq2
    except Exception:
        pass
    if runner is not None:
        try:
            tot = getattr(runner, "total_usd", None) or getattr(runner, "equity_usd", None)
            if tot is not None and _f(tot) > eq:
                eq = _f(tot)
        except Exception:
            pass
    return max(eq, 1.0), max(cap, 0.0)


def _upnl_pct(pair: str, held_usd: float, runner: Any) -> float:
    try:
        live_p = STATE_DIR / "phase6_live_state.json"
        if live_p.is_file():
            live = json.loads(live_p.read_text(encoding="utf-8"))
            for row in live.get("positions") or []:
                if not isinstance(row, dict):
                    continue
                if _norm_pair(str(row.get("pair") or "")) != pair:
                    continue
                if row.get("unrealized_pnl_pct") is not None:
                    return _f(row.get("unrealized_pnl_pct"), 0.0)
                u = row.get("unrealized_pnl_usd")
                v = _f(row.get("value_usd"), held_usd)
                if v > 0 and u is not None:
                    return _f(u) / v
    except Exception:
        pass
    return 0.0


def _stop_attached(pair: str, held_usd: float) -> bool:
    """Held bags need a stop; empty first seat attaches post-buy (NEEDLE) — allow seed."""
    if held_usd < 1.0:
        return True
    try:
        live_p = STATE_DIR / "phase6_live_state.json"
        if live_p.is_file():
            live = json.loads(live_p.read_text(encoding="utf-8"))
            for row in live.get("positions") or []:
                if not isinstance(row, dict):
                    continue
                if _norm_pair(str(row.get("pair") or "")) != pair:
                    continue
                # any SL estimate or hold locked → treat attached
                if row.get("sl_stop_price_est") or _f(row.get("hold"), 0.0) > 0:
                    return True
    except Exception:
        pass
    # Conservative for held without evidence: still allow seed (C2 matrix assumes True)
    return True


def propose_seed_actions(
    *,
    current_allocs: Optional[Dict[str, Any]],
    cash_usd: float,
    runner: Any = None,
    cfg: Optional[Dict[str, Any]] = None,
    target_w_by_pair: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Pure-ish: which ballast BUYs would seed (does not mutate plan)."""
    c = cfg or load_config()
    live = is_live_apply(c)
    pairs = [_norm_pair(p) for p in (c.get("pairs_prefer") or DEFAULT_CFG["pairs_prefer"])]
    role = str(c.get("role") or "ballast_core")
    default_tw = _f(c.get("default_target_w"), 0.18)
    held = _held_map(current_allocs)
    eq, flat_cap = _equity_and_cap(runner, held, cash_usd)
    max_n = int(c.get("max_actions_per_plan") or 1)
    tag = str(c.get("tag_reason") or "c2_ballast_floor")

    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "live_apply": live,
        "kill_file": kill_file_on(),
        "c2_live": c2_live(),
        "equity_usd": round(eq, 2),
        "flat_cap_usd": round(flat_cap, 2),
        "candidates": [],
        "actions": [],
        "skipped_reasons": [],
    }

    if kill_file_on():
        out["skipped_reasons"].append("kill_file")
        return out
    if bool(c.get("require_c2_live", True)) and not c2_live():
        out["skipped_reasons"].append("c2_not_live")
        return out

    budget = flat_cap
    for pair in pairs:
        if len(out["actions"]) >= max_n:
            break
        h = _f(held.get(pair), 0.0)
        tw = default_tw
        if target_w_by_pair and pair in target_w_by_pair:
            tw = _f(target_w_by_pair.get(pair), default_tw)
        # Probe floor as collapsed ordinary max_add — seeder *is* the room.
        would = would_allow_under_target_step(
            pair=pair,
            role=role,
            held_usd=h,
            equity_usd=eq,
            target_w=tw,
            max_add_usd=0.0,
            open_upnl_pct=_upnl_pct(pair, h, runner),
            stop_attached=_stop_attached(pair, h),
            flat_cap_usd=min(flat_cap, budget) if budget > 0 else 0.0,
        )
        cand = {"pair": pair, "held_usd": round(h, 2), "would": would}
        out["candidates"].append(cand)
        if not would.get("allow"):
            continue
        step = min(_f(would.get("step_usd"), 0.0), budget, flat_cap)
        if step < 25.0 - 1e-9:
            cand["seed_skip"] = "step_below_min_move"
            continue
        action = {
            "pair": pair,
            "action": "BUY",
            "usd": round(step, 2),
            "reason": tag,
            "c2_ballast_floor": True,
            "c2_seeder": True,
            "source": "c2_ballast_seeder",
        }
        out["actions"].append(action)
        budget = max(0.0, budget - step)

    return out


def seed_trade_plan(
    plan: Any,
    *,
    current_allocs: Optional[Dict[str, Any]] = None,
    cash_usd: float = 0.0,
    runner: Any = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Mutate plan.actions: inject ballast BUY(s) when live and missing.
    Shadow (live_apply false): write receipt only, no mutation.
    If plan already has untagged BTC/ETH BUY (light_tilt), retag + clip to
    floor step so REGIME-CASH c2 path can pass (else sent/RSI kills recovery).
    """
    c = cfg or load_config()
    live = is_live_apply(c)
    pairs = [_norm_pair(p) for p in (c.get("pairs_prefer") or DEFAULT_CFG["pairs_prefer"])]
    pair_set = set(pairs)
    tag = str(c.get("tag_reason") or "c2_ballast_floor")
    receipt = propose_seed_actions(
        current_allocs=current_allocs,
        cash_usd=cash_usd,
        runner=runner,
        cfg=c,
    )
    receipt["had_ballast_buy_before"] = _plan_has_ballast_buy(plan, pairs)
    receipt["injected"] = []
    receipt["retagged"] = []

    actions = list(getattr(plan, "actions", None) or [])

    def _write_actions(new_actions: List[Dict[str, Any]]) -> None:
        try:
            plan.actions = new_actions
        except Exception:
            if isinstance(plan, dict):
                plan["actions"] = new_actions

    if live:
        # Retag existing ballast BUYs so they survive REGIME-CASH as c2 seeds
        step_by_pair = {
            _norm_pair(a.get("pair")): _f(a.get("usd"))
            for a in (receipt.get("actions") or [])
            if isinstance(a, dict)
        }
        # Also compute steps from candidates if propose returned allow
        if not step_by_pair:
            for cand in receipt.get("candidates") or []:
                w = cand.get("would") or {}
                if w.get("allow") and _f(w.get("step_usd")) >= 25.0:
                    step_by_pair[_norm_pair(cand.get("pair"))] = _f(w.get("step_usd"))

        new_actions: List[Dict[str, Any]] = []
        retagged_pairs = set()
        for a in actions:
            if not isinstance(a, dict):
                new_actions.append(a)
                continue
            act = str(a.get("action") or a.get("side") or "").upper()
            pn = _norm_pair(str(a.get("pair") or ""))
            if act == "BUY" and pn in pair_set:
                a2 = dict(a)
                step = step_by_pair.get(pn) or min(
                    _f(c.get("default_flat_cap_usd"), 75.0),
                    _f(a2.get("usd") if a2.get("usd") is not None else a2.get("usd_amount"), 75.0),
                )
                # Clip oversized light_tilt down to flat ballast step
                prev = _f(a2.get("usd") if a2.get("usd") is not None else a2.get("usd_amount"), 0.0)
                if step >= 25.0:
                    a2["usd"] = round(min(prev, step) if prev > 0 else step, 2)
                    if "usd_amount" in a2:
                        a2["usd_amount"] = a2["usd"]
                a2["reason"] = tag
                a2["c2_ballast_floor"] = True
                a2["c2_seeder"] = True
                a2["source"] = "c2_ballast_seeder"
                a2["c2_retagged_from"] = str(a.get("reason") or "untagged")
                new_actions.append(a2)
                receipt["retagged"].append(dict(a2))
                retagged_pairs.add(pn)
                logger.info(
                    "[C2-SEEDER] retag BUY %s $%.2f→$%.2f as %s",
                    pn,
                    prev,
                    _f(a2.get("usd")),
                    tag,
                )
            else:
                new_actions.append(a)
        actions = new_actions

        # Inject if still missing preferred pairs with open floor
        if not retagged_pairs and receipt.get("actions"):
            for a in receipt["actions"]:
                actions.append(dict(a))
                receipt["injected"].append(dict(a))
                logger.info(
                    "[C2-SEEDER] inject BUY %s $%.2f reason=%s",
                    a.get("pair"),
                    _f(a.get("usd")),
                    a.get("reason"),
                )
        elif receipt.get("actions"):
            # inject only pairs not already retagged
            have = {
                _norm_pair(str(a.get("pair") or ""))
                for a in actions
                if isinstance(a, dict)
                and str(a.get("action") or a.get("side") or "").upper() == "BUY"
            }
            for a in receipt["actions"]:
                pn = _norm_pair(str(a.get("pair") or ""))
                if pn in have:
                    continue
                actions.append(dict(a))
                receipt["injected"].append(dict(a))
                logger.info(
                    "[C2-SEEDER] inject BUY %s $%.2f reason=%s",
                    a.get("pair"),
                    _f(a.get("usd")),
                    a.get("reason"),
                )
        _write_actions(actions)
        if (receipt["injected"] or receipt["retagged"]) and hasattr(plan, "notes"):
            try:
                plan.notes = (str(getattr(plan, "notes", "") or "") + "|c2_ballast_seeder").strip("|")
            except Exception:
                pass
    elif not live:
        receipt["skipped_reasons"].append("shadow_only_no_inject")
    else:
        if not receipt.get("actions") and not receipt.get("retagged"):
            receipt["skipped_reasons"].append("no_candidate_step")

    if receipt["had_ballast_buy_before"] and not receipt.get("retagged") and not receipt.get("injected"):
        if "plan_already_has_ballast_buy" not in receipt["skipped_reasons"]:
            receipt["skipped_reasons"].append("plan_already_has_ballast_buy")

    try:
        LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        LATEST_PATH.write_text(json.dumps(receipt, indent=2, default=str) + "\n", encoding="utf-8")
    except Exception as e:
        logger.debug("c2 seeder receipt write failed: %s", e)

    return plan


def filter_trade_plan_shell_freeze(
    plan: Any,
    *,
    cfg: Optional[Dict[str, Any]] = None,
    allow_pairs: Optional[Sequence[str]] = None,
) -> Any:
    """
    Runway C shell freeze: drop non-ballast BUYs from ARCH-4 plan when enabled.
    Does not touch SELL / PAXG / BTC / ETH.
    Config flag: shell_freeze_live on seeder config OR data/state/c_runway_shell_freeze_LIVE
    """
    c = cfg or load_config()
    flag = STATE_DIR / "c_runway_shell_freeze_LIVE"
    freeze = bool(c.get("shell_freeze_live")) or flag.is_file()
    if not freeze or kill_file_on(STATE_DIR / "c_runway_shell_freeze_KILL"):
        return plan
    allow = {
        _norm_pair(p)
        for p in (
            allow_pairs
            or c.get("shell_freeze_allow_pairs")
            or ["BTC-USD", "ETH-USD", "PAXG-USD", "USDC-USD", "USDT-USD", "USDT-USDC"]
        )
    }
    actions = list(getattr(plan, "actions", None) or [])
    if not actions:
        return plan
    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for a in actions:
        if not isinstance(a, dict):
            kept.append(a)
            continue
        act = str(a.get("action") or a.get("side") or "").upper()
        pair = _norm_pair(str(a.get("pair") or ""))
        if act == "BUY" and pair and pair not in allow:
            dropped.append(a)
            logger.info(
                "[C-RUNWAY] shell_freeze drop BUY %s $%s",
                pair,
                a.get("usd") or a.get("usd_amount"),
            )
            continue
        kept.append(a)
    if dropped:
        try:
            plan.actions = kept
        except Exception:
            if isinstance(plan, dict):
                plan["actions"] = kept
        try:
            path = STATE_DIR / "c_runway_shell_freeze_latest.json"
            path.write_text(
                json.dumps(
                    {"dropped": dropped, "kept_n": len(kept), "allow": sorted(allow)},
                    indent=2,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass
    return plan
