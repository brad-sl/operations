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
    # Boundary layer (observability + shadow). Does not change live park until promote.
    regime_layer: str = ""
    layer_label: str = ""
    shadow_stance: str = ""

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
            soft_up_width_pct=float(det_cfg.get("soft_up_width_pct", 2.0)),
            pre_bull_width_pct=float(det_cfg.get("pre_bull_width_pct", 1.0)),
            use_live_price=bool(det_cfg.get("use_live_price", True)),
        )
    regime = str(detection.get("regime") or "unknown")
    regime_layer = str(detection.get("regime_layer") or regime or "unknown")
    # Signed residual safety: downside must not inherit upside transition deploy
    try:
        btc_r = detection.get("btc_return_pct")
        btc_f = float(btc_r) if btc_r is not None else None
    except (TypeError, ValueError):
        btc_f = None
    if regime_layer == "soft_down" or (
        regime == "transition" and btc_f is not None and btc_f < 0
    ):
        regime = "soft_down"
        if regime_layer in ("", "transition", "unknown"):
            regime_layer = "soft_down"
    layer_label = str(detection.get("layer_label") or "")
    shadow_stance = str(detection.get("shadow_stance") or "")
    regimes = pol.get("regimes") or {}
    entry = deepcopy(regimes.get(regime) or regimes.get("unknown") or {})
    entry = _merge_knob_map(regime, pol, entry)

    snap = RegimeCashSnapshot(
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
        regime_layer=regime_layer,
        layer_label=layer_label,
        shadow_stance=shadow_stance,
    )
    # Recovery soft_down / quality_tryout: clamp bull deploy sleeve (default $75)
    return apply_recovery_cap_to_snapshot(snap, policy=pol)


def _normalize_pair_symbol(pair: str) -> str:
    p = (pair or "").strip().upper().replace("_", "-")
    if p and "-" not in p and p.endswith("USD") and not p.endswith("-USD"):
        p = p[:-3] + "-USD"
    return p


def _add_block_pairs(out: Set[str], xs: Any) -> None:
    if not xs:
        return
    if isinstance(xs, str):
        xs = [xs]
    try:
        for x in xs:
            n = _normalize_pair_symbol(str(x))
            if n:
                out.add(n)
    except TypeError:
        return


def collect_buy_block_pairs(
    policy: Optional[Dict[str, Any]] = None,
    *,
    trading_config: Optional[Dict[str, Any]] = None,
) -> Set[str]:
    """Union of deny lists: regime_cash_policy + trading_config + recovery overlay."""
    out: Set[str] = set()
    pol = policy if isinstance(policy, dict) else {}
    _add_block_pairs(out, pol.get("buy_block_pairs"))
    _add_block_pairs(out, pol.get("pair_buy_blocklist"))
    _add_block_pairs(out, pol.get("new_buy_block_list"))

    oo = pol.get("operator_override") if isinstance(pol.get("operator_override"), dict) else {}
    rec = oo.get("recovery_soft_down_20260828") if isinstance(oo, dict) else None
    if isinstance(rec, dict) and rec.get("enabled"):
        _add_block_pairs(out, rec.get("block_new_buy_pairs"))

    tc = trading_config
    if tc is None:
        try:
            tc_path = PROJECT_ROOT / "config" / "trading_config_phase6.json"
            if tc_path.exists():
                tc = json.loads(tc_path.read_text(encoding="utf-8"))
        except Exception:
            tc = None
    if isinstance(tc, dict):
        for blob in (tc.get("global_settings") or {}, tc.get("risk_management") or {}):
            if isinstance(blob, dict):
                _add_block_pairs(out, blob.get("buy_block_pairs"))
                _add_block_pairs(out, blob.get("pair_buy_blocklist"))
                _add_block_pairs(out, blob.get("new_buy_block_list"))
    return out


def _recovery_rec(policy: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    pol = policy if isinstance(policy, dict) else {}
    oo = pol.get("operator_override") if isinstance(pol.get("operator_override"), dict) else {}
    rec = oo.get("recovery_soft_down_20260828") if isinstance(oo, dict) else None
    if isinstance(rec, dict) and rec.get("enabled"):
        return rec
    return None


def _equity_health_hit_for_recovery(
    rec: Dict[str, Any],
    *,
    snap: Optional[RegimeCashSnapshot] = None,
) -> bool:
    """True when soft_down/declining path should enforce recovery new-seat rules."""
    health_hit = False
    if snap is not None:
        if str(getattr(snap, "regime", "") or "").lower() in (
            "soft_down",
            "soft_downtrend",
            "declining",
            "hard_down",
            "bear",
        ):
            health_hit = True
        if str(getattr(snap, "regime_layer", "") or "").lower() in (
            "soft_down",
            "soft_downtrend",
            "declining",
            "hard_down",
        ):
            health_hit = True

    if health_hit:
        return True

    # Only live equity health — not recovery phase marker alone (that file
    # stays on disk after path improves and must not blanket-block all alts).
    want = {str(x).lower() for x in (rec.get("while_equity_health_in") or [])}
    want |= {"soft_down", "soft_downtrend", "declining", "hard_down"}
    for rel in (
        "data/state/trend_repair_status.json",
        "data/state/regime_cash_status.json",
    ):
        try:
            tp = PROJECT_ROOT / rel
            if not tp.exists():
                continue
            raw = json.loads(tp.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            states: List[str] = []
            et = raw.get("equity_trend") if isinstance(raw.get("equity_trend"), dict) else {}
            h = et.get("health") if isinstance(et, dict) else None
            if isinstance(h, dict):
                states.append(str(h.get("state") or h.get("label") or "").lower())
            elif h is not None:
                states.append(str(h).lower())
            for key in ("regime", "regime_layer", "health_state", "equity_health"):
                if raw.get(key) is not None:
                    states.append(str(raw.get(key)).lower())
            if any(any(w in s for w in want if w) for s in states if s):
                return True
        except Exception:
            continue
    return False


def _norm_pair_set(xs: Any) -> Set[str]:
    out: Set[str] = set()
    _add_block_pairs(out, xs)
    return out


def recovery_quality_tryout_cfg(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize quality_tryout knobs (Brad GO 2026-09-01 thaw A; v2 2026-09-05)."""
    qt = rec.get("quality_tryout") if isinstance(rec.get("quality_tryout"), dict) else {}
    v2 = qt.get("v2") if isinstance(qt.get("v2"), dict) else {}
    # v2 nested knobs override flat deploy floors when present
    src = {**qt, **v2}
    return {
        "tryout_pairs": _norm_pair_set(qt.get("tryout_pairs") or rec.get("tryout_pairs") or []),
        "min_sentiment": float(src.get("min_sentiment", rec.get("quality_min_sentiment", 0.30)) or 0.30),
        "max_rsi": float(src.get("max_rsi", rec.get("quality_max_rsi", 55.0)) or 55.0),
        "min_rsi": float(src.get("min_rsi", rec.get("quality_min_rsi", 0.0)) or 0.0),
        "max_new_seats_per_day": int(
            src.get("max_new_seats_per_day", rec.get("max_new_seats_per_day", 1)) or 1
        ),
        "abs_cap_usd": float(src.get("abs_cap_usd", rec.get("tryout_abs_cap_usd", 75.0)) or 75.0),
        "v2_dynamic": bool(qt.get("v2_dynamic") or v2.get("live_apply") or False),
    }


def recovery_tryout_pairs_effective(rec: Dict[str, Any]) -> Set[str]:
    """Tryout sleeve pairs for recovery: static list (v1) or ledger-qualified (v2)."""
    qt = recovery_quality_tryout_cfg(rec)
    mode = str(rec.get("new_alt_policy") or "")
    use_v2 = mode.startswith("quality_tryout_v2") or bool(qt.get("v2_dynamic"))
    if use_v2:
        try:
            from phase6.core.recovery_tryout_qualify import (
                STATE_PATH,
                evaluate_basket_tryout,
            )

            # Prefer fresh scoreboard file (≤30m) to avoid full ledger scan per buy
            try:
                if STATE_PATH.exists():
                    age_s = datetime.now(timezone.utc).timestamp() - STATE_PATH.stat().st_mtime
                    if age_s <= 1800:
                        board = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                        if isinstance(board.get("eligible_tryout_pairs"), list):
                            return _norm_pair_set(board.get("eligible_tryout_pairs") or [])
            except Exception:
                pass
            board = evaluate_basket_tryout(rec=rec)
            return _norm_pair_set(board.get("eligible_tryout_pairs") or [])
        except Exception as e:
            logger.warning("recovery_tryout v2 board failed; falling back to static: %s", e)
    return set(qt.get("tryout_pairs") or set())


def count_new_seat_buys_today(
    *,
    exclude_pairs: Optional[Set[str]] = None,
    ledger_path: Optional[Path] = None,
) -> int:
    """Count non-dust BUY fills today (UTC) for empty-seat thaw rate limit.

    Skips:
      - exclude_pairs (ballast)
      - rows tagged tryout_day_exempt / quality_tryout_exempt
      - full-day wipe when data/state/quality_tryout_day_clear.json matches today (Brad GO)
    """
    # Operator day wipe (Brad GO C 2026-09-01: OP missfire not a tryout seat)
    try:
        clear_path = PROJECT_ROOT / "data" / "state" / "quality_tryout_day_clear.json"
        if clear_path.exists():
            clr = json.loads(clear_path.read_text(encoding="utf-8"))
            today_s = datetime.now(timezone.utc).date().isoformat()
            if clr.get("clear") and str(clr.get("date") or "") == today_s:
                return 0
    except Exception:
        pass

    path = ledger_path or (PROJECT_ROOT / "trades" / "phase6_trades.jsonl")
    if not path.exists():
        return 0
    exclude = {_normalize_pair_symbol(x) for x in (exclude_pairs or set())}
    today = datetime.now(timezone.utc).date()
    n = 0
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                side = str(row.get("side") or "").upper()
                if side != "BUY":
                    continue
                if row.get("tryout_day_exempt") or row.get("quality_tryout_exempt"):
                    continue
                pair = _normalize_pair_symbol(str(row.get("pair") or ""))
                if not pair or pair in exclude:
                    continue
                ts_raw = row.get("timestamp") or row.get("ts") or ""
                try:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if ts.date() != today:
                    continue
                # skip dust — only when we can form a notional; missing fields ≠ dust
                try:
                    notional = row.get("usd")
                    if notional is None:
                        notional = row.get("notional")
                    if notional is None:
                        notional = row.get("notional_usd")
                    if notional is not None:
                        if abs(float(notional)) < 5.0:
                            continue
                    else:
                        qty = float(
                            row.get("qty")
                            or row.get("size")
                            or row.get("quantity")
                            or row.get("filled_size")
                            or 0
                        )
                        px = float(
                            row.get("entry_price")
                            or row.get("price")
                            or row.get("exit_price")
                            or 0
                        )
                        if qty > 0 and px > 0 and abs(qty * px) < 5.0:
                            continue
                        # if still no size signal, count the BUY (conservative rate-limit)
                except (TypeError, ValueError):
                    pass
                n += 1
    except OSError:
        return 0
    return n


def recovery_soft_down_blocks_pair(
    pair: str,
    *,
    policy: Optional[Dict[str, Any]] = None,
    is_new_pair: bool = False,
    snap: Optional[RegimeCashSnapshot] = None,
) -> Optional[str]:
    """
    Recovery gate (soft_down / declining equity path).

    Explicit block_new_buy_pairs always deny.

    Modes (new_alt_policy):
      - block_unless_allowlist: only allowlist_pairs may open new seats
      - quality_tryout: ballast allowlist OR static tryout_pairs may open new seats
      - quality_tryout_v2: ballast OR ledger-qualified tier B(/C) tryout pairs
        (sentiment/RSI floors applied in evaluate_buy_entry)
    """
    pol = policy if isinstance(policy, dict) else {}
    rec = _recovery_rec(pol)
    if not rec:
        return None

    p = _normalize_pair_symbol(pair)
    blocked = _norm_pair_set(rec.get("block_new_buy_pairs"))
    if p in blocked:
        return f"recovery_soft_down block_list {p}"

    if not is_new_pair:
        return None

    if not _equity_health_hit_for_recovery(rec, snap=snap):
        return None

    policy_mode = str(rec.get("new_alt_policy") or "")
    allow = _norm_pair_set(rec.get("allowlist_pairs"))

    # --- quality_tryout / v2 (Brad GO 2026-09-01 + 2026-09-05) ---
    if policy_mode.startswith("quality_tryout"):
        if p in allow:
            return None
        tryout = recovery_tryout_pairs_effective(rec)
        if p in tryout:
            return None
        # Richer v2 deny reasons (explainable board)
        if policy_mode.startswith("quality_tryout_v2") or bool(
            recovery_quality_tryout_cfg(rec).get("v2_dynamic")
        ):
            try:
                from phase6.core.recovery_tryout_qualify import evaluate_pair_tryout

                v = evaluate_pair_tryout(p, rec=rec)
                cls = str(v.class_ or "not_eligible")
                return f"recovery_soft_down quality_tryout_v2 {cls} {p}"
            except Exception:
                pass
        return f"recovery_soft_down quality_tryout not_eligible {p}"

    # --- legacy allowlist-only ---
    if not policy_mode.startswith("block_unless_allowlist"):
        return None

    if not allow:
        return None
    if p in allow:
        return None
    return f"recovery_soft_down allowlist new_alt {p}"


def apply_recovery_cap_to_snapshot(
    snap: RegimeCashSnapshot,
    *,
    policy: Optional[Dict[str, Any]] = None,
) -> RegimeCashSnapshot:
    """Clamp rebalance_cap while recovery quality_tryout / soft_down path is active."""
    pol = policy if isinstance(policy, dict) else load_policy()
    rec = _recovery_rec(pol)
    if not rec:
        return snap
    if not _equity_health_hit_for_recovery(rec, snap=snap):
        return snap
    cap_max = rec.get("bull_rebalance_cap_usd_max")
    if cap_max is None:
        return snap
    try:
        cap_f = float(cap_max)
    except (TypeError, ValueError):
        return snap
    if cap_f < 0:
        return snap
    cur = float(snap.rebalance_cap_usd or 0.0)
    if cur <= 0:
        return snap
    if cur <= cap_f:
        return snap
    snap.rebalance_cap_usd = cap_f
    return snap


def evaluate_buy_entry(
    pair: str,
    snap: RegimeCashSnapshot,
    *,
    sentiment: Optional[float],
    rsi: Optional[float],
    lockout_pairs: Optional[Set[str]] = None,
    is_new_pair: bool = False,
    policy: Optional[Dict[str, Any]] = None,
) -> EntryDecision:
    reasons: List[str] = []
    lockout_pairs = lockout_pairs or set()
    eg = snap.entry

    if not snap.allow_new_buys or snap.strategy_mode == "usdc_park":
        reasons.append(f"regime_cash_park mode={snap.strategy_mode} allow_new_buys={snap.allow_new_buys}")
        return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)

    # BUY_BLOCK_PAIRS_RECOVERY_SOFT_DOWN_20260828 — config deny lists must stop fills
    try:
        pol = policy if isinstance(policy, dict) else load_policy()
    except Exception:
        pol = {}
    pair_n = _normalize_pair_symbol(pair)
    blocks = collect_buy_block_pairs(pol if isinstance(pol, dict) else {})
    if pair_n in blocks:
        reasons.append(f"buy_block_pairs {pair_n}")
        return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)
    rec_reason = recovery_soft_down_blocks_pair(
        pair,
        policy=pol if isinstance(pol, dict) else {},
        is_new_pair=bool(is_new_pair),
        snap=snap,
    )
    if rec_reason:
        reasons.append(rec_reason)
        return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)

    # Quality tryout floors + max 1 new seat/day (while recovery health binds)
    rec = _recovery_rec(pol if isinstance(pol, dict) else {})
    qt_cfg: Optional[Dict[str, Any]] = None
    on_tryout = False
    if rec and bool(is_new_pair) and _equity_health_hit_for_recovery(rec, snap=snap):
        mode = str(rec.get("new_alt_policy") or "")
        if mode.startswith("quality_tryout"):
            qt_cfg = recovery_quality_tryout_cfg(rec)
            tryout_set = recovery_tryout_pairs_effective(rec)
            ballast = _norm_pair_set(rec.get("allowlist_pairs"))
            on_tryout = pair_n in tryout_set and pair_n not in ballast
            if on_tryout:
                already = count_new_seat_buys_today(exclude_pairs=ballast)
                max_day = int(qt_cfg.get("max_new_seats_per_day") or 1)
                if already >= max_day:
                    reasons.append(
                        f"recovery_soft_down quality_tryout max_new_seats_per_day {already}>={max_day}"
                    )
                    return EntryDecision(
                        pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi
                    )

    # Miss-fire probation — ledger launch→no-explode→hole (new seats + re-entry)
    try:
        from phase6.core.missfire_probation import evaluate_pair_missfire

        mf = evaluate_pair_missfire(pair_n, enforce=True)
        if mf.blocked:
            reasons.append(f"missfire_probation {mf.class_}: {'; '.join(mf.reasons[:2])}")
            return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)
    except Exception:
        pass

    if eg.get("require_lockout_clear", True) and pair in lockout_pairs:
        reasons.append("lockout_active")
        return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)

    min_s = float(eg.get("min_sentiment_new_pair" if is_new_pair else "min_sentiment") or -1.0)
    max_rsi = float(eg.get("max_rsi") or 100.0)
    min_rsi = 0.0
    # Stricter quality bar for week-1 tryout names under recovery
    if qt_cfg is not None and on_tryout:
        min_s = max(min_s, float(qt_cfg["min_sentiment"]))
        max_rsi = min(max_rsi, float(qt_cfg["max_rsi"]))
        min_rsi = float(qt_cfg.get("min_rsi") or 0.0)

    if sentiment is None:
        reasons.append("sentiment_missing")
        return EntryDecision(pair=pair, allowed=False, reasons=reasons, sentiment=sentiment, rsi=rsi)
    if float(sentiment) < min_s:
        reasons.append(f"sentiment {sentiment:.3f} < min {min_s}")

    if rsi is None:
        reasons.append("rsi_missing")
    else:
        if float(rsi) > max_rsi:
            reasons.append(f"rsi {rsi:.1f} > max_buy {max_rsi}")
        if min_rsi > 0 and float(rsi) < min_rsi:
            reasons.append(f"rsi {rsi:.1f} < min_buy {min_rsi}")

    allowed = len(reasons) == 0
    if allowed:
        if qt_cfg is not None and on_tryout:
            tag = "quality_tryout_v2" if (
                str(rec.get("new_alt_policy") or "").startswith("quality_tryout_v2")
                or bool(qt_cfg.get("v2_dynamic"))
            ) else "quality_tryout"
            reasons.append(f"entry_ok {tag}")
        else:
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


RSI_MEMORY_PATH = PROJECT_ROOT / "data/state/hard_exit_rsi_memory.json"


def _load_rsi_memory(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or RSI_MEMORY_PATH
    try:
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
    except Exception:
        pass
    return {"schema": "hard_exit_rsi_memory_v1", "pairs": {}}


def _save_rsi_memory(mem: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or RSI_MEMORY_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        mem = dict(mem or {})
        mem["schema"] = "hard_exit_rsi_memory_v1"
        mem["updated_at"] = datetime.now(timezone.utc).isoformat()
        p.write_text(json.dumps(mem, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[REGIME-HARD-EXIT] rsi memory write failed: %s", e)


def update_rsi_memory(
    rsi_values: Optional[Dict[str, float]],
    *,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Persist last RSI per pair for cross-up detection (call after gate eval)."""
    mem = _load_rsi_memory(path)
    pairs = dict(mem.get("pairs") or {})
    now = datetime.now(timezone.utc).isoformat()
    for pair, raw in (rsi_values or {}).items():
        try:
            v = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        prev = pairs.get(str(pair)) or {}
        pairs[str(pair)] = {
            "rsi": v,
            "prev_rsi": prev.get("rsi"),
            "as_of": now,
        }
    mem["pairs"] = pairs
    _save_rsi_memory(mem, path)
    return mem


def _parse_ts_flex(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def _last_buy_ts_for_pair(pair: str) -> Optional[datetime]:
    """Best-effort hold clock from ledger last BUY."""
    try:
        from phase6.core.paths import PROJECT_ROOT as ROOT

        trades = ROOT / "trades" / "phase6_trades.jsonl"
        if not trades.exists():
            return None
        last: Optional[datetime] = None
        with trades.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if str(r.get("pair") or "") != pair:
                    continue
                if str(r.get("side") or "").upper() != "BUY":
                    continue
                t = _parse_ts_flex(r.get("timestamp") or r.get("ts") or r.get("filled_at"))
                if t and (last is None or t > last):
                    last = t
        return last
    except Exception:
        return None


def evaluate_cautious_hard_gates(
    pair: str,
    *,
    regime: str,
    rsi: Optional[float],
    overbought: float,
    mark_r: Optional[float],
    hold_hours: Optional[float],
    prev_rsi: Optional[float],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Quality gates for cautious H3 (flat auto path).

    Returns {ok, reasons_fail, reasons_ok, auto_regime}.
    """
    c = cfg or {}
    if not c.get("enabled", False):
        return {
            "ok": True,
            "skipped": True,
            "reasons_fail": [],
            "reasons_ok": ["cautious_disabled"],
            "auto_regime": False,
        }
    auto_regs = {str(x).lower() for x in (c.get("auto_apply_regimes") or ["flat"])}
    auto_regime = str(regime or "").lower() in auto_regs
    fails: List[str] = []
    oks: List[str] = []

    min_hold = float(c.get("min_hold_hours") or 24.0)
    if hold_hours is None:
        fails.append("hold_hours_unknown")
    elif float(hold_hours) < min_hold:
        fails.append(f"hold {float(hold_hours):.1f}h < {min_hold}h")
    else:
        oks.append(f"hold {float(hold_hours):.1f}h")

    min_r = float(c.get("min_mark_r") if c.get("min_mark_r") is not None else 0.0)
    if mark_r is None:
        fails.append("mark_r_unknown")
    elif float(mark_r) < min_r:
        fails.append(f"mark_r {float(mark_r):.3f} < {min_r}")
    else:
        oks.append(f"mark_r {float(mark_r):.3f}")

    if c.get("require_rsi_cross", True):
        if rsi is None:
            fails.append("rsi_unknown")
        elif prev_rsi is None:
            # First observation while already overbought — do not treat as cross
            fails.append("rsi_cross_no_prev")
        elif float(prev_rsi) >= float(overbought):
            fails.append(f"rsi_no_cross prev {float(prev_rsi):.1f} already >= {overbought}")
        elif float(rsi) < float(overbought):
            fails.append(f"rsi {float(rsi):.1f} < {overbought}")
        else:
            oks.append(f"rsi_cross {float(prev_rsi):.1f}->{float(rsi):.1f}>={overbought}")
    else:
        oks.append("rsi_cross_not_required")

    return {
        "ok": len(fails) == 0,
        "skipped": False,
        "reasons_fail": fails,
        "reasons_ok": oks,
        "auto_regime": auto_regime,
    }


def _position_mark_and_hold(
    pair: str,
    position_meta: Optional[Dict[str, Any]],
) -> tuple[Optional[float], Optional[float]]:
    """Return (mark_r, hold_hours)."""
    meta = (position_meta or {}).get(pair) or {}
    mark_r: Optional[float] = None
    try:
        if meta.get("unrealized_pnl_pct") is not None:
            mark_r = float(meta["unrealized_pnl_pct"])
            # ledger sometimes stores  -3 for -3% vs -0.03
            if abs(mark_r) > 1.5:
                mark_r = mark_r / 100.0
        else:
            ep = float(meta.get("entry_price") or 0)
            cp = float(meta.get("current_price") or meta.get("price") or 0)
            if ep > 0 and cp > 0:
                mark_r = (cp - ep) / ep
    except (TypeError, ValueError):
        mark_r = None

    hold_hours: Optional[float] = None
    opened = _parse_ts_flex(
        meta.get("opened_at")
        or meta.get("entry_time")
        or meta.get("opened_at_utc")
        or meta.get("first_fill_at")
    )
    if opened is None:
        opened = _last_buy_ts_for_pair(pair)
    if opened is not None:
        hold_hours = (datetime.now(timezone.utc) - opened).total_seconds() / 3600.0
    return mark_r, hold_hours


def build_hard_exit_sell_actions(
    held_positions: Dict[str, float],
    snap: RegimeCashSnapshot,
    *,
    sentiment_scores: Optional[Dict[str, float]] = None,
    rsi_values: Optional[Dict[str, float]] = None,
    min_sell_usd: float = 25.0,
    max_pair_fraction: float = 1.0,
    existing_pairs: Optional[Set[str]] = None,
    position_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    cautious_cfg: Optional[Dict[str, Any]] = None,
    rsi_memory: Optional[Dict[str, Any]] = None,
    apply_cautious_filter: bool = True,
) -> List[Dict[str, Any]]:
    """Propose SELL actions for hard prefer_exit hits only.

    held_positions: pair → value_usd
    Does NOT include park_prefer_reduce.
    When cautious_flat enabled + apply_cautious_filter, drop proposals that fail
    quality gates (still logged via gate_fail on discarded list by caller if needed).
    """
    sentiment_scores = sentiment_scores or {}
    rsi_values = rsi_values or {}
    existing_pairs = existing_pairs or set()
    actions: List[Dict[str, Any]] = []
    frac = max(0.0, min(1.0, float(max_pair_fraction)))
    mem_pairs = (rsi_memory or {}).get("pairs") or {}
    overbought = float((snap.exit or {}).get("overbought_rsi") or 80.0)
    ccfg = cautious_cfg or {}

    for pair, raw_val in (held_positions or {}).items():
        try:
            val = float(raw_val or 0.0)
        except (TypeError, ValueError):
            continue
        if val < float(min_sell_usd):
            continue
        if pair in existing_pairs:
            continue
        rsi_v = rsi_values.get(pair)
        try:
            rsi_f = float(rsi_v) if rsi_v is not None else None
        except (TypeError, ValueError):
            rsi_f = None
        dec = prefer_exit(
            pair,
            snap,
            sentiment=sentiment_scores.get(pair),
            rsi=rsi_f,
        )
        hard = hard_exit_reasons(dec.reasons)
        if not hard:
            continue
        sell_usd = round(val * frac, 2)
        if sell_usd < float(min_sell_usd):
            continue

        mark_r, hold_hours = _position_mark_and_hold(pair, position_meta)
        prev_rsi = None
        try:
            prev_rsi = (mem_pairs.get(pair) or {}).get("rsi")
            if prev_rsi is not None:
                prev_rsi = float(prev_rsi)
        except (TypeError, ValueError):
            prev_rsi = None

        gate = evaluate_cautious_hard_gates(
            pair,
            regime=str(snap.regime or ""),
            rsi=rsi_f,
            overbought=overbought,
            mark_r=mark_r,
            hold_hours=hold_hours,
            prev_rsi=prev_rsi,
            cfg=ccfg if ccfg.get("enabled") else {"enabled": False},
        )
        # Cautious filter: only drop when enabled and hard was RSI-led
        # (sentiment_weak alone can still surface for operator without cross)
        hard_is_rsi = any("rsi_overbought" in str(h).lower() for h in hard)
        if (
            apply_cautious_filter
            and ccfg.get("enabled")
            and hard_is_rsi
            and not gate.get("skipped")
            and not gate.get("ok")
        ):
            logger.info(
                "[REGIME-HARD-EXIT] cautious drop %s fail=%s",
                pair,
                gate.get("reasons_fail"),
            )
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
                "cautious_gates": gate,
                "mark_r": mark_r,
                "hold_hours": hold_hours,
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
    position_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    rsi_memory_path: Optional[Path] = None,
) -> Any:
    """TG-02: attach hard-exit SELL proposals.

    Default: operator_approve blocks global live_apply.
    Cautious flat (2026-08-25): when cautious_flat.enabled and regime in
    auto_apply_regimes and proposal passes quality gates, merge that SELL
    even while operator_approve stays true for other regimes.
    """
    cfg = hard_cfg or {}
    if not cfg.get("enabled", False):
        return plan
    min_usd = float(cfg.get("min_sell_usd") or 25.0)
    max_frac = float(cfg.get("max_pair_fraction") or 1.0)
    shadow_only = bool(cfg.get("shadow_only", True))
    live_apply_global = bool(cfg.get("live_apply", False)) and not shadow_only
    operator = bool(cfg.get("operator_approve", True))
    ccfg = dict(cfg.get("cautious_flat") or {})

    existing = set()
    for a in list(getattr(plan, "actions", None) or []):
        if str(a.get("action") or a.get("side") or "").upper() == "SELL":
            p = a.get("pair")
            if p:
                existing.add(p)

    mem = _load_rsi_memory(rsi_memory_path)
    proposals = build_hard_exit_sell_actions(
        held_positions,
        snap,
        sentiment_scores=sentiment_scores,
        rsi_values=rsi_values,
        min_sell_usd=min_usd,
        max_pair_fraction=max_frac,
        existing_pairs=existing,
        position_meta=position_meta,
        cautious_cfg=ccfg,
        rsi_memory=mem,
        apply_cautious_filter=True,
    )

    # Which proposals may auto-merge under cautious flat?
    auto_regs = {str(x).lower() for x in (ccfg.get("auto_apply_regimes") or ["flat"])}
    regime_l = str(snap.regime or "").lower()
    cautious_auto_on = bool(ccfg.get("enabled")) and regime_l in auto_regs
    live_proposals: List[Dict[str, Any]] = []
    if live_apply_global and not operator:
        live_proposals = list(proposals)
    elif cautious_auto_on:
        for p in proposals:
            g = p.get("cautious_gates") or {}
            if g.get("ok") and g.get("auto_regime", True):
                q = dict(p)
                q["reason"] = "regime_hard_exit_cautious_flat"
                q["exit_class"] = "hard_exit_cautious_flat"
                live_proposals.append(q)

    live_apply = bool(live_proposals)

    try:
        plan.regime_hard_exit_proposals = proposals  # type: ignore[attr-defined]
        plan.regime_hard_exit_live_proposals = live_proposals  # type: ignore[attr-defined]
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
        "operator_approve": operator,
        "cautious_flat": {
            "enabled": bool(ccfg.get("enabled")),
            "auto_apply_regimes": list(auto_regs),
            "regime_match": cautious_auto_on,
            "n_live": len(live_proposals),
        },
        "proposals": proposals,
        "live_proposals": live_proposals,
        "n": len(proposals),
    }

    # Legacy global path: operator_approve forces shadow unless cautious live set
    if operator and not live_proposals:
        payload["live_apply"] = False
        payload["shadow_only"] = True

    out = shadow_log_path or (PROJECT_ROOT / "data/state/regime_hard_exit_shadow.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("[REGIME-HARD-EXIT] shadow write failed: %s", e)

    if proposals or live_proposals:
        logger.info(
            "[REGIME-HARD-EXIT] %s n=%s live_n=%s pairs=%s live=%s",
            "LIVE_APPLY" if live_apply else "SHADOW+NOTIFY",
            len(proposals),
            len(live_proposals),
            [p.get("pair") for p in proposals],
            [p.get("pair") for p in live_proposals],
        )
        # Always notify on new proposals (operator visibility); live still merges
        if bool(cfg.get("notify_telegram", True)) or operator or live_apply:
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

    if live_apply and live_proposals and getattr(plan, "actions", None) is not None:
        plan.actions = list(plan.actions) + live_proposals

    # Update RSI memory after eval so next cycle can detect cross
    try:
        update_rsi_memory(rsi_values, path=rsi_memory_path)
    except Exception as e:
        logger.warning("[REGIME-HARD-EXIT] rsi memory update failed: %s", e)

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
    policy: Optional[Dict[str, Any]] = None,
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
        is_new = pair not in held_pairs
        dec = evaluate_buy_entry(
            pair,
            snap,
            sentiment=sentiment_scores.get(pair),
            rsi=rsi_values.get(pair),
            lockout_pairs=lockout_pairs,
            is_new_pair=is_new,
            policy=policy,
        )
        if dec.allowed:
            # Quality tryout: haircut notional to abs_cap / recovery rebalance sleeve
            try:
                pol_f = policy if isinstance(policy, dict) else load_policy()
                rec_f = _recovery_rec(pol_f)
                if (
                    rec_f
                    and is_new
                    and _equity_health_hit_for_recovery(rec_f, snap=snap)
                    and str(rec_f.get("new_alt_policy") or "").startswith("quality_tryout")
                ):
                    qt = recovery_quality_tryout_cfg(rec_f)
                    pn = _normalize_pair_symbol(str(pair))
                    tryout_set = recovery_tryout_pairs_effective(rec_f)
                    ballast = _norm_pair_set(rec_f.get("allowlist_pairs"))
                    if pn in tryout_set and pn not in ballast:
                        caps = [float(qt.get("abs_cap_usd") or 75.0)]
                        if float(snap.rebalance_cap_usd or 0) > 0:
                            caps.append(float(snap.rebalance_cap_usd))
                        cap = min(caps)
                        for key in ("usd", "usd_amount", "notional_usd", "size_usd"):
                            if key in a and a[key] is not None:
                                try:
                                    prev = float(a[key])
                                    if prev > cap:
                                        a[key] = round(cap, 2)
                                        a["quality_tryout_cap_usd"] = cap
                                        a["quality_tryout"] = True
                                        if str(rec_f.get("new_alt_policy") or "").startswith(
                                            "quality_tryout_v2"
                                        ) or bool(qt.get("v2_dynamic")):
                                            a["quality_tryout_v2"] = True
                                except (TypeError, ValueError):
                                    pass
            except Exception:
                pass
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
        policy=pol,
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
        # Prefer portfolio enriched values when available + position meta for gates
        position_meta: Dict[str, Dict[str, Any]] = {}
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
                            position_meta[pair] = {
                                "entry_price": p.get("entry_price") or p.get("avg_entry"),
                                "current_price": p.get("current_price") or p.get("price"),
                                "unrealized_pnl_pct": p.get("unrealized_pnl_pct"),
                                "opened_at": p.get("opened_at") or p.get("entry_time"),
                                "value_usd": p.get("value_usd"),
                            }
        except Exception:
            pass
        # Fallback: runner.current_positions dict form
        try:
            pos = getattr(runner, "current_positions", None) or {}
            for k, v in pos.items():
                if not isinstance(v, dict):
                    continue
                pair = str(k)
                if pair not in position_meta:
                    position_meta[pair] = {
                        "entry_price": v.get("entry_price") or v.get("avg_entry"),
                        "current_price": v.get("current_price") or v.get("price"),
                        "unrealized_pnl_pct": v.get("unrealized_pnl_pct"),
                        "opened_at": v.get("opened_at") or v.get("entry_time"),
                        "value_usd": v.get("value_usd"),
                    }
        except Exception:
            pass
        plan = apply_hard_exit_to_plan(
            plan,
            snap,
            held_vals,
            sentiment_scores=sentiment_scores,
            rsi_values=rsi,
            hard_cfg=hard_cfg,
            position_meta=position_meta,
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
