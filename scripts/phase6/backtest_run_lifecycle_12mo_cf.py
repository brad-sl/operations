#!/usr/bin/env python3
"""
12-month portfolio counterfactual: run-lifecycle stack vs baselines.

Arms:
  A) lifecycle   — P1 ignition (RSI×structure×phase) entries + P0 no late buys
                   + P2 dual-peak/extension partial exits + simple -3% SL
  B) chase_fomo  — buy strongest 5d momentum (sentiment proxy) ignoring phase
                   (what late scraps look like); exit only SL / +6% TP
  C) oversold    — classic RSI<35 mean-reversion; exit RSI>55 or SL
  D) btc_hodl    — 100% BTC buy & hold
  E) eq_hodl     — equal-weight buy & hold of universe

Data: backtests/data/long + historical packs + Coinbase public fill to latest.

Run:
  cd /home/brad/projects/crypto-trading-bot && PYTHONPATH=. python3 \\
    scripts/phase6/backtest_run_lifecycle_12mo_cf.py

Report: data/state/run_lifecycle_12mo_cf_report.json
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.run_lifecycle import (
    evaluate_dual_peak_exits,
    load_lifecycle_config,
    score_pair_ignition,
)
from phase6.core.run_phase_deploy import (
    apply_run_phase_buy_gate,
    classify_run_phase,
    normalize_candles,
    rsi_wilder,
)

OUT = ROOT / "data/state/run_lifecycle_12mo_cf_report.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; phase6-12mo-cf/1.0)"}

UNIVERSE = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "LINK-USD",
    "AVAX-USD",
    "XRP-USD",
    "DOGE-USD",
]
START_CAPITAL = 10_000.0
MAX_POSITIONS = 3
TICKET_USD = 150.0  # aligns with rebalance_cap spirit (scaled on $10k book)
MAX_PAIR_W = 0.30
SL_PCT = 0.03
FEE_BPS = 6.0  # ~6 bps roundish per side proxy
MIN_CASH = 50.0
# Deploy profile: "conservative" (ticket ~5%) | "deployed" (use free cash up to pair cap)
DEPLOY_PROFILE = "conservative"
DEPLOY_FRAC = 0.05  # fraction of equity per new ignition seat (conservative)
MIN_HOLD_DAYS_P2 = 0  # dual-peak min hold; set 3 in deployed profile


def _f(v, d=0.0):
    try:
        return float(v) if v is not None else d
    except Exception:
        return d


def parse_ts(s: str) -> datetime:
    s = str(s).replace("Z", "+00:00")
    return datetime.fromisoformat(s).astimezone(timezone.utc)


def day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def load_pair_ohlcv(pair: str) -> List[Dict[str, float]]:
    short = pair.split("-")[0].lower()
    rows: List[Dict[str, Any]] = []
    candidates = [
        ROOT / f"backtests/data/long/ohlcv_daily_{short}.json",
        ROOT / f"backtests/data/backtest_historical_ohlcv_{short}_2025-04-20_to_2026-04-20.json",
        ROOT / f"data/state/breadth_bakeoff_ohlcv_cache/{short}_usd.json",
    ]
    for p in candidates:
        if not p.exists():
            continue
        try:
            raw = json.loads(p.read_text())
        except Exception:
            continue
        if isinstance(raw, dict):
            raw = raw.get("candles") or raw.get("data") or raw.get("ohlcv") or []
        if not isinstance(raw, list) or not raw:
            continue
        for c in raw:
            if isinstance(c, dict):
                ts = c.get("timestamp") or c.get("time") or c.get("t")
                if isinstance(ts, (int, float)):
                    t = float(ts)
                    if t > 1e12:
                        t /= 1000.0
                else:
                    t = parse_ts(str(ts)).timestamp()
                rows.append(
                    {
                        "t": t,
                        "o": _f(c.get("open", c.get("o"))),
                        "h": _f(c.get("high", c.get("h"))),
                        "l": _f(c.get("low", c.get("l"))),
                        "c": _f(c.get("close", c.get("c"))),
                        "v": _f(c.get("volume", c.get("v"))),
                    }
                )
            elif isinstance(c, (list, tuple)) and len(c) >= 6:
                # coinbase style or [t,o,h,l,c,v]
                if _f(c[1]) > _f(c[2]):  # likely [t,l,h,o,c,v]
                    t, l, h, o, cl, v = c[0], c[1], c[2], c[3], c[4], c[5]
                else:
                    t, o, h, l, cl, v = c[0], c[1], c[2], c[3], c[4], c[5]
                rows.append(
                    {"t": float(t), "o": _f(o), "h": _f(h), "l": _f(l), "c": _f(cl), "v": _f(v)}
                )
        if rows:
            break

    # extend via Coinbase public
    try:
        url = f"https://api.exchange.coinbase.com/products/{pair}/candles?granularity=86400"
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode())
        for c in data:
            t, l, h, o, cl, v = c[0], c[1], c[2], c[3], c[4], c[5]
            rows.append(
                {"t": float(t), "o": _f(o), "h": _f(h), "l": _f(l), "c": _f(cl), "v": _f(v)}
            )
    except Exception as e:
        print(f"  warn fetch {pair}: {e}")

    rows = normalize_candles(rows)
    # dedupe by day
    by_day: Dict[str, Dict[str, float]] = {}
    for r in rows:
        dk = day_key(datetime.fromtimestamp(r["t"], tz=timezone.utc))
        by_day[dk] = r
    out = [by_day[k] for k in sorted(by_day.keys())]
    return out


def fee(notional: float) -> float:
    return abs(notional) * (FEE_BPS / 10_000.0)


@dataclass
class Lot:
    pair: str
    qty: float
    entry: float
    entry_day: str
    entry_sent: float = 0.2
    peak: float = 0.0
    sent_peak: float = 0.2
    arm_tag: str = ""

    def mtm(self, px: float) -> float:
        return self.qty * px

    def hold_days(self, day: str) -> int:
        try:
            a = datetime.strptime(self.entry_day, "%Y-%m-%d")
            b = datetime.strptime(day, "%Y-%m-%d")
            return max(0, (b - a).days)
        except Exception:
            return 999


@dataclass
class Portfolio:
    cash: float
    lots: List[Lot] = field(default_factory=list)
    equity_curve: List[Tuple[str, float]] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)

    def positions_usd(self, px: Dict[str, float]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for lot in self.lots:
            out[lot.pair] = out.get(lot.pair, 0.0) + lot.mtm(px.get(lot.pair, lot.entry))
        return out

    def equity(self, px: Dict[str, float]) -> float:
        return self.cash + sum(self.positions_usd(px).values())

    def held_pairs(self) -> List[str]:
        return sorted({l.pair for l in self.lots})


def buy(
    pf: Portfolio,
    pair: str,
    usd: float,
    px: float,
    day: str,
    tag: str,
    sent: float = 0.2,
) -> bool:
    if usd < 50 or px <= 0 or pf.cash < usd + MIN_CASH * 0.5:
        return False
    # leave min cash
    usd = min(usd, max(0.0, pf.cash - MIN_CASH))
    if usd < 50:
        return False
    cost = usd + fee(usd)
    if cost > pf.cash:
        usd = (pf.cash - MIN_CASH) / (1 + FEE_BPS / 10_000.0)
        if usd < 50:
            return False
        cost = usd + fee(usd)
    qty = usd / px
    pf.cash -= cost
    pf.lots.append(
        Lot(
            pair=pair,
            qty=qty,
            entry=px,
            entry_day=day,
            entry_sent=sent,
            peak=px,
            sent_peak=sent,
            arm_tag=tag,
        )
    )
    pf.trades.append(
        {
            "day": day,
            "side": "BUY",
            "pair": pair,
            "usd": round(usd, 2),
            "px": px,
            "tag": tag,
        }
    )
    return True


def sell_frac(
    pf: Portfolio,
    pair: str,
    frac: float,
    px: float,
    day: str,
    reason: str,
) -> float:
    frac = max(0.0, min(1.0, frac))
    if frac <= 0 or px <= 0:
        return 0.0
    proceeds = 0.0
    new_lots: List[Lot] = []
    for lot in pf.lots:
        if lot.pair != pair:
            new_lots.append(lot)
            continue
        sell_q = lot.qty * frac
        keep_q = lot.qty - sell_q
        usd = sell_q * px
        proceeds += usd - fee(usd)
        pf.trades.append(
            {
                "day": day,
                "side": "SELL",
                "pair": pair,
                "usd": round(usd, 2),
                "px": px,
                "tag": reason,
                "pnl_pct": round((px / lot.entry - 1.0) * 100, 2),
            }
        )
        if keep_q * px >= 5:
            lot.qty = keep_q
            new_lots.append(lot)
    pf.lots = new_lots
    pf.cash += proceeds
    return proceeds


def metrics(
    curve: List[Tuple[str, float]],
    trades: List[Dict],
    start: float,
    cash_fracs: Optional[List[float]] = None,
) -> Dict[str, Any]:
    if not curve:
        return {}
    eq = [e for _, e in curve]
    end = eq[-1]
    rets = []
    for i in range(1, len(eq)):
        if eq[i - 1] > 0:
            rets.append(eq[i] / eq[i - 1] - 1.0)
    peak = eq[0]
    max_dd = 0.0
    for e in eq:
        peak = max(peak, e)
        dd = (e / peak - 1.0) if peak > 0 else 0.0
        max_dd = min(max_dd, dd)
    sharpe = 0.0
    if rets:
        mu = sum(rets) / len(rets)
        var = sum((r - mu) ** 2 for r in rets) / max(1, len(rets) - 1)
        sd = math.sqrt(var) if var > 0 else 0.0
        if sd > 0:
            sharpe = (mu / sd) * math.sqrt(365)
    sells = [t for t in trades if t.get("side") == "SELL"]
    buys = [t for t in trades if t.get("side") == "BUY"]
    wins = [t for t in sells if _f(t.get("pnl_pct")) > 0]
    avg_cash = None
    if cash_fracs:
        avg_cash = round(100 * sum(cash_fracs) / len(cash_fracs), 1)
    # Trade PnL from closed sells (partials counted each)
    realized_pnl_usd = 0.0
    for t in sells:
        # reconstruct approx: usd * pnl_pct/100 / (1+pnl_pct/100) is wrong;
        # store notional sell * pnl/(1+pnl) ≈ gain on cost
        pnl_pct = _f(t.get("pnl_pct"))
        usd = _f(t.get("usd"))
        if pnl_pct != 0:
            # sell_usd = cost * (1+r) => cost = sell/(1+r), pnl = sell - cost
            r = pnl_pct / 100.0
            cost = usd / (1.0 + r) if abs(1.0 + r) > 1e-12 else usd
            realized_pnl_usd += usd - cost
        else:
            realized_pnl_usd += 0.0
    total_pnl_usd = end - start
    # monthly returns from curve
    monthly = {}
    for d, e in curve:
        ym = d[:7]
        if ym not in monthly:
            monthly[ym] = {"first": e, "last": e}
        monthly[ym]["last"] = e
    monthly_ret = []
    for ym in sorted(monthly):
        a, b = monthly[ym]["first"], monthly[ym]["last"]
        monthly_ret.append({
            "month": ym,
            "return_pct": round((b / a - 1.0) * 100, 2) if a > 0 else 0.0,
            "start_usd": round(a, 2),
            "end_usd": round(b, 2),
            "pnl_usd": round(b - a, 2),
        })
    return {
        "start_usd": start,
        "end_usd": round(end, 2),
        "total_pnl_usd": round(total_pnl_usd, 2),
        "realized_sell_pnl_usd": round(realized_pnl_usd, 2),
        "unrealized_pnl_usd": round(total_pnl_usd - realized_pnl_usd, 2),
        "total_return_pct": round((end / start - 1.0) * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_daily_ann": round(sharpe, 2),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "win_rate_sells_pct": round(100 * len(wins) / len(sells), 1) if sells else None,
        "avg_sell_pnl_pct": round(sum(_f(t.get("pnl_pct")) for t in sells) / len(sells), 2)
        if sells
        else None,
        "gross_profit_sells_usd": round(sum(
            (_f(t.get("usd")) - _f(t.get("usd")) / (1 + _f(t.get("pnl_pct")) / 100.0))
            for t in sells if _f(t.get("pnl_pct")) > 0
        ), 2) if sells else 0.0,
        "gross_loss_sells_usd": round(sum(
            (_f(t.get("usd")) - _f(t.get("usd")) / (1 + _f(t.get("pnl_pct")) / 100.0))
            for t in sells if _f(t.get("pnl_pct")) < 0
        ), 2) if sells else 0.0,
        "avg_cash_pct": avg_cash,
        "days": len(curve),
        "monthly": monthly_ret,
    }


def mom5(candles: List[Dict], i: int) -> float:
    if i < 5:
        return 0.0
    a, b = candles[i - 5]["c"], candles[i]["c"]
    return (b / a - 1.0) if a > 0 else 0.0


def run_arm(
    name: str,
    series: Dict[str, List[Dict[str, float]]],
    days: List[str],
    life_cfg: Dict[str, Any],
    mode: str,
    *,
    deploy_frac: float = 0.05,
    max_positions: int = 3,
    min_hold_days_p2: int = 0,
    p2_min_peak: float = 0.02,
) -> Dict[str, Any]:
    """mode: lifecycle | chase_fomo | oversold | btc_hodl | eq_hodl"""
    pf = Portfolio(cash=START_CAPITAL)
    cash_fracs: List[float] = []
    idx_maps = {}
    for pair, candles in series.items():
        idx_maps[pair] = {
            day_key(datetime.fromtimestamp(c["t"], tz=timezone.utc)): i
            for i, c in enumerate(candles)
        }

    def px_on(day: str) -> Dict[str, float]:
        out = {}
        for pair, candles in series.items():
            i = idx_maps[pair].get(day)
            if i is not None:
                out[pair] = candles[i]["c"]
        return out

    if mode == "btc_hodl":
        d0 = days[0]
        p0 = px_on(d0).get("BTC-USD")
        if p0:
            buy(pf, "BTC-USD", START_CAPITAL - MIN_CASH, p0, d0, "btc_hodl")
        for d in days:
            eq = pf.equity(px_on(d))
            pf.equity_curve.append((d, eq))
            cash_fracs.append(pf.cash / eq if eq > 0 else 1.0)
        return _pack(name, pf, cash_fracs)

    if mode == "eq_hodl":
        d0 = days[0]
        px0 = px_on(d0)
        pairs = [p for p in UNIVERSE if p in px0]
        if pairs:
            each = (START_CAPITAL - MIN_CASH) / len(pairs)
            for p in pairs:
                buy(pf, p, each, px0[p], d0, "eq_hodl")
        for d in days:
            eq = pf.equity(px_on(d))
            pf.equity_curve.append((d, eq))
            cash_fracs.append(pf.cash / eq if eq > 0 else 1.0)
        return _pack(name, pf, cash_fracs)

    p2_cfg = dict(life_cfg["dual_peak_exit"])
    p2_cfg["mode"] = "shadow"
    p2_cfg["enabled"] = True
    p2_cfg["min_peak_return"] = p2_min_peak
    if min_hold_days_p2 > 0:
        p2_cfg["extension_partial_shadow"] = False

    for d in days:
        px = px_on(d)
        if not px:
            continue
        for lot in pf.lots:
            if lot.pair in px:
                lot.peak = max(lot.peak, px[lot.pair])

        if mode == "lifecycle":
            for pair in list(pf.held_pairs()):
                lots_p = [l for l in pf.lots if l.pair == pair]
                if not lots_p:
                    continue
                entry = sum(l.entry * l.qty for l in lots_p) / sum(l.qty for l in lots_p)
                if px[pair] <= entry * (1 - SL_PCT):
                    sell_frac(pf, pair, 1.0, px[pair], d, "sl")

            lot_dicts = []
            for lot in pf.lots:
                if lot.hold_days(d) < min_hold_days_p2:
                    continue
                lot_dicts.append(
                    {
                        "pair": lot.pair,
                        "open": True,
                        "entry_price": lot.entry,
                        "entry_sentiment": lot.entry_sent,
                        "entry_sent_peak": lot.sent_peak,
                        "peak_price": lot.peak,
                        "usd": lot.mtm(px.get(lot.pair, lot.entry)),
                    }
                )
            sent_now = {}
            for pair in pf.held_pairs():
                i = idx_maps[pair].get(d)
                if i is None:
                    continue
                m = mom5(series[pair], i)
                sent_now[pair] = max(-0.2, min(0.9, 0.2 + m * 4))
                for lot in pf.lots:
                    if lot.pair == pair:
                        lot.sent_peak = max(lot.sent_peak, sent_now[pair])

            candles_by = {}
            for pair in pf.held_pairs():
                i = idx_maps[pair].get(d)
                if i is not None:
                    candles_by[pair] = series[pair][: i + 1]

            events = evaluate_dual_peak_exits(
                lots=lot_dicts,
                current_sentiment=sent_now,
                current_prices=px,
                positions_usd=pf.positions_usd(px),
                candles_by_pair=candles_by,
                cfg_p2=p2_cfg,
            )
            seen = set()
            for ev in sorted(events, key=lambda e: 0 if e.kind == "dual_peak" else 1):
                if ev.pair in seen or ev.pair not in px:
                    continue
                if ev.kind == "extension_partial" and min_hold_days_p2 > 0:
                    continue
                seen.add(ev.pair)
                sell_frac(pf, ev.pair, ev.would_trim_frac, px[ev.pair], d, f"p2_{ev.kind}")

        elif mode == "chase_fomo":
            for pair in list(pf.held_pairs()):
                lots_p = [l for l in pf.lots if l.pair == pair]
                entry = sum(l.entry * l.qty for l in lots_p) / sum(l.qty for l in lots_p)
                if px[pair] <= entry * (1 - SL_PCT):
                    sell_frac(pf, pair, 1.0, px[pair], d, "sl")
                elif px[pair] >= entry * 1.06:
                    sell_frac(pf, pair, 1.0, px[pair], d, "tp6")

        elif mode == "oversold":
            for pair in list(pf.held_pairs()):
                i = idx_maps[pair].get(d)
                if i is None:
                    continue
                closes = [c["c"] for c in series[pair][: i + 1]]
                rsi = rsi_wilder(closes, 14)
                lots_p = [l for l in pf.lots if l.pair == pair]
                entry = sum(l.entry * l.qty for l in lots_p) / sum(l.qty for l in lots_p)
                if px[pair] <= entry * (1 - SL_PCT):
                    sell_frac(pf, pair, 1.0, px[pair], d, "sl")
                elif rsi is not None and rsi >= 55:
                    sell_frac(pf, pair, 1.0, px[pair], d, "rsi_exit")

        eq = pf.equity(px)
        n_pos = len(pf.held_pairs())
        if n_pos >= max_positions or pf.cash < MIN_CASH + 50:
            pf.equity_curve.append((d, eq))
            cash_fracs.append(pf.cash / eq if eq > 0 else 1.0)
            continue

        if mode == "lifecycle":
            cands = []
            for pair, candles in series.items():
                i = idx_maps[pair].get(d)
                if i is None or i < 30:
                    continue
                if pair in pf.held_pairs():
                    continue
                m = mom5(candles, i)
                sent = max(-0.2, min(0.9, 0.15 + m * 3))
                cand = score_pair_ignition(
                    pair, candles[: i + 1], sentiment=sent, cfg_all=life_cfg
                )
                snap = classify_run_phase(candles[: i + 1], pair=pair)
                gate = apply_run_phase_buy_gate(pair, 500.0, snap, current_pair_usd=0.0)
                if gate.blocked or gate.final_usd <= 0:
                    continue
                if cand.score >= _f(life_cfg["ignition_scout"].get("min_score"), 0.55):
                    cands.append((cand.score, pair, sent, cand))
            cands.sort(reverse=True)
            for score, pair, sent, cand in cands[: max(0, max_positions - n_pos)]:
                eq = pf.equity(px)
                ticket = min(
                    max(TICKET_USD, eq * deploy_frac),
                    eq * MAX_PAIR_W,
                    pf.cash - MIN_CASH,
                )
                cur_w = pf.positions_usd(px).get(pair, 0.0) / eq if eq > 0 else 0
                room = max(0.0, (MAX_PAIR_W - cur_w) * eq)
                ticket = min(ticket, room)
                if ticket >= 50 and pair in px:
                    if buy(pf, pair, ticket, px[pair], d, f"ignition:{cand.phase_name}", sent=sent):
                        n_pos += 1
                        if n_pos >= max_positions:
                            break

        elif mode == "chase_fomo":
            ranked = []
            for pair, candles in series.items():
                i = idx_maps[pair].get(d)
                if i is None or i < 10:
                    continue
                if pair in pf.held_pairs():
                    continue
                ranked.append((mom5(candles, i), pair))
            ranked.sort(reverse=True)
            for m, pair in ranked[:1]:
                if m < 0.05:
                    break
                eq = pf.equity(px)
                ticket = min(pf.cash - MIN_CASH, eq * 0.35)
                if ticket >= 50 and pair in px:
                    buy(pf, pair, ticket, px[pair], d, f"fomo_mom5={m:.2f}", sent=0.8)
                    break

        elif mode == "oversold":
            ranked = []
            for pair, candles in series.items():
                i = idx_maps[pair].get(d)
                if i is None or i < 16:
                    continue
                if pair in pf.held_pairs():
                    continue
                rsi = rsi_wilder([c["c"] for c in candles[: i + 1]], 14)
                if rsi is not None and rsi < 35:
                    ranked.append((rsi, pair))
            ranked.sort()
            for rsi, pair in ranked[: max(0, max_positions - n_pos)]:
                eq = pf.equity(px)
                ticket = min(TICKET_USD * 2, eq * 0.08, pf.cash - MIN_CASH)
                if ticket >= 50 and pair in px:
                    if buy(pf, pair, ticket, px[pair], d, f"oversold_rsi={rsi:.0f}"):
                        n_pos += 1
                        if n_pos >= max_positions:
                            break

        eq = pf.equity(px)
        pf.equity_curve.append((d, eq))
        cash_fracs.append(pf.cash / eq if eq > 0 else 1.0)

    return _pack(name, pf, cash_fracs)


def _pack(name: str, pf: Portfolio, cash_fracs: Optional[List[float]] = None) -> Dict[str, Any]:
    start = START_CAPITAL
    m = metrics(pf.equity_curve, pf.trades, start, cash_fracs)
    return {
        "arm": name,
        "metrics": m,
        "n_trades": len(pf.trades),
        "final_positions": pf.held_pairs(),
        "final_cash": round(pf.cash, 2),
        "sample_trades": pf.trades[:8]
        + ([{"...": len(pf.trades) - 16}] if len(pf.trades) > 16 else [])
        + pf.trades[-8:],
        "equity_curve_tail": pf.equity_curve[-10:],
        "equity_curve_head": pf.equity_curve[:3],
    }


def main() -> int:
    print("Loading OHLCV…")
    series: Dict[str, List[Dict[str, float]]] = {}
    for pair in UNIVERSE:
        rows = load_pair_ohlcv(pair)
        series[pair] = rows
        if rows:
            d0 = day_key(datetime.fromtimestamp(rows[0]["t"], tz=timezone.utc))
            d1 = day_key(datetime.fromtimestamp(rows[-1]["t"], tz=timezone.utc))
            print(f"  {pair}: {len(rows)} bars {d0} → {d1}")
        else:
            print(f"  {pair}: EMPTY")

    series = {k: v for k, v in series.items() if len(v) >= 80}
    if "BTC-USD" not in series:
        print("Need BTC")
        return 1

    last_days = []
    for pair, rows in series.items():
        last_days.append(day_key(datetime.fromtimestamp(rows[-1]["t"], tz=timezone.utc)))
    end_day = min(last_days)
    end_dt = parse_ts(end_day + "T00:00:00+00:00")
    start_dt = end_dt - timedelta(days=365)
    start_day = day_key(start_dt)

    btc_days = [
        day_key(datetime.fromtimestamp(c["t"], tz=timezone.utc))
        for c in series["BTC-USD"]
    ]
    days = [d for d in btc_days if start_day <= d <= end_day]
    print(f"\nWindow: {days[0]} → {days[-1]}  ({len(days)} days)")
    print(f"Start capital: ${START_CAPITAL:,.0f}")

    cfg = json.loads((ROOT / "config/trading_config_phase6.json").read_text())
    life = load_lifecycle_config(cfg)
    print("Lifecycle min_score", life["ignition_scout"]["min_score"])

    specs = [
        ("lifecycle_conservative", "lifecycle", dict(deploy_frac=0.05, max_positions=3, min_hold_days_p2=0, p2_min_peak=0.02)),
        ("lifecycle_deployed", "lifecycle", dict(deploy_frac=0.20, max_positions=4, min_hold_days_p2=3, p2_min_peak=0.04)),
        ("chase_fomo", "chase_fomo", {}),
        ("oversold_rsi", "oversold", {}),
        ("btc_hodl", "btc_hodl", {}),
        ("eq_basket_hodl", "eq_hodl", {}),
    ]
    arms = {}
    for name, mode, kw in specs:
        print(f"Running {name}…")
        arms[name] = run_arm(name, series, days, life, mode, **kw)
        m = arms[name]["metrics"]
        print(
            f"  → ret {m.get('total_return_pct')}%  maxDD {m.get('max_drawdown_pct')}%  "
            f"sharpe {m.get('sharpe_daily_ann')}  buys {m.get('n_buys')}  "
            f"avgCash {m.get('avg_cash_pct')}%  end ${m.get('end_usd')}"
        )

    link_study = []
    if "LINK-USD" in series:
        for c in series["LINK-USD"]:
            d = day_key(datetime.fromtimestamp(c["t"], tz=timezone.utc))
            if d < "2026-08-01" or d > end_day:
                continue
            i = next(
                i
                for i, x in enumerate(series["LINK-USD"])
                if day_key(datetime.fromtimestamp(x["t"], tz=timezone.utc)) == d
            )
            cand = score_pair_ignition(
                "LINK-USD", series["LINK-USD"][: i + 1], sentiment=0.3, cfg_all=life
            )
            link_study.append(
                {
                    "date": d,
                    "close": c["c"],
                    "score": cand.score,
                    "phase": cand.phase_name,
                    "propose": cand.proposal_usd > 0,
                }
            )

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "window": {"start": days[0], "end": days[-1], "n_days": len(days)},
        "universe": list(series.keys()),
        "params": {
            "start_capital": START_CAPITAL,
            "sl_pct": SL_PCT,
            "fee_bps": FEE_BPS,
            "max_pair_w": MAX_PAIR_W,
            "lifecycle_conservative": "deploy_frac=5%, max_pos=3, p2 immediate",
            "lifecycle_deployed": "deploy_frac=20%, max_pos=4, p2 min_hold=3d peak>=4%",
            "note": (
                "Sentiment is MOMENTUM PROXY only (no historical X dump). "
                "Lifecycle entries use real phase+structure+RSI. "
                "P2 exits use dual-peak pure logic with proxy sent. "
                "Not a promise of live returns — structure CF over ~12 months."
            ),
        },
        "leaderboard": sorted(
            [{"arm": k, **v["metrics"]} for k, v in arms.items()],
            key=lambda x: x.get("total_pnl_usd") if x.get("total_pnl_usd") is not None else (x.get("total_return_pct") or -999),
            reverse=True,
        ),
        "arms": arms,
        "link_aug_2026_study": link_study,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))

    print("\n======== LEADERBOARD (12mo CF) + PnL ========")
    print(f"{'arm':24} {'PnL$':>10} {'ret%':>8} {'maxDD%':>8} {'sharpe':>7} {'cash%':>7} {'buys':>5} {'WR%':>6} {'end$':>10}")
    for row in report["leaderboard"]:
        print(
            f"{row['arm']:24} {row.get('total_pnl_usd', 0):10.2f} "
            f"{row.get('total_return_pct', 0):8.2f} "
            f"{row.get('max_drawdown_pct', 0):8.2f} {row.get('sharpe_daily_ann', 0):7.2f} "
            f"{row.get('avg_cash_pct') or 0:7.1f} "
            f"{row.get('n_buys', 0):5} {row.get('win_rate_sells_pct') or 0:6.1f} "
            f"{row.get('end_usd', 0):10.2f}"
        )
    # Monthly PnL for primary arms
    for arm_name in ("lifecycle_deployed", "btc_hodl", "chase_fomo"):
        arm = report["arms"].get(arm_name) or {}
        monthly = (arm.get("metrics") or {}).get("monthly") or []
        if not monthly:
            continue
        print(f"\n--- Monthly PnL: {arm_name} ---")
        print(f"{'month':8} {'pnl$':>10} {'ret%':>8} {'end$':>10}")
        for mrow in monthly:
            print(f"{mrow['month']:8} {mrow['pnl_usd']:10.2f} {mrow['return_pct']:8.2f} {mrow['end_usd']:10.2f}")

    print(f"\nReport → {OUT}")
    print(
        "\nHonesty: no historical X sentiment — chase uses 5d momentum FOMO proxy. "
        "Compare structure + risk shape, not as a live P&L guarantee."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
