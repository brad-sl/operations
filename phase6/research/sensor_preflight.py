#!/usr/bin/env python3
"""
Sensor / method preflight — global test validity gate (Brad 2026-09-02).

Run BEFORE scoring edge/WR/ROI. Degenerate sensors must not become
"inconclusive no edge" or expensive full suites.

Outcome vocabulary (subset of regimen):
  sensor_ok
  sensor_broken          — parser/API/shape failure (fix meter; do not score)
  sensor_degenerate      — feature stuck at neutral / zero variance
  sensor_thin            — too few samples / join rate too low
  method_invalid         — missing treatment definition / control

Usage:
  from phase6.research.sensor_preflight import (
      assert_feature_range, preflight_report, gate_or_stop
  )
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

Number = Union[int, float]


@dataclass
class PreflightResult:
    ok: bool
    code: str  # sensor_ok | sensor_broken | sensor_degenerate | sensor_thin | method_invalid
    plain_english: str
    checks: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    live_promote_allowed: bool = False
    score_allowed: bool = False  # False → do not run WR/edge tables

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["as_of"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        d["schema"] = "sensor_preflight_v1"
        return d


def _finite_nums(values: Iterable[Any]) -> List[float]:
    out: List[float] = []
    for v in values:
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            out.append(x)
    return out


def feature_stats(values: Sequence[Any]) -> Dict[str, Any]:
    xs = _finite_nums(values)
    if not xs:
        return {
            "n": 0,
            "unique_3dp": 0,
            "min": None,
            "max": None,
            "mean": None,
            "stdev": None,
            "all_equal": True,
        }
    rounded = {round(x, 3) for x in xs}
    stdev = statistics.pstdev(xs) if len(xs) > 1 else 0.0
    return {
        "n": len(xs),
        "unique_3dp": len(rounded),
        "min": min(xs),
        "max": max(xs),
        "mean": statistics.mean(xs),
        "stdev": stdev,
        "all_equal": len(rounded) <= 1,
    }


def assert_feature_range(
    values: Sequence[Any],
    *,
    name: str = "feature",
    min_n: int = 5,
    min_unique: int = 3,
    min_stdev: float = 1e-6,
    forbid_all_equal_to: Optional[float] = None,
    equal_tol: float = 1e-9,
) -> PreflightResult:
    """
    Core invariant: treatment/sensor variable must have real range before scoring.
    """
    st = feature_stats(values)
    checks: List[Dict[str, Any]] = []
    metrics = {"feature": name, **st}

    if st["n"] < min_n:
        return PreflightResult(
            ok=False,
            code="sensor_thin",
            plain_english=(
                f"{name}: only n={st['n']} finite samples (need ≥{min_n}). "
                "Do not score edge — thin sensor."
            ),
            checks=[{"name": "min_n", "pass": False, "got": st["n"], "need": min_n}],
            metrics=metrics,
            score_allowed=False,
        )

    checks.append({"name": "min_n", "pass": True, "got": st["n"], "need": min_n})

    if forbid_all_equal_to is not None and st["n"] > 0:
        target = float(forbid_all_equal_to)
        all_neutral = all(abs(x - target) <= equal_tol for x in _finite_nums(values))
        checks.append(
            {
                "name": "not_stuck_at_neutral",
                "pass": not all_neutral,
                "neutral": target,
            }
        )
        if all_neutral:
            return PreflightResult(
                ok=False,
                code="sensor_degenerate",
                plain_english=(
                    f"{name}: every sample equals neutral default {target}. "
                    "Meter stuck or parser broken — fix sensor, do not claim no-edge."
                ),
                checks=checks,
                metrics=metrics,
                score_allowed=False,
            )

    range_ok = (st["unique_3dp"] >= min_unique) or (float(st["stdev"] or 0) > min_stdev)
    checks.append(
        {
            "name": "has_range",
            "pass": range_ok,
            "unique_3dp": st["unique_3dp"],
            "stdev": st["stdev"],
            "need_unique": min_unique,
            "need_stdev": min_stdev,
        }
    )
    if not range_ok:
        return PreflightResult(
            ok=False,
            code="sensor_degenerate",
            plain_english=(
                f"{name}: zero useful range (unique_3dp={st['unique_3dp']}, "
                f"stdev={st['stdev']}). Degenerate feature — not an edge test."
            ),
            checks=checks,
            metrics=metrics,
            score_allowed=False,
        )

    return PreflightResult(
        ok=True,
        code="sensor_ok",
        plain_english=f"{name}: range OK (n={st['n']}, unique={st['unique_3dp']}, stdev={st['stdev']:.6g}).",
        checks=checks,
        metrics=metrics,
        score_allowed=True,
    )


def assert_join_rate(
    *,
    n_events: int,
    n_joined: int,
    name: str = "join",
    min_events: int = 10,
    min_join_rate: float = 0.3,
    min_joined: int = 5,
) -> PreflightResult:
    if n_events < min_events:
        return PreflightResult(
            ok=False,
            code="sensor_thin",
            plain_english=f"{name}: only {n_events} events (need ≥{min_events}).",
            metrics={"n_events": n_events, "n_joined": n_joined},
            score_allowed=False,
        )
    rate = (n_joined / n_events) if n_events else 0.0
    if n_joined < min_joined or rate < min_join_rate:
        return PreflightResult(
            ok=False,
            code="sensor_thin",
            plain_english=(
                f"{name}: joined {n_joined}/{n_events} (rate={rate:.2%}); "
                f"need ≥{min_joined} and rate≥{min_join_rate:.0%}. Fix stamps/join, don't score."
            ),
            metrics={"n_events": n_events, "n_joined": n_joined, "join_rate": rate},
            score_allowed=False,
        )
    return PreflightResult(
        ok=True,
        code="sensor_ok",
        plain_english=f"{name}: join OK ({n_joined}/{n_events} = {rate:.1%}).",
        metrics={"n_events": n_events, "n_joined": n_joined, "join_rate": rate},
        score_allowed=True,
    )


def assert_parsed_prices_not_default(
    raw_prices: Sequence[Any],
    parsed: Sequence[Any],
    *,
    default: float = 0.5,
    name: str = "outcome_prices",
) -> PreflightResult:
    """
    Catch Gamma-style bugs: wire type is JSON string, naive parser returns all 0.5.
    """
    if not raw_prices:
        return PreflightResult(
            ok=False,
            code="sensor_thin",
            plain_english=f"{name}: no raw prices to validate.",
            score_allowed=False,
        )
    str_n = sum(1 for p in raw_prices if isinstance(p, str))
    ps = _finite_nums(parsed)
    if not ps:
        return PreflightResult(
            ok=False,
            code="sensor_broken",
            plain_english=f"{name}: parser produced no finite prices (raw_str_count={str_n}).",
            metrics={"raw_n": len(raw_prices), "str_n": str_n, "parsed_n": 0},
            score_allowed=False,
        )
    all_default = all(abs(x - default) < 1e-12 for x in ps)
    # If majority of raw are strings and all parsed default → almost certainly broken parse
    if str_n >= max(1, len(raw_prices) // 2) and all_default:
        return PreflightResult(
            ok=False,
            code="sensor_broken",
            plain_english=(
                f"{name}: raw prices are mostly JSON strings ({str_n}/{len(raw_prices)}) "
                f"but parser emitted all {default}. Fix json.loads path before any study."
            ),
            metrics={
                "raw_n": len(raw_prices),
                "str_n": str_n,
                "parsed_unique": len({round(x, 4) for x in ps}),
                "parsed_all_default": True,
            },
            score_allowed=False,
        )
    if all_default and len(ps) >= 5:
        return PreflightResult(
            ok=False,
            code="sensor_degenerate",
            plain_english=(
                f"{name}: all parsed prices == {default} (n={len(ps)}). "
                "Likely parser bug or dead market set — do not score influence."
            ),
            metrics={"parsed_n": len(ps), "all_default": True},
            score_allowed=False,
        )
    return PreflightResult(
        ok=True,
        code="sensor_ok",
        plain_english=f"{name}: parse looks live (unique={len({round(x,4) for x in ps})}).",
        metrics={
            "raw_n": len(raw_prices),
            "str_n": str_n,
            "parsed_unique": len({round(x, 4) for x in ps}),
        },
        score_allowed=True,
    )


def combine_preflights(*results: PreflightResult) -> PreflightResult:
    """First failure wins; else OK."""
    checks: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {}
    for r in results:
        checks.extend(r.checks)
        metrics.update({f"{r.code}_{k}" if k in metrics else k: v for k, v in r.metrics.items()})
        if not r.ok:
            return PreflightResult(
                ok=False,
                code=r.code,
                plain_english=r.plain_english,
                checks=checks,
                metrics={**metrics, **r.metrics},
                score_allowed=False,
            )
    if not results:
        return PreflightResult(
            ok=False,
            code="method_invalid",
            plain_english="No preflight checks ran.",
            score_allowed=False,
        )
    return PreflightResult(
        ok=True,
        code="sensor_ok",
        plain_english="All sensor preflight checks passed.",
        checks=checks,
        metrics=metrics,
        score_allowed=True,
    )


def preflight_report(result: PreflightResult, path: Optional[Path] = None) -> Dict[str, Any]:
    d = result.to_dict()
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, indent=2, default=str) + "\n")
    return d


def gate_or_stop(result: PreflightResult) -> PreflightResult:
    """Identity helper for call sites: if not score_allowed, caller must return early."""
    return result


# Outcome classes allowed when sensor fails (trial_cycle + honesty)
SENSOR_OUTCOME_CLASSES = {
    "sensor_broken",
    "sensor_degenerate",
    "sensor_thin",
    "method_invalid",
}


def map_preflight_to_outcome_class(code: str) -> str:
    if code in SENSOR_OUTCOME_CLASSES:
        return code
    if code == "sensor_ok":
        return "sensor_ok"
    return "process_incomplete"
