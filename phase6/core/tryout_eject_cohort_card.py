#!/usr/bin/env python3
"""E-EJECT-COHORT-CARD — measure-only eject funnel scorecard.

Per scale-window eject shell:
  hold_h · phase · structure_ok · paper/live scaled · kindling block · PnL/fee

Headline: % of eject shells that ever cleared live_signal kindling before eject.

No knobs. No orders. Honesty: thin N → no edge claim.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from phase6.core.paths import PROJECT_ROOT, STATE_DIR

logger = logging.getLogger(__name__)

SCHEMA = "tryout_eject_cohort_card_v1"
EXPERIMENT_ID = "E-EJECT-COHORT-CARD"
LEDGER_PATH = PROJECT_ROOT / "trades" / "phase6_trades.jsonl"
GHOSTS_PATH = STATE_DIR / "tryout_open_lot_ghosts.jsonl"
SW_CRUMBS_PATH = STATE_DIR / "tryout_scale_window_crumbs.jsonl"
SHADOW_CRUMBS_PATH = STATE_DIR / "tryout_scale_up_shadow_crumbs.jsonl"
LIVE_CRUMBS_PATH = STATE_DIR / "tryout_scale_up_live_crumbs.jsonl"
OPEN_LOTS_PATH = STATE_DIR / "tryout_scale_up_open_lots.json"
LATEST_JSON = STATE_DIR / "tryout_eject_cohort_weekly.json"
LATEST_MD = PROJECT_ROOT / "reports" / "TRYOUT_EJECT_COHORT_CARD_LATEST.md"
REPORT_DIR = PROJECT_ROOT / "reports"

EJECT_REASON_TOKENS = ("tryout_scale_window_eject", "scale_window_eject")
LIVE_SCALE_BUY_TOKENS = (
    "tryout_scale_up",
    "scale_up_mid_flight",
    "kindling",
    "tryout_scale_up_mid_flight",
    "tryout_scale_up_live",
)


def _utc_iso(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _f(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _norm_pair(p: str) -> str:
    s = str(p or "").strip().upper().replace("_", "-")
    if not s:
        return ""
    if "-" not in s:
        s = f"{s}-USD"
    return s


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


def _is_eject_sell(row: Mapping[str, Any]) -> bool:
    side = str(row.get("side") or row.get("action") or "").upper()
    if side not in ("SELL", "SELL_SHORT", "EXIT"):
        return False
    rsn = str(row.get("reason") or row.get("exit_reason") or "").lower()
    return any(t in rsn for t in EJECT_REASON_TOKENS)


def _is_buy(row: Mapping[str, Any]) -> bool:
    return str(row.get("side") or row.get("action") or "").upper() in (
        "BUY",
        "BUY_LONG",
    )


def _is_live_scale_buy(row: Mapping[str, Any]) -> bool:
    if not _is_buy(row):
        return False
    rsn = str(row.get("reason") or row.get("exit_reason") or row.get("note") or "").lower()
    return any(t in rsn for t in LIVE_SCALE_BUY_TOKENS)


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
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
    except Exception as e:
        logger.warning("read_jsonl %s: %s", path, e)
    return out


def _load_ledger_rows(path: Path) -> List[Dict[str, Any]]:
    return _read_jsonl(path)


def _find_entry_buy(
    ledger: Sequence[Mapping[str, Any]],
    *,
    pair: str,
    exit_ts: Optional[datetime],
    entry_order_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    pn = _norm_pair(pair)
    if entry_order_id:
        for row in ledger:
            if str(row.get("order_id") or "") == str(entry_order_id) and _is_buy(row):
                return dict(row)
    cands: List[Tuple[datetime, Dict[str, Any]]] = []
    for row in ledger:
        if _norm_pair(str(row.get("pair") or row.get("product_id") or "")) != pn:
            continue
        if not _is_buy(row):
            continue
        # Prefer tryout-tagged / limit-first / seat buys over core rebalance when possible
        bts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if exit_ts and bts and bts > exit_ts:
            continue
        if bts is None:
            continue
        cands.append((bts, dict(row)))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    # Prefer last buy before exit that looks like tryout/seat
    for bts, row in reversed(cands):
        rsn = str(row.get("reason") or "").lower()
        if any(
            t in rsn
            for t in (
                "limit_first",
                "tryout",
                "rsi_event",
                "seat",
                "shell",
            )
        ):
            return row
    return cands[-1][1]


def _had_live_scale_before_eject(
    ledger: Sequence[Mapping[str, Any]],
    *,
    pair: str,
    entry_ts: Optional[datetime],
    exit_ts: Optional[datetime],
) -> Dict[str, Any]:
    pn = _norm_pair(pair)
    hits: List[Dict[str, Any]] = []
    for row in ledger:
        if _norm_pair(str(row.get("pair") or row.get("product_id") or "")) != pn:
            continue
        if not _is_live_scale_buy(row):
            continue
        bts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if entry_ts and bts and bts < entry_ts - timedelta(minutes=1):
            continue
        if exit_ts and bts and bts > exit_ts + timedelta(minutes=1):
            continue
        hits.append(
            {
                "ts": row.get("timestamp") or row.get("ts"),
                "order_id": row.get("order_id"),
                "reason": row.get("reason"),
                "notional": _f(row.get("notional_usd") or row.get("usd") or row.get("size_usd")),
            }
        )
    return {
        "cleared_live_kindling": bool(hits),
        "n_live_scale_buys": len(hits),
        "live_scale_buys": hits[-3:],
    }


def _match_ghost_lot(
    ghosts: Sequence[Mapping[str, Any]],
    *,
    pair: str,
    entry_ts: Optional[datetime],
    exit_ts: Optional[datetime],
) -> Optional[Dict[str, Any]]:
    pn = _norm_pair(pair)
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for g in ghosts:
        if "oid-test" in str(g).lower() or str(g.get("pair") or "").endswith("-TEST"):
            continue
        if _norm_pair(str(g.get("pair") or "")) != pn:
            continue
        lot = dict(g.get("lot") or {})
        if not lot:
            continue
        # skip pure unit-test ghosts
        if str(lot.get("seat_order_id") or "").startswith("oid-test"):
            continue
        le = _parse_ts(lot.get("entry_ts") or lot.get("registered_at"))
        # score by entry proximity
        score = 0.0
        if entry_ts and le:
            score = -abs((le - entry_ts).total_seconds())
        elif exit_ts and le and le <= exit_ts:
            score = -abs((exit_ts - le).total_seconds())
        else:
            score = -1e18
        lot_out = dict(lot)
        lot_out["_ghost_why"] = g.get("why")
        lot_out["_purged_at"] = g.get("purged_at")
        scored.append((score, lot_out))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best = scored[0]
    if best_score <= -1e17:
        return best  # last resort
    return best


def _shadow_near_exit(
    crumbs: Sequence[Mapping[str, Any]],
    *,
    pair: str,
    exit_ts: Optional[datetime],
    window_h: float = 36.0,
) -> Optional[Dict[str, Any]]:
    pn = _norm_pair(pair)
    if exit_ts is None:
        return None
    cut = exit_ts - timedelta(hours=window_h)
    cands: List[Tuple[datetime, Dict[str, Any]]] = []
    for row in crumbs:
        if _norm_pair(str(row.get("pair") or "")) != pn:
            continue
        ts = _parse_ts(row.get("ts") or row.get("timestamp"))
        if ts is None or ts > exit_ts + timedelta(minutes=5):
            continue
        if ts < cut:
            continue
        cands.append((ts, dict(row)))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    return cands[-1][1]


def _kindling_block_reason(
    *,
    live_scaled: bool,
    paper_scaled: bool,
    phase: Any,
    structure_ok: Any,
    hold_h: Optional[float],
    shadow_row: Optional[Mapping[str, Any]],
    live_scale_info: Mapping[str, Any],
) -> str:
    if live_scaled or live_scale_info.get("cleared_live_kindling"):
        return "cleared_live_kindling"
    reasons: List[str] = []
    if shadow_row:
        st = str(shadow_row.get("status") or shadow_row.get("kind") or "")
        rs = shadow_row.get("reasons") or []
        if st == "would_scale" or shadow_row.get("kind") == "would_scale":
            reasons.append("paper_would_scale_not_live")
        if isinstance(rs, list) and rs:
            reasons.extend([str(x) for x in rs[:4]])
        elif rs:
            reasons.append(str(rs)[:80])
    if paper_scaled and not live_scaled:
        reasons.append("paper_scaled_no_live_add")
    try:
        ph = int(phase) if phase is not None else None
    except (TypeError, ValueError):
        ph = None
    if ph is not None and ph >= 3:
        reasons.append(f"phase_{ph}_late_for_live_signal")
    if structure_ok is False:
        reasons.append("structure_break")
    if structure_ok is None:
        reasons.append("structure_unknown")
    if hold_h is not None and hold_h < 2.0:
        reasons.append(f"hold_{hold_h:.1f}h_under_min")
    if not reasons:
        reasons.append("never_cleared_live_signal_bar")
    # de-dupe preserve order
    seen = set()
    out: List[str] = []
    for r in reasons:
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    return "|".join(out)[:220]


def build_cohort_card(
    *,
    lookback_days: Optional[float] = 14.0,
    ledger_path: Optional[Path] = None,
    fee_payload: Optional[Mapping[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build the weekly eject cohort card (measure-only)."""
    now = now or datetime.now(timezone.utc)
    path = ledger_path or LEDGER_PATH
    ledger = _load_ledger_rows(path)
    cut = None
    if lookback_days is not None:
        cut = now - timedelta(days=float(lookback_days))

    fee_by_oid: Dict[str, Dict[str, Any]] = {}
    fee_by_pair_ts: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if fee_payload is None:
        try:
            from phase6.core.tryout_eject_fee_audit import audit_eject_cohort

            fee_payload = audit_eject_cohort(
                ledger_path=path,
                lookback_days=lookback_days,
                fetch_live=False,
            )
        except Exception as e:
            logger.warning("fee cohort join failed: %s", e)
            fee_payload = {}
    for r in (fee_payload or {}).get("cohort") or []:
        if not isinstance(r, dict):
            continue
        oid = str(r.get("order_id") or "")
        if oid:
            fee_by_oid[oid] = r
        pk = (_norm_pair(str(r.get("pair") or "")), str(r.get("timestamp") or "")[:19])
        fee_by_pair_ts[pk] = r

    ghosts = _read_jsonl(GHOSTS_PATH)
    shadow_crumbs = _read_jsonl(SHADOW_CRUMBS_PATH)
    # open lots (current) rarely hold closed shells; still useful meta
    open_lots: Dict[str, Any] = {}
    if OPEN_LOTS_PATH.is_file():
        try:
            blob = json.loads(OPEN_LOTS_PATH.read_text(encoding="utf-8"))
            lots = blob.get("lots") if isinstance(blob, dict) else {}
            if isinstance(lots, dict):
                open_lots = lots
        except Exception:
            pass

    ejects: List[Dict[str, Any]] = []
    for row in ledger:
        if not _is_eject_sell(row):
            continue
        ts = _parse_ts(row.get("timestamp") or row.get("ts"))
        if cut is not None and ts is not None and ts < cut:
            continue
        ejects.append(dict(row))

    rows_out: List[Dict[str, Any]] = []
    for sell in ejects:
        pair = _norm_pair(str(sell.get("pair") or sell.get("product_id") or ""))
        exit_ts = _parse_ts(sell.get("timestamp") or sell.get("ts"))
        entry_oid = sell.get("entry_order_id") or sell.get("parent_order_id")
        buy = _find_entry_buy(
            ledger,
            pair=pair,
            exit_ts=exit_ts,
            entry_order_id=str(entry_oid) if entry_oid else None,
        )
        entry_ts = _parse_ts((buy or {}).get("timestamp") or (buy or {}).get("ts"))
        hold_h = None
        if entry_ts and exit_ts:
            hold_h = round((exit_ts - entry_ts).total_seconds() / 3600.0, 3)

        ghost = _match_ghost_lot(
            ghosts, pair=pair, entry_ts=entry_ts, exit_ts=exit_ts
        )
        shadow = _shadow_near_exit(shadow_crumbs, pair=pair, exit_ts=exit_ts)

        live_scaled = bool((ghost or {}).get("live_scaled"))
        paper_scaled = bool(
            (ghost or {}).get("paper_scaled")
            or (ghost or {}).get("scaled")
            or (str((ghost or {}).get("status") or "") == "scored")
        )
        phase = (ghost or {}).get("phase")
        structure_ok = (ghost or {}).get("structure_ok")
        if phase is None and shadow is not None:
            phase = shadow.get("phase")
        if structure_ok is None and shadow is not None:
            structure_ok = shadow.get("structure_ok")
        if shadow and shadow.get("kind") == "would_scale":
            paper_scaled = True

        live_info = _had_live_scale_before_eject(
            ledger, pair=pair, entry_ts=entry_ts, exit_ts=exit_ts
        )
        if live_info.get("cleared_live_kindling"):
            live_scaled = True

        block = _kindling_block_reason(
            live_scaled=live_scaled,
            paper_scaled=paper_scaled,
            phase=phase,
            structure_ok=structure_ok,
            hold_h=hold_h,
            shadow_row=shadow,
            live_scale_info=live_info,
        )

        oid = str(sell.get("order_id") or "")
        fee = fee_by_oid.get(oid)
        if fee is None:
            fee = fee_by_pair_ts.get((pair, str(sell.get("timestamp") or "")[:19]))

        pnl_gross = None
        pnl_net = None
        rt_fee = None
        if fee:
            pnl_gross = fee.get("pnl_gross_usd")
            pnl_net = fee.get("pnl_net_usd")
            rt_fee = fee.get("rt_fee_usd")
        if pnl_gross is None:
            for k in ("pnl_gross", "pnl_gross_usd"):
                if sell.get(k) is not None:
                    pnl_gross = _f(sell.get(k))
                    break
        if pnl_net is None:
            for k in ("pnl", "pnl_usd", "realized_pnl"):
                if sell.get(k) is not None:
                    pnl_net = _f(sell.get(k))
                    break
        if rt_fee is None and sell.get("rt_fee_usd") is not None:
            rt_fee = _f(sell.get("rt_fee_usd"))

        rows_out.append(
            {
                "pair": pair,
                "exit_ts": sell.get("timestamp") or sell.get("ts"),
                "entry_ts": (buy or {}).get("timestamp") or (buy or {}).get("ts") or (ghost or {}).get("entry_ts"),
                "hold_h": hold_h,
                "phase": phase,
                "structure_ok": structure_ok,
                "paper_scaled": bool(paper_scaled),
                "live_scaled": bool(live_scaled),
                "cleared_live_kindling": bool(live_info.get("cleared_live_kindling") or live_scaled),
                "kindling_block": block,
                "entry_reason": (buy or {}).get("reason"),
                "entry_order_id": (buy or {}).get("order_id") or entry_oid,
                "exit_order_id": oid or None,
                "exit_reason": sell.get("reason") or sell.get("exit_reason"),
                "pnl_gross_usd": pnl_gross,
                "rt_fee_usd": rt_fee,
                "pnl_net_usd": pnl_net,
                "fee_blind_green": bool(fee.get("fee_blind_green")) if fee else None,
                "fee_aware_green": bool(fee.get("fee_aware_green")) if fee else None,
                "gross_green_net_red": bool(fee.get("gross_green_net_red")) if fee else None,
                "shadow_near_exit": (
                    {
                        "kind": shadow.get("kind") if shadow else None,
                        "phase": shadow.get("phase") if shadow else None,
                        "structure_ok": shadow.get("structure_ok") if shadow else None,
                        "hold_hours": shadow.get("hold_hours") if shadow else None,
                        "unrealized_r": shadow.get("unrealized_r") if shadow else None,
                        "reasons": (shadow.get("reasons") if shadow else None),
                        "ts": shadow.get("ts") if shadow else None,
                    }
                    if shadow
                    else None
                ),
                "ghost_why": (ghost or {}).get("_ghost_why"),
                "sources": {
                    "fee_joined": bool(fee),
                    "buy_joined": bool(buy),
                    "ghost_joined": bool(ghost),
                    "shadow_joined": bool(shadow),
                },
            }
        )

    rows_out.sort(key=lambda r: str(r.get("exit_ts") or ""), reverse=True)
    n = len(rows_out)
    n_cleared = sum(1 for r in rows_out if r.get("cleared_live_kindling"))
    n_paper = sum(1 for r in rows_out if r.get("paper_scaled") and not r.get("cleared_live_kindling"))
    n_struct_false = sum(1 for r in rows_out if r.get("structure_ok") is False)
    n_struct_unk = sum(1 for r in rows_out if r.get("structure_ok") is None)
    holds = [float(r["hold_h"]) for r in rows_out if r.get("hold_h") is not None]
    sum_gross = sum(_f(r.get("pnl_gross_usd")) for r in rows_out)
    sum_fee = sum(_f(r.get("rt_fee_usd")) for r in rows_out)
    sum_net = sum(_f(r.get("pnl_net_usd")) for r in rows_out)
    n_net_green = sum(
        1
        for r in rows_out
        if r.get("pnl_net_usd") is not None and _f(r.get("pnl_net_usd")) > 0
    )
    n_wiped = sum(1 for r in rows_out if r.get("gross_green_net_red"))

    # block reason tallies
    block_counts: Dict[str, int] = {}
    for r in rows_out:
        key = str(r.get("kindling_block") or "unknown").split("|")[0]
        block_counts[key] = block_counts.get(key, 0) + 1

    pct_cleared = round(n_cleared / n, 4) if n else None
    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "experiment_id": EXPERIMENT_ID,
        "as_of": _utc_iso(now),
        "lookback_days": lookback_days,
        "measure_only": True,
        "no_knobs": True,
        "edge_claim_allowed": False,
        "n_ejects": n,
        "headline": {
            "pct_cleared_live_kindling": pct_cleared,
            "n_cleared_live_kindling": n_cleared,
            "n_ejects": n,
            "plain": (
                f"{n_cleared}/{n} eject shells ever cleared live kindling "
                f"({(pct_cleared or 0)*100:.0f}%). "
                "No edge claim — measure funnel only."
                if n
                else "No scale-window ejects in window."
            ),
        },
        "scoreboard": {
            "n_ejects": n,
            "n_cleared_live_kindling": n_cleared,
            "pct_cleared_live_kindling": pct_cleared,
            "n_paper_scaled_not_live": n_paper,
            "n_structure_false": n_struct_false,
            "n_structure_unknown": n_struct_unk,
            "hold_h_mean": round(sum(holds) / len(holds), 3) if holds else None,
            "hold_h_median": (
                round(sorted(holds)[len(holds) // 2], 3) if holds else None
            ),
            "pnl_gross_usd": round(sum_gross, 6),
            "rt_fee_usd": round(sum_fee, 6),
            "pnl_net_usd": round(sum_net, 6),
            "n_fee_aware_green": n_net_green,
            "n_gross_green_net_red": n_wiped,
            "kindling_block_top": sorted(
                block_counts.items(), key=lambda kv: (-kv[1], kv[0])
            )[:8],
        },
        "rows": rows_out,
        "product_rule": (
            "Tryout shell = timed option on kindling. "
            "Headline = % ejects that cleared live_signal kindling before death. "
            "Fee-aware net only for profit language."
        ),
        "notes": [
            "cleared_live_kindling = ledger buy with tryout_scale_up/kindling reason in the lot window, or lot live_scaled.",
            "paper_scaled / would_scale is NOT live kindling clearance.",
            "phase/structure prefer ghost lot close meta, else nearest shadow crumb ≤36h before eject.",
            "Thin N: no promote / no knob advice from this card alone.",
        ],
        "paths": {
            "state": str(LATEST_JSON.relative_to(PROJECT_ROOT)),
            "report": str(LATEST_MD.relative_to(PROJECT_ROOT)),
        },
    }
    return payload


def render_markdown(payload: Mapping[str, Any]) -> str:
    sb = payload.get("scoreboard") or {}
    hd = payload.get("headline") or {}
    pct = sb.get("pct_cleared_live_kindling")
    pct_s = "—" if pct is None else f"{float(pct) * 100.0:.1f}%"
    lines = [
        f"# {payload.get('experiment_id') or EXPERIMENT_ID} — eject cohort card",
        "",
        f"**As of:** {payload.get('as_of')}  ",
        f"**Schema:** `{payload.get('schema')}`  ",
        f"**Lookback days:** {payload.get('lookback_days')}  ",
        f"**Measure-only / no knobs:** {payload.get('measure_only')} / {payload.get('no_knobs')}  ",
        f"**Edge claim:** {payload.get('edge_claim_allowed')}  ",
        "",
        "## Plain English",
        "",
        str(hd.get("plain") or "—"),
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Ejects | {sb.get('n_ejects')} |",
        f"| Cleared live kindling | {sb.get('n_cleared_live_kindling')} |",
        f"| **% cleared kindling** | **{pct_s}** |",
        f"| Paper-scaled, never live | {sb.get('n_paper_scaled_not_live')} |",
        f"| Structure false / unknown | {sb.get('n_structure_false')} / {sb.get('n_structure_unknown')} |",
        f"| Hold h mean / median | {sb.get('hold_h_mean')} / {sb.get('hold_h_median')} |",
        f"| Gross PnL | ${sb.get('pnl_gross_usd')} |",
        f"| RT fees | ${sb.get('rt_fee_usd')} |",
        f"| **Net PnL** | **${sb.get('pnl_net_usd')}** |",
        f"| Fee-aware green | {sb.get('n_fee_aware_green')} |",
        f"| Gross→net wipe | {sb.get('n_gross_green_net_red')} |",
        "",
        f"**Product rule:** {payload.get('product_rule')}",
        "",
        "## Kindling block (top)",
        "",
    ]
    tops = sb.get("kindling_block_top") or []
    if tops:
        lines.append("| block | n |")
        lines.append("|-------|---|")
        for k, v in tops:
            lines.append(f"| {k} | {v} |")
    else:
        lines.append("_none_")
    lines.extend(
        [
            "",
            "## Cohort rows",
            "",
            "| exit | pair | hold_h | phase | struct | paper | live | block | gross | fee | net |",
            "|------|------|--------|-------|--------|-------|------|-------|-------|-----|-----|",
        ]
    )
    for r in payload.get("rows") or []:
        ts = str(r.get("exit_ts") or "")[:19]
        struct = r.get("structure_ok")
        struct_s = "—" if struct is None else ("Y" if struct else "N")
        paper_s = "Y" if r.get("paper_scaled") else ""
        live_s = "Y" if r.get("live_scaled") else ""
        block_s = str(r.get("kindling_block") or "")[:40]
        lines.append(
            f"| {ts} | {r.get('pair')} | {r.get('hold_h')} | {r.get('phase')} | {struct_s} | "
            f"{paper_s} | {live_s} | {block_s} | {r.get('pnl_gross_usd')} | "
            f"{r.get('rt_fee_usd')} | {r.get('pnl_net_usd')} |"
        )
    lines.extend(["", "## Notes", ""])
    for n in payload.get("notes") or []:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def write_card(payload: Mapping[str, Any]) -> Dict[str, str]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, default=str) + "\n"
    LATEST_JSON.write_text(body, encoding="utf-8")
    md = render_markdown(payload)
    LATEST_MD.write_text(md, encoding="utf-8")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dated = REPORT_DIR / f"TRYOUT_EJECT_COHORT_CARD_{day}.md"
    dated.write_text(md, encoding="utf-8")
    return {
        "json": str(LATEST_JSON),
        "md": str(LATEST_MD),
        "dated_md": str(dated),
    }


def run_card(
    *,
    lookback_days: Optional[float] = 14.0,
    write: bool = True,
    ledger_path: Optional[Path] = None,
) -> Dict[str, Any]:
    payload = build_cohort_card(
        lookback_days=lookback_days,
        ledger_path=ledger_path,
    )
    if write:
        payload["written"] = write_card(payload)
    return payload


def snapshot_for_analyst(payload: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Compact slice for weekly analyst fact pack."""
    if payload is None:
        if LATEST_JSON.is_file():
            try:
                payload = json.loads(LATEST_JSON.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
        else:
            payload = {}
    sb = (payload or {}).get("scoreboard") or {}
    hd = (payload or {}).get("headline") or {}
    return {
        "experiment_id": (payload or {}).get("experiment_id") or EXPERIMENT_ID,
        "as_of": (payload or {}).get("as_of"),
        "n_ejects": sb.get("n_ejects") or (payload or {}).get("n_ejects"),
        "pct_cleared_live_kindling": sb.get("pct_cleared_live_kindling"),
        "n_cleared_live_kindling": sb.get("n_cleared_live_kindling"),
        "n_paper_scaled_not_live": sb.get("n_paper_scaled_not_live"),
        "hold_h_mean": sb.get("hold_h_mean"),
        "pnl_net_usd": sb.get("pnl_net_usd"),
        "rt_fee_usd": sb.get("rt_fee_usd"),
        "kindling_block_top": sb.get("kindling_block_top"),
        "plain": hd.get("plain"),
        "path": str(LATEST_JSON.relative_to(PROJECT_ROOT))
        if LATEST_JSON.is_file()
        else None,
        "edge_claim_allowed": False,
    }
