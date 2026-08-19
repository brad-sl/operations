#!/usr/bin/env python3
"""
Validate live REGIME-CASH setup against the modeled scorecard / scenario pack.

Writes:
  data/state/regime_cash_validation_latest.json
  data/state/regime_cash_validation_history.jsonl  (append)

Each run records: test scenario, duration, expectation, results, improvement vs prior.
Never auto-promotes live config.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.core.regime_cash_policy import load_policy, persist_status, resolve_regime_cash

LATEST = ROOT / "data/state/regime_cash_validation_latest.json"
HISTORY = ROOT / "data/state/regime_cash_validation_history.jsonl"
SCORECARD = ROOT / "data/state/analyst_regime_scorecard_latest.json"
SWEEP = ROOT / "data/state/regime_cash_param_sweep_latest.json"
OPT = ROOT / "data/state/regime_cash_optimization_latest.json"
LEADERBOARD = ROOT / "data/state/analyst_scenario_leaderboard_latest.json"
KNOB = ROOT / "config/regime_knob_map.json"
CONTINUOUS = ROOT / "phase6/research/run_regime_cash_continuous.py"
PRODUCTION = ROOT / "data/state/phase6_runner_state.json"


def _load(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _scorecard_regime(scorecard: dict, name: str) -> Optional[dict]:
    for rg in scorecard.get("regimes") or []:
        if rg.get("regime") == name:
            return rg
    # transition mapped from recent
    if name == "transition":
        for rg in scorecard.get("regimes") or []:
            if rg.get("regime") == "recent":
                return rg
    return None


def _scenario_brief(rg: dict, limit: int = 6) -> List[dict]:
    rows = []
    for sc in rg.get("scenarios") or []:
        m = sc.get("metrics") or {}
        rows.append(
            {
                "id": sc.get("id"),
                "total_return_pct": m.get("total_return_pct"),
                "max_drawdown_pct": m.get("max_drawdown_pct"),
                "sharpe_ratio": m.get("sharpe_ratio"),
                "total_trades": m.get("total_trades"),
                "error": sc.get("error"),
            }
        )
    rows.sort(
        key=lambda r: (
            r.get("total_return_pct") is None,
            -(r.get("total_return_pct") or -9999.0),
        )
    )
    return rows[:limit]


def _prior_history(n: int = 20) -> List[dict]:
    if not HISTORY.exists():
        return []
    lines = HISTORY.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _improvement(current: dict, prior: Optional[dict]) -> dict:
    if not prior:
        return {"has_prior": False, "note": "first validation run — baseline established"}
    cur_v = (current.get("results") or {}).get("verdict")
    pri_v = (prior.get("results") or {}).get("verdict")
    cur_checks = {(c.get("id"), c.get("pass")) for c in (current.get("results") or {}).get("checks") or []}
    pri_checks = {(c.get("id"), c.get("pass")) for c in (prior.get("results") or {}).get("checks") or []}
    gained = [cid for cid, ok in cur_checks if ok and (cid, False) in pri_checks]
    lost = [cid for cid, ok in cur_checks if not ok and (cid, True) in pri_checks]
    return {
        "has_prior": True,
        "prior_run_id": prior.get("run_id"),
        "prior_verdict": pri_v,
        "verdict_changed": cur_v != pri_v,
        "checks_improved": gained,
        "checks_regressed": lost,
        "prior_duration_sec": prior.get("duration_sec"),
        "duration_delta_sec": round(
            float(current.get("duration_sec") or 0) - float(prior.get("duration_sec") or 0), 3
        ),
    }


def main() -> int:
    t0 = time.perf_counter()
    started = datetime.now(timezone.utc)
    run_id = f"RCV-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"

    # 1) Refresh continuous loop (resolve + protected knob apply + sweep + recommendations)
    cont = subprocess.run(
        [sys.executable, str(CONTINUOUS)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": str(ROOT)},
        timeout=900,
    )
    cont_ok = cont.returncode == 0

    pol = load_policy()
    snap = resolve_regime_cash(policy=pol)
    persist_status(snap)
    scorecard = _load(SCORECARD) or {}
    sweep = _load(SWEEP) or {}
    opt = _load(OPT) or {}
    knob = _load(KNOB) or {}
    lb = _load(LEADERBOARD) or {}
    prod = _load(PRODUCTION) or {}

    live_regime = snap.regime
    rg = _scorecard_regime(scorecard, live_regime) or {}
    # If live is flat, also keep recent window for "current market" flavor
    recent_rg = _scorecard_regime(scorecard, "transition") or _scorecard_regime(scorecard, "recent") or {}

    modeled_winner = rg.get("optimal_strategy_id") or rg.get("winner_id")
    usdc_opt = rg.get("usdc_optimal") or {}
    alt_beats = usdc_opt.get("alt_beats_usdc_carry")
    date_range = rg.get("date_range") or {}

    knob_flat = (knob.get("regimes") or {}).get(live_regime) or (knob.get("regimes") or {}).get("flat") or {}
    operator_ov = knob_flat.get("operator_override") or {}

    # Expectations for option-B style gated deploy under flat
    expectation = {
        "statement": (
            f"Live REGIME-CASH ({live_regime}) should remain enforce=true with automated gates; "
            f"scorecard window for {live_regime} is compared honestly. "
            f"If scorecard prefers usdc_hold while operator_override protects cautious deploy, "
            f"verdict=tension (acceptable experiment) not silent fail — promotion still gated."
        ),
        "pass_criteria": [
            {"id": "enforce_on", "expect": "enforce==true and enabled==true"},
            {"id": "gates_present", "expect": "entry min_sentiment and max_rsi set"},
            {"id": "cap_bounded", "expect": "rebalance_cap_usd in (0, 150] when deploy; 0 when park"},
            {"id": "knob_protected_if_override", "expect": "operator_override.protect keeps deploy if set"},
            {"id": "scorecard_loaded", "expect": "scorecard has regime window for live or pack"},
            {"id": "continuous_ok", "expect": "run_regime_cash_continuous exit 0"},
            {"id": "no_auto_promote", "expect": "optimization auto_promote is false"},
            {
                "id": "model_alignment",
                "expect": "if scorecard optimal is usdc_hold and live is deploy → tension; if both park or both deploy-with-winner → aligned",
            },
        ],
    }

    checks: List[dict] = []

    def add(cid: str, ok: bool, detail: str, **extra):
        checks.append({"id": cid, "pass": bool(ok), "detail": detail, **extra})

    add("continuous_ok", cont_ok, f"returncode={cont.returncode} stdout_tail={(cont.stdout or '')[-300:]}")
    add("enforce_on", bool(snap.enforce and snap.enabled), f"enforce={snap.enforce} enabled={snap.enabled}")
    entry = snap.entry or {}
    add(
        "gates_present",
        entry.get("min_sentiment") is not None and entry.get("max_rsi") is not None,
        f"entry={entry}",
    )
    cap = float(snap.rebalance_cap_usd or 0)
    if snap.strategy_mode == "usdc_park" or not snap.allow_new_buys:
        add("cap_bounded", cap <= 0.0, f"park mode cap={cap}")
    else:
        add("cap_bounded", 0 < cap <= 150.0, f"deploy mode cap={cap}")

    if operator_ov.get("reason"):
        protected = bool(operator_ov.get("protect", True))
        still_deploy = snap.strategy_mode == "deploy" and snap.allow_new_buys
        add(
            "knob_protected_if_override",
            protected and still_deploy,
            f"override={operator_ov} mode={snap.strategy_mode} buys={snap.allow_new_buys}",
        )
    else:
        add("knob_protected_if_override", True, "no operator_override on live regime")

    add(
        "scorecard_loaded",
        bool(scorecard.get("regimes")),
        f"pack={scorecard.get('pack_id')} generated={scorecard.get('generated_at')} window={date_range}",
    )
    add(
        "no_auto_promote",
        (opt.get("auto_promote") is False) or (opt.get("auto_promote") is None),
        f"auto_promote={opt.get('auto_promote')}",
    )

    live_park = snap.strategy_mode == "usdc_park" or not snap.allow_new_buys
    model_park = (modeled_winner == "usdc_hold") or (alt_beats is False and modeled_winner == "usdc_hold")
    if not rg:
        alignment = "unknown"
        align_ok = True
        align_detail = "no scorecard row for live regime"
    elif live_park and model_park:
        alignment = "aligned_park"
        align_ok = True
        align_detail = f"live park matches scorecard winner={modeled_winner}"
    elif (not live_park) and modeled_winner and modeled_winner != "usdc_hold" and alt_beats:
        alignment = "aligned_deploy"
        align_ok = True
        align_detail = f"live deploy matches risk-on winner={modeled_winner} alt_beats_usdc={alt_beats}"
    elif (not live_park) and (modeled_winner == "usdc_hold" or alt_beats is False):
        alignment = "tension_operator_thaw"
        align_ok = True  # expected under option B — flag not fail
        align_detail = (
            f"scorecard prefers {modeled_winner} (alt_beats_usdc={alt_beats}) on {date_range}; "
            f"live is gated deploy cap={cap} under operator_override — research says cash better on that window"
        )
    else:
        alignment = "mixed"
        align_ok = True
        align_detail = f"live_park={live_park} winner={modeled_winner} alt_beats={alt_beats}"

    add("model_alignment", align_ok, align_detail, alignment=alignment)

    # Hard fails only
    hard_ids = {"enforce_on", "gates_present", "cap_bounded", "continuous_ok", "knob_protected_if_override"}
    hard_fail = [c for c in checks if c["id"] in hard_ids and not c["pass"]]
    if hard_fail:
        verdict = "fail"
    elif alignment == "tension_operator_thaw":
        verdict = "tension"
    elif all(c["pass"] for c in checks):
        verdict = "pass"
    else:
        verdict = "pass_with_warnings"

    finished = datetime.now(timezone.utc)
    duration = round(time.perf_counter() - t0, 3)

    # Weekly leaderboard winner (pack-level)
    lb_rank = lb.get("ranking") or []
    if isinstance(lb_rank, list):
        top_lb = lb_rank[:5]
    else:
        top_lb = []

    payload = {
        "schema": "regime_cash_validation_v1",
        "run_id": run_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_sec": duration,
        "live_setup": {
            "regime": snap.regime,
            "confidence": snap.confidence,
            "btc_return_pct": snap.btc_return_pct,
            "strategy_mode": snap.strategy_mode,
            "allow_new_buys": snap.allow_new_buys,
            "rebalance_cap_usd": snap.rebalance_cap_usd,
            "target_max_util_pct": snap.target_max_util_pct,
            "entry": snap.entry,
            "exit": snap.exit,
            "label": snap.label,
            "enforce": snap.enforce,
            "enabled": snap.enabled,
            "knob_map_scenario": snap.knob_map_scenario,
            "operator_override": operator_ov or None,
            "last_rebalance_date": prod.get("last_rebalance_date"),
            "rebalance_slots_tail": (prod.get("rebalance_slots_completed") or [])[-4:],
        },
        "test_scenario": {
            "pack_id": scorecard.get("pack_id"),
            "primary_metric": scorecard.get("primary_metric"),
            "scorecard_generated_at": scorecard.get("generated_at"),
            "regime_window": live_regime,
            "date_range": date_range,
            "modeled_winner": modeled_winner,
            "modeled_optimal": usdc_opt.get("optimal_strategy_id"),
            "best_alt": usdc_opt.get("best_alt_strategy_id"),
            "best_alt_ann_pct": usdc_opt.get("best_alt_annualized_return_pct"),
            "usdc_ann_pct": usdc_opt.get("usdc_annualized_return_pct") or usdc_opt.get("optimal_annualized_return_pct"),
            "alt_beats_usdc_carry": alt_beats,
            "top_scenarios": _scenario_brief(rg) if rg else [],
            "recent_window": {
                "date_range": (recent_rg or {}).get("date_range"),
                "winner_id": (recent_rg or {}).get("winner_id"),
                "optimal": ((recent_rg or {}).get("usdc_optimal") or {}).get("optimal_strategy_id"),
                "top_scenarios": _scenario_brief(recent_rg) if recent_rg else [],
            },
            "leaderboard_top": top_lb,
            "param_sweep_best": sweep.get("best"),
            "continuous_recommendations": opt.get("recommendations"),
        },
        "expectation": expectation,
        "results": {
            "verdict": verdict,
            "alignment": alignment,
            "checks": checks,
            "summary": align_detail if rg else "scorecard missing regime row",
            "promotion": {
                "auto_promote": False,
                "allowed_now": False,
                "reason": (
                    "tension: scorecard favors USDC on flat window — keep gated deploy experimental; "
                    "promote only if future packs beat USDC + live_param_audit + shadow"
                    if alignment == "tension_operator_thaw"
                    else "no auto-promote; require live_param_audit + USDC hurdle + shadow"
                ),
            },
        },
        "improvement": {},  # filled below
    }

    prior_list = _prior_history()
    prior = prior_list[-1] if prior_list else None
    payload["improvement"] = _improvement(payload, prior)

    # Simple rolling stats for history consumers
    verdicts = [p.get("results", {}).get("verdict") for p in prior_list] + [verdict]
    # sorted() cannot mix None with str (TypeError on py3.11+)
    verdict_keys = sorted({v for v in verdicts if v is not None}, key=str)
    if any(v is None for v in verdicts):
        verdict_keys.append(None)
    payload["history_stats"] = {
        "n_prior": len(prior_list),
        "n_including_this": len(verdicts),
        "verdict_counts": {
            ("null" if v is None else v): sum(1 for x in verdicts if x == v)
            for v in verdict_keys
        },
    }

    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with HISTORY.open("a", encoding="utf-8") as f:
        # compact history row
        hist = {
            "run_id": run_id,
            "started_at": payload["started_at"],
            "duration_sec": duration,
            "live_regime": snap.regime,
            "live_mode": snap.strategy_mode,
            "cap": snap.rebalance_cap_usd,
            "pack_id": scorecard.get("pack_id"),
            "window": date_range,
            "modeled_winner": modeled_winner,
            "expectation_summary": expectation["statement"][:200],
            "verdict": verdict,
            "alignment": alignment,
            "checks_passed": sum(1 for c in checks if c["pass"]),
            "checks_total": len(checks),
            "improvement": payload["improvement"],
        }
        f.write(json.dumps(hist) + "\n")

    print(
        f"REGIME-CASH validation {verdict} alignment={alignment} "
        f"duration={duration}s run_id={run_id} → {LATEST}"
    )
    for c in checks:
        mark = "OK" if c["pass"] else "FAIL"
        print(f"  [{mark}] {c['id']}: {c['detail'][:140]}")
    if payload["improvement"].get("has_prior"):
        print(
            f"  improvement: verdict_changed={payload['improvement'].get('verdict_changed')} "
            f"gained={payload['improvement'].get('checks_improved')} "
            f"lost={payload['improvement'].get('checks_regressed')}"
        )
    return 0 if verdict != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
