#!/usr/bin/env python3
"""
RSI-primary / sentiment-reinforce deploy gates (P0) + entry tags + sentiment-fade shadow (P1).

Principle: RSI is grounded structure. Sentiment is transient timing reinforcement.

See: docs/research/RSI_PRIMARY_SENTIMENT_REINFORCE_2026-08-24.md
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "rsi_oversold_max": 35.0,
    "rsi_structure_max": 40.0,
    "rsi_deadband_low": 40.0,
    "rsi_deadband_high": 60.0,
    "rsi_continuation_max": 68.0,
    "mom_continuation_pct": 1.5,
    "sentiment_reinforce_min": 0.20,
    "sentiment_only_size_frac": 0.35,
    "max_pair_weight": 0.30,
    "max_pair_weight_recovery": 0.35,
    "max_single_share_of_free_cash": 0.50,
    "enforce_rebalance_cap": True,
    "min_move_usd": 50.0,
    "sentiment_fade": {
        "mode": "shadow",  # shadow | live | off
        "fade_delta": 0.40,
        "fade_floor": 0.15,
        "trim_fraction": 0.50,
        "min_position_usd": 25.0,
        "tp_arm_pct": 0.04,
        "notify_telegram": True,
        "notify_dedupe_hours": 6,
        "time_stop_hours": 0,
    },
}

ENTRY_LOTS_PATH = Path("data/state/entry_driver_lots.json")
FADE_EVENTS_PATH = Path("data/state/sentiment_fade_shadow_events.jsonl")
FADE_NOTIFY_PATH = Path("data/state/sentiment_fade_notify_dedupe.json")


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        if isinstance(v, dict):
            for k in ("rsi", "value", "RSI", "rsi_14"):
                if k in v and v[k] is not None:
                    return float(v[k])
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _normalize_rsi_map(rsi_values: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Flatten nested RSI cache ({'LINK-USD': {'rsi': 39.4}}) to floats."""
    out: Dict[str, float] = {}
    for k, v in (rsi_values or {}).items():
        if v is None:
            continue
        if isinstance(v, dict):
            got = None
            for key in ("rsi", "value", "RSI", "rsi_14"):
                if key in v and v[key] is not None:
                    try:
                        got = float(v[key])
                    except (TypeError, ValueError):
                        got = None
                    break
            if got is None:
                continue
            out[str(k)] = got
        else:
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    return out


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_rsi_primary_config(config_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Merge trading_config rsi_primary_deploy over defaults."""
    out = json.loads(json.dumps(DEFAULTS))  # deep copy
    cfg = config_dict or {}
    block = cfg.get("rsi_primary_deploy") if isinstance(cfg, dict) else None
    if not isinstance(block, dict):
        # try global_settings nest
        gs = cfg.get("global_settings") if isinstance(cfg, dict) else None
        if isinstance(gs, dict) and isinstance(gs.get("rsi_primary_deploy"), dict):
            block = gs["rsi_primary_deploy"]
    if isinstance(block, dict):
        for k, v in block.items():
            if k == "sentiment_fade" and isinstance(v, dict):
                out["sentiment_fade"].update(v)
            else:
                out[k] = v
    return out


@dataclass
class EntryDrivers:
    pair: str
    drivers: List[str] = field(default_factory=list)
    sentiment_only: bool = False
    sentiment_led: bool = False
    full_size_ok: bool = False
    rsi: float = 50.0
    sentiment: float = 0.0
    momentum_pct: Optional[float] = None
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_entry_drivers(
    pair: str,
    rsi: float,
    sentiment: float,
    *,
    momentum_pct: Optional[float] = None,
    reason: str = "",
    cfg: Optional[Dict[str, Any]] = None,
) -> EntryDrivers:
    """
    Classify what justifies a BUY thesis.

    RSI drivers = structure. Sentiment = reinforce only.
    """
    c = cfg or DEFAULTS
    rsi = _f(rsi, 50.0)
    sent = _f(sentiment, 0.0)
    mom = None if momentum_pct is None else _f(momentum_pct, 0.0)
    drivers: List[str] = []

    oversold_max = _f(c.get("rsi_oversold_max"), 35.0)
    structure_max = _f(c.get("rsi_structure_max"), 40.0)
    dead_lo = _f(c.get("rsi_deadband_low"), 40.0)
    dead_hi = _f(c.get("rsi_deadband_high"), 60.0)
    cont_max = _f(c.get("rsi_continuation_max"), 68.0)
    mom_need = _f(c.get("mom_continuation_pct"), 1.5)
    sent_min = _f(c.get("sentiment_reinforce_min"), 0.20)

    if rsi < oversold_max:
        drivers.append("rsi_oversold")
    elif rsi < structure_max:
        drivers.append("rsi_structure")

    if mom is not None and dead_lo <= rsi <= cont_max and mom >= mom_need:
        if "rsi_continuation" not in drivers:
            drivers.append("rsi_continuation")

    # Reason-text hint: SignalGenerator says "RSI oversold"
    rlow = (reason or "").lower()
    if "rsi oversold" in rlow and "rsi_oversold" not in drivers and rsi < 45:
        drivers.append("rsi_oversold")

    if sent >= sent_min:
        drivers.append("sentiment")

    # Explicit structure tags from ignition scout / run-phase path
    rlow = (reason or "").lower()
    if "ignition_scout" in rlow or "run_ignition" in rlow or "rsi_structure" in rlow:
        if "rsi_structure" not in drivers and "rsi_continuation" not in drivers and "rsi_oversold" not in drivers:
            drivers.append("rsi_structure")

    rsi_drivers = {"rsi_oversold", "rsi_structure", "rsi_continuation"}
    has_rsi = any(d in rsi_drivers for d in drivers)
    has_sent = "sentiment" in drivers
    sentiment_only = has_sent and not has_rsi
    # Led: only-sent OR (sent + RSI stuck in deadband without oversold/structure/continuation)
    in_dead = dead_lo <= rsi <= dead_hi
    sentiment_led = sentiment_only or (has_sent and not has_rsi and in_dead)
    if has_sent and not has_rsi and in_dead:
        sentiment_led = True

    return EntryDrivers(
        pair=pair,
        drivers=drivers,
        sentiment_only=sentiment_only,
        sentiment_led=sentiment_led or sentiment_only,
        full_size_ok=has_rsi,
        rsi=rsi,
        sentiment=sent,
        momentum_pct=mom,
        reason=reason or "",
    )


@dataclass
class BuyGateResult:
    pair: str
    original_usd: float
    final_usd: float
    dropped: bool
    haircut_applied: bool
    ticket_cap_applied: bool
    pair_weight_applied: bool
    free_cash_share_applied: bool
    drivers: EntryDrivers
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["drivers"] = self.drivers.as_dict()
        return d


def apply_buy_size_gates(
    pair: str,
    proposed_usd: float,
    *,
    rsi: float,
    sentiment: float,
    equity_usd: float,
    current_pair_usd: float = 0.0,
    rebalance_cap_usd: Optional[float] = None,
    free_cash_usd: Optional[float] = None,
    emergency_recovery: bool = False,
    momentum_pct: Optional[float] = None,
    reason: str = "",
    cfg: Optional[Dict[str, Any]] = None,
) -> BuyGateResult:
    """
    Pure P0 sizing. Returns final USD (0 if dropped).
    Order: classify → sentiment-only haircut → ticket cap → pair weight room → free-cash share.
    """
    c = cfg or DEFAULTS
    usd0 = max(0.0, _f(proposed_usd, 0.0))
    drivers = classify_entry_drivers(
        pair, rsi, sentiment, momentum_pct=momentum_pct, reason=reason, cfg=c
    )
    notes: List[str] = []
    usd = usd0
    haircut = ticket = pair_w = free_s = False
    min_move = _f(c.get("min_move_usd"), 50.0)

    if not c.get("enabled", True):
        return BuyGateResult(
            pair=pair,
            original_usd=usd0,
            final_usd=usd0,
            dropped=False,
            haircut_applied=False,
            ticket_cap_applied=False,
            pair_weight_applied=False,
            free_cash_share_applied=False,
            drivers=drivers,
            notes=["disabled"],
        )

    # 1) Sentiment-only haircut
    frac = _f(c.get("sentiment_only_size_frac"), 0.35)
    frac = max(0.0, min(1.0, frac))
    if drivers.sentiment_only and frac < 1.0:
        usd = usd * frac
        haircut = True
        notes.append(f"sent_only_haircut×{frac:.2f}")

    # 2) Hard rebalance ticket cap
    if c.get("enforce_rebalance_cap", True) and rebalance_cap_usd is not None:
        cap = _f(rebalance_cap_usd, -1.0)
        if cap >= 0:
            if usd > cap:
                usd = cap
                ticket = True
                notes.append(f"ticket_cap={cap:.2f}")

    # 3) Max pair weight room
    eq = max(0.0, _f(equity_usd, 0.0))
    cur = max(0.0, _f(current_pair_usd, 0.0))
    w_key = "max_pair_weight_recovery" if emergency_recovery else "max_pair_weight"
    w = _f(c.get(w_key), 0.30 if not emergency_recovery else 0.35)
    w = max(0.0, min(1.0, w))
    if eq > 0 and w > 0:
        room = max(0.0, w * eq - cur)
        if usd > room:
            usd = room
            pair_w = True
            notes.append(f"pair_weight_room={room:.2f} (w={w:.2f})")

    # 4) Max share of free cash (single ticket)
    if free_cash_usd is not None:
        fc = max(0.0, _f(free_cash_usd, 0.0))
        share = _f(c.get("max_single_share_of_free_cash"), 0.50)
        share = max(0.0, min(1.0, share))
        if fc > 0 and share < 1.0:
            lim = fc * share
            if usd > lim:
                usd = lim
                free_s = True
                notes.append(f"free_cash_share={share:.2f}→{lim:.2f}")

    dropped = usd < min_move - 1e-9
    if dropped:
        notes.append(f"dropped_below_min_move={min_move}")
        usd = 0.0

    return BuyGateResult(
        pair=pair,
        original_usd=usd0,
        final_usd=usd,
        dropped=dropped,
        haircut_applied=haircut,
        ticket_cap_applied=ticket,
        pair_weight_applied=pair_w,
        free_cash_share_applied=free_s,
        drivers=drivers,
        notes=notes,
    )


def apply_gates_to_actions(
    actions: Sequence[Dict[str, Any]],
    *,
    rsi_by_pair: Dict[str, float],
    sent_by_pair: Dict[str, float],
    equity_usd: float,
    positions_usd: Dict[str, float],
    rebalance_cap_usd: Optional[float],
    free_cash_usd: float,
    emergency_recovery: bool = False,
    mom_by_pair: Optional[Dict[str, float]] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], List[BuyGateResult]]:
    """Filter/clip BUY actions in a TradePlan-like action list."""
    c = cfg or DEFAULTS
    mom_by_pair = mom_by_pair or {}
    out: List[Dict[str, Any]] = []
    results: List[BuyGateResult] = []
    # Track sequential free cash consumption so multi-BUY plans don't each claim 50% of original cash
    remaining_free = max(0.0, _f(free_cash_usd, 0.0))
    pos = {k: _f(v, 0.0) for k, v in (positions_usd or {}).items()}

    for a in actions:
        action = str(a.get("action") or a.get("side") or "").upper()
        pair = a.get("pair")
        if action != "BUY" or not pair:
            out.append(dict(a))
            continue

        proposed = _f(a.get("usd") if a.get("usd") is not None else a.get("usd_amount"), 0.0)
        # Ignition seats: allow ticket up to equity*deploy_frac (not rebalance_cap $150)
        ticket_cap = rebalance_cap_usd
        is_ign = bool(a.get("ignition_scout")) or "ignition_scout" in str(a.get("reason") or "").lower()
        if is_ign:
            try:
                from phase6.core.run_lifecycle import (
                    DEFAULTS_P1,
                    ignition_ticket_usd,
                    load_lifecycle_config,
                )

                p1 = dict(DEFAULTS_P1)
                try:
                    full = json.loads(Path("config/trading_config_phase6.json").read_text())
                    p1 = load_lifecycle_config(full)["ignition_scout"]
                except Exception:
                    pass
                ign_cap = ignition_ticket_usd(
                    equity_usd=equity_usd,
                    free_cash_usd=remaining_free,
                    current_pair_usd=pos.get(str(pair), 0.0),
                    cfg_p1=p1,
                )
                frac = max(0.05, min(0.30, _f(p1.get("deploy_frac"), 0.18)))
                raw = equity_usd * frac if equity_usd > 0 else 0.0
                ign_cap = max(ign_cap, min(raw, _f(p1.get("proposal_usd_cap"), 500.0)))
                if ign_cap > 0:
                    ticket_cap = max(_f(rebalance_cap_usd, 0.0), ign_cap)
            except Exception:
                pass
        gr = apply_buy_size_gates(
            str(pair),
            proposed,
            rsi=_f(rsi_by_pair.get(str(pair)), 50.0),
            sentiment=_f(sent_by_pair.get(str(pair)), 0.0),
            equity_usd=equity_usd,
            current_pair_usd=pos.get(str(pair), 0.0),
            rebalance_cap_usd=ticket_cap,
            free_cash_usd=remaining_free,
            emergency_recovery=emergency_recovery,
            momentum_pct=mom_by_pair.get(str(pair)),
            reason=str(a.get("reason") or ""),
            cfg=c,
        )
        results.append(gr)
        if gr.dropped or gr.final_usd <= 0:
            logger.info(
                "[RSI-PRIMARY] drop BUY %s $%.2f → 0 (%s)",
                pair,
                proposed,
                ";".join(gr.notes),
            )
            continue

        na = dict(a)
        na["usd"] = gr.final_usd
        if "usd_amount" in na:
            na["usd_amount"] = gr.final_usd
        tag = "|".join(gr.notes) if gr.notes else "ok"
        prev_r = str(na.get("reason") or "")
        na["reason"] = f"{prev_r}|rsi_primary:{tag}" if prev_r else f"rsi_primary:{tag}"
        na["entry_drivers"] = gr.drivers.drivers
        na["sentiment_only"] = gr.drivers.sentiment_only
        na["sentiment_led"] = gr.drivers.sentiment_led
        na["entry_rsi"] = gr.drivers.rsi
        na["entry_sentiment"] = gr.drivers.sentiment
        na["rsi_primary_gate"] = gr.as_dict()
        if gr.final_usd + 1e-6 < proposed:
            na["rsi_primary_clipped_from"] = proposed
            logger.info(
                "[RSI-PRIMARY] clip BUY %s $%.2f → $%.2f (%s) drivers=%s",
                pair,
                proposed,
                gr.final_usd,
                tag,
                gr.drivers.drivers,
            )
        out.append(na)
        remaining_free = max(0.0, remaining_free - gr.final_usd)
        pos[str(pair)] = pos.get(str(pair), 0.0) + gr.final_usd

    return out, results


def filter_trade_plan_rsi_primary_deploy(
    runner: Any,
    plan: Any,
    *,
    sentiment_scores: Optional[Dict[str, float]] = None,
    rsi_values: Optional[Dict[str, float]] = None,
    equity_usd: Optional[float] = None,
    positions_usd: Optional[Dict[str, float]] = None,
    rebalance_cap_usd: Optional[float] = None,
    free_cash_usd: Optional[float] = None,
    emergency_recovery: Optional[bool] = None,
) -> Any:
    """
    Runner-facing filter. Mutates plan.actions. Safe no-op if disabled/empty.
    """
    if plan is None or not getattr(plan, "actions", None):
        return plan

    cfg_dict = getattr(runner, "config_dict", None) or {}
    cfg = load_rsi_primary_config(cfg_dict if isinstance(cfg_dict, dict) else {})
    if not cfg.get("enabled", True):
        return plan

    rsi_values = rsi_values if rsi_values is not None else (getattr(runner, "rsi_values", None) or {})
    if sentiment_scores is None:
        try:
            from phase6.core.sentiment_scorer import load_sentiment_scores

            universe = list(getattr(runner, "FIXED_UNIVERSE", None) or [])
            sentiment_scores = load_sentiment_scores(universe=universe) if universe else load_sentiment_scores()
        except Exception:
            sentiment_scores = {}

    # Positions / equity
    # None → try live state. Explicit {} means "flat book" (tests / controlled callers).
    pos: Dict[str, float] = {} if positions_usd is not None else {}
    explicit_pos = positions_usd is not None
    if explicit_pos:
        pos = {str(k): _f(v, 0.0) for k, v in positions_usd.items()}
    eq = _f(equity_usd, 0.0) if equity_usd is not None else 0.0
    cash = _f(free_cash_usd, 0.0) if free_cash_usd is not None else 0.0
    if (not explicit_pos) or eq <= 0 or (free_cash_usd is None and cash <= 0):
        try:
            # mirror add_risk snapshot lightly
            live_p = Path("data/state/phase6_live_state.json")
            if live_p.exists():
                live = json.loads(live_p.read_text())
                if eq <= 0:
                    eq = _f(live.get("total_usd") or live.get("equity_usd"), 0.0)
                if free_cash_usd is None and cash <= 0:
                    cash = _f(live.get("cash_usd"), 0.0)
                if not explicit_pos:
                    for row in live.get("positions") or []:
                        if isinstance(row, dict) and row.get("pair"):
                            pos[str(row["pair"])] = _f(row.get("value_usd"), 0.0)
        except Exception:
            pass

    if (free_cash_usd is None and cash <= 0) and hasattr(runner, "exchange") and runner.exchange is not None:
        try:
            cash = _f(runner.exchange.get_account_balance("USD"), 0.0)
        except Exception:
            pass

    if rebalance_cap_usd is None:
        try:
            from phase6.core.runtime_knobs import rebalance_cap_usd as _cap_fn

            rebalance_cap_usd = _cap_fn(cfg_dict)
        except Exception:
            gs = cfg_dict.get("global_settings") or {}
            rebalance_cap_usd = gs.get("rebalance_cap_usd")

    if emergency_recovery is None:
        active = sum(1 for v in pos.values() if _f(v, 0.0) > _f(cfg.get("min_move_usd"), 50.0))
        emergency_recovery = active <= 2

    if eq <= 0:
        eq = cash + sum(pos.values())

    if free_cash_usd is None and cash <= 0:
        cash = sum(
            _f(a.get("usd"), 0.0)
            for a in plan.actions
            if str(a.get("action") or a.get("side") or "").upper() == "BUY"
        )

    rsi_flat = _normalize_rsi_map(rsi_values if isinstance(rsi_values, dict) else {})
    # Do NOT default missing RSI to 50 — that masks sent_only and false structure.
    # Missing keys stay absent; apply_gates treats absence as no RSI.
    sent_flat = {str(k): _f(v, 0.0) for k, v in (sentiment_scores or {}).items()}
    new_actions, results = apply_gates_to_actions(
        list(plan.actions),
        rsi_by_pair=rsi_flat,
        sent_by_pair=sent_flat,
        equity_usd=eq,
        positions_usd=pos,
        rebalance_cap_usd=rebalance_cap_usd if rebalance_cap_usd is not None else None,
        free_cash_usd=cash,
        emergency_recovery=bool(emergency_recovery),
        cfg=cfg,
    )
    plan.actions = new_actions
    # Annotate notes
    clipped = [r for r in results if r.original_usd - r.final_usd > 1e-6 or r.dropped]
    if clipped:
        extra = f"rsi_primary_clips={len(clipped)}"
        prev = getattr(plan, "notes", "") or ""
        plan.notes = f"{prev}; {extra}" if prev else extra
        try:
            audit = Path("data/state/rsi_primary_deploy_audit.jsonl")
            audit.parent.mkdir(parents=True, exist_ok=True)
            with audit.open("a") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": _utcnow(),
                            "results": [r.as_dict() for r in results],
                            "equity": eq,
                            "cash": cash,
                            "rebalance_cap_usd": rebalance_cap_usd,
                            "emergency_recovery": emergency_recovery,
                        }
                    )
                    + "\n"
                )
        except Exception as e:
            logger.debug("rsi_primary audit write failed: %s", e)
    return plan


# ---------------------------------------------------------------------------
# Entry lot tags + sentiment fade shadow
# ---------------------------------------------------------------------------


def load_entry_lots(path: Path = ENTRY_LOTS_PATH) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("lots"), list):
            return data["lots"]
    except Exception:
        return []
    return []


def save_entry_lots(lots: List[Dict[str, Any]], path: Path = ENTRY_LOTS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updated": _utcnow(), "lots": lots}, indent=2))


def record_entry_lot(
    *,
    pair: str,
    entry_price: float,
    usd: float,
    drivers: EntryDrivers,
    order_id: Optional[str] = None,
    qty: Optional[float] = None,
    path: Path = ENTRY_LOTS_PATH,
) -> Dict[str, Any]:
    lots = load_entry_lots(path)
    # Replace open lot for pair (single active lot tag per pair for MVP)
    lots = [x for x in lots if str(x.get("pair")) != pair]
    row = {
        "pair": pair,
        "ts": _utcnow(),
        "entry_price": _f(entry_price),
        "usd": _f(usd),
        "qty": qty,
        "drivers": list(drivers.drivers),
        "sentiment_only": bool(drivers.sentiment_only),
        "sentiment_led": bool(drivers.sentiment_led),
        "entry_rsi": drivers.rsi,
        "entry_sentiment": drivers.sentiment,
        "order_id": order_id,
        "open": True,
    }
    lots.append(row)
    save_entry_lots(lots, path)
    # Enrich with run-phase / structure lifecycle tags (best-effort)
    try:
        from phase6.core.run_lifecycle import enrich_entry_lot_lifecycle

        lots2 = load_entry_lots(path)
        for i, x in enumerate(lots2):
            if str(x.get("pair")) == pair and x.get("open", True):
                lots2[i] = enrich_entry_lot_lifecycle(x)
                row = lots2[i]
                break
        save_entry_lots(lots2, path)
    except Exception as e:
        logger.debug("entry lot lifecycle enrich skipped: %s", e)
    # Research SSOT: entry leg signal event at true buy time (not only reconcile lag)
    try:
        from phase6.core.indicator_snapshot import append_trade_signal_event

        append_trade_signal_event(
            {
                "timestamp": row.get("ts"),
                "pair": pair,
                "side": "BUY",
                "order_id": order_id,
                "entry_rsi": row.get("entry_rsi"),
                "entry_sentiment": row.get("entry_sentiment"),
                "entry_drivers": row.get("drivers"),
                "sentiment_only": row.get("sentiment_only"),
                "sentiment_led": row.get("sentiment_led"),
                "entry_price": row.get("entry_price"),
                "signal_source": "entry_driver_lot",
                "mode": "live",
                "indicators_at_trade": {
                    "rsi": row.get("entry_rsi"),
                    "sentiment": row.get("entry_sentiment"),
                    "leg": "entry",
                    "source": "entry_driver_lot",
                },
            }
        )
    except Exception as e:
        logger.debug("entry lot signal event skipped: %s", e)
    return row


def close_entry_lot(pair: str, path: Path = ENTRY_LOTS_PATH) -> None:
    lots = load_entry_lots(path)
    changed = False
    for x in lots:
        if str(x.get("pair")) == pair and x.get("open", True):
            x["open"] = False
            x["closed_ts"] = _utcnow()
            changed = True
    if changed:
        save_entry_lots(lots, path)


def record_entry_from_buy_action(
    action: Dict[str, Any],
    *,
    entry_price: float,
    order_id: Optional[str] = None,
    qty: Optional[float] = None,
    path: Path = ENTRY_LOTS_PATH,
) -> Optional[Dict[str, Any]]:
    """Call after successful BUY when action carries entry_drivers fields."""
    pair = action.get("pair")
    if not pair:
        return None
    drivers_list = action.get("entry_drivers")
    if drivers_list is None and not action.get("sentiment_only") and not action.get("rsi_primary_gate"):
        # Still tag from rsi/sent if present
        ed = classify_entry_drivers(
            str(pair),
            _f(action.get("entry_rsi"), 50.0),
            _f(action.get("entry_sentiment"), 0.0),
            reason=str(action.get("reason") or ""),
        )
    else:
        gate = action.get("rsi_primary_gate") or {}
        d = gate.get("drivers") if isinstance(gate, dict) else None
        if isinstance(d, dict):
            ed = EntryDrivers(
                pair=str(pair),
                drivers=list(d.get("drivers") or drivers_list or []),
                sentiment_only=bool(d.get("sentiment_only", action.get("sentiment_only"))),
                sentiment_led=bool(d.get("sentiment_led", action.get("sentiment_led"))),
                full_size_ok=bool(d.get("full_size_ok", False)),
                rsi=_f(d.get("rsi", action.get("entry_rsi")), 50.0),
                sentiment=_f(d.get("sentiment", action.get("entry_sentiment")), 0.0),
            )
        else:
            ed = EntryDrivers(
                pair=str(pair),
                drivers=list(drivers_list or []),
                sentiment_only=bool(action.get("sentiment_only")),
                sentiment_led=bool(action.get("sentiment_led")),
                full_size_ok=not bool(action.get("sentiment_only")),
                rsi=_f(action.get("entry_rsi"), 50.0),
                sentiment=_f(action.get("entry_sentiment"), 0.0),
            )
    usd = _f(action.get("usd") if action.get("usd") is not None else action.get("usd_amount"), 0.0)
    return record_entry_lot(
        pair=str(pair),
        entry_price=entry_price,
        usd=usd,
        drivers=ed,
        order_id=order_id,
        qty=qty,
        path=path,
    )


@dataclass
class FadeEvent:
    pair: str
    would_trim_usd: float
    would_trim_frac: float
    entry_sentiment: float
    current_sentiment: float
    fade: float
    peak_return: float
    reason: str
    mode: str
    shadow: bool = True

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ts"] = _utcnow()
        return d


def evaluate_sentiment_fade(
    *,
    lots: Sequence[Dict[str, Any]],
    current_sentiment: Dict[str, float],
    current_prices: Dict[str, float],
    positions_usd: Dict[str, float],
    cfg: Optional[Dict[str, Any]] = None,
) -> List[FadeEvent]:
    """
    Pure P1 fade evaluation. Never places orders.
    """
    c = cfg or DEFAULTS
    fade_cfg = dict(DEFAULTS["sentiment_fade"])
    if isinstance(c.get("sentiment_fade"), dict):
        fade_cfg.update(c["sentiment_fade"])
    mode = str(fade_cfg.get("mode") or "shadow").lower()
    if mode in ("off", "disabled", "false", "0"):
        return []

    delta = _f(fade_cfg.get("fade_delta"), 0.40)
    floor = _f(fade_cfg.get("fade_floor"), 0.15)
    trim_frac = max(0.0, min(1.0, _f(fade_cfg.get("trim_fraction"), 0.50)))
    min_pos = _f(fade_cfg.get("min_position_usd"), 25.0)
    arm = _f(fade_cfg.get("tp_arm_pct"), 0.04)

    events: List[FadeEvent] = []
    for lot in lots:
        if not lot.get("open", True):
            continue
        if not (lot.get("sentiment_led") or lot.get("sentiment_only")):
            continue
        pair = str(lot.get("pair") or "")
        if not pair:
            continue
        pos_usd = _f(positions_usd.get(pair), _f(lot.get("usd"), 0.0))
        if pos_usd < min_pos:
            continue
        entry_sent = _f(lot.get("entry_sentiment"), 0.0)
        cur_sent = _f(current_sentiment.get(pair), 0.0)
        fade = entry_sent - cur_sent
        entry_px = _f(lot.get("entry_price"), 0.0)
        cur_px = _f(current_prices.get(pair), 0.0)
        peak_ret = 0.0
        if entry_px > 0 and cur_px > 0:
            peak_ret = (cur_px / entry_px) - 1.0
        # If already in TP arm zone, TP owns the exit — skip fade
        if peak_ret >= arm - 1e-12:
            continue
        hit = fade >= delta - 1e-12 or cur_sent <= floor + 1e-12
        if not hit:
            continue
        reason_parts = []
        if fade >= delta - 1e-12:
            reason_parts.append(f"fade_delta={fade:.3f}>={delta:.3f}")
        if cur_sent <= floor + 1e-12:
            reason_parts.append(f"sent_floor={cur_sent:.3f}<={floor:.3f}")
        events.append(
            FadeEvent(
                pair=pair,
                would_trim_usd=round(pos_usd * trim_frac, 4),
                would_trim_frac=trim_frac,
                entry_sentiment=entry_sent,
                current_sentiment=cur_sent,
                fade=round(fade, 4),
                peak_return=round(peak_ret, 4),
                reason="|".join(reason_parts),
                mode=mode,
                shadow=(mode != "live"),
            )
        )
    return events


def run_sentiment_fade_shadow(
    *,
    config_dict: Optional[Dict[str, Any]] = None,
    notify: bool = False,
    lots_path: Path = ENTRY_LOTS_PATH,
    events_path: Path = FADE_EVENTS_PATH,
) -> List[Dict[str, Any]]:
    """
    Load lots + live caches, evaluate fade, append JSONL. Optional TG (deduped).
    Live apply is NOT implemented here — mode=live only logs stronger tag until Brad wires sell path.
    """
    cfg = load_rsi_primary_config(config_dict)
    fade_cfg = cfg.get("sentiment_fade") or {}
    lots = [x for x in load_entry_lots(lots_path) if x.get("open", True)]
    if not lots:
        return []

    pairs = [str(x["pair"]) for x in lots if x.get("pair")]
    try:
        from phase6.core.sentiment_scorer import load_sentiment_scores

        sent = load_sentiment_scores(universe=pairs) or {}
    except Exception:
        sent = {}

    prices: Dict[str, float] = {}
    positions: Dict[str, float] = {}
    try:
        live_p = Path("data/state/phase6_live_state.json")
        if live_p.exists():
            live = json.loads(live_p.read_text())
            for row in live.get("positions") or []:
                if isinstance(row, dict) and row.get("pair"):
                    p = str(row["pair"])
                    positions[p] = _f(row.get("value_usd"), 0.0)
                    prices[p] = _f(row.get("current_price"), 0.0)
    except Exception:
        pass

    # Fallback prices from rsi cache companion / price history not required for unit use
    events = evaluate_sentiment_fade(
        lots=lots,
        current_sentiment=sent,
        current_prices=prices,
        positions_usd=positions,
        cfg=cfg,
    )
    out_rows = []
    if events:
        events_path.parent.mkdir(parents=True, exist_ok=True)
        with events_path.open("a") as f:
            for ev in events:
                row = ev.as_dict()
                f.write(json.dumps(row) + "\n")
                out_rows.append(row)
                logger.info(
                    "[SENT-FADE-%s] %s would_trim=$%.2f (%.0f%%) entry_sent=%.3f cur=%.3f peak_r=%.2f%% %s",
                    "SHADOW" if ev.shadow else "LIVE-TAG",
                    ev.pair,
                    ev.would_trim_usd,
                    ev.would_trim_frac * 100,
                    ev.entry_sentiment,
                    ev.current_sentiment,
                    ev.peak_return * 100,
                    ev.reason,
                )

    if notify and out_rows and fade_cfg.get("notify_telegram", True):
        _maybe_notify_fade(out_rows, dedupe_hours=_f(fade_cfg.get("notify_dedupe_hours"), 6.0))

    return out_rows


def _maybe_notify_fade(rows: List[Dict[str, Any]], dedupe_hours: float = 6.0) -> None:
    try:
        dedupe = {}
        if FADE_NOTIFY_PATH.exists():
            dedupe = json.loads(FADE_NOTIFY_PATH.read_text())
    except Exception:
        dedupe = {}
    now = datetime.now(timezone.utc)
    to_send = []
    for r in rows:
        pair = r.get("pair")
        last = dedupe.get(pair)
        if last:
            try:
                prev = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                if (now - prev).total_seconds() < dedupe_hours * 3600:
                    continue
            except Exception:
                pass
        to_send.append(r)
        dedupe[pair] = now.isoformat()
    if not to_send:
        return
    try:
        FADE_NOTIFY_PATH.parent.mkdir(parents=True, exist_ok=True)
        FADE_NOTIFY_PATH.write_text(json.dumps(dedupe, indent=2))
    except Exception:
        pass
    lines = ["⚠️ Sentiment-fade SHADOW (no live sell)"]
    for r in to_send:
        lines.append(
            f"• {r['pair']}: would_trim ${r['would_trim_usd']:.0f} "
            f"({r['would_trim_frac']*100:.0f}%) sent {r['entry_sentiment']:.2f}→{r['current_sentiment']:.2f} "
            f"peak_r={r['peak_return']*100:.1f}% [{r['reason']}]"
        )
    msg = "\n".join(lines)
    try:
        # Best-effort; runner may have telegram helper
        from phase6.core.telegram_notifier import send_telegram_message  # type: ignore

        send_telegram_message(msg)
    except Exception:
        try:
            logger.warning("[SENT-FADE] notify skipped (no telegram helper). msg=\n%s", msg)
        except Exception:
            pass


def backfill_lot_from_buy_trade(
    trade: Dict[str, Any],
    *,
    rsi: float,
    sentiment: float,
    path: Path = ENTRY_LOTS_PATH,
) -> Dict[str, Any]:
    """Tag an existing open position from a historical BUY + current/historical rsi/sent."""
    pair = str(trade.get("pair"))
    ed = classify_entry_drivers(pair, rsi, sentiment, reason=str(trade.get("reason") or ""))
    qty = trade.get("qty")
    entry = _f(trade.get("entry_price"), 0.0)
    usd = _f(qty, 0.0) * entry if qty is not None else _f(trade.get("usd"), 0.0)
    return record_entry_lot(
        pair=pair,
        entry_price=entry,
        usd=usd,
        drivers=ed,
        order_id=trade.get("order_id"),
        qty=_f(qty) if qty is not None else None,
        path=path,
    )


if __name__ == "__main__":
    # Quick self-check
    ed = classify_entry_drivers("LINK-USD", 46.6, 0.89)
    assert ed.sentiment_only, ed
    g = apply_buy_size_gates(
        "LINK-USD",
        1925.0,
        rsi=46.6,
        sentiment=0.89,
        equity_usd=2372.0,
        current_pair_usd=0.0,
        rebalance_cap_usd=100.0,
        free_cash_usd=1975.0,
        emergency_recovery=True,
    )
    print("LINK case:", g.as_dict())
    assert g.final_usd <= 100.0 + 1e-6
    assert g.haircut_applied and g.ticket_cap_applied
    print("ok")
