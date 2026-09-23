#!/usr/bin/env python3
"""Break-even one-pager vs $150/mo take-home bar.

Measure-only. No knobs, no orders, no auto-promote.
Honest N tags — thin samples get no edge claim.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core.attribution_rt_weekly import build_attribution_rt_weekly
from phase6.core.paths import PROJECT_ROOT, STATE_DIR

try:
    from zoneinfo import ZoneInfo

    PT = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover
    PT = timezone.utc

SCHEMA = "break_even_one_pager_v1"
STATE_PATH = STATE_DIR / "break_even_one_pager_latest.json"
REPORT_PATH = PROJECT_ROOT / "reports" / "BREAK_EVEN_ONE_PAGER_LATEST.md"

# Operator bar (Brad 2026-09-23): need ≥ $150/mo take-home to break even.
DEFAULT_BE_USD_MO = 150.0
# Standing cost proxy until billing SSOT is wired (operator estimate).
DEFAULT_X_USD_PER_WEEK = 25.0
# Anchor for "this week" wait experiment (LINK fill day).
DEFAULT_WEEK_START_PT = "2026-09-23"


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except Exception:
        return str(path)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _pt_now(now: Optional[datetime] = None) -> datetime:
    now = now or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(PT)


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _portfolio_slice() -> Dict[str, Any]:
    live = _load_json(STATE_DIR / "phase6_live_state.json")
    bals_raw = live.get("balances")
    bals: Dict[str, Any] = bals_raw if isinstance(bals_raw, dict) else {}
    cash = 0.0
    for k in ("USD", "USDC", "USDT"):
        cell = bals.get(k)
        if isinstance(cell, dict):
            cash += _f(cell.get("available") if cell.get("available") is not None else cell.get("balance"))
        else:
            cash += _f(cell)
    # Prefer nested total if present
    tot = live.get("total_portfolio_value") or live.get("portfolio_value")
    if tot is None and isinstance(live.get("summary"), dict):
        tot = live["summary"].get("total_value")
    holdings = 0.0
    pos = live.get("trading_positions") or live.get("positions") or []
    n_pos = 0
    if isinstance(pos, list):
        for p in pos:
            if not isinstance(p, dict):
                continue
            pair = str(p.get("pair") or p.get("product_id") or "")
            if "USD" in pair and pair.split("-")[0] in ("USD", "USDC", "USDT"):
                continue
            mv = p.get("market_value") or p.get("value") or p.get("notional")
            if mv is None:
                try:
                    mv = _f(p.get("quantity") or p.get("size")) * _f(p.get("price") or p.get("mark") or p.get("current_price"))
                except Exception:
                    mv = 0.0
            holdings += _f(mv)
            if _f(mv) > 1.0:
                n_pos += 1
    total = _f(tot) if tot is not None else (cash + holdings)
    return {
        "total_usd": round(total, 2),
        "cash_usd": round(cash, 2) if cash else None,
        "holdings_usd": round(holdings, 2),
        "n_risk_positions": n_pos,
        "source": "phase6_live_state.json",
    }


def _fee_slice() -> Dict[str, Any]:
    for name in ("fee_tier_snapshot.json", "coinbase_fee_tier_snapshot.json", "fee_tier_latest.json"):
        p = STATE_DIR / name
        d = _load_json(p)
        if not d:
            continue
        maker = d.get("maker_rate") or d.get("maker") or (d.get("rates") or {}).get("maker")
        taker = d.get("taker_rate") or d.get("taker") or (d.get("rates") or {}).get("taker")
        if maker is not None or taker is not None:
            return {
                "maker_pct": round(_f(maker) * (100.0 if _f(maker) < 1 else 1.0), 4)
                if _f(maker) < 1
                else round(_f(maker), 4),
                "taker_pct": round(_f(taker) * (100.0 if _f(taker) < 1 else 1.0), 4)
                if _f(taker) < 1
                else round(_f(taker), 4),
                "raw_maker": maker,
                "raw_taker": taker,
                "as_of": d.get("as_of") or d.get("fetched_at") or d.get("timestamp"),
                "source": name,
            }
    return {"source": None, "note": "no fee snapshot on disk"}


def _x_cost_slice(
    *,
    week_start_pt: str,
    now_pt: datetime,
    x_usd_per_week: float,
) -> Dict[str, Any]:
    """Pair-query counts are honest activity; $ uses operator weekly estimate until billing SSOT."""
    budget = _load_json(STATE_DIR / "x_query_budget.json")
    day = str(budget.get("day_pt") or "")
    today_q = int(budget.get("pair_queries") or 0)
    rsi_q = int(budget.get("rsi_pair_queries") or 0)
    rebal_q = int(budget.get("rebal_pair_queries") or 0)

    # Probe event log — count paid-ish events in window if present
    probe_n = 0
    probe_path = STATE_DIR / "rsi_event_x_probe_events.jsonl"
    ws = _parse_iso(week_start_pt + "T00:00:00-07:00") or _parse_iso(week_start_pt + "T07:00:00+00:00")
    if probe_path.exists() and ws is not None:
        try:
            for line in probe_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                ts = _parse_ts_loose(ev.get("ts") or ev.get("timestamp"))
                if ts is None or ts < ws.astimezone(timezone.utc):
                    continue
                if ts > now_pt.astimezone(timezone.utc):
                    continue
                # count only events that look like paid pull
                if ev.get("paid") is False:
                    continue
                probe_n += 1
        except Exception:
            probe_n = 0

    days_elapsed = max(1, (now_pt.date() - datetime.fromisoformat(week_start_pt).date()).days + 1)
    # 2×/day primary is schedule cost; pair-queries are incremental probe cost proxy
    est_week_frac = min(1.0, days_elapsed / 7.0)
    est_x_usd_to_date = round(x_usd_per_week * est_week_frac, 2)
    est_x_usd_mo = round(x_usd_per_week * (52.0 / 12.0), 2)

    return {
        "budget_day_pt": day or None,
        "pair_queries_today": today_q,
        "rsi_pair_queries_today": rsi_q,
        "rebal_pair_queries_today": rebal_q,
        "probe_events_in_week_window": probe_n,
        "x_usd_per_week_assumption": x_usd_per_week,
        "x_usd_assumption_note": "operator estimate (~$25/wk) until X billing SSOT; not invoice-read",
        "days_elapsed_in_week": days_elapsed,
        "est_x_usd_to_date": est_x_usd_to_date,
        "est_x_usd_per_month": est_x_usd_mo,
        "primary_schedule": "2x/day 09:00+21:00 PT (phase6-x-sentiment-live-2x)",
    }


def _parse_ts_loose(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
        except Exception:
            return None
    return _parse_iso(str(v))


def _regime_slice() -> Dict[str, Any]:
    for name in ("regime_cash_status.json", "regime_climate_weather_latest.json"):
        d = _load_json(STATE_DIR / name)
        if not d:
            continue
        return {
            "regime": d.get("regime") or d.get("climate") or d.get("resolved_regime"),
            "strategy": d.get("strategy") or d.get("cash_strategy") or d.get("deploy_strategy"),
            "cap_usd": d.get("cap_usd") or d.get("tryout_cap_usd") or d.get("capital_cap"),
            "allow_new_buys": d.get("allow_new_buys"),
            "source": name,
            "as_of": d.get("as_of") or d.get("updated_at"),
        }
    return {"source": None}


def build_break_even_one_pager(
    *,
    write: bool = True,
    lookback_days: Optional[int] = None,
    week_start_pt: str = DEFAULT_WEEK_START_PT,
    be_usd_mo: float = DEFAULT_BE_USD_MO,
    x_usd_per_week: float = DEFAULT_X_USD_PER_WEEK,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = now or _utc_now()
    now_pt = _pt_now(now)

    # Window: from week_start PT through now (or explicit lookback)
    ws_local = datetime.fromisoformat(week_start_pt).replace(tzinfo=PT)
    if lookback_days is not None:
        since = now - timedelta(days=int(lookback_days))
        lb = int(lookback_days)
    else:
        since = ws_local.astimezone(timezone.utc)
        lb = max(1, int((now - since).total_seconds() // 86400) + 1)

    attr = build_attribution_rt_weekly(write=False, lookback_days=lb, now=now)
    # Re-stamp window to match our week experiment when not using free lookback override
    if lookback_days is None:
        # Filter primary rows to week_start..now if timestamps present
        rows = list(attr.get("rows_primary") or [])
        kept: List[Dict[str, Any]] = []
        for r in rows:
            ts = _parse_ts_loose(r.get("exit_ts") or r.get("sell_ts") or r.get("timestamp"))
            if ts is None:
                kept.append(r)
                continue
            if ts >= since and ts <= now:
                kept.append(r)
        if kept or not rows:
            # rebuild summary banks from kept
            tax = [r for r in kept if r.get("process_tax")]
            nontax = [r for r in kept if not r.get("process_tax")]

            def bank(rs: List[Dict[str, Any]]) -> Dict[str, Any]:
                pnls = [_f(r.get("pnl_usd") if r.get("pnl_usd") is not None else r.get("pnl")) for r in rs]
                return {
                    "n": len(rs),
                    "pnl_sum": round(sum(pnls), 4),
                    "pnl_mean": round(sum(pnls) / len(pnls), 4) if pnls else 0.0,
                }

            summary = dict(attr.get("summary") or {})
            summary["n_rt_primary"] = len(kept)
            summary["process_tax_bank"] = bank(tax)
            summary["non_tax_bank"] = bank(nontax)
            summary["edge_claim_allowed"] = len(kept) >= int(summary.get("edge_claim_min_n") or 20)
            if not summary["edge_claim_allowed"]:
                summary["edge_claim_note"] = (
                    f"No edge claim: need n_rt_primary≥{summary.get('edge_claim_min_n') or 20} with solid stamps"
                )
            attr = dict(attr)
            attr["summary"] = summary
            attr["rows_primary"] = kept
            attr["window_start"] = since.isoformat()
            attr["window_end"] = now.isoformat()
            attr["lookback_days"] = lb

    s = attr.get("summary") or {}
    tax = s.get("process_tax_bank") or {}
    nontax = s.get("non_tax_bank") or {}
    gross_rt = _f(nontax.get("pnl_sum")) + _f(tax.get("pnl_sum"))
    tax_usd = _f(tax.get("pnl_sum"))
    nontax_usd = _f(nontax.get("pnl_sum"))
    n_rt = int(s.get("n_rt_primary") or 0)

    x = _x_cost_slice(week_start_pt=week_start_pt, now_pt=now_pt, x_usd_per_week=x_usd_per_week)
    port = _portfolio_slice()
    fee = _fee_slice()
    regime = _regime_slice()

    est_x_to_date = _f(x.get("est_x_usd_to_date"))
    # Net trading vs fixed X estimate (fees inside RT pnl when ledger has them)
    net_vs_x_to_date = round(gross_rt - est_x_to_date, 2)

    # Annualize-ish only as illustration with heavy N disclaimer
    days = max(1, int(x.get("days_elapsed_in_week") or lb))
    run_rate_mo = round(gross_rt * (30.0 / days), 2) if n_rt > 0 else None
    be_gap_mo = round(be_usd_mo - (run_rate_mo or 0.0), 2) if run_rate_mo is not None else None
    be_gap_after_x_mo = None
    if run_rate_mo is not None:
        be_gap_after_x_mo = round(be_usd_mo - (run_rate_mo - _f(x.get("est_x_usd_per_month"))), 2)

    verdict = "N_INSUFFICIENT"
    if n_rt < 5:
        verdict = "N_INSUFFICIENT_path_proof_only"
    elif run_rate_mo is not None and run_rate_mo - _f(x.get("est_x_usd_per_month")) >= be_usd_mo:
        verdict = "ABOVE_BE_run_rate_thin_N_not_claim"
    elif run_rate_mo is not None and run_rate_mo > 0:
        verdict = "POSITIVE_RT_below_BE_or_costs"
    else:
        verdict = "NET_RED_or_flat_vs_costs"

    payload: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "as_of_pt": now_pt.isoformat(),
        "measure_only": True,
        "no_knobs": True,
        "be_usd_mo": be_usd_mo,
        "week_start_pt": week_start_pt,
        "window_start": attr.get("window_start"),
        "window_end": attr.get("window_end"),
        "lookback_days": attr.get("lookback_days"),
        "portfolio": port,
        "regime": regime,
        "fees": fee,
        "x_cost": x,
        "rt": {
            "n_rt_primary": n_rt,
            "gross_pnl_usd": round(gross_rt, 4),
            "process_tax_usd": round(tax_usd, 4),
            "process_tax_n": int(tax.get("n") or 0),
            "non_tax_usd": round(nontax_usd, 4),
            "non_tax_n": int(nontax.get("n") or 0),
            "by_bucket": s.get("by_bucket"),
            "edge_claim_allowed": bool(s.get("edge_claim_allowed")),
            "edge_claim_note": s.get("edge_claim_note"),
            "stamp_coverage_rate": s.get("stamp_coverage_rate"),
        },
        "vs_be": {
            "net_rt_minus_est_x_to_date_usd": net_vs_x_to_date,
            "gross_run_rate_usd_mo_ILLUSTRATIVE": run_rate_mo,
            "be_gap_usd_mo_ILLUSTRATIVE": be_gap_mo,
            "be_gap_after_est_x_usd_mo_ILLUSTRATIVE": be_gap_after_x_mo,
            "verdict": verdict,
            "note": (
                "Run-rate is days-scaled illustration only — not a forecast. "
                "Thin N → no edge claim. X $ is assumption until billing SSOT."
            ),
        },
        "attribution_coverage": attr.get("coverage_audit"),
        "rows_primary_n": len(attr.get("rows_primary") or []),
    }

    if write:
        write_artifacts(payload)
    return payload


def render_markdown(payload: Dict[str, Any]) -> str:
    rt = payload.get("rt") or {}
    vs = payload.get("vs_be") or {}
    x = payload.get("x_cost") or {}
    port = payload.get("portfolio") or {}
    reg = payload.get("regime") or {}
    fee = payload.get("fees") or {}
    lines = [
        "# Break-even one-pager",
        "",
        f"**As of (PT):** `{payload.get('as_of_pt')}`",
        f"**Window:** `{payload.get('window_start')}` → `{payload.get('window_end')}` "
        f"({payload.get('lookback_days')}d) · week_start_pt=`{payload.get('week_start_pt')}`",
        f"**Bar:** ≥ **${payload.get('be_usd_mo')}/mo** take-home",
        "",
        "> Measure-only. No knobs. No edge claim from thin N.",
        "",
        "## Go / no-go vs bar",
        "",
        f"- **Verdict:** `{vs.get('verdict')}`",
        f"- **Gross RT PnL (window):** `${rt.get('gross_pnl_usd')}` · n={rt.get('n_rt_primary')}",
        f"- **Process tax:** n={rt.get('process_tax_n')} · `${rt.get('process_tax_usd')}`",
        f"- **Non-tax exits:** n={rt.get('non_tax_n')} · `${rt.get('non_tax_usd')}`",
        f"- **Est X to date:** `${x.get('est_x_usd_to_date')}` "
        f"(assumption ${x.get('x_usd_per_week_assumption')}/wk)",
        f"- **Net RT − est X (to date):** `${vs.get('net_rt_minus_est_x_to_date_usd')}`",
        f"- **Illustrative gross run-rate $/mo:** `{vs.get('gross_run_rate_usd_mo_ILLUSTRATIVE')}`",
        f"- **Illustrative gap after est X vs BE:** `{vs.get('be_gap_after_est_x_usd_mo_ILLUSTRATIVE')}`",
        f"- **Edge claim:** `{rt.get('edge_claim_allowed')}` — {rt.get('edge_claim_note')}",
        "",
        "## Book / regime",
        "",
        f"- Portfolio ~`${port.get('total_usd')}` · holdings ~`${port.get('holdings_usd')}` · "
        f"risk seats open≈{port.get('n_risk_positions')}",
        f"- Regime: `{reg.get('regime')}` / `{reg.get('strategy')}` · cap=`{reg.get('cap_usd')}` · "
        f"allow_new_buys=`{reg.get('allow_new_buys')}`",
        f"- Fees: maker=`{fee.get('maker_pct')}` taker=`{fee.get('taker_pct')}` ({fee.get('source')})",
        "",
        "## X activity",
        "",
        f"- Today pair-queries: {x.get('pair_queries_today')} "
        f"(rsi={x.get('rsi_pair_queries_today')} rebal={x.get('rebal_pair_queries_today')})",
        f"- Probe events in week window: {x.get('probe_events_in_week_window')}",
        f"- Primary schedule: {x.get('primary_schedule')}",
        f"- Note: {x.get('x_usd_assumption_note')}",
        "",
        "## Buckets",
        "",
        f"```json\n{json.dumps(rt.get('by_bucket') or {}, indent=2)}\n```",
        "",
        f"State: `{_rel(STATE_PATH)}`",
        f"Report: `{_rel(REPORT_PATH)}`",
        "",
        str(vs.get("note") or ""),
        "",
    ]
    return "\n".join(lines)


def telegram_card(payload: Dict[str, Any]) -> str:
    """Short TG body — empty not used; always one card for scheduled one-shot."""
    rt = payload.get("rt") or {}
    vs = payload.get("vs_be") or {}
    x = payload.get("x_cost") or {}
    port = payload.get("portfolio") or {}
    lines = [
        "📊 Break-even one-pager (measure-only)",
        f"Bar: ≥${payload.get('be_usd_mo')}/mo · week from {payload.get('week_start_pt')}",
        f"Verdict: {vs.get('verdict')}",
        "",
        f"RT window: n={rt.get('n_rt_primary')} · gross ${rt.get('gross_pnl_usd')}",
        f"  tax n={rt.get('process_tax_n')} ${rt.get('process_tax_usd')} · "
        f"non-tax n={rt.get('non_tax_n')} ${rt.get('non_tax_usd')}",
        f"Est X to date: ${x.get('est_x_usd_to_date')} (~${x.get('x_usd_per_week_assumption')}/wk assume)",
        f"Net RT−X (to date): ${vs.get('net_rt_minus_est_x_to_date_usd')}",
        f"Illustrative $/mo gross→gap after X: "
        f"{vs.get('gross_run_rate_usd_mo_ILLUSTRATIVE')} → {vs.get('be_gap_after_est_x_usd_mo_ILLUSTRATIVE')}",
        f"Edge claim: {rt.get('edge_claim_allowed')} (need n≥20)",
        "",
        f"Book ~${port.get('total_usd')} · holdings ~${port.get('holdings_usd')}",
        "Full: reports/BREAK_EVEN_ONE_PAGER_LATEST.md",
        "No knobs · not a size-up GO",
    ]
    return "\n".join(lines)


def write_artifacts(payload: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(payload), encoding="utf-8")
