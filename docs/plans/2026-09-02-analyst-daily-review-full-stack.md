# Analyst Daily Review Full Stack — Implementation Plan

> **For Hermes:** Execute task-by-task. Brad GO 2026-09-02: full stack (A+B+C) + strip filler status.

**Goal:** One high-signal Analyst loop that answers: what's working, what's not, what needs change, what's in pipeline, results of changes, blockers, goal realization — with real proposals when earned, zero filler TG spam.

**Architecture:**
1. **C — Capacity unstick:** Close overdue `ANALYST-REGIME-BULL-KNOBS-20260824-TRIAL` via finalize/decide so strategy emit can run.
2. **A — Daily outcome scoreboard (no_agent):** Deterministic facts from ledger/signals/gates/trials/OPT → `data/state/analyst_daily_scoreboard_latest.json` + short markdown. Quiet stdout unless `--print`.
3. **B — Analyst daily review (agent, 1×/day):** Reads scoreboard + pipeline; writes structured review JSON + TG body only when material; proposes ≤3 evidence-backed improvements (novelty bar); never auto-promote / never write live knobs.
4. **Filler strip:** Demote twice-daily intel TG to local (facts still computed for scoreboard/inputs) OR keep one brief if still decision-useful; silence empty TG crons; kill static “status theater.” Primary Brad surface = **Analyst Daily Review** (goal realization), not duplicate HOLD spam.

**Must not touch:** live book, `config/regime_*` promote, seats, capital, credentials.

**Tech:** Python under `phase6/research/` + `phase6/scripts/`; Hermes cron; skill `phase6-analyst-daily-review`.

**Proof of done:**
- Scoreboard isolation test passes + JSON fresh
- Stuck trial not blocking capacity (CLOSED or REVIEW_PENDING with report)
- Review dry-run produces 7-section body
- Cron: scoreboard daily no_agent; review daily agent deliver telegram (empty→silent when nothing material optional)
- Filler: document which jobs paused/local; no duplicate daily HOLD noise

---

## TG contract (B) — required sections

```
=== Analyst Daily Review ===
date · time UTC
GOAL REALIZATION: <one line vs north star / Phase2 / equity path>
WORKING: …
NOT WORKING: …
NEEDS CHANGE: … (ranked; only real)
PIPELINE: … (trials/OPT/shadow/MASTER)
CHANGE RESULTS: … (recent closes / shadows)
BLOCKERS: …
NEEDS YOUR CALL: … (≤3 new proposals or none)
```

Quiet rule: if nothing material vs prior review hash and no blockers/proposals, stdout empty (no TG).

---

## Tasks

### Task 1: Unstick bull-knobs trial
Run offline report if possible; else finalize with honest `drop`/`abort` + note overdue empty reports; `decide` if appropriate; free capacity.

### Task 2: `analyst_daily_scoreboard.py`
Build facts pack: trades 1d/3d/7d, open positions snapshot, signals, sent/RSI, gates/blocks, Phase2, OPT hint, trial INDEX, proposal backlog freshness, north-star metrics.

### Task 3: Isolation test for scoreboard
### Task 4: Cron wrapper scoreboard
### Task 5: Review composer script (deterministic scaffold) + agent prompt skill
### Task 6: Hermes crons + filler strip
### Task 7: Verify + MASTER note
