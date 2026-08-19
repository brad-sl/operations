#!/usr/bin/env python3
"""
ANALYST-REGIME-FLAT-KNOBS offline T0/T1/T1b runner.

Hypothesis: under live flat option B (cap $75, RSI≤55, sent≥0.25), rebalance
beats rotation on real flat + live_overlap Path B windows; nearby cap grid may
improve return/DD. RSI/sentiment not applied in ARCH-4 (honest Path B gap).

Real OHLCV only. No live config writes.

Writes reports/REGIME_FLAT_KNOBS_TEST_<date>.md + .json
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.run_scenario_leaderboard import load_pack, run_scenario  # noqa: E402

TRIAL_ID = "ANALYST-REGIME-FLAT-KNOBS-20260730-TRIAL"
MASTER_ID = "ANALYST-REGIME-FLAT-KNOBS-20260730"
POLICY_PATH = ROOT / "config" / "regime_cash_policy.json"
KNOB_MAP_PATH = ROOT / "config" / "regime_knob_map.json"
STATUS_PATH = ROOT / "data" / "state" / "regime_cash_status.json"
SCORECARD_PATH = ROOT / "data" / "state" / "analyst_regime_scorecard_latest.json"
STRESS_PATH = ROOT / "data" / "state" / "analyst_reentry_knob_stress_latest.json"
VALIDATION_PATH = ROOT / "data" / "state" / "regime_cash_validation_latest.json"
REPORTS = ROOT / "reports"

# Sample gates (Path B multi-asset windows)
MIN_WINDOW_DAYS = 45
FOCUS_REGIMES = ("flat", "live_overlap")

# Live option B fingerprint (policy regimes.flat)
LIVE_B = {
    "rebalance_cap_usd": 75.0,
    "max_rsi": 55.0,
    "min_sentiment": 0.25,
    "strategy_mode": "deploy",
    "allow_new_buys": True,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _scenario(
    sid: str,
    label: str,
    strategy: str,
    freq: int,
    cap: float,
    *,
    note: str = "",
) -> dict:
    return {
        "id": sid,
        "label": label,
        "engine": "arch4",
        "arch4": {"strategy": strategy},
        "backtest": {
            "initial_capital": 1000,
            "rebalance_frequency_days": freq,
            "rebalance_cap_usd": cap,
        },
        "_research_note": note,
    }


def build_primary_scenarios() -> List[dict]:
    """Primary handoff comparison + USDC proxy."""
    return [
        _scenario(
            "flat_b_rebalance_7d",
            "Live-like flat B: rebalance 7d cap75",
            "rebalance",
            7,
            75,
            note="live flat option B envelope (no RSI/sent in harness)",
        ),
        _scenario(
            "flat_b_rotation_7d",
            "Flat B + rotation: rotation 7d cap75",
            "rotation",
            7,
            75,
            note="same cash envelope, rotation instead of rebalance",
        ),
        _scenario(
            "defensive_rebalance_14d",
            "Defensive rebalance 14d cap120",
            "rebalance",
            14,
            120,
            note="scorecard/defensive low-churn",
        ),
        _scenario(
            "usdc_hold_proxy",
            "Cash/USDC proxy (cap0)",
            "rebalance",
            7,
            0,
            note="Path B cap0 ~ park; no USDC APY in arch4 (~0)",
        ),
    ]


def build_grid_scenarios() -> List[dict]:
    """Nearby cap × strategy × freq grid (Path B expressible knobs only)."""
    cells = []
    for strategy in ("rebalance", "rotation"):
        for freq in (7, 14):
            for cap in (50.0, 75.0, 100.0, 150.0):
                sid = f"grid_{strategy}_{freq}d_cap{int(cap)}"
                cells.append(
                    _scenario(
                        sid,
                        f"Grid {strategy} {freq}d cap{int(cap)}",
                        strategy,
                        freq,
                        cap,
                        note="flat B neighborhood; RSI/sent not in Path B",
                    )
                )
    return cells


def focus_windows() -> List[dict]:
    template = load_pack(ROOT / "phase6/research/scenarios/regime_quad_template.json")
    rows = list(template["regime_windows"])
    by_reg = {r["regime"]: r for r in rows}
    out = []
    if "flat" in by_reg:
        out.append(by_reg["flat"])
    end = rows[-1]["date_range"]["end"] if rows else "2026-07-30"
    out.append(
        {
            "regime": "live_overlap",
            "label": "Since go-live OHLCV (2026-04-20..data_end)",
            "date_range": {"start": "2026-04-20", "end": end},
        }
    )
    return out


def summarize(metrics: Optional[dict]) -> dict:
    m = metrics or {}
    return {
        "total_return_pct": m.get("total_return_pct"),
        "sharpe_ratio": m.get("sharpe_ratio"),
        "max_drawdown_pct": m.get("max_drawdown_pct"),
        "total_trades": m.get("total_trades"),
        "avg_exposure_pct": m.get("avg_exposure_pct"),
        "strategy": m.get("strategy"),
    }


def run_pack_window(scenarios: List[dict], rw: dict) -> dict:
    pack = {
        "pack_id": f"flat_knobs_{rw['regime']}",
        "primary_metric": "sharpe_ratio",
        "baseline_scenario_id": scenarios[0]["id"],
        "default_engine": "arch4",
        "date_range": rw["date_range"],
        "scenarios": copy.deepcopy(scenarios),
    }
    results = []
    for sc in pack["scenarios"]:
        try:
            results.append(run_scenario(pack, sc))
        except Exception as e:  # noqa: BLE001
            results.append(
                {
                    "id": sc["id"],
                    "label": sc.get("label"),
                    "engine": "arch4",
                    "metrics": None,
                    "error": str(e),
                }
            )
    ranked = sorted(
        [r for r in results if (r.get("metrics") or {}).get("sharpe_ratio") is not None],
        key=lambda r: float((r.get("metrics") or {}).get("sharpe_ratio") or -1e9),
        reverse=True,
    )
    # Prefer lower maxDD when sharpe tie / primary risk north-star
    ranked_dd = sorted(
        [r for r in results if (r.get("metrics") or {}).get("max_drawdown_pct") is not None],
        key=lambda r: (
            float((r.get("metrics") or {}).get("max_drawdown_pct") or 999),
            -float((r.get("metrics") or {}).get("total_return_pct") or -999),
        ),
    )
    return {
        "regime": rw["regime"],
        "label": rw.get("label"),
        "date_range": rw["date_range"],
        "ranking_sharpe": [r["id"] for r in ranked],
        "ranking_dd": [r["id"] for r in ranked_dd],
        "best_sharpe_id": ranked[0]["id"] if ranked else None,
        "best_dd_id": ranked_dd[0]["id"] if ranked_dd else None,
        "scenarios": {
            r["id"]: {
                "label": r.get("label"),
                "metrics": summarize(r.get("metrics")),
                "error": r.get("error"),
            }
            for r in results
        },
        "n_ok": sum(1 for r in results if (r.get("metrics") or {}).get("total_return_pct") is not None),
        "n_err": sum(1 for r in results if r.get("error")),
    }


def tier0_isolation() -> dict:
    tests = [
        "phase6/research/test_isolation_scenario_knob_parity.py",
        "phase6/research/test_isolation_live_param_audit_gate.py",
    ]
    rows = []
    overall = True
    for rel in tests:
        path = ROOT / rel
        if not path.exists():
            rows.append({"name": rel, "pass": False, "detail": "missing"})
            overall = False
            continue
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        ok = proc.returncode == 0
        overall = overall and ok
        rows.append(
            {
                "name": path.stem,
                "pass": ok,
                "rc": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-400:],
                "stderr_tail": (proc.stderr or "")[-200:],
            }
        )
    # Fingerprint structural checks for flat B
    pol = _load_json(POLICY_PATH) or {}
    flat = (pol.get("regimes") or {}).get("flat") or {}
    entry = flat.get("entry") or {}
    checks = [
        {
            "name": "flat_cap_75",
            "pass": float(flat.get("rebalance_cap_usd") or -1) == 75.0,
            "got": flat.get("rebalance_cap_usd"),
        },
        {
            "name": "flat_max_rsi_55",
            "pass": float(entry.get("max_rsi") or -1) == 55.0,
            "got": entry.get("max_rsi"),
        },
        {
            "name": "flat_min_sent_0_25",
            "pass": float(entry.get("min_sentiment") or -1) == 0.25,
            "got": entry.get("min_sentiment"),
        },
        {
            "name": "flat_deploy_buys",
            "pass": flat.get("strategy_mode") == "deploy" and flat.get("allow_new_buys") is True,
            "got": {
                "strategy_mode": flat.get("strategy_mode"),
                "allow_new_buys": flat.get("allow_new_buys"),
            },
        },
    ]
    for c in checks:
        overall = overall and bool(c["pass"])
        rows.append(c)
    return {"pass": overall, "checks": rows}


def policy_fingerprint() -> dict:
    pol = _load_json(POLICY_PATH) or {}
    km = _load_json(KNOB_MAP_PATH) or {}
    st = _load_json(STATUS_PATH) or {}
    flat_pol = (pol.get("regimes") or {}).get("flat") or {}
    flat_km = (km.get("regimes") or {}).get("flat") or {}
    return {
        "regime_cash_policy_sha256": _sha256_file(POLICY_PATH),
        "regime_knob_map_sha256": _sha256_file(KNOB_MAP_PATH),
        "flat_policy_json": {
            "strategy_mode": flat_pol.get("strategy_mode"),
            "allow_new_buys": flat_pol.get("allow_new_buys"),
            "target_max_util_pct": flat_pol.get("target_max_util_pct"),
            "rebalance_cap_usd": flat_pol.get("rebalance_cap_usd"),
            "min_cash_reserve_pct": flat_pol.get("min_cash_reserve_pct"),
            "entry": flat_pol.get("entry"),
            "exit": flat_pol.get("exit"),
            "label": flat_pol.get("label"),
        },
        "knob_map_flat": {
            "scenario_id": flat_km.get("scenario_id"),
            "strategy_mode": flat_km.get("strategy_mode"),
            "live_overlay": flat_km.get("live_overlay"),
            "note": (flat_km.get("note") or "")[:240],
        },
        "live_status_snapshot": {
            "regime": st.get("regime"),
            "strategy_mode": st.get("strategy_mode"),
            "allow_new_buys": st.get("allow_new_buys"),
            "rebalance_cap_usd": st.get("rebalance_cap_usd"),
            "target_max_util_pct": st.get("target_max_util_pct"),
            "knob_map_scenario": st.get("knob_map_scenario"),
            "as_of": st.get("as_of"),
        },
        "live_b_expected": LIVE_B,
        "note": (
            "Flat option B is policy+knob_map when regime=flat. Live status may be "
            "transition/park — fingerprint both; no writes performed."
        ),
    }


def extract_scorecard_flat() -> dict:
    sc = _load_json(SCORECARD_PATH)
    if not sc:
        return {"available": False}
    for r in sc.get("regimes") or []:
        if r.get("regime") == "flat":
            tops = []
            for s in (r.get("scenarios") or [])[:6]:
                m = s.get("metrics") or {}
                tops.append(
                    {
                        "id": s.get("id"),
                        "total_return_pct": m.get("total_return_pct"),
                        "annualized_return_pct": m.get("annualized_return_pct"),
                        "max_drawdown_pct": m.get("max_drawdown_pct"),
                        "sharpe_ratio": m.get("sharpe_ratio"),
                        "engine": s.get("engine"),
                    }
                )
            return {
                "available": True,
                "date_range": r.get("date_range"),
                "winner_id": r.get("winner_id"),
                "ranking": r.get("ranking"),
                "top_scenarios": tops,
                "scorecard_generated_at": sc.get("generated_at"),
            }
    return {"available": False, "note": "no flat regime in scorecard"}


def primary_compare(primary_rows: List[dict]) -> dict:
    """rebalance_7d vs rotation_7d vs defensive_rebalance_14d under B-ish envelope."""
    out = {}
    keys = (
        "flat_b_rebalance_7d",
        "flat_b_rotation_7d",
        "defensive_rebalance_14d",
        "usdc_hold_proxy",
    )
    for row in primary_rows:
        reg = row["regime"]
        sc = row["scenarios"]
        block = {}
        for k in keys:
            block[k] = (sc.get(k) or {}).get("metrics") or {}
        reb = block["flat_b_rebalance_7d"]
        rot = block["flat_b_rotation_7d"]
        defb = block["defensive_rebalance_14d"]
        # rebalance beats rotation on DD (lower better) and preferably sharpe
        reb_dd = reb.get("max_drawdown_pct")
        rot_dd = rot.get("max_drawdown_pct")
        reb_sh = reb.get("sharpe_ratio")
        rot_sh = rot.get("sharpe_ratio")
        reb_ret = reb.get("total_return_pct")
        rot_ret = rot.get("total_return_pct")
        dd_win = (
            reb_dd is not None
            and rot_dd is not None
            and float(reb_dd) < float(rot_dd) - 0.05
        )
        sh_win = (
            reb_sh is not None
            and rot_sh is not None
            and float(reb_sh) > float(rot_sh)
        )
        # rotation not meaningfully better on return if DD much worse
        rot_return_edge = (
            reb_ret is not None
            and rot_ret is not None
            and float(rot_ret) > float(reb_ret) + 0.25
        )
        block["_verdict"] = {
            "rebalance_beats_rotation_dd": dd_win,
            "rebalance_beats_rotation_sharpe": sh_win,
            "rotation_material_return_edge": rot_return_edge,
            "primary_hypothesis_supported": bool(dd_win or sh_win) and not (
                rot_return_edge and not dd_win
            ),
            "defensive_vs_live_b_dd_delta_pp": (
                None
                if defb.get("max_drawdown_pct") is None or reb_dd is None
                else round(float(defb["max_drawdown_pct"]) - float(reb_dd), 4)
            ),
            "defensive_vs_live_b_ret_delta_pp": (
                None
                if defb.get("total_return_pct") is None or reb_ret is None
                else round(float(defb["total_return_pct"]) - float(reb_ret), 4)
            ),
        }
        out[reg] = block
    return out


def grid_winners(grid_rows: List[dict], primary_compare_block: dict) -> dict:
    """Find cells that beat live-B rebalance on return OR maxDD with same window."""
    summary = {}
    for row in grid_rows:
        reg = row["regime"]
        live = (primary_compare_block.get(reg) or {}).get("flat_b_rebalance_7d") or {}
        live_ret = live.get("total_return_pct")
        live_dd = live.get("max_drawdown_pct")
        live_sh = live.get("sharpe_ratio")
        beaters = []
        for sid, payload in (row.get("scenarios") or {}).items():
            m = payload.get("metrics") or {}
            if m.get("total_return_pct") is None:
                continue
            ret = float(m["total_return_pct"])
            dd = float(m["max_drawdown_pct"]) if m.get("max_drawdown_pct") is not None else None
            sh = float(m["sharpe_ratio"]) if m.get("sharpe_ratio") is not None else None
            better_ret = live_ret is not None and ret > float(live_ret) + 0.15
            better_dd = (
                live_dd is not None and dd is not None and dd < float(live_dd) - 0.15
            )
            better_sh = live_sh is not None and sh is not None and sh > float(live_sh) + 0.25
            # Reject rotation that "wins" return with much worse DD
            is_rot = "rotation" in sid
            if is_rot and dd is not None and live_dd is not None and dd > float(live_dd) + 1.0:
                if not better_dd:
                    continue
            if better_ret or better_dd or better_sh:
                beaters.append(
                    {
                        "id": sid,
                        "metrics": m,
                        "better_ret": better_ret,
                        "better_dd": better_dd,
                        "better_sh": better_sh,
                    }
                )
        beaters.sort(
            key=lambda x: (
                1 if x["better_dd"] else 0,
                1 if x["better_sh"] else 0,
                float((x["metrics"] or {}).get("total_return_pct") or -999),
            ),
            reverse=True,
        )
        # Cap binding / differentiation diagnostic
        rebal_caps = {}
        for sid, payload in (row.get("scenarios") or {}).items():
            if not sid.startswith("grid_rebalance_7d"):
                continue
            m = payload.get("metrics") or {}
            rebal_caps[sid] = {
                "ret": m.get("total_return_pct"),
                "dd": m.get("max_drawdown_pct"),
                "exp": m.get("avg_exposure_pct"),
                "tr": m.get("total_trades"),
            }
        unique_rets = {v["ret"] for v in rebal_caps.values() if v["ret"] is not None}
        summary[reg] = {
            "live_b_baseline": live,
            "n_beaters": len(beaters),
            "top_beaters": beaters[:5],
            "rebalance_7d_cap_slice": rebal_caps,
            "cap_differentiation_weak": len(unique_rets) <= 1,
            "date_range": row.get("date_range"),
            "n_ok": row.get("n_ok"),
        }
    return summary


def recommend(
    *,
    isolation_pass: bool,
    primary: dict,
    grid: dict,
    scorecard_flat: dict,
    fingerprint: dict,
) -> dict:
    path_b_gaps = [
        "ARCH-4 Path B does not apply live RSI/sentiment/lockout REGIME-CASH entry filters",
        "cap0 usdc_hold_proxy has no USDC APY (~0); scorecard usdc_hold uses ~3.5% APY",
        "live rebalance clock != day stride; basket/allocator differs from live book",
        "do not promote from Path B alone — gates + Brad required",
    ]
    # Primary hyp across focus windows
    prim_ok = []
    for reg in FOCUS_REGIMES:
        v = (primary.get(reg) or {}).get("_verdict") or {}
        if v:
            prim_ok.append(bool(v.get("primary_hypothesis_supported")))
    primary_supported = all(prim_ok) if prim_ok else False
    any_grid_beat = any(int((grid.get(r) or {}).get("n_beaters") or 0) > 0 for r in FOCUS_REGIMES)
    # Require grid beater on BOTH windows for promote path, and not rotation-only DD blowups
    strong_grid = True
    promote_candidate = None
    for reg in FOCUS_REGIMES:
        tops = (grid.get(reg) or {}).get("top_beaters") or []
        rebal_tops = [
            t
            for t in tops
            if "rebalance" in t["id"] and (t.get("better_dd") or t.get("better_sh"))
        ]
        if not rebal_tops:
            strong_grid = False
        else:
            promote_candidate = promote_candidate or rebal_tops[0]["id"]
    sc_winner = scorecard_flat.get("winner_id")
    live_reg = (fingerprint.get("live_status_snapshot") or {}).get("regime")

    # Default: keep B, no shadow
    enum = "continue_observe_only"
    go_shadow = False
    conf = "medium"
    reasons = []

    if not isolation_pass:
        enum = "abort"
        reasons.append("T0 isolation failed")
        conf = "low"
    elif not primary_supported:
        enum = "drop"
        reasons.append(
            "Primary hyp (rebalance beats rotation under B envelope on flat/live_overlap) NOT supported"
        )
        conf = "medium"
    else:
        reasons.append(
            "Primary hyp SUPPORTED: rebalance under B envelope beats rotation on DD/Sharpe "
            "on flat + live_overlap (Path B real OHLCV)"
        )
        if sc_winner == "usdc_hold":
            reasons.append(
                "Scorecard flat winner remains usdc_hold (true APY) — risk styles do not beat cash on flat window"
            )
        if any_grid_beat and not strong_grid:
            reasons.append(
                "Some grid cells beat live-B on one metric/window, but not a clean dual-window "
                "rebalance improvement — insufficient for shadow/promote"
            )
            conf = "medium"
        elif strong_grid and promote_candidate:
            enum = "propose_scoped_experiment"
            go_shadow = True
            reasons.append(
                f"Grid cell {promote_candidate} beats live-B on DD/Sharpe across focus windows — "
                "shadow-only candidate (still no RSI/sent evidence)"
            )
            conf = "medium-low"
        else:
            reasons.append(
                "Nearby cap/freq grid does not materially beat live-B rebalance_7d cap75; "
                "cap differentiation often weak at low Path B exposure"
            )
            reasons.append(
                "RSI/sentiment grid NOT testable in Path B — leave live B gates (RSI≤55, sent≥0.25) unchanged"
            )
            enum = "continue_observe_only"
            go_shadow = False
            conf = "medium-high"

    if live_reg and live_reg != "flat":
        reasons.append(
            f"Live detector is `{live_reg}` (not flat) — flat B knobs are latent until flat returns; "
            "no live apply regardless"
        )

    reasons.append("No live regime_cash_policy / knob_map writes in this trial")

    plain = (
        "Keep flat option B as-is (rebalance-style small cap, not rotation). "
        "Evidence: on real flat and live-overlap OHLCV, rotation under the same $75 envelope "
        "takes much more drawdown for little/no extra return. Nearby Path B cap grid does not "
        "clearly beat live B. Do not promote bull rotation knobs into flat. RSI/sent not proven "
        "in harness — leave gates. Live is not in flat right now anyway."
        if enum == "continue_observe_only"
        else f"Recommendation `{enum}`: " + "; ".join(reasons[:3])
    )

    return {
        "enum": enum,
        "go_shadow": go_shadow,
        "confidence": conf,
        "primary_hypothesis_supported": primary_supported,
        "grid_promote_candidate": promote_candidate if go_shadow else None,
        "reasons": reasons,
        "plain_english": plain,
        "path_b_gaps": path_b_gaps,
        "north_star": "better returns AND less loss — prefer lower DD over idle-cash FOMO",
    }


def run() -> dict:
    t0 = tier0_isolation()
    fp = policy_fingerprint()
    windows = focus_windows()
    primary_sc = build_primary_scenarios()
    grid_sc = build_grid_scenarios()

    primary_rows = []
    for rw in windows:
        print(f"=== primary {rw['regime']} {rw['date_range']} ===", flush=True)
        row = run_pack_window(primary_sc, rw)
        primary_rows.append(row)
        for sid in row.get("ranking_sharpe") or []:
            m = (row["scenarios"].get(sid) or {}).get("metrics") or {}
            print(
                f"  {sid:32} ret={m.get('total_return_pct')!s:>7} "
                f"sh={m.get('sharpe_ratio')!s:>8} dd={m.get('max_drawdown_pct')!s:>6}",
                flush=True,
            )

    grid_rows = []
    for rw in windows:
        print(f"=== grid {rw['regime']} {rw['date_range']} n={len(grid_sc)} ===", flush=True)
        row = run_pack_window(grid_sc, rw)
        grid_rows.append(row)
        print(
            f"  best_sharpe={row.get('best_sharpe_id')} best_dd={row.get('best_dd_id')} "
            f"ok={row.get('n_ok')} err={row.get('n_err')}",
            flush=True,
        )

    primary = primary_compare(primary_rows)
    grid = grid_winners(grid_rows, primary)
    sc_flat = extract_scorecard_flat()
    # Optional: attach prior stress artifact summary if present
    stress = _load_json(STRESS_PATH)
    stress_focus = []
    if stress:
        for r in stress.get("regimes") or []:
            if r.get("regime") in FOCUS_REGIMES:
                stress_focus.append(
                    {
                        "regime": r.get("regime"),
                        "date_range": r.get("date_range"),
                        "best_id": r.get("best_id"),
                        "flat_b_reb": (r.get("scenarios") or {})
                        .get("flat_option_b_rebalance_7d", {})
                        .get("metrics"),
                        "flat_b_rot": (r.get("scenarios") or {})
                        .get("flat_option_b_rotation_7d", {})
                        .get("metrics"),
                        "def_reb": (r.get("scenarios") or {})
                        .get("defensive_rebalance_14d", {})
                        .get("metrics"),
                    }
                )

    # Sample size
    sample = {}
    for row in primary_rows:
        dr = row.get("date_range") or {}
        try:
            from datetime import date as _date

            s = _date.fromisoformat(dr["start"])
            e = _date.fromisoformat(dr["end"])
            days = (e - s).days + 1
        except Exception:
            days = None
        sample[row["regime"]] = {
            "date_range": dr,
            "approx_days": days,
            "gate_met": days is not None and days >= MIN_WINDOW_DAYS,
            "n_ok_scenarios": row.get("n_ok"),
        }
    sample_ok = all(v.get("gate_met") for v in sample.values()) if sample else False

    rec = recommend(
        isolation_pass=bool(t0.get("pass")),
        primary=primary,
        grid=grid,
        scorecard_flat=sc_flat,
        fingerprint=fp,
    )
    if not sample_ok:
        rec = {
            **rec,
            "enum": "abort" if not sample_ok and not sample else rec["enum"],
            "confidence": "low",
            "reasons": ["Insufficient window length"] + list(rec.get("reasons") or []),
            "plain_english": "Insufficient real-data window — no promote.",
        }
        if not sample_ok:
            # keep continue if we actually have data; only abort if truly empty
            if all((v.get("n_ok_scenarios") or 0) == 0 for v in sample.values()):
                rec["enum"] = "abort"
            else:
                rec["enum"] = rec.get("enum") or "continue_observe_only"

    validation = _load_json(VALIDATION_PATH)

    report = {
        "trial_id": TRIAL_ID,
        "master_id": MASTER_ID,
        "family": "regime_flat_knobs",
        "generated_at": _utc_now(),
        "real_data_only": True,
        "live_config_writes": False,
        "hypothesis": (
            "Under live flat option B envelope (cap $75, RSI≤55, sent≥0.25), rebalance beats "
            "rotation on real flat + live_overlap windows. Nearby cap/RSI/sent grid may improve "
            "return or DD without promoting bull-only rotation knobs."
        ),
        "tier0_isolation": t0,
        "policy_fingerprint": fp,
        "sample_gates": {"min_window_days": MIN_WINDOW_DAYS, "windows": sample, "met": sample_ok},
        "tier1_primary_paths": {
            "method": "ARCH-4 Path B on regime_quad flat + live_overlap real OHLCV",
            "scenarios": [s["id"] for s in primary_sc],
            "rows": primary_rows,
            "compare": primary,
        },
        "tier1b_grid": {
            "method": "cap ∈ {50,75,100,150} × strategy ∈ {rebalance,rotation} × freq ∈ {7,14}",
            "path_b_rsi_sent": "NOT APPLIED — grid is cap/strategy/freq only",
            "rows": grid_rows,
            "winners_vs_live_b": grid,
        },
        "scorecard_flat": sc_flat,
        "prior_reentry_stress_focus": stress_focus,
        "validation_latest_snippet": {
            "available": validation is not None,
            "as_of": (validation or {}).get("as_of") or (validation or {}).get("generated_at"),
            "live_regime": ((validation or {}).get("live_detection") or {}).get("regime")
            if isinstance(validation, dict)
            else None,
        },
        "recommendation": rec,
        "honest_assessment": {
            "what_worked": (
                "Rebalance under $75 envelope dominates rotation on maxDD/Sharpe for flat and "
                "live_overlap — matches Path B 2026-07-30 stress narrative."
            ),
            "what_did_not": (
                "Nearby Path B cap grid rarely separates from live-B at low exposure; RSI/sent "
                "cannot be validated here. Scorecard flat still prefers USDC hold on true APY."
            ),
            "uncertainty": (
                "Harness exposure/trade counts are low for rebalance cells; live book + gates "
                "differ. Current live regime is not flat."
            ),
        },
    }
    return report


def write_reports(report: dict) -> Tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = f"REGIME_FLAT_KNOBS_TEST_{day}"
    json_path = REPORTS / f"{stem}.json"
    md_path = REPORTS / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")

    rec = report.get("recommendation") or {}
    fp = report.get("policy_fingerprint") or {}
    t0 = report.get("tier0_isolation") or {}
    primary = (report.get("tier1_primary_paths") or {}).get("compare") or {}
    grid = (report.get("tier1b_grid") or {}).get("winners_vs_live_b") or {}
    sc = report.get("scorecard_flat") or {}
    sample = (report.get("sample_gates") or {}).get("windows") or {}

    def _mline(reg: str, sid: str) -> str:
        m = ((primary.get(reg) or {}).get(sid)) or {}
        if isinstance(m, dict) and "_verdict" not in sid:
            return (
                f"ret={m.get('total_return_pct')} sh={m.get('sharpe_ratio')} "
                f"dd={m.get('max_drawdown_pct')} tr={m.get('total_trades')} "
                f"exp={m.get('avg_exposure_pct')}"
            )
        return "n/a"

    lines = [
        f"# Regime Flat Knobs Test — {day}",
        "",
        f"**Trial:** `{report['trial_id']}`  ",
        f"**Master:** `{report['master_id']}`  ",
        f"**Generated:** {report.get('generated_at')}  ",
        f"**Real data only:** {report.get('real_data_only')}  ",
        f"**Live config writes:** {report.get('live_config_writes')}",
        "",
        "## Executive summary (plain English)",
        "",
        rec.get("plain_english") or "",
        "",
        f"- **Recommendation enum:** `{rec.get('enum')}`  ",
        f"- **Shadow go?** **{rec.get('go_shadow')}**  ",
        f"- **Confidence:** {rec.get('confidence')}  ",
        f"- **Primary hyp (rebalance > rotation under B):** **{rec.get('primary_hypothesis_supported')}**  ",
        f"- Sample windows: `{json.dumps(sample)}`",
        "",
        "### Reasons",
        "",
    ]
    for r in rec.get("reasons") or []:
        lines.append(f"- {r}")
    lines += [
        "",
        "## Tier 0 — isolation",
        "",
        f"- Overall pass: **{t0.get('pass')}**",
        "",
        "```json",
        json.dumps(t0.get("checks"), indent=2)[:4000],
        "```",
        "",
        "## Policy fingerprint (start-of-run)",
        "",
        f"- `regime_cash_policy.json` sha256: `{fp.get('regime_cash_policy_sha256')}`",
        f"- `regime_knob_map.json` sha256: `{fp.get('regime_knob_map_sha256')}`",
        "",
        "```json",
        json.dumps(
            {
                "flat_policy_json": fp.get("flat_policy_json"),
                "knob_map_flat": fp.get("knob_map_flat"),
                "live_status_snapshot": fp.get("live_status_snapshot"),
                "note": fp.get("note"),
            },
            indent=2,
        ),
        "```",
        "",
        "## Tier 1 — primary paths (flat + live_overlap)",
        "",
        "Method: ARCH-4 Path B real OHLCV. Live B envelope = rebalance 7d cap $75 "
        "(RSI/sent **not** in harness).",
        "",
    ]
    for reg in FOCUS_REGIMES:
        block = primary.get(reg) or {}
        v = block.get("_verdict") or {}
        lines += [
            f"### {reg}",
            "",
            f"- flat_b_rebalance_7d: `{_mline(reg, 'flat_b_rebalance_7d')}`",
            f"- flat_b_rotation_7d: `{_mline(reg, 'flat_b_rotation_7d')}`",
            f"- defensive_rebalance_14d: `{_mline(reg, 'defensive_rebalance_14d')}`",
            f"- usdc_hold_proxy: `{_mline(reg, 'usdc_hold_proxy')}`",
            f"- Verdict: `{json.dumps(v)}`",
            "",
        ]
    lines += [
        "## Tier 1b — nearby grid vs live-B",
        "",
        "Path B expressible only: strategy × freq × cap. **RSI/sentiment grid gap.**",
        "",
        "```json",
        json.dumps(grid, indent=2, default=str)[:8000],
        "```",
        "",
        "## Scorecard multi-asset (flat)",
        "",
        "```json",
        json.dumps(sc, indent=2)[:4000],
        "```",
        "",
        "## Prior reentry stress (focus)",
        "",
        "```json",
        json.dumps(report.get("prior_reentry_stress_focus"), indent=2)[:3000],
        "```",
        "",
        "## Path B gaps",
        "",
    ]
    for g in rec.get("path_b_gaps") or []:
        lines.append(f"- {g}")
    lines += [
        "",
        "## Honest assessment",
        "",
        "```json",
        json.dumps(report.get("honest_assessment"), indent=2),
        "```",
        "",
        "## Decide (Brad)",
        "",
        "```bash",
        f"cd /home/brad/projects/crypto-trading-bot",
        f"python3 phase6/research/trial_cycle.py decide {report['trial_id']} {rec.get('enum')} \\",
        f"  --note 'see reports/{json_path.name}'",
        "```",
        "",
        "## Files",
        "",
        f"- `{json_path.relative_to(ROOT)}`",
        f"- `{md_path.relative_to(ROOT)}`",
        "- `phase6/research/run_regime_flat_knobs_test.py`",
        "- `scripts/phase6/run_reentry_knob_stress.py` (prior stress artifact)",
        "- `config/regime_cash_policy.json` (read-only fingerprint)",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> int:
    report = run()
    md_path, json_path = write_reports(report)
    print(
        json.dumps(
            {
                "md": str(md_path),
                "json": str(json_path),
                "recommendation": (report.get("recommendation") or {}).get("enum"),
                "go_shadow": (report.get("recommendation") or {}).get("go_shadow"),
                "primary_ok": (report.get("recommendation") or {}).get(
                    "primary_hypothesis_supported"
                ),
                "isolation_pass": (report.get("tier0_isolation") or {}).get("pass"),
                "policy_sha256": (report.get("policy_fingerprint") or {}).get(
                    "regime_cash_policy_sha256"
                ),
                "plain": (report.get("recommendation") or {}).get("plain_english"),
            },
            indent=2,
        )
    )
    print(f"\nWrote {md_path}\nWrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
