# Daily Dose — Publication Cycle

**Status:** IMPL_READY — D0/D1/D2 scripts live (TG off)  
**Date:** 2026-08-03  
**Product:** Crypto trading platform comms (trader status / ops brief) — **not** client SEO/SEM  
**Board:** `crypto-bot-project` (never `marketing-consultancy`)  
**Boundary:** `docs/PROJECT_BOUNDARY.md` — may **reuse role profiles** (`content-editor`, `publisher`); must **not** pull SEO/SEM/Ads client workflows or marketing-consultancy deliverables into this repo.

---

## 0. Plain English

We already have:
1. A **machine draft** (`run_daily_dose.py`) — rank RSS + rules editorial  
2. **People-shaped agents** — `content-editor`, `publisher`  

Brad’s sample review showed pure machine output still needs **editorial judgment** (kill #4/#8, active voice, drop filler).

**Publication cycle** = repeatable loop:

```
Cron/machine draft  →  Content editor  →  Publisher  →  Surfaces
     (cheap)              (quality)         (ship)      (disk→TG/dash)
```

Kanban holds the **workflow + gates**. Cron holds the **boring fetch**. Humans/agents hold **publish OK**.

---

## 1. Does Kanban make sense? (decision)

| Approach | When | Verdict |
|----------|------|---------|
| **Code-only forever** | Titles always perfect | ❌ Failed Brad sample |
| **Full marketing agency board** | Client SEO campaigns | ❌ Wrong project boundary |
| **Ad-hoc chat every day** | One-offs | ❌ No habit, no audit trail |
| **Publication cycle on crypto-bot Kanban** | Daily dose + later trader pages | ✅ **Yes** |

**Yes — create a publication cycle on `crypto-bot-project`.**  
Borrow **editor + publisher profiles**; do not open SEO/SEM cards.

---

## 2. Roles (thin cast)

| Role | Profile | Job | Does *not* |
|------|---------|-----|------------|
| **Draft engine** | cron / `run_daily_dose.py` | Fetch RSS, rank, rules editorial, write artifacts | Send TG, touch trading |
| **Content editor** | `content-editor` | Cut, rewrite active voice, kill filler/dupes, approve top 5 | Invent facts, trade |
| **Publisher** | `publisher` | Final format for TG/dash; ship only if editor `APPROVED` | Edit substance without re-review |
| **Orchestrator** | `crypto-orchestrator` or default | Unblock gates, Phase B enable TG, viability decide | Rewrite every headline |
| **Optional fact check** | `crypto-analyst` | Only if editor flags a claim as market-sensitive | Full rewrite |

WIP: **1 dose in flight per day.**

---

## 3. Pipeline stages (Kanban columns / card states)

Use existing board columns; encode stage in card title prefix + body checklist.

| Stage | Owner | Input | Output | Gate |
|-------|-------|-------|--------|------|
| **D0 DRAFT** | cron / engineer | RSS | `daily_dose_latest.json` + preview | Isolation tests green |
| **D1 EDIT** | content-editor | latest.json | `daily_dose_edited.json` + checklist | `status: APPROVED` or `REVISE` |
| **D2 PUBLISH** | publisher | edited.json | TG body final + optional dash payload | Editor APPROVED; Brad OK for live TG |
| **D3 ARCHIVE** | auto | published | history row + viability scorecard tick | Done |

### Editor checklist (D1)
- [ ] Drop roundups / “what happened today”  
- [ ] Drop vague explainers redundant with a news item  
- [ ] One card per event (e.g. one Coldcard)  
- [ ] Active voice titles  
- [ ] Max **5** bullets for TG (dash may show 8)  
- [ ] No per-bullet “why it matters on this platform” lines (retired 2026-08-13)  
- [ ] No trade recommendations  
- [ ] Mark `APPROVED` or `REVISE` + notes  

### Publisher checklist (D2)
- [ ] Banner: not a trade signal  
- [ ] Links work  
- [ ] Phase A: write `daily_dose_publish_ready.txt` only  
- [ ] Phase B: TG send only if `PUBLISH_TELEGRAM=1` **and** Brad OK flag  
- [ ] Never write sentiment_cache / runner  

---

## 4. Artifacts (canonical paths)

| File | Writer | Reader |
|------|--------|--------|
| `data/state/daily_dose_latest.json` | draft engine | editor |
| `data/state/daily_dose_telegram_preview.txt` | draft engine | editor |
| `data/state/daily_dose_edited.json` | content-editor | publisher |
| `data/state/daily_dose_publish_ready.txt` | publisher (`run_daily_dose_publish.py`) | TG/cron Phase B |
| `docs/features/DAILY_DOSE_OPERATOR_COMMANDS.md` | — | operator cheat sheet |
| `data/state/daily_dose_history.jsonl` | draft (+ publish meta) | viability |
| `reports/DAILY_DOSE_VIABILITY_*.md` | orchestrator weekly | Brad |

Schema for edited file: same item cards + `editorial_review: { status, notes, reviewer, at }`.

---

## 5. Cadence

### Phase A (viability — now)
| When | What |
|------|------|
| Daily ~07:15 PT (or manual) | Machine draft |
| Daily ~07:30 PT or on card | Editor pass (agent) |
| Daily ~07:45 PT | Publisher → **disk only** `publish_ready` |
| End of week | Viability scorecard; Brad: Phase B TG? |

**No live Telegram until Brad OK.**

### Phase B (after viable)
Same cycle + publisher may send TG; dash `/api/daily_dose` reads **edited or publish_ready**, never raw rank-only if editor ran.

### Phase C
Publisher (or dash) filters by trader symbols — still after editor.

---

## 6. Kanban shape (recurring)

### Epic card (once)
`DOSE-EPIC: Daily Dose publication cycle` — links spec + this doc.

### Recurring daily (template)
Prefer **one standing “loop” card** + daily child, or cron that opens a dated card:

`DOSE-2026-08-04: draft→edit→publish`

```
parents: none for draft
D1 parents=[D0] assignee=content-editor
D2 parents=[D1] assignee=publisher
```

If daily card spam is noisy: **single loop card** “Daily Dose publication loop” with checklist reset each day + cron draft only; editor/publisher claim via comments. Prefer **dated cards for first 2 weeks** (audit trail for viability), then collapse to loop.

### Implementation cards (one-time)
1. Engineer: wire `daily_dose_edited.json` + editor handoff template  
2. Engineer: publisher script `run_daily_dose_publish.py` (disk; TG stub)  
3. Cron: morning draft only  
4. Orchestrator: weekly viability  

---

## 7. What stays in code vs agents

| Layer | Owner | Why |
|-------|-------|-----|
| Fetch, rank, hard reject roundups, event dedupe, forced-to→active heuristics | **Code** | Cheap, repeatable, testable |
| Taste: “is this worth a trader’s attention?”, tone, final cut to 5 | **content-editor** | Brad’s review needs judgment |
| Channel format, send gates | **publisher** | Separation of duties |
| Enable TG / kill cycle | **Brad / orchestrator** | Risk |

Don’t replace code editorial with a full LLM on every RSS item — **agents review the shortlist**, not the firehose.

---

## 8. Anti-patterns

- ❌ Assigning SEO/SEM specialists  
- ❌ Cards on `marketing-consultancy` board  
- ❌ Publisher sending without editor APPROVED  
- ❌ Editor inventing prices or “buy the dip”  
- ❌ Wiring dose into allocator “because the headline is bullish”  
- ❌ 12-agent fan-out for 8 headlines  

---

## 9. Success metrics (cycle health)

| Metric | Target |
|--------|--------|
| Editor time | ≤10 min wall / dose |
| Drop rate from draft→publish | 20–50% items cut is healthy |
| Brad mute rate | 0 |
| Publish without APPROVED | 0 |
| Coffee test (spec §6.2) | Pass 4/5 days |

---

## 10. Related docs

- Feature Phase A: `docs/features/DAILY_DOSE_NEWS_FEED_PHASE_A_SPEC.md`  
- Handoff build: `handoffs/platform/Handoff_FEAT-DAILY-DOSE-NEWS-20260803.md`  
- This cycle: `docs/features/DAILY_DOSE_PUBLICATION_CYCLE.md`  
- Boundary: `docs/PROJECT_BOUNDARY.md`  

---

*End.*
