#!/usr/bin/env python3
"""Exit threshold × regime study (offline, real ledger + OHLCV).

Question (plain English):
  Had we used take-profit and/or RSI hard-exit thresholds instead of (or
  before) riding to stop-loss, would profit improve — and does the best
  setup differ by Bull / Bear / Flat / Transition?

Method:
  1. FIFO-match buy→sell legs from trades/phase6_trades.jsonl (real fills).
  2. Replay daily OHLCV path from entry→exit.
  3. Label BTC regime at entry (same thresholds as regime_cash detector).
  4. Counterfactual engines (whichever hits first on the path):
       - SL only at -sl_pct (default 3%)
       - Fixed TP at each tp in grid OR SL
       - RSI overbought at each rsi in grid (exit at that day's close) OR SL
       - Combined: TP OR RSI OR SL
  5. Score vs SL-only baseline by regime; pick best TP and best RSI per regime.

Writes (no live config):
  data/state/exit_threshold_regime_study_latest.json
  reports/EXIT_THRESHOLD_REGIME_STUDY_YYYY-MM-DD.{md,json}

Caveats (always surface):
  - Daily bars overstate ease of TP touch / understate intraday SL gaps.
  - Same-day TP high + SL low → SL wins (conservative).
  - RSI exit at close the day threshold crosses (no tick RSI).
  - OHLCV coverage may lag newest live legs.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRADES = ROOT / "trades" / "phase6_trades.jsonl"
OHLCV_DIR = ROOT / "backtests" / "data"
OUT_STATE = ROOT / "data" / "state" / "exit_threshold_regime_study_latest.json"
REPORTS = ROOT / "reports"

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
    "PAXG-USD": "paxg",
}

# Align with config/regime_cash_policy.json detector defaults
BULL_RET = 15.0
BEAR_RET = -10.0
FLAT_ABS = 8.0
REGIME_LOOKBACK = 30

DEFAULT_SL = 0.03
TP_GRID = (0.04, 0.05, 0.06, 0.08, 0.10, 0.12)
RSI_GRID = (60.0, 65.0, 68.0, 70.0, 75.0, 80.0)
RSI_PERIOD = 14
FEE_RT = 0.001  # ~10 bps round-trip haircut on CF exits (conservative)
MIN_N_REGIME = 8  # below → inconclusive for that regime
MIN_N_GLOBAL = 15


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
    candidates = sorted(OHLCV_DIR.glob(f"backtest_historical_ohlcv_{short}*.json"))
    if not candidates:
        return []
    try:
        data = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _load_unique_trades() -> List[Dict[str, Any]]:
    if not TRADES.exists():
        return []
    seen = set()
    rows: List[Dict[str, Any]] = []
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


def _match_rounds(rows: List[Dict[str, Any]], lookback_days: int) -> List[Tuple[Dict, Dict]]:
    cut = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    buys: Dict[str, List[Dict]] = {}
    rounds: List[Tuple[Dict, Dict]] = []
    timed: List[Tuple[datetime, Dict]] = []
    for r in rows:
        t = _parse_ts(r.get("timestamp") or r.get("ts") or r.get("filled_at"))
        if t is None or t < cut:
            continue
        timed.append((t, r))
    timed.sort(key=lambda x: x[0])
    for t, r in timed:
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
            rounds.append((q.pop(0), r))
    return rounds


def _leg_prices(buy: Dict, sell: Dict) -> Tuple[Optional[float], Optional[float], float]:
    """Return entry_px, exit_px, realized_r."""
    entry_px = buy.get("entry_price") or buy.get("price") or buy.get("avg_price") or buy.get("fill_price")
    exit_px = sell.get("exit_price") or sell.get("price") or sell.get("avg_price") or sell.get("fill_price")
    try:
        entry_px = float(entry_px) if entry_px is not None else None
        exit_px = float(exit_px) if exit_px is not None else None
    except (TypeError, ValueError):
        return None, None, 0.0
    if (entry_px is None or entry_px <= 0) and sell.get("pnl") is not None:
        try:
            pnl = float(sell["pnl"])
            qty = float(sell.get("qty") or 0)
            if qty and exit_px:
                entry_px = (qty * float(exit_px) - pnl) / qty
        except (TypeError, ValueError):
            pass
    if exit_px is None or exit_px <= 0:
        try:
            pct = sell.get("pnl_pct")
            if entry_px and pct is not None:
                exit_px = float(entry_px) * (1.0 + float(pct))
        except (TypeError, ValueError):
            pass
    if entry_px is None or entry_px <= 0 or exit_px is None or exit_px <= 0:
        return None, None, 0.0
    realized_r = (float(exit_px) - float(entry_px)) / float(entry_px)
    try:
        pct = sell.get("pnl_pct")
        if pct is not None and abs(float(pct)) <= 0.5:
            realized_r = float(pct)
    except (TypeError, ValueError):
        pass
    return float(entry_px), float(exit_px), float(realized_r)


def _bars_between(candles: List[Dict[str, Any]], start_d: str, end_d: str) -> List[Dict[str, Any]]:
    out = []
    for c in candles:
        d = str(c.get("timestamp") or "")[:10]
        if start_d <= d <= end_d:
            out.append(c)
    return out


def _rsi_series(closes: Sequence[float], period: int = RSI_PERIOD) -> List[Optional[float]]:
    """Wilder RSI; None until enough bars."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period + 1:
        return out
    gains = []
    losses = []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0:
        out[period] = 100.0
    else:
        rs = avg_g / avg_l
        out[period] = 100.0 - (100.0 / (1.0 + rs))
    for i in range(period + 1, n):
        d = closes[i] - closes[i - 1]
        g = max(d, 0.0)
        l = max(-d, 0.0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        if avg_l == 0:
            out[i] = 100.0
        else:
            rs = avg_g / avg_l
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def _btc_closes() -> List[Tuple[date, float]]:
    candles = _load_ohlcv("BTC-USD")
    out: List[Tuple[date, float]] = []
    for c in candles:
        ts = str(c.get("timestamp") or "")[:10]
        try:
            d = date.fromisoformat(ts)
            cl = float(c.get("close") or 0)
        except Exception:
            continue
        if cl > 0:
            out.append((d, cl))
    out.sort(key=lambda x: x[0])
    return out


def _regime_at(btc: List[Tuple[date, float]], as_of: date) -> Tuple[str, Optional[float]]:
    if not btc:
        return "unknown", None
    start = as_of - timedelta(days=REGIME_LOOKBACK)
    window = [(d, c) for d, c in btc if start <= d <= as_of]
    if len(window) < 2:
        # nearest prior bars
        prior = [(d, c) for d, c in btc if d <= as_of]
        window = prior[-min(len(prior), REGIME_LOOKBACK) :]
    if len(window) < 2:
        return "unknown", None
    p0, p1 = window[0][1], window[-1][1]
    ret = (p1 / p0 - 1.0) * 100.0 if p0 > 0 else 0.0
    if ret >= BULL_RET:
        reg = "bull"
    elif ret <= BEAR_RET:
        reg = "bear"
    elif abs(ret) <= FLAT_ABS:
        reg = "flat"
    else:
        reg = "transition"
    return reg, round(ret, 3)


def _simulate_path(
    entry_px: float,
    bars: List[Dict[str, Any]],
    *,
    sl_pct: float,
    tp: Optional[float],
    rsi_th: Optional[float],
    rsi_vals: List[Optional[float]],
    bar_offset: int,
) -> Dict[str, Any]:
    """Walk daily bars; first hit among SL / TP / RSI wins.

    SL: day's low <= entry*(1-sl) → exit at stop price (optimistic fill at stop).
    TP: day's high >= entry*(1+tp) → exit at tp (optimistic).
    Same day both: SL wins (conservative — don't bank TP through a stop day).
    RSI: rsi[i] >= th → exit at that day's close.
    If nothing fires: exit last close (open path end / still held to ledger exit).
    """
    if entry_px <= 0 or not bars:
        return {"r": None, "exit_reason": "no_path", "days": 0}

    sl_px = entry_px * (1.0 - sl_pct)
    tp_px = entry_px * (1.0 + tp) if tp is not None else None

    for i, c in enumerate(bars):
        h = float(c.get("high") or c.get("close") or 0)
        l = float(c.get("low") or c.get("close") or 0)
        cl = float(c.get("close") or 0)
        # SL first (conservative same-day)
        if l > 0 and l <= sl_px:
            r = -sl_pct - FEE_RT
            return {"r": r, "exit_reason": "sl", "days": i + 1, "exit_px": sl_px}
        if tp is not None and tp_px is not None and h > 0 and h >= tp_px:
            r = float(tp) - FEE_RT
            return {"r": r, "exit_reason": "tp", "days": i + 1, "exit_px": tp_px}
        if rsi_th is not None:
            idx = bar_offset + i
            rsi = rsi_vals[idx] if 0 <= idx < len(rsi_vals) else None
            # require RSI computed from closes *before/at* this bar; value is end-of-day
            if rsi is not None and rsi >= rsi_th and cl > 0:
                r = (cl - entry_px) / entry_px - FEE_RT
                return {
                    "r": r,
                    "exit_reason": "rsi",
                    "days": i + 1,
                    "exit_px": cl,
                    "rsi": rsi,
                }

    # path end without SL/TP/RSI — use last close (matches holding to ledger exit day)
    last = bars[-1]
    cl = float(last.get("close") or entry_px)
    r = (cl - entry_px) / entry_px - FEE_RT
    return {"r": r, "exit_reason": "path_end", "days": len(bars), "exit_px": cl}


def _summ(rs: List[float]) -> Dict[str, Any]:
    if not rs:
        return {"n": 0, "sum_r": 0.0, "mean_r": None, "wr": None, "median_r": None}
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
    }


def run(
    lookback_days: int = 120,
    sl_pct: float = DEFAULT_SL,
    tp_grid: Sequence[float] = TP_GRID,
    rsi_grid: Sequence[float] = RSI_GRID,
) -> Dict[str, Any]:
    rows = _load_unique_trades()
    rounds = _match_rounds(rows, lookback_days=lookback_days)
    btc = _btc_closes()

    legs: List[Dict[str, Any]] = []
    skipped = defaultdict(int)

    # Preload OHLCV + RSI per pair
    ohlcv_cache: Dict[str, List[Dict[str, Any]]] = {}
    rsi_cache: Dict[str, List[Optional[float]]] = {}
    day_index: Dict[str, Dict[str, int]] = {}

    def _prep(pair: str) -> None:
        if pair in ohlcv_cache:
            return
        candles = _load_ohlcv(pair)
        ohlcv_cache[pair] = candles
        closes = []
        idx: Dict[str, int] = {}
        for i, c in enumerate(candles):
            d = str(c.get("timestamp") or "")[:10]
            idx[d] = i
            try:
                closes.append(float(c.get("close") or 0))
            except (TypeError, ValueError):
                closes.append(0.0)
        rsi_cache[pair] = _rsi_series(closes, RSI_PERIOD)
        day_index[pair] = idx

    for buy, sell in rounds:
        pair = str(buy.get("pair") or sell.get("pair") or "")
        et = _parse_ts(buy.get("timestamp") or buy.get("ts"))
        xt = _parse_ts(sell.get("timestamp") or sell.get("ts"))
        if not pair or not et or not xt:
            skipped["bad_meta"] += 1
            continue
        entry_px, exit_px, realized_r = _leg_prices(buy, sell)
        if entry_px is None:
            skipped["no_price"] += 1
            continue
        reason = str(sell.get("reason") or "")
        # Focus structural comparison; still keep all sells but tag SL-dominated
        is_sl = "stop" in reason.lower()

        _prep(pair)
        candles = ohlcv_cache.get(pair) or []
        if not candles:
            skipped["no_ohlcv"] += 1
            continue
        bars = _bars_between(candles, _day(et), _day(xt))
        if len(bars) < 1:
            skipped["no_bars"] += 1
            continue

        entry_d = date.fromisoformat(_day(et))
        regime, btc_ret = _regime_at(btc, entry_d)

        # offset of first bar in full series
        first_d = str(bars[0].get("timestamp") or "")[:10]
        bar0 = day_index[pair].get(first_d, 0)
        rsi_vals = rsi_cache[pair]

        # Baseline engines
        sl_only = _simulate_path(
            entry_px, bars, sl_pct=sl_pct, tp=None, rsi_th=None, rsi_vals=rsi_vals, bar_offset=bar0
        )
        # realized is truth for what happened; SL-sim is clean policy baseline
        leg = {
            "pair": pair,
            "entry_ts": et.isoformat(),
            "exit_ts": xt.isoformat(),
            "entry_px": entry_px,
            "exit_px": exit_px,
            "realized_r": round(realized_r, 6),
            "reason": reason,
            "is_sl_exit": is_sl,
            "regime_at_entry": regime,
            "btc_ret_30d_pct": btc_ret,
            "bars": len(bars),
            "sl_only_r": sl_only.get("r"),
            "sl_only_reason": sl_only.get("exit_reason"),
            "cf": {},
        }

        for tp in tp_grid:
            key = f"tp_{int(tp * 100):02d}"
            leg["cf"][key] = _simulate_path(
                entry_px, bars, sl_pct=sl_pct, tp=tp, rsi_th=None, rsi_vals=rsi_vals, bar_offset=bar0
            )
        for rsi_th in rsi_grid:
            key = f"rsi_{int(rsi_th)}"
            leg["cf"][key] = _simulate_path(
                entry_px,
                bars,
                sl_pct=sl_pct,
                tp=None,
                rsi_th=rsi_th,
                rsi_vals=rsi_vals,
                bar_offset=bar0,
            )
        # Combined best-guess mid: tp06 + rsi68 (live-ish knobs) for reference
        leg["cf"]["tp06_rsi68"] = _simulate_path(
            entry_px, bars, sl_pct=sl_pct, tp=0.06, rsi_th=68.0, rsi_vals=rsi_vals, bar_offset=bar0
        )
        legs.append(leg)

    # Score policies
    def collect(policy_key: Optional[str], regime: Optional[str] = None, sl_only_legs: bool = False):
        rs = []
        exit_mix = defaultdict(int)
        for L in legs:
            if regime and L["regime_at_entry"] != regime:
                continue
            if sl_only_legs and not L["is_sl_exit"]:
                continue
            if policy_key is None:
                r = L["sl_only_r"]
                er = L["sl_only_reason"]
            else:
                cell = L["cf"].get(policy_key) or {}
                r = cell.get("r")
                er = cell.get("exit_reason")
            if r is None:
                continue
            rs.append(float(r))
            exit_mix[str(er)] += 1
        out = _summ(rs)
        out["exit_mix"] = dict(exit_mix)
        return out

    regimes = sorted({L["regime_at_entry"] for L in legs})
    policies: List[Tuple[str, Optional[str]]] = [("sl_only", None)]
    for tp in tp_grid:
        policies.append((f"tp_{int(tp * 100):02d}", f"tp_{int(tp * 100):02d}"))
    for rsi_th in rsi_grid:
        policies.append((f"rsi_{int(rsi_th)}", f"rsi_{int(rsi_th)}"))
    policies.append(("tp06_rsi68", "tp06_rsi68"))

    by_regime: Dict[str, Any] = {}
    for reg in ["all"] + regimes:
        rkey = reg
        block: Dict[str, Any] = {"policies": {}, "best_tp": None, "best_rsi": None, "best_overall": None}
        base = collect(None, None if reg == "all" else reg)
        block["policies"]["sl_only"] = base
        best_tp = None
        best_rsi = None
        best_any = ("sl_only", base.get("sum_r") or -1e9)

        for name, pkey in policies:
            if name == "sl_only":
                continue
            s = collect(pkey, None if reg == "all" else reg)
            # delta vs SL-only on same filter
            if base.get("n") and s.get("n") and base["n"] == s["n"] and base.get("sum_r") is not None:
                s["delta_sum_r_vs_sl"] = round(s["sum_r"] - base["sum_r"], 6)
                s["delta_mean_r_vs_sl"] = round((s["mean_r"] or 0) - (base["mean_r"] or 0), 6)
            block["policies"][name] = s
            sr = s.get("sum_r")
            if sr is not None and sr > best_any[1]:
                best_any = (name, sr)
            if name.startswith("tp_") and name != "tp06_rsi68":
                if best_tp is None or (sr is not None and sr > (block["policies"].get(best_tp, {}).get("sum_r") or -1e9)):
                    best_tp = name
            if name.startswith("rsi_"):
                if best_rsi is None or (sr is not None and sr > (block["policies"].get(best_rsi, {}).get("sum_r") or -1e9)):
                    best_rsi = name

        block["best_tp"] = best_tp
        block["best_rsi"] = best_rsi
        block["best_overall"] = best_any[0]
        n = base.get("n") or 0
        # Decision per regime
        if n < (MIN_N_GLOBAL if reg == "all" else MIN_N_REGIME):
            block["call"] = "inconclusive_thin_n"
        else:
            bt = block["policies"].get(best_tp or "", {})
            br = block["policies"].get(best_rsi or "", {})
            d_tp = bt.get("delta_sum_r_vs_sl")
            d_rsi = br.get("delta_sum_r_vs_sl")
            # meaningful = delta sum r > 0.15 (~15 percentage-points of one full R across book)
            # and mean improvement > 0.5%
            def meaningful(d_sum, d_mean, pol):
                if d_sum is None:
                    return False
                # require improvement on sum and not pure path_end gaming
                mix = pol.get("exit_mix") or {}
                fired = sum(v for k, v in mix.items() if k in ("tp", "rsi"))
                return d_sum >= 0.15 and (d_mean or 0) >= 0.005 and fired >= max(3, int(0.15 * n))

            tp_ok = meaningful(d_tp, bt.get("delta_mean_r_vs_sl"), bt)
            rsi_ok = meaningful(d_rsi, br.get("delta_mean_r_vs_sl"), br)
            if tp_ok and rsi_ok:
                # pick larger delta
                if (d_tp or 0) >= (d_rsi or 0):
                    block["call"] = f"prefer_tp_{best_tp}"
                else:
                    block["call"] = f"prefer_rsi_{best_rsi}"
            elif tp_ok:
                block["call"] = f"prefer_tp_{best_tp}"
            elif rsi_ok:
                block["call"] = f"prefer_rsi_{best_rsi}"
            elif (d_tp is not None and d_tp < -0.10) or (d_rsi is not None and d_rsi < -0.10):
                block["call"] = "prefer_sl_ride"  # early exits hurt
            else:
                block["call"] = "no_clear_edge_vs_sl"
        by_regime[rkey] = block

    # SL-exit-only slice (closer to user's question)
    sl_slice = {}
    for reg in ["all"] + regimes:
        base = collect(None, None if reg == "all" else reg, sl_only_legs=True)
        row = {"sl_only": base, "policies": {}}
        best = ("sl_only", base.get("sum_r") or -1e9)
        for name, pkey in policies:
            if name == "sl_only":
                continue
            s = collect(pkey, None if reg == "all" else reg, sl_only_legs=True)
            if base.get("n") and s.get("n") == base["n"]:
                s["delta_sum_r_vs_sl"] = round(s["sum_r"] - base["sum_r"], 6)
            row["policies"][name] = s
            if (s.get("sum_r") or -1e9) > best[1]:
                best = (name, s.get("sum_r") or -1e9)
        row["best"] = best[0]
        sl_slice[reg] = row

    # Global recommendation
    all_block = by_regime.get("all") or {}
    n_all = (all_block.get("policies") or {}).get("sl_only", {}).get("n") or 0
    if n_all < MIN_N_GLOBAL:
        enum = "insufficient_data"
    else:
        calls = {
            r: by_regime[r]["call"]
            for r in by_regime
            if r != "all" and not str(by_regime[r]["call"]).startswith("inconclusive")
        }
        if not calls:
            enum = "insufficient_data"
        elif all(c == "prefer_sl_ride" or c == "no_clear_edge_vs_sl" for c in calls.values()):
            enum = "prefer_sl_or_observe"  # aligns with prior ride-it-out
        elif len(set(calls.values())) == 1:
            enum = "uniform_" + list(calls.values())[0]
        else:
            enum = "regime_dependent"

    # Plain-English winners table
    winners = []
    for reg, block in by_regime.items():
        bt = block.get("best_tp")
        br = block.get("best_rsi")
        btp = (block.get("policies") or {}).get(bt or "", {})
        brp = (block.get("policies") or {}).get(br or "", {})
        base = (block.get("policies") or {}).get("sl_only", {})
        winners.append(
            {
                "regime": reg,
                "n": base.get("n"),
                "sl_sum_r": base.get("sum_r"),
                "sl_mean_r": base.get("mean_r"),
                "best_tp": bt,
                "best_tp_delta_sum_r": btp.get("delta_sum_r_vs_sl"),
                "best_rsi": br,
                "best_rsi_delta_sum_r": brp.get("delta_sum_r_vs_sl"),
                "best_overall": block.get("best_overall"),
                "call": block.get("call"),
            }
        )

    report = {
        "schema": "exit_threshold_regime_study_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "sl_pct": sl_pct,
        "tp_grid": list(tp_grid),
        "rsi_grid": list(rsi_grid),
        "fee_rt": FEE_RT,
        "live_config_writes": False,
        "n_rounds_matched": len(rounds),
        "n_legs_usable": len(legs),
        "skipped": dict(skipped),
        "regime_thresholds": {
            "bull_return_pct": BULL_RET,
            "bear_return_pct": BEAR_RET,
            "flat_abs_pct": FLAT_ABS,
            "lookback_days": REGIME_LOOKBACK,
        },
        "recommendation_enum": enum,
        "winners": winners,
        "by_regime": by_regime,
        "sl_exit_legs_only": sl_slice,
        "legs_sample": legs[:40],
        "notes": [
            "Daily OHLCV: TP touch optimistic; same-day SL+TP → SL wins.",
            "RSI exit at daily close when RSI>=threshold (Wilder 14).",
            "Baseline for deltas is simulated SL-only on the same path, not mixed rotation exits.",
            "realized_r kept for audit; policy ranking uses path engines.",
            "Prior sim 'ride it out' is the null; overturn only with meaningful delta + N gates.",
            "No live take_profit or operator_approve change from this report alone.",
        ],
    }
    return report


def to_md(rep: Dict[str, Any]) -> str:
    lines = [
        f"# Exit threshold × regime study — {rep['as_of'][:10]}",
        "",
        "## Plain English (read first)",
        "",
        f"**Recommendation enum:** `{rep['recommendation_enum']}`",
        f"- Usable legs: **{rep['n_legs_usable']}** (matched rounds {rep['n_rounds_matched']}) · lookback {rep['lookback_days']}d",
        f"- Stop baseline: **-{rep['sl_pct']*100:.0f}%** · fee haircut on CF: {rep['fee_rt']*100:.1f}% round-trip",
        f"- TP grid: {rep['tp_grid']} · RSI grid: {rep['rsi_grid']}",
        f"- Skipped: {rep.get('skipped')}",
        "",
        "### What we asked",
        "1. Best **take-profit** % vs riding to stop — by regime",
        "2. Best **RSI overbought exit** vs riding to stop — by regime",
        "3. Whether **one setup** works across Bull / Bear / Flat / Transition (we do **not** assume yes)",
        "",
        "### Winners by regime (path sim vs SL-only)",
        "",
        "| Regime | N | SL mean r | Best TP | Δ sum r | Best RSI | Δ sum r | Call |",
        "|--------|--:|----------:|---------|--------:|----------|--------:|------|",
    ]
    for w in rep.get("winners") or []:
        lines.append(
            f"| {w['regime']} | {w.get('n')} | {w.get('sl_mean_r')} | {w.get('best_tp')} | "
            f"{w.get('best_tp_delta_sum_r')} | {w.get('best_rsi')} | {w.get('best_rsi_delta_sum_r')} | "
            f"`{w.get('call')}` |"
        )

    lines += [
        "",
        "### How to read the call",
        "- `prefer_tp_*` / `prefer_rsi_*` — meaningful edge vs SL-only on that regime slice",
        "- `prefer_sl_ride` — early exits hurt (supports prior “ride it out”)",
        "- `no_clear_edge_vs_sl` — not enough lift after fees / thin fire rate",
        "- `inconclusive_thin_n` — do not tune live knobs from this cell",
        "",
        "### Policy detail (all regimes pooled)",
        "",
    ]
    allp = ((rep.get("by_regime") or {}).get("all") or {}).get("policies") or {}
    lines.append("| Policy | N | sum r | mean r | WR | Δsum vs SL | exit mix |")
    lines.append("|--------|--:|------:|-------:|---:|-----------:|----------|")
    for name in sorted(allp.keys(), key=lambda k: (0 if k == "sl_only" else 1, k)):
        p = allp[name]
        lines.append(
            f"| {name} | {p.get('n')} | {p.get('sum_r')} | {p.get('mean_r')} | {p.get('wr')} | "
            f"{p.get('delta_sum_r_vs_sl')} | {p.get('exit_mix')} |"
        )

    # Per-regime brief
    lines += ["", "### Per-regime policy snapshots", ""]
    for reg, block in (rep.get("by_regime") or {}).items():
        if reg == "all":
            continue
        lines.append(f"#### {reg} — `{block.get('call')}`")
        base = (block.get("policies") or {}).get("sl_only") or {}
        lines.append(
            f"- N={base.get('n')} · SL sum_r={base.get('sum_r')} mean={base.get('mean_r')} · "
            f"best_tp={block.get('best_tp')} best_rsi={block.get('best_rsi')} overall={block.get('best_overall')}"
        )
        # top 3 by sum r
        pols = block.get("policies") or {}
        ranked = sorted(
            pols.items(),
            key=lambda kv: (kv[1].get("sum_r") is not None, kv[1].get("sum_r") or -1e9),
            reverse=True,
        )[:5]
        for name, p in ranked:
            lines.append(
                f"  - {name}: sum_r={p.get('sum_r')} Δ={p.get('delta_sum_r_vs_sl')} mix={p.get('exit_mix')}"
            )
        lines.append("")

    # SL-exit only
    lines += [
        "### Slice: ledger reason = stop-loss only",
        "Closer to “vs riding to SL” on legs that actually stopped.",
        "",
    ]
    for reg, row in (rep.get("sl_exit_legs_only") or {}).items():
        base = row.get("sl_only") or {}
        lines.append(
            f"- **{reg}**: N={base.get('n')} SL_sum={base.get('sum_r')} best=`{row.get('best')}`"
        )

    lines += [
        "",
        "## Go / no-go (ops)",
        "",
        "| Action | Gate |",
        "|--------|------|",
        "| Live take-profit | Only if a regime call is `prefer_tp_*` with N≥8 that regime **and** Brad OK; still shadow-first |",
        "| Auto RSI hard-exit | Only if `prefer_rsi_*` with N gate **and** operator_approve flip explicit |",
        "| Single global threshold | **No** unless enum is `uniform_*` |",
        "| Default while thin/unclear | Keep SL live; TP shadow; hard-exit operator loop |",
        "",
        "## Notes",
    ]
    for n in rep.get("notes") or []:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    days = 120
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            pass
    rep = run(lookback_days=days)
    OUT_STATE.parent.mkdir(parents=True, exist_ok=True)
    OUT_STATE.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    day = rep["as_of"][:10]
    REPORTS.mkdir(parents=True, exist_ok=True)
    jp = REPORTS / f"EXIT_THRESHOLD_REGIME_STUDY_{day}.json"
    mp = REPORTS / f"EXIT_THRESHOLD_REGIME_STUDY_{day}.md"
    jp.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    mp.write_text(to_md(rep), encoding="utf-8")
    print(to_md(rep))
    print(f"wrote {mp}")
    print(f"wrote {OUT_STATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
