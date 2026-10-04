#!/usr/bin/env python3
"""P2 fee audit on tryout scale-window eject cohort.

Honesty rule: process-tax measurement must not ignore fees.
Gross green ejects that are net red after RT fees are process tax, not wins.

Sources (priority):
  1. Exchange fill total_fees on sell / entry order_id (truth)
  2. Ledger fee_usd / total_fees already stamped
  3. Live fee-tier taker rate × notional (estimate; labeled)

Measure-only by default. Optional ledger backfill stamps fee fields + net PnL
without inventing alpha.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger(__name__)

SCHEMA = "tryout_eject_fee_audit_v1"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
LATEST_JSON = STATE_DIR / "tryout_eject_fee_audit_latest.json"
LATEST_MD = PROJECT_ROOT / "reports" / "TRYOUT_EJECT_FEE_AUDIT_LATEST.md"
REPORT_DIR = PROJECT_ROOT / "reports"

EJECT_REASON_TOKENS = ("tryout_scale_window_eject", "scale_window_eject")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper()
    if not s:
        return ""
    if "-" not in s:
        s = f"{s}-USD"
    return s


def _is_eject_sell(row: Dict[str, Any]) -> bool:
    if str(row.get("side") or row.get("action") or "").upper() not in (
        "SELL",
        "SELL_SHORT",
        "EXIT",
    ):
        return False
    rsn = str(row.get("reason") or row.get("exit_reason") or "").lower()
    return any(t in rsn for t in EJECT_REASON_TOKENS)


def load_live_taker_rate(*, fallback: float = 0.009) -> Dict[str, Any]:
    """Prefer fee_tier_snapshot_latest; else fallback Intro-ish 0.9%."""
    out: Dict[str, Any] = {
        "taker_fee_rate": float(fallback),
        "source": "fallback_intro_0.9pct",
        "pricing_tier": None,
        "as_of": None,
    }
    try:
        from phase6.core.fee_tier_snapshot import load_latest_tier

        blob = load_latest_tier() or {}
        tier = blob.get("tier") or {}
        r = tier.get("taker_fee_rate")
        if r is not None and float(r) > 0:
            out["taker_fee_rate"] = float(r)
            out["source"] = "fee_tier_snapshot_latest"
            out["pricing_tier"] = tier.get("pricing_tier")
            out["as_of"] = blob.get("ts")
            out["maker_fee_rate"] = tier.get("maker_fee_rate")
    except Exception as e:
        out["load_err"] = str(e)[:120]
    return out


def estimate_side_fee_usd(notional_usd: float, rate: float) -> float:
    n = max(0.0, float(notional_usd or 0.0))
    r = max(0.0, float(rate or 0.0))
    return round(n * r, 6)


def _extract_fee_from_fill(fill: Dict[str, Any]) -> Optional[float]:
    if not isinstance(fill, dict):
        return None
    for k in ("total_fees", "fee_usd", "fees", "fee", "commission"):
        v = fill.get(k)
        if v is None or v == "":
            continue
        try:
            f = abs(float(v))
            if f >= 0:
                return f
        except (TypeError, ValueError):
            continue
    return None


def fetch_order_fee_usd(exchange: Any, order_id: Optional[str]) -> Dict[str, Any]:
    """One order_id → fee truth via get_order_fill_details."""
    out: Dict[str, Any] = {
        "order_id": order_id,
        "fee_usd": None,
        "source": None,
        "ok": False,
    }
    if not order_id or exchange is None:
        out["source"] = "no_order_or_exchange"
        return out
    if not hasattr(exchange, "get_order_fill_details"):
        out["source"] = "no_get_order_fill_details"
        return out
    try:
        fill = exchange.get_order_fill_details(str(order_id)) or {}
        fee = _extract_fee_from_fill(fill)
        out["fill_status"] = fill.get("status")
        out["average_filled_price"] = fill.get("average_filled_price")
        out["filled_size"] = fill.get("filled_size")
        if fee is not None:
            out["fee_usd"] = round(float(fee), 8)
            out["source"] = "exchange_fill"
            out["ok"] = True
        else:
            out["source"] = "exchange_fill_no_fee"
    except Exception as e:
        out["source"] = "exchange_err"
        out["error"] = str(e)[:160]
    return out


def resolve_row_fees(
    row: Dict[str, Any],
    *,
    taker_rate: float,
    exchange: Any = None,
    fetch_live: bool = False,
) -> Dict[str, Any]:
    """Resolve sell + entry fees for one eject SELL row."""
    pair = _norm_pair(str(row.get("pair") or row.get("product_id") or ""))
    qty = _f(row.get("qty") or row.get("filled_qty") or row.get("size"))
    entry_px = _f(
        row.get("entry_price")
        or row.get("avg_entry")
        or row.get("cost_basis")
        or row.get("basis_price")
    )
    exit_px = _f(
        row.get("exit_price")
        or row.get("average_filled_price")
        or row.get("fill_price")
        or row.get("price")
    )
    n_entry = entry_px * qty if entry_px > 0 and qty > 0 else 0.0
    n_exit = exit_px * qty if exit_px > 0 and qty > 0 else 0.0
    gross = (exit_px - entry_px) * qty if entry_px > 0 and exit_px > 0 and qty > 0 else None

    sell_fee: Optional[float] = None
    sell_src = "missing"
    entry_fee: Optional[float] = None
    entry_src = "missing"

    # Ledger stamps first
    for k in ("sell_fee_usd", "exit_fee_usd", "fee_usd", "total_fees", "fees", "fee"):
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            sell_fee = abs(float(v))
            sell_src = f"ledger:{k}"
            break
        except (TypeError, ValueError):
            continue
    for k in ("entry_fee_usd", "buy_fee_usd"):
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            entry_fee = abs(float(v))
            entry_src = f"ledger:{k}"
            break
        except (TypeError, ValueError):
            continue

    # Live exchange truth
    if fetch_live and exchange is not None:
        oid = row.get("order_id")
        if sell_src.startswith("missing") or sell_src.startswith("est"):
            got = fetch_order_fee_usd(exchange, str(oid) if oid else None)
            if got.get("ok") and got.get("fee_usd") is not None:
                sell_fee = float(got["fee_usd"])
                sell_src = "exchange_sell"
        eoid = row.get("entry_order_id")
        if eoid and (entry_src.startswith("missing") or entry_src.startswith("est")):
            got_e = fetch_order_fee_usd(exchange, str(eoid))
            if got_e.get("ok") and got_e.get("fee_usd") is not None:
                # Entry order may cover a larger parent lot — scale by tryout qty
                e_sz = _f(got_e.get("filled_size"))
                e_fee = float(got_e["fee_usd"])
                if e_sz > 0 and qty > 0 and e_sz > qty * 1.05:
                    # Parent fill larger than this shell — pro-rate by size
                    entry_fee = round(e_fee * (qty / e_sz), 8)
                    entry_src = "exchange_entry_prorated"
                    entry_parent_fee = e_fee
                else:
                    entry_fee = e_fee
                    entry_src = "exchange_entry"
                    entry_parent_fee = None
            else:
                entry_parent_fee = None
        else:
            entry_parent_fee = None
    else:
        entry_parent_fee = None

    # Estimates from live tier when still missing
    if sell_fee is None and n_exit > 0:
        sell_fee = estimate_side_fee_usd(n_exit, taker_rate)
        sell_src = "est_taker_exit"
    if entry_fee is None and n_entry > 0:
        entry_fee = estimate_side_fee_usd(n_entry, taker_rate)
        entry_src = "est_taker_entry"

    sell_fee_f = float(sell_fee or 0.0)
    entry_fee_f = float(entry_fee or 0.0)
    rt = round(sell_fee_f + entry_fee_f, 6)
    net = None if gross is None else round(float(gross) - rt, 6)
    fee_blind_win = gross is not None and float(gross) > 0
    fee_aware_win = net is not None and float(net) > 0
    wiped = bool(fee_blind_win and not fee_aware_win)

    return {
        "pair": pair,
        "timestamp": row.get("timestamp") or row.get("ts"),
        "order_id": row.get("order_id"),
        "entry_order_id": row.get("entry_order_id"),
        "qty": qty,
        "entry_price": entry_px or None,
        "exit_price": exit_px or None,
        "notional_entry_usd": round(n_entry, 4) if n_entry else None,
        "notional_exit_usd": round(n_exit, 4) if n_exit else None,
        "pnl_gross_usd": round(float(gross), 6) if gross is not None else None,
        "sell_fee_usd": round(sell_fee_f, 6) if sell_fee is not None else None,
        "entry_fee_usd": round(entry_fee_f, 6) if entry_fee is not None else None,
        "entry_fee_parent_usd": entry_parent_fee,
        "rt_fee_usd": rt,
        "pnl_net_usd": net,
        "sell_fee_source": sell_src,
        "entry_fee_source": entry_src,
        "fee_blind_green": fee_blind_win,
        "fee_aware_green": fee_aware_win,
        "gross_green_net_red": wiped,
        "ledger_pnl": row.get("pnl"),
        "ledger_pnl_gross": row.get("pnl_gross"),
        "ledger_fee_usd_applied": row.get("fee_usd_applied"),
        "taker_rate_used": taker_rate,
        "reason": row.get("reason"),
    }


def load_eject_sells(
    ledger_path: Optional[Path] = None,
    *,
    lookback_days: Optional[float] = None,
) -> List[Dict[str, Any]]:
    path = ledger_path or LEDGER_PATH
    rows: List[Dict[str, Any]] = []
    if not path.is_file():
        return rows
    cut = None
    if lookback_days is not None and lookback_days > 0:
        cut = datetime.now(timezone.utc).timestamp() - float(lookback_days) * 86400.0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or not _is_eject_sell(row):
            continue
        if cut is not None:
            ts = row.get("timestamp") or row.get("ts") or ""
            try:
                t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t.timestamp() < cut:
                    continue
            except Exception:
                pass
        rows.append(row)
    return rows


def audit_eject_cohort(
    *,
    ledger_path: Optional[Path] = None,
    lookback_days: Optional[float] = None,
    exchange: Any = None,
    fetch_live: bool = False,
    taker_rate: Optional[float] = None,
) -> Dict[str, Any]:
    tier = load_live_taker_rate()
    rate = float(taker_rate) if taker_rate is not None else float(tier["taker_fee_rate"])
    sells = load_eject_sells(ledger_path, lookback_days=lookback_days)
    cohort: List[Dict[str, Any]] = []
    for row in sells:
        cohort.append(
            resolve_row_fees(row, taker_rate=rate, exchange=exchange, fetch_live=fetch_live)
        )

    n = len(cohort)
    sum_gross = sum(_f(r.get("pnl_gross_usd")) for r in cohort)
    sum_rt = sum(_f(r.get("rt_fee_usd")) for r in cohort)
    sum_net = sum(_f(r.get("pnl_net_usd")) for r in cohort)
    n_blind_g = sum(1 for r in cohort if r.get("fee_blind_green"))
    n_aware_g = sum(1 for r in cohort if r.get("fee_aware_green"))
    n_wiped = sum(1 for r in cohort if r.get("gross_green_net_red"))
    n_sell_truth = sum(1 for r in cohort if str(r.get("sell_fee_source") or "").startswith("exchange"))
    n_entry_truth = sum(1 for r in cohort if str(r.get("entry_fee_source") or "").startswith("exchange"))

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _utc_iso(),
        "lookback_days": lookback_days,
        "n_ejects": n,
        "fee_tier": tier,
        "taker_rate_used": rate,
        "fetch_live": bool(fetch_live),
        "sums": {
            "pnl_gross_usd": round(sum_gross, 6),
            "rt_fee_usd": round(sum_rt, 6),
            "pnl_net_usd": round(sum_net, 6),
            "fee_drag_vs_gross": round(sum_gross - sum_net, 6),
        },
        "scoreboard": {
            "fee_blind_green_n": n_blind_g,
            "fee_blind_wr": round(n_blind_g / n, 4) if n else None,
            "fee_aware_green_n": n_aware_g,
            "fee_aware_wr": round(n_aware_g / n, 4) if n else None,
            "gross_green_net_red_n": n_wiped,
            "sell_fee_exchange_truth_n": n_sell_truth,
            "entry_fee_exchange_truth_n": n_entry_truth,
        },
        "cohort": cohort,
        "product_rule": (
            "Profit measurement on ejects must use fee-aware net. "
            "Gross-only green that nets red is process tax, not a win."
        ),
        "notes": [
            "Protected market exits historically omitted total_fees on ledger SELL rows.",
            "stamp_sell_pnl nets fees only when present — fee-blind gross was the default stamp.",
            f"Live tier taker used for estimates: {rate} ({tier.get('source')}).",
        ],
    }
    return payload


def render_markdown(payload: Dict[str, Any]) -> str:
    sb = payload.get("scoreboard") or {}
    sm = payload.get("sums") or {}
    tier = payload.get("fee_tier") or {}
    lines = [
        "# Tryout eject fee audit",
        "",
        f"**As of:** {payload.get('as_of')}  ",
        f"**Schema:** `{payload.get('schema')}`  ",
        f"**N ejects:** {payload.get('n_ejects')}  ",
        f"**Taker rate:** {payload.get('taker_rate_used')} "
        f"({tier.get('pricing_tier') or '?'} · {tier.get('source')})  ",
        f"**Live fetch:** {payload.get('fetch_live')}  ",
        "",
        "## Scoreboard (fee-blind vs fee-aware)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Gross PnL sum | ${sm.get('pnl_gross_usd')} |",
        f"| RT fees sum | ${sm.get('rt_fee_usd')} |",
        f"| **Net PnL sum** | **${sm.get('pnl_net_usd')}** |",
        f"| Fee-blind green | {sb.get('fee_blind_green_n')} "
        f"(WR {sb.get('fee_blind_wr')}) |",
        f"| Fee-aware green | {sb.get('fee_aware_green_n')} "
        f"(WR {sb.get('fee_aware_wr')}) |",
        f"| Gross-green → net-red | {sb.get('gross_green_net_red_n')} |",
        f"| Sell fee exchange truth | {sb.get('sell_fee_exchange_truth_n')} |",
        f"| Entry fee exchange truth | {sb.get('entry_fee_exchange_truth_n')} |",
        "",
        f"**Product rule:** {payload.get('product_rule')}",
        "",
        "## Cohort",
        "",
        "| ts | pair | gross | RT fee | net | wiped? | sell_src | entry_src |",
        "|----|------|-------|--------|-----|--------|----------|-----------|",
    ]
    for r in payload.get("cohort") or []:
        ts = str(r.get("timestamp") or "")[:19]
        wiped = "YES" if r.get("gross_green_net_red") else ""
        lines.append(
            f"| {ts} | {r.get('pair')} | {r.get('pnl_gross_usd')} | "
            f"{r.get('rt_fee_usd')} | {r.get('pnl_net_usd')} | {wiped} | "
            f"{r.get('sell_fee_source')} | {r.get('entry_fee_source')} |"
        )
    lines.extend(["", "## Notes", ""])
    for n in payload.get("notes") or []:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def write_audit(payload: Dict[str, Any]) -> Dict[str, str]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    md = render_markdown(payload)
    LATEST_MD.write_text(md, encoding="utf-8")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated = REPORT_DIR / f"TRYOUT_EJECT_FEE_AUDIT_{day}.md"
    dated.write_text(md, encoding="utf-8")
    return {
        "json": str(LATEST_JSON),
        "md": str(LATEST_MD),
        "dated_md": str(dated),
    }


def backfill_ledger_fees(
    payload: Dict[str, Any],
    *,
    ledger_path: Optional[Path] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Stamp sell/entry fees + net pnl on matching eject SELL rows.

    Matches on order_id when present, else pair+timestamp.
    """
    path = ledger_path or LEDGER_PATH
    if not path.is_file():
        return {"ok": False, "error": "no_ledger"}
    by_oid = {
        str(r.get("order_id")): r
        for r in (payload.get("cohort") or [])
        if r.get("order_id")
    }
    lines = path.read_text(encoding="utf-8").splitlines()
    out_lines: List[str] = []
    n_touch = 0
    for line in lines:
        if not line.strip():
            out_lines.append(line)
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out_lines.append(line)
            continue
        if not isinstance(row, dict) or not _is_eject_sell(row):
            out_lines.append(line)
            continue
        oid = str(row.get("order_id") or "")
        hit = by_oid.get(oid) if oid else None
        if hit is None:
            out_lines.append(json.dumps(row, default=str))
            continue
        # Preserve gross if not set
        if row.get("pnl_gross") in (None, "") and hit.get("pnl_gross_usd") is not None:
            row["pnl_gross"] = hit["pnl_gross_usd"]
        if hit.get("sell_fee_usd") is not None:
            row["sell_fee_usd"] = hit["sell_fee_usd"]
            row["fee_usd"] = hit["sell_fee_usd"]  # sell-side for stamp_sell_pnl
        if hit.get("entry_fee_usd") is not None:
            row["entry_fee_usd"] = hit["entry_fee_usd"]
        if hit.get("rt_fee_usd") is not None:
            row["rt_fee_usd"] = hit["rt_fee_usd"]
            row["fee_usd_applied"] = hit["rt_fee_usd"]
        if hit.get("pnl_net_usd") is not None:
            row["pnl"] = hit["pnl_net_usd"]
            row["pnl_usd"] = hit["pnl_net_usd"]
            row["realized_pnl"] = hit["pnl_net_usd"]
            n_entry = _f(hit.get("notional_entry_usd"))
            if n_entry > 0:
                row["pnl_pct"] = round(100.0 * float(hit["pnl_net_usd"]) / n_entry, 4)
        row["pnl_stamp"] = "fee_audit_net_rt"
        row["fee_audit_at"] = _utc_iso()
        row["fee_audit_sell_src"] = hit.get("sell_fee_source")
        row["fee_audit_entry_src"] = hit.get("entry_fee_source")
        row["gross_green_net_red"] = bool(hit.get("gross_green_net_red"))
        n_touch += 1
        out_lines.append(json.dumps(row, default=str))

    result: Dict[str, Any] = {
        "ok": True,
        "dry_run": bool(dry_run),
        "n_touched": n_touch,
        "path": str(path),
    }
    if dry_run:
        return result
    bak = path.with_suffix(path.suffix + f".bak_fee_audit_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    shutil.copy2(path, bak)
    path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    result["backup"] = str(bak)
    return result


def run_audit(
    *,
    fetch_live: bool = True,
    backfill: bool = False,
    dry_run_backfill: bool = True,
    lookback_days: Optional[float] = None,
    exchange: Any = None,
) -> Dict[str, Any]:
    own_ex = False
    ex = exchange
    if fetch_live and ex is None:
        try:
            from phase6.core.exchange_client import CoinbaseExchangeClient

            ex = CoinbaseExchangeClient(mode="live")
            own_ex = True
        except Exception as e:
            logger.warning("fee audit: no live exchange (%s) — estimate path", e)
            fetch_live = False
            ex = None
    try:
        payload = audit_eject_cohort(
            lookback_days=lookback_days,
            exchange=ex,
            fetch_live=fetch_live,
        )
        paths = write_audit(payload)
        payload["written"] = paths
        if backfill:
            payload["backfill"] = backfill_ledger_fees(
                payload, dry_run=dry_run_backfill
            )
        return payload
    finally:
        if own_ex and ex is not None and hasattr(ex, "close"):
            try:
                ex.close()
            except Exception:
                pass
