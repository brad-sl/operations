#!/usr/bin/env python3
"""Trade comparison standard — pair/process dig SSOT for platform optimization.

Class purpose
-------------
Turn "what happened on LINK?" into a **repeatable scoreboard** any pair (or the
whole book) can sit on — so process leaks are comparable and rule candidates are
paper-first, not vibes.

Honesty bars (see offline-strategy-honesty):
- SELL ledger PnL is closed-book SSOT; FIFO lots are diagnostic only.
- Drop phase6_fresh_start / zero-price noise from buy events.
- Sparse RSI/sent stamps = data gap, not "no edge".
- OHLCV forward/delay CF is context; skip-bad-class > micro-timing.
- Edge class vocabulary required; process hygiene ≠ HIT_10 alpha.
- No live evaluate_buy_entry / config writes from this module.

Leak classes (paper rule candidates)
------------------------------------
- post_sl_reentry_Nh
- post_tp_rebuy_Nh
- pile_on_add_streak
- elevated_rsi_large_ticket
- same_day_churn
"""
from __future__ import annotations

import json
import math
import time
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "trades" / "phase6_trades.jsonl"
STATE = ROOT / "data" / "state"
REPORTS = ROOT / "reports"

DEFAULT_FEE_RT = 0.016  # taker-taker est (Intro 2 class)
DEFAULT_SL_COOLDOWN_H = 48.0
DEFAULT_TP_COOLDOWN_H = 48.0
DEFAULT_LARGE_USD = 150.0
DEFAULT_ELEVATED_RSI = 55.0
DEFAULT_TRYOUT_USD = 150.0

NOISE_BUY_REASONS = frozenset({"phase6_fresh_start"})


def parse_ts(s: Any) -> Optional[datetime]:
    if s is None:
        return None
    text = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def load_ledger_rows(
    ledger_path: Path = LEDGER,
    pair: Optional[str] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not ledger_path.exists():
        return rows
    with ledger_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not isinstance(r, dict):
                continue
            if r.get("side") == "OPS_CORRECTION":
                continue
            p = str(r.get("pair") or "")
            if pair and p != pair:
                continue
            rows.append(r)
    rows.sort(key=lambda r: parse_ts(r.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc))
    return rows


def is_clean_buy(r: Dict[str, Any]) -> bool:
    if r.get("side") != "BUY":
        return False
    reason = str(r.get("reason") or r.get("signal_source") or "")
    if reason in NOISE_BUY_REASONS:
        return False
    ep = _f(r.get("entry_price") or r.get("price"))
    oid = r.get("order_id")
    # zero-price without order id = inventory ghost
    if ep <= 0 and not oid:
        return False
    return True


def buy_event(r: Dict[str, Any]) -> Dict[str, Any]:
    ts = parse_ts(r.get("timestamp"))
    ep = _f(r.get("entry_price") or r.get("price"))
    qty = _f(r.get("qty"))
    # known tryout shape: price on BUY, qty on matching SELL later
    if ep <= 0 and r.get("price") is not None:
        ep = _f(r.get("price"))
    ind = r.get("indicators_at_trade") or {}
    if not isinstance(ind, dict):
        ind = {}
    usd = ep * qty if ep > 0 and qty > 0 else None
    return {
        "ts": ts,
        "pair": r.get("pair"),
        "qty": qty if qty > 0 else None,
        "entry": ep if ep > 0 else None,
        "usd": usd,
        "reason": r.get("reason") or r.get("signal_source"),
        "rsi": r.get("entry_rsi") if r.get("entry_rsi") is not None else ind.get("rsi"),
        "sent": r.get("entry_sentiment")
        if r.get("entry_sentiment") is not None
        else ind.get("sentiment"),
        "sl_attached": r.get("sl_attached"),
        "order_id": r.get("order_id"),
        "raw": r,
    }


def sell_event(r: Dict[str, Any]) -> Dict[str, Any]:
    ts = parse_ts(r.get("timestamp"))
    qty = _f(r.get("qty"))
    entry = _f(r.get("entry_price")) or None
    exitp = _f(r.get("exit_price")) or None
    pnl = r.get("pnl")
    pct = r.get("pnl_pct")
    if pnl is None and entry and exitp and qty:
        pnl = (exitp - entry) * qty
        pct = (exitp / entry - 1.0) if entry else None
    ind = r.get("indicators_at_trade") or {}
    if not isinstance(ind, dict):
        ind = {}
    reason = r.get("exit_reason") or r.get("reason") or ""
    return {
        "ts": ts,
        "pair": r.get("pair"),
        "qty": qty if qty > 0 else None,
        "entry": entry,
        "exit": exitp,
        "pnl": pnl if isinstance(pnl, (int, float)) else None,
        "pct": pct if isinstance(pct, (int, float)) else None,
        "reason": reason,
        "exit_rsi": r.get("exit_rsi") or ind.get("exit_rsi") or ind.get("rsi"),
        "exit_sent": r.get("exit_sentiment") or ind.get("exit_sentiment"),
        "entry_rsi_stamp": r.get("entry_rsi") or ind.get("entry_rsi"),
        "entry_sent_stamp": r.get("entry_sentiment") or ind.get("entry_sentiment"),
        "order_id": r.get("order_id"),
        "raw": r,
    }


def exit_class(reason: str) -> str:
    r = (reason or "").lower()
    if "stop_loss" in r:
        return "stop_loss"
    if "take_profit" in r or r.endswith("_tp") or "fixed_tp" in r or "trail" in r:
        return "take_profit"
    if "dust" in r:
        return "dust"
    if "operator" in r or "manual" in r or "trim" in r:
        return "operator"
    if not r:
        return "unknown"
    return "other"


@dataclass
class PairScoreboard:
    pair: str
    n_clean_buys: int = 0
    n_sells: int = 0
    realized_pnl_usd: float = 0.0
    pnl_by_exit_class: Dict[str, Dict[str, float]] = field(default_factory=dict)
    n_by_exit_class: Dict[str, int] = field(default_factory=dict)
    leak_hits: Dict[str, int] = field(default_factory=dict)
    leak_examples: List[Dict[str, Any]] = field(default_factory=list)
    best_process_samples: List[Dict[str, Any]] = field(default_factory=list)
    worst_process_samples: List[Dict[str, Any]] = field(default_factory=list)
    stamp_coverage: Dict[str, Any] = field(default_factory=dict)
    edge_class: str = "ATTENTION_ONLY_less_loss_path"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def summarize_pair(
    pair: str,
    rows: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    sl_cooldown_h: float = DEFAULT_SL_COOLDOWN_H,
    tp_cooldown_h: float = DEFAULT_TP_COOLDOWN_H,
    large_usd: float = DEFAULT_LARGE_USD,
    elevated_rsi: float = DEFAULT_ELEVATED_RSI,
) -> PairScoreboard:
    all_rows = list(rows) if rows is not None else load_ledger_rows(pair=pair)
    pair_rows = [r for r in all_rows if str(r.get("pair") or "") == pair]
    buys = [buy_event(r) for r in pair_rows if is_clean_buy(r)]
    sells = [sell_event(r) for r in pair_rows if r.get("side") == "SELL"]

    sb = PairScoreboard(pair=pair, n_clean_buys=len(buys), n_sells=len(sells))
    by_class: Dict[str, Dict[str, float]] = defaultdict(lambda: {"n": 0.0, "pnl": 0.0})
    realized = 0.0
    for s in sells:
        cls = exit_class(str(s.get("reason") or ""))
        by_class[cls]["n"] += 1
        pnl = s.get("pnl")
        if isinstance(pnl, (int, float)):
            by_class[cls]["pnl"] += float(pnl)
            realized += float(pnl)
        # best/worst samples
        sample = {
            "ts": s["ts"].isoformat() if s.get("ts") else None,
            "reason": s.get("reason"),
            "exit_class": cls,
            "pnl": s.get("pnl"),
            "pct": s.get("pct"),
            "qty": s.get("qty"),
            "entry": s.get("entry"),
            "exit": s.get("exit"),
        }
        if isinstance(pnl, (int, float)):
            if pnl >= 3.0 or (isinstance(s.get("pct"), (int, float)) and s["pct"] >= 0.05):
                sb.best_process_samples.append(sample)
            if pnl <= -5.0 or (isinstance(s.get("pct"), (int, float)) and s["pct"] <= -0.02):
                sb.worst_process_samples.append(sample)

    sb.realized_pnl_usd = round(realized, 4)
    sb.pnl_by_exit_class = {k: {"n": int(v["n"]), "pnl": round(v["pnl"], 4)} for k, v in by_class.items()}
    sb.n_by_exit_class = {k: int(v["n"]) for k, v in by_class.items()}

    # stamp coverage
    buy_rsi = sum(1 for b in buys if b.get("rsi") is not None)
    buy_sent = sum(1 for b in buys if b.get("sent") is not None)
    sb.stamp_coverage = {
        "buy_rsi_n": buy_rsi,
        "buy_sent_n": buy_sent,
        "buy_rsi_rate": round(buy_rsi / len(buys), 3) if buys else None,
        "buy_sent_rate": round(buy_sent / len(buys), 3) if buys else None,
        "note": "Sparse stamps = data gap; do not invent joins",
    }

    leaks: Dict[str, int] = defaultdict(int)
    examples: List[Dict[str, Any]] = []

    sl_sells = [s for s in sells if exit_class(str(s.get("reason") or "")) == "stop_loss" and s.get("ts")]
    tp_sells = [s for s in sells if exit_class(str(s.get("reason") or "")) == "take_profit" and s.get("ts")]

    for b in buys:
        if not b.get("ts"):
            continue
        usd = b.get("usd") or 0.0
        rsi = b.get("rsi")
        # post SL reentry
        for sl in sl_sells:
            dt_h = (b["ts"] - sl["ts"]).total_seconds() / 3600.0
            if 0 < dt_h <= sl_cooldown_h:
                leaks["post_sl_reentry_Nh"] += 1
                examples.append(
                    {
                        "leak": "post_sl_reentry_Nh",
                        "buy_ts": b["ts"].isoformat(),
                        "ref_ts": sl["ts"].isoformat(),
                        "hours_after": round(dt_h, 2),
                        "usd": usd,
                        "rsi": rsi,
                        "reason": b.get("reason"),
                    }
                )
                break
        # post TP rebuy
        for tp in tp_sells:
            dt_h = (b["ts"] - tp["ts"]).total_seconds() / 3600.0
            if 0 < dt_h <= tp_cooldown_h:
                leaks["post_tp_rebuy_Nh"] += 1
                examples.append(
                    {
                        "leak": "post_tp_rebuy_Nh",
                        "buy_ts": b["ts"].isoformat(),
                        "ref_ts": tp["ts"].isoformat(),
                        "hours_after": round(dt_h, 2),
                        "usd": usd,
                        "rsi": rsi,
                        "reason": b.get("reason"),
                    }
                )
                break
        # elevated RSI large
        if rsi is not None and float(rsi) >= elevated_rsi and usd >= large_usd:
            leaks["elevated_rsi_large_ticket"] += 1
            examples.append(
                {
                    "leak": "elevated_rsi_large_ticket",
                    "buy_ts": b["ts"].isoformat(),
                    "usd": usd,
                    "rsi": rsi,
                    "reason": b.get("reason"),
                }
            )

    # pile-on: ≥3 buys in 7d window with cumulative usd ≥ 3*large
    for i, b in enumerate(buys):
        if not b.get("ts"):
            continue
        window = [
            x
            for x in buys
            if x.get("ts") and b["ts"] - timedelta(days=7) <= x["ts"] <= b["ts"]
        ]
        cum = sum((x.get("usd") or 0.0) for x in window)
        if len(window) >= 3 and cum >= 3 * large_usd:
            leaks["pile_on_add_streak"] += 1
            examples.append(
                {
                    "leak": "pile_on_add_streak",
                    "buy_ts": b["ts"].isoformat(),
                    "n_buys_7d": len(window),
                    "cum_usd_7d": round(cum, 2),
                    "reason": b.get("reason"),
                }
            )
            # count once per cluster end — skip if previous buy also flagged same day
            break  # one cluster flag per pair summary is enough; full list via scan_all below

    # recount pile-on clusters properly (non-overlapping greedy)
    leaks["pile_on_add_streak"] = 0
    examples = [e for e in examples if e.get("leak") != "pile_on_add_streak"]
    i = 0
    while i < len(buys):
        b = buys[i]
        if not b.get("ts"):
            i += 1
            continue
        j = i
        cum = 0.0
        n = 0
        while j < len(buys) and buys[j].get("ts") and buys[j]["ts"] <= b["ts"] + timedelta(days=7):
            # window from buys[i].ts
            if buys[j]["ts"] >= buys[i]["ts"]:
                cum += buys[j].get("usd") or 0.0
                n += 1
            j += 1
        # sliding: from each start
        window = [
            x
            for x in buys
            if x.get("ts") and buys[i]["ts"] <= x["ts"] <= buys[i]["ts"] + timedelta(days=7)
        ]
        cum = sum((x.get("usd") or 0.0) for x in window)
        n = len(window)
        if n >= 3 and cum >= 3 * large_usd:
            leaks["pile_on_add_streak"] += 1
            examples.append(
                {
                    "leak": "pile_on_add_streak",
                    "buy_ts": buys[i]["ts"].isoformat(),
                    "n_buys_7d": n,
                    "cum_usd_7d": round(cum, 2),
                    "reason": buys[i].get("reason"),
                }
            )
            # jump past window to reduce double count
            i = i + max(n - 1, 1)
            continue
        i += 1

    # same-day churn: buy and SL sell same UTC day with buy before sell
    for s in sl_sells:
        day = s["ts"].date()
        day_buys = [b for b in buys if b.get("ts") and b["ts"].date() == day and b["ts"] < s["ts"]]
        if day_buys:
            leaks["same_day_churn"] += 1
            examples.append(
                {
                    "leak": "same_day_churn",
                    "sell_ts": s["ts"].isoformat(),
                    "n_buys_same_day": len(day_buys),
                    "pnl": s.get("pnl"),
                }
            )

    sb.leak_hits = dict(leaks)
    sb.leak_examples = examples[:40]

    # edge class: net green but dominated by TP vs SL tax → less-loss hygiene
    tp_pnl = by_class.get("take_profit", {}).get("pnl", 0.0)
    sl_pnl = by_class.get("stop_loss", {}).get("pnl", 0.0)
    if realized < 0 and abs(sl_pnl) > abs(tp_pnl):
        sb.edge_class = "unstable_or_no_edge"
        sb.notes.append("Net red; SL tax dominates TP.")
    elif realized >= 0 and leaks:
        sb.edge_class = "ATTENTION_ONLY_less_loss_path"
        sb.notes.append("Net flat/green but process leaks present — hygiene > new alpha claim.")
    elif realized > 0 and not leaks:
        sb.edge_class = "ATTENTION_ONLY"
        sb.notes.append("Net green, few labeled leaks — still not HIT_10 without multipair WF.")
    else:
        sb.edge_class = "ATTENTION_ONLY_less_loss_path"

    if buy_rsi < max(3, int(0.3 * len(buys))) if buys else True:
        sb.notes.append("RSI stamp coverage thin — entry structure claims limited.")

    # sort samples
    sb.best_process_samples = sorted(
        sb.best_process_samples, key=lambda x: -(x.get("pnl") or 0)
    )[:8]
    sb.worst_process_samples = sorted(
        sb.worst_process_samples, key=lambda x: (x.get("pnl") or 0)
    )[:8]
    return sb


def paper_rule_candidates(
    sb: PairScoreboard,
    *,
    sl_cooldown_h: float = DEFAULT_SL_COOLDOWN_H,
    tp_cooldown_h: float = DEFAULT_TP_COOLDOWN_H,
    tryout_usd: float = DEFAULT_TRYOUT_USD,
    elevated_rsi: float = DEFAULT_ELEVATED_RSI,
) -> List[Dict[str, Any]]:
    """Map leak hits → paper rules (shadow would-block language only)."""
    rules: List[Dict[str, Any]] = []
    hits = sb.leak_hits or {}
    if hits.get("post_sl_reentry_Nh"):
        rules.append(
            {
                "id": "cooldown_after_sl",
                "pair_scope": sb.pair,
                "rule": f"No new buy within {sl_cooldown_h:.0f}h of SL fill (or tryout-only).",
                "hits": hits["post_sl_reentry_Nh"],
                "live": False,
            }
        )
    if hits.get("post_tp_rebuy_Nh"):
        rules.append(
            {
                "id": "cooldown_after_tp",
                "pair_scope": sb.pair,
                "rule": f"No full-size buy within {tp_cooldown_h:.0f}h of fixed/trail TP (tryout ≤ ${tryout_usd:.0f}).",
                "hits": hits["post_tp_rebuy_Nh"],
                "live": False,
            }
        )
    if hits.get("pile_on_add_streak") or hits.get("elevated_rsi_large_ticket"):
        rules.append(
            {
                "id": "single_ticket_cap",
                "pair_scope": sb.pair,
                "rule": f"Cap single buy ≤ ${tryout_usd:.0f} until 1 TP or 2 closed RTs (first-fill style).",
                "hits": int(hits.get("pile_on_add_streak") or 0)
                + int(hits.get("elevated_rsi_large_ticket") or 0),
                "live": False,
            }
        )
    if hits.get("elevated_rsi_large_ticket"):
        rules.append(
            {
                "id": "elevated_rsi_size_haircut",
                "pair_scope": sb.pair,
                "rule": f"If entry RSI ≥ {elevated_rsi:.0f}, skip or micro only.",
                "hits": hits["elevated_rsi_large_ticket"],
                "live": False,
            }
        )
    if hits.get("same_day_churn"):
        rules.append(
            {
                "id": "same_day_churn_block",
                "pair_scope": sb.pair,
                "rule": "No second buy same UTC day after SL on that pair.",
                "hits": hits["same_day_churn"],
                "live": False,
            }
        )
    rules.append(
        {
            "id": "keep_fixed_tp_bank_green",
            "pair_scope": sb.pair,
            "rule": "Keep bank-green fixed TP (~6% class); do not hold for full extension as default.",
            "hits": sb.n_by_exit_class.get("take_profit", 0),
            "live": False,
        }
    )
    return rules


def compare_pairs(
    pairs: Sequence[str],
    rows: Optional[Sequence[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    all_rows = list(rows) if rows is not None else load_ledger_rows()
    boards = [summarize_pair(p, all_rows, **kwargs) for p in pairs]
    ranked = sorted(boards, key=lambda b: b.realized_pnl_usd)
    leak_totals: Dict[str, int] = defaultdict(int)
    for b in boards:
        for k, v in (b.leak_hits or {}).items():
            leak_totals[k] += int(v)
    return {
        "schema": "trade_comparison_standard_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "n_pairs": len(boards),
        "realized_pnl_sum": round(sum(b.realized_pnl_usd for b in boards), 4),
        "leak_totals": dict(leak_totals),
        "pairs_worst_to_best": [b.pair for b in ranked],
        "scoreboards": [b.to_dict() for b in boards],
        "paper_rules": [r for b in boards for r in paper_rule_candidates(b)],
        "platform_note": (
            "Compare pairs on this scoreboard before pair-specific knobs. "
            "Generalize a rule only if leak appears on ≥2 pairs or multipair CF confirms. "
            "Shadow would-block first; live gate needs Brad GO."
        ),
    }


# --- optional OHLCV helpers (public Coinbase) ---


def fetch_coinbase_hourly(
    product_id: str,
    start: datetime,
    end: datetime,
    *,
    sleep_s: float = 0.15,
) -> List[List[float]]:
    """Return rows [time, low, high, open, close, volume] sorted."""
    gran = 3600
    out: List[List[float]] = []
    cur = start
    while cur < end:
        chunk_end = min(cur + timedelta(seconds=gran * 300), end)
        url = (
            f"https://api.exchange.coinbase.com/products/{product_id}/candles"
            f"?granularity={gran}&start={cur.isoformat().replace('+00:00', 'Z')}"
            f"&end={chunk_end.isoformat().replace('+00:00', 'Z')}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "phase6-trade-comparison"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            if isinstance(data, list):
                out.extend(data)
        except Exception:
            pass
        time.sleep(sleep_s)
        cur = chunk_end
    by: Dict[int, List[float]] = {}
    for row in out:
        try:
            by[int(row[0])] = row
        except Exception:
            continue
    return [by[k] for k in sorted(by)]


def forward_path_from_hourly(
    candles: Sequence[Sequence[float]],
    entry_ts: datetime,
    horizons_h: Sequence[int] = (24, 72, 168),
) -> Optional[Dict[str, Any]]:
    closes = {int(r[0]): float(r[4]) for r in candles}
    highs = {int(r[0]): float(r[2]) for r in candles}
    lows = {int(r[0]): float(r[1]) for r in candles}
    t0 = int(entry_ts.timestamp())
    t0 = t0 - (t0 % 3600)
    base = None
    for off in range(0, 12):
        for sign in (0, -1, 1) if off == 0 else (-1, 1):
            k = t0 + sign * off * 3600
            if k in closes:
                base = closes[k]
                t0 = k
                break
        if base is not None:
            break
    if base is None or base <= 0:
        return None
    mfe = 0.0
    mae = 0.0
    for h in range(1, 73):
        k = t0 + h * 3600
        if k in highs:
            mfe = max(mfe, highs[k] / base - 1.0)
        if k in lows:
            mae = min(mae, lows[k] / base - 1.0)
    out: Dict[str, Any] = {"entry_px": base, "mfe_72h": mfe, "mae_72h": mae}
    for H in horizons_h:
        k = t0 + int(H) * 3600
        px = None
        for back in range(0, 6):
            if k - back * 3600 in closes:
                px = closes[k - back * 3600]
                break
        if px is not None:
            out[f"ret_{H}h"] = px / base - 1.0
    return out


def would_block_buy(
    *,
    pair: str,
    buy_ts: datetime,
    usd: float,
    rsi: Optional[float],
    scoreboard: Optional[PairScoreboard] = None,
    recent_sells: Optional[Sequence[Dict[str, Any]]] = None,
    sl_cooldown_h: float = DEFAULT_SL_COOLDOWN_H,
    tp_cooldown_h: float = DEFAULT_TP_COOLDOWN_H,
    tryout_usd: float = DEFAULT_TRYOUT_USD,
    elevated_rsi: float = DEFAULT_ELEVATED_RSI,
) -> Dict[str, Any]:
    """Shadow would-block evaluator (no orders)."""
    reasons: List[str] = []
    sells = list(recent_sells or [])
    if scoreboard is None and not sells:
        # load pair sells
        sells = [sell_event(r) for r in load_ledger_rows(pair=pair) if r.get("side") == "SELL"]
    for s in sells:
        if not s.get("ts"):
            continue
        dt_h = (buy_ts - s["ts"]).total_seconds() / 3600.0
        if dt_h <= 0:
            continue
        cls = exit_class(str(s.get("reason") or ""))
        if cls == "stop_loss" and dt_h <= sl_cooldown_h:
            reasons.append(f"post_sl_reentry_{dt_h:.1f}h")
        if cls == "take_profit" and dt_h <= tp_cooldown_h and usd > tryout_usd:
            reasons.append(f"post_tp_fullsize_rebuy_{dt_h:.1f}h")
    if rsi is not None and float(rsi) >= elevated_rsi and usd > tryout_usd:
        reasons.append(f"elevated_rsi_{rsi:.1f}_large")
    if usd > tryout_usd * 4:
        reasons.append(f"mega_ticket_usd_{usd:.0f}")
    return {
        "pair": pair,
        "buy_ts": buy_ts.isoformat(),
        "block": bool(reasons),
        "reasons": reasons,
        "live": False,
        "note": "shadow only",
    }


def render_markdown_report(cmp: Dict[str, Any], title: str = "Trade comparison dig") -> str:
    lines = [
        f"# {title}",
        "",
        f"**As of:** {cmp.get('as_of')}",
        f"**Schema:** `{cmp.get('schema')}`",
        f"**Pairs:** {cmp.get('n_pairs')} · **Sum realized SELL PnL:** {cmp.get('realized_pnl_sum')}",
        "",
        "## Platform note",
        "",
        str(cmp.get("platform_note") or ""),
        "",
        "## Leak totals",
        "",
    ]
    leaks = cmp.get("leak_totals") or {}
    if not leaks:
        lines.append("_No labeled leaks._")
    else:
        lines.append("| Leak | Hits |")
        lines.append("|------|------|")
        for k, v in sorted(leaks.items(), key=lambda kv: -kv[1]):
            lines.append(f"| {k} | {v} |")
    lines.extend(["", "## Pair scoreboards (worst → best realized)", ""])
    order = cmp.get("pairs_worst_to_best") or []
    by = {b["pair"]: b for b in (cmp.get("scoreboards") or [])}
    for p in order:
        b = by.get(p) or {}
        lines.append(f"### {p}")
        lines.append("")
        lines.append(
            f"- realized **{b.get('realized_pnl_usd')}** · buys {b.get('n_clean_buys')} · sells {b.get('n_sells')} · edge `{b.get('edge_class')}`"
        )
        lines.append(f"- exit mix: `{b.get('pnl_by_exit_class')}`")
        lines.append(f"- leaks: `{b.get('leak_hits')}`")
        if b.get("notes"):
            lines.append(f"- notes: {'; '.join(b['notes'])}")
        lines.append("")
    lines.extend(["## Paper rule candidates (not live)", ""])
    for r in cmp.get("paper_rules") or []:
        lines.append(
            f"- **{r.get('id')}** [{r.get('pair_scope')}] hits={r.get('hits')}: {r.get('rule')}"
        )
    lines.extend(
        [
            "",
            "## Next",
            "",
            "1. If a leak is multipair → shadow would-block logger (no evaluate_buy_entry).",
            "2. Attach report to CR / trial finalize-report.",
            "3. Live gate only on Brad GO after multipair confirm.",
            "",
        ]
    )
    return "\n".join(lines)


def sensor_preflight_ledger(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Minimal sensor check before scoring."""
    if not rows:
        return {
            "outcome_class": "sensor_thin",
            "ok": False,
            "detail": "empty ledger slice",
        }
    sides = {str(r.get("side")) for r in rows}
    if "SELL" not in sides and "BUY" not in sides:
        return {"outcome_class": "sensor_broken", "ok": False, "detail": "no BUY/SELL sides"}
    sell_pnl = [
        r.get("pnl")
        for r in rows
        if r.get("side") == "SELL" and isinstance(r.get("pnl"), (int, float))
    ]
    if len([r for r in rows if r.get("side") == "SELL"]) >= 3 and len(sell_pnl) == 0:
        return {
            "outcome_class": "sensor_degenerate",
            "ok": False,
            "detail": "sells present but no numeric pnl",
        }
    return {"outcome_class": "sensor_ok", "ok": True, "n_rows": len(rows), "n_sell_pnl": len(sell_pnl)}
