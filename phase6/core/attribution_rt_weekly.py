"""
Attribution RT weekly closed loop (PC-06).

Stamped BUY→SELL rounds with RSI+sent+exit reason+R+tax flags.
No fake backfill; no edge claim below N threshold.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT

SCHEMA = "attribution_rt_weekly_v1"
STATE_PATH = PROJECT_ROOT / "data" / "state" / "attribution_rt_weekly_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "ATTRIBUTION_RT_WEEKLY_LATEST.md"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
SIGNAL_EVENTS = PROJECT_ROOT / "data" / "state" / "trade_signal_events.jsonl"

# Below this, reports may describe coverage only — no edge claim
EDGE_CLAIM_MIN_N = 20
DEFAULT_LOOKBACK_DAYS = 7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
    except OSError:
        return []
    return out


def _parse_ts(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _norm_pair(p: str) -> str:
    return str(p or "").strip().upper().replace("_", "-")


def _pnl(row: Mapping[str, Any]) -> float:
    for k in ("pnl", "realized_pnl", "pnl_usd"):
        if row.get(k) is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return 0.0


def classify_exit_reason(row: Mapping[str, Any]) -> str:
    reason = str(
        row.get("reason") or row.get("exit_reason") or row.get("done_reason") or ""
    ).strip()
    r = reason.lower()
    if not r:
        return "blank_untagged"
    if any(k in r for k in ("stop_loss", "stop-loss", "exchange_stop", "sl_hit", "sl_")):
        return "sl_exchange"
    if "dust_sweep" in r:
        return "dust_sweep"
    if any(k in r for k in ("take_profit", "fixed_tp", "trail")):
        return "tp_profit"
    if "dual_peak" in r or "lifecycle_dual_peak" in r:
        return "dual_peak"
    if "lifecycle_extension" in r or "extension_partial" in r:
        return "lifecycle_partial"
    if "hard_exit" in r or "regime_hard_exit" in r:
        return "hard_exit"
    if "rotation" in r:
        return "rotation"
    if "operator" in r or "manual" in r or "preserve_disarm" in r:
        return "operator_manual"
    if "test_cleanup" in r or "cleanup" in r:
        return "test_cleanup"
    return "other"


def is_process_tax(bucket: str) -> bool:
    return bucket in {"sl_exchange", "dust_sweep"}


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def coverage_flags(row: Mapping[str, Any], *, side: str) -> Dict[str, bool]:
    side_u = side.upper()
    if side_u == "BUY":
        return {
            "has_entry_rsi": row.get("entry_rsi") is not None
            or (isinstance(row.get("indicators_at_trade"), dict) and row["indicators_at_trade"].get("rsi") is not None),
            "has_entry_sent": row.get("entry_sentiment") is not None
            or (
                isinstance(row.get("indicators_at_trade"), dict)
                and row["indicators_at_trade"].get("sentiment") is not None
            ),
            "has_bag_id": bool(row.get("bag_id")),
            "has_signal_stamp": row.get("signal_stamp_schema") is not None
            or row.get("schema_version") is not None,
        }
    return {
        "has_exit_rsi": row.get("exit_rsi") is not None,
        "has_exit_sent": row.get("exit_sentiment") is not None,
        "has_entry_rsi": row.get("entry_rsi") is not None,
        "has_entry_sent": row.get("entry_sentiment") is not None,
        "has_exit_reason": bool(row.get("reason") or row.get("exit_reason")),
        "has_pnl": row.get("pnl") is not None or row.get("realized_pnl") is not None or row.get("pnl_usd") is not None,
        "has_bag_id": bool(row.get("bag_id")),
        "has_signal_stamp": row.get("signal_stamp_schema") is not None
        or row.get("schema_version") is not None,
    }


def index_buys(rows: Sequence[Mapping[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    by_pair: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        if str(r.get("side") or r.get("action") or "").upper() != "BUY":
            continue
        pair = _norm_pair(str(r.get("pair") or r.get("product_id") or ""))
        if not pair:
            continue
        by_pair.setdefault(pair, []).append(dict(r))
    for p in by_pair:
        by_pair[p].sort(key=lambda x: str(x.get("timestamp") or x.get("ts") or ""))
    return by_pair


def match_entry_lot(
    sell: Mapping[str, Any],
    buys_by_pair: Mapping[str, List[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    pair = _norm_pair(str(sell.get("pair") or sell.get("product_id") or ""))
    buys = list(buys_by_pair.get(pair) or [])
    if not buys:
        return None
    entry_oid = str(sell.get("entry_order_id") or sell.get("parent_sl_order_id") or "")
    if entry_oid:
        for b in reversed(buys):
            if str(b.get("order_id") or "") == entry_oid:
                return b
    bag = str(sell.get("bag_id") or "")
    if bag:
        for b in reversed(buys):
            if str(b.get("bag_id") or "") == bag:
                return b
    sell_ts = _parse_ts(sell.get("timestamp") or sell.get("ts"))
    # last buy before sell
    prior = []
    for b in buys:
        bt = _parse_ts(b.get("timestamp") or b.get("ts"))
        if sell_ts and bt and bt <= sell_ts:
            prior.append(b)
        elif sell_ts is None:
            prior.append(b)
    return prior[-1] if prior else buys[-1]


def build_rt_rows(
    ledger: Sequence[Mapping[str, Any]],
    *,
    since: datetime,
    until: Optional[datetime] = None,
    signal_by_oid: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    until = until or _utc_now()
    signal_by_oid = signal_by_oid or {}
    buys_by = index_buys(ledger)
    rts: List[Dict[str, Any]] = []

    for sell in ledger:
        if str(sell.get("side") or sell.get("action") or "").upper() != "SELL":
            continue
        ts = _parse_ts(sell.get("timestamp") or sell.get("ts"))
        if ts is None or ts < since or ts > until:
            continue
        pair = _norm_pair(str(sell.get("pair") or ""))
        if not pair or pair.startswith("USDT") or pair.startswith("USDC"):
            # skip stable rotations from RT edge table (still counted in coverage dump)
            pass
        buy = match_entry_lot(sell, buys_by)
        bucket = classify_exit_reason(sell)
        pnl = _pnl(sell)

        entry_rsi = _f(sell.get("entry_rsi"))
        entry_sent = _f(sell.get("entry_sentiment"))
        exit_rsi = _f(sell.get("exit_rsi"))
        exit_sent = _f(sell.get("exit_sentiment"))
        bag_id = sell.get("bag_id") or (buy or {}).get("bag_id")

        # enrich from matched buy / signal events
        if buy:
            if entry_rsi is None:
                entry_rsi = _f(buy.get("entry_rsi"))
                if entry_rsi is None and isinstance(buy.get("indicators_at_trade"), dict):
                    entry_rsi = _f(buy["indicators_at_trade"].get("rsi"))
            if entry_sent is None:
                entry_sent = _f(buy.get("entry_sentiment"))
                if entry_sent is None and isinstance(buy.get("indicators_at_trade"), dict):
                    entry_sent = _f(buy["indicators_at_trade"].get("sentiment"))
            if not bag_id:
                bag_id = buy.get("bag_id")
            oid = str(buy.get("order_id") or "")
            if oid and oid in signal_by_oid:
                sig = signal_by_oid[oid]
                if entry_rsi is None:
                    entry_rsi = _f(sig.get("entry_rsi"))
                if entry_sent is None:
                    entry_sent = _f(sig.get("entry_sentiment"))

        sell_oid = str(sell.get("order_id") or "")
        if sell_oid and sell_oid in signal_by_oid:
            sig = signal_by_oid[sell_oid]
            if exit_rsi is None:
                exit_rsi = _f(sig.get("exit_rsi"))
            if exit_sent is None:
                exit_sent = _f(sig.get("exit_sentiment"))
            if entry_rsi is None:
                entry_rsi = _f(sig.get("entry_rsi"))
            if entry_sent is None:
                entry_sent = _f(sig.get("entry_sentiment"))

        cov_sell = coverage_flags(sell, side="SELL")
        # recompute stamp completeness after enrich
        stamped = {
            "entry_rsi": entry_rsi is not None,
            "entry_sent": entry_sent is not None,
            "exit_rsi": exit_rsi is not None,
            "exit_sent": exit_sent is not None,
            "exit_reason": bool(sell.get("reason") or sell.get("exit_reason")),
            "pnl": sell.get("pnl") is not None
            or sell.get("realized_pnl") is not None
            or sell.get("pnl_usd") is not None,
            "bag_id": bool(bag_id),
        }
        full_core = all(
            [
                stamped["entry_rsi"],
                stamped["entry_sent"],
                stamped["exit_reason"],
                stamped["pnl"],
            ]
        )

        # skip pure stable noise for primary table but keep flag
        is_stable = pair.endswith("-USD") and pair.split("-")[0] in {
            "USDT",
            "USDC",
            "DAI",
            "USD",
        } or pair in {"USDT-USDC", "USDC-USDT"}

        rts.append(
            {
                "pair": pair,
                "sell_ts": ts.isoformat() if ts else None,
                "exit_reason_raw": sell.get("reason") or sell.get("exit_reason"),
                "exit_bucket": bucket,
                "process_tax": is_process_tax(bucket),
                "pnl": round(pnl, 4),
                "entry_rsi": entry_rsi,
                "entry_sentiment": entry_sent,
                "exit_rsi": exit_rsi,
                "exit_sentiment": exit_sent,
                "bag_id": bag_id,
                "entry_order_id": (buy or {}).get("order_id") or sell.get("entry_order_id"),
                "sell_order_id": sell.get("order_id"),
                "stamped": stamped,
                "full_core_stamp": full_core,
                "is_stable_rotation": is_stable or pair.startswith("USDT") or "USDC" in pair.split("-")[0:1],
                "cov_sell_raw": cov_sell,
            }
        )
    return rts


def summarize_rts(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    primary = [r for r in rows if not r.get("is_stable_rotation")]
    n = len(primary)
    n_full = sum(1 for r in primary if r.get("full_core_stamp"))
    tax = [r for r in primary if r.get("process_tax")]
    nontax = [r for r in primary if not r.get("process_tax")]
    buckets = Counter(str(r.get("exit_bucket")) for r in primary)

    def bank(rs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        pnls = [float(r.get("pnl") or 0) for r in rs]
        return {
            "n": len(rs),
            "pnl_sum": round(sum(pnls), 4),
            "pnl_mean": round(sum(pnls) / len(pnls), 4) if pnls else None,
        }

    return {
        "n_rt_primary": n,
        "n_rt_all_incl_stable": len(rows),
        "n_full_core_stamp": n_full,
        "stamp_coverage_rate": (n_full / n) if n else None,
        "by_bucket": dict(buckets),
        "process_tax_bank": bank(tax),
        "non_tax_bank": bank(nontax),
        "edge_claim_min_n": EDGE_CLAIM_MIN_N,
        "edge_claim_allowed": n >= EDGE_CLAIM_MIN_N and n_full >= max(5, EDGE_CLAIM_MIN_N // 4),
        "edge_claim_note": (
            f"No edge claim: need n_rt_primary≥{EDGE_CLAIM_MIN_N} with solid stamps"
            if n < EDGE_CLAIM_MIN_N
            else "N bar met — still no vibe promote; cite stamped set only"
        ),
    }


def render_markdown(payload: Mapping[str, Any]) -> str:
    s = payload.get("summary") or {}
    lines = [
        "# Attribution RT weekly (PC-06)",
        "",
        f"**As of:** {payload.get('as_of')}",
        f"**Window:** {payload.get('window_start')} → {payload.get('window_end')} ({payload.get('lookback_days')}d)",
        f"**Schema:** `{payload.get('schema')}`",
        "",
        "## Coverage",
        "",
        f"- Primary RTs (ex stable): **{s.get('n_rt_primary')}**",
        f"- Full core stamp (entry RSI+sent, exit reason, pnl): **{s.get('n_full_core_stamp')}**",
        f"- Stamp coverage: **{s.get('stamp_coverage_rate') if s.get('stamp_coverage_rate') is not None else 'n/a'}**",
        f"- Edge claim allowed: **{s.get('edge_claim_allowed')}** — {s.get('edge_claim_note')}",
        "",
        "## Banks",
        "",
        f"- Process tax (SL/dust): n={((s.get('process_tax_bank') or {}).get('n'))} sum=${((s.get('process_tax_bank') or {}).get('pnl_sum'))}",
        f"- Non-tax exits: n={((s.get('non_tax_bank') or {}).get('n'))} sum=${((s.get('non_tax_bank') or {}).get('pnl_sum'))}",
        f"- Buckets: `{s.get('by_bucket')}`",
        "",
        "## RT table (primary)",
        "",
        "| pair | sell_ts | bucket | tax | pnl | eRSI | eSent | xRSI | bag | core |",
        "|------|---------|--------|-----|-----|------|-------|------|-----|------|",
    ]
    for r in payload.get("rows_primary") or []:
        lines.append(
            "| {pair} | {ts} | {bucket} | {tax} | {pnl} | {ersi} | {es} | {xrsi} | {bag} | {core} |".format(
                pair=r.get("pair"),
                ts=str(r.get("sell_ts") or "")[:19],
                bucket=r.get("exit_bucket"),
                tax="Y" if r.get("process_tax") else "",
                pnl=r.get("pnl"),
                ersi=r.get("entry_rsi") if r.get("entry_rsi") is not None else "—",
                es=r.get("entry_sentiment") if r.get("entry_sentiment") is not None else "—",
                xrsi=r.get("exit_rsi") if r.get("exit_rsi") is not None else "—",
                bag=("Y" if r.get("bag_id") else ""),
                core=("Y" if r.get("full_core_stamp") else ""),
            )
        )
    if not (payload.get("rows_primary") or []):
        lines.append("| — | — | — | — | — | — | — | — | — | — |")
    lines.extend(
        [
            "",
            "## Rules",
            "",
            "- OPT / month_path may cite **stamped set only**.",
            "- No fake backfill of RSI/sent.",
            f"- Edge talk blocked when n < {EDGE_CLAIM_MIN_N}.",
            "",
            f"State: `{STATE_PATH.relative_to(PROJECT_ROOT)}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(payload: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(payload), encoding="utf-8")


def build_attribution_rt_weekly(
    *,
    write: bool = True,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ledger_path: Path = LEDGER_PATH,
    signal_path: Path = SIGNAL_EVENTS,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or _utc_now()
    since = now - timedelta(days=lookback_days)
    ledger = _read_jsonl(ledger_path)
    signals = _read_jsonl(signal_path)
    sig_by_oid: Dict[str, Dict[str, Any]] = {}
    for s in signals:
        oid = str(s.get("order_id") or "")
        if oid:
            sig_by_oid[oid] = s

    # coverage audit on recent ledger legs in window
    buys_w = sells_w = 0
    buy_stamp = sell_stamp = 0
    for r in ledger:
        ts = _parse_ts(r.get("timestamp") or r.get("ts"))
        if ts is None or ts < since or ts > now:
            continue
        side = str(r.get("side") or "").upper()
        if side == "BUY":
            buys_w += 1
            cf = coverage_flags(r, side="BUY")
            if cf.get("has_entry_rsi") and cf.get("has_entry_sent"):
                buy_stamp += 1
        elif side == "SELL":
            sells_w += 1
            cf = coverage_flags(r, side="SELL")
            if cf.get("has_exit_reason") and cf.get("has_pnl"):
                sell_stamp += 1

    rts = build_rt_rows(ledger, since=since, until=now, signal_by_oid=sig_by_oid)
    summary = summarize_rts(rts)
    primary = [r for r in rts if not r.get("is_stable_rotation")]
    # trim heavy nested for state size
    rows_out = []
    for r in primary[:80]:
        rows_out.append({k: v for k, v in r.items() if k != "cov_sell_raw"})

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "lookback_days": lookback_days,
        "window_start": since.isoformat(),
        "window_end": now.isoformat(),
        "coverage_audit": {
            "buys_in_window": buys_w,
            "sells_in_window": sells_w,
            "buys_with_entry_rsi_sent": buy_stamp,
            "sells_with_reason_pnl": sell_stamp,
            "signal_events_total": len(signals),
            "note": "No fake backfill — missing stamps stay missing",
        },
        "summary": summary,
        "rows_primary": rows_out,
        "measure_only": True,
        "no_edge_from_thin_n": True,
    }
    if write:
        write_artifacts(payload)
    return payload
