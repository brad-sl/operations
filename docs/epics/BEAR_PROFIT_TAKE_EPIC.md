# Epic — BEAR-PROFIT-TAKE (no short)

**ID:** EPIC-BEAR-PROFIT-TAKE  
**Start:** 2026-08-20  
**Status:** Phase 1 shadow **in progress / shipping**  
**Owner:** Phase 6 platform  
**Spec:** `docs/features/BEAR_PROFIT_TAKE_NO_SHORT_SPEC.md`

## Intent

Be **ready when bear hits**: rules-based partial profit-taking into strength, proceeds conceptually to stables, no shorts, no FOMO rebuy — **shadow evidence before any live sell**.

## Phases

| Phase | Deliverable | Live money |
|-------|-------------|------------|
| **P1** | Spec, ladder shadow, tests, runner hook, plain messages | **No** |
| **P2** | Offline path CF ladder vs ride-SL on bear legs; collection gates | No — **ran 2026-08-20** `pursue_shadow` (less-loss; synthetic N=276; 0 ledger bear) |
| **P3** | Optional relief-bounce detector (trough→strength) | No |
| **P4** | Brad OK → live partial exits + 72h rebuy block wire | **Yes only on OK** |

## Non-goals

- Loans as “TP”  
- Auto-promote  
- Replacing exchange SL  
- Thawing bear **entries** (stay park)

## Success

When BTC 30d ≤ bear threshold, shadow ladder logs clean episodes and trader-facing copy explains trims without jargon. Promote only if CF + gates + Brad OK.
