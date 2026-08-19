#!/usr/bin/env python3
"""Squeeze → regime → confirm breakout helpers (research / paper only).

Spec: docs/research/SQUEEZE_REGIME_BREAKOUT_RESEARCH.md

No live orders. Pure bar math + light evaluators.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.research.bull_reentry_layered import (
    BEAR_RET_PCT,
    BULL_RET_PCT,
    FLAT_ABS_PCT,
    regime_label_from_ret30,
    rolling_return_pct,
    rsi_series,
)

# --- frozen v1 knobs ---
BB_PERIOD = 20
BB_STD = 2.0
KC_PERIOD = 20
KC_ATR_MULT = 1.5
ATR_PERIOD = 14
WIDTH_LOOKBACK = 100
WIDTH_PCTILE_MAX = 20.0  # compression if width percentile <= this
VOL_SMA = 20
VOL_SPIKE_MULT = 1.5
RANGE_LOOKBACK = 20  # break vs prior N bars high/low (excl today)
EFFICIENCY_MIN = 0.55
COIL_LOOKBACK_BARS = 5
ATR_RISING_SMA = 20


def _sma(xs: Sequence[float], n: int, i: int) -> Optional[float]:
    if i + 1 < n or n <= 0:
        return None
    chunk = xs[i + 1 - n : i + 1]
    if len(chunk) < n:
        return None
    return sum(chunk) / n


def _stdev(xs: Sequence[float], n: int, i: int) -> Optional[float]:
    m = _sma(xs, n, i)
    if m is None:
        return None
    chunk = xs[i + 1 - n : i + 1]
    var = sum((x - m) ** 2 for x in chunk) / n
    return var ** 0.5


def true_range(h: float, l: float, prev_c: float) -> float:
    return max(h - l, abs(h - prev_c), abs(l - prev_c))


def atr_series(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = ATR_PERIOD,
) -> List[Optional[float]]:
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < 2:
        return out
    trs = [0.0] * n
    trs[0] = highs[0] - lows[0]
    for i in range(1, n):
        trs[i] = true_range(highs[i], lows[i], closes[i - 1])
    for i in range(period - 1, n):
        out[i] = sum(trs[i + 1 - period : i + 1]) / period
    return out


def bb_width_series(
    closes: Sequence[float],
    period: int = BB_PERIOD,
    num_std: float = BB_STD,
) -> List[Optional[float]]:
    """(upper-lower)/mid = 2*std*num_std / sma."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    for i in range(n):
        m = _sma(closes, period, i)
        sd = _stdev(closes, period, i)
        if m is None or sd is None or m <= 0:
            continue
        width = (2.0 * num_std * sd) / m
        out[i] = width
    return out


def width_percentile(
    widths: Sequence[Optional[float]],
    i: int,
    lookback: int = WIDTH_LOOKBACK,
) -> Optional[float]:
    """Percentile rank of widths[i] in trailing lookback window (0-100)."""
    w = widths[i] if i < len(widths) else None
    if w is None:
        return None
    start = max(0, i + 1 - lookback)
    hist = [widths[j] for j in range(start, i + 1) if widths[j] is not None]
    if len(hist) < max(20, lookback // 5):
        return None
    below = sum(1 for x in hist if x is not None and x <= w)
    return 100.0 * below / len(hist)


def keltner_bounds(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    period: int = KC_PERIOD,
    atr_mult: float = KC_ATR_MULT,
    atrs: Optional[Sequence[Optional[float]]] = None,
) -> Optional[Tuple[float, float, float]]:
    mid = _sma(closes, period, i)
    atrs = atrs or atr_series(highs, lows, closes)
    a = atrs[i] if i < len(atrs) else None
    if mid is None or a is None:
        return None
    return mid - atr_mult * a, mid, mid + atr_mult * a


def bb_bounds(
    closes: Sequence[float],
    i: int,
    period: int = BB_PERIOD,
    num_std: float = BB_STD,
) -> Optional[Tuple[float, float, float]]:
    m = _sma(closes, period, i)
    sd = _stdev(closes, period, i)
    if m is None or sd is None:
        return None
    return m - num_std * sd, m, m + num_std * sd


def ttm_squeeze_on(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    atrs: Optional[Sequence[Optional[float]]] = None,
) -> bool:
    """Classic TTM-style: Bollinger inside Keltner."""
    bb = bb_bounds(closes, i)
    kc = keltner_bounds(highs, lows, closes, i, atrs=atrs)
    if bb is None or kc is None:
        return False
    bb_lo, _, bb_hi = bb
    kc_lo, _, kc_hi = kc
    return bb_lo >= kc_lo and bb_hi <= kc_hi


@dataclass
class CompressionState:
    on: bool
    bb_width: Optional[float] = None
    width_pctile: Optional[float] = None
    width_compress: bool = False
    ttm_squeeze: bool = False
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compression_at(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    *,
    widths: Optional[Sequence[Optional[float]]] = None,
    atrs: Optional[Sequence[Optional[float]]] = None,
) -> CompressionState:
    widths = widths or bb_width_series(closes)
    w = widths[i] if i < len(widths) else None
    pct = width_percentile(widths, i)
    width_ok = pct is not None and pct <= WIDTH_PCTILE_MAX
    ttm = ttm_squeeze_on(highs, lows, closes, i, atrs=atrs)
    reasons = []
    if width_ok:
        reasons.append(f"width_pctile={pct:.1f}<={WIDTH_PCTILE_MAX}")
    if ttm:
        reasons.append("ttm_bb_inside_kc")
    if not reasons:
        reasons.append("no_compression")
    return CompressionState(
        on=bool(width_ok or ttm),
        bb_width=w,
        width_pctile=pct,
        width_compress=bool(width_ok),
        ttm_squeeze=ttm,
        reasons=reasons,
    )


def compression_recent(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    i: int,
    lookback: int = COIL_LOOKBACK_BARS,
    **kwargs: Any,
) -> bool:
    start = max(0, i - lookback + 1)
    for j in range(start, i + 1):
        if compression_at(highs, lows, closes, j, **kwargs).on:
            return True
    return False


def prior_range(
    highs: Sequence[float],
    lows: Sequence[float],
    i: int,
    lookback: int = RANGE_LOOKBACK,
) -> Optional[Tuple[float, float]]:
    """High/low of bars [i-lookback, i) — excludes bar i."""
    if i < 1:
        return None
    a = max(0, i - lookback)
    b = i  # exclusive
    if b <= a:
        return None
    return max(highs[a:b]), min(lows[a:b])


def candle_efficiency(o: float, h: float, l: float, c: float) -> Optional[float]:
    rng = h - l
    if rng <= 1e-12:
        return None
    return abs(c - o) / rng


@dataclass
class ConfirmState:
    break_up: bool
    break_down: bool
    vol_ok: bool
    atr_rising: bool
    efficiency: Optional[float]
    efficiency_ok: bool
    confirm_up: bool
    confirm_down: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def confirm_break(
    *,
    o: float,
    h: float,
    l: float,
    c: float,
    volume: float,
    volumes: Sequence[float],
    atrs: Sequence[Optional[float]],
    i: int,
    range_hi: Optional[float],
    range_lo: Optional[float],
    vol_mult: float = VOL_SPIKE_MULT,
    eff_min: float = EFFICIENCY_MIN,
) -> ConfirmState:
    reasons: List[str] = []
    break_up = range_hi is not None and c > range_hi
    break_down = range_lo is not None and c < range_lo
    if break_up:
        reasons.append("close_above_range")
    if break_down:
        reasons.append("close_below_range")

    vol_sma = _sma(list(volumes), VOL_SMA, i)
    vol_ok = vol_sma is not None and vol_sma > 0 and volume >= vol_mult * vol_sma
    if vol_ok:
        reasons.append(f"vol>={vol_mult}x")
    else:
        reasons.append("vol_weak")

    atr_i = atrs[i] if i < len(atrs) else None
    atr_ma = None
    if atr_i is not None:
        # SMA of ATR values that exist
        chunk: List[float] = []
        for j in range(max(0, i + 1 - ATR_RISING_SMA), i + 1):
            aj = atrs[j]
            if aj is not None:
                chunk.append(float(aj))
        if len(chunk) >= max(5, ATR_RISING_SMA // 2):
            atr_ma = sum(chunk) / len(chunk)
    atr_rising = atr_i is not None and atr_ma is not None and atr_i >= atr_ma
    if atr_rising:
        reasons.append("atr_rising")
    else:
        reasons.append("atr_not_rising")

    eff = candle_efficiency(o, h, l, c)
    eff_ok = eff is not None and eff >= eff_min
    if eff_ok:
        reasons.append(f"eff={eff:.2f}")
    else:
        reasons.append("eff_weak")

    # H3 core confirm: break + vol + atr (efficiency is M1 optional layer)
    core_up = break_up and vol_ok and atr_rising
    core_dn = break_down and vol_ok and atr_rising
    # close quality: for up, close in upper half of candle
    if core_up and h > l and (c - l) / (h - l) < 0.5:
        core_up = False
        reasons.append("up_close_not_strong")
    if core_dn and h > l and (h - c) / (h - l) < 0.5:
        core_dn = False
        reasons.append("dn_close_not_strong")

    return ConfirmState(
        break_up=break_up,
        break_down=break_down,
        vol_ok=vol_ok,
        atr_rising=atr_rising,
        efficiency=eff,
        efficiency_ok=eff_ok,
        confirm_up=core_up,
        confirm_down=core_dn,
        reasons=reasons,
    )


def regime_allows_direction(regime: str, side: str) -> bool:
    """side in {'up','down'}."""
    if regime == "bear" and side == "up":
        return False
    if regime == "bull" and side == "down":
        return False
    # flat / transition / unknown: both allowed if confirm strong (caller enforces)
    return True


def regime_requires_efficiency(regime: str) -> bool:
    return regime in ("flat", "transition", "unknown")


@dataclass
class SqueezeBreakSignal:
    """One bar evaluation for paper timing."""

    compression_on: bool
    compression_recent: bool
    regime: str
    confirm_up: bool
    confirm_down: bool
    efficiency_ok: bool
    # layered outputs
    s1_up: bool  # coil recent + confirm up
    s2_up: bool  # + regime allows
    s3_up: bool  # + efficiency (always require eff on S3)
    s3_strict_up: bool  # flat/transition must have eff; bull can skip? S3 always eff
    long_candidate: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_bar(
    *,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    i: int,
    regime: str,
    widths: Optional[Sequence[Optional[float]]] = None,
    atrs: Optional[Sequence[Optional[float]]] = None,
) -> SqueezeBreakSignal:
    atrs = atrs or atr_series(highs, lows, closes)
    widths = widths or bb_width_series(closes)
    comp = compression_at(highs, lows, closes, i, widths=widths, atrs=atrs)
    coil_r = compression_recent(highs, lows, closes, i, widths=widths, atrs=atrs)
    # break uses compression base: prefer confirm on bar after coil — allow coil today or recent
    rh_rl = prior_range(highs, lows, i)
    rh, rl = (rh_rl if rh_rl else (None, None))
    conf = confirm_break(
        o=opens[i],
        h=highs[i],
        l=lows[i],
        c=closes[i],
        volume=volumes[i],
        volumes=volumes,
        atrs=atrs,
        i=i,
        range_hi=rh,
        range_lo=rl,
    )
    s1_up = coil_r and conf.confirm_up
    s2_up = s1_up and regime_allows_direction(regime, "up")
    # bear veto longs
    if regime == "bear":
        s2_up = False
    s3_up = s2_up and conf.efficiency_ok
    # strict: flat always needs efficiency (same as s3 for up)
    long_candidate = s3_up
    reasons = list(comp.reasons) + list(conf.reasons) + [f"regime={regime}"]
    if long_candidate:
        reasons.append("long_candidate")
    return SqueezeBreakSignal(
        compression_on=comp.on,
        compression_recent=coil_r,
        regime=regime,
        confirm_up=conf.confirm_up,
        confirm_down=conf.confirm_down,
        efficiency_ok=conf.efficiency_ok,
        s1_up=s1_up,
        s2_up=s2_up,
        s3_up=s3_up,
        s3_strict_up=s3_up,
        long_candidate=long_candidate,
        reasons=reasons,
    )


def coil_then_breadth_fire(
    *,
    compression_recent_on: bool,
    breadth_on: bool,
    regime: str,
) -> bool:
    """M2: paper Path A alt — coil then participation expansion."""
    if regime == "bear":
        return False
    return bool(compression_recent_on and breadth_on)
