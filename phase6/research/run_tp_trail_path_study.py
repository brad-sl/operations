#!/usr/bin/env python3
"""TG-04: OHLCV path counterfactual for TP / trail vs realized ledger exits.

Real data: trades/phase6_trades.jsonl + backtests/data/backtest_historical_ohlcv_*.json
Daily bars: high watermark path from entry day → exit day.

Writes:
  reports/TP_TRAIL_PATH_STUDY_YYYY-MM-DD.{md,json}
  data/state/tp_trail_path_study_latest.json

Recommendation enum: design_shadow | drop | continue_observe | insufficient_data
No live config writes.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRADES = ROOT / "trades" / "phase6_trades.jsonl"
OHLCV_DIR = ROOT / "backtests" / "data"
OUT_STATE = ROOT / "data" / "state" / "tp_trail_path_study_latest.json"
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
}


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


def _load_ohlcv(pair: str) -> List[Dict[str, Any]]:
    short = PAIR_TO_SHORT.get(pair) or pair.split("-")[0].lower()
    # prefer extended pack filename
    candidates = sorted(OHLCV_DIR.glob(f"backtest_historical_ohlcv_{short}*.json"))
    if not candidates:
        return []
    path = candidates[-1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    return []


def _day(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _bars_between(candles: List[Dict[str, Any]], start_d: str, end_d: str) -> List[Dict[str, Any]]:
    out = []
    for c in candles:
        d = str(c.get("timestamp") or "")[:10]
        if start_d <= d <= end_d:
            out.append(c)
    return out


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
        key = oid or (r.get("timestamp") or r.get("ts"), r.get("pair"), r.get("side"), r.get("qty"), r.get("pnl"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    return rows


@dataclass
class LegCF:
    pair: str
    entry_ts: str
    exit_ts: str
    entry_px: float
    exit_px: float
    realized_r: float
    reason: str
    max_favorable_r: Optional[float]
    min_adverse_r: Optional[float]
    hit_tp04: bool
    hit_tp06: bool
    hit_tp08: bool
    first_tp06_day: Optional[str]
    cf_tp06_r: Optional[float]
    cf_trail_r: Optional[float]
    bars: int
    note: str = ""


def _match_rounds(rows: List[Dict[str, Any]], lookback_days: int = 60) -> List[Tuple[Dict, Dict]]:
    """Greedy FIFO buy→sell match per pair within window."""
    cut = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    buys: Dict[str, List[Dict]] = {}
    rounds: List[Tuple[Dict, Dict]] = []
    timed = []
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
            buys.setdefault(pair, []).append(r)
        elif side == "SELL":
            q = buys.get(pair) or []
            if not q:
                continue
            b = q.pop(0)
            rounds.append((b, r))
    return rounds


def _path_stats(entry_px: float, bars: List[Dict[str, Any]]) -> Dict[str, Any]:
    if entry_px <= 0 or not bars:
        return {}
    max_fav = None
    min_adv = None
    first_tp = {0.04: None, 0.06: None, 0.08: None}
    # trail: arm at +4%, stop at max(peak*(1-trail), entry*(1+be))
    arm = 0.04
    trail_pct = 0.02
    be = 0.005
    armed = False
    peak = entry_px
    trail_exit_r = None
    for c in bars:
        h = float(c.get("high") or c.get("close") or 0)
        l = float(c.get("low") or c.get("close") or 0)
        cl = float(c.get("close") or 0)
        d = str(c.get("timestamp") or "")[:10]
        if h > 0:
            fav = (h - entry_px) / entry_px
            max_fav = fav if max_fav is None else max(max_fav, fav)
            for tp, day in list(first_tp.items()):
                if day is None and fav >= tp:
                    first_tp[tp] = d
        if l > 0:
            adv = (l - entry_px) / entry_px
            min_adv = adv if min_adv is None else min(min_adv, adv)
        # trail on close path (conservative daily)
        if cl > peak:
            peak = cl
        r_close = (cl - entry_px) / entry_px
        if not armed and r_close >= arm:
            armed = True
        if armed and trail_exit_r is None:
            stop = max(peak * (1.0 - trail_pct), entry_px * (1.0 + be))
            if l > 0 and l <= stop:
                trail_exit_r = (stop - entry_px) / entry_px
    return {
        "max_favorable_r": max_fav,
        "min_adverse_r": min_adv,
        "first_tp": first_tp,
        "cf_trail_r": trail_exit_r,
        "cf_tp06_r": 0.06 if first_tp[0.06] else None,
        "cf_tp04_r": 0.04 if first_tp[0.04] else None,
        "cf_tp08_r": 0.08 if first_tp[0.08] else None,
    }


def run(lookback_days: int = 60) -> Dict[str, Any]:
    rows = _load_unique_trades()
    rounds = _match_rounds(rows, lookback_days=lookback_days)
    legs: List[LegCF] = []
    skipped = {"no_ohlcv": 0, "no_price": 0, "no_bars": 0}

    for buy, sell in rounds:
        pair = buy.get("pair") or sell.get("pair")
        et = _parse_ts(buy.get("timestamp") or buy.get("ts"))
        xt = _parse_ts(sell.get("timestamp") or sell.get("ts"))
        if not pair or not et or not xt:
            continue
        entry_px = buy.get("entry_price") or buy.get("price") or buy.get("avg_price") or buy.get("fill_price")
        exit_px = sell.get("exit_price") or sell.get("price") or sell.get("avg_price") or sell.get("fill_price")
        try:
            entry_px = float(entry_px) if entry_px is not None else None
            exit_px = float(exit_px) if exit_px is not None else None
        except (TypeError, ValueError):
            skipped["no_price"] += 1
            continue
        # Implied entry from sell ledger: entry_n = qty*exit - pnl → entry = entry_n/qty
        if (entry_px is None or entry_px <= 0) and sell.get("pnl") is not None:
            try:
                pnl = float(sell.get("pnl"))
                qty = float(sell.get("qty") or 0)
                xp = float(exit_px) if exit_px else None
                if qty and xp:
                    entry_px = (qty * xp - pnl) / qty
            except (TypeError, ValueError):
                pass
        if entry_px is None or entry_px <= 0:
            skipped["no_price"] += 1
            continue
        if exit_px is None or exit_px <= 0:
            try:
                pnl = float(sell.get("pnl"))
                qty = float(sell.get("qty") or buy.get("qty") or 0)
                if qty:
                    exit_px = entry_px + pnl / qty
            except (TypeError, ValueError):
                pass
        if exit_px is None or exit_px <= 0:
            # pnl_pct path
            try:
                pct = sell.get("pnl_pct")
                if pct is not None:
                    exit_px = entry_px * (1.0 + float(pct))
            except (TypeError, ValueError):
                pass
        if exit_px is None or exit_px <= 0:
            skipped["no_price"] += 1
            continue
        realized_r = (exit_px - entry_px) / entry_px
        # Prefer sell pnl_pct when present and sane
        try:
            pct = sell.get("pnl_pct")
            if pct is not None and abs(float(pct)) <= 0.5:
                realized_r = float(pct)
        except (TypeError, ValueError):
            pass
        candles = _load_ohlcv(str(pair))
        if not candles:
            skipped["no_ohlcv"] += 1
            legs.append(
                LegCF(
                    pair=str(pair),
                    entry_ts=et.isoformat(),
                    exit_ts=xt.isoformat(),
                    entry_px=entry_px,
                    exit_px=exit_px,
                    realized_r=realized_r,
                    reason=str(sell.get("reason") or ""),
                    max_favorable_r=None,
                    min_adverse_r=None,
                    hit_tp04=False,
                    hit_tp06=False,
                    hit_tp08=False,
                    first_tp06_day=None,
                    cf_tp06_r=None,
                    cf_trail_r=None,
                    bars=0,
                    note="no_ohlcv",
                )
            )
            continue
        bars = _bars_between(candles, _day(et), _day(xt))
        if len(bars) < 1:
            skipped["no_bars"] += 1
        stats = _path_stats(entry_px, bars)
        mf = stats.get("max_favorable_r")
        legs.append(
            LegCF(
                pair=str(pair),
                entry_ts=et.isoformat(),
                exit_ts=xt.isoformat(),
                entry_px=entry_px,
                exit_px=exit_px,
                realized_r=realized_r,
                reason=str(sell.get("reason") or ""),
                max_favorable_r=mf,
                min_adverse_r=stats.get("min_adverse_r"),
                hit_tp04=bool(stats.get("first_tp", {}).get(0.04)),
                hit_tp06=bool(stats.get("first_tp", {}).get(0.06)),
                hit_tp08=bool(stats.get("first_tp", {}).get(0.08)),
                first_tp06_day=stats.get("first_tp", {}).get(0.06),
                cf_tp06_r=stats.get("cf_tp06_r"),
                cf_trail_r=stats.get("cf_trail_r"),
                bars=len(bars),
                note="" if bars else "no_bars_in_range",
            )
        )

    usable = [L for L in legs if L.bars > 0 and L.max_favorable_r is not None]
    n = len(usable)
    # Baseline sum r
    base_sum = sum(L.realized_r for L in usable)
    # CF fixed TP: if path hit tp, bank tp; else realized (still stop/exit)
    # CF "rescue only": if realized <0 and path hit tp, bank tp; else realized
    tp06_sum = 0.0
    trail_sum = 0.0
    rescue_sum = 0.0
    tp06_improved = 0
    trail_improved = 0
    rescue_improved = 0
    gave_tp_missed = 0  # realized loss but path hit +6%
    for L in usable:
        if L.hit_tp06:
            tp06_sum += 0.06
            if 0.06 > L.realized_r + 1e-9:
                tp06_improved += 1
            if L.realized_r < 0:
                gave_tp_missed += 1
                rescue_sum += 0.06
                rescue_improved += 1
            else:
                rescue_sum += L.realized_r
        else:
            tp06_sum += L.realized_r
            rescue_sum += L.realized_r
        if L.cf_trail_r is not None:
            trail_sum += L.cf_trail_r
            if L.cf_trail_r > L.realized_r + 1e-9:
                trail_improved += 1
        else:
            trail_sum += L.realized_r

    hit_rate_06 = sum(1 for L in usable if L.hit_tp06) / n if n else None
    n_loss = sum(1 for L in usable if L.realized_r < 0)
    rescue_rate = (gave_tp_missed / n_loss) if n_loss else 0.0
    # Enum: prioritize *rescue* of losses that had path TP — not total sum r
    # (fixed TP always caps rare big winners and can look worse on sum r)
    if n < 12:
        enum = "insufficient_data"
    elif gave_tp_missed >= 3 and rescue_rate >= 0.15:
        enum = "design_shadow"
    elif gave_tp_missed >= 2 and (rescue_sum - base_sum) > 0.03:
        enum = "design_shadow"
    elif n_loss >= 8 and gave_tp_missed == 0 and hit_rate_06 is not None and hit_rate_06 < 0.1:
        enum = "drop"
    else:
        enum = "continue_observe"

    report = {
        "schema": "tp_trail_path_study_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "lookback_days": lookback_days,
        "live_config_writes": False,
        "n_rounds_matched": len(rounds),
        "n_legs_total": len(legs),
        "n_usable_path": n,
        "n_loss_legs": n_loss,
        "skipped": skipped,
        "baseline_sum_r": round(base_sum, 6),
        "cf_tp06_sum_r": round(tp06_sum, 6),
        "cf_trail_sum_r": round(trail_sum, 6),
        "cf_rescue_tp06_sum_r": round(rescue_sum, 6),
        "delta_tp06_vs_base_r": round(tp06_sum - base_sum, 6),
        "delta_trail_vs_base_r": round(trail_sum - base_sum, 6),
        "delta_rescue_vs_base_r": round(rescue_sum - base_sum, 6),
        "hit_rate_tp06": hit_rate_06,
        "n_tp06_improved_vs_realized": tp06_improved,
        "n_trail_improved_vs_realized": trail_improved,
        "n_loss_but_path_hit_tp06": gave_tp_missed,
        "rescue_rate_among_losses": round(rescue_rate, 4),
        "recommendation_enum": enum,
        "mean_realized_r": round(base_sum / n, 6) if n else None,
        "mean_max_favorable_r": round(sum(L.max_favorable_r or 0 for L in usable) / n, 6) if n else None,
        "legs_sample": [asdict(L) for L in usable[:25]],
        "notes": [
            "Daily OHLCV high/low — path CF is upper bound optimistic for TP touch (intrabar).",
            "Trail uses daily low vs stop after arm +4%; coarse vs tick stops.",
            "Enum weights rescue of path-TP-then-loss legs; fixed-TP sum r can look worse by capping winners.",
            "No live take_profit_pct change from this report alone.",
        ],
    }
    return report


def to_md(rep: Dict[str, Any]) -> str:
    lines = [
        f"# TP / Trail Path Study — {rep['as_of'][:10]}",
        "",
        f"**Enum:** `{rep['recommendation_enum']}` · live writes: false",
        f"- Matched rounds: {rep['n_rounds_matched']} · usable path legs: **{rep['n_usable_path']}** · losses: {rep.get('n_loss_legs')}",
        f"- Baseline sum r: {rep['baseline_sum_r']} · mean r: {rep.get('mean_realized_r')}",
        f"- CF TP+6% (always bank TP if touched) sum r: {rep['cf_tp06_sum_r']} (Δ {rep['delta_tp06_vs_base_r']})",
        f"- CF **rescue** (TP only if realized loss + path hit): sum r {rep.get('cf_rescue_tp06_sum_r')} (Δ {rep.get('delta_rescue_vs_base_r')})",
        f"- CF trail sum r: {rep['cf_trail_sum_r']} (Δ {rep['delta_trail_vs_base_r']})",
        f"- Hit rate path≥+6%: {rep.get('hit_rate_tp06')}",
        f"- Losses that still touched +6% on path: **{rep.get('n_loss_but_path_hit_tp06')}** (rescue rate {rep.get('rescue_rate_among_losses')})",
        f"- Skipped: {rep.get('skipped')}",
        "",
        "## Read",
        "- **Rescue rate** is the decision metric: losses that had a path TP opportunity.",
        "- Full fixed-TP sum can look worse because it caps winners — do not drop on that alone.",
        "- Daily bars slightly overstate TP ease.",
        "",
        "## Next",
        "- If design_shadow: shadow TP / trail research + same operator notify loop as hard exit.",
        "- Do not set live take_profit_pct without Brad + shadow days.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    days = 60
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
    jp = REPORTS / f"TP_TRAIL_PATH_STUDY_{day}.json"
    mp = REPORTS / f"TP_TRAIL_PATH_STUDY_{day}.md"
    jp.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    mp.write_text(to_md(rep), encoding="utf-8")
    print(to_md(rep))
    print(f"wrote {jp}")
    print(f"wrote {OUT_STATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
