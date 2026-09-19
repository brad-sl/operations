#!/usr/bin/env python3
"""Paid single-pair (top-K) X probe for RSI-event path — NO orders.

Brad GO 2026-09-18 validate track 1:
  spend_x ON only when RSI wash + stale eng + budget allows.
  Writes X cache + optional latch; never evaluate_buy_entry for live orders.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.core.paths import PROJECT_ROOT, STATE_DIR
from phase6.core.rsi_event_x_tryout_shadow import (
    ShadowConfig,
    build_shadow_board,
    run_shadow,
    write_artifacts,
)
from phase6.core.x_query_budget import BudgetConfig, check_can_spend, record_spend

SCHEMA = "rsi_event_x_probe_v1"
PROBE_LATEST = STATE_DIR / "rsi_event_x_probe_latest.json"
PROBE_EVENTS = STATE_DIR / "rsi_event_x_probe_events.jsonl"
MD_REPORT = PROJECT_ROOT / "reports" / "RSI_EVENT_X_PROBE_LATEST.md"
X_FETCH = PROJECT_ROOT / "fetch_x_sentiment.py"
X_CACHE = STATE_DIR / "x_sentiment_cache.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def fetch_x_for_pairs(pairs: Sequence[str], *, timeout_s: int = 180) -> Dict[str, Any]:
    """Run paid X fetch scoped to pairs via env PHASE6_X_PAIRS.

    Relies on fetch_x_sentiment.py honoring PHASE6_X_PAIRS (patched companion).
    """
    pairs = [str(p).strip().upper() for p in pairs if str(p).strip()]
    if not pairs:
        return {"ok": False, "error": "empty_pairs", "pairs": []}
    env = os.environ.copy()
    env["OPENBLAS_CORETYPE"] = "GENERIC"
    env["PHASE6_X_PAIRS"] = ",".join(pairs)
    env["PHASE6_X_FORCE_STALE"] = "1"  # probe means we want a fresh pull
    cmd = [str(PROJECT_ROOT / "run_sentiment.sh"), str(X_FETCH)]
    try:
        r = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}", "pairs": pairs}
    out = (r.stdout or "")[-2000:]
    err = (r.stderr or "")[-800:]
    return {
        "ok": r.returncode == 0,
        "returncode": r.returncode,
        "pairs": pairs,
        "stdout_tail": out,
        "stderr_tail": err,
    }


def _read_x_scores(pairs: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    if not X_CACHE.exists():
        return {}
    try:
        cache = json.loads(X_CACHE.read_text())
    except Exception:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for p in pairs:
        row = cache.get(p) or cache.get(p.replace("-USD", "")) or {}
        if isinstance(row, dict) and row:
            out[p] = {
                "sentiment": row.get("sentiment"),
                "post_count": row.get("post_count"),
                "timestamp": row.get("timestamp"),
                "confidence": row.get("confidence"),
            }
    return out


def _maybe_write_latch(pair: str, score: float, floor: float) -> Optional[str]:
    """If score clears tryout floor, write tryout_sent_latch (same path as refresh)."""
    if score is None or float(score) < float(floor):
        return None
    try:
        from phase6.core.tryout_sent_latch import write_latches_from_scores

        write_latches_from_scores(
            {pair: float(score)},
            tryout_pairs=[pair],
            floor=float(floor),
            source="rsi_event_x_probe",
        )
        return "write_latches_from_scores"
    except Exception as e:
        return f"latch_err:{type(e).__name__}:{e}"


def run_probe(
    *,
    dry_run: bool = True,
    spend_x: bool = False,
    top_k: int = 2,
    floor: float = 0.30,
    rsi_max: float = 40.0,
    budget_cfg: Optional[BudgetConfig] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Select top-K wash doors; optionally pay X; never place orders.

    dry_run=True (default): budget check + selection only, no API.
    spend_x=True and dry_run=False: paid fetch under budget.
    """
    now = now or _utc_now()
    budget_cfg = budget_cfg or BudgetConfig()
    cfg = ShadowConfig(
        rsi_wash_max=float(rsi_max),
        top_k=int(top_k),
        tryout_floor=float(floor),
        place_orders=False,
        mutate_config=False,
        spend_x=bool(spend_x) and not dry_run,
    )
    board = build_shadow_board(cfg, now=now)
    selected = list(board.get("selected") or [])
    want = [str(s.get("pair")) for s in selected if s.get("pair")]

    dec = check_can_spend(want, lane="rsi", cfg=budget_cfg, now=now)
    result: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": now.isoformat(),
        "dry_run": bool(dry_run),
        "spend_x_requested": bool(spend_x),
        "spend_x_executed": False,
        "place_orders": False,
        "live_gate": "OFF",
        "edge_class": "ATTENTION_ONLY_sensor_clock_probe",
        "selected_pre": selected,
        "budget": dec.to_dict(),
        "fetched": [],
        "x_scores": {},
        "latch_writes": {},
        "fetch_meta": None,
        "plain_english": "",
        "honesty": [
            "Probe validates sensor clock with real X — not a live buy path.",
            "place_orders always False; runner buy still needs normal gates + seat.",
            "Budget is pair-query hard cap (rsi lane ≤2/day default).",
            "dry_run default — --go required to spend.",
        ],
    }

    if not want:
        result["plain_english"] = (
            f"No RSI-wash+stale doors in top-K (universe={board.get('n_universe')}, "
            f"trigger={board.get('n_trigger_pool')}). Probe idle — no X spend."
        )
        _persist(result, board)
        return result

    if dry_run or not spend_x:
        result["plain_english"] = (
            f"DRY: would probe {dec.allowed_pairs or want} "
            f"(budget allowed={dec.allowed} reason={dec.reason} "
            f"rem_day={dec.remaining_day} rem_rsi={dec.remaining_lane}). "
            f"No API call. live_gate=OFF."
        )
        _persist(result, board)
        return result

    if not dec.allowed or not dec.allowed_pairs:
        result["plain_english"] = (
            f"Budget blocked paid X: {dec.reason} blocked={dec.blocked_pairs}. No spend."
        )
        _persist(result, board)
        return result

    pairs = list(dec.allowed_pairs)
    meta = fetch_x_for_pairs(pairs)
    result["fetch_meta"] = {
        "ok": meta.get("ok"),
        "returncode": meta.get("returncode"),
        "stdout_tail": (meta.get("stdout_tail") or "")[-500:],
        "stderr_tail": (meta.get("stderr_tail") or "")[-300:],
    }
    if not meta.get("ok"):
        result["plain_english"] = f"X fetch failed for {pairs}: {meta.get('error') or meta.get('returncode')}"
        _persist(result, board)
        return result

    # Record spend only after successful fetch
    spent = record_spend(pairs, lane="rsi", cfg=budget_cfg, now=now, note="rsi_event_x_probe")
    result["spend_x_executed"] = bool(spent.get("ok"))
    result["budget_after"] = (spent.get("state") or {})
    result["fetched"] = pairs
    scores = _read_x_scores(pairs)
    result["x_scores"] = scores

    latches: Dict[str, Any] = {}
    for p, row in scores.items():
        s = row.get("sentiment")
        try:
            sf = float(s) if s is not None else None
        except Exception:
            sf = None
        if sf is not None:
            latches[p] = {
                "score": sf,
                "clears_floor": sf >= float(floor),
                "latch": _maybe_write_latch(p, sf, float(floor)),
            }
    result["latch_writes"] = latches

    # Rebuild board against fresh cache for honest post-probe view
    board2 = build_shadow_board(cfg, now=_utc_now())
    write_artifacts(board2)
    result["board_post"] = {
        "n_trigger_pool": board2.get("n_trigger_pool"),
        "n_selected_top_k": board2.get("n_selected_top_k"),
        "n_would_buy_if_x_pass": board2.get("n_would_buy_if_x_pass"),
        "selected": board2.get("selected"),
        "plain_english": board2.get("plain_english"),
    }
    bits = []
    for p in pairs:
        row = latches.get(p) or {}
        bits.append(f"{p} x={row.get('score')} clear={row.get('clears_floor')}")
    result["plain_english"] = (
        f"PAID X probe OK: {', '.join(bits) or pairs}. "
        f"Budget spend recorded. live_gate=OFF · no orders. "
        f"Post board would_buy={ (result.get('board_post') or {}).get('n_would_buy_if_x_pass') }."
    )
    _persist(result, board2)
    return result


def _persist(result: Dict[str, Any], board: Dict[str, Any]) -> None:
    PROBE_LATEST.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(result)
    payload["shadow_board_snip"] = {
        "n_universe": board.get("n_universe"),
        "n_trigger_pool": board.get("n_trigger_pool"),
        "selected": board.get("selected"),
        "plain_english": board.get("plain_english"),
    }
    PROBE_LATEST.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    _append_jsonl(
        PROBE_EVENTS,
        {
            "ts": result.get("as_of"),
            "dry_run": result.get("dry_run"),
            "spend_x_executed": result.get("spend_x_executed"),
            "fetched": result.get("fetched"),
            "budget_reason": (result.get("budget") or {}).get("reason"),
            "plain": result.get("plain_english"),
        },
    )
    lines = [
        f"# RSI-event X probe",
        f"",
        f"- as_of: `{result.get('as_of')}`",
        f"- dry_run: **{result.get('dry_run')}** · spend_executed: **{result.get('spend_x_executed')}**",
        f"- live_gate: **OFF** · place_orders: **false**",
        f"- budget: `{json.dumps(result.get('budget'), default=str)}`",
        f"- fetched: `{result.get('fetched')}`",
        f"- x_scores: `{json.dumps(result.get('x_scores'), default=str)}`",
        f"",
        f"## Plain English",
        f"",
        str(result.get("plain_english") or ""),
        f"",
        f"## Honesty",
        f"",
    ]
    for h in result.get("honesty") or []:
        lines.append(f"- {h}")
    lines.append("")
    MD_REPORT.parent.mkdir(parents=True, exist_ok=True)
    MD_REPORT.write_text("\n".join(lines) + "\n")


def telegram_summary(result: Dict[str, Any], *, floor: float = 0.30) -> str:
    """Operator TG only when it matters (Brad A+C 2026-09-19).

    Ping when:
      - paid X + at least one pair clears tryout floor (latch/would-tryout path), or
      - hard fail (fetch attempted and failed).
    Silent (empty) when:
      - idle / no wash, dry would-probe, budget block, paid-but-under-floor.
    Under-floor spend stays in crumbs/logs — not a daily operator alert.
    """
    if not result:
        return ""

    # Hard fail: spend path tried X and fetch broke
    meta = result.get("fetch_meta") or {}
    if (
        not result.get("dry_run")
        and result.get("spend_x_requested")
        and meta
        and meta.get("ok") is False
    ):
        pe = str(result.get("plain_english") or "X fetch failed")[:280]
        return f"RSI-event X PROBE FAIL: {pe}"

    if not result.get("spend_x_executed"):
        # idle, dry, budget block — log only
        return ""

    fetched = list(result.get("fetched") or [])
    latches = result.get("latch_writes") or {}
    scores = result.get("x_scores") or {}
    fl = float(floor)
    clears: list[str] = []
    for p in fetched:
        row_l = latches.get(p) if isinstance(latches, dict) else None
        if isinstance(row_l, dict) and row_l.get("clears_floor"):
            clears.append(f"{p} x={row_l.get('score')}")
            continue
        row_s = scores.get(p) if isinstance(scores, dict) else None
        if isinstance(row_s, dict):
            raw = row_s.get("sentiment")
            if raw is None:
                continue
            try:
                sf = float(raw)
            except (TypeError, ValueError):
                continue
            if sf >= fl:
                clears.append(f"{p} x={sf}")
    if not clears:
        # paid but all under floor — crumbs only
        return ""
    return (
        "RSI-event X PROBE clear: "
        + "; ".join(clears)
        + " · latch path · live_gate=OFF · no orders"
    )
