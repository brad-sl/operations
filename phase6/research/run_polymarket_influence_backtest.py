#!/usr/bin/env python3
"""
Offline: quantify Polymarket regime bias vs trade outcomes.

- Legacy 024: full log (often sensor_degenerate — stuck 0.5)
- Rerun ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902: --since fix cutoff only

Honest constraints:
- Uses influence_stack_log.jsonl (logged bias snapshots) + trades/phase6_trades.jsonl
- No live config writes
- Sensor preflight FIRST — degenerate/stuck bias must not become a WR/ROI story
- Pre-fix stamps are contaminated; rerun must pass --since
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from phase6.research.sensor_preflight import (
    assert_feature_range,
    assert_join_rate,
    combine_preflights,
    map_preflight_to_outcome_class,
)

ROOT = Path(__file__).resolve().parents[2]
INFLUENCE = ROOT / "data" / "state" / "influence_stack_log.jsonl"
TRADES = ROOT / "trades" / "phase6_trades.jsonl"
# Defaults = legacy 024 paths (overridden by --out-stem / --since for rerun)
OUT_JSON = ROOT / "data" / "state" / "analyst_polymarket_influence_backtest_latest.json"
OUT_MD = ROOT / "reports" / "POLYMARKET_INFLUENCE_BACKTEST_20260902.md"
PREFLIGHT_JSON = ROOT / "data" / "state" / "sensor_preflight_polymarket_024_latest.json"
DEFAULT_FIX_CUTOFF = "2026-09-02T22:00:00+00:00"  # seal time (Hermes overlay sync); not calendar midnight


def _parse_ts(s: Any) -> Optional[datetime]:
    if not s:
        return None
    t = str(s).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _load_influence_raw() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not INFLUENCE.exists():
        return rows
    for line in INFLUENCE.open():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _load_influence() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for r in _load_influence_raw():
        ts = _parse_ts(r.get("timestamp") or r.get("as_of"))
        if not ts:
            continue
        poly = r.get("polymarket") or {}
        inf = r.get("influence") or {}
        bias = float(poly.get("risk_on_bias", 0.5) or 0.5)
        rows.append(
            {
                "ts": ts,
                "bias": bias,
                "conf": float(poly.get("confidence", 0) or 0),
                "vol": float(poly.get("total_vol", 0) or 0),
                "n_mkt": int(poly.get("num_markets", 0) or 0),
                "eff": float(inf.get("effective_influence", 0) or 0),
                "source": poly.get("source"),
                "events": list(poly.get("events") or []),
            }
        )
    rows.sort(key=lambda x: x["ts"])
    return rows


def _load_sells() -> List[Dict[str, Any]]:
    sells: List[Dict[str, Any]] = []
    if not TRADES.exists():
        return sells
    for line in TRADES.open():
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
        except Exception:
            continue
        side = str(t.get("side") or t.get("action") or "").lower()
        if side not in ("sell", "exit", "close") and not t.get("exit_price"):
            if (
                t.get("realized_pnl") is None
                and t.get("pnl_usd") is None
                and t.get("realized_pnl_usd") is None
            ):
                continue
        ts = _parse_ts(
            t.get("exit_time")
            or t.get("closed_at")
            or t.get("timestamp")
            or t.get("time")
            or t.get("filled_at")
        )
        if not ts:
            continue
        pnl = t.get("realized_pnl_usd")
        if pnl is None:
            pnl = t.get("realized_pnl")
        if pnl is None:
            pnl = t.get("pnl_usd")
        try:
            pnl_f = float(pnl) if pnl is not None else None
        except Exception:
            pnl_f = None
        sells.append(
            {
                "ts": ts,
                "pair": t.get("pair") or t.get("product_id") or t.get("symbol"),
                "pnl": pnl_f,
                "exit_reason": t.get("exit_reason") or t.get("reason"),
                "side": side,
            }
        )
    sells.sort(key=lambda x: x["ts"])
    return sells


def _nearest_bias(
    inf: List[Dict[str, Any]], ts: datetime, max_hours: float = 24.0
) -> Optional[Dict[str, Any]]:
    if not inf:
        return None
    best = None
    for row in inf:
        if row["ts"] <= ts:
            best = row
        else:
            break
    if best is None:
        return None
    age_h = (ts - best["ts"]).total_seconds() / 3600.0
    if age_h > max_hours:
        return None
    return {**best, "age_hours": round(age_h, 2)}


def _bucket(bias: float) -> str:
    if bias < 0.45:
        return "risk_off"
    if bias > 0.55:
        return "risk_on"
    return "neutral"


def _extract_yes_from_events(events: List[Any]) -> List[float]:
    out: List[float] = []
    for ev in events or []:
        if not isinstance(ev, str):
            continue
        m = re.search(r"yes=(\d+(?:\.\d+)?)", ev)
        if m:
            try:
                out.append(float(m.group(1)))
            except Exception:
                pass
    return out


def _sensor_preflight(inf: List[Dict[str, Any]], sells: List[Dict[str, Any]], joined: List[Dict[str, Any]]):
    """
    Gate BEFORE any WR/ROI table.
    - Bias range must not be stuck at 0.5
    - Event-stamped yes_p (when present) must not be all-default if mostly parseable
    - Trade↔bias join must be usable before bucket scoreboard
    """
    biases = [r["bias"] for r in inf]
    pf_bias = assert_feature_range(
        values=biases,
        name="Polymarket risk_on_bias",
        min_n=10,
        min_unique=3,
        min_stdev=0.01,
        forbid_all_equal_to=0.5,
    )

    # Legacy logs stamp event strings with yes=… — already floats, not raw Gamma wire.
    # Use feature-range (not assert_parsed_prices) so "0.5" stringified floats
    # aren't misread as JSON-string parse failure.
    from phase6.research.sensor_preflight import PreflightResult

    parsed_yes: List[float] = []
    for r in inf:
        parsed_yes.extend(_extract_yes_from_events(r.get("events") or []))
    if parsed_yes:
        pf_prices = assert_feature_range(
            values=parsed_yes,
            name="Polymarket event yes_p stamps",
            min_n=10,
            min_unique=3,
            min_stdev=0.01,
            forbid_all_equal_to=0.5,
        )
        # Map stuck yes stamps to sensor_degenerate (historical meter death)
        if not pf_prices.ok and pf_prices.code == "sensor_degenerate":
            pf_prices = PreflightResult(
                ok=False,
                code="sensor_degenerate",
                plain_english=(
                    "Polymarket event yes_p stamps stuck at 0.5 (historical log). "
                    "Overlay previously mis-parsed Gamma outcomePrices JSON strings — "
                    "re-run after parse fix + live bias range check; do not score WR/ROI."
                ),
                metrics=pf_prices.metrics,
                score_allowed=False,
                checks=pf_prices.checks,
            )
    else:
        pf_prices = PreflightResult(
            ok=True,
            code="sensor_ok",
            plain_english="No event yes_p stamps on influence log (skip yes_p range check).",
            score_allowed=True,
            metrics={"event_yes_n": 0},
        )

    # Join gate is advisory for full scoreboard — still report thin join honestly
    pf_join = assert_join_rate(
        n_events=max(len(sells), 1),
        n_joined=len(joined),
        name="Sells joined to bias ≤24h",
        min_events=10,
        min_join_rate=0.05,  # historical log is sparse vs sells; thin is real
        min_joined=5,
    )

    # Bias range is hard-stop for edge claims; join thin alone → sensor_thin after range OK
    # Order: prices health, bias range, then join
    return combine_preflights(pf_prices, pf_bias, pf_join)


def _write_outputs(
    result: Dict[str, Any],
    md_lines: List[str],
    *,
    out_json: Path,
    out_md: Path,
) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=2, default=str) + "\n")
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md_lines) + "\n")


def run(
    *,
    since: Optional[datetime] = None,
    proposal_id: str = "ANALYST-20260627-024",
    out_json: Optional[Path] = None,
    out_md: Optional[Path] = None,
    preflight_json: Optional[Path] = None,
    why_rerun: Optional[str] = None,
) -> Dict[str, Any]:
    out_json = out_json or OUT_JSON
    out_md = out_md or OUT_MD
    preflight_json = preflight_json or PREFLIGHT_JSON

    inf_all = _load_influence()
    if since is not None:
        inf = [r for r in inf_all if r["ts"] >= since]
    else:
        inf = list(inf_all)

    sells_all = _load_sells()
    if since is not None:
        # Only sells that can join to post-cutoff bias (exit on/after cutoff)
        sells = [s for s in sells_all if s["ts"] >= since]
    else:
        sells = list(sells_all)

    joined: List[Dict[str, Any]] = []
    for s in sells:
        nb = _nearest_bias(inf, s["ts"], max_hours=24.0)
        if nb is None:
            continue
        if s.get("pnl") is None:
            continue
        joined.append(
            {
                **s,
                "bias": nb["bias"],
                "bucket": _bucket(nb["bias"]),
                "age_hours": nb["age_hours"],
                "eff": nb["eff"],
            }
        )

    preflight = _sensor_preflight(inf, sells, joined)
    preflight_json.parent.mkdir(parents=True, exist_ok=True)
    preflight_json.write_text(json.dumps(preflight.to_dict(), indent=2, default=str) + "\n")

    biases = [r["bias"] for r in inf]
    bias_stats = {
        "n_snapshots": len(biases),
        "n_unique_bias_3dp": len({round(b, 3) for b in biases}) if biases else 0,
        "bias_min": min(biases) if biases else None,
        "bias_max": max(biases) if biases else None,
        "bias_mean": statistics.mean(biases) if biases else None,
        "bias_stdev": statistics.pstdev(biases) if len(biases) > 1 else 0.0,
        "eff_mean": statistics.mean([r["eff"] for r in inf]) if inf else 0.0,
        "eff_max": max((r["eff"] for r in inf), default=0.0),
        "first_ts": inf[0]["ts"].isoformat() if inf else None,
        "last_ts": inf[-1]["ts"].isoformat() if inf else None,
        "sources": {},
    }
    from collections import Counter

    bias_stats["sources"] = dict(Counter(str(r.get("source") or "?") for r in inf))

    if not preflight.score_allowed:
        outcome = map_preflight_to_outcome_class(preflight.code)
        # Prefer explicit sensor classes; keep legacy alias for stuck-0.5 history
        if outcome == "sensor_degenerate" and bias_stats.get("n_unique_bias_3dp", 0) <= 1:
            outcome = "sensor_degenerate"
        recommendation = "fix_sensor_or_data_pipeline"
        plain = (
            preflight.plain_english
            + " Cannot measure WR/ROI lift vs bias until the meter produces a real range. "
            "Do not promote allocator influence from this study."
        )
        result = {
            "schema": "polymarket_influence_backtest_v1",
            "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "proposal_id": proposal_id,
            "since": since.isoformat() if since else None,
            "why_rerun": why_rerun,
            "n_influence_all": len(inf_all),
            "n_influence_in_window": len(inf),
            "outcome_class": outcome,
            "recommendation": recommendation,
            "plain_english": plain,
            "bias_stats": bias_stats,
            "n_sells_loaded": len(sells),
            "n_joined": len(joined),
            "bucket_stats": {},
            "sample_joined_tail": [],
            "live_promote_allowed": False,
            "preflight": preflight.to_dict(),
            "artifacts": {
                "influence_log": str(INFLUENCE),
                "trades": str(TRADES),
                "preflight": str(preflight_json),
            },
        }
        lines = [
            f"# Polymarket influence backtest — {proposal_id} (PREFLIGHT FAIL)",
            "",
            f"**Proposal:** {proposal_id}",
            f"**Since:** {since.isoformat() if since else 'full log'}",
            f"**Outcome:** `{outcome}`",
            f"**Recommendation:** `{recommendation}` (no live promote)",
            "",
        ]
        if why_rerun:
            lines += ["## Why re-run / window", why_rerun, ""]
        lines += [
            "## Plain English",
            plain,
            "",
            "## Bias log",
            f"- Snapshots (window): {bias_stats['n_snapshots']} (all-log={len(inf_all)})",
            f"- Unique bias (3dp): {bias_stats['n_unique_bias_3dp']}",
            f"- Min/max/mean: {bias_stats['bias_min']} / {bias_stats['bias_max']} / {bias_stats['bias_mean']}",
            f"- Stdev: {bias_stats['bias_stdev']}",
            f"- Window: {bias_stats['first_ts']} → {bias_stats['last_ts']}",
            "",
            "## Preflight",
            f"```json\n{json.dumps(preflight.to_dict(), indent=2, default=str)}\n```",
            "",
            "## Next",
            "1. Ensure intel/influence stamps post-fix leave 0.5 (parse + polarity sealed 2026-09-02).",
            "2. Prefer bias at **entry** on decision_context when available.",
            "3. Re-score with `--since` only; never promote from pre-fix stuck log.",
            "",
            f"JSON: `{out_json}`",
            "",
        ]
        _write_outputs(result, lines, out_json=out_json, out_md=out_md)
        return result

    # --- Scoreboard path (only when sensor_ok) ---
    buckets: Dict[str, List[float]] = defaultdict(list)
    for j in joined:
        if j.get("pnl") is not None:
            buckets[j["bucket"]].append(float(j["pnl"]))

    bucket_stats: Dict[str, Any] = {}
    for b, pnls in buckets.items():
        wins = sum(1 for p in pnls if p > 0)
        bucket_stats[b] = {
            "n": len(pnls),
            "wr": (wins / len(pnls)) if pnls else None,
            "mean_pnl": statistics.mean(pnls) if pnls else None,
            "sum_pnl": sum(pnls),
        }

    # Simple lift: risk_on mean vs neutral mean (needs both buckets)
    lift_note = "insufficient bucket coverage for lift claim"
    recommendation = "continue_observe_only"
    outcome = "inconclusive_sparse_N"
    if bucket_stats.get("risk_on", {}).get("n", 0) >= 5 and bucket_stats.get("neutral", {}).get("n", 0) >= 5:
        ro = bucket_stats["risk_on"]["mean_pnl"]
        neu = bucket_stats["neutral"]["mean_pnl"]
        if ro is not None and neu is not None:
            delta = ro - neu
            lift_note = f"risk_on mean_pnl − neutral = {delta:.4f}"
            if delta > 0 and bucket_stats["risk_on"]["wr"] and bucket_stats["risk_on"]["wr"] >= 0.5:
                outcome = "ATTENTION_ONLY"
                recommendation = "continue_observe_only"
            else:
                outcome = "unstable_or_no_edge"
                recommendation = "drop"
    elif len(joined) < 5:
        outcome = "sensor_thin" if not joined else "inconclusive_sparse_N"
        recommendation = "fix_sensor_or_data_pipeline" if not joined else "extend_trial"

    plain = (
        f"Sensor OK. Joined {len(joined)}/{len(sells)} sells to bias≤24h. "
        f"{lift_note}. Live promote still blocked without Brad GO + promotion gates."
    )
    result = {
        "schema": "polymarket_influence_backtest_v1",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "proposal_id": proposal_id,
        "since": since.isoformat() if since else None,
        "why_rerun": why_rerun,
        "n_influence_all": len(inf_all),
        "n_influence_in_window": len(inf),
        "outcome_class": outcome,
        "recommendation": recommendation,
        "plain_english": plain,
        "bias_stats": bias_stats,
        "n_sells_loaded": len(sells),
        "n_joined": len(joined),
        "bucket_stats": bucket_stats,
        "sample_joined_tail": [
            {
                "ts": j["ts"].isoformat(),
                "pair": j.get("pair"),
                "pnl": j.get("pnl"),
                "bias": j.get("bias"),
                "bucket": j.get("bucket"),
            }
            for j in joined[-8:]
        ],
        "live_promote_allowed": False,
        "preflight": preflight.to_dict(),
        "artifacts": {
            "influence_log": str(INFLUENCE),
            "trades": str(TRADES),
            "preflight": str(preflight_json),
        },
    }
    lines = [
        f"# Polymarket influence backtest — {proposal_id}",
        "",
        f"**Proposal:** {proposal_id}",
        f"**Since:** {since.isoformat() if since else 'full log'}",
        f"**Outcome:** `{outcome}`",
        f"**Recommendation:** `{recommendation}` (no live promote)",
        "",
    ]
    if why_rerun:
        lines += ["## Why re-run / window", why_rerun, ""]
    lines += [
        "## Plain English",
        plain,
        "",
        "## Bias log",
        f"- Snapshots (window): {bias_stats['n_snapshots']} (all-log={len(inf_all)})",
        f"- Unique bias (3dp): {bias_stats['n_unique_bias_3dp']}",
        f"- Min/max/mean: {bias_stats['bias_min']} / {bias_stats['bias_max']} / {bias_stats['bias_mean']}",
        f"- Stdev: {bias_stats['bias_stdev']}",
        "",
        "## Buckets",
        f"```json\n{json.dumps(bucket_stats, indent=2)}\n```",
        "",
        "## Preflight",
        f"```json\n{json.dumps(preflight.to_dict(), indent=2, default=str)}\n```",
        "",
        f"JSON: `{out_json}`",
        "",
    ]
    _write_outputs(result, lines, out_json=out_json, out_md=out_md)
    return result


def _paths_for_stem(stem: str) -> tuple[Path, Path, Path]:
    """Map out-stem to json/md/preflight paths."""
    stem = stem.strip().replace(" ", "_")
    out_md = ROOT / "reports" / f"{stem}.md"
    out_json = ROOT / "data" / "state" / f"analyst_{stem.lower()}_latest.json"
    pf = ROOT / "data" / "state" / f"sensor_preflight_{stem.lower()}_latest.json"
    return out_json, out_md, pf


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Polymarket influence backtest (sensor-gated)")
    ap.add_argument(
        "--since",
        default=None,
        help=f"ISO timestamp; only influence/sells on/after (rerun cutoff default none; use {DEFAULT_FIX_CUTOFF})",
    )
    ap.add_argument(
        "--proposal-id",
        default=None,
        help="Proposal/trial id stamped on report",
    )
    ap.add_argument(
        "--out-stem",
        default=None,
        help="Report stem e.g. POLYMARKET_INFLUENCE_RERUN_20260902",
    )
    ap.add_argument(
        "--why-rerun",
        default=None,
        help="Plain note embedded in report (why new trial / bad prior data)",
    )
    ap.add_argument(
        "--rerun",
        action="store_true",
        help="Convenience: since=fix cutoff + rerun stem + proposal + why text",
    )
    args = ap.parse_args()

    since_s = args.since
    proposal = args.proposal_id
    stem = args.out_stem
    why = args.why_rerun
    if args.rerun:
        since_s = since_s or DEFAULT_FIX_CUTOFF
        proposal = proposal or "ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902"
        stem = stem or "POLYMARKET_INFLUENCE_RERUN_20260902"
        why = why or (
            "Re-run of 024: prior study used degenerate sensor (bias stuck 0.5 from "
            "Gamma outcomePrices JSON-string parse + polarity). Historical log not rewritten. "
            "This window is post-fix stamps only; sensor_ok required before scoreboard. No live promote."
        )

    since_dt = _parse_ts(since_s) if since_s else None
    if stem:
        out_json, out_md, pf = _paths_for_stem(stem)
    else:
        out_json, out_md, pf = OUT_JSON, OUT_MD, PREFLIGHT_JSON
    if not proposal:
        proposal = "ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902" if since_dt else "ANALYST-20260627-024"

    out = run(
        since=since_dt,
        proposal_id=proposal,
        out_json=out_json,
        out_md=out_md,
        preflight_json=pf,
        why_rerun=why,
    )
    print(json.dumps({k: out.get(k) for k in (
        "proposal_id", "since", "outcome_class", "recommendation",
        "plain_english", "n_joined", "n_influence_in_window", "live_promote_allowed"
    )}, indent=2))
    print("wrote", out_json)
    print("wrote", out_md)
