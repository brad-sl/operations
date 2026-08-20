#!/usr/bin/env python3
"""P2: Bear ladder path counterfactual — real OHLCV + ledger legs.

Policies compared on the same path:
  A) sl_ride     — hold until SL (~3%) or path end
  B) full_tp_06  — first hit SL or +6% full exit (offline prior: often hurts in bear)
  C) ladder_v1   — scale-out 25% at +3/+5/+8%; moon bag 25% rides to SL/path end

Regime label: BTC 30d return at entry (same thresholds as regime_cash detector).

Primary sample: closed ledger buy→sell rounds (phase6_trades.jsonl).
Secondary sample: non-overlapping synthetic entries on majors while BTC in bear
  (real daily bars only — labeled synthetic_bear_entry).

Writes:
  data/state/bear_ladder_path_cf_latest.json
  reports/BEAR_LADDER_PATH_CF_LATEST.md
  reports/BEAR_LADDER_PATH_CF_YYYY-MM-DD.md

Recommendation: pursue_shadow | drop | inconclusive | no_clear_edge
No live config writes. No orders.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TRADES = ROOT / "trades" / "phase6_trades.jsonl"
OHLCV_DIR = ROOT / "backtests" / "data"
LONG_DIR = ROOT / "backtests" / "data" / "long"
OUT_STATE = ROOT / "data" / "state" / "bear_ladder_path_cf_latest.json"
REPORTS = ROOT / "reports"
CFG_PATH = ROOT / "config" / "bear_profit_take.json"

# Detector defaults (regime_cash_policy)
LOOKBACK = 30
BULL_RET = 15.0
BEAR_RET = -10.0
FLAT_ABS = 8.0
DEFAULT_SL = 0.03
FEE_RT = 0.002  # round-trip-ish drag per full exit; partials pro-rated
MIN_N = 15
MAX_HOLD_SYNTH = 45
SYNTH_STRIDE_DAYS = 14  # non-overlap-ish entries while in bear

PAIR_TO_SHORT = {
    "BTC-USD": "btc",
    "ETH-USD": "eth",
    "SOL-USD": "sol",
    "XRP-USD": "xrp",
    "DOGE-USD": "doge",
    "AVAX-USD": "avax",
    "LINK-USD": "link",
    "ADA-USD": "ada",
    "ARB-USD": "arb",
    "UNI-USD": "uni",
    "OP-USD": "op",
    "NEAR-USD": "near",
}

DEFAULT_LADDER = [
    {"level": 1, "r_pct": 0.03, "sell_frac": 0.25},
    {"level": 2, "r_pct": 0.05, "sell_frac": 0.25},
    {"level": 3, "r_pct": 0.08, "sell_frac": 0.25},
]


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


def _load_ohlcv(pair: str) -> List[Dict[str, Any]]:
    short = PAIR_TO_SHORT.get(pair) or pair.split("-")[0].lower()
    candidates: List[Path] = []
    candidates += sorted(OHLCV_DIR.glob(f"backtest_historical_ohlcv_{short}*.json"))
    if LONG_DIR.exists():
        candidates += sorted(LONG_DIR.glob(f"*{short}*.json"))
        candidates += sorted(LONG_DIR.glob(f"ohlcv_daily_{short}.json"))
    # also project long daily names
    for p in (
        OHLCV_DIR / f"ohlcv_daily_{short}.json",
        LONG_DIR / f"ohlcv_daily_{short}.json",
    ):
        if p.exists():
            candidates.append(p)
    # de-dupe preserve order
    seen = set()
    uniq = []
    for c in candidates:
        s = str(c)
        if s not in seen:
            seen.add(s)
            uniq.append(c)
    best: List[Dict[str, Any]] = []
    for path in uniq:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            data = data.get("candles") or data.get("data") or data.get("ohlcv") or []
        if not isinstance(data, list) or not data:
            continue
        if len(data) > len(best):
            best = data
    return best


def _load_unique_trades() -> List[Dict[str, Any]]:
    if not TRADES.exists():
        return []
    seen = set()
    rows = []
    for line in TRADES.read_text(encoding="utf-8").splitlines():
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


def _match_rounds(rows: List[Dict[str, Any]], lookback_days: int = 0) -> List[Tuple[Dict, Dict]]:
    """FIFO buy→sell per pair."""
    by_pair: Dict[str, List[Dict]] = defaultdict(list)
    for r in rows:
        pair = str(r.get("pair") or "")
        side = str(r.get("side") or r.get("action") or "").lower()
        if not pair or side not in ("buy", "sell"):
            continue
        ts = _parse_ts(r.get("timestamp") or r.get("ts"))
        if not ts:
            continue
        if lookback_days > 0:
            cut = datetime.now(timezone.utc) - timedelta(days=lookback_days)
            if ts < cut:
                continue
        by_pair[pair].append(r)

    rounds: List[Tuple[Dict, Dict]] = []
    for pair, lst in by_pair.items():
        lst.sort(key=lambda x: _parse_ts(x.get("timestamp") or x.get("ts")) or datetime.min.replace(tzinfo=timezone.utc))
        q: List[Dict] = []
        for r in lst:
            side = str(r.get("side") or r.get("action") or "").lower()
            if side == "buy":
                q.append(r)
            elif side == "sell" and q:
                buy = q.pop(0)
                rounds.append((buy, r))
    return rounds


def _bars_between(candles: List[Dict[str, Any]], start_d: str, end_d: str) -> List[Dict[str, Any]]:
    out = []
    for c in candles:
        d = str(c.get("timestamp") or c.get("date") or c.get("time") or "")[:10]
        if len(d) >= 10 and start_d <= d <= end_d:
            out.append(c)
    return out


def _btc_closes() -> List[Tuple[date, float]]:
    candles = _load_ohlcv("BTC-USD")
    out: List[Tuple[date, float]] = []
    for c in candles:
        d = str(c.get("timestamp") or c.get("date") or "")[:10]
        try:
            dd = date.fromisoformat(d)
            cl = float(c.get("close") or 0)
        except Exception:
            continue
        if cl > 0:
            out.append((dd, cl))
    out.sort(key=lambda x: x[0])
    return out


def _regime_at(btc: List[Tuple[date, float]], as_of: date) -> Tuple[str, Optional[float]]:
    # find index
    idx = None
    for i, (d, _) in enumerate(btc):
        if d == as_of:
            idx = i
            break
        if d > as_of:
            idx = i - 1
            break
    if idx is None:
        if btc and btc[-1][0] <= as_of:
            idx = len(btc) - 1
        else:
            return "unknown", None
    if idx < LOOKBACK:
        return "unknown", None
    p0 = btc[idx - LOOKBACK][1]
    p1 = btc[idx][1]
    if p0 <= 0:
        return "unknown", None
    ret = (p1 / p0 - 1.0) * 100.0
    if ret >= BULL_RET:
        reg = "bull"
    elif ret <= BEAR_RET:
        reg = "bear"
    elif abs(ret) <= FLAT_ABS:
        reg = "flat"
    else:
        reg = "transition"
    return reg, round(ret, 3)


def _fee_frac(frac: float) -> float:
    """Half-ish round trip fee scaled by fraction sold (exit leg)."""
    return FEE_RT * 0.5 * max(0.0, min(1.0, frac))


def simulate_sl_ride(entry_px: float, bars: List[Dict[str, Any]], sl_pct: float = DEFAULT_SL) -> Dict[str, Any]:
    if entry_px <= 0 or not bars:
        return {"r": None, "exit_reason": "no_path", "days": 0}
    sl_px = entry_px * (1.0 - sl_pct)
    for i, c in enumerate(bars):
        lo = float(c.get("low") or c.get("close") or 0)
        if lo > 0 and lo <= sl_px:
            return {
                "r": round(-sl_pct - FEE_RT, 6),
                "exit_reason": "sl",
                "days": i + 1,
                "exit_px": sl_px,
            }
    cl = float(bars[-1].get("close") or entry_px)
    return {
        "r": round((cl - entry_px) / entry_px - FEE_RT, 6),
        "exit_reason": "path_end",
        "days": len(bars),
        "exit_px": cl,
    }


def simulate_full_tp(
    entry_px: float,
    bars: List[Dict[str, Any]],
    *,
    sl_pct: float = DEFAULT_SL,
    tp: float = 0.06,
) -> Dict[str, Any]:
    if entry_px <= 0 or not bars:
        return {"r": None, "exit_reason": "no_path", "days": 0}
    sl_px = entry_px * (1.0 - sl_pct)
    tp_px = entry_px * (1.0 + tp)
    for i, c in enumerate(bars):
        hi = float(c.get("high") or c.get("close") or 0)
        lo = float(c.get("low") or c.get("close") or 0)
        if lo > 0 and lo <= sl_px:
            return {
                "r": round(-sl_pct - FEE_RT, 6),
                "exit_reason": "sl",
                "days": i + 1,
                "exit_px": sl_px,
            }
        if hi >= tp_px:
            return {
                "r": round(tp - FEE_RT, 6),
                "exit_reason": "full_tp",
                "days": i + 1,
                "exit_px": tp_px,
            }
    cl = float(bars[-1].get("close") or entry_px)
    return {
        "r": round((cl - entry_px) / entry_px - FEE_RT, 6),
        "exit_reason": "path_end",
        "days": len(bars),
        "exit_px": cl,
    }


def simulate_ladder(
    entry_px: float,
    bars: List[Dict[str, Any]],
    *,
    sl_pct: float = DEFAULT_SL,
    tranches: Optional[Sequence[Dict[str, Any]]] = None,
    moon_bag_frac: float = 0.25,
) -> Dict[str, Any]:
    """Weighted R from partial fills + residual to SL/path end.

    Optimistic TP fill at threshold price when day's high tags it.
    Same-day SL vs TP: SL wins on residual (conservative).
    """
    if entry_px <= 0 or not bars:
        return {"r": None, "exit_reason": "no_path", "days": 0, "slices": 0}

    trs = list(tranches or DEFAULT_LADDER)
    trs = sorted(trs, key=lambda t: float(t.get("r_pct") or 0))
    remaining = 1.0
    realized = 0.0  # weighted r contributions
    slices = 0
    filled_levels = set()
    sl_px = entry_px * (1.0 - sl_pct)
    max_sellable = max(0.0, 1.0 - moon_bag_frac)

    for i, c in enumerate(bars):
        hi = float(c.get("high") or c.get("close") or 0)
        lo = float(c.get("low") or c.get("close") or 0)
        cl = float(c.get("close") or entry_px)

        # SL on remaining first
        if lo > 0 and lo <= sl_px and remaining > 1e-12:
            # fee on residual exit
            r_piece = -sl_pct - _fee_frac(remaining) / max(remaining, 1e-12) * remaining
            # simpler: contribution = remaining * (-sl_pct) - fee on that frac
            realized += remaining * (-sl_pct) - _fee_frac(remaining)
            return {
                "r": round(realized, 6),
                "exit_reason": "sl_after_ladder" if slices else "sl",
                "days": i + 1,
                "exit_px": sl_px,
                "slices": slices,
                "remaining_at_end": 0.0,
            }

        # ladder tags on high
        sold_today = 0.0
        for t in trs:
            lvl = int(t.get("level") or 0)
            thr = float(t.get("r_pct") or 0)
            frac = float(t.get("sell_frac") or 0)
            if lvl in filled_levels or frac <= 0:
                continue
            thr_px = entry_px * (1.0 + thr)
            if hi < thr_px:
                continue
            # sell min(frac, remaining, room under moon bag accounting)
            # moon bag: never sell more than max_sellable total from original
            already_sold = 1.0 - remaining
            room = max_sellable - already_sold
            take = min(frac, remaining, max(0.0, room))
            if take <= 1e-12:
                continue
            realized += take * thr - _fee_frac(take)
            remaining -= take
            sold_today += take
            slices += 1
            filled_levels.add(lvl)

        if remaining <= 1e-12:
            return {
                "r": round(realized, 6),
                "exit_reason": "ladder_flat",
                "days": i + 1,
                "exit_px": cl,
                "slices": slices,
                "remaining_at_end": 0.0,
            }

    # path end: mark residual
    cl = float(bars[-1].get("close") or entry_px)
    r_end = (cl - entry_px) / entry_px
    realized += remaining * r_end - _fee_frac(remaining)
    return {
        "r": round(realized, 6),
        "exit_reason": "path_end",
        "days": len(bars),
        "exit_px": cl,
        "slices": slices,
        "remaining_at_end": round(remaining, 4),
    }


def _summ(rs: List[float]) -> Dict[str, Any]:
    if not rs:
        return {"n": 0, "sum_r": 0.0, "mean_r": None, "wr": None, "median_r": None, "p25": None, "p75": None}
    s = sorted(rs)
    n = len(s)
    mid = s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
    wins = sum(1 for x in rs if x > 0)
    return {
        "n": n,
        "sum_r": round(sum(rs), 6),
        "mean_r": round(sum(rs) / n, 6),
        "wr": round(wins / n, 4),
        "median_r": round(mid, 6),
        "p25": round(s[max(0, n // 4)], 6),
        "p75": round(s[min(n - 1, (3 * n) // 4)], 6),
    }


def _load_ladder_cfg() -> Tuple[List[Dict[str, Any]], float]:
    if CFG_PATH.exists():
        try:
            cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            ladder = cfg.get("ladder") or {}
            tr = list(ladder.get("tranches") or DEFAULT_LADDER)
            moon = float(ladder.get("leave_moon_bag_frac") or 0.25)
            return tr, moon
        except Exception:
            pass
    return list(DEFAULT_LADDER), 0.25


def _leg_prices(buy: Dict, sell: Dict) -> Tuple[Optional[float], Optional[float]]:
    def px(row: Dict) -> Optional[float]:
        for k in ("price", "fill_price", "avg_price", "executed_price"):
            try:
                v = float(row.get(k) or 0)
                if v > 0:
                    return v
            except (TypeError, ValueError):
                pass
        return None

    return px(buy), px(sell)


def build_ledger_legs(
    btc: List[Tuple[date, float]],
    *,
    lookback_days: int = 0,
    regime_filter: str = "bear",
) -> List[Dict[str, Any]]:
    rows = _load_unique_trades()
    rounds = _match_rounds(rows, lookback_days=lookback_days)
    legs = []
    ohlcv_cache: Dict[str, List[Dict[str, Any]]] = {}

    for buy, sell in rounds:
        pair = str(buy.get("pair") or sell.get("pair") or "")
        et = _parse_ts(buy.get("timestamp") or buy.get("ts"))
        xt = _parse_ts(sell.get("timestamp") or sell.get("ts"))
        if not et or not xt or xt <= et:
            continue
        entry_px, exit_px = _leg_prices(buy, sell)
        if not entry_px:
            continue
        entry_d = date.fromisoformat(_day(et))
        exit_d = date.fromisoformat(_day(xt))
        reg, btc_ret = _regime_at(btc, entry_d)
        if regime_filter and reg != regime_filter:
            continue
        if pair not in ohlcv_cache:
            ohlcv_cache[pair] = _load_ohlcv(pair)
        bars = _bars_between(ohlcv_cache[pair], _day(et), _day(xt))
        if len(bars) < 1:
            continue
        realized_r = None
        if exit_px and entry_px:
            realized_r = (exit_px / entry_px) - 1.0
        legs.append(
            {
                "source": "ledger",
                "pair": pair,
                "entry_d": _day(et),
                "exit_d": _day(xt),
                "entry_px": entry_px,
                "exit_px": exit_px,
                "realized_r": realized_r,
                "regime_at_entry": reg,
                "btc_ret_30d": btc_ret,
                "bars": bars,
            }
        )
    return legs


def build_synthetic_bear_legs(
    btc: List[Tuple[date, float]],
    pairs: Sequence[str],
    *,
    max_hold: int = MAX_HOLD_SYNTH,
    stride: int = SYNTH_STRIDE_DAYS,
) -> List[Dict[str, Any]]:
    """Non-overlapping entries on real daily bars while BTC regime is bear."""
    legs = []
    btc_by_d = {d: c for d, c in btc}

    for pair in pairs:
        candles = _load_ohlcv(pair)
        if len(candles) < LOOKBACK + max_hold + 5:
            continue
        # index by day
        by_d: Dict[str, Dict] = {}
        ordered_days: List[str] = []
        for c in candles:
            d = str(c.get("timestamp") or c.get("date") or "")[:10]
            if len(d) < 10:
                continue
            by_d[d] = c
            ordered_days.append(d)
        ordered_days = sorted(set(ordered_days))
        next_ok = ordered_days[0] if ordered_days else ""
        i = 0
        while i < len(ordered_days) - 2:
            d = ordered_days[i]
            if d < next_ok:
                i += 1
                continue
            try:
                dd = date.fromisoformat(d)
            except ValueError:
                i += 1
                continue
            reg, btc_ret = _regime_at(btc, dd)
            if reg != "bear":
                i += 1
                continue
            entry_c = by_d[d]
            try:
                entry_px = float(entry_c.get("close") or 0)
            except (TypeError, ValueError):
                i += 1
                continue
            if entry_px <= 0:
                i += 1
                continue
            # path forward max_hold days
            end_idx = min(len(ordered_days) - 1, i + max_hold)
            end_d = ordered_days[end_idx]
            bars = _bars_between(candles, d, end_d)
            # skip entry bar for path walk? include from next day for fair SL
            if len(bars) >= 2:
                path = bars[1:]
            else:
                path = bars
            if not path:
                i += 1
                continue
            legs.append(
                {
                    "source": "synthetic_bear_entry",
                    "pair": pair,
                    "entry_d": d,
                    "exit_d": end_d,
                    "entry_px": entry_px,
                    "exit_px": None,
                    "realized_r": None,
                    "regime_at_entry": "bear",
                    "btc_ret_30d": btc_ret,
                    "bars": path,
                }
            )
            # stride forward
            try:
                nd = date.fromisoformat(d) + timedelta(days=stride)
                next_ok = nd.isoformat()
            except ValueError:
                next_ok = ordered_days[min(i + stride, len(ordered_days) - 1)]
            i += 1
    return legs


def score_legs(
    legs: List[Dict[str, Any]],
    *,
    tranches: Sequence[Dict[str, Any]],
    moon: float,
    sl_pct: float = DEFAULT_SL,
) -> Dict[str, Any]:
    rows = []
    for L in legs:
        bars = L["bars"]
        ep = float(L["entry_px"])
        a = simulate_sl_ride(ep, bars, sl_pct)
        b = simulate_full_tp(ep, bars, sl_pct=sl_pct, tp=0.06)
        c = simulate_ladder(ep, bars, sl_pct=sl_pct, tranches=tranches, moon_bag_frac=moon)
        if a.get("r") is None or c.get("r") is None:
            continue
        rows.append(
            {
                "source": L["source"],
                "pair": L["pair"],
                "entry_d": L["entry_d"],
                "regime": L["regime_at_entry"],
                "btc_ret_30d": L.get("btc_ret_30d"),
                "sl_ride_r": a["r"],
                "sl_ride_reason": a.get("exit_reason"),
                "full_tp_r": b.get("r"),
                "full_tp_reason": b.get("exit_reason"),
                "ladder_r": c["r"],
                "ladder_reason": c.get("exit_reason"),
                "ladder_slices": c.get("slices"),
                "delta_ladder_vs_sl": round(float(c["r"]) - float(a["r"]), 6),
                "delta_ladder_vs_full_tp": round(float(c["r"]) - float(b["r"] or 0), 6)
                if b.get("r") is not None
                else None,
                "delta_full_tp_vs_sl": round(float(b["r"]) - float(a["r"]), 6)
                if b.get("r") is not None
                else None,
            }
        )
    return {"n": len(rows), "rows": rows}


def decide(block: Dict[str, Any], *, ledger_n: int = 0) -> Dict[str, Any]:
    """Plain-English call from summary stats."""
    n = int(block.get("n") or 0)
    if n < MIN_N:
        return {
            "call": "inconclusive",
            "plain": f"Only {n} paths (need ≥{MIN_N}). Keep shadow; do not promote.",
            "edge_class": "insufficient_n",
        }
    mean_d = block.get("mean_delta_ladder_vs_sl")
    mean_l = block.get("ladder", {}).get("mean_r")
    mean_s = block.get("sl_ride", {}).get("mean_r")
    mean_ftp = block.get("full_tp", {}).get("mean_r")
    mean_d_ftp = block.get("mean_delta_ladder_vs_full_tp")
    if mean_d is None:
        return {"call": "inconclusive", "plain": "No delta stats.", "edge_class": "no_stats"}

    # Absolute still red = less-loss framing only
    abs_note = ""
    if mean_l is not None and mean_l < 0:
        abs_note = (
            f" Absolute ladder mean R is still negative ({mean_l*100:.2f}%) — "
            "this is **less-loss vs ride-SL**, not a profit engine."
        )

    ledger_note = ""
    if ledger_n <= 0:
        ledger_note = (
            " Sample is **synthetic bear entries on real daily bars** "
            "(0 ledger legs entered in bear) — treat as design evidence, not live book proof."
        )
    elif ledger_n < MIN_N:
        ledger_note = f" Ledger bear legs only N={ledger_n} (thin); synthetic fills the rest."

    if mean_d >= 0.005:
        call = "pursue_shadow"
        plain = (
            f"Ladder beats ride-to-SL by ~{mean_d*100:.2f}% mean R on N={n}. "
            "Keep Phase-1 shadow; **not** a live promote."
        )
        edge = "LESS_LOSS_VS_SL" if (mean_l is not None and mean_l < 0) else "POS_DELTA_VS_SL"
    elif mean_d <= -0.005:
        call = "drop"
        plain = (
            f"Ladder loses to ride-to-SL by ~{abs(mean_d)*100:.2f}% mean R on N={n}. "
            "Do not promote; redesign or drop."
        )
        edge = "worse_than_sl"
    else:
        call = "no_clear_edge"
        plain = (
            f"Ladder ≈ ride-to-SL (Δmean R {mean_d*100:.2f}%) on N={n}. "
            "Optional discipline product only; no edge claim."
        )
        edge = "flat_vs_sl"

    note_ftp = ""
    if mean_d_ftp is not None and mean_ftp is not None and mean_s is not None:
        if mean_ftp < mean_s - 0.002:
            note_ftp = " Full +6% TP still worse than ride-SL on mean (prior intact)."
        elif mean_ftp > mean_s + 0.002:
            note_ftp = (
                f" Note: full +6% TP mean R ({mean_ftp*100:.2f}%) also beats ride-SL here;"
                " ladder is not uniquely magical vs one-shot TP on this tape."
            )
        if mean_d_ftp >= 0.003:
            note_ftp += " Ladder beats full +6% TP on mean."
        elif mean_d_ftp is not None and mean_d_ftp <= -0.003:
            note_ftp += " Ladder does **not** beat full +6% TP on mean in this sample."

    plain = plain + abs_note + ledger_note + note_ftp
    return {
        "call": call,
        "plain": plain,
        "edge_class": edge,
        "mean_delta_ladder_vs_sl": mean_d,
        "mean_ladder_r": mean_l,
        "mean_sl_ride_r": mean_s,
        "mean_full_tp_r": mean_ftp,
        "ledger_bear_n": ledger_n,
    }


def _summarize_rows(rows: List[Dict[str, Any]], *, ledger_n: int = 0) -> Dict[str, Any]:
    sl = [float(r["sl_ride_r"]) for r in rows if r.get("sl_ride_r") is not None]
    ld = [float(r["ladder_r"]) for r in rows if r.get("ladder_r") is not None]
    ftp = [float(r["full_tp_r"]) for r in rows if r.get("full_tp_r") is not None]
    d_ls = [float(r["delta_ladder_vs_sl"]) for r in rows if r.get("delta_ladder_vs_sl") is not None]
    d_lf = [
        float(r["delta_ladder_vs_full_tp"])
        for r in rows
        if r.get("delta_ladder_vs_full_tp") is not None
    ]
    block = {
        "n": len(rows),
        "sl_ride": _summ(sl),
        "ladder": _summ(ld),
        "full_tp": _summ(ftp),
        "mean_delta_ladder_vs_sl": round(sum(d_ls) / len(d_ls), 6) if d_ls else None,
        "sum_delta_ladder_vs_sl": round(sum(d_ls), 6) if d_ls else None,
        "mean_delta_ladder_vs_full_tp": round(sum(d_lf) / len(d_lf), 6) if d_lf else None,
        "pct_ladder_beats_sl": round(sum(1 for x in d_ls if x > 0) / len(d_ls), 4) if d_ls else None,
        "mean_slices": round(
            sum(float(r.get("ladder_slices") or 0) for r in rows) / len(rows), 3
        )
        if rows
        else None,
    }
    block["decision"] = decide(block, ledger_n=ledger_n)
    return block


def run(*, include_synthetic: bool = True, ledger_lookback: int = 0) -> Dict[str, Any]:
    tranches, moon = _load_ladder_cfg()
    btc = _btc_closes()
    if len(btc) < LOOKBACK + 50:
        return {
            "error": "insufficient_btc_ohlcv",
            "btc_bars": len(btc),
            "recommendation": "inconclusive",
        }

    ledger_bear = build_ledger_legs(btc, lookback_days=ledger_lookback, regime_filter="bear")
    ledger_all = build_ledger_legs(btc, lookback_days=ledger_lookback, regime_filter="")
    # also ledger legs that are bear OR transition soft-down? stick to bear only for primary

    synth = []
    pairs = list(PAIR_TO_SHORT.keys())
    if include_synthetic:
        synth = build_synthetic_bear_legs(btc, pairs)

    scored_ledger = score_legs(ledger_bear, tranches=tranches, moon=moon)
    scored_synth = score_legs(synth, tranches=tranches, moon=moon)
    # combined unique by pair+entry_d
    combined_rows = list(scored_ledger["rows"]) + list(scored_synth["rows"])

    ln = scored_ledger["n"]
    by_source = {
        "ledger_bear": _summarize_rows(scored_ledger["rows"], ledger_n=ln),
        "synthetic_bear": _summarize_rows(scored_synth["rows"], ledger_n=ln),
        "combined_bear": _summarize_rows(combined_rows, ledger_n=ln),
    }
    # per-pair on combined
    by_pair: Dict[str, Any] = {}
    for p in sorted({r["pair"] for r in combined_rows}):
        by_pair[p] = _summarize_rows([r for r in combined_rows if r["pair"] == p], ledger_n=ln)

    # Primary decision: prefer combined if synth used; else ledger
    primary_key = "combined_bear" if include_synthetic else "ledger_bear"
    primary = by_source[primary_key]
    dec = primary.get("decision") or {}

    # Regime mix on ledger for context
    reg_counts = defaultdict(int)
    for L in ledger_all:
        reg_counts[L.get("regime_at_entry") or "?"] += 1

    payload = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "schema": "bear_ladder_path_cf_v1",
        "sl_pct": DEFAULT_SL,
        "fee_rt": FEE_RT,
        "ladder_tranches": tranches,
        "moon_bag_frac": moon,
        "min_n": MIN_N,
        "btc_bars": len(btc),
        "ledger_rounds_all_regimes": len(ledger_all),
        "ledger_regime_counts": dict(reg_counts),
        "n_ledger_bear": scored_ledger["n"],
        "n_synthetic_bear": scored_synth["n"],
        "n_combined": len(combined_rows),
        "by_source": by_source,
        "by_pair": {k: {kk: vv for kk, vv in v.items() if kk != "decision"} | {"call": (v.get("decision") or {}).get("call")} for k, v in by_pair.items()},
        "primary_sample": primary_key,
        "recommendation": dec.get("call") or "inconclusive",
        "plain_english": dec.get("plain") or "",
        "live_money": False,
        "notes": [
            "Optimistic threshold fills when day's high tags level; SL same-day wins on residual.",
            "Synthetic entries: close on bear-regime day, path up to 45d, stride 14d — real bars only.",
            "Not a live promote. Shadow collection still required in live bear.",
        ],
        # compact row sample
        "sample_rows": combined_rows[:40],
    }
    return payload


def write_report(payload: Dict[str, Any]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = REPORTS / f"BEAR_LADDER_PATH_CF_{day}.md"
    latest = REPORTS / "BEAR_LADDER_PATH_CF_LATEST.md"
    bs = payload.get("by_source") or {}
    prim = bs.get(payload.get("primary_sample") or "combined_bear") or {}

    def fmt_block(name: str, b: Dict[str, Any]) -> List[str]:
        if not b:
            return [f"### {name}", "empty", ""]
        d = b.get("decision") or {}
        lines = [
            f"### {name}",
            f"- N={b.get('n')} · call **{d.get('call')}**",
            f"- {d.get('plain')}",
            f"- sl_ride mean R: {((b.get('sl_ride') or {}).get('mean_r'))}",
            f"- ladder mean R: {((b.get('ladder') or {}).get('mean_r'))}",
            f"- full_tp_06 mean R: {((b.get('full_tp') or {}).get('mean_r'))}",
            f"- Δ ladder−SL mean: {b.get('mean_delta_ladder_vs_sl')} · "
            f"ladder beats SL on {b.get('pct_ladder_beats_sl')}",
            f"- mean ladder slices/path: {b.get('mean_slices')}",
            "",
        ]
        return lines

    lines = [
        "# Bear ladder path CF (P2)",
        "",
        f"**As of:** {payload.get('as_of')}",
        f"**Recommendation:** `{payload.get('recommendation')}`",
        f"**Live money:** {payload.get('live_money')}",
        "",
        "## Plain English",
        "",
        payload.get("plain_english") or "",
        "",
        "## Setup",
        "",
        f"- SL floor: {payload.get('sl_pct')}",
        f"- Ladder: {json.dumps(payload.get('ladder_tranches'))}",
        f"- Moon bag: {payload.get('moon_bag_frac')}",
        f"- BTC bars: {payload.get('btc_bars')}",
        f"- Ledger rounds (all regimes): {payload.get('ledger_rounds_all_regimes')} "
        f"`{payload.get('ledger_regime_counts')}`",
        f"- Ledger bear legs scored: {payload.get('n_ledger_bear')}",
        f"- Synthetic bear paths: {payload.get('n_synthetic_bear')}",
        f"- Combined: {payload.get('n_combined')}",
        "",
        "## Results by sample",
        "",
    ]
    for k in ("ledger_bear", "synthetic_bear", "combined_bear"):
        lines.extend(fmt_block(k, bs.get(k) or {}))

    lines += [
        "## Per-pair (combined)",
        "",
        "| Pair | N | call | mean Δ ladder−SL | ladder mean R | sl mean R |",
        "|------|---|------|------------------|---------------|-----------|",
    ]
    for p, b in sorted((payload.get("by_pair") or {}).items()):
        lines.append(
            f"| {p} | {b.get('n')} | {b.get('call')} | {b.get('mean_delta_ladder_vs_sl')} | "
            f"{(b.get('ladder') or {}).get('mean_r')} | {(b.get('sl_ride') or {}).get('mean_r')} |"
        )
    lines += [
        "",
        "## Notes",
        "",
    ]
    for n in payload.get("notes") or []:
        lines.append(f"- {n}")
    lines += [
        "",
        "## Next",
        "",
        "- If `pursue_shadow`: keep P1 runner shadow; do **not** live_apply.",
        "- If `drop`: disable ladder enabled or redesign tranches after review.",
        "- If `inconclusive` / `no_clear_edge`: hold shadow, no edge marketing.",
        "",
    ]
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    OUT_STATE.parent.mkdir(parents=True, exist_ok=True)
    # slim state (drop huge bars already not in payload)
    slim = dict(payload)
    slim.pop("sample_rows", None)
    # keep sample compact
    slim["sample_rows"] = payload.get("sample_rows") or []
    OUT_STATE.write_text(json.dumps(slim, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def main() -> int:
    payload = run(include_synthetic=True, ledger_lookback=0)
    path = write_report(payload)
    print(
        json.dumps(
            {
                "recommendation": payload.get("recommendation"),
                "plain_english": payload.get("plain_english"),
                "n_ledger_bear": payload.get("n_ledger_bear"),
                "n_synthetic_bear": payload.get("n_synthetic_bear"),
                "n_combined": payload.get("n_combined"),
                "report": str(path),
                "primary": (payload.get("by_source") or {}).get(payload.get("primary_sample") or ""),
            },
            indent=2,
            default=str,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
