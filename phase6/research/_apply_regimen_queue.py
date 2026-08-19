#!/usr/bin/env python3
"""
Apply TEST_REGIMEN_E2E hygiene to queue:
- Retrofit CLOSED trials with success_criteria, outcome, follow_on, decision packets
  WITHOUT changing decision enums.
- Upgrade planned roadmap items with design + success_criteria + protocol paths.
Does NOT close planned/placeholder future work.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from phase6.research import trial_cycle as tc  # noqa: E402

TRIALS = ROOT / "data" / "state" / "trials"
PROTO = ROOT / "docs" / "testing" / "trials"
NOW = datetime.now(timezone.utc).isoformat()
DAY = datetime.now(timezone.utc).strftime("%Y%m%d")

# Reconstruct regimen fields from known closed work. Decisions are frozen.
CLOSED_PATCH: Dict[str, Dict[str, Any]] = {
    "ANALYST-KELLY-SIZING-TEST-20260721-TRIAL": {
        "design": {
            "hypothesis": "Half/quarter Kelly risk-at-SL improves growth/DD vs fixed knobs",
            "primary_window": "ledger_oos",
            "legacy_debt": True,
        },
        "success_criteria": {
            "primary_window": "ledger_oos",
            "min_n_trades": 15,
            "require_both_ret_and_dd": True,
            "live_promote_allowed": False,
            "sparse_is": "inconclusive_not_promote",
            "shadow_ok_if": "primary_pass_and_n_ok",
        },
        "outcome": {
            "class": "unstable_or_no_edge",
            "primary_pass": False,
            "plain_english": "OOS edge fail; drop — no shadow promote.",
            "at": NOW,
            "retrofit": True,
        },
        "follow_on": {"mode": "none", "detail": "No Kelly promote line; sizing research stays gated.", "at": NOW},
        "cr": "REJECT",
    },
    "ANALYST-REGIME-BULL-KNOBS-20260803-TRIAL": {
        "design": {
            "hypothesis": "Bull live knobs under-deploy or over-trade vs scorecard winner",
            "primary_window": "bull_windows",
            "legacy_debt": True,
            "note": "Zombie: execute cron never produced reports — abort is process, not market reject.",
        },
        "success_criteria": {
            "primary_window": "bull_windows",
            "min_n_trades": 15,
            "require_both_ret_and_dd": True,
            "live_promote_allowed": False,
            "sparse_is": "inconclusive_not_promote",
        },
        "outcome": {
            "class": "process_incomplete",
            "primary_pass": False,
            "plain_english": "No dig landed (reports=[]). Abort frees slot. Real bull test is PLAN-BULL-KNOBS-002.",
            "at": NOW,
            "retrofit": True,
        },
        "follow_on": {
            "mode": "extend",
            "detail": "PLAN-BULL-KNOBS-002 planned; emit_only_when_regime=bull",
            "at": NOW,
        },
        "cr": "REJECT",  # abort = reject process
        "placeholder_for_real_test": False,
        "successor_is_real_test": "PLAN-BULL-KNOBS-002",
    },
    "ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL": {
        "design": {
            "hypothesis": "Under flat option B, rebalance beats rotation; nearby grid may improve without bull rotation knobs",
            "primary_window": "flat_live_overlap",
            "legacy_debt": True,
        },
        "success_criteria": {
            "primary_window": "flat_live_overlap",
            "min_n_trades": 15,
            "require_both_ret_and_dd": True,
            "live_promote_allowed": False,
            "sparse_is": "inconclusive_not_promote",
            "shadow_ok_if": "primary_pass_and_n_ok",
        },
        "outcome": {
            "class": "HIT_CRITERIA",  # proposed scoped experiment — partial accept path
            "primary_pass": True,
            "plain_english": "Scoped experiment proposed (not full promote). CR ACCEPT scoped only.",
            "at": NOW,
            "retrofit": True,
        },
        "follow_on": {
            "mode": "scoped_shadow",
            "detail": "propose_scoped_experiment — shadow/param_audit only; no live write",
            "at": NOW,
        },
        "cr": "ACCEPT",
    },
    "ANALYST-REGIME-TRANSITION-20260727-TRIAL": {
        "design": {
            "hypothesis": "Transition cap/park settings drive unnecessary whipsaw or idle cash",
            "primary_window": "transition_slices",
            "legacy_debt": True,
        },
        "success_criteria": {
            "primary_window": "transition_slices",
            "min_n_trades": 10,
            "require_both_ret_and_dd": True,
            "live_promote_allowed": False,
            "sparse_is": "inconclusive_not_promote",
        },
        "outcome": {
            "class": "unstable_or_no_edge",
            "primary_pass": False,
            "plain_english": "Drop — no transition knob promote from this dig.",
            "at": NOW,
            "retrofit": True,
        },
        "follow_on": {"mode": "none", "detail": "No transition promote line from this trial.", "at": NOW},
        "cr": "REJECT",
    },
    "ANALYST-STOCH-SL-PREDICTOR-20260803": {
        "design": {
            "hypothesis": "Entry-time Stoch predicts SL better than chance (not exit-time reverse causality)",
            "primary_window": "entry_time_forward_sl",
            "legacy_debt": True,
        },
        "success_criteria": {
            "primary_window": "entry_time_forward_sl",
            "min_n_trades": 15,
            "require_both_ret_and_dd": False,
            "live_promote_allowed": False,
            "sparse_is": "inconclusive_not_promote",
            "utility_lift_min": 1.0,
        },
        "outcome": {
            "class": "unstable_or_no_edge",
            "primary_pass": False,
            "plain_english": "no_utility_drop → decide drop. No combo-fish.",
            "at": NOW,
            "retrofit": True,
        },
        "follow_on": {"mode": "none", "detail": "No RSI+Stoch combo fishing; parent observe path separate.", "at": NOW},
        "cr": "REJECT",
    },
    "STOCH-RSI-PARALLEL-20260721": {
        "design": {
            "hypothesis": "Stoch adds SL/risk timing edge beyond RSI alone",
            "primary_window": "parallel_instrumentation_window",
            "legacy_debt": True,
        },
        "success_criteria": {
            "primary_window": "parallel_instrumentation_window",
            "min_n_trades": 15,
            "require_both_ret_and_dd": False,
            "live_promote_allowed": False,
            "sparse_is": "inconclusive_not_promote",
        },
        "outcome": {
            "class": "inconclusive_sparse_N",
            "primary_pass": False,
            "plain_english": "continue_observe_only — not promote; ~30d re-eval calendar.",
            "at": NOW,
            "retrofit": True,
        },
        "follow_on": {
            "mode": "extend",
            "detail": "NEEDS_REEVAL ~2026-09-03 counterfactual (continue_observe_only)",
            "at": NOW,
        },
        "cr": "NO_CR",
    },
    "TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL": {
        "design": {
            "hypothesis": "MACD×RSI×ATR confluence beats BASE on long tape",
            "primary_window": "long_tape",
            "legacy_debt": True,
        },
        "success_criteria": {
            "primary_window": "long_tape",
            "min_n_trades": 15,
            "require_both_ret_and_dd": True,
            "live_promote_allowed": False,
            "sparse_is": "inconclusive_not_promote",
        },
        "outcome": {
            "class": "unstable_or_no_edge",
            "primary_pass": False,
            "plain_english": "Long-tape WF fail; drop — no standard opt.",
            "at": NOW,
            "retrofit": True,
        },
        "follow_on": {"mode": "none", "detail": "No combo-fish reopen without Brad one-door.", "at": NOW},
        "cr": "REJECT",
    },
}

# Planned roadmap upgrades — REAL future tests, stay planned
PLANNED_UPGRADE: Dict[str, Dict[str, Any]] = {
    "PLAN-BEAR-PARK-001": {
        "design": {
            "hypothesis": "Strict park minimizes loss vs any tactical bear deploy on real bears",
            "non_goals": [
                "No live regime_cash_policy write without Brad + gates",
                "No bull/flat knob fishing under bear label",
            ],
            "arms": ["USDC_full_park", "tactical_small_deploy", "live_bear_fingerprint"],
            "baseline": "live_bear_or_tactical_default",
            "data": "Coinbase public OHLCV + scorecard bear windows",
            "primary_window": "bear_historical_slices",
            "context_windows": ["last_bear_episode", "long_tape_bear_mask"],
            "runner": "phase6/research/run_regime_bear_park_test.py",
            "regimen": "docs/testing/TEST_REGIMEN_E2E.md",
        },
        "success_criteria": {
            "primary_window": "bear_historical_slices",
            "min_n_trades": 15,
            "must_beat_baseline_ret_pp": 0.0,
            "must_beat_baseline_dd_pp": 0.0,
            "require_both_ret_and_dd": True,
            "usdc_hurdle": True,
            "sparse_is": "inconclusive_not_promote",
            "live_promote_allowed": False,
            "shadow_ok_if": "primary_pass_and_n_ok",
            "cr_accept_only_if": "park beats tactical on maxDD and terminal on primary; N>=15",
        },
        "protocol_template": "docs/testing/trials/PLAN-BEAR-PARK-001_PROTOCOL.md",
        "emit_gate_note": "Prefer when live regime=bear OR offline bear slices available; not a placeholder — full offline dig.",
        "regimen_ready": True,
    },
    "PLAN-METHOD-ROTATION-001": {
        "design": {
            "hypothesis": "Scorecard rotation winner still beats production path on fresh window",
            "non_goals": [
                "No auto-apply OPT winner to live",
                "No fishing new packs without stale scorecard trigger",
            ],
            "arms": ["defensive_rotation_21d", "production_path", "control_no_swap"],
            "baseline": "production_path",
            "data": "ANALYST-OPT scenario pack + compare-production",
            "primary_window": "fresh_opt_window",
            "context_windows": ["prior_scorecard"],
            "runner": "phase6/research (analyst_opt_scenario_pack / compare-production)",
            "opt_hook": "analyst_opt_scenario_pack",
            "regimen": "docs/testing/TEST_REGIMEN_E2E.md",
        },
        "success_criteria": {
            "primary_window": "fresh_opt_window",
            "min_n_trades": 15,
            "must_beat_baseline_ret_pp": 0.0,
            "must_beat_baseline_dd_pp": 0.0,
            "require_both_ret_and_dd": True,
            "sparse_is": "inconclusive_not_promote",
            "live_promote_allowed": False,
            "shadow_ok_if": "primary_pass_and_n_ok",
            "cr_accept_only_if": "leaderboard delta + compare-production pass honesty classes; not bags-only",
        },
        "protocol_template": "docs/testing/trials/PLAN-METHOD-ROTATION-001_PROTOCOL.md",
        "emit_gate_note": "Emit when scorecard stale or capacity free after higher prio; real OPT pack test.",
        "regimen_ready": True,
    },
    "PLAN-BULL-KNOBS-002": {
        "design": {
            "hypothesis": "Bull live knobs under-deploy or over-trade vs scorecard winner",
            "non_goals": [
                "No live util loosen without Brad + gates",
                "No run while regime≠bull (emit_only_when_regime=bull)",
                "Not a placeholder for 001 — 001 was zombie process abort; 002 is the real test",
            ],
            "arms": ["live_bull_fingerprint", "scorecard_bull_winner", "USDC_hurdle"],
            "baseline": "live_bull_fingerprint",
            "data": "bull OHLCV windows + scorecard",
            "primary_window": "bull_windows",
            "context_windows": ["btc_30d_ge_15"],
            "runner": "phase6/research/run_regime_bull_knobs_test.py",
            "predecessor": "PLAN-BULL-KNOBS-001 abort zombie",
            "regimen": "docs/testing/TEST_REGIMEN_E2E.md",
        },
        "success_criteria": {
            "primary_window": "bull_windows",
            "min_n_trades": 15,
            "must_beat_baseline_ret_pp": 0.0,
            "must_beat_baseline_dd_pp": 0.0,
            "require_both_ret_and_dd": True,
            "usdc_hurdle": True,
            "sparse_is": "inconclusive_not_promote",
            "live_promote_allowed": False,
            "shadow_ok_if": "primary_pass_and_n_ok",
            "cr_accept_only_if": "beats live bull + USDC on primary; DD bound; N>=15",
        },
        "protocol_template": "docs/testing/trials/PLAN-BULL-KNOBS-002_PROTOCOL.md",
        "emit_only_when_regime": "bull",
        "emit_gate_note": "REAL re-test of bull knobs; parked until detector bull / BTC 30d ≥ +15%.",
        "regimen_ready": True,
    },
}


def write_packet(t: Dict[str, Any], patch: Dict[str, Any]) -> Path:
    tid = t["trial_id"]
    dec_raw = t.get("decision")
    dec: Dict[str, Any] = dict(dec_raw) if isinstance(dec_raw, dict) else {}
    decision = str(dec.get("value") or "unknown")
    note = str(dec.get("note") or patch.get("outcome", {}).get("plain_english") or "")
    fo_raw = patch.get("follow_on") or {}
    fo: Dict[str, Any] = dict(fo_raw) if isinstance(fo_raw, dict) else {}
    # Ensure decision dict has regimen fields without changing value
    dec.setdefault("cr", patch.get("cr") or tc._cr_label(decision))
    dec.setdefault("follow_on", fo.get("mode", "none"))
    dec.setdefault("follow_on_detail", fo.get("detail", ""))
    t["decision"] = dec
    t["follow_on"] = fo
    t["success_criteria"] = patch["success_criteria"]
    t["design"] = patch["design"]
    t["outcome"] = patch["outcome"]
    if not t.get("protocol"):
        cand = PROTO / f"{tid}_PROTOCOL.md"
        if cand.exists():
            t["protocol"] = str(cand.relative_to(ROOT))
    path = tc.write_decision_packet(
        t,
        decision=decision,
        note=f"[regimen retrofit {DAY}] {note}",
        decided_by=str(dec.get("by") or "brad"),
        follow_on=str(fo.get("mode") or "none"),
        follow_on_detail=str(fo.get("detail") or ""),
    )
    # annotate packet
    extra = (
        f"\n## Regimen retrofit\n"
        f"- Applied {DAY} under `docs/testing/TEST_REGIMEN_E2E.md`\n"
        f"- Decision enum **unchanged** (`{decision}`)\n"
        f"- Fields backfilled: success_criteria, outcome, follow_on, packet\n"
    )
    if patch.get("successor_is_real_test"):
        extra += f"- Successor real test: `{patch['successor_is_real_test']}` (not closed as placeholder)\n"
    path.write_text(path.read_text() + extra)
    t["decision_packet"] = str(path.relative_to(ROOT))
    t["regimen_retrofit_at"] = NOW
    return path


def protocol_md(plan_id: str, u: Dict[str, Any], plan: Dict[str, Any]) -> str:
    d = u["design"]
    sc = u["success_criteria"]
    return f"""# Protocol — {plan_id}

**Status:** PLANNED (regimen-ready design; not launched)  
**Master task:** _(emit creates MASTER)_  
**Kind:** `{plan.get('trial_kind')}`  
**Family:** `{plan.get('family')}`  
**Regimen:** `docs/testing/TEST_REGIMEN_E2E.md`

## 1. Hypothesis
{d.get('hypothesis')}

## 2. Non-goals
{chr(10).join('- ' + x for x in d.get('non_goals') or [])}

## 3. Design
| Item | Value |
|------|--------|
| Control / baseline | {d.get('baseline')} |
| Arms | {', '.join(d.get('arms') or [])} |
| Data | {d.get('data')} |
| Primary window | **{d.get('primary_window')}** |
| Context windows | {', '.join(d.get('context_windows') or [])} |
| Runner | `{d.get('runner')}` |

## 4. Success criteria (frozen before run)
| Gate | Value |
|------|--------|
| primary_window | {sc.get('primary_window')} |
| min_n_trades | {sc.get('min_n_trades')} |
| beat baseline ret+dd | {sc.get('require_both_ret_and_dd')} |
| usdc_hurdle | {sc.get('usdc_hurdle', False)} |
| sparse_is | {sc.get('sparse_is')} |
| live_promote_allowed | {sc.get('live_promote_allowed')} |
| CR accept only if | {sc.get('cr_accept_only_if')} |

## 5. Outcome classes
`HIT_CRITERIA` | `EDGE_VS_BAGS_ONLY` | `inconclusive_sparse_N` | `unstable_or_no_edge` | `process_incomplete`

## 6. Decision path
1. Emit → MASTER Type:test → pickup → runner  
2. `finalize-report` with outcome block  
3. `review-request` → Brad `decide` + `--follow-on`  
4. Packet under `docs/testing/decisions/`

## 7. Emit gates
{u.get('emit_gate_note')}  
`emit_only_when_regime`: {u.get('emit_only_when_regime') or plan.get('emit_only_when_regime') or '—'}

## 8. Placeholder policy
This is a **real** future test design, not a stub to close. Do **not** `decide drop/abort` until a run produces outcome evidence (or genuine process zombie after launch).
"""


def main() -> int:
    # --- retrofit closed ---
    for tid, patch in CLOSED_PATCH.items():
        try:
            t = tc.load_trial(tid)
        except FileNotFoundError:
            print("MISSING", tid)
            continue
        if t.get("status") != "CLOSED":
            print("SKIP non-closed", tid, t.get("status"))
            continue
        # Don't clobber FIB/SR style complete packets if already regimen-ok
        if t.get("decision_packet") and t.get("outcome") and t.get("success_criteria"):
            print("ALREADY_OK", tid)
            continue
        path = write_packet(t, patch)
        tc.save_trial(t)
        print("RETROFIT", tid, "->", path.relative_to(ROOT))

    # FIB/SR already ok — mark note
    for tid in (
        "TEST-FIB-DISCOUNT-ENTRY-SHADOW-20260815",
        "TEST-SR-STRUCTURE-ENTRY-SHADOW-20260815",
    ):
        t = tc.load_trial(tid)
        t.setdefault("notes", []).append(
            {
                "at": NOW,
                "text": (
                    "Regimen audit 2026-08-17: NOT a placeholder close. "
                    "Real OHLCV multipair dig + long-tape outcome; CR REJECT drop is evidence-based."
                ),
            }
        )
        tc.save_trial(t)
        print("ANNOTATE_REAL", tid)

    # --- planned upgrades ---
    s_path = TRIALS / "TEST_STRATEGY.json"
    s = json.loads(s_path.read_text())
    for plan in s.get("roadmap", []):
        pid = plan.get("plan_id")
        if pid not in PLANNED_UPGRADE:
            continue
        u = PLANNED_UPGRADE[pid]
        plan["design"] = u["design"]
        plan["success_criteria"] = u["success_criteria"]
        plan["protocol_template"] = u["protocol_template"]
        plan["regimen_ready"] = True
        plan["regimen"] = "docs/testing/TEST_REGIMEN_E2E.md"
        plan["emit_gate_note"] = u.get("emit_gate_note")
        if u.get("emit_only_when_regime"):
            plan["emit_only_when_regime"] = u["emit_only_when_regime"]
        # write protocol
        ppath = ROOT / u["protocol_template"]
        ppath.parent.mkdir(parents=True, exist_ok=True)
        ppath.write_text(protocol_md(pid, u, plan))
        print("PLANNED_READY", pid, "->", u["protocol_template"])

    s.setdefault("notes", []).append(
        f"{DAY}: TEST_REGIMEN_E2E applied to queue — closed trials retrofitted with packets "
        f"(decisions unchanged); planned BEAR/METHOD/BULL-002 got design+success_criteria+protocols "
        f"(stay planned — real tests, not closed as placeholders). FIB/SR confirmed evidence drop not stubs."
    )
    s["updated_at"] = NOW
    s_path.write_text(json.dumps(s, indent=2) + "\n")
    print("STRATEGY_UPDATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
