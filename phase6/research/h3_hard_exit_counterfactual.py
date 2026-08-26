#!/usr/bin/env python3
"""EXIT-H3 counterfactual: locked hard-exit (RSI) vs ride to realized exit / SL.

Question (Brad product bar):
  Had we exited at the first locked RSI hard-exit hit vs riding the actual path
  (esp. exchange SL), would total $ after fees be meaningfully better?

Rules:
  - Thresholds locked from config/regime_cash_policy.json regimes.*.exit
  - Hard exit = RSI overbought only on path (sentiment path not reconstructed —
    no historical pair sentiment series; RSI is the measurable H3 leg)
  - Real ledger buy→sell legs + backtest OHLCV packs
  - No live config writes, no orders

Writes via runner:
  data/state/h3_hard_exit_cf_latest.json
  reports/H3_HARD_EXIT_CF_LATEST.md
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
OHLCV_DIR = ROOT / "backtests" / "data"
POLICY = ROOT / "config" / "regime_cash_policy.json"
OUT_STATE = ROOT / "data" / "state" / "h3_hard_exit_cf_latest.json"
OUT_MD = ROOT / "reports" / "H3_HARD_EXIT_CF_LATEST.md"

# Round-trip fee drag applied to CF exit (both sides) — honest vs free paper
DEFAULT_FEE_RT = 0.0024  # ~12 bps each way

PAIR_TO_SHORT = {
    "BTC-USD": "btc",
    "ETH-USD": "eth",
    "SOL-USD": "sol",
    "XRP-USD": "xrp",
    "DOGE-USD": "doge",
    "AVAX-USD": "avax",
    "LINK-USD": "link",
    "ARB-USD": "arb",
    "ADA-USD": "ada",
    "UNI-USD": "uni",
    "OP-USD": "op",
    "NEAR-USD": "near",
    "ICP-USD": "icp",
    "RAVE-USD": "rave",
    "PENGU-USD": "pengu",
}

# Decide bars (from exit-layers-plain-english / skill)
N_MIN_TRIGGERED = 15
MEAN_EXCESS_MEANINGFUL = 0.005  # +0.5% mean excess after fees vs ride
HIT_MIN = 0.55


def _parse_ts(raw: Any) -> Optional[datetime]:
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def _day(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d")


def load_exit_thresholds(path: Path = POLICY) -> Dict[str, Dict[str, float]]:
    """regime → {overbought_rsi, max_sentiment_hold} locked from live policy."""
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out: Dict[str, Dict[str, float]] = {}
    for name, body in (raw.get("regimes") or {}).items():
        ex = (body or {}).get("exit") or {}
        try:
            ob = float(ex.get("overbought_rsi") or 80.0)
        except (TypeError, ValueError):
            ob = 80.0
        try:
            ms = float(ex.get("max_sentiment_hold") if ex.get("max_sentiment_hold") is not None else -1.0)
        except (TypeError, ValueError):
            ms = -1.0
        out[str(name)] = {"overbought_rsi": ob, "max_sentiment_hold": ms}
    if not out:
        out = {
            "bull": {"overbought_rsi": 75.0, "max_sentiment_hold": -0.35},
            "flat": {"overbought_rsi": 65.0, "max_sentiment_hold": -0.15},
            "bear": {"overbought_rsi": 60.0, "max_sentiment_hold": 0.0},
            "transition": {"overbought_rsi": 68.0, "max_sentiment_hold": -0.2},
            "soft_down": {"overbought_rsi": 62.0, "max_sentiment_hold": -0.1},
            "unknown": {"overbought_rsi": 70.0, "max_sentiment_hold": -0.2},
        }
    return out


def load_detector_knobs(path: Path = POLICY) -> Dict[str, float]:
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    d = raw.get("detector") or {}
    return {
        "lookback_days": float(d.get("lookback_days") or 30),
        "bull_return_pct": float(d.get("bull_return_pct") or 15.0),
        "bear_return_pct": float(d.get("bear_return_pct") or -10.0),
        "flat_abs_pct": float(d.get("flat_abs_pct") or 8.0),
    }


def rsi_wilder(closes: Sequence[float], period: int = 14) -> List[Optional[float]]:
    """Wilder RSI aligned to closes; first period values None until seeded."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period + 1:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period + 1, n):
        d = closes[i] - closes[i - 1]
        gain = d if d > 0 else 0.0
        loss = -d if d < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def load_ohlcv(pair: str) -> List[Dict[str, Any]]:
    short = PAIR_TO_SHORT.get(pair) or pair.split("-")[0].lower()
    candidates = sorted(OHLCV_DIR.glob(f"backtest_historical_ohlcv_{short}*.json"))
    if not candidates:
        return []
    try:
        data = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def classify_regime_btc(
    btc_closes_by_day: Dict[str, float],
    as_of_day: str,
    knobs: Dict[str, float],
) -> str:
    """Simple 30d BTC return regime label (aligned with detector cuts, not full soft_*)."""
    days = sorted(btc_closes_by_day.keys())
    if as_of_day not in btc_closes_by_day:
        # nearest prior
        prior = [d for d in days if d <= as_of_day]
        if not prior:
            return "unknown"
        as_of_day = prior[-1]
    i = days.index(as_of_day) if as_of_day in days else -1
    if i < 0:
        return "unknown"
    lb = int(knobs.get("lookback_days") or 30)
    j = max(0, i - lb)
    c0 = btc_closes_by_day[days[j]]
    c1 = btc_closes_by_day[days[i]]
    if c0 <= 0:
        return "unknown"
    ret_pct = (c1 / c0 - 1.0) * 100.0
    bull = knobs.get("bull_return_pct", 15.0)
    bear = knobs.get("bear_return_pct", -10.0)
    flat_abs = knobs.get("flat_abs_pct", 8.0)
    if ret_pct >= bull:
        return "bull"
    if ret_pct <= bear:
        return "bear"
    if abs(ret_pct) <= flat_abs:
        return "flat"
    if ret_pct > 0:
        return "transition"
    return "soft_down"


def load_unique_trades(path: Path = TRADES) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    seen = set()
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        oid = r.get("order_id") or r.get("exchange_order_id") or ""
        key = oid or (
            r.get("timestamp") or r.get("ts"),
            r.get("pair"),
            r.get("side"),
            r.get("qty"),
            r.get("pnl"),
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    return rows


def match_rounds(
    rows: List[Dict[str, Any]], lookback_days: int = 120
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    cut = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    buys: Dict[str, List[Dict[str, Any]]] = {}
    rounds: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    timed: List[Tuple[datetime, Dict[str, Any]]] = []
    for r in rows:
        t = _parse_ts(r.get("timestamp") or r.get("ts") or r.get("filled_at"))
        if t is None or t < cut:
            continue
        timed.append((t, r))
    timed.sort(key=lambda x: x[0])
    for _t, r in timed:
        side = str(r.get("side") or "").upper()
        pair = r.get("pair")
        if not pair:
            continue
        if side == "BUY":
            buys.setdefault(str(pair), []).append(r)
        elif side == "SELL":
            q = buys.get(str(pair)) or []
            if not q:
                continue
            b = q.pop(0)
            rounds.append((b, r))
    return rounds


def _px(row: Dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        try:
            f = float(v)
            if f > 0:
                return f
        except (TypeError, ValueError):
            continue
    return None


def resolve_prices(
    buy: Dict[str, Any], sell: Dict[str, Any]
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """entry_px, exit_px, realized_r."""
    entry_px = _px(buy, "entry_price", "price", "avg_price", "fill_price")
    exit_px = _px(sell, "exit_price", "price", "avg_price", "fill_price")
    if (entry_px is None or entry_px <= 0) and sell.get("pnl") is not None and exit_px:
        try:
            pnl = float(sell["pnl"])
            qty = float(sell.get("qty") or buy.get("qty") or 0)
            if qty:
                entry_px = (qty * exit_px - pnl) / qty
        except (TypeError, ValueError):
            pass
    if exit_px is None and entry_px and sell.get("pnl") is not None:
        try:
            pnl = float(sell["pnl"])
            qty = float(sell.get("qty") or buy.get("qty") or 0)
            if qty:
                exit_px = entry_px + pnl / qty
        except (TypeError, ValueError):
            pass
    if entry_px is None or exit_px is None or entry_px <= 0 or exit_px <= 0:
        return None, None, None
    realized_r = (exit_px - entry_px) / entry_px
    try:
        pct = sell.get("pnl_pct")
        if pct is not None and abs(float(pct)) <= 0.5:
            realized_r = float(pct)
    except (TypeError, ValueError):
        pass
    return entry_px, exit_px, realized_r


def notional_usd(buy: Dict[str, Any], sell: Dict[str, Any], entry_px: float) -> float:
    for row in (sell, buy):
        for k in ("usd", "usd_amount", "notional", "quote_qty"):
            try:
                v = float(row.get(k) or 0)
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
        try:
            qty = float(row.get("qty") or 0)
            if qty > 0 and entry_px > 0:
                return qty * entry_px
        except (TypeError, ValueError):
            pass
    return 100.0  # unit notional fallback for r-only aggregation


@dataclass
class H3LegCF:
    pair: str
    entry_ts: str
    exit_ts: str
    entry_px: float
    exit_px: float
    realized_r: float
    reason: str
    is_sl: bool
    regime_at_entry: str
    overbought_rsi: float
    notional_usd: float
    hard_fired: bool
    hard_day: Optional[str]
    hard_rsi: Optional[float]
    cf_hard_r_gross: Optional[float]
    cf_hard_r_net: Optional[float]
    delta_r_net: Optional[float]  # hard_net - realized (positive = hard better)
    delta_usd_net: Optional[float]
    days_held: int
    days_to_hard: Optional[int]
    note: str = ""


def walk_hard_exit_on_path(
    *,
    candles: List[Dict[str, Any]],
    entry_day: str,
    exit_day: str,
    entry_px: float,
    overbought: float,
    fee_rt: float = DEFAULT_FEE_RT,
    cautious: bool = False,
    min_hold_days: int = 1,
    min_mark_r: float = 0.0,
    require_rsi_cross: bool = True,
) -> Dict[str, Any]:
    """First qualifying day on [entry, exit] where RSI hard-exit fires → CF at close.

    cautious=True applies Brad 2026-08-25 gates:
      - min_hold_days after entry (no day-0)
      - RSI cross up through overbought (prev bar < thr, this bar >= thr)
      - mark_r at exit day >= min_mark_r (green-or-flat)
    """
    if entry_px <= 0 or not candles:
        return {"hard_fired": False, "note": "no_path"}
    # full series for RSI warm-up
    series = sorted(candles, key=lambda c: str(c.get("timestamp") or "")[:10])
    days = [str(c.get("timestamp") or "")[:10] for c in series]
    closes = []
    for c in series:
        try:
            closes.append(float(c.get("close") or 0))
        except (TypeError, ValueError):
            closes.append(0.0)
    rsis = rsi_wilder(closes, 14)
    hard_day = None
    hard_rsi = None
    hard_close = None
    hard_idx = None
    entry_idx = next((i for i, d in enumerate(days) if d >= entry_day), 0)
    for i, d in enumerate(days):
        if d < entry_day or d > exit_day:
            continue
        rsi = rsis[i]
        if rsi is None:
            continue
        if float(rsi) < float(overbought):
            continue
        days_to = max(0, i - entry_idx)
        if cautious and days_to < int(min_hold_days):
            continue
        if cautious and require_rsi_cross:
            prev = rsis[i - 1] if i > 0 else None
            if prev is None or float(prev) >= float(overbought):
                continue
        if cautious:
            mark = (closes[i] - entry_px) / entry_px if entry_px > 0 else None
            if mark is None or float(mark) < float(min_mark_r):
                continue
        hard_day = d
        hard_rsi = float(rsi)
        hard_close = closes[i]
        hard_idx = i
        break
    if hard_day is None or hard_close is None or hard_close <= 0:
        return {
            "hard_fired": False,
            "note": "no_hard_hit_cautious" if cautious else "no_hard_hit",
            "bars_in_window": sum(1 for d in days if entry_day <= d <= exit_day),
        }
    days_to_hard = max(0, (hard_idx or 0) - entry_idx)
    gross = (hard_close - entry_px) / entry_px
    net = gross - float(fee_rt)
    return {
        "hard_fired": True,
        "hard_day": hard_day,
        "hard_rsi": hard_rsi,
        "cf_hard_r_gross": gross,
        "cf_hard_r_net": net,
        "days_to_hard": days_to_hard,
        "note": "ok_cautious" if cautious else "ok",
        "cautious": cautious,
    }


def analyze_leg(
    buy: Dict[str, Any],
    sell: Dict[str, Any],
    *,
    thresholds: Dict[str, Dict[str, float]],
    detector: Dict[str, float],
    btc_closes: Dict[str, float],
    fee_rt: float = DEFAULT_FEE_RT,
    ohlcv_loader=load_ohlcv,
    cautious: bool = False,
    min_hold_days: int = 1,
    min_mark_r: float = 0.0,
    require_rsi_cross: bool = True,
    min_notional_usd: float = 0.0,
    auto_regimes: Optional[Sequence[str]] = None,
) -> Optional[H3LegCF]:
    pair = str(buy.get("pair") or sell.get("pair") or "")
    et = _parse_ts(buy.get("timestamp") or buy.get("ts"))
    xt = _parse_ts(sell.get("timestamp") or sell.get("ts"))
    if not pair or not et or not xt:
        return None
    entry_px, exit_px, realized_r = resolve_prices(buy, sell)
    if entry_px is None or exit_px is None or realized_r is None:
        return None
    reason = str(sell.get("reason") or "")
    is_sl = "stop_loss" in reason.lower() or reason.lower() in ("sl", "stop")
    ed = _day(et)
    xd = _day(xt)
    regime = classify_regime_btc(btc_closes, ed, detector) if btc_closes else "unknown"
    th = thresholds.get(regime) or thresholds.get("unknown") or {"overbought_rsi": 70.0}
    ob = float(th["overbought_rsi"])
    notion = notional_usd(buy, sell, entry_px)
    if min_notional_usd > 0 and notion < float(min_notional_usd):
        return None
    candles = ohlcv_loader(pair)
    if not candles:
        return H3LegCF(
            pair=pair,
            entry_ts=et.isoformat(),
            exit_ts=xt.isoformat(),
            entry_px=entry_px,
            exit_px=exit_px,
            realized_r=realized_r,
            reason=reason,
            is_sl=is_sl,
            regime_at_entry=regime,
            overbought_rsi=ob,
            notional_usd=notion,
            hard_fired=False,
            hard_day=None,
            hard_rsi=None,
            cf_hard_r_gross=None,
            cf_hard_r_net=None,
            delta_r_net=None,
            delta_usd_net=None,
            days_held=max(0, (xt - et).days),
            days_to_hard=None,
            note="no_ohlcv",
        )
    # Cautious path only scores auto regimes (default flat)
    if cautious and auto_regimes is not None:
        allowed = {str(x).lower() for x in auto_regimes}
        if str(regime).lower() not in allowed:
            return H3LegCF(
                pair=pair,
                entry_ts=et.isoformat(),
                exit_ts=xt.isoformat(),
                entry_px=entry_px,
                exit_px=exit_px,
                realized_r=realized_r,
                reason=reason,
                is_sl=is_sl,
                regime_at_entry=regime,
                overbought_rsi=ob,
                notional_usd=notion,
                hard_fired=False,
                hard_day=None,
                hard_rsi=None,
                cf_hard_r_gross=None,
                cf_hard_r_net=None,
                delta_r_net=None,
                delta_usd_net=None,
                days_held=max(0, (xt - et).days),
                days_to_hard=None,
                note="regime_not_auto",
            )
    path = walk_hard_exit_on_path(
        candles=candles,
        entry_day=ed,
        exit_day=xd,
        entry_px=entry_px,
        overbought=ob,
        fee_rt=fee_rt,
        cautious=cautious,
        min_hold_days=min_hold_days,
        min_mark_r=min_mark_r,
        require_rsi_cross=require_rsi_cross,
    )
    hard_fired = bool(path.get("hard_fired"))
    cf_net = path.get("cf_hard_r_net") if hard_fired else None
    delta_r = (float(cf_net) - float(realized_r)) if hard_fired and cf_net is not None else None
    delta_usd = (delta_r * notion) if delta_r is not None else None
    return H3LegCF(
        pair=pair,
        entry_ts=et.isoformat(),
        exit_ts=xt.isoformat(),
        entry_px=entry_px,
        exit_px=exit_px,
        realized_r=realized_r,
        reason=reason,
        is_sl=is_sl,
        regime_at_entry=regime,
        overbought_rsi=ob,
        notional_usd=notion,
        hard_fired=hard_fired,
        hard_day=path.get("hard_day"),
        hard_rsi=path.get("hard_rsi"),
        cf_hard_r_gross=path.get("cf_hard_r_gross"),
        cf_hard_r_net=cf_net,
        delta_r_net=delta_r,
        delta_usd_net=delta_usd,
        days_held=max(0, (xt - et).days),
        days_to_hard=path.get("days_to_hard"),
        note=str(path.get("note") or ""),
    )


def _mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def decide(
    legs: List[H3LegCF],
    *,
    n_min: int = N_MIN_TRIGGERED,
    mean_excess_min: float = MEAN_EXCESS_MEANINGFUL,
    hit_min: float = HIT_MIN,
) -> Dict[str, Any]:
    """Go/no-go for H3 auto from path CF (not a flip instruction)."""
    usable = [L for L in legs if L.note not in ("no_ohlcv",) and L.hard_fired and L.delta_r_net is not None]
    sl_trig = [L for L in usable if L.is_sl]
    # primary: legs that actually hit SL (the stated question)
    primary = sl_trig if len(sl_trig) >= max(5, n_min // 3) else usable
    deltas = [float(L.delta_r_net) for L in primary if L.delta_r_net is not None]
    n = len(deltas)
    mean_ex = _mean(deltas)
    hit = (sum(1 for d in deltas if d > 0) / n) if n else None
    sum_usd = sum(float(L.delta_usd_net or 0) for L in primary)

    # false alarms: hard would cut a winning realized leg
    winners_cut = [
        L
        for L in legs
        if L.hard_fired and L.realized_r is not None and float(L.realized_r) > 0.005
        and L.cf_hard_r_net is not None
        and float(L.cf_hard_r_net) < float(L.realized_r)
    ]

    if n < n_min:
        status = "inconclusive"
        go = False
        plain = (
            f"INCONCLUSIVE — only {n} legs with hard-exit trigger + path "
            f"(need ≥{n_min}). Keep operator loop; do not flip H3."
        )
    elif mean_ex is not None and mean_ex >= mean_excess_min and hit is not None and hit >= hit_min:
        status = "edge_for_hard"
        go = False  # still not auto-flip — Brad review
        plain = (
            f"EDGE SIGNAL — hard exit beat ride on mean excess {mean_ex*100:.2f}% "
            f"hit={hit*100:.0f}% N={n}. Still NOT live flip — Brad review + re-entry cost."
        )
    elif mean_ex is not None and mean_ex <= -mean_excess_min:
        status = "prefer_ride"
        go = False
        plain = (
            f"PREFER RIDE — hard exit worse by mean {-mean_ex*100:.2f}% "
            f"hit={((hit or 0)*100):.0f}% N={n}. Keep H3 operator loop."
        )
    else:
        status = "no_clear_edge"
        go = False
        plain = (
            f"NO CLEAR EDGE — mean excess {(mean_ex or 0)*100:.2f}% "
            f"hit={((hit or 0)*100):.0f}% N={n}. Keep operator loop."
        )

    return {
        "status": status,
        "recommend_live_h3_auto": go,
        "plain_english": plain,
        "n_triggered": n,
        "n_min": n_min,
        "primary_set": "sl_triggered" if primary is sl_trig and sl_trig else "all_triggered",
        "mean_excess_r": mean_ex,
        "hit_rate_hard_better": hit,
        "sum_delta_usd": sum_usd,
        "n_false_alarm_winners_cut": len(winners_cut),
        "gates": {
            "n_ok": n >= n_min,
            "mean_excess_ok": bool(mean_ex is not None and mean_ex >= mean_excess_min),
            "hit_ok": bool(hit is not None and hit >= hit_min),
        },
    }


def run_study(
    *,
    lookback_days: int = 120,
    fee_rt: float = DEFAULT_FEE_RT,
    trades_path: Path = TRADES,
    policy_path: Path = POLICY,
    cautious: bool = True,
    min_notional_usd: float = 25.0,
) -> Dict[str, Any]:
    thresholds = load_exit_thresholds(policy_path)
    detector = load_detector_knobs(policy_path)
    pol = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else {}
    ccfg = ((pol.get("hard_exit") or {}).get("cautious_flat") or {}) if isinstance(pol, dict) else {}
    min_hold_hours = float(ccfg.get("min_hold_hours") or 24.0)
    min_hold_days = max(1, int(round(min_hold_hours / 24.0)))
    min_mark_r = float(ccfg.get("min_mark_r") if ccfg.get("min_mark_r") is not None else 0.0)
    require_cross = bool(ccfg.get("require_rsi_cross", True))
    auto_regs = list(ccfg.get("auto_apply_regimes") or ["flat"])
    if ccfg.get("min_sell_usd") is not None:
        try:
            min_notional_usd = float(ccfg.get("min_sell_usd"))
        except (TypeError, ValueError):
            pass

    rows = load_unique_trades(trades_path)
    rounds = match_rounds(rows, lookback_days=lookback_days)

    btc = load_ohlcv("BTC-USD")
    btc_closes: Dict[str, float] = {}
    for c in btc:
        d = str(c.get("timestamp") or "")[:10]
        try:
            btc_closes[d] = float(c.get("close") or 0)
        except (TypeError, ValueError):
            pass

    legs: List[H3LegCF] = []
    for buy, sell in rounds:
        leg = analyze_leg(
            buy,
            sell,
            thresholds=thresholds,
            detector=detector,
            btc_closes=btc_closes,
            fee_rt=fee_rt,
            cautious=cautious,
            min_hold_days=min_hold_days,
            min_mark_r=min_mark_r,
            require_rsi_cross=require_cross,
            min_notional_usd=min_notional_usd,
            auto_regimes=auto_regs if cautious else None,
        )
        if leg:
            legs.append(leg)

    triggered = [L for L in legs if L.hard_fired]
    sl_legs = [L for L in legs if L.is_sl]
    sl_trig = [L for L in sl_legs if L.hard_fired]
    # Cautious sample is thinner — still report honestly (n_min stays 15)
    decision = decide(legs)

    by_regime: Dict[str, Any] = {}
    for L in triggered:
        by_regime.setdefault(L.regime_at_entry, {"n": 0, "deltas": []})
        by_regime[L.regime_at_entry]["n"] += 1
        if L.delta_r_net is not None:
            by_regime[L.regime_at_entry]["deltas"].append(L.delta_r_net)
    regime_summary = {
        k: {
            "n": v["n"],
            "mean_delta_r": _mean(v["deltas"]),
            "hit": (sum(1 for d in v["deltas"] if d > 0) / len(v["deltas"])) if v["deltas"] else None,
        }
        for k, v in by_regime.items()
    }

    payload = {
        "schema": "h3_hard_exit_cf_v2_cautious",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "question": (
            "Had we exited at first locked RSI hard-exit vs riding to realized exit "
            "(esp. exchange SL), meaningful profit/less loss after fees?"
        ),
        "method": {
            "rsi": "Wilder 14 on daily OHLCV closes",
            "thresholds": thresholds,
            "sentiment_on_path": False,
            "sentiment_note": (
                "Pair sentiment history not reconstructed; H3 CF is RSI-primary. "
                "Live H3 also fires on sentiment_weak — not measured here."
            ),
            "fee_rt": fee_rt,
            "lookback_days": lookback_days,
            "regime_label": "BTC 30d return cuts from detector knobs (simplified soft_*)",
            "cautious": cautious,
            "cautious_gates": {
                "min_hold_days": min_hold_days,
                "min_mark_r": min_mark_r,
                "require_rsi_cross": require_cross,
                "min_notional_usd": min_notional_usd,
                "auto_regimes": auto_regs if cautious else "all",
            },
        },
        "counts": {
            "rounds": len(rounds),
            "legs_scored": len(legs),
            "hard_triggered": len(triggered),
            "sl_legs": len(sl_legs),
            "sl_with_prior_hard": len(sl_trig),
            "no_ohlcv": sum(1 for L in legs if L.note == "no_ohlcv"),
            "no_hard_hit": sum(1 for L in legs if L.note in ("no_hard_hit", "no_hard_hit_cautious")),
            "regime_not_auto": sum(1 for L in legs if L.note == "regime_not_auto"),
        },
        "decision": decision,
        "by_regime": regime_summary,
        "legs": [asdict(L) for L in legs],
        "top_helps": [
            asdict(L)
            for L in sorted(
                [x for x in triggered if x.delta_r_net is not None],
                key=lambda z: float(z.delta_r_net or 0),
                reverse=True,
            )[:8]
        ],
        "top_hurts": [
            asdict(L)
            for L in sorted(
                [x for x in triggered if x.delta_r_net is not None],
                key=lambda z: float(z.delta_r_net or 0),
            )[:8]
        ],
        "live_h3_knobs": {
            "operator_approve": True,
            "live_apply_global": False,
            "shadow_only": True,
            "cautious_flat_enabled": bool(ccfg.get("enabled", True)),
            "note": (
                "Cautious flat auto-merge is LIVE in code when gates pass; "
                "global operator_approve stays true for non-flat / failed gates."
            ),
        },
    }
    return payload


def format_report(payload: Dict[str, Any]) -> str:
    d = payload.get("decision") or {}
    c = payload.get("counts") or {}
    lines = [
        "# H3 hard-exit counterfactual",
        "",
        f"_as_of {payload.get('as_of')}_",
        "",
        "## BOTTOM LINE",
        "",
        str(d.get("plain_english") or ""),
        "",
        f"- recommend_live_h3_auto: **{d.get('recommend_live_h3_auto')}**",
        f"- status: `{d.get('status')}`",
        f"- N triggered (primary): **{d.get('n_triggered')}** (min {d.get('n_min')})",
        f"- mean excess r (hard − ride, after fees): "
        f"**{(d.get('mean_excess_r') or 0)*100:.2f}%**"
        if d.get("mean_excess_r") is not None
        else "- mean excess r: n/a",
        f"- hit rate hard better: "
        f"**{(d.get('hit_rate_hard_better') or 0)*100:.0f}%**"
        if d.get("hit_rate_hard_better") is not None
        else "- hit rate: n/a",
        f"- sum Δ$ (primary): **${float(d.get('sum_delta_usd') or 0):.2f}**",
        f"- winners hard would have cut worse: **{d.get('n_false_alarm_winners_cut')}**",
        "",
        "## Counts",
        "",
        f"- rounds matched: {c.get('rounds')}",
        f"- legs scored: {c.get('legs_scored')}",
        f"- hard triggered: {c.get('hard_triggered')}",
        f"- SL legs: {c.get('sl_legs')} (with prior hard: {c.get('sl_with_prior_hard')})",
        f"- no OHLCV: {c.get('no_ohlcv')} · no hard hit: {c.get('no_hard_hit')}",
        "",
        "## Method limits",
        "",
        f"- {(payload.get('method') or {}).get('sentiment_note')}",
        f"- fee_rt={(payload.get('method') or {}).get('fee_rt')}",
        f"- lookback_days={(payload.get('method') or {}).get('lookback_days')}",
        "",
        "## By regime (triggered only)",
        "",
    ]
    for reg, st in sorted((payload.get("by_regime") or {}).items()):
        me = st.get("mean_delta_r")
        ht = st.get("hit")
        if me is None:
            lines.append(f"- **{reg}**: n={st.get('n')} mean_Δr=n/a")
        elif ht is None:
            lines.append(f"- **{reg}**: n={st.get('n')} mean_Δr={me*100:.2f}%")
        else:
            lines.append(
                f"- **{reg}**: n={st.get('n')} mean_Δr={me*100:.2f}% hit={ht*100:.0f}%"
            )
    lines += [
        "",
        "## Locked thresholds",
        "",
        "```json",
        json.dumps((payload.get("method") or {}).get("thresholds") or {}, indent=2),
        "```",
        "",
        "## Top helps (hard better)",
        "",
    ]
    for L in payload.get("top_helps") or []:
        lines.append(
            f"- {L.get('pair')} {L.get('reason')}: Δr={(float(L.get('delta_r_net') or 0)*100):.2f}% "
            f"hard@{L.get('hard_day')} RSI={L.get('hard_rsi')} regime={L.get('regime_at_entry')}"
        )
    lines += ["", "## Top hurts (hard worse)", ""]
    for L in payload.get("top_hurts") or []:
        lines.append(
            f"- {L.get('pair')} {L.get('reason')}: Δr={(float(L.get('delta_r_net') or 0)*100):.2f}% "
            f"hard@{L.get('hard_day')} RSI={L.get('hard_rsi')} regime={L.get('regime_at_entry')}"
        )
    lines += [
        "",
        "---",
        "No config flip. H3 stays operator_approve until Brad go after clear edge + N.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(payload: Dict[str, Any]) -> Tuple[Path, Path]:
    OUT_STATE.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    # slim legs in md companion state full
    OUT_STATE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = format_report(payload)
    OUT_MD.write_text(md, encoding="utf-8")
    return OUT_STATE, OUT_MD
