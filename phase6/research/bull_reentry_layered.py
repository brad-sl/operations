#!/usr/bin/env python3
"""Bull re-entry layered timing — pure functions (spec-frozen 2026-07-30).

See docs/research/BULL_REENTRY_LAYERED_SPEC.md.
No live side effects. Used by offline stress + future feature-flagged live hook.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

# --- frozen knobs (spec) ---
LOOKBACK_BULL_D = 30
BULL_RET_PCT = 15.0
BEAR_RET_PCT = -10.0
FLAT_ABS_PCT = 8.0

BREAKOUT_HIGH_D = 30
BREAKOUT_EXIT_LOW_D = 20
BREAKOUT_EXIT_RET14_PCT = -5.0
BREAKOUT_ENTER_RET14_MIN = 0.0

RSI_PERIOD = 14
RSI_BAND_LO = 50.0
RSI_BAND_HI = 70.0

CAP_PARK = 0.0
CAP_REENTRY = 75.0  # flat option B size
CAP_BULL = 200.0


def rolling_return_pct(
    days: Sequence[date],
    px: Dict[date, float],
    i: int,
    lookback_days: int,
) -> Optional[float]:
    if i < 1 or i >= len(days):
        return None
    d = days[i]
    target = d - timedelta(days=lookback_days)
    j = i
    while j > 0 and days[j] > target:
        j -= 1
    p0 = px.get(days[j])
    p1 = px.get(d)
    if not p0 or not p1 or p0 <= 0:
        return None
    return (p1 / p0 - 1.0) * 100.0


def rsi_series(closes: Sequence[float], period: int = RSI_PERIOD) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = [0.0] * len(closes)
    losses = [0.0] * len(closes)
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        gains[i] = max(ch, 0.0)
        losses[i] = max(-ch, 0.0)
    for i in range(period, len(closes)):
        ag = sum(gains[i - period + 1 : i + 1]) / period
        al = sum(losses[i - period + 1 : i + 1]) / period
        if al <= 1e-12:
            out[i] = 100.0
        else:
            rs = ag / al
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def regime_label_from_ret30(r30: Optional[float]) -> str:
    if r30 is None:
        return "unknown"
    if r30 >= BULL_RET_PCT:
        return "bull"
    if r30 <= BEAR_RET_PCT:
        return "bear"
    if abs(r30) <= FLAT_ABS_PCT:
        return "flat"
    return "transition"


@dataclass
class LayeredSignal:
    as_of: str
    btc_ret_30: Optional[float]
    btc_ret_14: Optional[float]
    rsi: Optional[float]
    breakout_on: bool
    regime_label: str
    layer: str
    cap_usd: float
    allow_new_buys: bool
    allocator_preference: str  # rebalance | rotation | park
    reasons: List[str]


def step_breakout_state(
    *,
    prev_on: bool,
    days: Sequence[date],
    px: Dict[date, float],
    i: int,
    r14: Optional[float],
) -> bool:
    """Sticky breakout state machine (spec)."""
    if i < BREAKOUT_HIGH_D:
        return False
    d = days[i]
    price = px[d]
    prior_high = max(px[days[k]] for k in range(i - (BREAKOUT_HIGH_D - 1), i))
    new_high = price >= prior_high
    w_low = [px[days[k]] for k in range(i - (BREAKOUT_EXIT_LOW_D - 1), i + 1)]
    on = prev_on
    if not on:
        if new_high and (r14 is not None and r14 > BREAKOUT_ENTER_RET14_MIN):
            on = True
    else:
        if price < min(w_low) or (r14 is not None and r14 < BREAKOUT_EXIT_RET14_PCT):
            on = False
    return on


def resolve_layered_cap(
    *,
    regime_label: str,
    btc_ret_30: Optional[float],
    breakout_on: bool,
    rsi: Optional[float],
    flat_deploy_without_breakout: bool = True,
) -> Tuple[str, float, bool, str, List[str]]:
    """
    Returns layer, cap_usd, allow_new_buys, allocator_preference, reasons.

    flat_deploy_without_breakout: if True, detector flat keeps $75 (live B path).
    """
    reasons: List[str] = []
    bear = regime_label == "bear" or (
        btc_ret_30 is not None and btc_ret_30 <= BEAR_RET_PCT
    )
    if bear:
        reasons.append("bear_veto")
        return "bear_park", CAP_PARK, False, "park", reasons

    if regime_label == "bull" or (
        btc_ret_30 is not None and btc_ret_30 >= BULL_RET_PCT
    ):
        reasons.append("size_up_30d_bull")
        return "bull_size_up", CAP_BULL, True, "rotation_or_bull_knobs", reasons

    rsi_ok = rsi is not None and RSI_BAND_LO <= rsi <= RSI_BAND_HI
    if breakout_on and rsi_ok:
        reasons.append("reentry_breakout_rsi_band")
        return "reentry_flat_b", CAP_REENTRY, True, "rebalance", reasons

    if breakout_on and not rsi_ok:
        reasons.append(f"breakout_on_but_rsi_out_of_band rsi={rsi}")

    if flat_deploy_without_breakout and regime_label == "flat":
        reasons.append("flat_option_b_live_path")
        return "flat_b", CAP_REENTRY, True, "rebalance", reasons

    reasons.append("transition_or_no_trigger_park")
    return "park", CAP_PARK, False, "park", reasons


def build_signal_series(
    days: List[date],
    btc_px: Dict[date, float],
    *,
    flat_deploy_without_breakout: bool = True,
) -> List[LayeredSignal]:
    closes = [btc_px[d] for d in days]
    rsis = rsi_series(closes, RSI_PERIOD)
    out: List[LayeredSignal] = []
    brk = False
    for i, d in enumerate(days):
        r30 = rolling_return_pct(days, btc_px, i, LOOKBACK_BULL_D)
        r14 = rolling_return_pct(days, btc_px, i, 14)
        brk = step_breakout_state(prev_on=brk, days=days, px=btc_px, i=i, r14=r14)
        lab = regime_label_from_ret30(r30)
        layer, cap, buys, alloc, reasons = resolve_layered_cap(
            regime_label=lab,
            btc_ret_30=r30,
            breakout_on=brk,
            rsi=rsis[i],
            flat_deploy_without_breakout=flat_deploy_without_breakout,
        )
        rsi_v = rsis[i]
        out.append(
            LayeredSignal(
                as_of=d.isoformat(),
                btc_ret_30=None if r30 is None else round(r30, 3),
                btc_ret_14=None if r14 is None else round(r14, 3),
                rsi=None if rsi_v is None else round(float(rsi_v), 2),
                breakout_on=brk,
                regime_label=lab,
                layer=layer,
                cap_usd=cap,
                allow_new_buys=buys,
                allocator_preference=alloc,
                reasons=reasons,
            )
        )
    return out
