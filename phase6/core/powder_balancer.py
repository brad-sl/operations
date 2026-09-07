"""
Powder balancer — keep USD dry powder for tryout/deploy waves; park the rest in USDC.

Problem this solves
-------------------
Under quality_tryout (e.g. 2×$75) most cash is a *structural stub* the book cannot absorb.
Legacy USDC park either:
  - parks only on full park_signal (deploy days stay 100% USD → $0 yield), or
  - full redeploy-unwinds almost all USDC on deploy edge (kills yield every flip).

Powder balancer (park-while-micro-deploy):
  - NEVER sells crypto alts (availability for C is unchanged)
  - Targets USD reserve = next buy wave(s) + buffer (auto from tryout / rebalance cap)
  - Parks excess USD → USDC
  - Tops up USD ← USDC when powder is short of reserve
  - Writes status for monitor / dashboard

Gated by live_usdc_park.enabled AND powder_balancer.enabled.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from phase6.core.paths import PROJECT_ROOT

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)

STATUS_PATH = PROJECT_ROOT / "data/state/powder_balancer_status.json"
HISTORY_PATH = PROJECT_ROOT / "data/state/powder_balancer_history.jsonl"

ACTION_HOLD = "hold"
ACTION_PARK_TO_USDC = "park_to_usdc"
ACTION_TOPUP_FROM_USDC = "topup_from_usdc"
ACTION_DISABLED = "disabled"
ACTION_SKIP = "skip"


@dataclass
class WaveNeed:
    """How much USD the next deploy wave(s) may need."""

    seat_usd: float = 75.0
    max_seats_per_day: int = 2
    max_concurrent_seats: int = 2
    rebalance_cap_usd: float = 75.0
    wave_usd: float = 150.0
    source: str = "default"


@dataclass
class PowderPlan:
    """Pure decision — no exchange IO."""

    action: str = ACTION_HOLD
    reason: str = ""
    usd: float = 0.0
    usdc: float = 0.0
    crypto_usd: float = 0.0
    nav: float = 0.0
    cash_total: float = 0.0
    target_usd_reserve: float = 0.0
    usd_excess: float = 0.0
    usd_shortfall: float = 0.0
    convert_usd: float = 0.0  # USD → USDC
    unwind_usd: float = 0.0  # USDC → USD
    structural_stub_usd: float = 0.0
    wave: Dict[str, Any] = field(default_factory=dict)
    powder_cfg: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _recovery_block(config_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Find enabled soft-down / quality_tryout recovery block."""

    def _from_oo(oo: Any) -> Dict[str, Any]:
        if not isinstance(oo, dict):
            return {}
        rec = oo.get("recovery_soft_down_20260828") or {}
        if isinstance(rec, dict) and rec.get("enabled"):
            return rec
        return {}

    if config_dict:
        rcp = config_dict.get("regime_cash_policy") or {}
        if isinstance(rcp, dict):
            hit = _from_oo(rcp.get("operator_override"))
            if hit:
                return hit
        hit = _from_oo(config_dict.get("operator_override"))
        if hit:
            return hit
        rec = config_dict.get("recovery_soft_down_20260828") or {}
        if isinstance(rec, dict) and rec.get("enabled"):
            return rec

    # Disk SSOT when runner config lacks nested recovery
    path = PROJECT_ROOT / "config" / "regime_cash_policy.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        hit = _from_oo(raw.get("operator_override"))
        if hit:
            return hit
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return {}


def compute_wave_need(config_dict: Optional[Dict[str, Any]] = None) -> WaveNeed:
    """Derive next-wave USD need from tryout + rebalance cap."""
    gs = (config_dict or {}).get("global_settings") or {}
    rebal_cap = float(gs.get("rebalance_cap_usd") or 0.0)
    seat = max(rebal_cap, 0.0) if rebal_cap > 0 else 75.0
    max_day = 2
    max_conc = 2
    source = "rebalance_cap"

    rec = _recovery_block(config_dict)
    qt = rec.get("quality_tryout") if isinstance(rec.get("quality_tryout"), dict) else {}
    if qt:
        try:
            abs_cap = float(qt.get("abs_cap_usd") or seat or 75.0)
            seat = abs_cap
            max_day = int(qt.get("max_new_seats_per_day") or max_day)
            # concurrent ≈ day pace under tryout (same sleeve inventory bound)
            max_conc = max(1, max_day)
            source = "quality_tryout"
        except (TypeError, ValueError):
            pass

    # bull override cap sometimes tighter
    bull_max = rec.get("bull_rebalance_cap_usd_max")
    if bull_max is not None:
        try:
            seat = min(seat, float(bull_max))
        except (TypeError, ValueError):
            pass

    if rebal_cap > 0:
        seat = min(seat, rebal_cap) if seat > 0 else rebal_cap

    wave = float(seat) * float(max_conc)
    return WaveNeed(
        seat_usd=float(seat),
        max_seats_per_day=int(max_day),
        max_concurrent_seats=int(max_conc),
        rebalance_cap_usd=float(rebal_cap),
        wave_usd=wave,
        source=source,
    )


def powder_balancer_cfg(park_cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Normalize powder_balancer knobs from live_usdc_park settings."""
    raw = dict((park_cfg or {}).get("powder_balancer") or {})

    def fnum(key: str, default: float) -> float:
        if key not in raw or raw[key] is None or raw[key] == "":
            return float(default)
        return float(raw[key])

    out = {
        "enabled": bool(raw.get("enabled", False)),
        "auto_reserve_from_tryout": bool(raw.get("auto_reserve_from_tryout", True)),
        "reserve_waves": fnum("reserve_waves", 1.0),
        "usd_reserve_usd": raw.get("usd_reserve_usd"),  # explicit override or None
        "usd_reserve_floor_usd": fnum("usd_reserve_floor_usd", 150.0),
        "usd_reserve_buffer_usd": fnum("usd_reserve_buffer_usd", 50.0),
        "usd_reserve_ceiling_usd": fnum("usd_reserve_ceiling_usd", 400.0),
        "min_action_usd": fnum("min_action_usd", 25.0),
        "hysteresis_usd": fnum("hysteresis_usd", 20.0),
        "do_not_sell_alts": bool(raw.get("do_not_sell_alts", True)),
        "note": str(
            raw.get("note")
            or "Park structural stub in USDC; keep USD wave reserve for buys."
        ),
    }
    return out


def compute_target_usd_reserve(
    wave: WaveNeed,
    pcfg: Dict[str, Any],
) -> float:
    explicit = pcfg.get("usd_reserve_usd")
    if explicit is not None and str(explicit).strip() != "":
        try:
            base = float(explicit)
        except (TypeError, ValueError):
            base = wave.wave_usd
    elif pcfg.get("auto_reserve_from_tryout", True):
        base = wave.wave_usd * float(pcfg.get("reserve_waves", 1.0) or 1.0)
    else:
        base = float(pcfg.get("usd_reserve_floor_usd", 150.0) or 150.0)

    base = base + float(pcfg.get("usd_reserve_buffer_usd", 50.0) or 0.0)
    floor = float(pcfg.get("usd_reserve_floor_usd", 150.0) or 150.0)
    ceiling = float(pcfg.get("usd_reserve_ceiling_usd", 400.0) or 400.0)
    return max(floor, min(ceiling, base))


def plan_powder_balance(
    *,
    usd: float,
    usdc: float,
    crypto_usd: float = 0.0,
    nav: Optional[float] = None,
    park_cfg: Optional[Dict[str, Any]] = None,
    config_dict: Optional[Dict[str, Any]] = None,
    park_master_enabled: bool = True,
) -> PowderPlan:
    """Pure planner: decide park / topup / hold. Never proposes alt sells."""
    pcfg = powder_balancer_cfg(park_cfg)
    wave = compute_wave_need(config_dict)
    plan = PowderPlan(
        usd=float(usd or 0.0),
        usdc=float(usdc or 0.0),
        crypto_usd=float(crypto_usd or 0.0),
        wave=asdict(wave),
        powder_cfg=pcfg,
    )
    plan.nav = float(nav) if nav is not None else plan.usd + plan.usdc + plan.crypto_usd
    plan.cash_total = plan.usd + plan.usdc
    plan.target_usd_reserve = compute_target_usd_reserve(wave, pcfg)
    plan.structural_stub_usd = max(0.0, plan.cash_total - plan.target_usd_reserve)

    if not park_master_enabled:
        plan.action = ACTION_DISABLED
        plan.reason = "live_usdc_park_disabled"
        return plan
    if not pcfg.get("enabled"):
        plan.action = ACTION_DISABLED
        plan.reason = "powder_balancer_disabled"
        return plan

    min_act = float(pcfg.get("min_action_usd", 25.0) or 25.0)
    hyst = float(pcfg.get("hysteresis_usd", 20.0) or 20.0)
    target = plan.target_usd_reserve

    excess = plan.usd - target
    shortfall = target - plan.usd
    plan.usd_excess = max(0.0, excess)
    plan.usd_shortfall = max(0.0, shortfall)

    # Top up powder first (availability for buys beats yield)
    if shortfall > max(min_act, hyst * 0.5) and plan.usdc >= min_act:
        unwind = min(shortfall, plan.usdc)
        if unwind >= min_act:
            plan.action = ACTION_TOPUP_FROM_USDC
            plan.unwind_usd = round(unwind, 2)
            plan.reason = "usd_below_wave_reserve"
            return plan

    # Park structural excess USD → USDC
    if excess > max(min_act, hyst) and plan.usd > target + min_act:
        convert = excess  # leave exactly ~target USD
        if convert >= min_act:
            plan.action = ACTION_PARK_TO_USDC
            plan.convert_usd = round(convert, 2)
            plan.reason = "usd_above_wave_reserve_park_stub"
            return plan

    plan.action = ACTION_HOLD
    if abs(plan.usd - target) <= hyst:
        plan.reason = "within_hysteresis"
    else:
        plan.reason = "no_action_threshold"
    return plan


def write_powder_status(payload: Dict[str, Any]) -> Path:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["ts"] = payload.get("ts") or datetime.now(timezone.utc).isoformat()
    STATUS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except OSError:
        pass
    return STATUS_PATH


def execute_powder_balance(
    runner: "Phase6Runner",
    park_cfg: Dict[str, Any],
    *,
    account_id: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute park/topup USD↔USDC only. Never sells basket alts.
    """
    from phase6.core.usdc_park_executor import _portfolio_snapshot

    snap = _portfolio_snapshot(runner)
    plan = plan_powder_balance(
        usd=snap["usd"],
        usdc=snap["usdc"],
        crypto_usd=snap["crypto_usd"],
        nav=snap["nav"],
        park_cfg=park_cfg,
        config_dict=getattr(runner, "config_dict", None) or {},
        park_master_enabled=bool(park_cfg.get("enabled")),
    )
    out: Dict[str, Any] = {
        "ok": True,
        "account_id": account_id,
        "mode": getattr(runner, "mode", "unknown"),
        "dry_run": bool(dry_run),
        "plan": plan.to_dict(),
        "snap_before": {
            "usd": round(snap["usd"], 2),
            "usdc": round(snap["usdc"], 2),
            "crypto_usd": round(snap["crypto_usd"], 2),
            "nav": round(snap["nav"], 2),
        },
        "action": plan.action,
        "reason": plan.reason,
        "convert_usd": plan.convert_usd,
        "unwind_usd": plan.unwind_usd,
        "target_usd_reserve": plan.target_usd_reserve,
        "structural_stub_usd": plan.structural_stub_usd,
        "wave_usd": plan.wave.get("wave_usd"),
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    if plan.action in (ACTION_DISABLED, ACTION_HOLD, ACTION_SKIP):
        out["skipped"] = True
        write_powder_status(out)
        logger.info(
            "[POWDER] %s reason=%s usd=%.0f target=%.0f usdc=%.0f stub=%.0f",
            plan.action,
            plan.reason,
            plan.usd,
            plan.target_usd_reserve,
            plan.usdc,
            plan.structural_stub_usd,
        )
        return out

    # Venue has no USDC-USD spot on CONSUMER portfolios — use usdc_convert
    # (native Convert when allowed, else USDT two-hop).
    trade: Optional[Dict[str, Any]] = None

    if dry_run or getattr(runner, "mode", "") != "live":
        # shadow / dry: record intent only
        out["skipped"] = True
        out["shadow_intent"] = True
        out["trade"] = {
            "would_action": plan.action,
            "convert_usd": plan.convert_usd,
            "unwind_usd": plan.unwind_usd,
            "method": "shadow_intent",
        }
        write_powder_status(out)
        logger.info(
            "[POWDER] shadow %s convert=$%s unwind=$%s",
            plan.action,
            plan.convert_usd,
            plan.unwind_usd,
        )
        return out

    try:
        from phase6.core.usdc_convert import convert_via_runner

        if plan.action == ACTION_PARK_TO_USDC and plan.convert_usd >= 1.0:
            trade = convert_via_runner(
                runner, direction="usd_to_usdc", amount=plan.convert_usd
            )
        elif plan.action == ACTION_TOPUP_FROM_USDC and plan.unwind_usd >= 1.0:
            trade = convert_via_runner(
                runner, direction="usdc_to_usd", amount=plan.unwind_usd
            )
        else:
            trade = {"success": True, "skipped": True, "reason": "no_size"}
    except Exception as e:
        logger.exception("[POWDER] trade failed")
        trade = {"success": False, "error": str(e)}
        out["ok"] = False

    if getattr(runner, "portfolio", None):
        try:
            runner.portfolio.refresh()
        except Exception:
            pass
    snap2 = _portfolio_snapshot(runner)
    out["trade"] = trade
    out["ok"] = bool((trade or {}).get("success", False)) and out.get("ok", True)
    out["snap_after"] = {
        "usd": round(snap2["usd"], 2),
        "usdc": round(snap2["usdc"], 2),
        "crypto_usd": round(snap2["crypto_usd"], 2),
        "nav": round(snap2["nav"], 2),
    }
    out["skipped"] = False
    write_powder_status(out)
    logger.info(
        "[POWDER] live %s ok=%s convert=$%s unwind=$%s usd %.0f→%.0f usdc %.0f→%.0f",
        plan.action,
        out["ok"],
        plan.convert_usd,
        plan.unwind_usd,
        snap["usd"],
        snap2["usd"],
        snap["usdc"],
        snap2["usdc"],
    )
    return out


def monitor_powder_snapshot(
    *,
    usd: float,
    usdc: float,
    crypto_usd: float,
    park_cfg: Optional[Dict[str, Any]] = None,
    config_dict: Optional[Dict[str, Any]] = None,
    park_master_enabled: bool = True,
) -> Dict[str, Any]:
    """Read-only monitor payload (no trades)."""
    plan = plan_powder_balance(
        usd=usd,
        usdc=usdc,
        crypto_usd=crypto_usd,
        park_cfg=park_cfg,
        config_dict=config_dict,
        park_master_enabled=park_master_enabled,
    )
    d = plan.to_dict()
    d["crypto_in_play_note"] = (
        f"Max concurrent tryout notional ~${plan.wave.get('wave_usd', 0):.0f} "
        f"({plan.wave.get('max_concurrent_seats')}×${plan.wave.get('seat_usd', 0):.0f}). "
        f"Structural cash stub ~${plan.structural_stub_usd:.0f} is yield-park candidate — "
        f"raising crypto-in-play requires seat/cap policy, not more USD powder."
    )
    d["availability_ok"] = plan.usd >= plan.target_usd_reserve - float(
        plan.powder_cfg.get("hysteresis_usd", 20) or 20
    )
    return d
