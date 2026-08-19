"""
ANALYST-OPT R5: Data-driven honest assessment + evolution notes for daily/weekly briefs.

Voice rules: docs/research/CRYPTO_ANALYST_PERSONALITY.md
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]

PERSONA_ONE_LINER = (
    "Persona: Truth-seeking, direct, no fluff. Cite run_id + metrics. "
    "Production P&L before scenario hype. Occasional dry humor."
)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def format_honest_assessment(
    *,
    full_coverage_count: int,
    total_pairs: int,
    sl_risks: Dict[str, Any],
    opt_brief: Optional[Dict[str, Any]] = None,
    leaderboard: Optional[Dict[str, Any]] = None,
) -> List[str]:
    lines: List[str] = []
    lb = leaderboard or {}
    ob = opt_brief or {}

    prod_ret = ob.get("production_since_go_live_return_pct")
    if prod_ret is None and lb.get("production_since_go_live"):
        prod_ret = (lb["production_since_go_live"].get("metrics") or {}).get("total_return_pct")

    eq = ob.get("production_end_equity_usd")
    trades = ob.get("production_trade_count")
    as_of = (ob.get("production_refreshed_at") or "")[:16]
    meta = ""
    if eq is not None and trades is not None:
        meta = f" | ${eq} equity | {trades} trades"
    if as_of:
        meta += f" | as of {as_of}Z"
    if ob.get("production_deposit_adjusted"):
        meta += " | deposit-adjusted"
    unadj = ob.get("production_total_return_pct_unadjusted")
    netd = ob.get("production_net_external_flows_usd")
    if unadj is not None and prod_ret is not None and abs(float(unadj) - float(prod_ret)) > 1.0:
        meta += f" | raw NAV Δ {float(unadj):+.1f}%"
    if netd is not None and abs(float(netd)) >= 50:
        meta += f" | net deposits ${float(netd):,.0f}"

    if prod_ret is not None:
        if prod_ret < -15:
            lines.append(
                f"Production since go-live is down {prod_ret:.1f}% — that is the scoreboard; "
                f"scenario rankings on older OHLCV do not erase it.{meta}"
            )
        elif prod_ret < 0:
            lines.append(f"Production since go-live: {prod_ret:.1f}% (negative, not catastrophic yet).{meta}")
        else:
            lines.append(
                f"Production since go-live: +{prod_ret:.1f}% — validate drawdown & SL quality.{meta}"
            )

    run_id = ob.get("run_id") or lb.get("run_id")
    winner = ob.get("winner_id")
    win_ret = ob.get("winner_return_pct")
    if run_id and winner is not None and not ob.get("production_refreshed_at"):
        lines.append(
            f"Latest scenario pack `{run_id}`: top scenario `{winner}` "
            f"return_pct={win_ret} on OHLCV window (engine={lb.get('engine_mode', 'unknown')})."
        )
    elif run_id and winner is not None and ob.get("production_refreshed_at"):
        lines.append(
            f"Weekly OPT `{run_id}`: sim winner `{winner}` ({win_ret}% on pack window) — "
            "live P&L above is refreshed daily."
        )

    deploy = ob.get("deployment_hint") or ""
    if "blocked" in deploy.lower() or "hold" in deploy.lower():
        lines.append(f"Deployment: {deploy}")
    elif deploy:
        lines.append(f"Deployment hint: {deploy}")

    try:
        from phase6.research.promotion_gates import evaluate_promotion_gates

        if lb:
            gates = evaluate_promotion_gates(lb)
            if not gates.passed and gates.failures:
                lines.append("Promotion gates FAILED: " + "; ".join(gates.failures[:3]))
            for w in gates.warnings[:2]:
                lines.append(f"Gate warning: {w}")
    except Exception:
        pass

    scorecard = ROOT / "data/state/analyst_regime_scorecard_latest.json"
    if not scorecard.exists():
        lines.append(
            "Regime stress incomplete: no `analyst_regime_scorecard_latest.json` — "
            "bull-only winners are not trustworthy for SL/regime shifts."
        )

    high_sl = sum(
        1
        for r in (sl_risks or {}).values()
        if str(r.get("level", "")).upper() in ("HIGH", "CRITICAL")
    )
    if high_sl:
        lines.append(f"SL layer: {high_sl} pair(s) HIGH/CRITICAL risk — size and re-attach remain fragile.")

    cov_ratio = full_coverage_count / max(total_pairs, 1)
    if cov_ratio < 0.85:
        lines.append(
            f"Coverage patchy ({full_coverage_count}/{total_pairs} FULL) — allocator may be guessing on missing pairs."
        )

    if prod_ret is not None and prod_ret < -20 and win_ret is not None and float(win_ret) > float(prod_ret) + 10:
        lines.append(
            "Calendar mismatch: scenario window is not the same as live pain — do not treat backtest green as proof."
        )

    if not lines:
        lines.append("Insufficient state for assessment — run weekly OPT and refresh production metrics.")

    return lines


def build_evolution_note(
    *,
    full_coverage_count: int,
    total_pairs: int,
    opt_brief: Optional[Dict[str, Any]] = None,
    leaderboard: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    lb = leaderboard or {}
    ob = opt_brief or {}
    prod_ret = ob.get("production_since_go_live_return_pct")
    run_id = ob.get("run_id") or lb.get("run_id") or "n/a"

    thesis = f"Path B scenarios ({run_id}) can suggest knob trials when gates pass."
    outcome = (
        f"Coverage {full_coverage_count}/{total_pairs}. "
        f"Prod since go-live return_pct={prod_ret}. "
        f"Winner={ob.get('winner_id')} on pack window."
    )
    evolution = (
        "Run regime scorecard; fill regime_knob_map from bear/flat winners; "
        "keep shadow+drift before any live config promotion."
    )
    if ob.get("overlap_coverage") == "none":
        evolution = (
            "Extend OHLCV into live period OR compare only since-go-live production metrics; "
            + evolution
        )
    return {"thesis": thesis, "outcome": outcome, "evolution_note": evolution}


def optimization_proposal_candidates(
    opt_brief: Optional[Dict[str, Any]],
    leaderboard: Optional[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Strategic proposal seeds driven by OPT state (merged into daily brief)."""
    out: List[Dict[str, str]] = []
    lb = leaderboard or {}
    ob = opt_brief or {}

    if not (ROOT / "data/state/analyst_regime_scorecard_latest.json").exists():
        out.append(
            {
                "title": "Run regime quad scorecard before next shadow promotion",
                "description": (
                    "Execute `run_regime_scorecard.py` on bull/bear/flat/recent windows; "
                    "update `config/regime_knob_map.json` from per-regime winners. "
                    f"Cite latest run_id `{ob.get('run_id', lb.get('run_id', 'n/a'))}`."
                ),
                "benefits": "Reduces bull-market overconfidence and SL surprises after regime shift.",
                "risks": "Extra compute weekly (mitigation: monthly full quad, weekly recent+bear only).",
                "priority": "High",
                "effort": "Low",
                "category": "ANALYST-OPT / Regime",
            }
        )

    deploy = (ob.get("deployment_hint") or "").lower()
    if "negative" in deploy or "hold" in deploy or "blocked" in deploy:
        out.append(
            {
                "title": "Tighten scenario pack toward positive Sharpe on ARCH-4 holdout",
                "description": (
                    "Current gates block promotion when winner Sharpe < 0. Add scenarios with defensive rotation, "
                    "longer rebalance_freq, and bear-window validation. Document in scenario pack YAML."
                ),
                "benefits": "Only shadow trials with non-losing risk-adjusted profiles reach proposals.",
                "risks": "May reduce nominal return in bull-only sims (mitigation: regime map handles bull separately).",
                "priority": "Medium",
                "effort": "Medium",
                "category": "ANALYST-OPT / Gates",
            }
        )

    if ob.get("overlap_coverage") == "none":
        out.append(
            {
                "title": "Align OHLCV data window with production go-live for fair compare",
                "description": (
                    "Refresh or extend `backtests/data` so scenario windows overlap live trades; "
                    "until then briefs must headline since-go-live production return."
                ),
                "benefits": "Honest scenario vs production narrative; fewer false promotions.",
                "risks": "Data pipeline work (mitigation: incremental pair files).",
                "priority": "Medium",
                "effort": "Medium",
                "category": "ANALYST-OPT / Data",
            }
        )

    return out[:3]


def persist_weekly_assessment(
    lines: List[str],
    evolution: Dict[str, str],
    opt_brief: Optional[Dict[str, Any]],
) -> Path:
    path = ROOT / "data/state/analyst_weekly_assessment_latest.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "persona": PERSONA_ONE_LINER,
        "honest_assessment": lines,
        "evolution": evolution,
        "optimization": opt_brief,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    return path