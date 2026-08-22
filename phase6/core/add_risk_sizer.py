"""
Factor-based add sizing for existing stacks (P6-ADD-RISK-SIZER-20260821).

Purpose-led bounds for BUY *adds* into bags we already hold:
  risk_budget = min(open_upnl * k_profit, equity * h_add, book_heat_left)
  max_add     = risk_budget / stop_gap   (then exposure room, free cash, rebalance cap)
  optional gap_scale between min_gap and gap_full

Does NOT force sells on oversized open bags — only clips/skips future adds.
New entries (no meaningful bag) pass through unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Defaults when regime table omits keys (bull-ish single gear).
_DEFAULT_FACTORS: Dict[str, Any] = {
    "enabled": True,
    "allow_pyramid": True,
    "k_profit": 0.33,
    "h_add": 0.02,
    "H_book": 0.06,
    "target_pair_weight": 0.20,
    "min_gap_pct": 0.02,
    "gap_full_pct": 0.25,
    "use_gap_scale": True,
    "min_move_usd": 50.0,
    "min_position_usd": 25.0,
    "stop_loss_pct": 0.03,
}

# Regime overlays — purpose-led posture, not fear round-numbers.
REGIME_ADD_RISK_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "bull": {
        "allow_pyramid": True,
        "k_profit": 0.33,
        "h_add": 0.02,
        "H_book": 0.06,
        "target_pair_weight": 0.22,
        "cash_frac": 0.25,
    },
    "flat": {
        "allow_pyramid": True,
        "k_profit": 0.25,
        "h_add": 0.01,
        "H_book": 0.04,
        "target_pair_weight": 0.18,
        "cash_frac": 0.12,
    },
    "transition": {
        "allow_pyramid": False,
        "k_profit": 0.15,
        "h_add": 0.005,
        "H_book": 0.03,
        "target_pair_weight": 0.15,
        "cash_frac": 0.08,
    },
    "bear": {
        "allow_pyramid": False,
        "k_profit": 0.0,
        "h_add": 0.0,
        "H_book": 0.02,
        "target_pair_weight": 0.12,
        "cash_frac": 0.0,
    },
    "unknown": {
        "allow_pyramid": False,
        "k_profit": 0.0,
        "h_add": 0.0,
        "H_book": 0.02,
        "target_pair_weight": 0.12,
        "cash_frac": 0.0,
    },
}


@dataclass
class AddRiskFactors:
    enabled: bool = True
    allow_pyramid: bool = True
    k_profit: float = 0.33
    h_add: float = 0.02
    H_book: float = 0.06
    target_pair_weight: float = 0.20
    min_gap_pct: float = 0.02
    gap_full_pct: float = 0.25
    use_gap_scale: bool = True
    min_move_usd: float = 50.0
    min_position_usd: float = 25.0
    stop_loss_pct: float = 0.03
    cash_frac: float = 0.25
    rebalance_cap_usd: Optional[float] = None
    min_cash_reserve_pct: float = 0.10
    regime: str = "unknown"


@dataclass
class AddSizeDecision:
    pair: str
    proposed_usd: float
    max_add_usd: float
    final_usd: float
    action: str  # "pass" | "clip" | "skip" | "unchanged_new"
    reasons: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return self.action in ("clip", "skip")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def resolve_add_risk_factors(
    *,
    regime: Optional[str] = None,
    regime_entry: Optional[Dict[str, Any]] = None,
    policy_add_risk: Optional[Dict[str, Any]] = None,
    risk_management: Optional[Dict[str, Any]] = None,
    rebalance_cap_usd: Optional[float] = None,
    min_cash_reserve_pct: Optional[float] = None,
) -> AddRiskFactors:
    """Merge defaults ← regime table ← policy.add_risk ← risk_management.add_risk."""
    reg = (regime or "unknown").strip().lower()
    # Map layered labels onto coarse buckets when needed
    if reg in ("soft_up", "climb", "pre_bull"):
        base_key = "flat" if reg == "soft_up" else "bull"
    else:
        base_key = reg if reg in REGIME_ADD_RISK_DEFAULTS else "unknown"

    merged: Dict[str, Any] = dict(_DEFAULT_FACTORS)
    merged.update(REGIME_ADD_RISK_DEFAULTS.get(base_key) or {})
    if isinstance(policy_add_risk, dict):
        # global policy block
        merged.update({k: v for k, v in policy_add_risk.items() if v is not None and k != "by_regime"})
        by = policy_add_risk.get("by_regime") if isinstance(policy_add_risk.get("by_regime"), dict) else {}
        if isinstance(by.get(base_key), dict):
            merged.update({k: v for k, v in by[base_key].items() if v is not None})
        if isinstance(by.get(reg), dict):
            merged.update({k: v for k, v in by[reg].items() if v is not None})
    # per-regime entry embedded add_risk
    if isinstance(regime_entry, dict) and isinstance(regime_entry.get("add_risk"), dict):
        merged.update({k: v for k, v in regime_entry["add_risk"].items() if v is not None})
    rm = risk_management or {}
    if isinstance(rm.get("add_risk"), dict):
        merged.update({k: v for k, v in rm["add_risk"].items() if v is not None})
    # top-level rm toggles
    if "add_risk_sizer_enabled" in rm:
        merged["enabled"] = bool(rm.get("add_risk_sizer_enabled"))

    cap = rebalance_cap_usd
    if cap is None and regime_entry is not None:
        cap = regime_entry.get("rebalance_cap_usd")
    reserve = min_cash_reserve_pct
    if reserve is None and regime_entry is not None:
        reserve = regime_entry.get("min_cash_reserve_pct")

    return AddRiskFactors(
        enabled=bool(merged.get("enabled", True)),
        allow_pyramid=bool(merged.get("allow_pyramid", True)),
        k_profit=_f(merged.get("k_profit"), 0.33),
        h_add=_f(merged.get("h_add"), 0.02),
        H_book=_f(merged.get("H_book"), 0.06),
        target_pair_weight=_f(merged.get("target_pair_weight"), 0.20),
        min_gap_pct=_f(merged.get("min_gap_pct"), 0.02),
        gap_full_pct=_f(merged.get("gap_full_pct"), 0.25),
        use_gap_scale=bool(merged.get("use_gap_scale", True)),
        min_move_usd=_f(merged.get("min_move_usd"), 50.0),
        min_position_usd=_f(merged.get("min_position_usd"), 25.0),
        stop_loss_pct=_f(merged.get("stop_loss_pct"), 0.03),
        cash_frac=_f(merged.get("cash_frac"), 0.25),
        rebalance_cap_usd=_f(cap, 0.0) if cap is not None else None,
        min_cash_reserve_pct=_f(reserve, 0.10) if reserve is not None else 0.10,
        regime=reg,
    )


def stop_gap_pct(price: float, stop: float) -> Optional[float]:
    px = _f(price)
    sp = _f(stop)
    if px <= 0 or sp <= 0:
        return None
    return (px - sp) / px


def gap_scale(gap: Optional[float], min_gap: float, full_gap: float, use: bool) -> float:
    if not use:
        return 1.0
    if gap is None:
        return 0.0
    lo = max(0.0, float(min_gap))
    hi = max(lo + 1e-9, float(full_gap))
    if gap <= lo:
        return 0.0
    if gap >= hi:
        return 1.0
    return (gap - lo) / (hi - lo)


def pair_stop_risk_usd(
    *,
    value_usd: float,
    price: float,
    stop: float,
) -> float:
    """Approximate $ risk if mark moves to stop (same % on notional)."""
    g = stop_gap_pct(price, stop)
    if g is None or g <= 0:
        return 0.0
    return max(0.0, _f(value_usd) * g)


def compute_max_add_usd(
    *,
    pair: str,
    position_usd: float,
    entry_price: float,
    current_price: float,
    stop_price: Optional[float],
    equity_usd: float,
    cash_usd: float,
    factors: AddRiskFactors,
    other_book_heat_usd: float = 0.0,
) -> Tuple[float, Dict[str, Any]]:
    """
    Return (max_add_notional_usd, detail).
    0 means no add.
    """
    detail: Dict[str, Any] = {
        "pair": pair,
        "regime": factors.regime,
        "position_usd": round(_f(position_usd), 4),
        "equity_usd": round(_f(equity_usd), 4),
    }
    pos = _f(position_usd)
    eq = max(_f(equity_usd), 1e-9)
    px = _f(current_price)
    entry = _f(entry_price)
    stop = _f(stop_price) if stop_price is not None else 0.0
    if stop <= 0 and entry > 0 and factors.stop_loss_pct > 0:
        stop = entry * (1.0 - factors.stop_loss_pct)
        detail["stop_source"] = "theoretical_from_entry"
    else:
        detail["stop_source"] = "provided" if stop > 0 else "none"

    if not factors.enabled:
        detail["reason"] = "disabled"
        return float("inf"), detail  # caller treats as no clip

    if pos < factors.min_position_usd:
        detail["reason"] = "not_existing_stack"
        return float("inf"), detail

    if not factors.allow_pyramid:
        detail["reason"] = "pyramid_disallowed_regime"
        return 0.0, detail

    gap = stop_gap_pct(px, stop) if stop > 0 and px > 0 else None
    detail["stop_price"] = round(stop, 6) if stop > 0 else None
    detail["current_price"] = round(px, 6) if px > 0 else None
    detail["entry_price"] = round(entry, 6) if entry > 0 else None
    detail["stop_gap_pct"] = round(gap, 6) if gap is not None else None

    if gap is None:
        detail["reason"] = "gap_unknown"
        return 0.0, detail
    if gap < factors.min_gap_pct:
        detail["reason"] = "gap_below_min"
        return 0.0, detail

    # Open profit vs cost basis (entry * qty approximated via value/price)
    qty = (pos / px) if px > 0 else 0.0
    cost = qty * entry if entry > 0 else 0.0
    open_upnl = pos - cost if cost > 0 else 0.0
    detail["open_upnl_usd"] = round(open_upnl, 4)

    profit_budget = max(0.0, open_upnl) * max(0.0, factors.k_profit)
    heat_budget = eq * max(0.0, factors.h_add)
    book_cap = eq * max(0.0, factors.H_book)
    book_left = max(0.0, book_cap - max(0.0, other_book_heat_usd))
    risk_budget = min(profit_budget, heat_budget, book_left)
    detail["profit_budget"] = round(profit_budget, 4)
    detail["heat_budget"] = round(heat_budget, 4)
    detail["book_heat_left"] = round(book_left, 4)
    detail["risk_budget"] = round(risk_budget, 4)

    if risk_budget <= 0:
        detail["reason"] = "zero_risk_budget"
        return 0.0, detail

    # Notional from risk / gap
    max_from_risk = risk_budget / max(gap, 1e-9)
    gscale = gap_scale(gap, factors.min_gap_pct, factors.gap_full_pct, factors.use_gap_scale)
    max_from_risk *= gscale
    detail["gap_scale"] = round(gscale, 4)
    detail["max_from_risk"] = round(max_from_risk, 4)

    # Exposure room to target weight
    target_val = eq * max(0.0, min(1.0, factors.target_pair_weight))
    room = max(0.0, target_val - pos)
    detail["target_pair_usd"] = round(target_val, 4)
    detail["exposure_room"] = round(room, 4)

    # Free cash after reserve
    reserve = eq * max(0.0, factors.min_cash_reserve_pct)
    free_cash = max(0.0, _f(cash_usd) - reserve)
    cash_slice = free_cash * max(0.0, min(1.0, factors.cash_frac))
    detail["free_cash"] = round(free_cash, 4)
    detail["cash_slice"] = round(cash_slice, 4)

    caps = [max_from_risk, room, cash_slice]
    if factors.rebalance_cap_usd is not None and factors.rebalance_cap_usd >= 0:
        caps.append(float(factors.rebalance_cap_usd))
        detail["rebalance_cap_usd"] = float(factors.rebalance_cap_usd)

    max_add = max(0.0, min(caps))
    detail["max_add_usd"] = round(max_add, 4)
    detail["reason"] = "ok" if max_add > 0 else "capped_to_zero"
    return max_add, detail


def decide_add_size(
    *,
    pair: str,
    proposed_usd: float,
    position_usd: float,
    entry_price: float,
    current_price: float,
    stop_price: Optional[float],
    equity_usd: float,
    cash_usd: float,
    factors: AddRiskFactors,
    other_book_heat_usd: float = 0.0,
) -> AddSizeDecision:
    proposed = max(0.0, _f(proposed_usd))
    pos = _f(position_usd)

    if pos < factors.min_position_usd:
        return AddSizeDecision(
            pair=pair,
            proposed_usd=proposed,
            max_add_usd=proposed,
            final_usd=proposed,
            action="unchanged_new",
            reasons=["new_or_dust_stack"],
        )

    max_add, detail = compute_max_add_usd(
        pair=pair,
        position_usd=pos,
        entry_price=entry_price,
        current_price=current_price,
        stop_price=stop_price,
        equity_usd=equity_usd,
        cash_usd=cash_usd,
        factors=factors,
        other_book_heat_usd=other_book_heat_usd,
    )

    if max_add == float("inf"):
        return AddSizeDecision(
            pair=pair,
            proposed_usd=proposed,
            max_add_usd=proposed,
            final_usd=proposed,
            action="pass",
            reasons=[str(detail.get("reason") or "pass")],
            detail=detail,
        )

    if max_add < factors.min_move_usd:
        return AddSizeDecision(
            pair=pair,
            proposed_usd=proposed,
            max_add_usd=max_add,
            final_usd=0.0,
            action="skip",
            reasons=[f"max_add ${max_add:.2f} < min_move ${factors.min_move_usd:.2f}", str(detail.get("reason") or "")],
            detail=detail,
        )

    if proposed <= max_add + 1e-9:
        return AddSizeDecision(
            pair=pair,
            proposed_usd=proposed,
            max_add_usd=max_add,
            final_usd=proposed,
            action="pass",
            reasons=["within_budget"],
            detail=detail,
        )

    return AddSizeDecision(
        pair=pair,
        proposed_usd=proposed,
        max_add_usd=max_add,
        final_usd=max_add,
        action="clip",
        reasons=[f"clip ${proposed:.2f} → ${max_add:.2f}", str(detail.get("reason") or "ok")],
        detail=detail,
    )


def _position_snapshot(runner: Any) -> Tuple[Dict[str, Dict[str, float]], float, float]:
    """Returns positions[pair]={value,entry,price}, equity, cash."""
    positions: Dict[str, Dict[str, float]] = {}
    cash = 0.0
    equity = 0.0
    try:
        live = None
        if hasattr(runner, "portfolio") and runner.portfolio is not None:
            raw = runner.portfolio.get_enriched_positions()
            if isinstance(raw, dict) and "positions" in raw:
                pos_map = raw.get("positions") or {}
                cash = _f(raw.get("cash_usd") or raw.get("cash"), 0.0)
            else:
                pos_map = raw or {}
            for pair, meta in (pos_map or {}).items():
                if not isinstance(meta, dict):
                    positions[str(pair)] = {"value": _f(meta), "entry": 0.0, "price": 0.0}
                    continue
                positions[str(pair)] = {
                    "value": _f(meta.get("value_usd") or meta.get("usd_value") or meta.get("value"), 0.0),
                    "entry": _f(meta.get("entry_price") or meta.get("avg_entry") or meta.get("entry"), 0.0),
                    "price": _f(meta.get("current_price") or meta.get("price"), 0.0),
                    "amount": _f(meta.get("amount") or meta.get("qty"), 0.0),
                }
        # cash/equity from live state helpers if present
        if hasattr(runner, "get_cash_usd"):
            try:
                cash = _f(runner.get_cash_usd(), cash)
            except Exception:
                pass
        # fallback live state file via runner attributes
        for attr in ("last_total_equity", "total_equity_usd", "equity_usd"):
            if hasattr(runner, attr):
                equity = _f(getattr(runner, attr), 0.0)
                if equity > 0:
                    break
        holdings = sum(p.get("value", 0.0) for p in positions.values())
        if equity <= 0:
            equity = holdings + cash
        if cash <= 0 and hasattr(runner, "cash_usd"):
            cash = _f(getattr(runner, "cash_usd"), 0.0)
    except Exception as e:
        logger.warning("[ADD-RISK] position snapshot failed: %s", e)
    return positions, equity, cash


def _stop_for_pair(pair: str, entry: float, stop_loss_pct: float) -> Optional[float]:
    try:
        from phase6.core.runner_capital_events import _latest_registry_stop_for_pair

        row = _latest_registry_stop_for_pair(pair)
        if isinstance(row, dict):
            sp = _f(row.get("stop_price"), 0.0)
            if sp > 0:
                return sp
            en = _f(row.get("entry_price"), entry)
            if en > 0 and stop_loss_pct > 0:
                return en * (1.0 - stop_loss_pct)
    except Exception:
        pass
    if entry > 0 and stop_loss_pct > 0:
        return entry * (1.0 - stop_loss_pct)
    return None


def _load_factors_for_runner(runner: Any) -> AddRiskFactors:
    regime = "unknown"
    regime_entry: Dict[str, Any] = {}
    policy_ar: Dict[str, Any] = {}
    cap = None
    reserve = None
    try:
        from phase6.core.regime_cash_policy import load_policy, resolve_regime_cash

        pol = load_policy()
        policy_ar = pol.get("add_risk") if isinstance(pol.get("add_risk"), dict) else {}
        snap = resolve_regime_cash(policy=pol)
        regime = getattr(snap, "regime", None) or "unknown"
        cap = getattr(snap, "rebalance_cap_usd", None)
        reserve = getattr(snap, "min_cash_reserve_pct", None)
        regimes = (pol.get("regimes") or {}) if isinstance(pol, dict) else {}
        regime_entry = regimes.get(regime) if isinstance(regimes.get(regime), dict) else {}
        # layered label → coarse
        layer = None
        det = getattr(snap, "detector", None) or {}
        if isinstance(det, dict):
            layer = det.get("regime_layer") or det.get("regime")
        if layer and isinstance(regimes.get(str(layer)), dict):
            # prefer coarse regime entry already; layer only if bull/flat/bear missing add_risk
            pass
    except Exception as e:
        logger.warning("[ADD-RISK] regime resolve failed: %s", e)

    cfg = getattr(runner, "config_dict", None) or {}
    rm = cfg.get("risk_management") if isinstance(cfg, dict) else {}
    gs = cfg.get("global_settings") if isinstance(cfg, dict) else {}
    if cap is None and isinstance(gs, dict):
        cap = gs.get("rebalance_cap_usd")
    if isinstance(rm, dict) and rm.get("stop_loss_pct") is not None:
        # fold into factors via risk_management.add_risk or default
        pass

    factors = resolve_add_risk_factors(
        regime=str(regime),
        regime_entry=regime_entry if isinstance(regime_entry, dict) else {},
        policy_add_risk=policy_ar if isinstance(policy_ar, dict) else {},
        risk_management=rm if isinstance(rm, dict) else {},
        rebalance_cap_usd=_f(cap) if cap is not None else None,
        min_cash_reserve_pct=_f(reserve) if reserve is not None else None,
    )
    # stop_loss_pct from rm
    if isinstance(rm, dict) and rm.get("stop_loss_pct") is not None:
        factors.stop_loss_pct = _f(rm.get("stop_loss_pct"), factors.stop_loss_pct)
    if isinstance(rm, dict) and rm.get("near_stop_min_gap_pct") is not None:
        factors.min_gap_pct = _f(rm.get("near_stop_min_gap_pct"), factors.min_gap_pct)
    return factors


def filter_trade_plan_add_risk(runner: Any, plan: Any) -> Any:
    """
    Clip/skip BUY adds into existing stacks using factor budgets.
    Mutates plan.actions when present.
    """
    if plan is None or not getattr(plan, "actions", None):
        return plan

    factors = _load_factors_for_runner(runner)
    if not factors.enabled:
        return plan

    positions, equity, cash = _position_snapshot(runner)
    if equity <= 0:
        # try live state path
        try:
            from pathlib import Path
            import json

            p = Path("data/state/phase6_live_state.json")
            if p.exists():
                live = json.loads(p.read_text())
                cash = _f(live.get("cash_usd"), cash)
                equity = _f(live.get("total_usd") or live.get("equity_usd"), equity)
                for row in live.get("positions") or []:
                    if not isinstance(row, dict):
                        continue
                    pair = row.get("pair")
                    if not pair:
                        continue
                    positions[str(pair)] = {
                        "value": _f(row.get("value_usd"), 0.0),
                        "entry": _f(row.get("entry_price"), 0.0),
                        "price": _f(row.get("current_price"), 0.0),
                        "amount": _f(row.get("amount"), 0.0),
                    }
        except Exception:
            pass

    # Precompute per-pair stop + heat
    stops: Dict[str, float] = {}
    heats: Dict[str, float] = {}
    for pair, meta in positions.items():
        st = _stop_for_pair(pair, meta.get("entry", 0.0), factors.stop_loss_pct)
        if st:
            stops[pair] = st
        px = meta.get("price") or 0.0
        if (not px or px <= 0) and hasattr(runner, "exchange") and runner.exchange is not None:
            try:
                px = _f(runner.exchange.get_price(pair), 0.0)
                meta["price"] = px
            except Exception:
                pass
        heats[pair] = pair_stop_risk_usd(
            value_usd=meta.get("value", 0.0),
            price=meta.get("price", 0.0) or 0.0,
            stop=stops.get(pair) or 0.0,
        )

    decisions: List[AddSizeDecision] = []
    new_actions: List[Dict[str, Any]] = []
    # Track heat consumed by adds we keep in this plan (sequential)
    planned_heat = 0.0

    for a in list(plan.actions):
        action = str(a.get("action") or a.get("side") or "").upper()
        pair = a.get("pair")
        if action != "BUY" or not pair:
            new_actions.append(a)
            continue

        meta = positions.get(pair) or {}
        pos_usd = _f(meta.get("value"), 0.0)
        # other book heat excludes this pair + adds heat already planned
        other_heat = sum(v for k, v in heats.items() if k != pair) + planned_heat

        proposed = _f(a.get("usd") if a.get("usd") is not None else a.get("usd_amount"), 0.0)
        dec = decide_add_size(
            pair=str(pair),
            proposed_usd=proposed,
            position_usd=pos_usd,
            entry_price=_f(meta.get("entry"), 0.0),
            current_price=_f(meta.get("price"), 0.0),
            stop_price=stops.get(str(pair)),
            equity_usd=equity,
            cash_usd=cash,
            factors=factors,
            other_book_heat_usd=other_heat,
        )
        decisions.append(dec)

        if dec.action == "skip":
            logger.info(
                "[ADD-RISK] skip %s proposed=$%.2f max=$%.2f regime=%s reasons=%s",
                pair,
                dec.proposed_usd,
                dec.max_add_usd,
                factors.regime,
                dec.reasons,
            )
            continue

        if dec.action == "clip":
            a = dict(a)
            a["usd"] = dec.final_usd
            if "usd_amount" in a:
                a["usd_amount"] = dec.final_usd
            a["add_risk_clipped_from"] = dec.proposed_usd
            a["add_risk_max"] = dec.max_add_usd
            a["reason"] = (str(a.get("reason") or "") + "|add_risk_clip").strip("|")
            logger.info(
                "[ADD-RISK] clip %s $%.2f → $%.2f regime=%s gap=%s risk_bud=$%s",
                pair,
                dec.proposed_usd,
                dec.final_usd,
                factors.regime,
                (dec.detail or {}).get("stop_gap_pct"),
                (dec.detail or {}).get("risk_budget"),
            )
            # approximate heat of this add
            g = (dec.detail or {}).get("stop_gap_pct") or 0.0
            planned_heat += max(0.0, dec.final_usd * float(g))
            new_actions.append(a)
            continue

        # pass / unchanged_new
        if dec.action == "pass" and pos_usd >= factors.min_position_usd:
            g = (dec.detail or {}).get("stop_gap_pct") or 0.0
            planned_heat += max(0.0, dec.final_usd * float(g))
            logger.info(
                "[ADD-RISK] pass %s $%.2f (max $%.2f) regime=%s",
                pair,
                dec.final_usd,
                dec.max_add_usd,
                factors.regime,
            )
        new_actions.append(a)

    plan.actions = new_actions
    try:
        plan.add_risk_decisions = [  # type: ignore[attr-defined]
            {
                "pair": d.pair,
                "action": d.action,
                "proposed": d.proposed_usd,
                "max_add": d.max_add_usd,
                "final": d.final_usd,
                "reasons": d.reasons,
                "detail": d.detail,
            }
            for d in decisions
        ]
        plan.add_risk_regime = factors.regime  # type: ignore[attr-defined]
    except Exception:
        pass
    return plan


def report_open_pairs_add_room(
    *,
    positions: Sequence[Dict[str, Any]] | Dict[str, Any],
    equity_usd: float,
    cash_usd: float,
    factors: AddRiskFactors,
    stops: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """Observational: max add room per open pair (no plan mutation)."""
    stops = stops or {}
    pos_list: List[Tuple[str, Dict[str, float]]] = []
    if isinstance(positions, dict) and positions and not any(
        isinstance(k, str) and k.endswith("-USD") for k in list(positions.keys())[:3]
    ):
        # maybe {positions: [...]}
        if "positions" in positions:
            raw = positions.get("positions")
            if isinstance(raw, list):
                for row in raw:
                    if isinstance(row, dict) and row.get("pair"):
                        pos_list.append(
                            (
                                str(row["pair"]),
                                {
                                    "value": _f(row.get("value_usd"), 0.0),
                                    "entry": _f(row.get("entry_price"), 0.0),
                                    "price": _f(row.get("current_price"), 0.0),
                                },
                            )
                        )
            elif isinstance(raw, dict):
                for pair, meta in raw.items():
                    if isinstance(meta, dict):
                        pos_list.append(
                            (
                                str(pair),
                                {
                                    "value": _f(meta.get("value_usd") or meta.get("value"), 0.0),
                                    "entry": _f(meta.get("entry_price"), 0.0),
                                    "price": _f(meta.get("current_price"), 0.0),
                                },
                            )
                        )
        else:
            for pair, meta in positions.items():
                if isinstance(meta, dict):
                    pos_list.append(
                        (
                            str(pair),
                            {
                                "value": _f(meta.get("value_usd") or meta.get("value"), 0.0),
                                "entry": _f(meta.get("entry_price"), 0.0),
                                "price": _f(meta.get("current_price"), 0.0),
                            },
                        )
                    )
    elif isinstance(positions, list):
        for row in positions:
            if isinstance(row, dict) and row.get("pair"):
                pos_list.append(
                    (
                        str(row["pair"]),
                        {
                            "value": _f(row.get("value_usd"), 0.0),
                            "entry": _f(row.get("entry_price"), 0.0),
                            "price": _f(row.get("current_price"), 0.0),
                        },
                    )
                )
    else:
        for pair, meta in (positions or {}).items():  # type: ignore[union-attr]
            if isinstance(meta, dict):
                pos_list.append(
                    (
                        str(pair),
                        {
                            "value": _f(meta.get("value_usd") or meta.get("value"), 0.0),
                            "entry": _f(meta.get("entry_price"), 0.0),
                            "price": _f(meta.get("current_price"), 0.0),
                        },
                    )
                )

    heats = {}
    for pair, meta in pos_list:
        st = stops.get(pair)
        if st is None:
            st = _stop_for_pair(pair, meta["entry"], factors.stop_loss_pct)
        if st:
            stops[pair] = st
        heats[pair] = pair_stop_risk_usd(
            value_usd=meta["value"], price=meta["price"], stop=stops.get(pair) or 0.0
        )

    out: List[Dict[str, Any]] = []
    for pair, meta in pos_list:
        if meta["value"] < factors.min_position_usd:
            out.append(
                {
                    "pair": pair,
                    "position_usd": meta["value"],
                    "status": "dust_or_flat",
                    "max_add_usd": None,
                    "note": "not an existing stack for add sizer",
                }
            )
            continue
        other = sum(v for k, v in heats.items() if k != pair)
        max_add, detail = compute_max_add_usd(
            pair=pair,
            position_usd=meta["value"],
            entry_price=meta["entry"],
            current_price=meta["price"],
            stop_price=stops.get(pair),
            equity_usd=equity_usd,
            cash_usd=cash_usd,
            factors=factors,
            other_book_heat_usd=other,
        )
        weight = meta["value"] / max(equity_usd, 1e-9)
        out.append(
            {
                "pair": pair,
                "position_usd": round(meta["value"], 2),
                "weight_pct": round(weight * 100.0, 2),
                "open_upnl_usd": detail.get("open_upnl_usd"),
                "stop_gap_pct": detail.get("stop_gap_pct"),
                "stop_price": detail.get("stop_price"),
                "pair_heat_usd": round(heats.get(pair, 0.0), 2),
                "max_add_usd": None if max_add == float("inf") else round(float(max_add), 2),
                "over_target": weight > factors.target_pair_weight + 1e-9,
                "status": "over_target_no_forced_sell" if weight > factors.target_pair_weight else "in_band",
                "detail_reason": detail.get("reason"),
                "budgets": {
                    "profit": detail.get("profit_budget"),
                    "heat": detail.get("heat_budget"),
                    "book_left": detail.get("book_heat_left"),
                    "exposure_room": detail.get("exposure_room"),
                    "cash_slice": detail.get("cash_slice"),
                    "rebalance_cap": detail.get("rebalance_cap_usd"),
                },
            }
        )
    return out
