"""Sunday decision packet for bank/trail-while-green triple shadow.

Measure-only. Never flips live_apply. Gates decide N_INSUFFICIENT /
SIGNAL_THIN / READY_FOR_LETTER_GO from the CF summary + per-leg deltas.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/home/brad/projects/crypto-trading-bot")
DEFAULT_DECISION_CFG = ROOT / "config" / "bank_trail_while_green_decision.json"
DEFAULT_SHADOW_CFG = ROOT / "config" / "bank_trail_while_green_shadow.json"
DEFAULT_OUT_JSON = ROOT / "data" / "state" / "bank_trail_while_green_sunday_review_latest.json"
DEFAULT_OUT_MD = ROOT / "reports" / "BANK_TRAIL_WHILE_GREEN_SUNDAY_REVIEW_LATEST.md"


def load_decision_cfg(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_DECISION_CFG
    return json.loads(p.read_text(encoding="utf-8"))


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _arm_leg_deltas(legs: list[dict[str, Any]], arm: str) -> list[float]:
    out: list[float] = []
    for r in legs:
        a = r.get(arm) or {}
        if not a.get("would_arm"):
            continue
        out.append(_f(a.get("delta_vs_actual_usd")))
    return out


def _single_leg_share(deltas: list[float]) -> float:
    if not deltas:
        return 0.0
    abs_sum = sum(abs(d) for d in deltas)
    if abs_sum <= 1e-12:
        return 0.0
    return max(abs(d) for d in deltas) / abs_sum


def evaluate_decision(
    cf_payload: dict[str, Any],
    *,
    decision_cfg: dict[str, Any] | None = None,
    shadow_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return decision packet from a CF run payload (summary + legs)."""
    dcfg = decision_cfg or load_decision_cfg()
    scfg = shadow_cfg or {}
    if not scfg and DEFAULT_SHADOW_CFG.exists():
        scfg = json.loads(DEFAULT_SHADOW_CFG.read_text(encoding="utf-8"))

    gates = dict(dcfg.get("gates") or {})
    verdicts = dict(dcfg.get("verdicts") or {})
    summary = cf_payload.get("summary") or {}
    legs = list(cf_payload.get("legs") or [])
    wo = summary.get("would_arm_only") or {}

    n_would = int(summary.get("n_would_arm_legs") or 0)
    n_legs = int(summary.get("n_legs") or 0)
    winner = summary.get("winner_would_arm_only")

    arm_rows: dict[str, dict[str, Any]] = {}
    for k in ("A", "C", "AC"):
        a = wo.get(k) or {}
        deltas = _arm_leg_deltas(legs, k)
        arm_rows[k] = {
            "n": int(a.get("n") or len(deltas) or 0),
            "sum_delta_vs_actual_usd": _f(a.get("sum_delta_vs_actual_usd")),
            "median_delta_vs_actual_usd": _f(a.get("median_delta_vs_actual_usd")),
            "sum_pnl_usd": _f(a.get("sum_pnl_usd")),
            "single_leg_share": round(_single_leg_share(deltas), 4),
            "leg_deltas": [round(x, 4) for x in deltas],
        }

    # rank by sum delta on would-arm board
    ranked = sorted(
        ((k, arm_rows[k]["sum_delta_vs_actual_usd"]) for k in ("A", "C", "AC")),
        key=lambda x: x[1],
        reverse=True,
    )
    if winner not in ("A", "C", "AC") and ranked:
        winner = ranked[0][0]

    w_stats = arm_rows.get(winner or "C") or {}
    second_sum = ranked[1][1] if len(ranked) > 1 else 0.0
    winner_sum = _f(w_stats.get("sum_delta_vs_actual_usd"))
    winner_med = _f(w_stats.get("median_delta_vs_actual_usd"))
    winner_share = _f(w_stats.get("single_leg_share"))
    gap = winner_sum - second_sum

    shadow_live = bool(scfg.get("live_apply"))
    decision_live = bool(dcfg.get("live_apply"))
    live_flag = shadow_live or decision_live

    failures: list[str] = []
    checks: dict[str, Any] = {
        "n_would_arm_legs": {
            "value": n_would,
            "min": int(gates.get("min_would_arm_legs") or 5),
            "pass": n_would >= int(gates.get("min_would_arm_legs") or 5),
        },
        "winner_sum_delta_usd": {
            "value": round(winner_sum, 4),
            "min": _f(gates.get("min_sum_delta_usd"), 15.0),
            "pass": winner_sum >= _f(gates.get("min_sum_delta_usd"), 15.0),
        },
        "winner_median_delta_usd": {
            "value": round(winner_med, 4),
            "min": _f(gates.get("min_median_delta_usd"), 0.5),
            "pass": winner_med >= _f(gates.get("min_median_delta_usd"), 0.5),
        },
        "single_leg_share": {
            "value": round(winner_share, 4),
            "max": _f(gates.get("max_single_leg_share_of_abs_sum_delta"), 0.55),
            "pass": winner_share <= _f(gates.get("max_single_leg_share_of_abs_sum_delta"), 0.55)
            if n_would > 0
            else False,
        },
        "winner_gap_vs_second_usd": {
            "value": round(gap, 4),
            "min": _f(gates.get("require_winner_beats_second_by_usd"), 5.0),
            "pass": gap >= _f(gates.get("require_winner_beats_second_by_usd"), 5.0)
            if n_would > 0
            else False,
        },
        "live_apply_still_false": {
            "value": not live_flag,
            "pass": (not live_flag) if gates.get("require_live_apply_still_false", True) else True,
        },
    }

    for name, c in checks.items():
        if not c.get("pass"):
            failures.append(name)

    if live_flag and gates.get("require_live_apply_still_false", True):
        verdict = "BLOCKED_LIVE_FLAG"
    elif n_would < int(gates.get("min_would_arm_legs") or 5):
        verdict = "N_INSUFFICIENT"
    elif any(
        f in failures
        for f in (
            "winner_sum_delta_usd",
            "winner_median_delta_usd",
            "single_leg_share",
            "winner_gap_vs_second_usd",
        )
    ):
        verdict = "SIGNAL_THIN"
    else:
        verdict = "READY_FOR_LETTER_GO"

    # recommend arm only when ready; else null
    recommend_arm = winner if verdict == "READY_FOR_LETTER_GO" else None
    letter_go_line = None
    if recommend_arm:
        letter_go_line = (
            f"Letter GO candidate: arm **{recommend_arm}** only "
            f"(would-arm n={n_would}, sum Δ$={winner_sum:.2f}, med Δ$={winner_med:.2f}). "
            "Reply e.g. `GO bank-trail C` to authorize live gap-fill design — this job still does not flip."
        )

    plain = {
        "N_INSUFFICIENT": (
            f"Not enough data yet: would-arm legs **{n_would}** "
            f"(need ≥{gates.get('min_would_arm_legs', 5)}). Keep shadow. No GO."
        ),
        "SIGNAL_THIN": (
            f"n={n_would} but signal thin on primary board "
            f"(winner={winner}, sum Δ$={winner_sum:.2f}, med={winner_med:.2f}, "
            f"leg_share={winner_share:.0%}, gap=${gap:.2f}). Keep shadow."
        ),
        "READY_FOR_LETTER_GO": (
            f"Gates pass. Winner **{winner}** on would-arm board "
            f"(n={n_would}, sum Δ$={winner_sum:.2f}). Ready for **letter GO** only — no auto flip."
        ),
        "BLOCKED_LIVE_FLAG": (
            "live_apply already true on shadow/decision config — audit before any further GO."
        ),
    }.get(verdict, verdict)

    return {
        "schema": "bank_trail_while_green_sunday_review_v1",
        "status": "MEASURE_ONLY",
        "live_apply": False,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "cf_as_of": cf_payload.get("as_of"),
        "cf_since": cf_payload.get("since"),
        "verdict": verdict,
        "verdict_text": verdicts.get(verdict) or plain,
        "plain": plain,
        "recommend_arm": recommend_arm,
        "letter_go_line": letter_go_line,
        "winner_would_arm_only": winner,
        "n_legs": n_legs,
        "n_would_arm_legs": n_would,
        "arm_board_would_arm_only": arm_rows,
        "ranked_by_sum_delta": [{"arm": k, "sum_delta_usd": round(v, 4)} for k, v in ranked],
        "gates": gates,
        "checks": checks,
        "failures": failures,
        "do_not": list(dcfg.get("do_not") or []),
        "shadow_live_apply": shadow_live,
        "decision_cfg_live_apply": decision_live,
        "next_action": {
            "N_INSUFFICIENT": "Keep weekly CF collecting; re-review next Sunday.",
            "SIGNAL_THIN": "Keep shadow; optional sensitivity on arm_mfe / lock_frac — still no live.",
            "READY_FOR_LETTER_GO": "Ask Brad for letter GO naming the arm; design live gap-fill only after GO.",
            "BLOCKED_LIVE_FLAG": "Audit config live_apply flags immediately.",
        }.get(verdict),
    }


def format_md(decision: dict[str, Any], cf_summary: dict[str, Any] | None = None) -> str:
    s = cf_summary or {}
    lines = [
        "# Bank / trail while green — Sunday review",
        "",
        f"**Status:** MEASURE_ONLY · `live_apply: false`",
        f"**As of:** {decision.get('as_of')}",
        f"**CF since:** {decision.get('cf_since')}",
        f"**Verdict:** `{decision.get('verdict')}`",
        "",
        decision.get("plain") or "",
        "",
        "## Gates",
        "",
        "| Check | value | bar | pass |",
        "|-------|-------|-----|------|",
    ]
    for name, c in (decision.get("checks") or {}).items():
        bar = c.get("min", c.get("max", ""))
        lines.append(
            f"| {name} | {c.get('value')} | {bar} | {'✓' if c.get('pass') else '✗'} |"
        )
    lines += [
        "",
        f"**Failures:** {', '.join(decision.get('failures') or []) or '(none)'}",
        "",
        "## Primary board (would-arm only)",
        "",
        "| Arm | n | sum Δ$ | median Δ$ | single-leg share |",
        "|-----|---|--------|-----------|------------------|",
    ]
    board = decision.get("arm_board_would_arm_only") or {}
    for k in ("A", "C", "AC"):
        a = board.get(k) or {}
        lines.append(
            f"| **{k}** | {a.get('n')} | {a.get('sum_delta_vs_actual_usd')} | "
            f"{a.get('median_delta_vs_actual_usd')} | {a.get('single_leg_share')} |"
        )
    lines += [
        "",
        f"**Winner:** `{decision.get('winner_would_arm_only')}`",
        f"**Recommend arm:** `{decision.get('recommend_arm')}`",
        "",
    ]
    if decision.get("letter_go_line"):
        lines += [decision["letter_go_line"], ""]
    lines += [
        f"**Next:** {decision.get('next_action')}",
        "",
        "## Do not",
        "",
    ]
    for d in decision.get("do_not") or []:
        lines.append(f"- {d}")
    lines += [
        "",
        "## CF snapshot",
        "",
        f"- n_legs={s.get('n_legs')} · n_would_arm={s.get('n_would_arm_legs')}",
        f"- actual_pnl_sum={s.get('actual_pnl_sum')}",
        f"- full CF: `reports/BANK_TRAIL_WHILE_GREEN_CF_LATEST.md`",
        "",
        "_This packet never flips money. Letter GO from Brad is required before live design._",
        "",
    ]
    return "\n".join(lines) + "\n"


def format_tg_card(decision: dict[str, Any]) -> str:
    """Short Telegram-friendly card (stdout for no_agent or agent inject)."""
    board = decision.get("arm_board_would_arm_only") or {}
    lines = [
        "Bank/trail-while-green — Sunday review (MEASURE_ONLY)",
        f"Verdict: {decision.get('verdict')}",
        decision.get("plain") or "",
        f"n_legs={decision.get('n_legs')} would_arm={decision.get('n_would_arm_legs')} "
        f"winner={decision.get('winner_would_arm_only')}",
    ]
    for k in ("A", "C", "AC"):
        a = board.get(k) or {}
        lines.append(
            f"  {k}: n={a.get('n')} sumΔ=${a.get('sum_delta_vs_actual_usd')} "
            f"med=${a.get('median_delta_vs_actual_usd')} share={a.get('single_leg_share')}"
        )
    fails = decision.get("failures") or []
    if fails:
        lines.append(f"Failed gates: {', '.join(fails)}")
    if decision.get("letter_go_line"):
        lines.append(str(decision["letter_go_line"]))
    else:
        lines.append(f"Next: {decision.get('next_action')}")
    lines.append("No live flip from this job. No global 8→3.")
    lines.append("Report: reports/BANK_TRAIL_WHILE_GREEN_SUNDAY_REVIEW_LATEST.md")
    return "\n".join(lines) + "\n"


def write_decision_outputs(
    decision: dict[str, Any],
    *,
    cf_summary: dict[str, Any] | None = None,
    out_json: Path | None = None,
    out_md: Path | None = None,
) -> dict[str, str]:
    oj = out_json or DEFAULT_OUT_JSON
    om = out_md or DEFAULT_OUT_MD
    oj.parent.mkdir(parents=True, exist_ok=True)
    om.parent.mkdir(parents=True, exist_ok=True)
    try:
        from phase6.research.measure_collect_health import health_bank_trail

        bh = health_bank_trail()
        decision = dict(decision)
        decision["measure_health"] = bh
        decision["collect_clock_ok"] = bool(bh.get("collect_clock_ok"))
        decision["measure_health_code"] = bh.get("code")
        # Gate: health fail → never imply letter GO
        if not bh.get("collect_clock_ok"):
            decision["letter_go_blocked_by_measure_health"] = True
            if decision.get("letter_go_line"):
                decision["letter_go_line_suppressed"] = decision.get("letter_go_line")
                decision["letter_go_line"] = (
                    f"NO_GO_FIX_METER · bank_trail health={bh.get('code')} "
                    f"(clock_FROZEN). {bh.get('plain_english')}"
                )
    except Exception as e:
        decision = dict(decision)
        decision["measure_health"] = {
            "ok": False,
            "code": "sensor_broken",
            "plain_english": f"health attach failed: {e}",
            "collect_clock_ok": False,
        }
    oj.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    om.write_text(format_md(decision, cf_summary), encoding="utf-8")
    return {"json": str(oj), "md": str(om)}
