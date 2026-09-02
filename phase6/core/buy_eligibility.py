"""
Hard BUY eligibility gates — basket membership + required RSI/sentiment.

P0 (2026-09-01): Ignition scout / opportunity_pool could append BUY actions for
pairs outside the trading basket (e.g. OP-USD) and those actions skipped the
post-filter stack (regime_cash / quality_tryout). That produced live fills with
no Signals-pane membership and weak/missing RSI coverage — the pile-on→SL pattern.

Rules (BUY only; SELL always kept):
1. Pair must be in trading basket OR explicit ballast (PAXG/USDC cash park).
2. Non-ballast BUY requires finite RSI and finite sentiment (from runner caches
   or stamped on the action). Missing either → block.
3. enforce=True drops; enforce=False keeps but logs WOULD_BLOCK (shadow).

Call this AFTER every plan mutation (allocator, ignition, etc.) and again
immediately before execute.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

logger = logging.getLogger("phase6.buy_eligibility")

# Default ballast — cash/metal park, not opportunity alts
_DEFAULT_BALLAST = frozenset({"PAXG-USD", "PAXG-USDC", "USDC-USD", "USD-USDC"})


def _norm(pair: str) -> str:
    return str(pair or "").strip().upper().replace("_", "-")


def load_trading_basket_set() -> Set[str]:
    try:
        from phase6.core.paths import load_trading_basket

        return {_norm(p) for p in (load_trading_basket() or []) if p}
    except Exception as e:
        logger.warning("[BUY-ELIG] load_trading_basket failed: %s", e)
        return set()


def load_ballast_set(config_dict: Optional[Dict[str, Any]] = None) -> Set[str]:
    out = set(_DEFAULT_BALLAST)
    cfg = config_dict or {}
    try:
        life = (cfg.get("run_lifecycle") or {}) if isinstance(cfg, dict) else {}
        ign = life.get("ignition_scout") or {}
        for p in ign.get("ballast_pairs") or []:
            out.add(_norm(p))
        for p in (life.get("dual_peak_exit") or {}).get("ballast_pairs") or []:
            out.add(_norm(p))
        p6 = cfg.get("phase_6_specific") or {}
        for p in p6.get("ballast_pairs") or []:
            out.add(_norm(p))
    except Exception:
        pass
    return out


def _finite_num(v: Any) -> Optional[float]:
    """Accept bare float or nested cache dicts like {'rsi': 44.1} / {'score': 0.5}."""
    if v is None:
        return None
    if isinstance(v, dict):
        for key in ("rsi", "value", "score", "sentiment", "eng_sent", "entry_rsi", "entry_sentiment"):
            if key in v and v[key] is not None:
                return _finite_num(v[key])
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def normalize_rsi_map(rsi_values: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Flatten rsi_cache-style maps to {pair: float}."""
    out: Dict[str, float] = {}
    if not isinstance(rsi_values, dict) or not rsi_values:
        return out
    src: Dict[str, Any] = rsi_values
    nested = src.get("rsi")
    if isinstance(nested, dict):
        src = nested
    for k, v in src.items():
        # skip non-pair meta keys if someone passes the full cache without nested unwrap
        if str(k) in ("timestamp", "calls_made", "universe", "errors", "schema_version", "merge_mode", "updated_pairs", "note"):
            continue
        f = _finite_num(v)
        if f is not None:
            out[_norm(str(k))] = f
            out[str(k)] = f
    return out


def load_rsi_map_from_cache() -> Dict[str, float]:
    try:
        import json
        from pathlib import Path

        from phase6.core.paths import RSI_CACHE

        raw = json.loads(Path(RSI_CACHE).read_text())
        return normalize_rsi_map(raw if isinstance(raw, dict) else {})
    except Exception:
        return {}


def evaluate_buy_eligibility(
    pair: str,
    *,
    basket: Optional[Set[str]] = None,
    ballast: Optional[Set[str]] = None,
    rsi: Any = None,
    sentiment: Any = None,
    require_signals: bool = True,
) -> Dict[str, Any]:
    """
    Return {allowed: bool, reasons: [str], in_basket, is_ballast, rsi, sentiment}.
    """
    pn = _norm(pair)
    bask = basket if basket is not None else load_trading_basket_set()
    ball = ballast if ballast is not None else load_ballast_set()
    in_basket = pn in bask
    is_ballast = pn in ball
    reasons: List[str] = []

    if not in_basket and not is_ballast:
        reasons.append("not_in_trading_basket")

    rsi_f = _finite_num(rsi)
    sent_f = _finite_num(sentiment)

    if require_signals and not is_ballast:
        if rsi_f is None:
            reasons.append("missing_rsi")
        if sent_f is None:
            reasons.append("missing_sentiment")

    return {
        "allowed": len(reasons) == 0,
        "reasons": reasons,
        "in_basket": in_basket,
        "is_ballast": is_ballast,
        "rsi": rsi_f,
        "sentiment": sent_f,
        "pair": pn,
    }


def filter_trade_plan_buy_eligibility(
    plan: Any,
    *,
    rsi_values: Optional[Dict[str, Any]] = None,
    sentiment_scores: Optional[Dict[str, Any]] = None,
    basket: Optional[Iterable[str]] = None,
    ballast: Optional[Iterable[str]] = None,
    config_dict: Optional[Dict[str, Any]] = None,
    require_signals: bool = True,
    enforce: bool = True,
) -> Any:
    """
    Drop BUY actions that fail basket membership and/or RSI+sentiment presence.
    Mutates plan.actions when enforce=True.
    """
    if plan is None or not getattr(plan, "actions", None):
        return plan

    bask = {_norm(p) for p in (basket if basket is not None else load_trading_basket_set())}
    if ballast is not None:
        ball = {_norm(p) for p in ballast}
    else:
        ball = load_ballast_set(config_dict)

    rsi_flat = normalize_rsi_map(rsi_values)
    if not rsi_flat:
        rsi_flat = load_rsi_map_from_cache()
    sentiment_scores = sentiment_scores or {}

    def _lookup_sent(m: Dict[str, Any], pair: str) -> Any:
        if pair in m:
            return m[pair]
        pn = _norm(pair)
        if pn in m:
            return m[pn]
        for k, v in m.items():
            if _norm(k) == pn:
                return v
        return None

    kept: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []

    for a in list(plan.actions or []):
        if not isinstance(a, dict):
            kept.append(a)
            continue
        action = str(a.get("action") or a.get("side") or "").upper()
        pair = a.get("pair")
        if action != "BUY" or not pair:
            kept.append(a)
            continue

        # Prefer live caches; fall back to action stamps (ignition may set them)
        rsi = rsi_flat.get(_norm(str(pair)))
        if rsi is None:
            rsi = rsi_flat.get(str(pair))
        if rsi is None:
            rsi = a.get("entry_rsi") if a.get("entry_rsi") is not None else a.get("rsi")
        sent = _lookup_sent(sentiment_scores, str(pair))
        if sent is None:
            sent = (
                a.get("entry_sentiment")
                if a.get("entry_sentiment") is not None
                else a.get("sentiment")
            )

        dec = evaluate_buy_eligibility(
            str(pair),
            basket=bask,
            ballast=ball,
            rsi=rsi,
            sentiment=sent,
            require_signals=require_signals,
        )
        if dec["allowed"]:
            a["buy_eligibility"] = "ok"
            kept.append(a)
        else:
            blocked.append(
                {
                    "pair": pair,
                    "usd": a.get("usd") or a.get("usd_amount"),
                    "reasons": dec["reasons"],
                    "ignition_scout": bool(a.get("ignition_scout")),
                }
            )
            logger.info(
                "[BUY-ELIG] %s BUY %s reasons=%s ignition=%s enforce=%s",
                "BLOCK" if enforce else "WOULD_BLOCK",
                pair,
                dec["reasons"],
                bool(a.get("ignition_scout")),
                enforce,
            )
            if not enforce:
                a["buy_eligibility"] = "would_block:" + ",".join(dec["reasons"])
                kept.append(a)

    if enforce:
        plan.actions = kept
    try:
        plan.buy_eligibility_blocked = blocked  # type: ignore[attr-defined]
    except Exception:
        pass
    return plan


def pair_in_live_buy_universe(
    pair: str,
    *,
    basket: Optional[Sequence[str]] = None,
    ballast: Optional[Sequence[str]] = None,
    config_dict: Optional[Dict[str, Any]] = None,
) -> bool:
    """True if pair may ever receive a live BUY (basket or ballast)."""
    bask = {_norm(p) for p in (basket if basket is not None else load_trading_basket_set())}
    ball = (
        {_norm(p) for p in ballast}
        if ballast is not None
        else load_ballast_set(config_dict)
    )
    pn = _norm(pair)
    return pn in bask or pn in ball
