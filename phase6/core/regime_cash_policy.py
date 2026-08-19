"""
REGIME-CASH: resolve active regime → cash budget + entry/exit gates; filter TradePlan BUYs.

All thresholds load from config/regime_cash_policy.json (optimizable). Real detector + signals only.
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from phase6.core.paths import PROJECT_ROOT

logger = logging.getLogger("phase6.regime_cash")

DEFAULT_POLICY_PATH = PROJECT_ROOT / "config/regime_cash_policy.json"
DEFAULT_STATUS_PATH = PROJECT_ROOT / "data/state/regime_cash_status.json"


@dataclass
class EntryDecision:
    pair: str
    allowed: bool
    reasons: List[str] = field(default_factory=list)
    sentiment: Optional[float] = None
    rsi: Optional[float] = None


@dataclass
class RegimeCashSnapshot:
    regime: str
    confidence: float
    btc_return_pct: Optional[float]
    strategy_mode: str
    allow_new_buys: bool
    target_max_util_pct: float
    rebalance_cap_usd: float
    min_cash_reserve_pct: float
    entry: Dict[str, Any]
    exit: Dict[str, Any]
    label: str
    detector: Dict[str, Any]
    knob_map_scenario: Optional[str] = None
    enforce: bool = True
    enabled: bool = True
    as_of: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def load_policy(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or DEFAULT_POLICY_PATH
    if not p.exists():
        return {"enabled": False, "enforce": False, "regimes": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def _merge_knob_map(regime: str, policy: Dict[str, Any], entry: Dict[str, Any]) -> Dict[str, Any]:
    """If knob_map says usdc_park or cap 0, force park semantics."""
    rel = policy.get("knob_map_path") or "config/regime_knob_map.json"
    km_path = PROJECT_ROOT / rel
    if not km_path.exists():
        return entry
    try:
        km = json.loads(km_path.read_text(encoding="utf-8"))
        rg = (km.get("regimes") or {}).get(regime) or {}
    except (json.JSONDecodeError, OSError):
        return entry
    out = deepcopy(entry)
    out["_knob_map_scenario"] = rg.get("scenario_id")
    mode = rg.get("strategy_mode")
    overlay = rg.get("live_overlay") or {}
    cap = overlay.get("global_settings.rebalance_cap_usd")
    if mode == "usdc_park" or (cap is not None and float(cap) <= 0):
        out["strategy_mode"] = "usdc_park"
        out["allow_new_buys"] = False
        out["rebalance_cap_usd"] = 0.0
    elif cap is not None:
        # Take the more conservative cap
        out["rebalance_cap_usd"] = min(float(out.get("rebalance_cap_usd") or cap), float(cap))
    return out


def resolve_regime_cash(
    *,
    policy: Optional[Dict[str, Any]] = None,
    detection: Optional[Dict[str, Any]] = None,
    policy_path: Optional[Path] = None,
) -> RegimeCashSnapshot:
    pol = policy if policy is not None else load_policy(policy_path)
    if detection is None:
        from phase6.research.regime_detector import detect_regime

        det_cfg = pol.get("detector") or {}
        detection = detect_regime(
            lookback_days=int(det_cfg.get("lookback_days") or 30),
            bull_return_pct=float(det_cfg.get("bull_return_pct", 15.0)),
            bear_return_pct=float(det_cfg.get("bear_return_pct", -10.0)),
            flat_abs_pct=float(det_cfg.get("flat_abs_pct", 8.0)),
            use_live_price=bool(det_cfg.get("use_live_price", True)),
        )
    regime = str(detection.get("regime") or "unknown")
    regimes = pol.get("regimes") or {}
    entry = deepcopy(regimes.get(regime) or regimes.get("unknown") or {})
    entry = _merge_knob_map(regime, pol, entry)

    return RegimeCashSnapshot(
        regime=regime,
        confidence=float(detection.get("confidence") or 0.0),
        btc_return_pct=detection.get("btc_return_pct"),
        strategy_mode=str(entry.get("strategy_mode") or "deploy"),
        allow_new_buys=bool(entry.get("allow_new_buys", True)),
        target_max_util_pct=float(entry.get("target_max_util_pct") or 0.8),
        rebalance_cap_usd=float(entry.get("rebalance_cap_usd") or 0.0),
        min_cash_reserve_pct=float(entry.get("min_cash_reserve_pct") or 0.1),
        entry=dict(entry.get("entry") or {}),
        exit=dict(entry.get("exit") or {}),
        label=str(entry.get("label") or regime),
        detector=dict(detection),
        knob_map_scenario=entry.get("_knob_map_scenario"),
        enforce=bool(pol.get("enforce", False)),
        enabled=bool(pol.get("enabled", False)),
        as_of=datetime.now(timezone.utc).isoformat(),
    )


def evaluate_buy_entry(
    pair: str,
    snap: RegimeCashSnapshot,
    *,
    sentiment: Optional[float],
    rsi: Optional[float],
    lockout_pairs: Optional[Set[str]] = None,
    is_new_pair: bool = False,
) -> EntryDecision:
    reasons: List[str] = []
    lockout_pairs = lockout_pairs or set()
    eg = snap.entry

    if not snap.allow_new_buys or snap.strategy_mode == "usdc_park":
        reasons.append(f"regime_cash_park mode={snap.strategy_mode} allow_new_buys={snap.allow_new_buys}")
        return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)

    if eg.get("require_lockout_clear", True) and pair in lockout_pairs:
        reasons.append("lockout_active")
        return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)

    min_s = float(eg.get("min_sentiment_new_pair" if is_new_pair else "min_sentiment") or -1.0)
    if sentiment is None:
        reasons.append("sentiment_missing")
        return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)
    if float(sentiment) < min_s:
        reasons.append(f"sentiment {sentiment:.3f} < min {min_s}")

    max_rsi = float(eg.get("max_rsi") or 100.0)
    if rsi is None:
        reasons.append("rsi_missing")
    elif float(rsi) > max_rsi:
        reasons.append(f"rsi {rsi:.1f} > max_buy {max_rsi}")

    allowed = len(reasons) == 0
    if allowed:
        reasons.append("entry_ok")
    return EntryDecision(pair=pair, allowed=allowed, reasons=reasons, sentiment=sentiment, rsi=rsi)


def prefer_exit(
    pair: str,
    snap: RegimeCashSnapshot,
    *,
    sentiment: Optional[float],
    rsi: Optional[float],
) -> EntryDecision:
    """Soft exit bias — caller may use for prioritising SELLs.

    Hard reasons: RSI overbought, sentiment weak.
    Soft: park_prefer_reduce (never auto-fire without operator).
    """
    reasons: List[str] = []
    xg = snap.exit
    overbought = float(xg.get("overbought_rsi") or 80.0)
    max_hold_s = float(xg.get("max_sentiment_hold") or -1.0)
    if rsi is not None and float(rsi) >= overbought:
        reasons.append(f"rsi_overbought {rsi:.1f}>={overbought}")
    if sentiment is not None and float(sentiment) <= max_hold_s:
        reasons.append(f"sentiment_weak {sentiment:.3f}<={max_hold_s}")
    if snap.strategy_mode == "usdc_park":
        reasons.append("park_prefer_reduce")
    allowed = len(reasons) > 0
    return EntryDecision(pair=pair, allowed=allowed, reasons=reasons or ["hold_ok"], sentiment=sentiment, rsi=rsi)


def hard_exit_reasons(reasons: Sequence[str]) -> List[str]:
    """Filter prefer_exit reasons to hard knobs only (never park_prefer_reduce)."""
    hard: List[str] = []
    for r in reasons or []:
        s = str(r)
        sl = s.lower()
        if "park_prefer_reduce" in sl:
            continue
        if "rsi_overbought" in sl or sl.startswith("rsi_overbought"):
            hard.append(s)
        elif "sentiment_weak" in sl or sl.startswith("sentiment_weak"):
            hard.append(s)
    return hard


def is_hard_exit(decision: EntryDecision) -> bool:
    return bool(hard_exit_reasons(decision.reasons))


def build_hard_exit_sell_actions(
    held_positions: Dict[str, float],
    snap: RegimeCashSnapshot,
    *,
    sentiment_scores: Optional[Dict[str, float]] = None,
    rsi_values: Optional[Dict[str, float]] = None,
    min_sell_usd: float = 25.0,
    max_pair_fraction: float = 1.0,
    existing_pairs: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Propose SELL actions for hard prefer_exit hits only.

    held_positions: pair → value_usd
    Does NOT include park_prefer_reduce.
    """
    sentiment_scores = sentiment_scores or {}
    rsi_values = rsi_values or {}
    existing_pairs = existing_pairs or set()
    actions: List[Dict[str, Any]] = []
    frac = max(0.0, min(1.0, float(max_pair_fraction)))
    for pair, raw_val in (held_positions or {}).items():
        try:
            val = float(raw_val or 0.0)
        except (TypeError, ValueError):
            continue
        if val < float(min_sell_usd):
            continue
        if pair in existing_pairs:
            continue
        dec = prefer_exit(
            pair,
            snap,
            sentiment=sentiment_scores.get(pair),
            rsi=rsi_values.get(pair),
        )
        hard = hard_exit_reasons(dec.reasons)
        if not hard:
            continue
        sell_usd = round(val * frac, 2)
        if sell_usd < float(min_sell_usd):
            continue
        actions.append(
            {
                "pair": pair,
                "action": "SELL",
                "side": "SELL",
                "usd": sell_usd,
                "usd_amount": sell_usd,
                "reason": "regime_hard_exit",
                "exit_class": "hard_exit",
                "exit_reasons": hard,
                "shadow_source": "prefer_exit_hard",
            }
        )
    return actions


def apply_hard_exit_to_plan(
    plan: Any,
    snap: RegimeCashSnapshot,
    held_positions: Dict[str, float],
    *,
    sentiment_scores: Optional[Dict[str, float]] = None,
    rsi_values: Optional[Dict[str, float]] = None,
    hard_cfg: Optional[Dict[str, Any]] = None,
    shadow_log_path: Optional[Path] = None,
) -> Any:
    """TG-02: attach hard-exit SELL proposals.

    Default shadow_only: log proposals, do not mutate live plan actions.
    live_apply=true (operator): merge SELLs into plan.
    """
    cfg = hard_cfg or {}
    if not cfg.get("enabled", False):
        return plan
    min_usd = float(cfg.get("min_sell_usd") or 25.0)
    max_frac = float(cfg.get("max_pair_fraction") or 1.0)
    shadow_only = bool(cfg.get("shadow_only", True))
    live_apply = bool(cfg.get("live_apply", False)) and not shadow_only

    existing = set()
    for a in list(getattr(plan, "actions", None) or []):
        if str(a.get("action") or a.get("side") or "").upper() == "SELL":
            p = a.get("pair")
            if p:
                existing.add(p)

    proposals = build_hard_exit_sell_actions(
        held_positions,
        snap,
        sentiment_scores=sentiment_scores,
        rsi_values=rsi_values,
        min_sell_usd=min_usd,
        max_pair_fraction=max_frac,
        existing_pairs=existing,
    )
    try:
        plan.regime_hard_exit_proposals = proposals  # type: ignore[attr-defined]
        plan.regime_hard_exit_shadow = not live_apply  # type: ignore[attr-defined]
    except Exception:
        pass

    payload = {
        "schema": "regime_hard_exit_shadow_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "regime": snap.regime,
        "strategy_mode": snap.strategy_mode,
        "shadow_only": not live_apply,
        "live_apply": live_apply,
        "operator_approve": bool(cfg.get("operator_approve", True)),
        "proposals": proposals,
        "n": len(proposals),
    }
    # Operator loop: never live_apply while operator_approve is on
    if bool(cfg.get("operator_approve", True)):
        live_apply = False
        payload["live_apply"] = False
        payload["shadow_only"] = True

    out = shadow_log_path or (PROJECT_ROOT / "data/state/regime_hard_exit_shadow.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[REGIME-HARD-EXIT] shadow write failed: %s", e)

    if proposals:
        logger.info(
            "[REGIME-HARD-EXIT] %s n=%s pairs=%s",
            "LIVE_APPLY" if live_apply else "SHADOW+NOTIFY",
            len(proposals),
            [p.get("pair") for p in proposals],
        )
        # Decision-loop notify (Telegram + pending inbox); never auto-sell
        if bool(cfg.get("notify_telegram", True)) or bool(cfg.get("operator_approve", True)):
            try:
                from phase6.scripts.hard_exit_controls import maybe_notify_hard_exits

                nr = maybe_notify_hard_exits(
                    payload,
                    notify=bool(cfg.get("notify_telegram", True)),
                    dedupe_hours=float(cfg.get("notify_dedupe_hours") or 12.0),
                )
                payload["notify_result"] = nr
                try:
                    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                except Exception:
                    pass
            except Exception as e:
                logger.warning("[REGIME-HARD-EXIT] notify skipped: %s", e)

    if live_apply and proposals and getattr(plan, "actions", None) is not None:
        plan.actions = list(plan.actions) + proposals
    return plan


def filter_trade_plan_regime_cash(
    plan: Any,
    snap: RegimeCashSnapshot,
    *,
    sentiment_scores: Optional[Dict[str, float]] = None,
    rsi_values: Optional[Dict[str, float]] = None,
    lockout_pairs: Optional[Set[str]] = None,
    held_pairs: Optional[Set[str]] = None,
    enforce: Optional[bool] = None,
) -> Any:
    """
    Drop BUY actions that fail regime cash entry gates.
    SELLs always kept. Mutates plan.actions when present.
    """
    if not getattr(plan, "actions", None):
        return plan
    do_enforce = snap.enforce if enforce is None else bool(enforce)
    if not snap.enabled:
        return plan

    sentiment_scores = sentiment_scores or {}
    rsi_values = rsi_values or {}
    lockout_pairs = lockout_pairs or set()
    held_pairs = held_pairs or set()

    kept: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    for a in list(plan.actions):
        action = str(a.get("action") or a.get("side") or "").upper()
        pair = a.get("pair")
        if action != "BUY" or not pair:
            kept.append(a)
            continue
        dec = evaluate_buy_entry(
            pair,
            snap,
            sentiment=sentiment_scores.get(pair),
            rsi=rsi_values.get(pair),
            lockout_pairs=lockout_pairs,
            is_new_pair=pair not in held_pairs,
        )
        if dec.allowed:
            kept.append(a)
        else:
            blocked.append({"pair": pair, "usd": a.get("usd") or a.get("usd_amount"), "reasons": dec.reasons})
            if not do_enforce:
                kept.append(a)  # shadow: keep but log
            logger.info(
                "[REGIME-CASH] %s BUY %s reasons=%s enforce=%s",
                "BLOCK" if do_enforce else "WOULD_BLOCK",
                pair,
                dec.reasons,
                do_enforce,
            )

    if do_enforce:
        plan.actions = kept
    # attach audit for decision context
    try:
        plan.regime_cash_blocked = blocked  # type: ignore[attr-defined]
        plan.regime_cash_regime = snap.regime  # type: ignore[attr-defined]
    except Exception:
        pass
    return plan


def persist_status(snap: RegimeCashSnapshot, blocked: Optional[Sequence[Dict[str, Any]]] = None, path: Optional[Path] = None) -> Path:
    pol = load_policy()
    out_path = path or PROJECT_ROOT / (pol.get("status_path") or "data/state/regime_cash_status.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **snap.to_dict(),
        "blocked_buys": list(blocked or []),
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def apply_to_runner_plan(
    runner: Any,
    plan: Any,
    *,
    sentiment_scores: Optional[Dict[str, float]] = None,
    rsi_values: Optional[Dict[str, float]] = None,
) -> Any:
    """Convenience for rebalance_coordinator: resolve, filter, persist."""
    pol = load_policy()
    if not pol.get("enabled"):
        return plan
    snap = resolve_regime_cash(policy=pol)
    # Live cash budget: clamp runner rebalance_cap from snapshot (park → 0; cautious flat → small cap)
    try:
        cfg = getattr(runner, "config_dict", None)
        if isinstance(cfg, dict) and snap.enforce:
            gs = cfg.setdefault("global_settings", {})
            prev = gs.get("rebalance_cap_usd")
            if snap.strategy_mode == "usdc_park" or not snap.allow_new_buys:
                gs["rebalance_cap_usd"] = 0.0
            elif snap.rebalance_cap_usd is not None and float(snap.rebalance_cap_usd) >= 0:
                # Take the tighter of policy snap vs any existing runner default
                try:
                    prev_f = float(prev) if prev is not None else float("inf")
                except (TypeError, ValueError):
                    prev_f = float("inf")
                gs["rebalance_cap_usd"] = min(prev_f, float(snap.rebalance_cap_usd))
            logger = __import__("logging").getLogger("phase6.regime_cash")
            logger.info(
                "[REGIME-CASH] cap apply regime=%s mode=%s cap=%s (was %s)",
                snap.regime,
                snap.strategy_mode,
                gs.get("rebalance_cap_usd"),
                prev,
            )
    except Exception:
        pass
    lockout: Set[str] = set()
    try:
        from phase6.core.runner_capital_events import get_deployment_cooldown_pairs

        lockout = set(get_deployment_cooldown_pairs(runner) or [])
    except Exception:
        pass
    held: Set[str] = set()
    try:
        pos = getattr(runner, "current_positions", None) or {}
        held = {k for k, v in pos.items() if float(v if not isinstance(v, dict) else v.get("value_usd") or 0) > 1.0}
    except Exception:
        pass
    rsi = rsi_values if rsi_values is not None else getattr(runner, "rsi_values", {}) or {}
    plan = filter_trade_plan_regime_cash(
        plan,
        snap,
        sentiment_scores=sentiment_scores,
        rsi_values=rsi,
        lockout_pairs=lockout,
        held_pairs=held,
    )
    # TG-02: hard prefer_exit → shadow (default) or live SELL legs
    try:
        hard_cfg = (pol.get("hard_exit") or {}) if isinstance(pol, dict) else {}
        held_vals: Dict[str, float] = {}
        pos = getattr(runner, "current_positions", None) or {}
        for k, v in pos.items():
            try:
                if isinstance(v, dict):
                    held_vals[str(k)] = float(v.get("value_usd") or v.get("amount") or 0.0)
                else:
                    held_vals[str(k)] = float(v or 0.0)
            except (TypeError, ValueError):
                continue
        # Prefer portfolio enriched values when available
        try:
            port = getattr(runner, "portfolio", None)
            if port and hasattr(port, "get_enriched_positions"):
                enr = port.get_enriched_positions() or {}
                plist = enr.get("positions") or enr.get("trading_positions") or []
                if isinstance(plist, list):
                    for p in plist:
                        pair = str(p.get("pair") or "")
                        if pair and pair not in ("USD", "USDC"):
                            held_vals[pair] = float(p.get("value_usd") or held_vals.get(pair) or 0.0)
        except Exception:
            pass
        plan = apply_hard_exit_to_plan(
            plan,
            snap,
            held_vals,
            sentiment_scores=sentiment_scores,
            rsi_values=rsi,
            hard_cfg=hard_cfg,
        )
    except Exception as e:
        logger.warning("[REGIME-HARD-EXIT] apply skipped: %s", e)
    # TG-04: shadow TP / trail evaluator (config knobs; no live orders in shadow)
    try:
        from phase6.core.shadow_tp import apply_shadow_tp_from_runner

        st = apply_shadow_tp_from_runner(runner)
        try:
            plan.shadow_tp_status = st  # type: ignore[attr-defined]
        except Exception:
            pass
    except Exception as e:
        logger.warning("[SHADOW-TP] apply skipped: %s", e)
    blocked = getattr(plan, "regime_cash_blocked", []) or []
    persist_status(snap, blocked=blocked)
    return plan
