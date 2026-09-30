"""NEEDLE-03 / Stage 3: BTC/ETH beta core clip planner.

First live clip is $200–$400 (default $300), 60/40 BTC/ETH, no 3% SL.
Never 40% of book overnight. Bear / usdc_park → no core.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

CORE_PAIRS = ("BTC-USD", "ETH-USD")
BTC_FRAC = 0.60
ETH_FRAC = 0.40
CLIP_MIN_USD = 200.0
CLIP_MAX_USD = 400.0
DEFAULT_CLIP_USD = 300.0
TRYOUT_RESERVE_USD = 150.0
SOFT_UP_LAYERS = frozenset({"soft_up", "climb", "pre_bull"})
BLOCK_REGIMES = frozenset({"bear", "usdc_park", "soft_down"})


@dataclass
class CoreLeg:
    pair: str
    usd: float
    skip_sl: bool = True
    sleeve: str = "core"


@dataclass
class CorePlan:
    status: str
    reasons: List[str] = field(default_factory=list)
    clip_usd: float = 0.0
    btc_usd: float = 0.0
    eth_usd: float = 0.0
    unwind_usdc_usd: float = 0.0
    usd_before: float = 0.0
    usdc_before: float = 0.0
    reserve_usd: float = TRYOUT_RESERVE_USD
    skip_sl: bool = True
    legs: List[CoreLeg] = field(default_factory=list)
    regime: str = ""
    regime_layer: str = ""
    strategy_mode: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _layer_from_status(status: Optional[Dict[str, Any]]) -> str:
    st = status if isinstance(status, dict) else {}
    det = st.get("detector") if isinstance(st.get("detector"), dict) else {}
    return str(det.get("regime_layer") or st.get("regime_layer") or "").strip().lower()


def core_door_open(status: Optional[Dict[str, Any]]) -> tuple[bool, str]:
    """soft_up/climb/pre_bull, or transition+deploy. Bear/park closed."""
    st = status if isinstance(status, dict) else {}
    regime = str(st.get("regime") or "").strip().lower()
    layer = _layer_from_status(st)
    mode = str(st.get("strategy_mode") or "").strip().lower()
    if regime in BLOCK_REGIMES or layer in BLOCK_REGIMES:
        return False, f"blocked_regime:{regime or layer}"
    if layer in SOFT_UP_LAYERS:
        return True, f"layer:{layer}"
    if regime == "transition" and mode in {"deploy", "transition_deploy"}:
        return True, "transition_deploy"
    if bool(st.get("allow_new_buys")) and regime in {"soft_up", "bull", "climb"}:
        return True, f"regime:{regime}"
    return False, f"door_closed:{regime}/{layer}/{mode}"


def clip_usd_for_equity(equity: float, requested: float = DEFAULT_CLIP_USD) -> float:
    """First-wave clip: $200–$400, never 40% of book."""
    eq = max(0.0, _f(equity))
    req = _f(requested, DEFAULT_CLIP_USD)
    clip = min(max(req, CLIP_MIN_USD), CLIP_MAX_USD)
    forty = eq * 0.40
    if forty > 0:
        clip = min(clip, forty)
    if eq > 0 and clip > eq * 0.25:
        # Stage 3 first clip stays well under overnight 40%
        clip = min(clip, max(CLIP_MIN_USD, eq * 0.20))
    return round(clip, 2)


def plan_beta_core(
    *,
    equity: float,
    usd: float,
    usdc: float,
    status: Optional[Dict[str, Any]] = None,
    clip_usd: float = DEFAULT_CLIP_USD,
    reserve_usd: float = TRYOUT_RESERVE_USD,
    btc_frac: float = BTC_FRAC,
    held: Optional[Sequence[str]] = None,
) -> CorePlan:
    st = status if isinstance(status, dict) else {}
    regime = str(st.get("regime") or "")
    layer = _layer_from_status(st)
    mode = str(st.get("strategy_mode") or "")
    open_ok, why = core_door_open(st)
    usd_f = max(0.0, _f(usd))
    usdc_f = max(0.0, _f(usdc))
    eq = max(0.0, _f(equity))
    reserve = max(0.0, _f(reserve_usd, TRYOUT_RESERVE_USD))

    if not open_ok:
        return CorePlan(
            status="blocked",
            reasons=[why],
            usd_before=usd_f,
            usdc_before=usdc_f,
            reserve_usd=reserve,
            regime=regime,
            regime_layer=layer,
            strategy_mode=mode,
        )

    clip = clip_usd_for_equity(eq, clip_usd)
    if clip + 1e-9 < CLIP_MIN_USD:
        return CorePlan(
            status="blocked",
            reasons=[f"clip_below_min:{clip}"],
            clip_usd=clip,
            usd_before=usd_f,
            usdc_before=usdc_f,
            reserve_usd=reserve,
            regime=regime,
            regime_layer=layer,
            strategy_mode=mode,
        )

    need_usd = clip + reserve
    unwind = 0.0
    if usd_f < need_usd:
        unwind = min(usdc_f, need_usd - usd_f)
    spendable_after = usd_f + unwind
    if spendable_after + 1e-9 < clip:
        return CorePlan(
            status="blocked",
            reasons=[
                f"insufficient_cash:usd={usd_f:.2f}+unwind={unwind:.2f}<clip={clip:.2f}"
            ],
            clip_usd=clip,
            unwind_usdc_usd=round(unwind, 2),
            usd_before=usd_f,
            usdc_before=usdc_f,
            reserve_usd=reserve,
            regime=regime,
            regime_layer=layer,
            strategy_mode=mode,
        )

    btc = round(clip * float(btc_frac), 2)
    eth = round(clip - btc, 2)
    held_n = {str(h).upper() for h in (held or [])}
    legs: List[CoreLeg] = []
    reasons = [why, f"clip=${clip:.2f}", "skip_sl", "limit_first_no_market"]
    for pair, usd_leg in (("BTC-USD", btc), ("ETH-USD", eth)):
        if usd_leg < 10:
            continue
        legs.append(CoreLeg(pair=pair, usd=usd_leg, skip_sl=True))
        if pair in held_n:
            reasons.append(f"add_to_existing:{pair}")

    return CorePlan(
        status="planned",
        reasons=reasons,
        clip_usd=clip,
        btc_usd=btc,
        eth_usd=eth,
        unwind_usdc_usd=round(unwind, 2),
        usd_before=usd_f,
        usdc_before=usdc_f,
        reserve_usd=reserve,
        skip_sl=True,
        legs=legs,
        regime=regime,
        regime_layer=layer,
        strategy_mode=mode,
    )


CORE_LIMIT_FIRST_CFG: Dict[str, Any] = {
    "entry_execution": {
        "mode": "limit_first_v1",
        "limit_first": {
            "enabled": True,
            "post_only": True,
            "price_ref": "bid",
            "offset_bps": -2.0,
            "fill_wait_s": 120,
            "poll_interval_s": 2,
            "min_fill_usd": 10,
            "market_fallback": False,
            "market_fallback_max_usd": 0.0,
            "max_requotes": 0,
            "elevated_tape": "abort",
            "pilot_max_buys_per_day": 8,
            "pilot_max_usd_per_day": 1000.0,
        },
    }
}
