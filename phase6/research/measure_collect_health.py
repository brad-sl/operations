#!/usr/bin/env python3
"""
Measure-collect health — catch dead meters before the 14d GO window burns.

Class problem (Brad 2026-10-25): shadow/measure tests start collecting, values never
populate (or stay stuck/zero), and we only notice weeks later at promote/GO time.
W2 would-arm: 523 rows with hours_held≡0 and has_tryout_lot≡false is the poster case.

This module is the **ongoing** cousin of sensor_preflight:
  - sensor_preflight → before scoring a dig
  - measure_collect_health → every collect tick + day-1 + GO packet lead

Status vocabulary (subset of regimen + collect-specific):
  sensor_ok              — inputs vary; treatment can fire in principle
  sensor_broken          — required input keys missing / unreadable
  sensor_degenerate      — key fields stuck at default (0 / false / empty)
  sensor_thin            — too few snaps / no class under study in book
  method_invalid         — health contract missing required fields
  collect_armed          — sensor_ok AND ≥1 positive treatment sample in window
  collect_empty_book_ok  — sensor_ok inputs, but open book has no target class
                           (honest empty — do NOT start 14d clock on this alone)

Contract for a measure stream (declare at ship):
  {
    "name": "w2_would_arm",
    "history_path": "...jsonl",
    "latest_path": "...json",
    "row_key": "rows",                 # list of per-unit evals inside each snap
    "required_row_fields": ["hours_held", "has_tryout_lot", "mfe_pct", ...],
    "stuck_defaults": {"hours_held": 0.0, "has_tryout_lot": False},
    "treatment_field": "would_arm_3pct",  # optional; true = positive fire
    "min_snaps_for_range": 3,
    "min_unique_hours": 2,              # hours_held must not be all-equal
    "min_true_rate_tryout_when_alts": 0.05,  # if alts held, some tryout bits
    "alt_pairs_hint": non-core pairs that should often be tryout-ish
  }
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from phase6.research.sensor_preflight import (
    PreflightResult,
    assert_feature_range,
    combine_preflights,
    feature_stats,
    map_preflight_to_outcome_class,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "data" / "state"
DEFAULT_CORE = {"BTC-USD", "ETH-USD", "PAXG-USD", "BTC-USDC", "ETH-USDC"}


@dataclass
class MeasureHealthResult:
    ok: bool
    code: str
    plain_english: str
    collect_clock_ok: bool  # True only if this snap may count toward N-day gate
    go_packet_allowed: bool  # False → do not open GO talk from this stream
    checks: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["as_of"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        d["schema"] = "measure_collect_health_v1"
        d["outcome_class"] = map_preflight_to_outcome_class(self.code) if self.code.startswith(
            "sensor_"
        ) or self.code == "method_invalid" else self.code
        return d


def _load_jsonl(path: Path, limit: int = 500) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(o, dict):
            out.append(o)
    return out


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        o = json.loads(path.read_text(encoding="utf-8"))
        return o if isinstance(o, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _rows_from_snap(snap: Dict[str, Any], row_key: str) -> List[Dict[str, Any]]:
    rows = snap.get(row_key)
    if isinstance(rows, list):
        return [r for r in rows if isinstance(r, dict)]
    # dig-out nests w2
    nested = snap.get("w2_sl_width_would_arm")
    if isinstance(nested, dict):
        rows = nested.get(row_key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    return []


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def health_from_rows(
    rows: Sequence[Dict[str, Any]],
    *,
    name: str,
    required_row_fields: Sequence[str],
    stuck_defaults: Optional[Dict[str, Any]] = None,
    treatment_field: Optional[str] = None,
    min_rows: int = 1,
    core_pairs: Optional[set] = None,
) -> MeasureHealthResult:
    """
    Single-snap or multi-snap flattened rows → health.
    """
    stuck_defaults = stuck_defaults or {}
    core = core_pairs or DEFAULT_CORE
    checks: List[Dict[str, Any]] = []
    metrics: Dict[str, Any] = {"n_rows": len(rows), "name": name}

    if len(rows) < min_rows:
        return MeasureHealthResult(
            ok=False,
            code="sensor_thin",
            plain_english=f"{name}: n_rows={len(rows)} < min_rows={min_rows}. No collect sample.",
            collect_clock_ok=False,
            go_packet_allowed=False,
            checks=[{"name": "min_rows", "pass": False, "got": len(rows), "need": min_rows}],
            metrics=metrics,
            name=name,
        )

    # required fields present
    missing_counts = {k: 0 for k in required_row_fields}
    for r in rows:
        for k in required_row_fields:
            if k not in r or r.get(k) is None:
                missing_counts[k] += 1
    missing_bad = {k: c for k, c in missing_counts.items() if c == len(rows)}
    checks.append({"name": "required_fields", "missing_all_rows": missing_bad})
    if missing_bad:
        return MeasureHealthResult(
            ok=False,
            code="sensor_broken",
            plain_english=(
                f"{name}: required fields missing on every row: {list(missing_bad)}. "
                "Wire inputs before starting any day-count gate."
            ),
            collect_clock_ok=False,
            go_packet_allowed=False,
            checks=checks,
            metrics={**metrics, "missing_all_rows": missing_bad},
            name=name,
        )

    # stuck defaults (the W2 killer)
    stuck_hits: Dict[str, Any] = {}
    alt_rows = [
        r
        for r in rows
        if str(r.get("pair") or "") not in (core_pairs or DEFAULT_CORE)
        and _f(r.get("held_usd")) >= 5.0
    ]
    for field_name, default in stuck_defaults.items():
        vals = [r.get(field_name) for r in rows]
        if isinstance(default, bool):
            all_stuck = all(bool(v) is default for v in vals)
            rate_true = sum(1 for v in vals if bool(v)) / max(1, len(vals))
            metrics[f"{field_name}_true_rate"] = round(rate_true, 4)
            # Boolean default False is only degenerate when alts are held (should see some True)
            # Core-only book with all False tryout bits = honest empty, not stuck meter
            if all_stuck and default is False and not alt_rows:
                all_stuck = False
                checks.append(
                    {
                        "name": f"not_stuck_{field_name}",
                        "pass": True,
                        "note": "core_only_book_all_false_ok",
                        "default": default,
                        "n": len(vals),
                    }
                )
                continue
        else:
            nums = [_f(v, float("nan")) for v in vals]
            finite = [x for x in nums if x == x]
            all_stuck = bool(finite) and all(abs(x - float(default)) < 1e-12 for x in finite)
            st = feature_stats(finite)
            metrics[f"{field_name}_stats"] = st
        checks.append(
            {
                "name": f"not_stuck_{field_name}",
                "pass": not all_stuck,
                "default": default,
                "n": len(vals),
            }
        )
        if all_stuck:
            stuck_hits[field_name] = default

    if stuck_hits:
        return MeasureHealthResult(
            ok=False,
            code="sensor_degenerate",
            plain_english=(
                f"{name}: fields stuck at defaults {stuck_hits} across n={len(rows)} rows. "
                "Meter not reading live inputs — fix wiring; do NOT burn 14d gate or GO from this log."
            ),
            collect_clock_ok=False,
            go_packet_allowed=False,
            checks=checks,
            metrics={**metrics, "stuck_hits": stuck_hits, "n_alt_rows": len(alt_rows)},
            name=name,
        )

    # hours / continuous range if present — only when enough held rows to expect variance
    if ("hours_held" in required_row_fields or any("hours_held" in r for r in rows)) and len(
        rows
    ) >= 2:
        hrs = [_f(r.get("hours_held")) for r in rows]
        # Single-pair or all-zero still degenerate when alts held or n>=2 all zero
        if all(abs(h) < 1e-12 for h in hrs):
            return MeasureHealthResult(
                ok=False,
                code="sensor_degenerate",
                plain_english=(
                    f"{name}.hours_held: every sample is 0.0 (n={len(hrs)}). "
                    "Meter not reading entry timestamps — fix lots/ledger join."
                ),
                collect_clock_ok=False,
                go_packet_allowed=False,
                checks=checks
                + [{"name": "hours_held_not_all_zero", "pass": False, "n": len(hrs)}],
                metrics=metrics,
                name=name,
            )
        if len(hrs) >= 3:
            pf = assert_feature_range(
                hrs,
                name=f"{name}.hours_held",
                min_n=min(3, len(hrs)),
                min_unique=2,
                min_stdev=1e-9,
                forbid_all_equal_to=0.0,
            )
            checks.extend(pf.checks)
            metrics["hours_held_preflight"] = pf.code
            if not pf.ok:
                return MeasureHealthResult(
                    ok=False,
                    code=pf.code,
                    plain_english=pf.plain_english
                    + " (collect clock frozen until hours_held has real range.)",
                    collect_clock_ok=False,
                    go_packet_allowed=False,
                    checks=checks,
                    metrics=metrics,
                    name=name,
                )

    # treatment fire rate
    n_treat = 0
    if treatment_field:
        n_treat = sum(1 for r in rows if r.get(treatment_field))
        metrics["n_treatment_true"] = n_treat
        metrics["treatment_field"] = treatment_field

    # empty-book vs degenerate: alts held without tryout bit already caught;
    # if only core rows, empty target class can be honest
    pairs = {str(r.get("pair") or "") for r in rows}
    metrics["n_alt_rows"] = len(alt_rows)
    metrics["pairs"] = sorted(pairs)

    if treatment_field and n_treat == 0 and alt_rows:
        # Inputs OK (not stuck) but treatment never true — may be honest empty class
        # or over-tight rule. Flag as collect_empty_book_ok only if shellish inputs look live.
        return MeasureHealthResult(
            ok=True,
            code="collect_empty_book_ok",
            plain_english=(
                f"{name}: inputs have range but treatment '{treatment_field}' never true "
                f"(n_rows={len(rows)}, n_alt={len(alt_rows)}). Honest empty OR rule never matches — "
                "do not count pure empty days toward promote N without a closed-leg CF bound."
            ),
            collect_clock_ok=True,  # inputs live; day can count as sensor_ok day
            go_packet_allowed=False,  # still need fires or closed-leg CF bound
            checks=checks + [{"name": "treatment_fires", "pass": False, "n": 0}],
            metrics=metrics,
            name=name,
        )

    if treatment_field and n_treat > 0:
        return MeasureHealthResult(
            ok=True,
            code="collect_armed",
            plain_english=(
                f"{name}: sensor live and treatment fired n={n_treat}/{len(rows)}. "
                "Day may count toward gate."
            ),
            collect_clock_ok=True,
            go_packet_allowed=False,  # GO still needs N-day + Brad
            checks=checks + [{"name": "treatment_fires", "pass": True, "n": n_treat}],
            metrics=metrics,
            name=name,
        )

    return MeasureHealthResult(
        ok=True,
        code="sensor_ok",
        plain_english=f"{name}: inputs look live (n_rows={len(rows)}).",
        collect_clock_ok=True,
        go_packet_allowed=False,
        checks=checks,
        metrics=metrics,
        name=name,
    )


def health_from_history(
    *,
    name: str,
    history_path: Path,
    latest_path: Optional[Path] = None,
    row_key: str = "rows",
    required_row_fields: Sequence[str],
    stuck_defaults: Optional[Dict[str, Any]] = None,
    treatment_field: Optional[str] = None,
    min_snaps: int = 3,
    lookback_snaps: int = 50,
    post_fix_since: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Multi-snap health for a measure stream. Writes nothing — caller persists.

    Live meter = LATEST snap (or newest history row). Contaminated pre-fix
    history does not freeze a repaired live meter; sensor_ok_days only count
    snaps with collect_clock_ok after post_fix_since (if set).
    """
    snaps = _load_jsonl(Path(history_path), limit=max(lookback_snaps, 200))
    latest = _load_json(Path(latest_path)) if latest_path else {}
    if not latest and snaps:
        latest = snaps[-1]

    if len(snaps) < 1 and not latest:
        r = MeasureHealthResult(
            ok=False,
            code="sensor_thin",
            plain_english=f"{name}: no history and no latest — collector not running.",
            collect_clock_ok=False,
            go_packet_allowed=False,
            name=name,
            metrics={"n_snaps": 0},
        )
        return r.to_dict()

    # LIVE meter from latest only
    live_rows = _rows_from_snap(latest, row_key) if latest else []
    live = health_from_rows(
        live_rows,
        name=f"{name}_live",
        required_row_fields=required_row_fields,
        stuck_defaults=stuck_defaults,
        treatment_field=treatment_field,
        min_rows=0 if not live_rows else 1,
    )

    # History contamination (pre-fix)
    cutoff = (post_fix_since or "")[:19]
    hist_rows: List[Dict[str, Any]] = []
    ok_days = set()
    bad_days = set()
    for s in snaps:
        day = str(s.get("as_of") or "")[:10]
        asof = str(s.get("as_of") or "")[:19]
        if cutoff and asof and asof < cutoff:
            continue
        rows = _rows_from_snap(s, row_key)
        hist_rows.extend(rows)
        # prefer stamped collect_clock_ok on snap
        if "collect_clock_ok" in s:
            if s.get("collect_clock_ok"):
                if day:
                    ok_days.add(day)
            else:
                if day:
                    bad_days.add(day)
            continue
        # unstamped legacy: score the snap rows
        sh = health_from_rows(
            rows,
            name=name,
            required_row_fields=required_row_fields,
            stuck_defaults=stuck_defaults,
            treatment_field=treatment_field,
            min_rows=0 if not rows else 1,
        )
        if sh.collect_clock_ok and day:
            ok_days.add(day)
        elif day:
            bad_days.add(day)

    hist = health_from_rows(
        hist_rows[-500:] if hist_rows else live_rows,
        name=f"{name}_history",
        required_row_fields=required_row_fields,
        stuck_defaults=stuck_defaults,
        treatment_field=treatment_field,
        min_rows=0 if not (hist_rows or live_rows) else 1,
    )

    # Primary code = live meter; history may be contaminated
    primary = live
    d = primary.to_dict()
    d["name"] = name
    d["n_snaps_history"] = len(snaps)
    d["min_snaps_gate"] = min_snaps
    d["history_path"] = str(history_path)
    if latest_path:
        d["latest_path"] = str(latest_path)
    d["live_meter"] = {
        "code": live.code,
        "ok": live.ok,
        "collect_clock_ok": live.collect_clock_ok,
        "plain_english": live.plain_english,
        "metrics": live.metrics,
    }
    d["history_meter"] = {
        "code": hist.code,
        "ok": hist.ok,
        "collect_clock_ok": hist.collect_clock_ok,
        "plain_english": hist.plain_english,
        "post_fix_since": post_fix_since,
        "n_rows_scored": len(hist_rows),
    }
    days = sorted({str(s.get("as_of") or "")[:10] for s in snaps if s.get("as_of")})
    d["calendar_days_in_log"] = len(days)
    d["calendar_day_list"] = days
    d["sensor_ok_days"] = sorted(ok_days)
    d["sensor_ok_day_estimate"] = len(ok_days)
    d["sensor_bad_days"] = sorted(bad_days)
    d["gate_note"] = (
        "14d/N-day promote gates must use sensor_ok_days (collect_clock_ok), "
        "not raw calendar span. Contaminated pre-fix history does not count; "
        "set post_fix_since after a meter repair."
    )
    # Contaminated history warning does not override a healthy live meter
    if live.collect_clock_ok and not hist.collect_clock_ok and hist_rows:
        d["history_contaminated"] = True
        d["plain_english"] = (
            live.plain_english
            + " History still contaminated (pre-fix zeros) — clock uses post-fix "
            "sensor_ok_days only; do not GO from full calendar span."
        )
    if len(ok_days) < 1 and not live.collect_clock_ok:
        d["go_packet_allowed"] = False
    return d


# --- Built-in contracts -------------------------------------------------

W2_POST_FIX_MARKER = STATE_DIR / "w2_meter_post_fix_since.txt"

W2_CONTRACT = {
    "name": "w2_would_arm",
    "history_path": STATE_DIR / "sl_width_would_arm_history.jsonl",
    "latest_path": STATE_DIR / "sl_width_would_arm_latest.json",
    "row_key": "rows",
    "required_row_fields": (
        "pair",
        "held_usd",
        "hours_held",
        "has_tryout_lot",
        "mfe_pct",
        "would_arm_3pct",
        "rule_id",
    ),
    "stuck_defaults": {"hours_held": 0.0, "has_tryout_lot": False},
    "treatment_field": "would_arm_3pct",
    "min_snaps": 3,
    "repair_hint": (
        "W2 inputs: open lots SSOT tryout_scale_up_open_lots.json + ledger last BUY hours; "
        "untagged alt shells ≤$80 count as tryout_lot. Re-run run_sl_width_would_arm_shadow; "
        "stamp w2_meter_post_fix_since.txt; clock = post-fix sensor_ok_days only."
    ),
}


def _post_fix_since_w2() -> Optional[str]:
    if W2_POST_FIX_MARKER.is_file():
        try:
            return W2_POST_FIX_MARKER.read_text(encoding="utf-8").strip()[:32] or None
        except OSError:
            return None
    return None


def health_w2_would_arm() -> Dict[str, Any]:
    c = W2_CONTRACT
    return health_from_history(
        name=c["name"],
        history_path=c["history_path"],
        latest_path=c["latest_path"],
        row_key=c["row_key"],
        required_row_fields=c["required_row_fields"],
        stuck_defaults=c["stuck_defaults"],
        treatment_field=c["treatment_field"],
        min_snaps=int(c["min_snaps"]),
        post_fix_since=_post_fix_since_w2(),
    )


def health_bank_trail() -> Dict[str, Any]:
    """Bank-trail CF + Sunday review — not a would-arm row stream; scalar contract."""
    cf: Dict[str, Any] = _load_json(STATE_DIR / "bank_trail_while_green_cf_latest.json")
    sun: Dict[str, Any] = _load_json(STATE_DIR / "bank_trail_while_green_sunday_review_latest.json")
    checks: List[Dict[str, Any]] = []
    if not cf:
        r = MeasureHealthResult(
            ok=False,
            code="sensor_thin",
            plain_english="bank_trail: no CF latest — collector not run.",
            collect_clock_ok=False,
            go_packet_allowed=False,
            name="bank_trail",
        )
        return r.to_dict()

    summary = cf.get("summary") if isinstance(cf.get("summary"), dict) else {}
    assert isinstance(summary, dict)
    n_legs = int(summary.get("n_legs") or cf.get("n_legs") or 0)
    n_arm = int(
        summary.get("n_would_arm_legs")
        or sun.get("n_would_arm_legs")
        or 0
    )
    checks.append({"name": "cf_present", "pass": True, "n_legs": n_legs, "n_would_arm": n_arm})

    # Degenerate: CF present but every path_mfe missing / all zero while n_legs>0
    legs_raw = cf.get("legs")
    legs: List[Any] = legs_raw if isinstance(legs_raw, list) else []
    mfes: List[float] = []
    for leg in legs:
        if isinstance(leg, dict) and leg.get("path_mfe") is not None:
            mfes.append(_f(leg.get("path_mfe")))
    if n_legs >= 3 and legs and (not mfes or all(abs(x) < 1e-12 for x in mfes)):
        r = MeasureHealthResult(
            ok=False,
            code="sensor_degenerate",
            plain_english=(
                f"bank_trail: n_legs={n_legs} but path_mfe all missing/zero — "
                "candle join broken; do not GO."
            ),
            collect_clock_ok=False,
            go_packet_allowed=False,
            checks=checks,
            metrics={"n_legs": n_legs, "n_mfe": len(mfes)},
            name="bank_trail",
        )
        d = r.to_dict()
        d["repair_hint"] = "Re-run bank_trail_while_green_cf with real OHLCV; check candle loader."
        return d

    if n_legs < 1:
        code = "sensor_thin"
        ok = False
        clock = False
        pe = "bank_trail: zero legs in CF window."
    elif n_arm < 1:
        code = "collect_empty_book_ok"
        ok = True
        clock = True
        pe = (
            f"bank_trail: CF live n_legs={n_legs} but n_would_arm=0 — "
            "honest empty arm class or sleeve filter; keep collecting."
        )
    else:
        code = "collect_armed" if n_arm >= 1 else "sensor_ok"
        ok = True
        clock = True
        pe = f"bank_trail: CF live n_legs={n_legs} n_would_arm={n_arm} verdict={sun.get('verdict')}."

    gates = sun.get("gates") if isinstance(sun.get("gates"), dict) else {}
    assert isinstance(gates, dict)
    r = MeasureHealthResult(
        ok=ok,
        code=code,
        plain_english=pe,
        collect_clock_ok=clock,
        go_packet_allowed=False,
        checks=checks
        + [
            {
                "name": "sunday_verdict",
                "verdict": sun.get("verdict"),
                "n_would_arm": n_arm,
                "need": gates.get("min_would_arm_legs"),
            }
        ],
        metrics={
            "n_legs": n_legs,
            "n_would_arm_legs": n_arm,
            "verdict": sun.get("verdict"),
            "cf_as_of": cf.get("as_of"),
            "sunday_as_of": sun.get("as_of"),
        },
        name="bank_trail",
    )
    d = r.to_dict()
    d["sensor_ok_day_estimate"] = 1 if clock else 0
    d["repair_hint"] = (
        "If path_mfe dead: fix CF candles. If N_INSUFFICIENT: collect more ballast/core "
        "would-arm legs (need ≥5) — not a meter fail."
    )
    return d


def health_jev_select_few() -> Dict[str, Any]:
    latest = _load_json(STATE_DIR / "jev_select_few_cf_latest.json")
    if not latest:
        r = MeasureHealthResult(
            ok=False,
            code="sensor_thin",
            plain_english="jev_select_few: no latest CF.",
            collect_clock_ok=False,
            go_packet_allowed=False,
            name="jev_select_few",
        )
        return r.to_dict()
    funnel_raw = latest.get("funnel")
    book_raw = latest.get("book")
    funnel: Dict[str, Any] = funnel_raw if isinstance(funnel_raw, dict) else {}
    book: Dict[str, Any] = book_raw if isinstance(book_raw, dict) else {}
    n_buy = int(funnel.get("n_buy") or funnel.get("buy") or 0)
    # crumbs as treatment presence
    crumbs = STATE_DIR / "jev_select_few_cf_crumbs.jsonl"
    n_crumb = 0
    if crumbs.is_file():
        try:
            n_crumb = sum(1 for _ in crumbs.read_text(encoding="utf-8").splitlines() if _.strip())
        except OSError:
            n_crumb = 0
    claim = str(latest.get("claim_class") or "")
    # Degenerate: forever zero closed + zero buy crumbs while measure_only collecting long
    n_closed = int(book.get("n_closed") or funnel.get("n_closed") or 0)
    n_open = int(book.get("n_open") or funnel.get("n_open") or 0)
    if n_crumb == 0 and n_closed == 0 and n_open == 0:
        code = "sensor_thin"
        ok = False
        clock = False
        pe = "jev_select_few: no crumbs and empty book — collector/judgment path quiet or broken."
    elif n_buy == 0 and n_crumb > 20 and n_closed == 0 and n_open == 0:
        # known class: collection gate / floors — meter of judgment may be OK
        code = "collect_empty_book_ok"
        ok = True
        clock = True
        pe = (
            f"jev_select_few: crumbs={n_crumb} but paper seats never open "
            f"(claim={claim}). Check collection floors / eligible-first — not silent GO."
        )
    else:
        code = "sensor_ok" if n_crumb > 0 else "sensor_thin"
        ok = n_crumb > 0
        clock = n_crumb > 0
        pe = (
            f"jev_select_few: crumbs={n_crumb} open={n_open} closed={n_closed} "
            f"claim={claim}."
        )
    r = MeasureHealthResult(
        ok=ok,
        code=code if ok or code.startswith("sensor") else "sensor_thin",
        plain_english=pe,
        collect_clock_ok=clock,
        go_packet_allowed=False,
        metrics={
            "n_crumb": n_crumb,
            "n_open": n_open,
            "n_closed": n_closed,
            "claim_class": claim,
            "as_of": latest.get("as_of"),
        },
        name="jev_select_few",
    )
    d = r.to_dict()
    d["repair_hint"] = (
        "If crumbs exist but seats never open: collection gate / soft floors "
        "(see measure-only-cf-collection-funnel). If no crumbs: Jev lab tick / budget."
    )
    return d


def health_decision_discipline() -> Dict[str, Any]:
    latest = _load_json(STATE_DIR / "tryout_decision_discipline_latest.json")
    triples = STATE_DIR / "tryout_decision_triples.jsonl"
    n_trip = 0
    if triples.is_file():
        try:
            n_trip = sum(1 for _ in triples.read_text(encoding="utf-8").splitlines() if _.strip())
        except OSError:
            n_trip = 0
    if not latest and n_trip == 0:
        r = MeasureHealthResult(
            ok=False,
            code="sensor_thin",
            plain_english="decision_discipline: no latest and no triples.",
            collect_clock_ok=False,
            go_packet_allowed=False,
            name="decision_discipline",
        )
        return r.to_dict()
    last = latest.get("last_triple") if isinstance(latest, dict) else None
    code = "collect_armed" if last else ("sensor_ok" if n_trip else "sensor_thin")
    ok = code != "sensor_thin"
    r = MeasureHealthResult(
        ok=ok,
        code=code,
        plain_english=(
            f"decision_discipline: triples={n_trip} live_apply={latest.get('live_apply')} "
            f"last={((last or {}) if isinstance(last, dict) else {}).get('pair')}"
        ),
        collect_clock_ok=ok,
        go_packet_allowed=False,
        metrics={"n_triples": n_trip, "as_of": latest.get("as_of"), "live_apply": latest.get("live_apply")},
        name="decision_discipline",
    )
    return r.to_dict()


STREAM_REGISTRY: Dict[str, Any] = {
    "w2_would_arm": {
        "fn": health_w2_would_arm,
        "severity_if_bad": "HIGH",
        "repair_hint": W2_CONTRACT["repair_hint"],
    },
    "bank_trail": {
        "fn": health_bank_trail,
        "severity_if_bad": "WARNING",
        "repair_hint": "Re-run CF candles / Sunday review; N_INSUFFICIENT is sample not meter.",
    },
    "jev_select_few": {
        "fn": health_jev_select_few,
        "severity_if_bad": "WARNING",
        "repair_hint": "Crumb path + collection floors (eligible-first).",
    },
    "decision_discipline": {
        "fn": health_decision_discipline,
        "severity_if_bad": "WARNING",
        "repair_hint": "tryout_decision_discipline collector / triples jsonl.",
    },
}


def evaluate_all_streams() -> Dict[str, Any]:
    """Roll up every registered measure stream for ops agent."""
    streams: Dict[str, Any] = {}
    frozen: List[str] = []
    bad: List[str] = []
    for name, meta in STREAM_REGISTRY.items():
        try:
            h = meta["fn"]()
        except Exception as e:
            h = MeasureHealthResult(
                ok=False,
                code="sensor_broken",
                plain_english=f"{name}: health fn raised {e}",
                collect_clock_ok=False,
                go_packet_allowed=False,
                name=name,
            ).to_dict()
        h["repair_hint"] = h.get("repair_hint") or meta.get("repair_hint")
        h["severity_if_bad"] = meta.get("severity_if_bad") or "WARNING"
        streams[name] = h
        if not h.get("collect_clock_ok"):
            frozen.append(name)
        if not h.get("ok"):
            bad.append(name)
    out = {
        "schema": "measure_collect_health_rollup_v1",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "n_streams": len(streams),
        "n_frozen": len(frozen),
        "n_bad": len(bad),
        "frozen": frozen,
        "bad": bad,
        "streams": streams,
        "plain_english": (
            f"measure health rollup: {len(streams)} streams, "
            f"{len(frozen)} clock_FROZEN, {len(bad)} not-ok."
            if frozen or bad
            else f"measure health rollup: {len(streams)} streams all clock_OK."
        ),
    }
    return out


def attach_health_to_snap(snap: Dict[str, Any], health: Dict[str, Any]) -> Dict[str, Any]:
    """Embed health into a would-arm / dig-out snap (mutates copy)."""
    out = dict(snap)
    out["measure_health"] = health
    # freeze day-count eligibility on the snap itself
    out["collect_clock_ok"] = bool(health.get("collect_clock_ok"))
    out["measure_health_code"] = health.get("code")
    return out


def telegram_health_line(health: Dict[str, Any]) -> str:
    code = health.get("code") or "?"
    name = health.get("name") or health.get("metrics", {}).get("name") or "measure"
    clock = "clock_OK" if health.get("collect_clock_ok") else "clock_FROZEN"
    return f"{name} health={code} {clock}"


def stamp_w2_post_fix(ts: Optional[str] = None) -> str:
    """Mark start of clean W2 collect window after meter repair."""
    t = ts or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    W2_POST_FIX_MARKER.write_text(t + "\n", encoding="utf-8")
    return t


if __name__ == "__main__":
    roll = evaluate_all_streams()
    out_path = STATE_DIR / "measure_collect_health_rollup_latest.json"
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(roll, indent=2, default=str) + "\n", encoding="utf-8")
    print(roll["plain_english"])
    for name, h in (roll.get("streams") or {}).items():
        print(f"  · {telegram_health_line(h)}")
    print(f"wrote {out_path}")
