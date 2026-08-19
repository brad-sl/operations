# Platform optimization examine-pack (2026-08-13)

> **For Hermes:** Fan-out five examine lanes, then SYNTH, then REV. Do not implement live knobs.

**Goal:** Turn the “too many optimization ideas” pile into discrete agent tasks, each with a written go/no-go, then one scorecard Brad can act on.

**Architecture:** Parallel **read-only** examinations → one synthesis scorecard → honesty review. No live TP, no mid-cycle enable, no new indicator grid, no second cron SSOT.

**Tech Stack:** Existing Phase 6 ledger/state JSON, shadow exit map, Dose artifacts, MASTER.

---

## Why this shape

Yesterday closed P0 wounds (armed-stop race + same-session SL *metric*). What remains is **assessment**, not invention:

| Already decided | Still examine |
|-----------------|---------------|
| Live profit-exit / hard-exit auto-apply = gated | Is shadow tape even ready to *discuss*? |
| Stoch observe_only (reeval later) | 3-day post-gate same-session SL vs old 30d |
| Mid-cycle flag off | Does a counterfactual study already exist / what would it say? |
| Dose v4 shipped | Did today’s publish actually keep diversity + domain links? |
| ~5%/mo underwritable; 20%/mo avg = fantasy | Do-not-reopen list still intact? |

---

## Task graph

```
EX-01 exits     EX-02 wounds     EX-03 allocator     EX-04 hold     EX-05 dose
   \                 \                 |                  /              /
    \                 \                |                 /              /
                         SYNTH  (scorecard + ranked next 1–2)
                                   |
                                  REV  (honesty / no live flip)
```

All five EX cards are independent. SYNTH waits for all five. REV waits for SYNTH.

---

## Cards

| ID | Assignee | Job | Output |
|----|----------|-----|--------|
| EX-01 | crypto-analyst | Shadow regime-exit map readiness | `reports/OPT_EX_01_EXITS_*.md` |
| EX-02 | crypto-analyst | 3d same-session SL + dust after SL | `reports/OPT_EX_02_WOUNDS_*.md` |
| EX-03 | crypto-analyst | Mid-cycle allocator eval (study only) | `reports/OPT_EX_03_ALLOC_*.md` |
| EX-04 | crypto-analyst | Do-not-reopen audit | `reports/OPT_EX_04_HOLD_*.md` |
| EX-05 | crypto-engineer | Dose v4 publish verify | `reports/OPT_EX_05_DOSE_*.md` |
| SYNTH | crypto-orchestrator | Ranked scorecard | `reports/OPT_EX_SYNTH_SCORECARD_*.md` |
| REV | crypto-orchestrator | Honesty sign-off | MASTER note + Kanban complete |

Handoffs: `handoffs/Handoff_P6_OPT_EX_*.md`

---

## Assessment rubric (every EX report)

Plain English first (5–8 lines):

1. **Question** this lane answered  
2. **Evidence** (paths + dates + counts)  
3. **Call:** `pursue` / `watch` / `drop` / `blocked_on_brad`  
4. **Not a 10–20% edge** unless numbers actually say so (they almost never will)

Honesty (`offline-strategy-honesty`):

- Real ledger/OHLCV only  
- Separate abs return, ΔBH, expectancy if any returns are cited  
- Less-loss vs crashing BH ≠ winner  
- N<15 or thin regime coverage → inconclusive  
- No combo-fish, no live config writes

---

## Explicit non-goals

- Live TP / RSI hard-exit flip  
- Mid-cycle `true`  
- New indicator mashup / standard_opt  
- Duplicate Phase6 Dose/X/rebalance crons  
- SEO/SEM / marketing profiles  
- Mail Batch B  

---

## After REV

Brad sees **one page**: ranked 1–2 next actions or “nothing due — idle with reason.”
