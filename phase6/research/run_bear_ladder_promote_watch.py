#!/usr/bin/env python3
"""Bear ladder promote-watch — don't lose the FEAT after real bear data arrives.

no_agent cron: print Telegram body only on meaningful change / gate ready.
Silent (empty stdout) when nothing new — avoids spam.

Never flips live_apply. Brad still OK's the live switch.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

STATE = ROOT / "data" / "state"
CFG = ROOT / "config" / "bear_profit_take.json"
STATUS = STATE / "bear_profit_take_shadow_status.json"
COLL = STATE / "bear_profit_take_collection.json"
CF = STATE / "bear_ladder_path_cf_latest.json"
REGIME = STATE / "regime_cash_status.json"
WATCH = STATE / "bear_ladder_promote_watch.json"
OUT_MD = ROOT / "reports" / "BEAR_LADDER_PROMOTE_WATCH_LATEST.md"


def _load(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _snapshot() -> Dict[str, Any]:
    cfg = _load(CFG)
    st = _load(STATUS)
    coll = _load(COLL)
    cf = _load(CF)
    reg = _load(REGIME)
    prom = cfg.get("promotion") or {}

    regime = str(st.get("regime") or reg.get("regime") or "unknown").lower()
    episodes = int(
        st.get("n_episodes_total")
        or coll.get("n_episodes_total")
        or 0
    )
    multi = int(st.get("n_pairs_multi_slice") or coll.get("n_pairs_multi_slice") or 0)
    bear_days = int(
        st.get("bear_calendar_days")
        or coll.get("bear_calendar_days")
        or 0
    )
    min_ep = int(prom.get("min_ladder_episodes") or 10)
    min_days = int(prom.get("shadow_min_bear_calendar_days") or 30)
    min_multi = int(prom.get("min_multi_slice_episodes") or 5)
    cf_call = str(cf.get("recommendation") or prom.get("path_cf_call") or "unknown")
    live = bool(cfg.get("live_apply"))
    mode = str(cfg.get("mode") or "shadow")
    enabled = bool(cfg.get("enabled", True))

    path_ok = cf_call == "pursue_shadow"
    ep_ok = episodes >= min_ep
    days_ok = bear_days >= min_days
    multi_ok = multi >= min_multi
    # multi_slice soft: if no multi field yet, don't hard-block ready on multi alone
    gates_ready = (
        enabled
        and mode == "shadow"
        and not live
        and path_ok
        and ep_ok
        and days_ok
    )

    if live or mode == "live":
        phase = "already_live_audit"
    elif regime == "bear" and episodes == 0 and bear_days <= 1:
        phase = "bear_just_started"
    elif regime == "bear":
        phase = "bear_collecting"
    elif gates_ready:
        phase = "ready_for_brad_go"
    elif path_ok and (episodes > 0 or bear_days > 0):
        phase = "partial_data"
    else:
        phase = "waiting_for_bear"

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "regime": regime,
        "mode": mode,
        "live_apply": live,
        "enabled": enabled,
        "path_cf_call": cf_call,
        "episodes": episodes,
        "min_episodes": min_ep,
        "bear_days": bear_days,
        "min_bear_days": min_days,
        "multi_slice_pairs": multi,
        "min_multi": min_multi,
        "gates": {
            "path_cf": path_ok,
            "episodes": ep_ok,
            "bear_days": days_ok,
            "multi_slice_soft": multi_ok,
            "ready_for_brad_go": gates_ready,
        },
        "brad_intent": "promote_asap_when_real_data_gates_met",
        "live_flip_allowed_by_watch": False,
    }


def _should_alert(cur: Dict[str, Any], prev: Dict[str, Any]) -> Tuple[bool, str]:
    """Alert on phase change, first bear day, episode milestones, or gates ready."""
    if not prev:
        # first run: only alert if already interesting
        if cur["phase"] in ("bear_just_started", "bear_collecting", "ready_for_brad_go", "partial_data"):
            return True, "baseline_interesting"
        return False, "baseline_quiet"

    if cur.get("phase") != prev.get("phase"):
        return True, f"phase {prev.get('phase')} → {cur.get('phase')}"

    if cur["phase"] == "ready_for_brad_go" and not prev.get("gates", {}).get("ready_for_brad_go"):
        return True, "gates_ready"

    # episode milestones: 1, 5, 10, then every +5
    ep, pep = int(cur.get("episodes") or 0), int(prev.get("episodes") or 0)
    if ep > pep:
        for m in (1, 5, 10, 15, 20, 30, 50):
            if pep < m <= ep:
                return True, f"episodes hit {m}"

    bd, pbd = int(cur.get("bear_days") or 0), int(prev.get("bear_days") or 0)
    if bd > pbd and cur.get("regime") == "bear":
        if bd in (1, 7, 14, 30) or bd > pbd and bd >= 30:
            return True, f"bear_days={bd}"

    if cur.get("regime") == "bear" and prev.get("regime") != "bear":
        return True, "regime_entered_bear"

    return False, ""


def _format_msg(cur: Dict[str, Any], reason: str) -> str:
    g = cur.get("gates") or {}
    lines = [
        "🐻 Bear ladder — promote watch",
        f"Why ping: {reason}",
        "",
        f"Phase: {cur.get('phase')}",
        f"Regime now: {cur.get('regime')}",
        f"Path CF: {cur.get('path_cf_call')} · shadow mode={cur.get('mode')} live={cur.get('live_apply')}",
        f"Episodes: {cur.get('episodes')}/{cur.get('min_episodes')}",
        f"Bear calendar days: {cur.get('bear_days')}/{cur.get('min_bear_days')}",
        f"Multi-slice pairs: {cur.get('multi_slice_pairs')}/{cur.get('min_multi')} (soft)",
        f"Gates ready for your GO: {g.get('ready_for_brad_go')}",
        "",
    ]
    if g.get("ready_for_brad_go"):
        lines += [
            "✅ Collection gates met on paper.",
            "Brad intent: turn ON ASAP with real data.",
            "Still needs your explicit live flip — watch does NOT auto-promote.",
            "Say: enable bear ladder live / live_apply bear profit take",
            "",
        ]
    elif cur.get("phase") in ("bear_just_started", "bear_collecting"):
        lines += [
            "Real bear (or collecting) — ladder shadow should be arming.",
            "Keep runner up; no live sells yet.",
            "",
        ]
    elif cur.get("phase") == "waiting_for_bear":
        lines += [
            "Still waiting for a labeled bear regime to collect live episodes.",
            "",
        ]
    lines += [
        "Winning path: residual × bounce ≥2 slices × no FOMO rebuy",
        "Docs: docs/research/BEAR_LADDER_TRADE_OPT_PROCEED.md",
        "MASTER: P6-BEAR-PROFIT-TAKE-SHADOW-20260820",
    ]
    return "\n".join(lines)


def main() -> int:
    cur = _snapshot()
    prev = _load(WATCH).get("last_snapshot") or {}
    alert, reason = _should_alert(cur, prev)

    WATCH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_run": cur.get("as_of"),
        "last_snapshot": cur,
        "last_alert_reason": reason if alert else (WATCH.exists() and _load(WATCH).get("last_alert_reason")),
        "last_alert_at": cur.get("as_of") if alert else _load(WATCH).get("last_alert_at"),
    }
    WATCH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    md = [
        "# Bear ladder promote watch",
        "",
        f"**As of:** {cur.get('as_of')}",
        f"**Phase:** `{cur.get('phase')}`",
        f"**Alert this tick:** {alert} ({reason or 'silent'})",
        "",
        f"- Regime: {cur.get('regime')}",
        f"- Episodes: {cur.get('episodes')}/{cur.get('min_episodes')}",
        f"- Bear days: {cur.get('bear_days')}/{cur.get('min_bear_days')}",
        f"- Path CF: {cur.get('path_cf_call')}",
        f"- Ready for Brad GO: {(cur.get('gates') or {}).get('ready_for_brad_go')}",
        "",
        "Brad intent: promote ASAP when real data gates met. No auto live.",
        "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    if alert:
        print(_format_msg(cur, reason))
    # empty stdout = silent cron delivery
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
