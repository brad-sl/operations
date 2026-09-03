## Candidate A · angle=fleet_scale
### Primary (exactly one task id)
`P6-SCALE-GAP-03-CAP-SCOPE-MATRIX-20260816`
### Optional secondary (0–1)
none
### Why now (≤5 bullets)
- $75 rebalance_cap is leaky on rotations/stacks; violates product law for all traders at 100s scale
- Explicit cap scope matrix (cash_only / cash+rotation / max_position) required before safe cloning of option B to fleet
- Directly addresses L2 Capital/regime machine: same knobs + outer risk envelope for every tenant
- High P(gain at scale) per lanes map; queued, offline+iso ready, no live writes needed
- Enables platform clone readiness and controls blast radius before scaling expectancy/reentry work
### Kill / pass criteria
- Pass: offline CF+ISO under flat_B produces honest enum rec (keep_cash_only|extend_to_rotations|add_max_position) with ≥15 trades or slice count; report P&L/DD/stop/rotation $; no live config
- Kill: enum=inconclusive after honest N; or any live capital/config write attempted; or low-evidence run
### Must not touch
- No live config / order / capital / sleeve / USDC / mid-cycle / TP/SL flips
- No live promote without Brad
- Prefer frozen bars + existing harness; no inventing staged decisions
- Idle-with-reason OK for immature clocks
### Effort class: M
