"""
Park package coordinator — USDC (A) + PAXG Hold (B) + REGIME-CASH (C).

Evaluates coordinated sequences and writes status each cycle.
Never auto-arms PAXG. Optional USDC toggle coordination is gated off by default.

Auto trim B on deploy (when execution.auto_trim_b_on_deploy=true):
  Edge-triggered park→deploy only — sells armed PAXG via disarm_preserve_hold.
  Does not dump gold while already sitting in multi-day bull/deploy.
  Skips Keep-Hold recommendations.

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
AUTO_TRIM_STATE_PATH = STATE_DIR / "park_auto_trim_state.json"
TRIM_ACTIONS = frozenset(
    {
        "TRIM_DEFAULT_TO_A",
        "TRIM_DEFAULT",
        "TRIM_TO_A",
        "REPAIR_E1_OR_DISARM",  # if still armed after repair path fails — operator-safe flat
    }
)
KEEP_HOLD_MARKERS = ("KEEP_HOLD",)

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
        rec = str(shadow_b.get("recommended_action") or "").strip().upper()
        keep_hold = any(m in rec for m in KEEP_HOLD_MARKERS)
        if regime.get("deploy_open") and auto_trim and not keep_hold:
            step(
                "auto_trim_B_to_A",
                "TRIM_DEFAULT_TO_A — disarm+sell PAXG→A on park→deploy edge (auto)",
                auto=True,
                shadow=shadow_b,
                edge_triggered=True,
                note="Fires only on park→deploy transition; see park_auto_trim_state.json",
            )
        elif regime.get("deploy_open") and auto_trim and keep_hold:
            step(
                "keep_hold_b_on_deploy",
                "KEEP_HOLD — auto trim skipped",
                auto=True,
                shadow=shadow_b,
            )
        elif regime.get("deploy_open") and not auto_trim:
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


def _load_auto_trim_state() -> Dict[str, Any]:
    if not AUTO_TRIM_STATE_PATH.exists():
        return {}
    try:
        return json.loads(AUTO_TRIM_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_auto_trim_state(st: Dict[str, Any]) -> None:
    AUTO_TRIM_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTO_TRIM_STATE_PATH.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")


def _posture_key(regime: Dict[str, Any]) -> str:
    if regime.get("park_signal"):
        return "park"
    if regime.get("deploy_open"):
        return "deploy"
    return "other"


def should_execute_auto_trim_b(plan: Dict[str, Any], pkg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gate for live B trim. Edge-triggered: only when posture moves park → deploy
    while B is armed, package on, flag on, and not Keep-Hold.
    """
    out: Dict[str, Any] = {"execute": False, "reason": "init"}
    if not plan.get("package_enabled"):
        out["reason"] = "package_disabled"
        return out
    execution = pkg.get("execution") or {}
    if not execution.get("auto_trim_b_on_deploy"):
        out["reason"] = "auto_trim_b_on_deploy=false"
        return out
    b = plan.get("bucket_b") or {}
    preserve = b.get("preserve") or {}
    if not preserve.get("armed"):
        out["reason"] = "b_not_armed"
        return out
    regime = (plan.get("bucket_c") or {}).get("regime") or {}
    if regime.get("park_signal"):
        out["reason"] = "park_signal_active"
        return out
    if not regime.get("deploy_open"):
        out["reason"] = "deploy_not_open"
        return out
    rec = str((b.get("shadow") or {}).get("recommended_action") or "").upper()
    if any(m in rec for m in KEEP_HOLD_MARKERS):
        out["reason"] = "keep_hold"
        return out

    st = _load_auto_trim_state()
    prev = str(st.get("last_posture") or "unknown")
    cur = _posture_key(regime)
    out["prev_posture"] = prev
    out["cur_posture"] = cur
    edge = prev == "park" and cur == "deploy"
    if not edge:
        out["reason"] = f"no_park_to_deploy_edge (prev={prev}, cur={cur})"
        return out
    edge_id = f"park->deploy@{st.get('last_park_seen_at')}"
    if st.get("last_trim_ok") and st.get("last_trim_edge_id") == edge_id:
        out["reason"] = "already_trimmed_this_edge"
        return out
    out["execute"] = True
    out["reason"] = "park_to_deploy_edge"
    return out


def maybe_execute_auto_trim_b(
    runner: "Phase6Runner",
    plan: Dict[str, Any],
    pkg: Dict[str, Any],
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Live disarm+sell PAXG when should_execute_auto_trim_b says go."""
    gate = should_execute_auto_trim_b(plan, pkg)
    result: Dict[str, Any] = {
        "attempted": False,
        "ok": False,
        "gate": gate,
        "orders": False,
        "dry_run": dry_run,
    }
    # Always refresh posture memory so we can detect the next park→deploy edge
    regime = (plan.get("bucket_c") or {}).get("regime") or {}
    st = _load_auto_trim_state()
    cur = _posture_key(regime)
    if cur == "park":
        st["last_park_seen_at"] = _now()
    st["last_posture"] = cur
    st["updated_at"] = _now()
    if not gate.get("execute"):
        _save_auto_trim_state(st)
        result["reason"] = gate.get("reason")
        return result

    result["attempted"] = True
    if dry_run:
        result["ok"] = True
        result["reason"] = "dry_run_would_disarm_sell"
        st["last_trim_preview"] = _now()
        _save_auto_trim_state(st)
        return result

    exchange = getattr(runner, "exchange", None)
    if exchange is None or getattr(exchange, "shadow_mode", False):
        result["reason"] = "no_live_exchange"
        _save_auto_trim_state(st)
        return result

    full_config = getattr(runner, "config_dict", None) or {}
    try:
        from phase6.core.preserve_hold import disarm_preserve_hold

        disarm_out = disarm_preserve_hold(exchange, full_config, sell=True)
        result["orders"] = True
        result["ok"] = bool(disarm_out.get("ok"))
        result["disarm"] = {
            "ok": disarm_out.get("ok"),
            "steps": (disarm_out.get("steps") or [])[:12],
        }
        result["reason"] = "disarmed" if result["ok"] else "disarm_failed"
        st["last_trim_at"] = _now()
        st["last_trim_ok"] = result["ok"]
        st["last_trim_edge_id"] = f"park->deploy@{st.get('last_park_seen_at')}"
        st["last_trim_reason"] = result["reason"]
        logger.info(
            "[PARK-PACKAGE] auto_trim_B_to_A ok=%s reason=%s",
            result["ok"],
            result["reason"],
        )
    except Exception as exc:
        result["reason"] = f"disarm_exception:{exc}"
        st["last_trim_at"] = _now()
        st["last_trim_ok"] = False
        st["last_error"] = str(exc)
        logger.warning("[PARK-PACKAGE] auto_trim_B failed: %s", exc)
    _save_auto_trim_state(st)
    return result


def maybe_park_package_cycle(runner: "Phase6Runner") -> Dict[str, Any]:
    """
    Runner hook: evaluate + write status each cycle when write_status_each_cycle.
    Never arms B. When auto_trim_b_on_deploy=true, may disarm+sell B on park→deploy edge.
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

        trim_out = maybe_execute_auto_trim_b(runner, plan, pkg, dry_run=False)
        plan["auto_trim_execution"] = {
            k: trim_out.get(k)
            for k in ("attempted", "ok", "reason", "orders", "gate")
            if k in trim_out or True
        }
        # rewrite status with execution result
        try:
            write_park_package_status(plan)
        except Exception:
            pass

        if trim_out.get("attempted"):
            logger.info(
                "[PARK-PACKAGE] auto_trim attempted ok=%s reason=%s",
                trim_out.get("ok"),
                trim_out.get("reason"),
            )
        else:
            logger.debug(
                "[PARK-PACKAGE] profile=%s enabled=%s auto_trim=%s",
                plan.get("profile"),
                plan.get("package_enabled"),
                (trim_out.get("gate") or {}).get("reason"),
            )
        return plan
    except Exception as exc:
        logger.warning("[PARK-PACKAGE] cycle failed: %s", exc)
        return {"error": str(exc), "orders": False}
