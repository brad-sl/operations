#!/usr/bin/env python3
"""
Dedicated Retrospective Analyzer for Polymarket Tilt / Tie-Breaker Signal.

Designed to be:
- Called automatically by the daily intelligence report (crypto-analyst status).
- Run standalone by the analyst for deeper dives: `python phase6/scripts/analyze_pm_tilt_retrospective.py`
- Used to generate data-backed tuning suggestions that feed the Tuning Protocol and strategic proposals.

Focus: Measure PM's marginal value as a *tie-breaker* (when X/Reddit neutral but other factors like price_declining suggest movement).

Outputs structured results + concrete suggestions for the decision matrix / allocator.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Project root detection (keep it simple and robust)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DECISION_LOG = PROJECT_ROOT / "data/state/decision_context_log.jsonl"
INFLUENCE_LOG = PROJECT_ROOT / "data/state/influence_stack_log.jsonl"
REBALANCE_DIR = PROJECT_ROOT / "data/state/rebalance_history"
TRADES_JSONL = PROJECT_ROOT / "trades/phase6_trades.jsonl"

DEFAULT_NEUTRAL_THRESHOLDS = {
    "x_strength": 0.15,
    "reddit_strength": 0.10,
}


def _load_jsonl(path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    if limit:
        lines = lines[-limit:]
    out = []
    for line in lines:
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Handles both with and without Z / offset
        ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def load_data() -> Dict[str, Any]:
    decisions = _load_jsonl(DECISION_LOG)
    influences = _load_jsonl(INFLUENCE_LOG)
    rebalances = []
    for p in REBALANCE_DIR.glob("*.jsonl"):
        rebalances.extend(_load_jsonl(p))

    trades = []
    if TRADES_JSONL.exists():
        trades = _load_jsonl(TRADES_JSONL)

    return {
        "decisions": decisions,
        "influences": influences,
        "rebalances": rebalances,
        "trades": trades,
        "loaded_at": datetime.utcnow().isoformat(),
    }


def identify_tiebreaker_periods(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Find periods where PM was explicitly used (or would have been) as tie-breaker."""
    periods = []
    for d in data["decisions"]:
        if not isinstance(d, dict):
            continue
        if d.get("pm_used_as_tiebreaker") is True:
            periods.append({
                "timestamp": d.get("timestamp"),
                "pm_bias": d.get("pm_bias"),
                "pm_conf": d.get("pm_conf"),
                "x_neutral": d.get("x_neutral"),
                "reddit_neutral": d.get("reddit_neutral"),
                "other_factors": d.get("other_factors", {}),
                "regime_mult": d.get("regime_mult_applied"),
            })
    return periods


def bucket_rebalances_around_tiebreakers(
    data: Dict[str, Any],
    tiebreaker_periods: List[Dict[str, Any]],
    window_hours: int = 6,
) -> Dict[str, Any]:
    """Associate rebalances with nearby tie-breaker decisions."""
    if not tiebreaker_periods:
        return {"tied_rebalances": [], "baseline_rebalances": data.get("rebalances", [])}

    tied = []
    baseline = []

    for rb in data.get("rebalances", []):
        rb_ts = _parse_ts(rb.get("timestamp", ""))
        if not rb_ts:
            baseline.append(rb)
            continue

        matched = False
        for tb in tiebreaker_periods:
            tb_ts = _parse_ts(tb.get("timestamp", ""))
            if not tb_ts:
                continue
            delta = abs((rb_ts - tb_ts).total_seconds()) / 3600
            if delta <= window_hours:
                rb_copy = dict(rb)
                rb_copy["tiebreaker_context"] = {
                    "pm_bias": tb.get("pm_bias"),
                    "other_factors": tb.get("other_factors"),
                    "regime_mult": tb.get("regime_mult"),
                    "delta_hours": round(delta, 1),
                }
                tied.append(rb_copy)
                matched = True
                break
        if not matched:
            baseline.append(rb)

    return {
        "tied_rebalances": tied,
        "baseline_rebalances": baseline,
    }


def compute_lift_metrics(buckets: Dict[str, Any]) -> Dict[str, Any]:
    """Compute simple lift between tie-breaker influenced vs baseline rebalances."""
    tied = buckets.get("tied_rebalances", [])
    baseline = buckets.get("baseline_rebalances", [])

    def _stats(events: List[Dict]) -> Dict[str, Any]:
        if not events:
            return {"count": 0}
        executed = sum(e.get("executed", 0) for e in events)
        capital = sum(e.get("capital_deployed_usd", 0) for e in events)
        return {
            "count": len(events),
            "total_executed": executed,
            "avg_capital_per_event": round(capital / max(1, len(events)), 1),
            "reasons": list(set(e.get("reason", "unknown") for e in events)),
        }

    tied_stats = _stats(tied)
    base_stats = _stats(baseline)

    lift = {}
    if base_stats["count"] > 0 and tied_stats["count"] > 0:
        lift["capital_deployed_delta_pct"] = round(
            ((tied_stats["avg_capital_per_event"] or 0) / (base_stats["avg_capital_per_event"] or 1) - 1) * 100, 1
        )

    return {
        "tiebreaker_influenced": tied_stats,
        "baseline": base_stats,
        "lift": lift,
        "note": "Positive lift suggests value in the tilt when conditions met. Data still sparse until more decisions are logged.",
    }


def analyze_other_factors_correlation(tiebreaker_periods: List[Dict[str, Any]]) -> Dict[str, Any]:
    """See which other_factors co-occur with tie-breaker activations."""
    if not tiebreaker_periods:
        return {"price_declining_rate": None, "volume_spike_rate": None, "note": "No tie-breaker periods yet."}

    declining = sum(1 for p in tiebreaker_periods if p.get("other_factors", {}).get("price_declining"))
    vol = sum(1 for p in tiebreaker_periods if p.get("other_factors", {}).get("volume_spike"))
    total = len(tiebreaker_periods)

    return {
        "total_tiebreaker_activations": total,
        "price_declining_rate": round(declining / total, 3) if total else None,
        "volume_spike_rate": round(vol / total, 3) if total else None,
        "common_other_factors": list(set(
            k for p in tiebreaker_periods for k, v in p.get("other_factors", {}).items() if v
        )),
    }


def generate_tuning_suggestions(
    tiebreaker_periods: List[Dict[str, Any]],
    metrics: Dict[str, Any],
    factors: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Produce analyst-ready tuning suggestions for the decision matrix / allocator."""
    suggestions = []

    if not tiebreaker_periods:
        suggestions.append({
            "type": "instrumentation",
            "priority": "high",
            "title": "Continue collecting decision_context with PM tie-breaker flags",
            "suggestion": "Run rebalances and ensure influence_stack + decision logs are populated. Current retrospective shows 0 historical activations because PM bias has been flat at 0.5.",
            "matrix_change": None,
        })
        return suggestions

    # Example data-driven suggestions
    if factors.get("price_declining_rate", 0) and factors["price_declining_rate"] > 0.5:
        suggestions.append({
            "type": "matrix_tune",
            "priority": "medium",
            "title": "Boost regime_mult when price_declining + tie-breaker",
            "suggestion": "When pm_used_as_tiebreaker=True and other_factors.price_declining=True, consider extra +0.1 to +0.2 on regime_mult (or lower the min_pairs threshold in _detect_declining_trend).",
            "matrix_change": {
                "path": "tilt_effects.risk_on.regime_mult_boost",
                "current": "current range",
                "proposed": "add conditional +0.1 when price_declining",
            },
        })

    if metrics.get("lift", {}).get("capital_deployed_delta_pct", 0) > 5:
        suggestions.append({
            "type": "allocator_tune",
            "priority": "medium",
            "title": "Relax rebalance_cap or deploy_pct on confirmed tie-breakers",
            "suggestion": "Observed higher capital deployment in tie-breaker windows. Consider small increase to rebalance_cap_usd (e.g. +10-20%) when tie-breaker active.",
            "matrix_change": None,
        })

    # Always include a general one for the analyst
    suggestions.append({
        "type": "protocol",
        "priority": "low",
        "title": "Add explicit 'other_factors' weighting in future matrix versions",
        "suggestion": "Extend decision matrix with weights for price_declining and volume_spike so the tilt strength can be modulated (e.g. full tilt only when 1+ other factors present).",
    })

    return suggestions


def run_pm_tilt_analysis(window_hours: int = 6) -> Dict[str, Any]:
    """Main entry point. Returns a rich dict suitable for printing or feeding the intelligence report."""
    data = load_data()
    tie_periods = identify_tiebreaker_periods(data)
    buckets = bucket_rebalances_around_tiebreakers(data, tie_periods, window_hours=window_hours)
    metrics = compute_lift_metrics(buckets)
    factor_stats = analyze_other_factors_correlation(tie_periods)
    suggestions = generate_tuning_suggestions(tie_periods, metrics, factor_stats)

    # Try to leverage existing TradeLedger regime analysis if trades exist
    ledger_analysis = None
    try:
        from phase6.core.trade_ledger import TradeLedger
        ledger = TradeLedger(base_dir=PROJECT_ROOT)
        ledger_analysis = ledger.analyze_regime_impact(min_trades=5)
    except Exception:
        pass

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "data_summary": {
            "decisions_loaded": len(data["decisions"]),
            "influences_loaded": len(data["influences"]),
            "rebalances_loaded": len(data["rebalances"]),
            "trades_loaded": len(data["trades"]),
        },
        "tiebreaker_activations": len(tie_periods),
        "tiebreaker_periods": tie_periods[-5:],  # last few for context
        "rebalance_buckets": {
            "tied_count": len(buckets.get("tied_rebalances", [])),
            "baseline_count": len(buckets.get("baseline_rebalances", [])),
        },
        "lift_metrics": metrics,
        "other_factors_correlation": factor_stats,
        "existing_regime_analysis": ledger_analysis,
        "tuning_suggestions": suggestions,
        "recommendation": "Treat as slow regime tilt. Use for tie-breaker only when X/Reddit neutral + supporting other_factors. Update matrix thresholds after 2-4 weeks of live data.",
    }
    return result


def main():
    """Standalone runner for the crypto-analyst."""
    print("=== PM Tilt Retrospective Analyzer ===\n")
    result = run_pm_tilt_analysis()

    print(f"Data loaded: {result['data_summary']}")
    print(f"Tie-breaker activations found: {result['tiebreaker_activations']}")
    print(f"Rebalances near tie-breakers: {result['rebalance_buckets']['tied_count']}")
    print(f"Baseline rebalances: {result['rebalance_buckets']['baseline_count']}\n")

    print("Lift Metrics:")
    print(json.dumps(result["lift_metrics"], indent=2))
    print()

    print("Other Factors Correlation:")
    print(json.dumps(result["other_factors_correlation"], indent=2))
    print()

    if result["tuning_suggestions"]:
        print("=== Tuning Suggestions for Crypto Analyst ===")
        for s in result["tuning_suggestions"]:
            print(f"- [{s['priority'].upper()}] {s['title']}")
            print(f"  {s['suggestion']}")
            if s.get("matrix_change"):
                print(f"  Matrix change: {s['matrix_change']}")
            print()

    print("Full result saved to data/state/pm_tilt_retrospective_analysis.json for further review.")
    Path("data/state/pm_tilt_retrospective_analysis.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
