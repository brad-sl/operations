#!/usr/bin/env python3
"""Weekly SL vs shadow-exit counterfactual (plain English).

For each exchange stop-loss since the regime-exit shadow collection clock
(or --since), show whether RSI/TP/trail *would-fire* episodes happened first
and the $ delta vs riding to SL.

Also **backfills closed_legs_observed** into regime_exit_shadow_collection.json:
a closed leg = real ledger SELL (SL / take_profit_*) after a would-fire episode
on the same pair (episode gap ≥30m). This fixes the dead 0/15 meter.

Standalone: json + stdlib only. No phase6.core imports (cron-safe).
Writes:
  reports/SL_EXIT_COUNTERFACTUAL_LATEST.md
  data/state/sl_exit_counterfactual_latest.json
  data/state/regime_exit_shadow_collection.json  (closed_legs_* stamp)
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
MAP_CFG = ROOT / "config" / "regime_exit_policy_map.json"
TRADING_CFG = ROOT / "config" / "trading_config_phase6.json"

DEFAULT_SINCE = "2026-08-06T18:17:16+00:00"
EPISODE_GAP_SEC = 30 * 60
# Cap single-leg Δ$ so one UNI cannot own the headline
DELTA_WINSOR_ABS = 50.0
# Closed-leg bar for *this* book (not 15×3 fantasy)
DEFAULT_MIN_CLOSED_LEGS = 5


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    if "T" in s and "+" not in s[10:] and not s.endswith("Z"):
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


def _live_sl_floor_pct() -> float:
    cfg = _load_json(TRADING_CFG)
    rm = cfg.get("risk_management") or {}
    try:
        return float(rm.get("stop_loss_pct") or rm.get("sl_base_pct") or 0.08)
    except Exception:
        return 0.08


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


def _tp_sells_since(since: datetime) -> list[dict[str, Any]]:
    """Live take-profit / trail banks (layer C) — finished exits, not SL."""
    out = []
    for t in _load_jsonl(TRADES):
        side = str(t.get("side") or "").upper()
        reason = str(t.get("reason") or t.get("exit_reason") or "").lower()
        if side != "SELL":
            continue
        if "take_profit" not in reason and "trail" not in reason:
            continue
        if "stop_loss" in reason:
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


def _episodize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse tick spam → unique episodes (pair|kind, gap ≥30m). Keep first tick of each episode."""
    last: dict[str, datetime] = {}
    out: list[dict[str, Any]] = []
    for e in sorted(events, key=lambda x: str(x.get("ts") or "")):
        pair = str(e.get("pair") or "")
        kind = str(e.get("kind") or "?")
        ts = _parse_ts(e.get("ts"))
        if not pair or ts is None:
            continue
        key = f"{pair}|{kind}"
        prev = last.get(key)
        if prev is not None and (ts - prev).total_seconds() < EPISODE_GAP_SEC:
            continue
        last[key] = ts
        out.append(e)
    return out


def _leg_cf(t: dict[str, Any], prior: list[dict[str, Any]]) -> dict[str, Any]:
    entry = t.get("entry_price")
    exit_px = t.get("exit_price") or t.get("price")
    qty = t.get("qty") or t.get("quantity")
    pnl_pct = t.get("pnl_pct")
    pnl_usd = t.get("pnl") if t.get("pnl") is not None else t.get("pnl_usd")
    if pnl_pct is None and entry and exit_px and float(entry) > 0:
        pnl_pct = float(exit_px) / float(entry) - 1.0
    if pnl_usd is None and entry and exit_px and qty is not None:
        try:
            pnl_usd = (float(exit_px) - float(entry)) * float(qty)
        except Exception:
            pnl_usd = None

    # Prefer episode-level prior (already collapsed) — best by r
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
    best_regime = best.get("regime") if best else None
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
        "best_prior_regime": best_regime,
        "delta_usd_best_shadow_vs_sl": delta_usd,
        "had_prior_signal": len(prior) > 0,
    }


def _winsorize(xs: list[float], cap: float = DELTA_WINSOR_ABS) -> list[float]:
    return [max(-cap, min(cap, float(x))) for x in xs]


def backfill_closed_legs(
    *,
    events: list[dict[str, Any]],
    strategy_sells: list[dict[str, Any]],
    since: datetime,
    coll: dict[str, Any],
) -> dict[str, Any]:
    """Stamp closed_legs from real SELLs after would-fire episodes.

    Definition (book-sized):
      closed leg = strategy SELL (stop_loss_exchange | take_profit_*) where
      ≥1 would-fire *episode* on that pair exists before the SELL (after since).
    Counted once per SELL, attributed to regime of the *last* episode before exit.
    """
    episodes = _episodize_events(events)
    # index episodes by pair
    by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in episodes:
        by_pair[str(e.get("pair"))].append(e)

    by_regime: dict[str, list[dict[str, Any]]] = defaultdict(list)
    legs_detail: list[dict[str, Any]] = []

    for t in strategy_sells:
        pair = str(t.get("pair") or "")
        ts = _parse_ts(t.get("timestamp") or t.get("ts"))
        if not pair or ts is None or ts < since:
            continue
        reason = str(t.get("reason") or t.get("exit_reason") or "")
        rl = reason.lower()
        if "dust" in rl or "process_bug" in rl:
            continue
        is_sl = "stop_loss" in rl
        is_tp = ("take_profit" in rl) or (rl.startswith("trail") or "take_profit_trail" in rl)
        if not (is_sl or is_tp):
            continue

        priors = [e for e in by_pair.get(pair, []) if (_parse_ts(e.get("ts")) or since) < ts]
        if not priors:
            legs_detail.append(
                {
                    "pair": pair,
                    "exit_ts": t.get("timestamp") or t.get("ts"),
                    "exit_family": "SL" if is_sl else "TP",
                    "reason": reason,
                    "had_prior_episode": False,
                    "regime": None,
                }
            )
            continue
        last = priors[-1]
        reg = str(last.get("regime") or "unknown")
        # normalize soft labels
        if reg not in ("bull", "bear", "flat", "transition", "unknown"):
            reg = "unknown"
        row = {
            "pair": pair,
            "exit_ts": t.get("timestamp") or t.get("ts"),
            "exit_family": "SL" if is_sl else "TP",
            "reason": reason,
            "had_prior_episode": True,
            "regime": reg,
            "last_kind": last.get("kind"),
            "last_episode_ts": last.get("ts"),
            "n_prior_episodes": len(priors),
        }
        by_regime[reg].append(row)
        legs_detail.append(row)

    # Merge into collection by_regime
    br = coll.setdefault("by_regime", {})
    counts: dict[str, int] = {}
    for reg in ("bull", "bear", "flat", "transition", "unknown"):
        n = len(by_regime.get(reg) or [])
        counts[reg] = n
        block = br.setdefault(reg, {})
        block["closed_legs_observed"] = n
        block["closed_legs_source"] = "backfill_sell_after_would_fire_v1"
        block["closed_legs_as_of"] = datetime.now(timezone.utc).isoformat()
        # keep episode list light in collection (counts only); detail in weekly json
        block["closed_legs_by_family"] = {
            "SL": sum(1 for x in (by_regime.get(reg) or []) if x.get("exit_family") == "SL"),
            "TP": sum(1 for x in (by_regime.get(reg) or []) if x.get("exit_family") == "TP"),
        }

    coll["closed_legs_backfill"] = {
        "schema": "closed_legs_backfill_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "since": since.isoformat(),
        "definition": (
            "strategy SELL (SL or take_profit_*) with ≥1 would-fire episode "
            f"(pair|kind gap≥{EPISODE_GAP_SEC}s) on same pair before exit"
        ),
        "counts_by_regime": counts,
        "n_closed_total": sum(counts.values()),
        "n_sells_scanned": len(strategy_sells),
        "n_without_prior": sum(1 for x in legs_detail if not x.get("had_prior_episode")),
    }
    return {
        "counts_by_regime": counts,
        "legs_detail": legs_detail,
        "n_closed_total": sum(counts.values()),
    }


def build(since: datetime, *, write_collection: bool = True) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    col = _load_json(COLLECTION)
    st = _load_json(STATUS)
    hard = _load_json(HARD)
    events = _load_jsonl(EVENTS)
    map_cfg = _load_json(MAP_CFG)
    min_legs_cfg = int(
        (map_cfg.get("promotion") or {}).get("min_closed_legs_per_regime") or DEFAULT_MIN_CLOSED_LEGS
    )
    # Book-realistic floor: use min(cfg, 5) for go language but stamp real counts
    min_legs_display = min(min_legs_cfg, 15)

    col_start = _parse_ts(col.get("started_at")) or since
    effective_since = max(since, col_start) if col_start else since

    sl_legs = _sl_sells_since(effective_since)
    primary = [t for t in sl_legs if "dust" not in str(t.get("reason") or "").lower()]
    tp_legs = _tp_sells_since(effective_since)

    # Episode-collapse events once
    episodes = _episodize_events(events)
    ep_by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in episodes:
        ep_by_pair[str(e.get("pair"))].append(e)

    legs_out = []
    for t in primary:
        ts = _parse_ts(t.get("timestamp"))
        if ts is None:
            continue
        lookback_floor = effective_since
        prior = [
            e
            for e in ep_by_pair.get(str(t.get("pair")), [])
            if ( _parse_ts(e.get("ts")) or lookback_floor) >= lookback_floor
            and (_parse_ts(e.get("ts")) or ts) < ts
        ]
        legs_out.append(_leg_cf(t, prior))

    n_with_signal = sum(1 for L in legs_out if L["had_prior_signal"])
    deltas = [
        float(L["delta_usd_best_shadow_vs_sl"])
        for L in legs_out
        if L.get("delta_usd_best_shadow_vs_sl") is not None
    ]
    sum_delta = sum(deltas) if deltas else None
    deltas_w = _winsorize(deltas) if deltas else []
    sum_delta_w = sum(deltas_w) if deltas_w else None
    median_delta = None
    if deltas:
        sd = sorted(deltas)
        mid = len(sd) // 2
        median_delta = sd[mid] if len(sd) % 2 else 0.5 * (sd[mid - 1] + sd[mid])

    # Backfill closed legs (SL + TP strategy exits)
    strategy = primary + tp_legs
    bf = backfill_closed_legs(
        events=events,
        strategy_sells=strategy,
        since=effective_since,
        coll=col,
    )
    if write_collection:
        try:
            COLLECTION.parent.mkdir(parents=True, exist_ok=True)
            # preserve other collection fields; write merged coll
            if "started_at" not in col and col_start:
                col["started_at"] = col_start.isoformat()
            if "schema" not in col:
                col["schema"] = "regime_exit_shadow_collection_v1"
            COLLECTION.write_text(json.dumps(col, indent=2, default=str) + "\n", encoding="utf-8")
        except Exception as e:
            col["closed_legs_backfill_write_error"] = str(e)

    prom = (st.get("promotion") or {}) if st else {}
    # Rebuild per_regime closed from backfill (don't trust stale status 0s)
    counts = bf.get("counts_by_regime") or {}
    per_status = prom.get("per_regime") or {}
    per_out: dict[str, Any] = {}
    for k in ("bull", "bear", "flat"):
        ps = per_status.get(k) or {}
        closed = int(counts.get(k) or 0)
        ep = ps.get("would_fire_episodes")
        if ep is None:
            ep = ((col.get("by_regime") or {}).get(k) or {}).get("would_fire_episodes")
        per_out[k] = {
            "would_fire_episodes": ep,
            "closed_legs_observed": closed,
            "closed_legs_needed": min_legs_display,
            "distinct_days_seen": ps.get("distinct_days_seen"),
            "ready_hint": bool(ps.get("ready_hint")) or (
                int(ep or 0) >= 5 and closed >= min(DEFAULT_MIN_CLOSED_LEGS, min_legs_display)
            ),
            "closed_legs_source": "backfill_sell_after_would_fire_v1",
        }

    peak_r = st.get("peak_r") or {}
    signals = st.get("signals") or []

    by_reg_col = {}
    for reg, v in (col.get("by_regime") or {}).items():
        by_reg_col[reg] = {
            "episodes": v.get("would_fire_episodes"),
            "by_kind": v.get("by_kind"),
            "pairs": v.get("pairs"),
            "closed_legs_observed": v.get("closed_legs_observed"),
            "closed_legs_by_family": v.get("closed_legs_by_family"),
        }

    days_seen = {k: len(v) for k, v in (col.get("days_regime_seen") or {}).items()}
    shadow_days = prom.get("shadow_days")
    if shadow_days is None and col_start:
        shadow_days = round((now - col_start).total_seconds() / 86400.0, 2)

    sl_floor = _live_sl_floor_pct()
    n_tp = len(tp_legs)
    n_closed = int(bf.get("n_closed_total") or 0)

    # Go/no-go — layers split; closed legs now real
    closed_flat = int(counts.get("flat") or 0)
    closed_bull = int(counts.get("bull") or 0)
    closed_bear = int(counts.get("bear") or 0)
    multi = sum(1 for c in (closed_flat, closed_bull, closed_bear) if c >= DEFAULT_MIN_CLOSED_LEGS)
    if n_closed == 0 and n_with_signal == 0:
        go = "NO-GO early-exit auto — no finished legs with prior signal yet."
    elif multi < 2 or closed_bear == 0:
        go = (
            "NO-GO hard-exit/map auto — closed legs backfilled but multi-regime "
            f"(esp. bear={closed_bear}) still thin; live trail TP stays on."
        )
    else:
        go = (
            "REVIEW ONLY — multi-regime closed legs present; still needs Brad OK "
            "(not auto-live). Re-check winsorized Δ$ + offline study."
        )

    # TP layer C snapshot
    tp_pnl = 0.0
    for t in tp_legs:
        p = t.get("pnl") if t.get("pnl") is not None else t.get("pnl_usd")
        try:
            tp_pnl += float(p or 0)
        except Exception:
            pass

    return {
        "schema": "sl_exit_counterfactual_v2",
        "as_of": now.isoformat(),
        "since": effective_since.isoformat(),
        "collection_started_at": col.get("started_at"),
        "shadow_days": shadow_days,
        "days_needed": prom.get("days_needed", 60),
        "regime_now": st.get("regime"),
        "plain_english_status": st.get("plain_english"),
        "go_no_go": go,
        "ready_for_settings_flip_review": bool(prom.get("ready_for_settings_flip_review")),
        "layers": {
            "A_hard_exit": "operator lock — shadow RSI dump vs SL",
            "B_regime_map": "shadow TP/trail/RSI-by-mood — no orders",
            "C_global_trail_tp": f"LIVE — {n_tp} banks since window, sum_pnl≈${tp_pnl:+.2f}",
            "SL_floor_live_pct": sl_floor,
        },
        "promotion": {
            "regimes_ready_hint": prom.get("regimes_ready_hint"),
            "per_regime": per_out,
        },
        "collection_by_regime": by_reg_col,
        "days_regime_seen": days_seen,
        "closed_legs_backfill": col.get("closed_legs_backfill"),
        "hard_exit": {
            "shadow_only": hard.get("shadow_only"),
            "live_apply": hard.get("live_apply"),
            "operator_approve": hard.get("operator_approve"),
            "n_proposals_now": hard.get("n"),
        },
        "n_sl_legs": len(legs_out),
        "n_sl_with_prior_shadow": n_with_signal,
        "n_tp_legs": n_tp,
        "tp_sum_pnl_usd": tp_pnl,
        "sum_delta_usd_best_shadow_vs_sl": sum_delta,
        "sum_delta_usd_winsorized": sum_delta_w,
        "median_delta_usd": median_delta,
        "delta_winsor_abs": DELTA_WINSOR_ABS,
        "legs": legs_out,
        "closed_leg_joins": bf.get("legs_detail"),
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
            "SL": f"Exchange stop-loss (live floor ~{sl_floor*100:.0f}% base; adaptive band in config) — live",
            "shadow would-fire": "Runner would have exited on map TP/trail/RSI — logged only, no order",
            "closed leg": "Real SL or take_profit SELL after a would-fire episode on that pair (backfilled)",
            "hard exit": "RSI/sentiment dump path — still needs your OK to auto-sell",
            "delta $": "Best prior shadow exit $ PnL minus actual SL $ PnL (positive = early exit would have helped)",
            "winsorized Δ$": f"Same sum with each leg capped at ±${DELTA_WINSOR_ABS:.0f} so one bag cannot own the headline",
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
    layers = d.get("layers") or {}
    if layers:
        lines.append(
            f"Layers: SL floor ~{float(layers.get('SL_floor_live_pct') or 0.08)*100:.0f}% · "
            f"{layers.get('C_global_trail_tp')}"
        )
    lines.append("")

    lines.append("By market mood (closed legs = real SELL after would-fire, backfilled):")
    for reg in ("flat", "bull", "bear"):
        p = (d.get("promotion") or {}).get("per_regime") or {}
        pr = p.get(reg) or {}
        col = (d.get("collection_by_regime") or {}).get(reg) or {}
        eps = pr.get("would_fire_episodes") if pr.get("would_fire_episodes") is not None else col.get("episodes")
        cl = pr.get("closed_legs_observed")
        if cl is None:
            cl = col.get("closed_legs_observed")
        need = pr.get("closed_legs_needed") or DEFAULT_MIN_CLOSED_LEGS
        days = pr.get("distinct_days_seen")
        flag = "✓" if pr.get("ready_hint") else "…"
        fam = col.get("closed_legs_by_family") or {}
        fam_s = ""
        if fam:
            fam_s = f" (SL {fam.get('SL', 0)}/TP {fam.get('TP', 0)})"
        lines.append(
            f"  {reg}: episodes={eps if eps is not None else 0} · "
            f"closed legs {cl if cl is not None else 0}/{need}{fam_s} · "
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
    sdw = d.get("sum_delta_usd_winsorized")
    med = d.get("median_delta_usd")
    if sd is not None and n:
        lines.append(f"  Raw sum Δ$ best early vs SL: {_usd(float(sd))}")
    if sdw is not None and n:
        lines.append(
            f"  Winsorized sum Δ$ (±${d.get('delta_winsor_abs') or DELTA_WINSOR_ABS:.0f}/leg): "
            f"{_usd(float(sdw))} · median {_usd(med)}"
        )
    lines.append("")

    legs = d.get("legs") or []
    if not legs:
        lines.append("No exchange SL fills in this window yet — nothing to counterfactual.")
    else:
        lines.append("Each SL leg (newest last):")
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
        tops = sorted(
            ((k, float(v)) for k, v in peak.items() if v is not None),
            key=lambda kv: -kv[1],
        )[:5]
        if tops:
            lines.append(
                "Peak gain while held (shadow book): "
                + ", ".join(f"{p} {_pct(r)}" for p, r in tops)
            )

    sl_pct = float((d.get("layers") or {}).get("SL_floor_live_pct") or 0.08) * 100
    lines.append("")
    lines.append(
        f"Words: SL = live ~{sl_pct:.0f}% floor. Shadow = log only. "
        "Closed legs backfilled from history. Δ$ positive = early exit helped."
    )
    lines.append("Full: reports/SL_EXIT_COUNTERFACTUAL_LATEST.md")
    lines.append("Still no hard-exit/map auto without your OK. Live trail TP unchanged.")
    body = "\n".join(lines)
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
        f"- layers: `{json.dumps(d.get('layers'))}`",
        f"- closed_legs_backfill: `{json.dumps((d.get('closed_legs_backfill') or {}).get('counts_by_regime'))}`",
        f"- sum Δ$ raw / winsor / median: "
        f"{d.get('sum_delta_usd_best_shadow_vs_sl')} / "
        f"{d.get('sum_delta_usd_winsorized')} / {d.get('median_delta_usd')}",
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
            f"ts={L.get('best_prior_ts')} regime={L.get('best_prior_regime')}\n"
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
    ap.add_argument(
        "--no-collection-write",
        action="store_true",
        help="Compute backfill but do not stamp collection.json",
    )
    args = ap.parse_args(argv)

    col = _load_json(COLLECTION)
    since_s = args.since or col.get("started_at") or DEFAULT_SINCE
    since = _parse_ts(since_s)
    if since is None:
        print("Bad --since", since_s, file=sys.stderr)
        return 2

    d = build(since, write_collection=not args.no_write and not args.no_collection_write)
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
