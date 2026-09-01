#!/usr/bin/env python3
"""Stand-down filter C exploitability dig (read-only).

C = do not process-enter when tape is already elevated (hostile structure).
Not a long-after-whale arm. No live changes.

Honesty:
- Real verified fills + phase6.db prices only.
- Frozen elevated definitions pre-registered below (no post-hoc cutoff fishing).
- Outcomes use first same-pair SELL within 21d (imperfect lot match) + fee CF.
- Edge class vocabulary from offline-strategy-honesty.
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACC = "3176ac3f-deca-4fca-9c67-87ba91f96558"
NOW = datetime.now(timezone.utc)
LOOKBACK_DAYS = 90
EXIT_HORIZON_D = 21
NAV_FALLBACK = 2295.0

# Pre-registered elevated-tape defs (do not retune on this sample).
ELEVATED_DEFS = {
    # Overnight audit "heat" — pure FOMO-ish
    "heat_strict": {
        "desc": "r24>=12 OR (r24>=8 & RSI>=70) OR r6>=8",
        "fn": "heat_strict",
    },
    # Overnight "process_in_elevated_tape" boundary (process + r24>=5)
    "elev_r24_5": {
        "desc": "r24>=5 (elevated; process-on-heat boundary)",
        "fn": "elev_r24_5",
    },
    # Mid band
    "elev_r24_8": {
        "desc": "r24>=8 OR r6>=5",
        "fn": "elev_r24_8",
    },
    # Soft / early heat
    "elev_soft": {
        "desc": "r24>=3 OR r6>=3 OR RSI>=65",
        "fn": "elev_soft",
    },
}


def parse_ts(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        if s > 1e12:
            s /= 1000.0
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


def is_elevated(name: str, r24, r6, rsi) -> tuple[bool, list[str]]:
    why = []
    if name == "heat_strict":
        if r24 is not None and r24 >= 12:
            why.append(f"r24={r24:.1f}>=12")
        if r24 is not None and r24 >= 8 and rsi is not None and rsi >= 70:
            why.append(f"r24={r24:.1f}>=8&rsi={rsi:.0f}>=70")
        if r6 is not None and r6 >= 8:
            why.append(f"r6={r6:.1f}>=8")
    elif name == "elev_r24_5":
        if r24 is not None and r24 >= 5:
            why.append(f"r24={r24:.1f}>=5")
    elif name == "elev_r24_8":
        if r24 is not None and r24 >= 8:
            why.append(f"r24={r24:.1f}>=8")
        if r6 is not None and r6 >= 5:
            why.append(f"r6={r6:.1f}>=5")
    elif name == "elev_soft":
        if r24 is not None and r24 >= 3:
            why.append(f"r24={r24:.1f}>=3")
        if r6 is not None and r6 >= 3:
            why.append(f"r6={r6:.1f}>=3")
        if rsi is not None and rsi >= 65:
            why.append(f"rsi={rsi:.0f}>=65")
    return (len(why) > 0, why)


def process_hint(src: str, reason: str) -> bool:
    """Machinery entries — not bare 'signal' (too loose) or pure reconcile."""
    blob = f"{src} {reason}".lower()
    if "reconcile" in blob and not any(
        k in blob for k in ("rebalance", "arch4", "allocator", "fresh_start", "runner")
    ):
        return False
    keys = (
        "rebalance",
        "runner",
        "phase6",
        "trade_plan",
        "allocator",
        "regime",
        "fresh_start",
        "arch4",
        "rotation_in",
        "rotation_out",
        "deploy_capital",
        "opportunity_scanner",
    )
    return any(k in blob for k in keys)


def load_verified_side(side: str) -> list[dict]:
    rows: list[dict] = []
    # exchange fills
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
            sd = (o.get("side") or lr.get("side") or "").upper()
            if sd != side:
                continue
            ts = parse_ts(
                o.get("last_fill_time")
                or o.get("created_time")
                or lr.get("timestamp")
                or d.get("ingested_at")
            )
            pair = o.get("product_id") or lr.get("pair")
            q = fnum(o.get("filled_size") or lr.get("qty"))
            px = fnum(
                o.get("average_filled_price")
                or (lr.get("exit_price") if side == "SELL" else lr.get("entry_price"))
            )
            if px is None:
                px = fnum(lr.get("entry_price")) or fnum(lr.get("exit_price"))
            notional = fnum(o.get("filled_value"))
            if notional is None and q is not None and px is not None:
                notional = q * px
            fees = fnum(o.get("total_fees"))
            if fees is None:
                fees = fnum(lr.get("fees"), 0.0) or 0.0
            rows.append(
                {
                    "ts": ts,
                    "pair": pair,
                    "qty": q,
                    "price": px,
                    "notional": notional,
                    "fees": fees or 0.0,
                    "order_type": (o.get("order_type") or lr.get("order_type") or "").upper(),
                    "reason": lr.get("reason") or lr.get("exit_reason") or "",
                    "signal_source": lr.get("signal_source") or "",
                    "order_id": o.get("order_id") or lr.get("order_id"),
                    "src": "exchange_fills",
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
                if (d.get("side") or "").upper() != side:
                    continue
                q = fnum(d.get("qty"))
                px = fnum(d.get("exit_price") if side == "SELL" else d.get("entry_price"))
                if px is None:
                    px = fnum(d.get("entry_price")) or fnum(d.get("exit_price"))
                notional = q * px if q is not None and px is not None else None
                rows.append(
                    {
                        "ts": parse_ts(d.get("timestamp")),
                        "pair": d.get("pair"),
                        "qty": q,
                        "price": px,
                        "notional": notional,
                        "fees": fnum(d.get("fees"), 0.0) or 0.0,
                        "order_type": (d.get("order_type") or "").upper(),
                        "reason": d.get("reason") or d.get("exit_reason") or "",
                        "signal_source": d.get("signal_source") or "",
                        "order_id": d.get("order_id"),
                        "src": p.name,
                    }
                )

    # CSV ledger buys/sells as backup (fees often missing)
    for p in sorted((ROOT / "trades").glob("phase6_trades_*.csv")):
        with p.open() as fh:
            for row in csv.DictReader(fh):
                if (row.get("side") or "").upper() != side:
                    continue
                q = fnum(row.get("qty"))
                px = fnum(
                    row.get("exit_price")
                    if side == "SELL"
                    else (row.get("entry_price") or row.get("price"))
                )
                if px is None:
                    px = fnum(row.get("entry_price")) or fnum(row.get("exit_price"))
                notional = q * px if q is not None and px is not None else None
                rows.append(
                    {
                        "ts": parse_ts(row.get("timestamp")),
                        "pair": row.get("pair"),
                        "qty": q,
                        "price": px,
                        "notional": notional,
                        "fees": fnum(row.get("fees"), 0.0) or 0.0,
                        "order_type": (row.get("order_type") or "").upper(),
                        "reason": row.get("reason") or "",
                        "signal_source": row.get("signal_source") or "",
                        "order_id": row.get("order_id"),
                        "src": p.name,
                    }
                )

    # dedupe
    by_oid = {}
    no_oid = []
    for r in rows:
        if not r.get("ts") or not r.get("pair"):
            continue
        oid = r.get("order_id")
        if not oid:
            key = (
                r["pair"],
                r["ts"].strftime("%Y%m%d%H%M%S"),
                round(r.get("price") or 0, 6),
                side,
            )
            no_oid.append((key, r))
            continue
        prev = by_oid.get(oid)
        if prev is None or (r["fees"] or 0) >= (prev["fees"] or 0):
            by_oid[oid] = r
    seen_k = set()
    out = list(by_oid.values())
    for k, r in no_oid:
        if k in seen_k:
            continue
        seen_k.add(k)
        out.append(r)
    out.sort(key=lambda x: x["ts"])
    return out


def summarize_pnls(pnls: list[float]) -> dict:
    if not pnls:
        return {"n": 0}
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": len(pnls),
        "win_rate": round(wins / len(pnls), 3),
        "sum_pnl": round(sum(pnls), 2),
        "avg_pnl": round(sum(pnls) / len(pnls), 2),
        "median_pnl": round(statistics.median(pnls), 2),
        "p25": round(sorted(pnls)[max(0, len(pnls) // 4)], 2),
        "p75": round(sorted(pnls)[min(len(pnls) - 1, 3 * len(pnls) // 4)], 2),
    }


def edge_class(sum_blocked_pnl: float, fee_saved: float, n_blocked: int) -> str:
    """Classify C counterfactual — not a promote claim."""
    if n_blocked < 8:
        return "inconclusive_sparse_N"
    # Blocking avoids the next-sell crude PnL of those buys (if negative, C helps)
    # + always saves buy fees (and approx sell fees on matched exits)
    total = (-sum_blocked_pnl) + fee_saved  # if blocked buys lost money, -sum is positive help
    # Wait: if we block a buy that would have lost $X, we save X (benefit = -pnl of blocked).
    # benefit = -sum(pnl_blocked) + fees_saved
    benefit = -sum_blocked_pnl + fee_saved
    if benefit > 50 and -sum_blocked_pnl > 0:
        return "ATTENTION_ONLY_less_loss_path"  # not HIT abs; CF path DD/fee help
    if benefit > 0 and -sum_blocked_pnl >= 0:
        return "ATTENTION_ONLY_fee_or_flat"
    if benefit <= 0 and sum_blocked_pnl > 0:
        return "unstable_or_no_edge_blocked_winners"
    return "unstable_or_no_edge"


def main() -> int:
    cutoff = NOW - timedelta(days=LOOKBACK_DAYS)
    buys_all = load_verified_side("BUY")
    sells_all = load_verified_side("SELL")
    buys = [b for b in buys_all if b["ts"] and b["ts"] >= cutoff]
    sells = [s for s in sells_all if s["ts"] and s["ts"] >= cutoff - timedelta(days=EXIT_HORIZON_D)]

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

    # Enrich buys
    enriched = []
    for b in buys:
        r24 = prior_return(b["pair"], b["ts"], 24)
        r6 = prior_return(b["pair"], b["ts"], 6)
        # Sanity: bogus DB prices (fresh-start zeros) → drop tape features
        if r24 is not None and abs(r24) > 200:
            r24 = None
        if r6 is not None and abs(r6) > 200:
            r6 = None
        rsi = rsi_near(b["pair"], b["ts"])
        ph = process_hint(b.get("signal_source") or "", b.get("reason") or "")
        # fee estimate if missing: 0.8% of notional (book median)
        fee = b.get("fees") or 0.0
        notional = b.get("notional") or (
            (b.get("qty") or 0) * (b.get("price") or 0) if b.get("qty") and b.get("price") else 0
        )
        if (not fee or fee <= 0) and notional:
            fee = 0.008 * notional
            fee_imputed = True
        else:
            fee_imputed = False
            if not fee:
                fee = 0.0
                fee_imputed = True
        # match next sell
        next_sell = None
        horizon = b["ts"] + timedelta(days=EXIT_HORIZON_D)
        for s in sells:
            if s["pair"] != b["pair"]:
                continue
            if s["ts"] <= b["ts"]:
                continue
            if s["ts"] > horizon:
                break
            next_sell = s
            break
        # crude pnl
        pnl = None
        sell_fee = 0.0
        if next_sell and b.get("price") and next_sell.get("price") and b.get("qty"):
            # use min qty
            q = min(b.get("qty") or 0, next_sell.get("qty") or b.get("qty") or 0)
            if q > 0:
                pnl = q * (next_sell["price"] - b["price"])
                # subtract fees on both sides proportional
                buy_fee_leg = fee
                sf = next_sell.get("fees") or 0.0
                sn = next_sell.get("notional") or (
                    (next_sell.get("qty") or 0) * (next_sell.get("price") or 0)
                )
                if (not sf or sf <= 0) and sn:
                    sf = 0.008 * sn
                # scale sell fee if partial
                if next_sell.get("qty") and next_sell["qty"] > 0:
                    sell_fee = sf * (q / next_sell["qty"])
                else:
                    sell_fee = sf
                pnl = pnl - buy_fee_leg - sell_fee
        enriched.append(
            {
                **{k: b[k] for k in b},
                "r24": None if r24 is None else round(r24, 2),
                "r6": None if r6 is None else round(r6, 2),
                "rsi": None if rsi is None else round(rsi, 1),
                "process_hint": ph,
                "notional_used": round(notional or 0, 2),
                "fee_used": round(fee or 0, 4),
                "fee_imputed": fee_imputed,
                "next_sell_ts": next_sell["ts"].isoformat() if next_sell else None,
                "next_sell_reason": (next_sell or {}).get("reason"),
                "next_sell_fee": round(sell_fee, 4),
                "roundtrip_pnl_after_fees": None if pnl is None else round(pnl, 2),
            }
        )

    con.close()

    nav = NAV_FALLBACK
    live = ROOT / "data/state/phase6_live_state.json"
    if live.exists():
        try:
            ls = json.loads(live.read_text())
            nav = float(
                ls.get("total_usd")
                or ls.get("portfolio_value")
                or (ls.get("balances") or {}).get("total_usd")
                or NAV_FALLBACK
            )
        except Exception:
            pass

    # Baseline: all buys with exits
    base_pnls = [
        e["roundtrip_pnl_after_fees"]
        for e in enriched
        if e["roundtrip_pnl_after_fees"] is not None
    ]
    base_fees_buy = sum(e["fee_used"] for e in enriched)
    base_fees_sell_matched = sum(
        e["next_sell_fee"] for e in enriched if e["roundtrip_pnl_after_fees"] is not None
    )

    results_by_def = {}
    row_samples = {}

    for def_name, meta in ELEVATED_DEFS.items():
        blocked = []
        allowed = []
        for e in enriched:
            elev, why = is_elevated(def_name, e["r24"], e["r6"], e["rsi"])
            # C rule: block when elevated AND (process_hint OR always-on elevated block)
            # Primary C = block elevated process-ish entries; also report "block all elevated"
            e2 = dict(e)
            e2["elevated"] = elev
            e2["elev_why"] = why
            if elev and e["process_hint"]:
                e2["c_block_process"] = True
            else:
                e2["c_block_process"] = False
            e2["c_block_all_elev"] = bool(elev)
            if e2["c_block_process"]:
                blocked.append(e2)
            else:
                allowed.append(e2)

        def pack(rows, key_block_flag):
            # For CF we care about rows that WOULD be blocked under flag
            return rows

        # Process-elevated block CF
        b_proc = [e for e in enriched if is_elevated(def_name, e["r24"], e["r6"], e["rsi"])[0] and e["process_hint"]]
        a_proc = [e for e in enriched if e not in b_proc]
        # identity: rebuild
        b_proc, a_proc = [], []
        for e in enriched:
            elev, why = is_elevated(def_name, e["r24"], e["r6"], e["rsi"])
            row = {**e, "elevated": elev, "elev_why": why}
            if elev and e["process_hint"]:
                b_proc.append(row)
            else:
                a_proc.append(row)

        b_all, a_all = [], []
        for e in enriched:
            elev, why = is_elevated(def_name, e["r24"], e["r6"], e["rsi"])
            row = {**e, "elevated": elev, "elev_why": why}
            if elev:
                b_all.append(row)
            else:
                a_all.append(row)

        def cf_stats(blocked_rows, allowed_rows, mode):
            bp = [
                r["roundtrip_pnl_after_fees"]
                for r in blocked_rows
                if r["roundtrip_pnl_after_fees"] is not None
            ]
            ap = [
                r["roundtrip_pnl_after_fees"]
                for r in allowed_rows
                if r["roundtrip_pnl_after_fees"] is not None
            ]
            fee_buy_saved = sum(r["fee_used"] for r in blocked_rows)
            fee_sell_saved = sum(
                r["next_sell_fee"]
                for r in blocked_rows
                if r["roundtrip_pnl_after_fees"] is not None
            )
            fee_saved = fee_buy_saved + fee_sell_saved
            sum_bp = sum(bp) if bp else 0.0
            # CF portfolio of *matched blocked trades only*:
            # benefit if we never took them = -sum(pnl) + we already included fees in pnl
            # So fee_saved double-counts if pnl is after fees.
            # Use: avoided_pnl_after_fees = -sum(bp)  (if bp negative, positive benefit)
            avoided_net = -sum_bp if bp else 0.0
            # Also report fee-only (if exits unmatched)
            unmatched = [r for r in blocked_rows if r["roundtrip_pnl_after_fees"] is None]
            fee_only_unmatched = sum(r["fee_used"] for r in unmatched)

            # Half-sample stability
            blocked_sorted = sorted(blocked_rows, key=lambda x: x["ts"])
            mid = len(blocked_sorted) // 2
            h1 = [
                r["roundtrip_pnl_after_fees"]
                for r in blocked_sorted[:mid]
                if r["roundtrip_pnl_after_fees"] is not None
            ]
            h2 = [
                r["roundtrip_pnl_after_fees"]
                for r in blocked_sorted[mid:]
                if r["roundtrip_pnl_after_fees"] is not None
            ]

            return {
                "mode": mode,
                "n_blocked": len(blocked_rows),
                "n_allowed": len(allowed_rows),
                "n_blocked_with_exit": len(bp),
                "n_allowed_with_exit": len(ap),
                "blocked_outcome": summarize_pnls(bp),
                "allowed_outcome": summarize_pnls(ap),
                "blocked_buy_notional": round(sum(r["notional_used"] for r in blocked_rows), 2),
                "fee_buy_on_blocked": round(fee_buy_saved, 2),
                "fee_sell_on_blocked_matched": round(fee_sell_saved, 2),
                # primary CF metric (pnl already after fees):
                "cf_avoided_net_pnl_after_fees": round(avoided_net, 2),
                "cf_fee_only_unmatched_buys": round(fee_only_unmatched, 2),
                "cf_total_if_add_unmatched_fees": round(avoided_net + fee_only_unmatched, 2),
                "cf_pct_nav": round((avoided_net + fee_only_unmatched) / nav * 100, 2),
                "edge_class": edge_class(sum_bp, fee_only_unmatched, len(bp)),
                "half1_blocked": summarize_pnls(h1),
                "half2_blocked": summarize_pnls(h2),
                "blocked_pairs": Counter(r["pair"] for r in blocked_rows).most_common(12),
                "blocked_reasons_src": Counter(
                    ((r.get("signal_source") or r.get("reason") or "—")[:40]) for r in blocked_rows
                ).most_common(8),
            }

        results_by_def[def_name] = {
            "definition": meta["desc"],
            "process_on_elevated_block": cf_stats(b_proc, a_proc, "block_process_if_elevated"),
            "all_elevated_block": cf_stats(b_all, a_all, "block_all_if_elevated"),
            # calm vs elevated process comparison (diagnostic, not CF)
            "diagnostic": {
                "n_elevated": sum(
                    1 for e in enriched if is_elevated(def_name, e["r24"], e["r6"], e["rsi"])[0]
                ),
                "n_process_elevated": len(b_proc),
                "n_process_calm": sum(
                    1
                    for e in enriched
                    if e["process_hint"]
                    and not is_elevated(def_name, e["r24"], e["r6"], e["rsi"])[0]
                ),
            },
        }
        # samples
        row_samples[def_name] = [
            {
                "ts": r["ts"].isoformat(),
                "pair": r["pair"],
                "r24": r["r24"],
                "r6": r["r6"],
                "rsi": r["rsi"],
                "process_hint": r["process_hint"],
                "notional": r["notional_used"],
                "fee": r["fee_used"],
                "pnl_aft_fees": r["roundtrip_pnl_after_fees"],
                "src": r.get("signal_source"),
                "elev_why": r.get("elev_why"),
            }
            for r in sorted(b_proc, key=lambda x: x["ts"], reverse=True)[:15]
        ]

    # Calm process vs elevated process under elev_r24_5 (main C boundary)
    def_name = "elev_r24_5"
    calm_proc_pnls = []
    elev_proc_pnls = []
    for e in enriched:
        elev, _ = is_elevated(def_name, e["r24"], e["r6"], e["rsi"])
        if not e["process_hint"] or e["roundtrip_pnl_after_fees"] is None:
            continue
        if elev:
            elev_proc_pnls.append(e["roundtrip_pnl_after_fees"])
        else:
            calm_proc_pnls.append(e["roundtrip_pnl_after_fees"])

    out = {
        "as_of": NOW.isoformat(),
        "mode": "read_only_counterfactual",
        "thesis": "C_standdown_filter",
        "nav_usd": nav,
        "lookback_days": LOOKBACK_DAYS,
        "exit_horizon_days": EXIT_HORIZON_D,
        "method": {
            "C": "Block process-hint buys when elevated-tape def is true; alt arm blocks all elevated buys.",
            "elevated_defs_frozen": {k: v["desc"] for k, v in ELEVATED_DEFS.items()},
            "process_hint": "src/reason contains rebalance|rsi|runner|phase6|allocator|regime|fresh_start|arch4|rotation|deploy|opportunity|signal",
            "pnl": "qty_min * (sell_px - buy_px) - buy_fee - scaled_sell_fee; fee imputed at 0.8% if missing",
            "caveats": [
                "Imperfect lot match (first SELL within 21d)",
                "Fee imputation when ledger fee blank",
                "No path simulation of capital reuse after block",
                "Blocking winners hurts CF — reported honestly",
                "Not walk-forward optimized; half-sample split only",
                "No live gate / no promote",
            ],
        },
        "baseline_90d": {
            "n_buys": len(enriched),
            "n_with_exit": len(base_pnls),
            "outcome_all_buys": summarize_pnls(base_pnls),
            "sum_buy_fees": round(base_fees_buy, 2),
            "sum_matched_sell_fees": round(base_fees_sell_matched, 2),
            "process_hint_count": sum(1 for e in enriched if e["process_hint"]),
            "fee_imputed_buy_count": sum(1 for e in enriched if e["fee_imputed"]),
        },
        "calm_vs_elev_process_elev_r24_5": {
            "calm_process": summarize_pnls(calm_proc_pnls),
            "elevated_process": summarize_pnls(elev_proc_pnls),
            "delta_avg_pnl_elev_minus_calm": (
                round(
                    (sum(elev_proc_pnls) / len(elev_proc_pnls))
                    - (sum(calm_proc_pnls) / len(calm_proc_pnls)),
                    2,
                )
                if calm_proc_pnls and elev_proc_pnls
                else None
            ),
        },
        "counterfactuals": results_by_def,
        "blocked_samples": row_samples,
    }

    # Plain-English verdict
    primary = results_by_def["elev_r24_5"]["process_on_elevated_block"]
    strict = results_by_def["heat_strict"]["process_on_elevated_block"]
    soft = results_by_def["elev_soft"]["process_on_elevated_block"]
    verdict_lines = []
    verdict_lines.append(
        f"Primary C (process + r24>=5): blocked n={primary['n_blocked']} "
        f"with_exit={primary['n_blocked_with_exit']} "
        f"cf_avoided_net=${primary['cf_avoided_net_pnl_after_fees']} "
        f"({primary['cf_pct_nav']}% NAV) class={primary['edge_class']}"
    )
    verdict_lines.append(
        f"Strict heat process block: n={strict['n_blocked']} "
        f"cf=${strict['cf_avoided_net_pnl_after_fees']} class={strict['edge_class']}"
    )
    verdict_lines.append(
        f"Soft elev process block: n={soft['n_blocked']} "
        f"cf=${soft['cf_avoided_net_pnl_after_fees']} class={soft['edge_class']}"
    )
    # Decision language
    p = primary
    h1n = p["half1_blocked"].get("n", 0) or 0
    h2n = p["half2_blocked"].get("n", 0) or 0
    h1a = p["half1_blocked"].get("avg_pnl")
    h2a = p["half2_blocked"].get("avg_pnl")
    half_ok = h1n >= 3 and h2n >= 3 and h1a is not None and h2a is not None and h1a < 0 and h2a < 0

    if p["n_blocked_with_exit"] < 8:
        decision = (
            "INCONCLUSIVE — too few blocked process-on-elevated exits to claim C edge. "
            "Keep C as product/risk doctrine; do not promote a hard live gate from this N."
        )
        go = "NO-GO_live_gate"
    elif p["cf_avoided_net_pnl_after_fees"] > 0 and p["blocked_outcome"].get("avg_pnl", 0) < 0:
        # blocked trades lost on average — C would have helped on this sample
        if half_ok and p["cf_pct_nav"] >= 1.0:
            decision = (
                "ATTENTION_ONLY — C (process on r24>=5) would have avoided net losses on this sample; "
                "half-sample both negative avg with n>=3 each. Not HIT abs return. "
                "**Shadow gate candidate only** — not live."
            )
            go = "SHADOW_ONLY"
        elif p["cf_pct_nav"] >= 1.0 and p["blocked_outcome"].get("win_rate", 1) == 0:
            decision = (
                "ATTENTION_ONLY — direction favors stand-down (blocked process-on-elevated all red after fees); "
                "half-sample thin so treat as **research bias / optional shadow log**, not a promote. "
                "Also note: calm process was red too — C is less-loss on hot tape, not proof process works when calm."
            )
            go = "RESEARCH_CONTINUE_shadow_ok"
        else:
            decision = (
                "ATTENTION_ONLY / weak — direction favors stand-down on elevated process entries, "
                "but stability or magnitude below bar for shadow promote without more tape."
            )
            go = "RESEARCH_CONTINUE"
    elif p["cf_avoided_net_pnl_after_fees"] <= 0:
        decision = (
            "NO EDGE for C on primary def this sample — blocking elevated process would have "
            "removed winners or flat. Do not gate live. Doctrine stand-down still OK as bias, not rule."
        )
        go = "NO-GO_live_gate"
    else:
        decision = "Mixed — see JSON."
        go = "RESEARCH_CONTINUE"

    out["plain_english"] = {
        "verdict_lines": verdict_lines,
        "decision": decision,
        "go_no_go": go,
        "recommended_next": [
            "If SHADOW_ONLY: paper log would-block events at rebalance without changing fills",
            "Improve signal_source on ledger (many ambiguous rows)",
            "Do not retune elevated cutoffs on this same 90d",
            "Fee path (maker entries) remains separate high-leverage work",
        ],
    }

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "STANDDOWN_FILTER_C_DIG.json").write_text(
        json.dumps(out, indent=2, default=str) + "\n"
    )

    # Markdown
    md = [
        "# Stand-down filter C — exploitability dig",
        "",
        f"**As of:** {NOW.isoformat()}  ",
        f"**NAV:** ${nav:,.2f}  ",
        f"**Window:** {LOOKBACK_DAYS}d buys · exit horizon {EXIT_HORIZON_D}d  ",
        "**Mode:** read-only counterfactual · **no live changes**  ",
        "",
        "## Plain English",
        "",
        f"**GO/NO-GO:** `{go}`",
        "",
        decision,
        "",
        *[f"- {v}" for v in verdict_lines],
        "",
        "## What C is",
        "",
        "When tape is already elevated, **do not let process machinery enter** "
        "(rebalance/allocator/runner buys). Not chase-whale. Not buy-the-FOMO-leg.",
        "",
        "## Frozen elevated definitions",
        "",
    ]
    for k, v in ELEVATED_DEFS.items():
        md.append(f"- `{k}`: {v['desc']}")
    md += [
        "",
        "## Baseline (all buys in window)",
        "",
        f"- Buys: **{len(enriched)}** · with exit match: **{len(base_pnls)}**",
        f"- All matched outcome: `{summarize_pnls(base_pnls)}`",
        f"- Process-hint buys: **{sum(1 for e in enriched if e['process_hint'])}**",
        f"- Buy fees (used/imputed): **${base_fees_buy:.2f}**",
        "",
        "## Calm vs elevated process (`elev_r24_5`)",
        "",
        f"- Calm process: `{summarize_pnls(calm_proc_pnls)}`",
        f"- Elevated process: `{summarize_pnls(elev_proc_pnls)}`",
        f"- Δ avg (elev − calm): **{out['calm_vs_elev_process_elev_r24_5']['delta_avg_pnl_elev_minus_calm']}**",
        "",
        "## Counterfactuals (process-on-elevated block)",
        "",
        "| Def | n_block | n_exit | blocked avg pnl | CF avoided net | %NAV | class |",
        "|-----|---------|--------|-----------------|----------------|------|-------|",
    ]
    for dn, block in results_by_def.items():
        p = block["process_on_elevated_block"]
        bo = p["blocked_outcome"]
        md.append(
            f"| `{dn}` | {p['n_blocked']} | {p['n_blocked_with_exit']} | "
            f"{bo.get('avg_pnl')} | ${p['cf_avoided_net_pnl_after_fees']} | "
            f"{p['cf_pct_nav']}% | {p['edge_class']} |"
        )
    md += [
        "",
        "### All-elevated block (stricter arm)",
        "",
        "| Def | n_block | n_exit | CF avoided net | %NAV | class |",
        "|-----|---------|--------|----------------|------|-------|",
    ]
    for dn, block in results_by_def.items():
        p = block["all_elevated_block"]
        md.append(
            f"| `{dn}` | {p['n_blocked']} | {p['n_blocked_with_exit']} | "
            f"${p['cf_avoided_net_pnl_after_fees']} | {p['cf_pct_nav']}% | {p['edge_class']} |"
        )
    md += [
        "",
        "## Half-sample stability (primary `elev_r24_5` process block)",
        "",
        f"- H1: `{primary['half1_blocked']}`",
        f"- H2: `{primary['half2_blocked']}`",
        "",
        "## Caveats",
        "",
    ]
    for c in out["method"]["caveats"]:
        md.append(f"- {c}")
    md += [
        "",
        "## Artifacts",
        "",
        "- `reports/STANDDOWN_FILTER_C_DIG.json`",
        "- `reports/STANDDOWN_FILTER_C_DIG.md` (this file)",
        "- `scripts/phase6/dig_standdown_filter_c.py`",
        "",
        "## Edge vocabulary",
        "",
        "- No `HIT_10/20_*` claimed.",
        "- Best available tag from this dig is `ATTENTION_ONLY` or `inconclusive` / `no_edge`.",
        "- Live gate requires Brad GO + shadow period — not auto from this file.",
        "",
    ]
    (reports / "STANDDOWN_FILTER_C_DIG.md").write_text("\n".join(md) + "\n")

    print("OK")
    print("go", go)
    print("decision", decision)
    print("n_buys", len(enriched), "with_exit", len(base_pnls))
    print("calm_proc", summarize_pnls(calm_proc_pnls))
    print("elev_proc", summarize_pnls(elev_proc_pnls))
    for dn in ELEVATED_DEFS:
        p = results_by_def[dn]["process_on_elevated_block"]
        print(
            dn,
            "block",
            p["n_blocked"],
            "exit",
            p["n_blocked_with_exit"],
            "cf",
            p["cf_avoided_net_pnl_after_fees"],
            "class",
            p["edge_class"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
