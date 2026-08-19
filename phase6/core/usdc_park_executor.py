"""
Live USDC park: sell alts → USD, convert deployable USD → USDC when regime/optimal says park.

Gated by config/trader_accounts.json → live_usdc_park.enabled per account_id.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from phase6.core.paths import PROJECT_ROOT
from phase6.core.trader_account_config import live_usdc_park_settings

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger(__name__)

PARK_STATE_DIR = PROJECT_ROOT / "data/state/usdc_park"


def park_signal_active(config_dict: Dict[str, Any]) -> bool:
    """True when analyst/regime overlay indicates USDC park (not merely low cap)."""
    gs = config_dict.get("global_settings") or {}
    if gs.get("strategy_mode") == "usdc_park":
        return True
    shadow = config_dict.get("_analyst_shadow") or {}
    if shadow.get("scenario_id") == "usdc_hold":
        return True
    rp = shadow.get("regime_policy") or {}
    ub = (rp.get("usdc_benchmark") or {})
    if ub.get("reason") == "optimal_strategy" and shadow.get("scenario_id") == "usdc_hold":
        return True
    if (
        gs.get("risk_free_preference") == "USDC"
        and float(gs.get("rebalance_cap_usd", 1) or 0) <= 0.0
    ):
        return True
    return False


def _pair_base(pair: str) -> str:
    return pair.split("-")[0].upper() if "-" in pair else pair.upper()


def _portfolio_snapshot(runner: "Phase6Runner") -> Dict[str, Any]:
    usd = float(runner.exchange.get_account_balance("USD") or 0.0)
    try:
        usdc = float(runner.exchange.get_account_balance("USDC") or 0.0)
    except Exception:
        usdc = 0.0
    crypto_usd = 0.0
    positions: Dict[str, float] = {}
    raw = runner.portfolio.get_enriched_positions() if getattr(runner, "portfolio", None) else {}
    if isinstance(raw, dict) and "positions" in raw:
        pos = raw.get("positions") or raw.get("value_usd") or {}
    else:
        pos = raw or {}
    for pair, data in (pos.items() if isinstance(pos, dict) else []):
        if not str(pair).endswith("-USD"):
            continue
        if isinstance(data, dict):
            val = float(data.get("value_usd", data.get("usd_value", 0)) or 0)
        else:
            val = float(data or 0)
        if val > 0:
            positions[pair] = val
            crypto_usd += val
    nav = usd + usdc + crypto_usd
    usdc_pct = (usdc / nav) if nav > 0 else 0.0
    return {
        "usd": usd,
        "usdc": usdc,
        "crypto_usd": crypto_usd,
        "nav": nav,
        "usdc_pct": usdc_pct,
        "positions": positions,
    }


def _save_park_state(account_id: str, payload: dict) -> None:
    PARK_STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in account_id)[:128]
    path = PARK_STATE_DIR / f"{safe}_latest.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def execute_usdc_park_cycle(
    runner: "Phase6Runner",
    park_cfg: Dict[str, Any],
    *,
    account_id: str,
    reason: str = "regime_usdc_park",
) -> Dict[str, Any]:
    """
    Sell basket alts, then market-buy USDC with USD above reserve.
    Returns summary dict for decision_context / logs.
    """
    snap = _portfolio_snapshot(runner)
    skip_above = float(park_cfg.get("skip_if_usdc_pct_above", 0.88))
    if snap["nav"] > 0 and snap["usdc_pct"] >= skip_above and snap["crypto_usd"] < float(
        park_cfg.get("min_sell_usd", 15)
    ):
        out = {
            "ok": True,
            "skipped": True,
            "reason": "already_parked",
            "usdc_pct": round(snap["usdc_pct"], 4),
            "nav": round(snap["nav"], 2),
        }
        _save_park_state(account_id, {**out, "ts": datetime.now(timezone.utc).isoformat()})
        logger.info("[USDC-PARK] skip — already %.1f%% USDC", snap["usdc_pct"] * 100)
        return out

    min_sell = float(park_cfg.get("min_sell_usd", 15.0))
    sells: List[Dict[str, Any]] = []
    basket = getattr(runner, "FIXED_UNIVERSE", []) or []

    with runner.stop_loss_coordinator.suspend_reattach_context(
        basket, snap.get("positions") or {}
    ):
        for pair in basket:
            usd_val = float((snap["positions"] or {}).get(pair, 0) or 0)
            if usd_val < min_sell:
                continue
            try:
                if getattr(runner, "use_platform_executor", False) and getattr(
                    runner, "trade_executor", None
                ):
                    result = runner.trade_executor.execute_sell(pair, usd_val)
                else:
                    result = runner.order_executor.execute_sell(pair, usd_val)
                sells.append(
                    {
                        "pair": pair,
                        "usd": usd_val,
                        "success": bool(result.get("success")),
                        "order_id": result.get("order_id"),
                        "error": result.get("error"),
                    }
                )
                if runner.mode == "live" and not result.get("success"):
                    logger.error("[USDC-PARK] sell failed %s — aborting park", pair)
                    break
            except Exception as e:
                logger.exception("[USDC-PARK] sell error %s", pair)
                sells.append({"pair": pair, "success": False, "error": str(e)})
                if runner.mode == "live":
                    break

        runner.portfolio.refresh()
        snap2 = _portfolio_snapshot(runner)
        reserve = float(park_cfg.get("min_usd_reserve_usd", 50.0))
        target_pct = float(park_cfg.get("target_usdc_pct", 0.92))
        nav = snap2["nav"]
        target_usdc = max(0.0, nav * target_pct - snap2["usdc"])
        deployable_usd = max(0.0, snap2["usd"] - reserve)
        convert_usd = min(deployable_usd, target_usdc)
        product = str(park_cfg.get("usdc_product_id", "USDC-USD"))

        convert_result: Optional[Dict[str, Any]] = None
        if convert_usd >= 1.0:
            try:
                if getattr(runner, "use_platform_executor", False) and getattr(
                    runner, "trade_executor", None
                ):
                    convert_result = runner.trade_executor.execute_buy(product, convert_usd)
                else:
                    convert_result = runner.order_executor.execute_buy(product, convert_usd)
            except Exception as e:
                convert_result = {"success": False, "error": str(e)}
        else:
            convert_result = {"success": True, "skipped": True, "reason": "no_usd_to_convert"}

    snap3 = _portfolio_snapshot(runner)
    out = {
        "ok": True,
        "skipped": False,
        "reason": reason,
        "account_id": account_id,
        "mode": runner.mode,
        "sells": sells,
        "convert_usd": round(convert_usd, 2),
        "convert": convert_result,
        "nav_before": round(snap["nav"], 2),
        "nav_after": round(snap3["nav"], 2),
        "usdc_pct_after": round(snap3["usdc_pct"], 4),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _save_park_state(account_id, out)
    logger.info(
        "[USDC-PARK] done sells=%s convert=$%s usdc_pct=%.1f%%",
        sum(1 for s in sells if s.get("success")),
        out.get("convert_usd"),
        snap3["usdc_pct"] * 100,
    )
    return out


# Daily rebalance entry: phase6.core.usdc_park_transitions.plan_usdc_park_for_daily_rebalance