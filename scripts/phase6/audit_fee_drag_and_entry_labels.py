#!/usr/bin/env python3
"""Fee drag + entry process-vs-heat labeling audit (read-only, no live changes)."""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACC = "3176ac3f-deca-4fca-9c67-87ba91f96558"
NOW = datetime.now(timezone.utc)
WINDOWS = {
    "30d": NOW - timedelta(days=30),
    "90d": NOW - timedelta(days=90),
}


def parse_ts(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        if s > 1e12:
            s = s / 1000.0
        return datetime.fromtimestamp(s, tz=timezone.utc)
    s = str(s).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def fnum(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def liq_class(ot: str) -> str:
    ot = (ot or "").upper()
    if "MARKET" in ot and "STOP" not in ot:
        return "taker"
    if "STOP" in ot:
        return "taker_stop"
    if "LIMIT" in ot:
        return "maker_limit"
    if not ot:
        return "unknown"
    return "other:" + ot[:24]


def load_fills() -> list[dict]:
    fills: list[dict] = []
    ef = ROOT / "trades/phase6_exchange_fills.jsonl"
    if ef.exists():
        for ln in ef.read_text().strip().splitlines():
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            o = d.get("order") or {}
            lr = d.get("ledger_row") or {}
            ts = parse_ts(
                o.get("last_fill_time")
                or o.get("created_time")
                or lr.get("timestamp")
                or d.get("ingested_at")
            )
            pair = o.get("product_id") or lr.get("pair")
            side = (o.get("side") or lr.get("side") or "").upper()
            filled_val = fnum(o.get("filled_value"))
            if filled_val is None:
                q = fnum(o.get("filled_size") or lr.get("qty"))
                px = fnum(
                    o.get("average_filled_price")
                    or lr.get("exit_price")
                    or lr.get("entry_price")
                )
                if q is not None and px is not None:
                    filled_val = q * px
            fees = fnum(o.get("total_fees"))
            if fees is None:
                fees = fnum(lr.get("fees"))
            if fees is None:
                cd = o.get("commission_detail_total") or {}
                fees = fnum(cd.get("total_commission") or cd.get("client_commission"))
            ot = (o.get("order_type") or lr.get("order_type") or "").upper()
            fills.append(
                {
                    "source": "exchange_fills",
                    "order_id": o.get("order_id") or lr.get("order_id"),
                    "ts": ts,
                    "pair": pair,
                    "side": side,
                    "notional": filled_val,
                    "fees": fees or 0.0,
                    "order_type": ot,
                    "reason": lr.get("reason") or lr.get("exit_reason") or "",
                    "signal_source": lr.get("signal_source") or "",
                }
            )

    vdir = ROOT / f"data/state/trading_log/{ACC}"
    if vdir.exists():
        for p in sorted(vdir.glob("verified_fills_*.jsonl")):
            for ln in p.read_text().strip().splitlines():
                if not ln.strip():
                    continue
                try:
                    d = json.loads(ln)
                except Exception:
                    continue
                ts = parse_ts(d.get("timestamp") or d.get("ingested_at"))
                pair = d.get("pair")
                side = (d.get("side") or "").upper()
                q = fnum(d.get("qty"))
                px = fnum(d.get("exit_price") if side == "SELL" else d.get("entry_price"))
                if px is None:
                    px = fnum(d.get("entry_price")) or fnum(d.get("exit_price"))
                notional = q * px if q is not None and px is not None else None
                fees = fnum(d.get("fees"), 0.0) or 0.0
                fills.append(
                    {
                        "source": p.name,
                        "order_id": d.get("order_id"),
                        "ts": ts,
                        "pair": pair,
                        "side": side,
                        "notional": notional,
                        "fees": fees,
                        "order_type": (d.get("order_type") or "").upper(),
                        "reason": d.get("reason") or d.get("exit_reason") or "",
                        "signal_source": d.get("signal_source") or "",
                    }
                )

    by_oid: dict = {}
    no_oid = []
    for f in fills:
        oid = f.get("order_id")
        if not oid:
            no_oid.append(f)
            continue
        prev = by_oid.get(oid)
        if prev is None:
            by_oid[oid] = f
            continue
        score = (1 if f["source"] == "exchange_fills" else 0) + (1 if f["fees"] else 0)
        pscore = (1 if prev["source"] == "exchange_fills" else 0) + (
            1 if prev["fees"] else 0
        )
        if score >= pscore:
            m = dict(prev)
            m.update({k: v for k, v in f.items() if v not in (None, "", 0)})
            m["fees"] = max(float(prev.get("fees") or 0), float(f.get("fees") or 0))
            if not m.get("notional"):
                m["notional"] = prev.get("notional") or f.get("notional")
            by_oid[oid] = m

    uniq = list(by_oid.values()) + no_oid
    for f in uniq:
        f["liq"] = liq_class(f.get("order_type") or "")
        n = f.get("notional")
        fee = f.get("fees") or 0
        f["fee_pct"] = (fee / n * 100) if n and n > 0 else None
    return uniq


def window_stats(uniq, cutoff):
    rows = [f for f in uniq if f["ts"] and f["ts"] >= cutoff]
    total_fees = sum(f["fees"] or 0 for f in rows)
    total_notional = sum(f["notional"] or 0 for f in rows if f.get("notional"))
    n_with_n = sum(1 for f in rows if f.get("notional"))
    by_liq = Counter(f["liq"] for f in rows)
    fees_by_liq: dict = defaultdict(float)
    notional_by_liq: dict = defaultdict(float)
    for f in rows:
        fees_by_liq[f["liq"]] += f["fees"] or 0
        if f.get("notional"):
            notional_by_liq[f["liq"]] += f["notional"]
    by_side = Counter(f["side"] for f in rows)
    fees_side: dict = defaultdict(float)
    for f in rows:
        fees_side[f["side"]] += f["fees"] or 0
    rates = [
        f["fee_pct"]
        for f in rows
        if f.get("fee_pct") is not None and f.get("notional") and f["notional"] > 1
    ]
    pair_fees: dict = defaultdict(float)
    pair_n: dict = defaultdict(float)
    pair_cnt: Counter = Counter()
    for f in rows:
        if not f.get("pair"):
            continue
        pair_fees[f["pair"]] += f["fees"] or 0
        pair_cnt[f["pair"]] += 1
        if f.get("notional"):
            pair_n[f["pair"]] += f["notional"]
    top_pairs = sorted(pair_fees.items(), key=lambda x: -x[1])[:12]
    mon: dict = defaultdict(lambda: {"fees": 0.0, "n": 0, "notional": 0.0})
    for f in rows:
        k = f["ts"].strftime("%Y-%m")
        mon[k]["fees"] += f["fees"] or 0
        mon[k]["n"] += 1
        mon[k]["notional"] += f.get("notional") or 0
    reasons = Counter((f.get("reason") or "—")[:48] for f in rows)
    ot = Counter((f.get("order_type") or "—")[:32] for f in rows)
    return {
        "n_fills": len(rows),
        "total_fees_usd": round(total_fees, 4),
        "total_notional_usd": round(total_notional, 2),
        "fee_pct_of_notional": round(total_fees / total_notional * 100, 4)
        if total_notional
        else None,
        "n_with_notional": n_with_n,
        "by_liq_count": dict(by_liq),
        "fees_by_liq": {k: round(v, 4) for k, v in fees_by_liq.items()},
        "notional_by_liq": {k: round(v, 2) for k, v in notional_by_liq.items()},
        "by_side": dict(by_side),
        "fees_by_side": {k: round(v, 4) for k, v in fees_side.items()},
        "fee_pct_median": round(sorted(rates)[len(rates) // 2], 4) if rates else None,
        "fee_pct_p25": round(sorted(rates)[len(rates) // 4], 4) if rates else None,
        "fee_pct_p75": round(sorted(rates)[3 * len(rates) // 4], 4) if rates else None,
        "top_pairs_by_fee": [
            (p, round(fe, 4), pair_cnt[p], round(pair_n.get(p, 0), 2))
            for p, fe in top_pairs
        ],
        "by_month": {
            k: {
                kk: (round(vv, 4) if isinstance(vv, float) else vv)
                for kk, vv in v.items()
            }
            for k, v in sorted(mon.items())
        },
        "top_reasons": reasons.most_common(12),
        "order_types": ot.most_common(12),
        "fills_per_day": round(len(rows) / max(1, (NOW - cutoff).days), 2),
    }


def load_buys() -> list[dict]:
    buys: list[dict] = []
    tdir = ROOT / "trades"
    for p in sorted(tdir.glob("phase6_trades_*.csv")):
        with p.open() as fh:
            for row in csv.DictReader(fh):
                side = (row.get("side") or "").upper()
                if side != "BUY":
                    continue
                buys.append(
                    {
                        "ts": parse_ts(row.get("timestamp")),
                        "pair": row.get("pair"),
                        "qty": fnum(row.get("qty")),
                        "price": fnum(row.get("entry_price") or row.get("price")),
                        "signal_source": row.get("signal_source") or "",
                        "reason": row.get("reason") or "",
                        "source_file": p.name,
                    }
                )
    vdir = ROOT / f"data/state/trading_log/{ACC}"
    if vdir.exists():
        for p in sorted(vdir.glob("verified_fills_*.jsonl")):
            for ln in p.read_text().strip().splitlines():
                try:
                    d = json.loads(ln)
                except Exception:
                    continue
                if (d.get("side") or "").upper() != "BUY":
                    continue
                buys.append(
                    {
                        "ts": parse_ts(d.get("timestamp")),
                        "pair": d.get("pair"),
                        "qty": fnum(d.get("qty")),
                        "price": fnum(d.get("entry_price")),
                        "signal_source": d.get("signal_source") or "",
                        "reason": d.get("reason") or "",
                        "source_file": p.name,
                    }
                )
    seen = set()
    ub = []
    for b in buys:
        if not b["ts"] or not b["pair"]:
            continue
        key = (b["pair"], b["ts"].strftime("%Y%m%d%H%M"), round(b["price"] or 0, 6))
        if key in seen:
            continue
        seen.add(key)
        ub.append(b)
    return ub


def main() -> int:
    uniq = load_fills()
    fee_report = {name: window_stats(uniq, cut) for name, cut in WINDOWS.items()}
    all_ts = [f["ts"] for f in uniq if f["ts"]]
    if all_ts:
        fee_report["all_available"] = window_stats(uniq, min(all_ts))

    buys = load_buys()
    sample_cut = WINDOWS["90d"]
    cands = [b for b in buys if b["ts"] and b["ts"] >= sample_cut]
    cands.sort(key=lambda x: x["ts"], reverse=True)

    con = sqlite3.connect(str(ROOT / "data/phase6.db"))

    def prior_return(pair, ts, hours=24):
        t0 = (ts - timedelta(hours=hours)).isoformat()
        t1 = ts.isoformat()
        row1 = con.execute(
            "SELECT price FROM prices WHERE pair=? AND ts<=? ORDER BY ts DESC LIMIT 1",
            (pair, t1),
        ).fetchone()
        row0 = con.execute(
            "SELECT price FROM prices WHERE pair=? AND ts<=? ORDER BY ts DESC LIMIT 1",
            (pair, t0),
        ).fetchone()
        if not row0 or not row1:
            return None
        p0, p1 = float(row0[0]), float(row1[0])
        if p0 <= 0:
            return None
        return (p1 - p0) / p0 * 100.0

    def rsi_near(pair, ts):
        row = con.execute(
            "SELECT value FROM rsi_values WHERE pair=? AND ts<=? ORDER BY ts DESC LIMIT 1",
            (pair, ts.isoformat()),
        ).fetchone()
        return float(row[0]) if row else None

    def sent_near(pair, ts):
        row = con.execute(
            "SELECT score FROM sentiment_scores WHERE pair=? AND ts<=? ORDER BY ts DESC LIMIT 1",
            (pair, ts.isoformat()),
        ).fetchone()
        return float(row[0]) if row else None

    def label_buy(b):
        r24 = prior_return(b["pair"], b["ts"], 24)
        r6 = prior_return(b["pair"], b["ts"], 6)
        rsi = rsi_near(b["pair"], b["ts"])
        sent = sent_near(b["pair"], b["ts"])
        src = (b.get("signal_source") or "").lower()
        reason = (b.get("reason") or "").lower()
        heat = False
        heat_why = []
        if r24 is not None and r24 >= 12:
            heat = True
            heat_why.append(f"r24={r24:.1f}%>=12")
        if r24 is not None and r24 >= 8 and rsi is not None and rsi >= 70:
            heat = True
            heat_why.append(f"r24={r24:.1f}%>=8 & rsi={rsi:.0f}>=70")
        if r6 is not None and r6 >= 8:
            heat = True
            heat_why.append(f"r6={r6:.1f}%>=8")
        process_hint = any(
            k in src or k in reason
            for k in (
                "rebalance",
                "rsi",
                "runner",
                "phase6",
                "trade_plan",
                "allocator",
                "regime",
            )
        )
        if heat:
            lab = "heat_reaction"
        elif process_hint and (r24 is None or r24 < 5):
            lab = "process"
        elif process_hint:
            lab = "process_in_elevated_tape"
        else:
            lab = "ambiguous"
        return {
            **{
                k: b[k]
                for k in ("pair", "qty", "price", "signal_source", "reason", "source_file")
            },
            "ts": b["ts"].isoformat(),
            "r24_pct": None if r24 is None else round(r24, 2),
            "r6_pct": None if r6 is None else round(r6, 2),
            "rsi": None if rsi is None else round(rsi, 1),
            "sentiment": None if sent is None else round(sent, 3),
            "label": lab,
            "heat_why": heat_why,
        }

    labeled = [label_buy(b) for b in cands]
    label_counts = Counter(x["label"] for x in labeled)

    pnl_by_label: dict = defaultdict(list)
    for lab in labeled:
        row = con.execute(
            """SELECT pnl, pnl_pct, ts FROM trades
               WHERE pair=? AND upper(side)='SELL' AND ts>? AND pnl IS NOT NULL
               ORDER BY ts ASC LIMIT 1""",
            (lab["pair"], lab["ts"]),
        ).fetchone()
        if row:
            lab["next_sell_pnl"] = float(row[0]) if row[0] is not None else None
            lab["next_sell_pnl_pct"] = float(row[1]) if row[1] is not None else None
            lab["next_sell_ts"] = row[2]
            pnl_by_label[lab["label"]].append(lab["next_sell_pnl"] or 0.0)
        else:
            lab["next_sell_pnl"] = None

    outcome_summary = {}
    for lab, pnls in pnl_by_label.items():
        if not pnls:
            continue
        wins = sum(1 for p in pnls if p > 0)
        outcome_summary[lab] = {
            "n_with_exit": len(pnls),
            "win_rate": round(wins / len(pnls), 3),
            "sum_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
        }

    con.close()

    nav = None
    live = ROOT / "data/state/phase6_live_state.json"
    if live.exists():
        try:
            ls = json.loads(live.read_text())
            nav = (
                ls.get("total_usd")
                or ls.get("portfolio_value")
                or (ls.get("balances") or {}).get("total_usd")
            )
        except Exception:
            pass

    out = {
        "as_of": NOW.isoformat(),
        "nav_usd_snapshot": nav,
        "method": {
            "fills": "Deduped trades/phase6_exchange_fills.jsonl + verified_fills_*.jsonl by order_id",
            "maker_taker": (
                "Heuristic from order_type only (these rows lack explicit liquidity flag). "
                "LIMIT→maker_limit; STOP*→taker_stop; MARKET→taker."
            ),
            "fees": "order.total_fees / ledger fees (USD)",
            "entry_labels": {
                "heat_reaction": "24h ret≥12% OR (24h≥8% & RSI≥70) OR 6h ret≥8% at buy time",
                "process": "signal/reason hints rebalance|rsi|runner|... AND 24h ret<5%",
                "process_in_elevated_tape": "process machinery but tape already up",
                "ambiguous": "else",
            },
            "caveats": [
                "Maker/taker is order_type heuristic, not exchange liquidity tag",
                "next_sell_pnl is first SELL after BUY in phase6.db — imperfect lot match",
                "Read-only audit; no orders",
            ],
        },
        "fee_drag": fee_report,
        "entry_labels_90d": {
            "n_buys": len(labeled),
            "counts": dict(label_counts),
            "outcome_by_label_crude": outcome_summary,
            "sample_newest_40": labeled[:40],
        },
    }

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "FEE_DRAG_AUDIT_LATEST.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n"
    )
    (reports / "ENTRY_PROCESS_VS_HEAT_LABELS_90D.json").write_text(
        json.dumps(labeled, indent=2, default=str) + "\n"
    )

    # Markdown brief
    lines = [
        "# Fee drag + entry label audit",
        "",
        f"**As of:** {NOW.isoformat()}  ",
        f"**NAV snapshot:** {nav}  ",
        "**Mode:** read-only  ",
        "",
        "## 1. Fee drag",
        "",
    ]
    for w in ("30d", "90d", "all_available"):
        fr = fee_report.get(w) or {}
        if not fr:
            continue
        lines += [
            f"### Window `{w}`",
            "",
            f"- Fills: **{fr.get('n_fills')}** (~{fr.get('fills_per_day')}/day)",
            f"- Fees paid (USD): **${fr.get('total_fees_usd')}**",
            f"- Notional traded: **${fr.get('total_notional_usd')}**",
            f"- Fees / notional: **{fr.get('fee_pct_of_notional')}%**",
            f"- Fee% median (fills with notional>$1): **{fr.get('fee_pct_median')}%** (p25={fr.get('fee_pct_p25')}, p75={fr.get('fee_pct_p75')})",
            f"- Liquidity class counts: `{fr.get('by_liq_count')}`",
            f"- Fees by class: `{fr.get('fees_by_liq')}`",
            f"- Side counts: `{fr.get('by_side')}` fees `{fr.get('fees_by_side')}`",
            f"- Top order types: `{fr.get('order_types')}`",
            f"- Top reasons: `{fr.get('top_reasons')}`",
            f"- Top pairs by fee: `{fr.get('top_pairs_by_fee')}`",
            f"- By month: `{fr.get('by_month')}`",
            "",
        ]
    lines += [
        "### Interpretation notes",
        "",
        "- **House cut is real even when $ small** — fee% of notional is the structural tax.",
        "- **`taker_stop` share** = protective exits often paying taker-like costs when stops fire.",
        "- **`maker_limit` share** = intended path for entries; if fees cluster on stops, churn still taxes the book.",
        "- Compare fee_pct medians to Coinbase schedule (maker ~0.05–0.25% tier-dependent; taker higher).",
        "",
        "## 2. Entry labels (90d)",
        "",
        f"- Buys labeled: **{len(labeled)}**",
        f"- Counts: `{dict(label_counts)}`",
        f"- Crude exit outcome by label: `{outcome_summary}`",
        "",
        "Label rules frozen in JSON `method.entry_labels`. Full rows: `ENTRY_PROCESS_VS_HEAT_LABELS_90D.json`.",
        "",
        "### Newest sample (12)",
        "",
    ]
    for row in labeled[:12]:
        lines.append(
            f"- `{row.get('ts')}` **{row.get('pair')}** label=`{row.get('label')}` "
            f"r24={row.get('r24_pct')} r6={row.get('r6_pct')} rsi={row.get('rsi')} "
            f"src=`{row.get('signal_source')}` why={row.get('heat_why')} "
            f"next_pnl={row.get('next_sell_pnl')}"
        )
    lines += [
        "",
        "## 3. Artifacts",
        "",
        "- `reports/FEE_DRAG_AUDIT_LATEST.json`",
        "- `reports/ENTRY_PROCESS_VS_HEAT_LABELS_90D.json`",
        "- `reports/FEE_DRAG_AND_ENTRY_LABEL_AUDIT.md` (this file)",
        "- Script: `scripts/phase6/audit_fee_drag_and_entry_labels.py`",
        "",
    ]
    (reports / "FEE_DRAG_AND_ENTRY_LABEL_AUDIT.md").write_text("\n".join(lines) + "\n")

    print("OK")
    print("unique_fills", len(uniq))
    print("buys_90d", len(labeled), dict(label_counts))
    for w in ("30d", "90d"):
        fr = fee_report[w]
        print(
            w,
            "n",
            fr["n_fills"],
            "fees",
            fr["total_fees_usd"],
            "notional",
            fr["total_notional_usd"],
            "fee%",
            fr["fee_pct_of_notional"],
            "liq",
            fr["by_liq_count"],
        )
    print("outcomes", outcome_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
