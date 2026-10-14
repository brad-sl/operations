#!/usr/bin/env python3
"""
Dig-out practical sequence shadow board (measure-only).

§1 C1/D1 would_* logs · §4 intake discipline skips · §5 3% fuse would-arm
No orders. live_apply stays false until Brad GO + production follow-up.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.core.ballast_under_target_floor import would_allow_under_target_step
from phase6.core.flat_deploy_priority import would_prefer_ballast_before_shell
from phase6.core.paths import PROJECT_ROOT, STATE_DIR
from phase6.core.sl_width_would_arm_shadow import evaluate_open_shells_would_arm

logger = logging.getLogger(__name__)

SCHEMA = "dig_out_shadow_board_v1"
REPORTS_DIR = PROJECT_ROOT / "reports"
LATEST = STATE_DIR / "dig_out_shadow_board_latest.json"
HISTORY = STATE_DIR / "dig_out_shadow_board_history.jsonl"
REPORT = REPORTS_DIR / "DIG_OUT_SHADOW_BOARD_LATEST.md"
MATRIX = STATE_DIR / "membership_sizing_matrix_latest.json"
REGIME = STATE_DIR / "regime_cash_status.json"
LIVE = STATE_DIR / "phase6_live_state.json"
DISCIPLINE = STATE_DIR / "tryout_decision_discipline_latest.json"
TRIPLES = STATE_DIR / "tryout_decision_triples.jsonl"
KILL_C = STATE_DIR / "ballast_under_target_floor_KILL"
KILL_D = STATE_DIR / "flat_deploy_priority_KILL"
KILL_W = STATE_DIR / "sl_width_arming_KILL"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> Any:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("load %s failed: %s", path, e)
        return {}


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except (TypeError, ValueError):
        return float(default)


def _equity(matrix: Dict[str, Any], live: Dict[str, Any]) -> float:
    meta = matrix.get("add_room_meta") if isinstance(matrix.get("add_room_meta"), dict) else {}
    eq = _f(meta.get("equity_usd"))
    if eq > 0:
        return eq
    return max(_f(live.get("total_usd")), 1.0)


def _stop_attached_guess(pair: str, live: Dict[str, Any], held: float) -> bool:
    """Conservative: held ballast with stop_gap present elsewhere → True; empty bag N/A True for empty ETH path."""
    if held <= 1.0:
        return True  # empty bag uses new-buy path; stop attaches post-fill
    # Prefer explicit stop maps if present
    for key in ("open_stops", "stops", "stop_orders", "active_stops"):
        blob = live.get(key)
        if isinstance(blob, dict) and pair in blob:
            return True
        if isinstance(blob, list):
            for row in blob:
                if isinstance(row, dict) and str(row.get("pair") or "").upper().replace("_", "-") == pair:
                    return True
    # Unknown → assume attached when held (do not invent naked-risk shadow rejects)
    return True


def _upnl_pct(row: Dict[str, Any], held: float) -> float:
    upnl = row.get("open_upnl_usd")
    if upnl is None or held <= 0:
        return 0.0
    return _f(upnl) / max(held, 1e-9)


def build_board() -> Dict[str, Any]:
    matrix_raw = _load(MATRIX)
    matrix = matrix_raw if isinstance(matrix_raw, dict) else {}
    regime_raw = _load(REGIME)
    regime = regime_raw if isinstance(regime_raw, dict) else {}
    live_raw = _load(LIVE)
    live = live_raw if isinstance(live_raw, dict) else {}
    disc_raw = _load(DISCIPLINE)
    disc = disc_raw if isinstance(disc_raw, dict) else {}

    rows = matrix.get("rows") if isinstance(matrix.get("rows"), list) else []
    eq = _equity(matrix, live)
    reg = str(regime.get("regime") or (matrix.get("regime_sheet") or {}).get("live_regime") or "unknown")
    deploy_cap = _f(regime.get("rebalance_cap_usd"), 75.0)

    btc = next((r for r in rows if str(r.get("pair")) == "BTC-USD"), {})
    eth = next((r for r in rows if str(r.get("pair")) == "ETH-USD"), {})
    btc_held = _f(btc.get("held_usd"))
    eth_held = _f(eth.get("held_usd"))
    tw_btc = _f(btc.get("target_pair_weight"), 0.15)
    tw_eth = _f(eth.get("target_pair_weight"), 0.15)

    floor_rows: List[Dict[str, Any]] = []
    for pair, row in (("BTC-USD", btc), ("ETH-USD", eth)):
        held = _f(row.get("held_usd"))
        tw = _f(row.get("target_pair_weight"), 0.15)
        max_add = row.get("max_add_usd")
        max_add_f = _f(max_add, 0.0) if max_add is not None else 0.0
        # flat_no_stack / empty: max_add None → treat as 0 collapsed for floor probe
        if max_add is None and held < 1.0:
            max_add_f = 0.0
        stop_ok = _stop_attached_guess(pair, live, held)
        res = would_allow_under_target_step(
            pair=pair,
            role=str(row.get("role") or "ballast_core"),
            held_usd=held,
            equity_usd=eq,
            target_w=tw,
            max_add_usd=max_add_f,
            open_upnl_pct=_upnl_pct(row, held),
            stop_attached=stop_ok,
            flat_cap_usd=deploy_cap,
        )
        res["matrix_max_add_usd"] = max_add
        res["matrix_block_reason"] = row.get("block_reason")
        res["held_usd"] = held
        res["target_pair_usd"] = row.get("target_pair_usd") or round(eq * tw, 2)
        floor_rows.append(res)

    priority = would_prefer_ballast_before_shell(
        regime=reg,
        deploy_cap_usd=deploy_cap,
        btc_held=btc_held,
        eth_held=eth_held,
        equity=eq,
        target_w_btc=tw_btc,
        target_w_eth=tw_eth,
        btc_late_run_blocked=False,
        eth_late_run_blocked=False,
    )

    # §4 intake measure: discipline skip crumbs
    skip_n = 0
    seat_n = 0
    last_actions: List[Dict[str, Any]] = []
    if TRIPLES.is_file():
        try:
            lines = TRIPLES.read_text(encoding="utf-8").strip().splitlines()[-200:]
            for line in lines:
                try:
                    t = json.loads(line)
                except Exception:
                    continue
                act = str(t.get("action") or t.get("rung") or "")
                if t.get("would_block_if_live") or act.upper() in ("STAND_DOWN", "SKIP", "BLOCK"):
                    skip_n += 1
                if act.upper() in ("BUY_FULL", "BUY", "FULL_SHELL", "SEAT"):
                    seat_n += 1
                if len(last_actions) < 5:
                    last_actions.append(
                        {
                            "pair": t.get("pair"),
                            "action": act,
                            "would_block_if_live": t.get("would_block_if_live"),
                            "decision_id": t.get("decision_id"),
                        }
                    )
        except Exception as e:
            logger.warning("triples read: %s", e)

    would_arm = evaluate_open_shells_would_arm(matrix_rows=rows, live=live)

    out: Dict[str, Any] = {
        "schema": SCHEMA,
        "as_of": _utc(),
        "live_apply": False,
        "shadow_only": True,
        "kills": {
            "ballast_floor": KILL_C.is_file(),
            "flat_priority": KILL_D.is_file(),
            "sl_width": KILL_W.is_file(),
        },
        "regime": reg,
        "equity_usd": round(eq, 2),
        "deploy_cap_usd": deploy_cap,
        "ballast_snapshot": {
            "btc_held": btc_held,
            "eth_held": eth_held,
            "btc_target_usd": round(eq * tw_btc, 2),
            "eth_target_usd": round(eq * tw_eth, 2),
        },
        "c1_under_target_floor": {
            "n_allow": sum(1 for r in floor_rows if r.get("allow")),
            "rows": floor_rows,
        },
        "d1_flat_priority": priority,
        "b_intake_measure": {
            "discipline_live_apply": bool(disc.get("live_apply")),
            "last_triple": disc.get("last_triple"),
            "triples_window_n": skip_n + seat_n,
            "would_skip_n": skip_n,
            "would_seat_n": seat_n,
            "recent": last_actions,
            "note": "eng floor already live; measure skip/seat rates only — no new refuse hardcode",
        },
        "w2_sl_width_would_arm": would_arm,
        "do_not": [
            "global_stop_8_to_3",
            "liquidate_btc_sol_tia_paxg",
            "paxg_preserve_change",
            "kelly_deploy_pct_promote",
            "dual_agree_auto",
            "flat_cap_blowout",
        ],
        "production_gates": {
            "c2_live_floor": "shadow until Sunday weekly + Brad GO live floor",
            "d2_live_priority": "shadow until Sunday weekly + Brad GO live priority",
            "w2_3pct_fuse": "14d would_arm shadow then Brad GO; tryout corpses only",
            "partial_trail_residual": "CF measure only; no live TP shape change",
        },
    }
    return out


def write_report(board: Dict[str, Any]) -> str:
    c1 = board.get("c1_under_target_floor") or {}
    d1 = board.get("d1_flat_priority") or {}
    b = board.get("b_intake_measure") or {}
    w = board.get("w2_sl_width_would_arm") or {}
    snap = board.get("ballast_snapshot") or {}
    lines = [
        "# Dig-out shadow board (LATEST)",
        "",
        f"**as_of:** {board.get('as_of')} · **live_apply:** false · **regime:** {board.get('regime')}",
        f"**equity:** ${board.get('equity_usd')} · **deploy_cap:** ${board.get('deploy_cap_usd')}",
        "",
        "## Ballast",
        f"- BTC held ${snap.get('btc_held')} vs target ${snap.get('btc_target_usd')}",
        f"- ETH held ${snap.get('eth_held')} vs target ${snap.get('eth_target_usd')}",
        "",
        "## §1 C1 under-target floor (would_allow)",
        f"- n_allow={c1.get('n_allow')}",
    ]
    for r in c1.get("rows") or []:
        lines.append(
            f"  - {r.get('pair')}: allow={r.get('allow')} step=${r.get('step_usd')} "
            f"reasons={r.get('reasons')} held=${r.get('held_usd')} max_add={r.get('matrix_max_add_usd')}"
        )
    lines += [
        "",
        "## §1 D1 flat priority (would_prefer_ballast)",
        f"- would_prefer_ballast={d1.get('would_prefer_ballast')} reserve=${d1.get('reserve_usd')} "
        f"shells_ok={d1.get('shells_ok')} reasons={d1.get('reasons')}",
        "",
        "## §4 Intake discipline measure",
        f"- discipline_live_apply={b.get('discipline_live_apply')} "
        f"would_skip_n={b.get('would_skip_n')} would_seat_n={b.get('would_seat_n')}",
        f"- note: {b.get('note')}",
        "",
        "## §5 3% fuse would_arm (open shells)",
        f"- n_open_eval={w.get('n_eval')} would_arm_3pct={w.get('n_would_3pct')} "
        f"would_arm_8pct={w.get('n_would_8pct')}",
        "",
        "## Do-not (still locked)",
    ]
    for x in board.get("do_not") or []:
        lines.append(f"- {x}")
    lines += ["", "## Production gates"]
    for k, v in (board.get("production_gates") or {}).items():
        lines.append(f"- **{k}:** {v}")
    lines += [
        "",
        f"State: `{LATEST.relative_to(PROJECT_ROOT)}`",
        f"History: `{HISTORY.relative_to(PROJECT_ROOT)}`",
    ]
    text = "\n".join(lines) + "\n"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    return text


def run_and_persist() -> Dict[str, Any]:
    board = build_board()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(board, indent=2, default=str) + "\n", encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(board, default=str) + "\n")
    write_report(board)
    return board


def telegram_quiet(board: Dict[str, Any]) -> str:
    """Always non-empty header for no_agent cron (Hermes skips empty stdout)."""
    c1 = board.get("c1_under_target_floor") or {}
    d1 = board.get("d1_flat_priority") or {}
    w = board.get("w2_sl_width_would_arm") or {}
    return (
        f"Dig-out shadow · {str(board.get('as_of') or '')[:19]}Z · "
        f"reg={board.get('regime')} · "
        f"C1_allow={c1.get('n_allow')} · "
        f"D1_prefer={d1.get('would_prefer_ballast')} res=${d1.get('reserve_usd')} · "
        f"W2_3pct={w.get('n_would_3pct')}/{w.get('n_eval')} · live_apply=OFF"
    )


if __name__ == "__main__":
    b = run_and_persist()
    print(telegram_quiet(b))
    print(f"report: {REPORT}")
    print(f"state: {LATEST}")
