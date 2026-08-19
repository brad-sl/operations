#!/usr/bin/env python3
"""Weekly SL vs shadow-exit counterfactual (plain English).

For each exchange stop-loss since the regime-exit shadow collection clock
(or --since), show whether RSI/TP/trail *would-fire* episodes happened first
and the $ delta vs riding to SL.

Standalone: json + stdlib only. No phase6.core imports (cron-safe).
Writes:
  reports/SL_EXIT_COUNTERFACTUAL_LATEST.md
  data/state/sl_exit_counterfactual_latest.json
Prints Telegram-friendly body to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/brad/projects/crypto-trading-bot")
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
EVENTS = ROOT / "data" / "state" / "regime_exit_shadow_events.jsonl"
COLLECTION = ROOT / "data" / "state" / "regime_exit_shadow_collection.json"
STATUS = ROOT / "data" / "state" / "regime_exit_shadow_status.json"
HARD = ROOT / "data" / "state" / "regime_hard_exit_shadow.json"
OUT_MD = ROOT / "reports" / "SL_EXIT_COUNTERFACTUAL_LATEST.md"
OUT_JSON = ROOT / "data" / "state" / "sl_exit_counterfactual_latest.json"

# Default clean collection clock (regime map live-shadow)
DEFAULT_SINCE = "2026-08-06T18:17:16+00:00"


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    if "T" in s and "+" not in s[10:] and not s.endswith("Z"):
        # naive → assume UTC
        if len(s) >= 19 and s[10] == "T":
            s = s[:19] + "+00:00" if "+" not in s else s
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def _pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:+.2f}%"


def _usd(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"${x:+.2f}"


def _sl_sells_since(since: datetime) -> list[dict[str, Any]]:
    out = []
    for t in _load_jsonl(TRADES):
        side = str(t.get("side") or "").upper()
        reason = str(t.get("reason") or t.get("exit_reason") or "")
        if side != "SELL":
            continue
        if "stop_loss" not in reason.lower():
            continue
        ts = _parse_ts(t.get("timestamp") or t.get("ts"))
        if ts is None or ts < since:
            continue
        out.append(t)
    out.sort(key=lambda r: str(r.get("timestamp") or ""))
    return out


def _events_for_pair_before(
    events: list[dict[str, Any]], pair: str, before: datetime, after: datetime | None
) -> list[dict[str, Any]]:
    hit = []
    for e in events:
        if e.get("pair") != pair:
            continue
        et = _parse_ts(e.get("ts"))
        if et is None or et >= before:
            continue
        if after is not None and et < after:
            continue
        hit.append(e)
    hit.sort(key=lambda e: str(e.get("ts") or ""))
    return hit


def _leg_cf(t: dict[str, Any], prior: list[dict[str, Any]]) -> dict[str, Any]:
    entry = t.get("entry_price")
    exit_px = t.get("exit_price") or t.get("price")
    qty = t.get("qty") or t.get("quantity")
    pnl_pct = t.get("pnl_pct")
    pnl_usd = t.get("pnl")
    if pnl_pct is None and entry and exit_px and float(entry) > 0:
        pnl_pct = float(exit_px) / float(entry) - 1.0
    if pnl_usd is None and entry and exit_px and qty is not None:
        try:
            pnl_usd = (float(exit_px) - float(entry)) * float(qty)
        except Exception:
            pnl_usd = None

    best = None
    for e in prior:
        r = e.get("r")
        if r is None:
            continue
        if best is None or float(r) > float(best.get("r") or -9e9):
            best = e

    best_r = float(best["r"]) if best and best.get("r") is not None else None
    best_kind = best.get("kind") if best else None
    best_ts = best.get("ts") if best else None
    best_detail = (best.get("detail") or "")[:120] if best else None
    # $ if we had exited at best shadow mark vs actual SL
    delta_usd = None
    if best is not None and entry and qty is not None and best.get("mark_px") is not None:
        try:
            shadow_pnl = (float(best["mark_px"]) - float(entry)) * float(qty)
            if pnl_usd is not None:
                delta_usd = shadow_pnl - float(pnl_usd)
            else:
                delta_usd = shadow_pnl
        except Exception:
            delta_usd = None

    kinds: dict[str, int] = defaultdict(int)
    for e in prior:
        kinds[str(e.get("kind") or "?")] += 1

    return {
        "pair": t.get("pair"),
        "sl_ts": t.get("timestamp"),
        "reason": t.get("reason") or t.get("exit_reason"),
        "entry": entry,
        "exit": exit_px,
        "qty": qty,
        "sl_pnl_pct": pnl_pct,
        "sl_pnl_usd": pnl_usd,
        "prior_episodes": len(prior),
        "prior_kinds": dict(kinds),
        "best_prior_r": best_r,
        "best_prior_kind": best_kind,
        "best_prior_ts": best_ts,
        "best_prior_detail": best_detail,
        "delta_usd_best_shadow_vs_sl": delta_usd,
        "had_prior_signal": len(prior) > 0,
    }


def build(since: datetime) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    col = _load_json(COLLECTION)
    st = _load_json(STATUS)
    hard = _load_json(HARD)
    events = _load_jsonl(EVENTS)

    col_start = _parse_ts(col.get("started_at")) or since
    effective_since = max(since, col_start) if col_start else since

    sl_legs = _sl_sells_since(effective_since)
    # Dedup dust_sweep_after_sl — only true stop_loss_exchange for primary legs
    primary = [t for t in sl_legs if "dust" not in str(t.get("reason") or "").lower()]

    legs_out = []
    for t in primary:
        ts = _parse_ts(t.get("timestamp"))
        if ts is None:
            continue
        # Look back from bag entry if known, else 14d before SL, floored at collection
        lookback_floor = effective_since
        prior = _events_for_pair_before(events, str(t.get("pair")), ts, lookback_floor)
        legs_out.append(_leg_cf(t, prior))

    n_with_signal = sum(1 for L in legs_out if L["had_prior_signal"])
    deltas = [
        L["delta_usd_best_shadow_vs_sl"]
        for L in legs_out
        if L.get("delta_usd_best_shadow_vs_sl") is not None
    ]
    sum_delta = sum(deltas) if deltas else None

    prom = (st.get("promotion") or {}) if st else {}
    per = prom.get("per_regime") or {}
    peak_r = st.get("peak_r") or {}
    signals = st.get("signals") or []

    by_reg_col = {}
    for reg, v in (col.get("by_regime") or {}).items():
        by_reg_col[reg] = {
            "episodes": v.get("would_fire_episodes"),
            "by_kind": v.get("by_kind"),
            "pairs": v.get("pairs"),
        }

    days_seen = {k: len(v) for k, v in (col.get("days_regime_seen") or {}).items()}
    shadow_days = prom.get("shadow_days")
    if shadow_days is None and col_start:
        shadow_days = round((now - col_start).total_seconds() / 86400.0, 2)

    # Go/no-go for live flip
    ready = bool(prom.get("ready_for_settings_flip_review"))
    if ready:
        go = "REVIEW ONLY — gates hint ready; still needs Brad OK (not auto-live)"
    elif (prom.get("n_regimes_ready_hint") or 0) >= 1 and (shadow_days or 0) < 45:
        go = "NO-GO live exits — collecting (early). Shadow only."
    else:
        go = "NO-GO live exits — keep shadow; not enough multi-regime closed legs."

    return {
        "schema": "sl_exit_counterfactual_v1",
        "as_of": now.isoformat(),
        "since": effective_since.isoformat(),
        "collection_started_at": col.get("started_at"),
        "shadow_days": shadow_days,
        "days_needed": prom.get("days_needed", 60),
        "regime_now": st.get("regime"),
        "plain_english_status": st.get("plain_english"),
        "go_no_go": go,
        "ready_for_settings_flip_review": ready,
        "promotion": {
            "regimes_ready_hint": prom.get("regimes_ready_hint"),
            "per_regime": {
                k: {
                    "would_fire_episodes": (per.get(k) or {}).get("would_fire_episodes"),
                    "closed_legs_observed": (per.get(k) or {}).get("closed_legs_observed"),
                    "closed_legs_needed": (per.get(k) or {}).get("closed_legs_needed"),
                    "distinct_days_seen": (per.get(k) or {}).get("distinct_days_seen"),
                    "ready_hint": (per.get(k) or {}).get("ready_hint"),
                }
                for k in ("bull", "bear", "flat")
            },
        },
        "collection_by_regime": by_reg_col,
        "days_regime_seen": days_seen,
        "hard_exit": {
            "shadow_only": hard.get("shadow_only"),
            "live_apply": hard.get("live_apply"),
            "operator_approve": hard.get("operator_approve"),
            "n_proposals_now": hard.get("n"),
        },
        "n_sl_legs": len(legs_out),
        "n_sl_with_prior_shadow": n_with_signal,
        "sum_delta_usd_best_shadow_vs_sl": sum_delta,
        "legs": legs_out,
        "open_peak_r": peak_r,
        "open_would_fire_now": [
            {
                "pair": s.get("pair"),
                "kind": s.get("kind"),
                "r": s.get("r"),
                "detail": (s.get("detail") or "")[:100],
            }
            for s in signals
        ],
        "glossary": {
            "SL": "Exchange stop-loss (~3% floor) — live",
            "shadow would-fire": "Runner would have exited on TP/trail/RSI rule — logged only, no order",
            "hard exit": "RSI/sentiment dump path — still needs your OK to auto-sell",
            "delta $": "Best prior shadow exit $ PnL minus actual SL $ PnL (positive = early exit would have helped)",
        },
    }


def render_telegram(d: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("📊 Weekly exit check — SL vs early signals")
    lines.append("")
    lines.append(f"Go/no-go: {d.get('go_no_go')}")
    lines.append(
        f"Collection: day {d.get('shadow_days')}/{d.get('days_needed')} · "
        f"regime now: {d.get('regime_now') or '?'}"
    )
    pe = d.get("plain_english_status")
    if pe:
        lines.append(str(pe)[:220])
    lines.append("")

    # Regime table compact
    lines.append("By market mood (need bull+bear+flat before live talk):")
    for reg in ("flat", "bull", "bear"):
        p = (d.get("promotion") or {}).get("per_regime") or {}
        pr = p.get(reg) or {}
        col = (d.get("collection_by_regime") or {}).get(reg) or {}
        eps = pr.get("would_fire_episodes") if pr.get("would_fire_episodes") is not None else col.get("episodes")
        cl = pr.get("closed_legs_observed")
        need = pr.get("closed_legs_needed") or 15
        days = pr.get("distinct_days_seen")
        flag = "✓ episodes" if pr.get("ready_hint") else "…"
        lines.append(
            f"  {reg}: episodes={eps if eps is not None else 0} · "
            f"closed legs after signal {cl if cl is not None else 0}/{need} · "
            f"days={days if days is not None else 0} {flag}"
        )

    he = d.get("hard_exit") or {}
    lines.append(
        f"Hard exit auto-sell: OFF (operator_approve={he.get('operator_approve')}, "
        f"live_apply={he.get('live_apply')})"
    )
    lines.append("")

    n = d.get("n_sl_legs") or 0
    n_sig = d.get("n_sl_with_prior_shadow") or 0
    lines.append(f"Exchange SL legs since {str(d.get('since') or '')[:10]}: {n}")
    lines.append(f"  with prior shadow signal: {n_sig}/{n}")
    sd = d.get("sum_delta_usd_best_shadow_vs_sl")
    if sd is not None and n:
        lines.append(
            f"  If best early signal had been taken on those legs: "
            f"{_usd(float(sd))} vs riding to SL (sum)"
        )
    lines.append("")

    legs = d.get("legs") or []
    if not legs:
        lines.append("No exchange SL fills in this window yet — nothing to counterfactual.")
    else:
        lines.append("Each SL leg (newest last):")
        # show last 8 to keep TG short
        for L in legs[-8:]:
            ts = str(L.get("sl_ts") or "")[:16].replace("T", " ")
            pair = L.get("pair")
            lines.append(
                f"• {ts} {pair} SL {_pct(L.get('sl_pnl_pct'))} "
                f"({_usd(L.get('sl_pnl_usd'))})"
            )
            if L.get("had_prior_signal"):
                kinds = L.get("prior_kinds") or {}
                ktxt = ", ".join(f"{k}×{v}" for k, v in kinds.items())
                lines.append(
                    f"  early signal: YES ({L.get('prior_episodes')} eps: {ktxt})"
                )
                lines.append(
                    f"  best was {L.get('best_prior_kind')} @ {_pct(L.get('best_prior_r'))} "
                    f"→ Δ vs SL {_usd(L.get('delta_usd_best_shadow_vs_sl'))}"
                )
            else:
                lines.append("  early signal: none logged before SL")
        if len(legs) > 8:
            lines.append(f"  … {len(legs) - 8} older legs in full report file")

    open_sig = d.get("open_would_fire_now") or []
    peak = d.get("open_peak_r") or {}
    lines.append("")
    if open_sig:
        lines.append("Open bags would-fire *right now* (still no order):")
        for s in open_sig[:5]:
            lines.append(
                f"  {s.get('pair')} {s.get('kind')} r={_pct(s.get('r'))}"
            )
    else:
        lines.append("Open bags: no would-fire signal right now.")
    if peak:
        # top peaks
        tops = sorted(
            ((k, float(v)) for k, v in peak.items() if v is not None),
            key=lambda kv: -kv[1],
        )[:5]
        if tops:
            lines.append(
                "Peak gain while held (shadow book): "
                + ", ".join(f"{p} {_pct(r)}" for p, r in tops)
            )

    lines.append("")
    lines.append("Words: SL = live ~3% stop. Shadow = log only. Δ$ = early exit helped if positive.")
    lines.append("Full: reports/SL_EXIT_COUNTERFACTUAL_LATEST.md")
    lines.append("Still shadow — no live early-exit flip without your OK.")
    body = "\n".join(lines)
    # Telegram hard limit safety
    if len(body) > 3900:
        body = body[:3850] + "\n…(truncated)"
    return body


def render_md(d: dict[str, Any]) -> str:
    lines = [
        "# SL exit counterfactual",
        "",
        f"- as_of: `{d.get('as_of')}`",
        f"- since: `{d.get('since')}`",
        f"- go/no-go: **{d.get('go_no_go')}**",
        f"- shadow_days: {d.get('shadow_days')}/{d.get('days_needed')}",
        f"- regime_now: {d.get('regime_now')}",
        "",
        "## Legs",
        "",
    ]
    for L in d.get("legs") or []:
        lines.append(
            f"### {L.get('pair')} @ {L.get('sl_ts')}\n"
            f"- SL PnL: {_pct(L.get('sl_pnl_pct'))} ({_usd(L.get('sl_pnl_usd'))})\n"
            f"- prior episodes: {L.get('prior_episodes')} {L.get('prior_kinds')}\n"
            f"- best prior: {L.get('best_prior_kind')} r={_pct(L.get('best_prior_r'))} "
            f"ts={L.get('best_prior_ts')}\n"
            f"- Δ$ best shadow vs SL: {_usd(L.get('delta_usd_best_shadow_vs_sl'))}\n"
            f"- detail: {L.get('best_prior_detail')}\n"
        )
    lines.append("## Raw JSON")
    lines.append("")
    lines.append(f"See `{OUT_JSON.relative_to(ROOT)}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--since",
        default=None,
        help="ISO start (default: collection started_at or 2026-08-06 map clock)",
    )
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    col = _load_json(COLLECTION)
    since_s = args.since or col.get("started_at") or DEFAULT_SINCE
    since = _parse_ts(since_s)
    if since is None:
        print("Bad --since", since_s, file=sys.stderr)
        return 2

    d = build(since)
    body = render_telegram(d)
    md = render_md(d)

    if not args.no_write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_MD.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(json.dumps(d, indent=2, default=str) + "\n", encoding="utf-8")
        OUT_MD.write_text(md, encoding="utf-8")

    if args.json_only:
        print(json.dumps(d, indent=2, default=str))
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
