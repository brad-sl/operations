# Analyst weekly 7d trade review (fact pack)

**As of:** 2026-10-04T17:43:11.787781+00:00
**Window:** 2026-09-27T17:43:11.787781+00:00 → 2026-10-04T17:43:11.787781+00:00 (7d)
**Schema:** `analyst_weekly_trade_review_v1`

## Scorecard

- Primary buys/sells: **14** / **13** (stable legs 26)
- Realized PnL (primary exits w/ pnl): **$4.7888**
- Exit WR: **0.6** (green 3 / red 1 / flat 1)
- Process tax: n=2 sum=**$0.0** · non-tax n=3 sum=**$4.7888**
- Same-day buy+sell pair-days: **4**
- Goal/path (scoreboard): **OFF_TRACK** / **sideways** · recent 0.27%
- Regime: **flat** · util **None%** · equity ~$None

## Exit buckets

```{
  "scale_window_eject": 8,
  "tp_profit": 2,
  "dust_sweep": 2,
  "other": 1
}```

## Exit reasons (top)

- `tryout_scale_window_eject` × 8
- `take_profit_trail` × 2
- `dust_sweep_orphan` × 2
- `unknown` × 1

## Pair PnL (worst → best head)

- BTC-USD: $0.0 (sells=3)
- LINK-USD: $2.3574 (sells=4)
- SOL-USD: $2.4314 (sells=2)

Best:
- SOL-USD: $2.4314 (sells=2)
- LINK-USD: $2.3574 (sells=4)
- BTC-USD: $0.0 (sells=3)

## Seed hypotheses (agent starting points)

- **P1** `seed_tryout_intake_quality` (tryout_funnel): ~8 scale-window/tryout ejects in window — intake (discipline/knife/RSI door) or kindling bar may be admitting shells that never clear scale.
- **P2** `seed_same_day_churn` (tryout_churn): 4 pair-days with same-day buy+sell — dead-kindling loop is working but fee+cooloff tax may dominate; check seat quality vs eject bar.
- **P1** `seed_matrix_block_max` (matrix_room): Matrix: 3 held bags with max_add=$0 — review binding budgets + role_law vs flat add-risk knobs; matrix is rulebook not stone (optimize w/ Brad GO).

## Membership sizing matrix (rulebook — not stone)

Membership sizing matrix is the live rulebook for class/role/scale-path/regime room — not stone. Weekly analyst must review rules + live room and may suggest optimizations (measure-only; Brad GO before knobs).

- Regime: **flat** · rows **13** · inconsistent **0**
- Role counts: `{"ballast_core": 2, "liquid_held": 10, "preserve_ballast": 1}`
- Scale-path counts: `{"add_risk_pyramid": 12, "none": 1}`
- Live add-risk: `{"allow_pyramid": true, "k_profit": 0.25, "h_add": 0.01, "H_book": 0.04, "target_pair_weight": 0.18, "rebalance_cap_usd": null}`

### Held bags

- ETH-USD: role=ballast_core held=$242.7 max_add=$0.0 path=add_risk_pyramid block=cash_slice|capped_to_zero
- BTC-USD: role=ballast_core held=$55.6 max_add=$0.0 path=add_risk_pyramid block=cash_slice|capped_to_zero
- PAXG-USD: role=preserve_ballast held=$78.53 max_add=$0.0 path=none block=cash_slice|capped_to_zero

### Block-max held (max_add=$0)

- ETH-USD: ballast_core held=$242.7 · cash_slice|capped_to_zero
- BTC-USD: ballast_core held=$55.6 · cash_slice|capped_to_zero
- PAXG-USD: preserve_ballast held=$78.53 · cash_slice|capped_to_zero

CLI: `python scripts/phase6/run_membership_sizing_matrix.py --filter block_max`
Docs: `docs/features/MEMBERSHIP_SIZING_MATRIX.md`

## Agent brief

Review prior 7d trades + Membership Sizing Matrix rulebook + free quest outside history; propose concrete ways to improve deposit-adj take-home (~5%/mo north star). Prefer less process tax and higher quality scale/membership over new digs. Matrix is the current regime rulebook — not stone; suggest optimizations with evidence.

Rules:
- Ground every claim in fact pack numbers or cited state files.
- No live config/knob/order writes — suggestions + backlog IDs only.
- Honesty over cosmetics; paper MTM ≠ filled PnL.
- If N is thin, say so — no edge theater.
- Separate process tax vs true alpha miss.
- MUST review membership_sizing_matrix in context (role_law, regime add-risk, block_max, inconsistencies, kindling vs ballast).
- Quest OK: matrix CLI/API, scale-window board, money-arms monitor, regime/add-risk, OPT leaderboard, dwell, prior week continuity/notepad.
- Use job notepad + continuity for week-over-week memory (open suggestions, GO status).

Output contract:
- 1) Week scorecard (PnL, WR, tax, util, regime) — 5 lines max
- 2) What worked / what hurt — bullets with $ or counts
- 3) Matrix rulebook review — what binds growth; any policy drift; 1–3 matrix optimization ideas
- 4) Top 3–7 suggestions ranked P0/P1/P2 with: lever, expected effect, evidence, risk, GO needed?
- 5) Explicit non-suggestions (do not touch)
- 6) Optional: 1 measurement experiment for next week
- 7) Update notepad keys: last_scorecard, open_suggestions, matrix_notes (short)

## Recent primary sells (detail head)

| pair | ts | bucket | tax | pnl | reason |
|------|----|--------|-----|-----|--------|
| SOL-USD | 2026-10-04T16:45:46 | scale_window_eject |  | None | tryout_scale_window_eject |
| LINK-USD | 2026-10-03T22:45:44 | scale_window_eject |  | None | tryout_scale_window_eject |
| HYPE-USD | 2026-10-02T22:45:43 | scale_window_eject |  | None | tryout_scale_window_eject |
| SOL-USD | 2026-10-02T07:21:56 | tp_profit |  | 2.4314 | take_profit_trail |
| HYPE-USD | 2026-10-02T04:45:43 | scale_window_eject |  | None | tryout_scale_window_eject |
| BTC-USD | 2026-10-02T04:03:58 | dust_sweep | Y | 0.0 | dust_sweep_orphan |
| BTC-USD | 2026-10-02T04:02:43 | dust_sweep | Y | -0.0 | dust_sweep_orphan |
| BTC-USD | 2026-10-02T04:00:58 | other |  | 0.0 | unknown |
| TIA-USD | 2026-10-01T14:41:54 | scale_window_eject |  | None | tryout_scale_window_eject |
| LINK-USD | 2026-10-01T14:41:49 | scale_window_eject |  | None | tryout_scale_window_eject |
| LINK-USD | 2026-10-01T05:29:58 | scale_window_eject |  | None | tryout_scale_window_eject |
| TIA-USD | 2026-10-01T05:29:54 | scale_window_eject |  | None | tryout_scale_window_eject |
| LINK-USD | 2026-09-29T15:30:38 | tp_profit |  | 2.3574 | take_profit_trail |

State: `data/state/analyst_weekly_trade_review_latest.json`
Report: `reports/ANALYST_WEEKLY_TRADE_REVIEW_LATEST.md`

**Measure-only.** Suggestions require Brad GO before knobs.
