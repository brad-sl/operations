## Candidate A · angle=fleet_scale

### Primary (exactly one task id)
`P6-SCALE-GAP-03-CAP-SCOPE-MATRIX-20260816`

### Optional secondary (0–1)
`P6-SCALE-GAP-08-PROMO-FIREDRILL-20260816`

### Why now (≤5 bullets)
- At 100s of traders, ambiguous cap scope (cash-only vs cash+rotation vs max position) multiplies into silent risk envelope drift — L2 semantics before more entry/exit chrome.
- MASTER already froze offline arms + honesty enums; live cap rewrite stays Brad-gated, so staff can finish an offline CF+ISO without touching books.
- Map staffing default puts L2 cap semantics after L1/L3 wounds; GAP-01/02 are shipped — next fleet lever that is still open and regimen-ready is GAP-03.
- Optional GAP-08 fire-drill is pure L5 blast-radius insurance (bad overlay → detect → rollback) with zero permanent knobs — only if primary has spare capacity.
- OPT_EX remains idle-with-reason; liq live_partial stays NO-GO; do not staff single-book trims.

### Kill / pass criteria
- Pass: offline report under flat_B fingerprint with three scopes; P&L/DD/stop$/rotation$; enum keep_cash_only|extend_to_rotations|add_max_position|inconclusive; finalize-report + decide packet; no live config write.
- Kill: N dishonest without inconclusive label; any live rebalance_cap rewrite; thaw util chase; scope expands into mid-cycle/USDC/TP.

### Must not touch
Live TP, hard-exit auto-apply, mid-cycle allocator, USDC park, live capital rewrite, sleeve trims, live_partial liq hop, dropped indicator mashups.

### Effort class: M
