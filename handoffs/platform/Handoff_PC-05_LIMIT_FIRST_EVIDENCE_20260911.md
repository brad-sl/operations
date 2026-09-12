# Handoff — PC-05 Limit-first fill evidence — 2026-09-11

**MASTER:** `PC-05-LIMIT-FIRST-EVIDENCE-20260911`  
**Parent epic:** `PLATFORM-COMPLETENESS-20260911`  
**Assignee when staffed:** `crypto-engineer`  
**Priority:** P1  
**Kanban tag:** `[STAGED]`  
**Note:** Denominator may stay 0 until PC-03 yields buy attempts — report that honestly.

### Objective

Instrument and report limit-first attempts/fills/skips; keep market_fallback at 0 unless Brad GO.

### Must Do

1. Counters + latest JSON under `data/state/`
2. Report after attempts exist or 14d drought note
3. Align with `docs/design/LIMIT_FIRST_BUY_DESIGN.md`

### Must Not

- market_fallback_max_usd &gt; 0 without GO
- Volume grind for maker tier

### Success Criteria

- Honest fill-rate with clear denominator
- Isolation if new counter module
