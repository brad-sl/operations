"""Ensure spendable USD for a tryout shell from USDC (capped clip unwind).

A+ money path: door open + shell sized → if USD short, USDC→USD for shortfall only.
Never dumps the USDC stub. Never sells crypto. Park/bear keeps USDC.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from phase6.core.paths import STATE_DIR

logger = logging.getLogger(__name__)

LATEST_PATH = STATE_DIR / "tryout_fund_from_usdc_latest.json"
EVENTS_PATH = STATE_DIR / "tryout_fund_from_usdc_events.jsonl"

# Buffer above shell so fees / post-only misses don't strand the seat.
DEFAULT_BUFFER_USD = 5.0
MIN_ACTION_USD = 5.0
MAX_UNWIND_USD = 150.0


@dataclass
class FundPlan:
    action: str = "hold"  # hold | unwind | blocked
    reason: str = ""
    usd: float = 0.0
    usdc: float = 0.0
    shell_usd: float = 0.0
    need_usd: float = 0.0
    shortfall: float = 0.0
    unwind_usd: float = 0.0
    park_or_bear: bool = False
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        __import__("json").dumps(obj, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(__import__("json").dumps(row, default=str) + "\n")


def usd_usdc_from_live_state(live: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Read available USD / USDC from phase6_live_state balances."""
    if live is None:
        p = STATE_DIR / "phase6_live_state.json"
        try:
            import json

            live = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        except Exception:
            live = {}
    usd = 0.0
    usdc = 0.0
    bals = (live or {}).get("balances") if isinstance(live, dict) else None
    if isinstance(bals, list):
        for b in bals:
            if not isinstance(b, dict):
                continue
            ccy = str(b.get("currency") or b.get("ccy") or "").upper()
            avail = _f(b.get("available") if b.get("available") is not None else b.get("balance"))
            if ccy == "USD":
                usd = avail
            elif ccy == "USDC":
                usdc = avail
    elif isinstance(bals, dict):
        for k, v in bals.items():
            ccy = str(k).upper()
            if isinstance(v, dict):
                avail = _f(v.get("available") if v.get("available") is not None else v.get("balance"))
            else:
                avail = _f(v)
            if ccy == "USD":
                usd = avail
            elif ccy == "USDC":
                usdc = avail
    return {"usd": usd, "usdc": usdc}


def regime_park_or_bear(snap: Any = None) -> bool:
    """True when USDC must stay parked (no tryout fund unwind)."""
    try:
        if snap is None:
            from phase6.core.regime_cash_policy import resolve_regime_cash

            snap = resolve_regime_cash()
        mode = str(getattr(snap, "strategy_mode", "") or "").lower()
        regime = str(getattr(snap, "regime", "") or getattr(snap, "label", "") or "").lower()
        if mode in ("usdc_park", "park", "preserve"):
            return True
        if "bear" in regime or "usdc_park" in regime:
            return True
        if not bool(getattr(snap, "allow_new_buys", True)):
            return True
    except Exception as e:
        logger.warning("regime_park_or_bear: %s", e)
    return False


def plan_fund_for_shell(
    *,
    shell_usd: float,
    usd: float,
    usdc: float,
    buffer_usd: float = DEFAULT_BUFFER_USD,
    max_unwind: float = MAX_UNWIND_USD,
    min_action: float = MIN_ACTION_USD,
    park_or_bear: bool = False,
) -> FundPlan:
    """Pure decision: hold if USD covers shell+buffer; else capped USDC→USD."""
    shell = max(0.0, _f(shell_usd))
    usd = max(0.0, _f(usd))
    usdc = max(0.0, _f(usdc))
    buf = max(0.0, _f(buffer_usd))
    need = shell + buf
    plan = FundPlan(
        usd=usd,
        usdc=usdc,
        shell_usd=shell,
        need_usd=need,
        shortfall=max(0.0, need - usd),
        park_or_bear=bool(park_or_bear),
    )
    if shell < 5.0 - 1e-9:
        plan.action = "blocked"
        plan.reason = "shell_too_small"
        return plan
    if park_or_bear:
        plan.action = "blocked" if plan.shortfall >= min_action else "hold"
        plan.reason = "park_or_bear_keep_usdc"
        return plan
    if plan.shortfall < min_action:
        plan.action = "hold"
        plan.reason = "usd_covers_shell"
        return plan
    if usdc < min_action:
        plan.action = "blocked"
        plan.reason = "usdc_below_min_cannot_fund"
        return plan
    unwind = min(plan.shortfall, usdc, max(0.0, _f(max_unwind)))
    if unwind < min_action:
        plan.action = "blocked"
        plan.reason = "unwind_below_min_action"
        return plan
    # Still short after max unwind?
    if usd + unwind + 1e-9 < need and usdc >= plan.shortfall:
        # Cap prevented full cover
        if unwind + 1e-9 < plan.shortfall:
            plan.action = "unwind"
            plan.unwind_usd = round(unwind, 2)
            plan.reason = "usd_short_capped_unwind"
            plan.detail["still_short_after"] = round(need - usd - unwind, 2)
            return plan
    plan.action = "unwind"
    plan.unwind_usd = round(unwind, 2)
    plan.reason = "usd_short_of_shell"
    return plan


def ensure_usd_for_shell(
    *,
    shell_usd: float,
    live: Optional[Dict[str, Any]] = None,
    executor: Any = None,
    runner: Any = None,
    dry_run: bool = True,
    snap: Any = None,
    buffer_usd: float = DEFAULT_BUFFER_USD,
) -> Dict[str, Any]:
    """Plan + optional live USDC→USD via convert_via_runner / convert_usdc_to_usd.

    dry_run=True → never converts; returns would_*.
    """
    bals = usd_usdc_from_live_state(live)
    # Prefer live exchange balances when executor present
    if executor is not None and not dry_run:
        try:
            ex = getattr(executor, "exchange", None) or executor
            if hasattr(ex, "get_account_balance"):
                bals["usd"] = _f(ex.get_account_balance("USD"), bals["usd"])
                bals["usdc"] = _f(ex.get_account_balance("USDC"), bals["usdc"])
        except Exception as e:
            logger.warning("live balance read failed: %s", e)

    park = regime_park_or_bear(snap)
    plan = plan_fund_for_shell(
        shell_usd=shell_usd,
        usd=bals["usd"],
        usdc=bals["usdc"],
        buffer_usd=buffer_usd,
        park_or_bear=park,
    )
    out: Dict[str, Any] = {
        "schema": "tryout_fund_from_usdc_v1",
        "ts": datetime.now(timezone.utc).isoformat(),
        "dry_run": bool(dry_run),
        "plan": plan.to_dict(),
        "ok": True,
        # hold = USD already covers shell (+buffer), including park-with-enough-USD
        "funded": plan.action == "hold",
        "converted": False,
        "trade": None,
        "error": None,
    }
    if plan.action == "hold":
        out["funded"] = True
        _persist(out)
        return out
    if plan.action == "blocked":
        out["ok"] = False
        out["funded"] = False
        out["error"] = plan.reason
        _persist(out)
        return out
    if plan.action != "unwind" or plan.unwind_usd < MIN_ACTION_USD:
        out["ok"] = False
        out["funded"] = False
        out["error"] = plan.reason or "no_unwind_planned"
        _persist(out)
        return out
    # unwind
    if dry_run:
        out["would_unwind_usd"] = plan.unwind_usd
        out["funded"] = False  # not actually funded yet
        out["ok"] = True
        _persist(out)
        return out

    try:
        from phase6.core.usdc_convert import convert_usdc_to_usd, convert_via_runner

        trade: Dict[str, Any]
        if runner is not None:
            trade = convert_via_runner(
                runner, direction="usdc_to_usd", amount=float(plan.unwind_usd)
            )
        else:
            ex = None
            if executor is not None:
                ex = getattr(executor, "exchange", None) or executor
            if ex is None:
                out["ok"] = False
                out["error"] = "no_exchange_for_convert"
                _persist(out)
                return out
            trade = convert_usdc_to_usd(ex, float(plan.unwind_usd))
        out["trade"] = trade
        ok = bool((trade or {}).get("success"))
        out["ok"] = ok
        out["converted"] = ok
        out["funded"] = ok
        if not ok:
            out["error"] = str((trade or {}).get("error") or "convert_failed")
        logger.info(
            "[TRYOUT-FUND] unwind $%.2f ok=%s reason=%s",
            plan.unwind_usd,
            ok,
            plan.reason,
        )
    except Exception as e:
        out["ok"] = False
        out["funded"] = False
        out["error"] = str(e)
        logger.exception("[TRYOUT-FUND] convert failed")
    _persist(out)
    return out


def _persist(out: Dict[str, Any]) -> None:
    try:
        _write_json(LATEST_PATH, out)
        _append_jsonl(EVENTS_PATH, out)
    except Exception as e:
        logger.warning("tryout_fund persist failed: %s", e)
