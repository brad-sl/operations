#!/usr/bin/env python3
"""Compare OPT winner + live-like re-entry knobs across regime windows.

Not a promotion gate. Honest research: which deploy styles make money
on bull/flat/recent/live-overlap without assuming RSI/sentiment (Path B gap).
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase6.research.run_scenario_leaderboard import load_pack, run_scenario  # noqa: E402

OUT = ROOT / "data/state/analyst_reentry_knob_stress_latest.json"
WINNER_OUT = ROOT / "data/state/analyst_winner_regime_stress_latest.json"


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


def build_scenarios() -> list[dict]:
    """Knobs expressible in ARCH-4 Path B (freq/cap/rotation|rebalance only)."""
    return [
        _scenario(
            "baseline_7d",
            "Baseline rotation weekly cap200",
            "rotation",
            7,
            200,
            note="pack baseline",
        ),
        _scenario(
            "bear_window_rotation_14d",
            "OPT winner: rotation 14d cap100",
            "rotation",
            14,
            100,
            note="OPT-20260726 winner knobs",
        ),
        _scenario(
            "defensive_rotation_21d",
            "Scorecard bull winner: rotation 21d cap100",
            "rotation",
            21,
            100,
            note="knob_map bull",
        ),
        _scenario(
            "defensive_rebalance_14d",
            "Defensive rebalance 14d cap120",
            "rebalance",
            14,
            120,
            note="low-churn rebalance",
        ),
        _scenario(
            "flat_option_b_rebalance_7d",
            "Live-like flat B: rebalance 7d cap75",
            "rebalance",
            7,
            75,
            note="live flat option B envelope (no RSI/sent in harness)",
        ),
        _scenario(
            "flat_option_b_rotation_7d",
            "Flat B + rotation: rotation 7d cap75",
            "rotation",
            7,
            75,
            note="same cash envelope, rotation instead of rebalance",
        ),
        _scenario(
            "transition_micro_rebalance_7d",
            "Transition micro: rebalance 7d cap50",
            "rebalance",
            7,
            50,
            note="policy transition rebalance_cap_usd=50 (park still blocks buys live)",
        ),
        _scenario(
            "transition_micro_rotation_14d",
            "Transition micro rotation: rotation 14d cap50",
            "rotation",
            14,
            50,
            note="winner stride + half cap",
        ),
        _scenario(
            "lean_rebalance_7d_cap150",
            "Lean rebalance: 7d cap150",
            "rebalance",
            7,
            150,
            note="more deploy without full baseline rotation",
        ),
        _scenario(
            "usdc_hold_proxy",
            "Cash/USDC proxy (no trades)",
            "rebalance",
            7,
            0,
            note="cap0 ~ park; return ~0 in Path B (no APY in arch4)",
        ),
    ]


def windows() -> list[dict]:
    template = load_pack(ROOT / "phase6/research/scenarios/regime_quad_template.json")
    rows = list(template["regime_windows"])
    # Live book / go-live overlap (deposit era)
    rows.append(
        {
            "regime": "live_overlap",
            "label": "Since go-live OHLCV (2026-04-20..data_end)",
            "date_range": {"start": "2026-04-20", "end": rows[-1]["date_range"]["end"]},
        }
    )
    # Very recent 30d-ish for re-entry timing
    end = rows[-1]["date_range"]["end"]
    rows.append(
        {
            "regime": "last_45d",
            "label": "Last ~45d tail",
            "date_range": {"start": "2026-06-15", "end": end},
        }
    )
    return rows


def summarize(metrics: dict | None) -> dict:
    m = metrics or {}
    return {
        "total_return_pct": m.get("total_return_pct"),
        "sharpe_ratio": m.get("sharpe_ratio"),
        "max_drawdown_pct": m.get("max_drawdown_pct"),
        "total_trades": m.get("total_trades"),
        "avg_exposure_pct": m.get("avg_exposure_pct"),
        "strategy": m.get("strategy"),
    }


def main() -> int:
    scenarios = build_scenarios()
    primary = "sharpe_ratio"
    baseline_id = "baseline_7d"
    winner_id = "bear_window_rotation_14d"

    all_regimes = []
    winner_only = []

    for rw in windows():
        pack = {
            "pack_id": f"reentry_stress_{rw['regime']}",
            "primary_metric": primary,
            "baseline_scenario_id": baseline_id,
            "default_engine": "arch4",
            "date_range": rw["date_range"],
            "scenarios": copy.deepcopy(scenarios),
        }
        results = []
        for sc in pack["scenarios"]:
            try:
                results.append(run_scenario(pack, sc))
            except Exception as e:  # noqa: BLE001 — research surface
                results.append(
                    {
                        "id": sc["id"],
                        "label": sc.get("label"),
                        "engine": "arch4",
                        "metrics": None,
                        "error": str(e),
                    }
                )

        by_id = {r["id"]: r for r in results}
        ranked = sorted(
            [r for r in results if (r.get("metrics") or {}).get(primary) is not None],
            key=lambda r: float((r.get("metrics") or {}).get(primary) or -1e9),
            reverse=True,
        )
        ranking = [r["id"] for r in ranked]
        best = ranking[0] if ranking else None

        # positive return candidates with controlled DD
        pos = []
        for r in ranked:
            m = r.get("metrics") or {}
            ret = m.get("total_return_pct")
            dd = m.get("max_drawdown_pct")
            if ret is not None and float(ret) > 0:
                pos.append(
                    {
                        "id": r["id"],
                        "return_pct": ret,
                        "sharpe": m.get("sharpe_ratio"),
                        "max_dd": dd,
                        "trades": m.get("total_trades"),
                        "exposure": m.get("avg_exposure_pct"),
                    }
                )

        row = {
            "regime": rw["regime"],
            "label": rw.get("label"),
            "date_range": rw["date_range"],
            "ranking": ranking,
            "best_id": best,
            "positive_return_scenarios": pos,
            "scenarios": {
                r["id"]: {
                    "label": r.get("label"),
                    "metrics": summarize(r.get("metrics")),
                    "error": r.get("error"),
                }
                for r in results
            },
        }
        all_regimes.append(row)

        # Classic winner-vs-baseline block for drop-in replace of old artifact
        b = by_id.get(baseline_id, {})
        w = by_id.get(winner_id, {})
        bm = b.get("metrics") or {}
        wm = w.get("metrics") or {}
        b_sh, w_sh = bm.get("sharpe_ratio"), wm.get("sharpe_ratio")
        beats = (
            w_sh is not None and b_sh is not None and float(w_sh) > float(b_sh)
        )
        winner_only.append(
            {
                "regime": rw["regime"],
                "label": rw.get("label"),
                "date_range": rw["date_range"],
                "baseline_sharpe": b_sh,
                "winner_sharpe": w_sh,
                "baseline_return_pct": bm.get("total_return_pct"),
                "winner_return_pct": wm.get("total_return_pct"),
                "baseline_max_dd": bm.get("max_drawdown_pct"),
                "winner_max_dd": wm.get("max_drawdown_pct"),
                "winner_beats_baseline_sharpe": beats,
            }
        )

        print(
            f"\n=== {rw['regime']} {rw['date_range']['start']}..{rw['date_range']['end']} "
            f"best={best} ==="
        )
        for r in ranked[:6]:
            m = r.get("metrics") or {}
            print(
                f"  {r['id']:32} ret={m.get('total_return_pct')!s:>7} "
                f"sh={m.get('sharpe_ratio')!s:>8} dd={m.get('max_drawdown_pct')!s:>6} "
                f"tr={m.get('total_trades')} exp={m.get('avg_exposure_pct')}"
            )

    # Cross-window: which styles are positive most often
    ids = [s["id"] for s in scenarios]
    scoreboard = []
    for sid in ids:
        wins = 0
        pos_n = 0
        rets = []
        sharpes = []
        for reg in all_regimes:
            m = (reg["scenarios"].get(sid) or {}).get("metrics") or {}
            ret = m.get("total_return_pct")
            sh = m.get("sharpe_ratio")
            if ret is not None:
                rets.append(float(ret))
                if float(ret) > 0:
                    pos_n += 1
            if sh is not None:
                sharpes.append(float(sh))
            if reg.get("best_id") == sid:
                wins += 1
        scoreboard.append(
            {
                "id": sid,
                "best_count": wins,
                "positive_return_windows": pos_n,
                "windows": len(all_regimes),
                "avg_return_pct": round(sum(rets) / len(rets), 3) if rets else None,
                "avg_sharpe": round(sum(sharpes) / len(sharpes), 3) if sharpes else None,
                "min_return_pct": round(min(rets), 3) if rets else None,
                "max_return_pct": round(max(rets), 3) if rets else None,
            }
        )
    scoreboard.sort(
        key=lambda x: (
            x["positive_return_windows"],
            x["avg_sharpe"] if x["avg_sharpe"] is not None else -999,
            x["avg_return_pct"] if x["avg_return_pct"] is not None else -999,
        ),
        reverse=True,
    )

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "generated_at": now,
        "purpose": "reentry_knob_stress_vs_opt_winner_and_live_like_params",
        "path_b_gaps": [
            "ARCH-4 harness does not apply live RSI/sentiment/lockout REGIME-CASH entry filters",
            "cap0 usdc_hold_proxy has no USDC APY (~0 return), live USDC ~3.5% APY",
            "live rebalance clock != day stride",
            "do not promote from this alone",
        ],
        "primary_metric": primary,
        "opt_winner_id": winner_id,
        "scenarios_tested": [
            {"id": s["id"], "label": s["label"], "note": s.get("_research_note")}
            for s in scenarios
        ],
        "regimes": all_regimes,
        "cross_window_scoreboard": scoreboard,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")

    # Refresh classic winner stress artifact (core four + extras flagged)
    core = [r for r in winner_only if r["regime"] in {"bull", "bear", "flat", "recent"}]
    winner_payload = {
        "generated_at": now,
        "winner_id": winner_id,
        "baseline_id": baseline_id,
        "primary_metric": primary,
        "ohlcv_data_end": windows()[3]["date_range"]["end"],
        "regimes": core,
        "extra_windows": [r for r in winner_only if r["regime"] not in {"bull", "bear", "flat", "recent"}],
        "source_script": "scripts/phase6/run_reentry_knob_stress.py",
        "also_see": str(OUT.relative_to(ROOT)),
    }
    WINNER_OUT.write_text(json.dumps(winner_payload, indent=2) + "\n")

    print("\n=== CROSS-WINDOW SCOREBOARD (pos returns, then avg Sharpe) ===")
    for s in scoreboard:
        print(
            f"  {s['id']:32} pos={s['positive_return_windows']}/{s['windows']} "
            f"best={s['best_count']} avg_ret={s['avg_return_pct']} avg_sh={s['avg_sharpe']} "
            f"min={s['min_return_pct']} max={s['max_return_pct']}"
        )
    print(f"\nWrote {OUT}")
    print(f"Wrote {WINNER_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
