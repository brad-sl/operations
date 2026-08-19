#!/usr/bin/env python3
"""
Kelly dig-further pack (extension of ANALYST-KELLY-SIZING-TEST).

Addresses:
  1) Walk-forward: fit (p,b) on early trades, size on later (no peeking)
  2) Loss-aware scores: growth - λ * max_dd for λ in {0.5, 1.0, 2.0}
  3) Uncapped (risk-only) paths so half vs full actually separate
  4) Multi-asset haircut sensitivity {1.0, 0.5, 0.33}
  5) Time slices as crude "regime" proxies (pre-July vs July+)

Real ledger only. No live config writes.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.kelly_sizing import (  # noqa: E402
    estimate_edge_from_returns,
    fractional_kelly,
    kelly_fraction,
)
from phase6.research.run_kelly_sizing_test import (  # noqa: E402
    MAX_ABS_RETURN,
    MIN_ENTRY_NOTIONAL,
    baseline_risk_fraction,
    enrich_trade,
    load_closed_sells,
    load_config_knobs,
    max_drawdown,
    simulate_path,
)
from phase6.research.production_period_baseline import compute_since_go_live  # noqa: E402

REPORTS = ROOT / "reports"
TRIAL_ID = "ANALYST-KELLY-SIZING-TEST-20260721-TRIAL"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def load_enriched() -> List[dict]:
    rows = []
    for r in load_closed_sells():
        e = enrich_trade(r)
        if not e:
            continue
        ret = e.get("r")
        if ret is None:
            continue
        if abs(float(ret)) > MAX_ABS_RETURN:
            continue
        if float(e.get("entry_notional") or 0) < MIN_ENTRY_NOTIONAL:
            continue
        rows.append(e)
    rows.sort(key=lambda x: _parse_ts(x.get("timestamp") or "") or datetime.min.replace(tzinfo=timezone.utc))
    return rows


def score_path(p: Dict[str, Any], lam: float) -> float:
    g = float(p.get("growth_pct") or 0)
    dd = float(p.get("max_dd_pct") or 0)
    return round(g - lam * dd, 4)


def soft_envelopes(knobs: Dict[str, Any], loose: bool) -> Dict[str, Any]:
    """loose=True → huge caps so Kelly f actually binds path differences."""
    if loose:
        return {
            "min_reserve_usd": float(knobs["min_reserve_usd"]),
            "deploy_pct": 0.99,
            "regime_target_max_util_pct": 0.99,
            "max_position_usd": 1e9,
            "already_deployed_usd": 0.0,
        }
    return {
        "min_reserve_usd": float(knobs["min_reserve_usd"]),
        "deploy_pct": float(knobs["deploy_pct"]),
        "regime_target_max_util_pct": float(knobs["regime_flat_target_max_util_pct"]),
        "max_position_usd": 800.0,
        "already_deployed_usd": 0.0,
    }


def run_paths(
    returns: List[float],
    start_eq: float,
    sl: float,
    knobs: Dict[str, Any],
    f_full: float,
    haircut: float,
    loose: bool,
) -> Dict[str, Dict[str, Any]]:
    env = soft_envelopes(knobs, loose=loose)
    base_f = baseline_risk_fraction(knobs["deploy_pct"], sl)["path_baseline_f"]
    f_half = max(0.0, f_full * 0.5 * haircut)
    f_q = max(0.0, f_full * 0.25 * haircut)
    f_full_h = max(0.0, f_full * haircut)
    out = {
        "baseline_1pct_risk": simulate_path(returns, base_f, sl, start_eq, env, "baseline_1pct_risk"),
        "quarter_kelly": simulate_path(returns, f_q, sl, start_eq, env, "quarter_kelly"),
        "half_kelly": simulate_path(returns, f_half, sl, start_eq, env, "half_kelly"),
        "full_kelly": simulate_path(returns, f_full_h, sl, start_eq, env, "full_kelly"),
    }
    for k, v in out.items():
        v["haircut"] = haircut
        v["loose_envelopes"] = loose
        v["scores"] = {f"lam_{lam}": score_path(v, lam) for lam in (0.5, 1.0, 2.0)}
    return out


def walk_forward(rows: List[dict], knobs: Dict[str, Any], sl: float, start_eq: float) -> Dict[str, Any]:
    n = len(rows)
    if n < 40:
        return {"ok": False, "reason": f"n={n}<40 for walk-forward"}
    # 50/50 chronological split
    cut = n // 2
    train = rows[:cut]
    test = rows[cut:]
    train_r = [float(x["r"]) for x in train]
    test_r = [float(x["r"]) for x in test]
    edge_tr = estimate_edge_from_returns(train_r)
    edge_te = estimate_edge_from_returns(test_r)
    f_tr = float(edge_tr.get("f_full") or 0.0)
    # size ONLY from train edge on test returns
    paths_loose = run_paths(test_r, start_eq, sl, knobs, f_tr, haircut=0.5, loose=True)
    paths_live = run_paths(test_r, start_eq, sl, knobs, f_tr, haircut=0.5, loose=False)
    # oracle cheat (diagnostic): fit on test — should not drive decisions
    f_te = float(edge_te.get("f_full") or 0.0)
    paths_oracle = run_paths(test_r, start_eq, sl, knobs, f_te, haircut=0.5, loose=True)
    return {
        "ok": True,
        "n_train": len(train),
        "n_test": len(test),
        "train_ts": [train[0].get("timestamp"), train[-1].get("timestamp")],
        "test_ts": [test[0].get("timestamp"), test[-1].get("timestamp")],
        "edge_train": edge_tr,
        "edge_test": edge_te,
        "f_full_train": f_tr,
        "f_full_test": f_te,
        "paths_test_sized_from_train_loose": paths_loose,
        "paths_test_sized_from_train_live_envelopes": paths_live,
        "paths_test_oracle_fit_on_test_loose_DIAGNOSTIC": paths_oracle,
    }


def haircut_grid(returns: List[float], knobs: Dict[str, Any], sl: float, start_eq: float, f_full: float) -> Dict[str, Any]:
    grid = {}
    for h in (1.0, 0.5, 0.33):
        grid[f"haircut_{h}"] = {
            "loose": run_paths(returns, start_eq, sl, knobs, f_full, h, loose=True),
            "live_env": run_paths(returns, start_eq, sl, knobs, f_full, h, loose=False),
        }
    return grid


def time_slices(rows: List[dict]) -> Dict[str, Any]:
    out = {}
    july = datetime(2026, 7, 1, tzinfo=timezone.utc)
    pre = [r for r in rows if (_parse_ts(r.get("timestamp") or "") or july) < july]
    post = [r for r in rows if (_parse_ts(r.get("timestamp") or "") or july) >= july]
    for label, part in (("pre_2026-07", pre), ("from_2026-07", post), ("full", rows)):
        rets = [float(x["r"]) for x in part]
        edge = estimate_edge_from_returns(rets) if rets else {"n": 0, "f_full": 0}
        out[label] = {"n": len(part), "edge": edge}
    return out


def plain_english_verdict(wf: Dict[str, Any], slices: Dict[str, Any]) -> Dict[str, Any]:
    """Human-readable decision helper — not auto-promote."""
    bullets = []
    enum = "drop"
    go_shadow = False

    if not wf.get("ok"):
        return {
            "enum": "continue_observe_only",
            "go_shadow": False,
            "headline": "Not enough clean trades for walk-forward.",
            "bullets": [wf.get("reason")],
            "what_this_means": "Keep collecting real closed trades; do not change sizing.",
        }

    f_tr = float(wf.get("f_full_train") or 0)
    f_te = float(wf.get("f_full_test") or 0)
    bullets.append(f"Train-period Kelly full fraction was {f_tr:.3f}; test-period edge Kelly was {f_te:.3f}.")
    if f_te <= 0:
        bullets.append("On the later half of trades, measured edge was zero/negative — any size from early wins would have been betting a cold streak.")
    if f_tr > 0 and f_te <= 0:
        bullets.append("Classic trap: early good results → large Kelly → later losses get amplified if you had sized up.")

    loose = wf.get("paths_test_sized_from_train_loose") or {}
    base = loose.get("baseline_1pct_risk") or {}
    half = loose.get("half_kelly") or {}
    full = loose.get("full_kelly") or {}
    quarter = loose.get("quarter_kelly") or {}

    # Separate half vs full?
    half_g, full_g = half.get("growth_pct"), full.get("growth_pct")
    half_dd, full_dd = half.get("max_dd_pct"), full.get("max_dd_pct")
    if half_g is not None and full_g is not None:
        if abs(float(half_g) - float(full_g)) < 0.05 and abs(float(half_dd or 0) - float(full_dd or 0)) < 0.05:
            bullets.append("Even with loose caps, half and full paths still look almost identical — edge on test is too weak for Kelly fraction to matter.")
        else:
            bullets.append(
                f"With loose caps (Kelly can actually bite): half growth={half_g}% DD={half_dd}% vs full growth={full_g}% DD={full_dd}% vs baseline growth={base.get('growth_pct')}% DD={base.get('max_dd_pct')}%."
            )

    # λ=1 and λ=2: does half beat baseline?
    def beats(path: dict, lam: float) -> bool:
        return score_path(path, lam) > score_path(base, lam) + 1.0 and float(path.get("max_dd_pct") or 99) <= float(base.get("max_dd_pct") or 0) + 2.0

    for lam in (0.5, 1.0, 2.0):
        bullets.append(
            f"Score growth−{lam}×DD on test (loose): "
            f"base={score_path(base, lam)}, quarter={score_path(quarter, lam)}, "
            f"half={score_path(half, lam)}, full={score_path(full, lam)}"
        )

    live_paths = wf.get("paths_test_sized_from_train_live_envelopes") or {}
    live_half = live_paths.get("half_kelly") or {}
    live_base = live_paths.get("baseline_1pct_risk") or {}
    bullets.append(
        f"With live-like envelopes on test: half growth={live_half.get('growth_pct')} DD={live_half.get('max_dd_pct')} "
        f"vs baseline growth={live_base.get('growth_pct')} DD={live_base.get('max_dd_pct')}."
    )

    july = (slices.get("from_2026-07") or {}).get("edge") or {}
    bullets.append(
        f"July+ slice: n={july.get('n')}, win rate p={july.get('p')}, Kelly full={july.get('f_full')} "
        f"(if ≤0, recent book should not size up)."
    )

    # Decision rules (conservative)
    if f_te <= 0 or f_tr <= 0:
        enum = "drop"
        go_shadow = False
        headline = "No opportunity to promote Kelly sizing — out-of-sample edge failed."
        meaning = (
            "The first report’s high Half-Kelly growth used the same trades to both "
            "estimate luck and size the bets (like grading a test with the answer key). "
            "When we only use early trades to set size and later trades to judge, Kelly "
            "does not beat careful small sizing. Do not turn on a Kelly shadow."
        )
    elif beats(half, 1.0) or beats(quarter, 1.0):
        enum = "propose_scoped_shadow_experiment"
        go_shadow = True
        which = "half" if beats(half, 1.0) else "quarter"
        headline = f"Weak but interesting: {which}-Kelly beat baseline on walk-forward with DD discipline (λ=1)."
        meaning = "Only then consider a tiny shadow overlay — still not live. Needs your go."
    elif score_path(half, 0.5) > score_path(base, 0.5) + 1 and float(half.get("max_dd_pct") or 0) > float(base.get("max_dd_pct") or 0) + 2:
        enum = "drop"
        go_shadow = False
        headline = "Kelly only 'wins' if we under-weight drawdowns — that fights your loss-minimizing goal."
        meaning = "Chasing growth with bigger DD is the opposite of what you asked for."
    else:
        enum = "drop"
        go_shadow = False
        headline = "Walk-forward does not support Kelly over baseline 1% risk."
        meaning = "Stick with current risk language; revisit when more stable winning trades accumulate."

    return {
        "enum": enum,
        "go_shadow": go_shadow,
        "headline": headline,
        "bullets": bullets,
        "what_this_means": meaning,
    }


def render_md(payload: Dict[str, Any]) -> str:
    v = payload["verdict"]
    wf = payload["walk_forward"]
    lines = [
        f"# Kelly dig-further — {_now()[:10]}",
        "",
        f"**Trial:** `{TRIAL_ID}`  ",
        f"**Parent report:** `reports/KELLY_SIZING_TEST_2026-07-21.md`  ",
        f"**Real data only:** True · **Live writes:** False",
        "",
        "## Plain-English verdict",
        "",
        f"### {v['headline']}",
        "",
        v["what_this_means"],
        "",
        f"- **Recommendation enum:** `{v['enum']}`",
        f"- **Shadow go?** **{v['go_shadow']}**",
        "",
        "### Why (short bullets)",
        "",
    ]
    for b in v.get("bullets") or []:
        lines.append(f"- {b}")
    lines += [
        "",
        "## What we added vs the first report",
        "",
        "| Dig | Why it matters |",
        "|-----|----------------|",
        "| Walk-forward | Stops using the same trades to both invent Kelly and grade it |",
        "| Scores growth−λ×DD | λ=2 = you hate drawdowns more; λ=0.5 = growth-chasing |",
        "| Loose envelopes | Lets half vs full Kelly actually differ (first report caps made them identical) |",
        "| Haircut grid | Concurrent multi-pair book needs smaller effective f |",
        "| Time slices | Early vs July+ shows if edge died |",
        "",
        "## Walk-forward summary",
        "",
    ]
    if wf.get("ok"):
        et, ee = wf.get("edge_train") or {}, wf.get("edge_test") or {}
        lines += [
            f"- Train n={wf['n_train']} ({wf['train_ts'][0]} → {wf['train_ts'][1]})",
            f"- Test n={wf['n_test']} ({wf['test_ts'][0]} → {wf['test_ts'][1]})",
            f"- Train: p={et.get('p')} b={et.get('b')} f_full={et.get('f_full')}",
            f"- Test:  p={ee.get('p')} b={ee.get('b')} f_full={ee.get('f_full')}",
            "",
            "### Test window paths — size from **train** only, **loose** caps",
            "",
            "| Path | Growth % | Max DD % | score λ=0.5 | λ=1 | λ=2 |",
            "|------|----------|----------|-------------|-----|-----|",
        ]
        for name, p in (wf.get("paths_test_sized_from_train_loose") or {}).items():
            sc = p.get("scores") or {}
            lines.append(
                f"| {name} | {p.get('growth_pct')} | {p.get('max_dd_pct')} | "
                f"{sc.get('lam_0.5')} | {sc.get('lam_1.0')} | {sc.get('lam_2.0')} |"
            )
        lines += [
            "",
            "### Test window — size from train, **live-like** envelopes",
            "",
            "| Path | Growth % | Max DD % | score λ=1 |",
            "|------|----------|----------|-----------|",
        ]
        for name, p in (wf.get("paths_test_sized_from_train_live_envelopes") or {}).items():
            sc = p.get("scores") or {}
            lines.append(f"| {name} | {p.get('growth_pct')} | {p.get('max_dd_pct')} | {sc.get('lam_1.0')} |")
    else:
        lines.append(f"- Walk-forward skipped: {wf.get('reason')}")

    lines += [
        "",
        "## Time-slice edge (crude regime proxy)",
        "",
        "```json",
        json.dumps(payload.get("time_slices"), indent=2)[:2500],
        "```",
        "",
        "## Haircut sensitivity (full sample, diagnostic)",
        "",
        "See JSON for full grid. Rule of thumb: if only haircut=1 (no multi-asset cut) looks good, ignore it for live.",
        "",
        "## Decide (Brad)",
        "",
        "First report already leaned `drop`. Dig-further is the tie-breaker:",
        "",
        "```bash",
        f"python3 phase6/research/trial_cycle.py decide {TRIAL_ID} {v['enum']} --note 'dig-further {REPORTS.name}/KELLY_SIZING_TEST_DIG_*.md'",
        "```",
        "",
        "## Files",
        "",
        f"- `reports/KELLY_SIZING_TEST_DIG_{_now()[:10]}.md`",
        f"- `reports/KELLY_SIZING_TEST_DIG_{_now()[:10]}.json`",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    knobs = load_config_knobs()
    sl = float(knobs["stop_loss_pct"])
    rows = load_enriched()
    rets = [float(r["r"]) for r in rows]
    try:
        base = compute_since_go_live()
        start_eq = float(base.get("start_equity_usd") or 748.18)
    except Exception:
        start_eq = 748.18

    edge_full = estimate_edge_from_returns(rets)
    f_full = float(edge_full.get("f_full") or 0.0)

    wf = walk_forward(rows, knobs, sl, start_eq)
    slices = time_slices(rows)
    grid = haircut_grid(rets, knobs, sl, start_eq, f_full) if rets else {}
    # full-sample loose separation diagnostic
    sep = run_paths(rets, start_eq, sl, knobs, f_full, haircut=0.5, loose=True) if rets else {}

    verdict = plain_english_verdict(wf, slices)
    payload = {
        "generated_at": _now(),
        "trial_id": TRIAL_ID,
        "n_plausible": len(rows),
        "start_equity": start_eq,
        "edge_full_sample": edge_full,
        "walk_forward": wf,
        "time_slices": slices,
        "haircut_grid_meta": {
            "note": "nested paths under haircut_*; loose vs live_env",
            "haircuts": [1.0, 0.5, 0.33],
        },
        "haircut_grid": grid,
        "full_sample_loose_separation": sep,
        "verdict": verdict,
        "live_writes": False,
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    day = _now()[:10]
    jp = REPORTS / f"KELLY_SIZING_TEST_DIG_{day}.json"
    mp = REPORTS / f"KELLY_SIZING_TEST_DIG_{day}.md"
    jp.write_text(json.dumps(payload, indent=2) + "\n")
    mp.write_text(render_md(payload))

    # Update trial
    tp = ROOT / "data" / "state" / "trials" / f"{TRIAL_ID}.json"
    if tp.exists():
        t = json.loads(tp.read_text())
        t.setdefault("reports", []).append(
            {"phase": "dig_further", "path": str(mp.relative_to(ROOT)), "at": _now(), "recommendation": verdict.get("enum")}
        )
        t["dig_further"] = {
            "at": _now(),
            "enum": verdict.get("enum"),
            "go_shadow": verdict.get("go_shadow"),
            "headline": verdict.get("headline"),
            "report": str(mp.relative_to(ROOT)),
        }
        t["updated_at"] = _now()
        tp.write_text(json.dumps(t, indent=2) + "\n")

    print(json.dumps({"report_md": str(mp), "report_json": str(jp), "verdict": verdict}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
