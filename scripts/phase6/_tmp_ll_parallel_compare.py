#!/usr/bin/env python3
"""One-shot luck ladder parallel compare board (operator)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from phase6.core import rsi_event_x_tryout_shadow as r0
from phase6.core import tryout_scale_up_live as live
from phase6.core import tryout_scale_up_shadow as s
from phase6.core.knife_filter_shadow import run_knife_filter_shadow

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    b1 = run_knife_filter_shadow()
    b5 = s.run_cycle()
    pl = live.plan_live_steps(board=b5)
    b0 = r0.build_shadow_board() if hasattr(r0, "build_shadow_board") else r0.run_cycle()
    if isinstance(b0, tuple):
        b0 = b0[0]

    gaps = [
        "CF chicken-egg: scores only after would_scale registers paper lot AND later exit; would_scale=0 => CF n=0 => live plan blocked while require=true",
        "R5 gates (hold>=2h, r in [1.5%,3.8%], phase in {1,2}) reject ZEC phase5 / LINK phase3 flat bags — may never scale these seats",
        "Armed path still needs operator CLI for money; no runner hook / no auto-apply (intentional)",
        "same_day_pair_buy is entry gate (R0); scale uses OrderExecutor direct — live SL reattach + bag_id on add not E2E proven",
        "tryout_tagged_buy false / empty entry_reason on live lots — weak episode tagging for scale registry",
        "R2 exit geometry / R3 fee tax / R4 seat lottery / R6 regime tryout still scheduled/blocked",
        "No dedicated parallel-compare cron; board is on-demand",
        "R0 spend_x false on shadow board; paid probe separate — entry crumbs slow",
    ]

    compare = {
        "schema": "luck_ladder_parallel_compare_v1",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "r5_scale": {
            "shadow_live_apply_pin": b5.get("live_apply"),
            "decision_live_apply": b5.get("brad_decision_live_apply"),
            "live_path_armed": pl.get("live_armed"),
            "n_scanned": b5.get("n_scanned"),
            "would_scale_pairs": b5.get("would_scale_pairs"),
            "decisions": b5.get("decisions"),
            "cf": b5.get("cf"),
            "live_plan": {
                "n_would_scale": pl.get("n_would_scale"),
                "n_planned": pl.get("n_planned"),
                "n_blocked": pl.get("n_blocked"),
                "cf_gate": pl.get("cf_gate"),
                "kill": pl.get("kill"),
                "daily": pl.get("daily"),
            },
        },
        "r0_sensor_clock": {
            "n_universe": b0.get("n_universe"),
            "n_trigger_pool": b0.get("n_trigger_pool"),
            "n_selected_top_k": b0.get("n_selected_top_k"),
            "n_would_buy_if_x_pass": b0.get("n_would_buy_if_x_pass"),
            "n_production_entry_ok": b0.get("n_production_entry_ok"),
            "live_gate": b0.get("live_gate"),
            "place_orders": b0.get("place_orders"),
            "spend_x": b0.get("spend_x"),
            "edge_class": b0.get("edge_class"),
            "plain": (b0.get("plain_english") or "")[:500],
            "selected_pairs": [x.get("pair") for x in (b0.get("selected") or [])],
        },
        "r1_knife": {
            "n_pairs": b1.get("n_pairs"),
            "claim_class": b1.get("claim_class"),
            "arm_table": b1.get("arm_table"),
            "plain": (b1.get("plain_english") or "")[:400],
            "live_gate": b1.get("live_gate"),
            "row_pairs": [r.get("pair") for r in (b1.get("rows") or [])],
        },
        "e2e_gaps": gaps,
    }
    (ROOT / "data/state/luck_ladder_parallel_compare_latest.json").write_text(
        json.dumps(compare, indent=2, default=str) + "\n"
    )

    dec_lines = [
        f"- **{d.get('pair')}**: {d.get('status')} · {d.get('reasons')}"
        for d in (b5.get("decisions") or [])
    ]
    md_parts = [
        "# Luck Ladder ∥ Scale-up parallel compare",
        "",
        f"**As of:** {compare['as_of']}",
        "**Mode:** R0/R1 measure · R5 live-path **ARMED** · money CLI-only · CF require ON",
        "",
        "## Side-by-side",
        "",
        "| Lane | Signal now | Blocks |",
        "|------|------------|--------|",
        (
            f"| **R0 sensor clock** | univ {b0.get('n_universe')} · trigger {b0.get('n_trigger_pool')} · "
            f"would_buy_if_x {b0.get('n_would_buy_if_x_pass')} · prod_ok {b0.get('n_production_entry_ok')} | "
            "live_gate OFF; X floor; ZEC same_day |"
        ),
        f"| **R1 knife** | n_pairs={b1.get('n_pairs')} · {b1.get('claim_class')} | measure-only; thin n_r |",
        f"| **R5 scale shadow** | scanned {b5.get('n_scanned')} · would_scale **0** | ZEC hold/r/phase5; LINK hold/r/phase3 |",
        f"| **R5 live path** | **armed=True** · planned **0** | CF n=0<8; no would_scale |",
        "",
        "## R5 decisions",
        *dec_lines,
        "",
        "## R1 arm_table",
        "```",
        json.dumps(b1.get("arm_table"), indent=2),
        "```",
        f"plain: {(b1.get('plain_english') or '')[:300]}",
        "",
        "## R0 plain",
        (b0.get("plain_english") or "")[:400],
        "",
        "## E2E gaps still open",
        *[f"- {g}" for g in gaps],
        "",
        "## How to get quality data (without degen)",
        "1. Keep shadow cron — wait hold>=2h; if r/phase never clear, loosen **measure** gates so paper would_scale can register CF legs.",
        "2. Or waive CF require for first 1–2 operator steps (separate GO) — still 1/day $25 caps.",
        "3. Or synthetic scale-vs-stay on every tryout exit (code) — best N, bigger change.",
        "",
        "State: `data/state/luck_ladder_parallel_compare_latest.json`",
    ]
    (ROOT / "reports/LUCK_LADDER_PARALLEL_COMPARE_LATEST.md").write_text("\n".join(md_parts) + "\n")

    status = """# Luck Ladder Status — LATEST

**Plan:** `docs/plans/2026-09-15-luck-ladder-platform-refine.md`  
**Updated:** 2026-09-19  
**Mode:** measure-only rungs · R5 live **path ARMED** · money still CLI + CF bar · no auto-buy · no promote

## Board

| Rung | Factor | Status | Gate / next |
|------|--------|--------|-------------|
| **R0** | Sensor clock | **RUNNING shadow + paid probe** | live_gate OFF on shadow; probe budgeted; same_day blocks ZEC/LINK re-entry today |
| **R1** | Knife vs wash | **RUNNING shadow** | thin n_r; ATTENTION_ONLY |
| **R2** | Exit geometry | SCHEDULED | After denser R0/R1 crumbs |
| **R3** | Fee / path tax | SCHEDULED | With/after R2 |
| **R4** | Seat lottery | BLOCKED | Needs R1 crumbs |
| **R5** | Size ladder | **SHADOW ON + LIVE PATH ARMED** | would_scale=0; CF n=0; money OFF until would_scale+CF/waive+CLI |
| **R6** | Regime tryout | BLOCKED | Needs R1 arms stable |

## Parallel compare (2026-09-19)

See `reports/LUCK_LADDER_PARALLEL_COMPARE_LATEST.md`.

## Decisions log
- 2026-09-19: Brad GO arm R5 live path (`live_apply=true` decision file). Shadow pin stays false. CF require stays true. No money fire.
- 2026-09-19: $25 shell band on scale shadow; live path module shipped.
"""
    (ROOT / "reports/LUCK_LADDER_STATUS_LATEST.md").write_text(status)

    print(
        json.dumps(
            {
                "armed": live.is_live_armed(),
                "planned": pl.get("n_planned"),
                "cf_gate": pl.get("cf_gate"),
                "r0_trigger": b0.get("n_trigger_pool"),
                "r0_would_buy": b0.get("n_would_buy_if_x_pass"),
                "r0_prod_ok": b0.get("n_production_entry_ok"),
                "r1_n": b1.get("n_pairs"),
                "r1_class": b1.get("claim_class"),
                "r5_scan": b5.get("n_scanned"),
                "r5_would": b5.get("would_scale_pairs"),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
