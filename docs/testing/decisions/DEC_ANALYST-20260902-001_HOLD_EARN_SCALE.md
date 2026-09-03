# ANALYST-20260902-001 — Hold earn/scale until Phase 2 bars clear

**Decision:** **ACCEPT / Brad GO**  
**When:** 2026-09-02 (PT)  
**Source:** Analyst Daily Review Needs-your-call #1  
**Proposal id:** `ANALYST-20260902-001`

## Ruling

**Hold Phase 3 earn and Phase 4 scale** until:

1. `phase2_stabilize_check` reports `phase2_ready=true` (all exit bars met), **and**
2. Brad gives an explicit new GO to reopen earn/scale.

Until then:

- Stay on stabilize / recovery path (Phase 1–2 posture).
- **Leave open book as-is** (no forced trims from this decision).
- No earn/scale promote, no “path looks better so size up,” no late FOMO seat adds for scale.
- UNI/RAVE new-buy blocks and other Phase1 wires remain unless separately lifted.
- Offline tests / shadow OPT / scoreboard continue (not live scale).

## Facts at decision (disk)

- `phase2_ready`: **false**
- Verdict: NO-GO phase2 exit bar not met
- Bars failing: 14D ≥ −2%, slope ≥ −0.03/d, ≥1 clean TP/rotation green in 7d
- Bars holding: no UNI/RAVE reopen since Phase1; code wire PASS
- Path tiles: d7 −1.85%, d14 −6.21%, slope −0.24%/d, health=declining
- Live regime surface: transition · `usdc_park` · `allow_new_buys=false` · rebalance_cap $0
- Equity ~$2284; deposit-adj go-live return context −58.8%

## What this is NOT

- Not a live order.
- Not a change to TP/SL knobs or regime `enforce`.
- Not a close of open seats.
- Not approval of proposals 002–004 (still open unless Brad says otherwise).

## Clear condition

Revisit earn/scale **only when** scoreboard/phase2 check flips ready **and** Brad GO. Default remains hold.

## Artifacts

- Sticky: `data/state/brad_go_hold_earn_scale_until_phase2.json`
- Backlog: proposal `ANALYST-20260902-001` → `accepted`
- Recovery bars SSOT: `data/state/recovery_path_soft_down_20260828.json` (`phase3_earn` / `phase4_scale`)
