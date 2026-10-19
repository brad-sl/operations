# Handoff: W-PROCESS-TAX-ALT-SHELL-SL + E-ALT-SHELL-SL-CAREER

**Date:** 2026-10-19  
**Assignee:** crypto-analyst  
**Priority:** P0  
**Source:** Analyst Weekly Trade Review 2026-10-18 (`reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md` §6–8)  
**Type:** One-off measure RCA + career packet (no knobs, no orders)

---

## Objective

One honest data exploration of this week’s dominant process-tax line (**ADA / TIA / LINK** exchange stops) to answer: **what would optimize returns and/or reduce losses next** — without flipping live money knobs.

Attach experiment **E-ALT-SHELL-SL-CAREER** to suggestion **W-PROCESS-TAX-ALT-SHELL-SL**.

## Context (facts from weekly)

| Pair | Approx PnL | Notes |
|------|------------|-------|
| ADA-USD | ~−$5.89 | exchange stop |
| TIA-USD | ~−$4.01 | exchange stop; post-proof demote on SL |
| LINK-USD | ~−$1.96 | same-day buy→SL Oct 12; re-seat Oct 16 + Oct 17 after stop |
| Week primary | −$12.03 · WR 0/6 | tax only · zero TP meat |

Week window: **2026-10-12 → 2026-10-19** UTC.  
Prior template: `reports/E_ETH_BALLAST_SL_CAREER_2026-10-12.md` + `scripts/phase6/run_eth_ballast_sl_career.py`.

## Must Do

1. **Ledger career for each of ADA, TIA, LINK** in the weekly window (and LINK re-seat chain if legs start slightly earlier):
   - entry reason / size / notional
   - role: tryout shell vs liquid / rebalance / other (honest classification)
   - SL attach % and whether stop was naked/shallow/exchange
   - hold_h, MFE if available (`sl_width_3v8_cf` or path CF if present)
   - cooloff / re-seat after SL (especially LINK Oct 12 → 16/17)
   - post-proof dwell demote if any (TIA, LINK called out)
2. **Cross-cut table** comparing the three careers (size band, role, hold, re-seat leak, SL width).
3. **Optimize returns / reduce losses** section with ranked, evidence-backed options:
   - intake / cooloff / re-seat after SL
   - role mis-size (shell treated as liquid or reverse)
   - bank/trail vs wide SL on green-then-die
   - door quality / discipline (tie to already-live intake hygiene — do not re-implement)
   - ballast-before-shell (tie to C2/D2 already live — do not re-implement)
4. Explicit **GO / NO-GO** recommendations:
   - what Brad could GO later (config/code)
   - what is **already shipped** (C2/D2, intake discipline, dwell demote) so we don’t duplicate
   - what is **never** from this packet (global 8%→3%, PAXG, Kelly, dual_agree auto, blow flat $75)
5. Ship permanent artifacts (not scratch):
   - `reports/E_ALT_SHELL_SL_CAREER_2026-10-19.md`
   - `data/state/e_alt_shell_sl_career_latest.json`
   - optional rebuild script `scripts/phase6/run_alt_shell_sl_career.py` (mirror ETH career one-call; measure-only)
6. Update notepad keys if weekly memory expects: `open_suggestions`, `go_queue` (measure notes only).

## Must Not Do

- No live orders, no runner restarts, no config `live_apply` flips
- No global `stop_loss_pct` 0.08 → 0.03
- No PAXG / scale-window / post-proof dwell live_apply changes
- No Kelly / deploy_pct / dual_agree auto / perma buy_block expansion
- No edge/promote claim language from thin N
- Do not invent missing ledger rows — mark unknown honestly

## Expected Deliverables

| Artifact | Path |
|----------|------|
| Career MD | `reports/E_ALT_SHELL_SL_CAREER_2026-10-19.md` |
| Career JSON | `data/state/e_alt_shell_sl_career_latest.json` |
| Rebuild script (preferred) | `scripts/phase6/run_alt_shell_sl_career.py` |
| Short MASTER note | append under `WEEKLY-SUGGESTIONS-20261018` in `docs/MASTER_TASK_TRACKING.md` |

## Success Criteria

- [ ] All three pairs have entry→SL chain with timestamps + PnL grounded in `trades/phase6_trades.jsonl` (and related state if needed)
- [ ] Role classification honest (tryout vs liquid vs other)
- [ ] LINK re-seat after SL explained with cooloff/intake facts
- [ ] Ranked “optimize return / reduce loss” options with **GO vs already-live vs NO-GO**
- [ ] Explicit: no knob flips in this card
- [ ] Artifacts under `reports/` + `data/state/` committed path (main repo workspace)

## Validation

```bash
cd /home/brad/projects/crypto-trading-bot
# if script shipped:
.venv/bin/python scripts/phase6/run_alt_shell_sl_career.py
test -f reports/E_ALT_SHELL_SL_CAREER_2026-10-19.md
test -f data/state/e_alt_shell_sl_career_latest.json
```

Cross-check week totals ≈ ADA+TIA+LINK tax vs weekly −$12.03 primary.

## Skills to load

- `offline-strategy-honesty`
- `trade-comparison-standard`
- `phase6-sl-exits-and-dust`
- `phase6-tryout-lifecycle` (role / cooloff / dwell demote vocabulary)

## References

- `reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md`
- `data/state/analyst_weekly_trade_review_latest.json`
- `reports/E_ETH_BALLAST_SL_CAREER_2026-10-12.md`
- `scripts/phase6/run_eth_ballast_sl_career.py`
- `reports/SOFT_DOWN_8PCT_DIAGNOSTIC_LATEST.md`
- `reports/SOFT_DOWN_REVERSE_STACK_GO_LATEST.md` (C2/D2/intake already GO 2026-10-17)
- `trades/phase6_trades.jsonl`
- FAQ: `docs/faq/Internal_Trading_Platform_FAQ.md`

## Workspace

Use **project repo** (`dir:/home/brad/projects/crypto-trading-bot` or board project anchor) — permanent artifacts only. No ephemeral scratch as final home.
