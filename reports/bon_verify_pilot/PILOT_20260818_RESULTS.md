# BoN Verify Pilot Results — 2026-08-18

**Pilot ID:** `BON-STAFF-PRIORITY-20260818`  
**Question:** What single scale-gap should we staff next (7 days), max fleet bang, min drag?  
**Method:** N=3 angled generators + single-shot baseline → multi-criteria verifier (1–20) → margin gate  
**Artifacts:** `reports/bon_verify_pilot/`  
**Skill:** `best-of-n-verify` v1  

---

## Decision (machine)

| Field | Value |
|-------|--------|
| **decision** | **`escalate`** (no auto-pick) |
| **margin** | **0.2** (need ≥1.5) |
| **winner_id** | null |
| **top two** | C (17.2) vs B (17.0) |
| **vs baseline** | Top BoN (C) **+0.8** over BASELINE (16.4); B **+0.6** |

Safety floors: all candidates passed (`live_safety≥14`, `evidence_honesty≥12`). No DQ.

---

## Scoreboard

| Rank | ID | Primary | Angle | Effort | overall | fleet | feas7d | live | honesty | drag |
|------|-----|---------|-------|--------|---------|-------|--------|------|---------|------|
| 1 | **C** | GAP-06 perf API soak | evidence_clock | **S** | **17.2** | 14 | 18 | 18 | 18 | 18 |
| 2 | **B** | GAP-05 post-SL reentry | less_loss | M | **17.0** | 18 | 15 | 18 | 18 | 16 |
| 3 | BASELINE | GAP-05 + sec GAP-06 | single_shot | M | 16.4 | 17 | 15 | 18 | 17 | 15 |
| 4 | A* | GAP-03 cap scope matrix | fleet_scale | M | 16.0 | 17 | 14 | 18 | 17 | 14 |

\*A written by parent after leaf A search-loop thrash (process finding — not pure leaf gen).

---

## What the near-tie means (plain English)

- **C** wins on *finish this week / low drag / validate KPI truth* (NEEDS_VALIDATE + harness ready). Lower pure fleet-bang.
- **B** wins on *fleet less-loss expectancy* (map L3 after GAP-02). Slightly heavier offline ledger work.
- Margin gate **refused to pretend** 0.2 is a clear winner — correct for a strategic optimizer.
- **Baseline** already blended B-primary + C-secondary; BoN split the tradeoff so the gate can see it.

### Recommended human resolution (not auto)

| If you optimize for… | Staff |
|----------------------|--------|
| **Fast closed loop this week (S)** | **C** — `P6-SCALE-GAP-06-PERF-API-SOAK-20260816` |
| **Fleet less-loss (map default)** | **B** — `P6-SCALE-GAP-05-POST-SL-REENTRY-EFF-20260816` |
| **Both without thrash** | **BASELINE shape:** primary GAP-05, secondary GAP-06 only if capacity after primary kickoff |

**Not this week as primary:** GAP-03 (A) — real fleet lever, worse 7d feasibility/drag. GAP-04 build — C correctly marked watch-not-build (n≈0 staged).

Live book: untouched. No TP / mid-cycle / USDC / capital writes.

---

## Process findings (optimizer drag)

| Finding | Action in skill |
|---------|-----------------|
| Leaf A over-searched MASTER | Steer hard + timebox; pack must be sufficient alone |
| Baseline written early → B/C saw it | Write baseline **after** gens; forbid sibling reads |
| Forced steers reduced gen diversity | Prefer angle-only steers; don’t name the primary unless stuck |
| Margin gate valuable | Keep margin_min=1.5; escalate is a success mode |
| Parallel leaves ~2.5–3 min when finishing | OK for high-stakes only; not every turn |

---

## Keep / kill / scale

| Verdict | Detail |
|---------|--------|
| **Keep** | Skill + opt-in BoN for staff/priority, code-with-tests, analyst promote readiness |
| **Kill** | Default-on every session; live-order path; BoN without frozen criteria |
| **Scale next** | Only after 1–2 more pilots (code fix BoN with real tests) OR Brad picks C or B and we measure rework |

---

## Files

```
reports/bon_verify_pilot/
  PILOT_20260818_CONTEXT.md
  candidate_{A,B,C,BASELINE}.md
  VERIFIER_RUBRIC.md
  verifier_scores_raw.json
  PILOT_20260818_RESULT.json
  PILOT_20260818_RESULTS.md   ← this file

~/.hermes/skills/software-development/best-of-n-verify/
  SKILL.md
  references/criteria_*.md
  scripts/score_candidates.py
```
