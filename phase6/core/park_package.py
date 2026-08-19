"""
Park package coordinator — USDC (A) + PAXG Hold (B) + REGIME-CASH (C).

Evaluates coordinated sequences and writes status. Does not place orders.
Never auto-arms PAXG. Optional USDC toggle coordination is gated off by default.

Spec: docs/features/PARK_USDC_PAXG_PACKAGE_SPEC.md
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from phase6.core.paths import PROJECT_ROOT, STATE_DIR
from phase6.core.trader_account_config import (
    live_usdc_park_settings,
    resolve_account_config,
)

if TYPE_CHECKING:
    from phase6.core.phase6_runner import Phase6Runner

logger = logging.getLogger("phase6.park_package")

PARK_PACKAGE_PATH = PROJECT_ROOT / "config/park_package.json"
DEFAULT_STATUS_PATH = STATE_DIR / "park_package_status.json"

PROFILES = frozenset({"off", "a_only", "a_plus_b_micro", "a_plus_b_full_eligible"})
PROFILES_WANT_A = frozenset({"a_only", "a_plus_b_micro", "a_plus_b_full_eligible"})
PROFILES_WANT_B = frozenset({"a_plus_b_micro", "a_plus_b_full_eligible"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_book_park_package() -> Dict[str, Any]:
    if not PARK_PACKAGE_PATH.exists():
        return {
            "schema_version": 1,
            "enabled": False,
            "profile": "off",
            "buckets": {
                "A": {"micro_usd": 75.0, "target_usdc_pct": 0.92, "min_usd_reserve_usd": 50.0},
                "B": {"micro_usd": 75.0, "require_explicit_arm": True, "derisk_enabled": False},
            },
            "execution": {
                "allow_coordinate_toggles": False,
                "auto_arm_b": False,
                "auto_trim_b_on_deploy": False,
                "write_status_each_cycle": True,
            },
        }
    try:
        return json.loads(PARK_PACKAGE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[PARK-PACKAGE] config unreadable: %s", exc)
        return {"enabled": False, "profile": "off", "buckets": {}, "execution": {}}


def load_park_package_config(account_id: Optional[str] = None) -> Dict[str, Any]:
    """Merge book park_package.json with optional per-account overlay."""
    book = load_book_park_package()
    if not account_id:
        cfg = deepcopy(book)
        cfg["account_id"] = None
        return cfg
    acct = resolve_account_config(account_id)
    overlay = acct.get("park_package") or {}
    # Also allow legacy: if only live_usdc / preserve elsewhere, still merge park_package key only
    merged = _deep_merge(book, overlay if isinstance(overlay, dict) else {})
    merged["account_id"] = account_id
    return merged


def _normalize_profile(raw: Any) -> str:
    p = str(raw or "off").strip().lower()
    if p not in PROFILES:
        return "off"
    return p


def _regime_snapshot(full_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rc_path = STATE_DIR / "regime_cash_status.json"
    rc: Dict[str, Any] = {}
    if rc_path.exists():
        try:
            rc = json.loads(rc_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            rc = {}
    gs = (full_config or {}).get("global_settings") or {}
    strategy = rc.get("strategy_mode") or gs.get("strategy_mode")
    cap = gs.get("rebalance_cap_usd")
    if cap is None:
        cap = rc.get("rebalance_cap_usd")
    try:
        cap_f = float(cap or 0)
    except (TypeError, ValueError):
        cap_f = 0.0
    park_signal = False
    try:
        from phase6.core.usdc_park_executor import park_signal_active

        park_signal = park_signal_active(full_config or {"global_settings": gs})
    except Exception:
        park_signal = str(strategy or "").lower() in ("usdc_park", "park")
    deploy_open = False
    try:
        from phase6.core.usdc_park_transitions import deploy_signal_active

        deploy_open = deploy_signal_active(full_config or {"global_settings": gs})
    except Exception:
        deploy_open = (not park_signal) and cap_f > 0
    return {
        "regime": rc.get("regime"),
        "strategy_mode": strategy,
        "rebalance_cap_usd": cap_f,
        "park_signal": bool(park_signal),
        "deploy_open": bool(deploy_open),
        "allow_new_buys": rc.get("allow_new_buys"),
        "label": rc.get("label"),
    }


def _preserve_snapshot(full_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        from phase6.core.preserve_hold import load_preserve_config, load_state

        cfg = load_preserve_config(full_config)
        st = load_state()
    except Exception as exc:
        return {
            "enabled": False,
            "armed": False,
            "micro": False,
            "error": str(exc),
        }
    return {
        "enabled": bool(cfg.get("enabled")),
        "armed": bool(st.get("armed") or cfg.get("armed")),
        "micro": bool(st.get("soak_micro") or cfg.get("micro_live")),
        "micro_usd": float(cfg.get("micro_usd") or 75.0),
        "asset": cfg.get("asset") or "PAXG-USD",
        "derisk_enabled": bool((cfg.get("derisk") or {}).get("enabled")),
        "allow_preserve_with_crypto_util": bool(cfg.get("allow_preserve_with_crypto_util")),
        "venue_probe_result": cfg.get("venue_probe_result"),
    }


def _shadow_b_recommendation() -> Dict[str, Any]:
    path = STATE_DIR / "park_ballast_decision_latest.json"
    if not path.exists():
        return {}
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return {
            "recommended_action": d.get("recommended_action") or d.get("recommended"),
            "b_target": d.get("b_target"),
            "as_of": d.get("as_of"),
            "orders": d.get("orders"),
        }
    except (json.JSONDecodeError, OSError):
        return {}


def _crypto_util_est() -> Optional[float]:
    try:
        from phase6.core.park_ballast_shadow import crypto_util_pct_from_live

        return crypto_util_pct_from_live()
    except Exception:
        live = STATE_DIR / "phase6_live_state.json"
        if not live.exists():
            return None
        try:
            st = json.loads(live.read_text(encoding="utf-8"))
            total = float(st.get("total_usd") or 0)
            ab = st.get("account_balances") or {}
            cash = float(ab.get("USD", 0) or 0) + float(ab.get("USDC", 0) or 0)
            # rough: non-cash / total; gold may be in holdings
            if total <= 0:
                return None
            return max(0.0, min(1.0, (total - cash) / total))
        except Exception:
            return None


def _earmark_b_usd(pkg: Dict[str, Any], profile: str, b_snap: Dict[str, Any]) -> float:
    if profile not in PROFILES_WANT_B:
        return 0.0
    b = (pkg.get("buckets") or {}).get("B") or {}
    micro = float(b.get("micro_usd") or b_snap.get("micro_usd") or 75.0)
    if b_snap.get("armed") and not b_snap.get("micro"):
        # already full-ish — earmark 0 additional for plan simplicity
        return 0.0
    if b_snap.get("armed"):
        return 0.0
    return micro


def evaluate_park_package(
    *,
    account_id: Optional[str] = None,
    full_config: Optional[Dict[str, Any]] = None,
    runner: Optional["Phase6Runner"] = None,
) -> Dict[str, Any]:
    """
    Build coordinated park package plan. No orders.
    """
    if runner is not None:
        account_id = account_id or getattr(runner, "account_id", None) or "default"
        full_config = full_config or getattr(runner, "config_dict", None) or {}

    pkg = load_park_package_config(account_id)
    profile = _normalize_profile(pkg.get("profile"))
    package_enabled = bool(pkg.get("enabled"))
    execution = pkg.get("execution") or {}
    auto_arm_b = bool(execution.get("auto_arm_b"))  # must remain false in v1
    auto_trim = bool(execution.get("auto_trim_b_on_deploy"))
    allow_coord = bool(execution.get("allow_coordinate_toggles"))

    aid = account_id or "default"
    usdc = live_usdc_park_settings(aid)
    usdc_on = bool(usdc.get("enabled"))
    regime = _regime_snapshot(full_config)
    b_snap = _preserve_snapshot(full_config)
    shadow_b = _shadow_b_recommendation()
    util = _crypto_util_est()
    earmark_b = _earmark_b_usd(pkg, profile, b_snap)
    a_bucket = (pkg.get("buckets") or {}).get("A") or {}
    min_reserve = float(a_bucket.get("min_usd_reserve_usd") or usdc.get("min_usd_reserve_usd") or 50.0)
    target_usdc = float(a_bucket.get("target_usdc_pct") or usdc.get("target_usdc_pct") or 0.92)

    warnings: List[str] = []
    if profile in PROFILES_WANT_A and not usdc_on:
        warnings.append(
            "profile_wants_A_usdc_but_live_usdc_park.enabled=false — turn on via manage_trader_account or accept USD-only A"
        )
    if profile in PROFILES_WANT_B and not package_enabled:
        warnings.append("profile includes B but park_package.enabled=false — coordination/status only if you enable package flag")
    if b_snap.get("derisk_enabled"):
        warnings.append("preserve derisk.enabled=true — doctrine forbids DeRisk ladder; turn off")
    if auto_arm_b:
        warnings.append("execution.auto_arm_b=true is unsupported/forbidden in v1 — ignored")
    if profile == "off" and (usdc_on or (b_snap.get("armed") and package_enabled)):
        warnings.append("profile=off but USDC and/or B sleeve active — layers run independently of package")

    # --- sequence steps ---
    sequence: List[Dict[str, Any]] = []

    def step(sid: str, action: str, *, auto: bool, blocked_reason: Optional[str] = None, **extra: Any) -> None:
        sequence.append(
            {
                "id": sid,
                "action": action,
                "auto": auto,
                "blocked_reason": blocked_reason,
                **extra,
            }
        )

    # C
    if regime.get("park_signal") or not regime.get("deploy_open"):
        step(
            "ensure_C_no_new_risk",
            "REGIME-CASH controls C (park/stand-down or capped deploy)",
            auto=True,
            regime=regime.get("regime"),
            cap=regime.get("rebalance_cap_usd"),
        )
    else:
        step(
            "C_deploy_gates_open",
            "Deploy gates open — C may buy under caps after A/B sequence",
            auto=True,
            cap=regime.get("rebalance_cap_usd"),
        )

    # A
    want_a = profile in PROFILES_WANT_A
    if want_a and usdc_on and regime.get("park_signal"):
        step(
            "run_A_usdc_park_if_eligible",
            "live_usdc_park executor parks alts → USDC",
            auto=True,
            executor="usdc_park_transitions.plan_usdc_park_for_daily_rebalance",
            target_usdc_pct=target_usdc,
            min_usd_reserve_usd=min_reserve,
            cash_earmarked_b_usd=earmark_b,
        )
    elif want_a and usdc_on and regime.get("deploy_open"):
        step(
            "run_A_usdc_redeploy_unwind",
            "USDC unwind then ARCH-4",
            auto=True,
            executor="usdc_park_transitions",
        )
    elif want_a and not usdc_on:
        step(
            "run_A_usdc_park_if_eligible",
            "A wants USDC but toggle off — USD stand-down only",
            auto=False,
            blocked_reason="live_usdc_park.enabled=false",
        )
    else:
        step(
            "A_regime_cash_usd",
            "Profile off or A not requested — REGIME-CASH USD/cash park only",
            auto=True,
        )

    # B
    want_b = profile in PROFILES_WANT_B
    parked_enough = bool(regime.get("park_signal")) or (util is not None and util < 0.30)
    b_cfg = (pkg.get("buckets") or {}).get("B") or {}
    require_parked = bool(b_cfg.get("require_crypto_parked_before_arm", True))
    allow_dual = bool(b_cfg.get("allow_preserve_with_crypto_util", False))

    if b_snap.get("armed"):
        if regime.get("deploy_open") and not auto_trim:
            step(
                "shadow_or_manual_trim_B_to_A",
                shadow_b.get("recommended_action") or "TRIM_DEFAULT_TO_A (manual/shadow)",
                auto=False,
                blocked_reason="auto_trim_b_on_deploy=false",
                shadow=shadow_b,
            )
        elif regime.get("park_signal"):
            step(
                "hold_B_in_park",
                "HOLD_B_IN_PARK — maintain sleeve + E1",
                auto=True,
                micro=b_snap.get("micro"),
            )
        else:
            step("hold_B_observe", "HOLD_OBSERVE", auto=True, shadow=shadow_b)
    elif want_b:
        arm_ok = True
        blocked = None
        if b_cfg.get("require_explicit_arm", True) or not auto_arm_b:
            arm_ok = False
            blocked = "require_explicit_arm — run arm_preserve_hold CLI"
        if require_parked and not parked_enough:
            arm_ok = False
            blocked = (blocked or "") + "; crypto not parked/low-util enough"
        if not allow_dual and util is not None and util >= 0.45:
            arm_ok = False
            blocked = (blocked or "") + f"; crypto util {util:.0%} high for dual stack"
        step(
            "offer_B_only_if_profile_and_operator",
            "OFFER_ARM_MICRO" if want_b else "STAY_A_ONLY",
            auto=False,
            blocked_reason=blocked,
            arm_allowed=False,  # v1 never auto
            would_offer=want_b and parked_enough,
            earmark_usd=earmark_b,
        )
        if not arm_ok:
            warnings.append(f"B arm blocked: {blocked}")
    else:
        step("B_not_in_profile", "STAY_A_ONLY for ballast", auto=True)

    # Double-spend / consistency
    double_spend_ok = True
    if earmark_b > 0 and min_reserve + earmark_b > 1e9:  # nonsense guard
        double_spend_ok = False
    # Logical: earmark must sit inside A reserve planning
    cash_plan = {
        "min_usd_reserve_usd": min_reserve,
        "cash_earmarked_b_usd": earmark_b,
        "a_target_usdc_pct": target_usdc,
        "rule": "B funds from A only; never raise C caps",
        "double_spend_ok": double_spend_ok,
    }

    recommended_a = "none"
    if want_a and not usdc_on:
        recommended_a = "enable_live_usdc_park_toggle"
    elif want_a and usdc_on and regime.get("park_signal"):
        recommended_a = "execute_or_await_usdc_park"
    elif want_a and usdc_on and regime.get("deploy_open"):
        recommended_a = "usdc_redeploy_unwind"

    recommended_b = "none"
    if want_b and not b_snap.get("armed"):
        recommended_b = "operator_arm_micro_when_parked"
    elif b_snap.get("armed") and regime.get("deploy_open"):
        recommended_b = shadow_b.get("recommended_action") or "trim_default_manual"

    plan: Dict[str, Any] = {
        "schema_version": 1,
        "as_of": _now(),
        "method": "park_package_v1",
        "spec_doc": "docs/features/PARK_USDC_PAXG_PACKAGE_SPEC.md",
        "orders": False,
        "package_enabled": package_enabled,
        "profile": profile,
        "account_id": aid,
        "research_usdc_apy_note": pkg.get("research_usdc_apy_note"),
        "bucket_a": {
            "prefer_asset": a_bucket.get("prefer_asset") or "USDC",
            "live_usdc_park_enabled": usdc_on,
            "park_signal": regime.get("park_signal"),
            "deploy_open": regime.get("deploy_open"),
            "recommended_a_action": recommended_a,
            "target_usdc_pct": target_usdc,
            "settings": {
                k: usdc.get(k)
                for k in (
                    "target_usdc_pct",
                    "min_usd_reserve_usd",
                    "usdc_product_id",
                    "redeploy_target_usdc_pct",
                )
            },
        },
        "bucket_b": {
            "preserve": b_snap,
            "shadow": shadow_b,
            "recommended_b_action": recommended_b,
            "auto_arm": False,
            "auto_trim_on_deploy": auto_trim,
            "profile_includes_b": want_b,
        },
        "bucket_c": {
            "regime": regime,
            "crypto_util_est": util,
            "controlled_by": "REGIME-CASH",
        },
        "cash_plan": cash_plan,
        "sequence": sequence,
        "consistency_warnings": warnings,
        "execution_flags": {
            "allow_coordinate_toggles": allow_coord,
            "auto_arm_b": False,
            "auto_trim_b_on_deploy": auto_trim,
        },
        "coordinate_toggle_suggestion": (
            {"live_usdc_park.enabled": True}
            if (package_enabled and allow_coord and want_a and not usdc_on)
            else None
        ),
    }
    return plan


def write_park_package_status(plan: Dict[str, Any], path: Optional[Path] = None) -> Path:
    status_path = path or DEFAULT_STATUS_PATH
    # allow override from config
    try:
        book = load_book_park_package()
        rel = book.get("status_path")
        if rel and path is None:
            status_path = PROJECT_ROOT / rel if not str(rel).startswith("/") else Path(rel)
    except Exception:
        pass
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return status_path


def evaluate_and_write_status(
    *,
    account_id: Optional[str] = None,
    full_config: Optional[Dict[str, Any]] = None,
    runner: Optional["Phase6Runner"] = None,
) -> Dict[str, Any]:
    plan = evaluate_park_package(
        account_id=account_id, full_config=full_config, runner=runner
    )
    write_park_package_status(plan)
    return plan


def maybe_park_package_cycle(runner: "Phase6Runner") -> Dict[str, Any]:
    """
    Runner hook: evaluate + write status each cycle when write_status_each_cycle.
    Never places orders. Never arms B. Toggle coordinate only if explicitly allowed.
    """
    try:
        pkg = load_park_package_config(getattr(runner, "account_id", None))
        execution = pkg.get("execution") or {}
        if not execution.get("write_status_each_cycle", True) and not pkg.get("enabled"):
            return {"skipped": True, "reason": "status_writes_disabled"}

        plan = evaluate_and_write_status(runner=runner)

        # Future: allow_coordinate_toggles — still default false
        if (
            plan.get("package_enabled")
            and (pkg.get("execution") or {}).get("allow_coordinate_toggles")
            and plan.get("coordinate_toggle_suggestion")
        ):
            logger.info(
                "[PARK-PACKAGE] coordinate suggestion (not applied unless code path extended): %s",
                plan.get("coordinate_toggle_suggestion"),
            )

        logger.debug(
            "[PARK-PACKAGE] profile=%s enabled=%s warnings=%d",
            plan.get("profile"),
            plan.get("package_enabled"),
            len(plan.get("consistency_warnings") or []),
        )
        return plan
    except Exception as exc:
        logger.warning("[PARK-PACKAGE] cycle failed: %s", exc)
        return {"error": str(exc), "orders": False}
