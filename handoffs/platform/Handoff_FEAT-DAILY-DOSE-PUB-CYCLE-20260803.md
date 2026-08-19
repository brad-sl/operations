# Handoff — Daily Dose Publication Cycle (Kanban)

**Status:** IMPL_DONE (scripts + isolation)\n**MASTER:** `FEAT-DAILY-DOSE-PUB-CYCLE-2026-08`  
**Spec:** `docs/features/DAILY_DOSE_PUBLICATION_CYCLE.md`  
**Board:** `crypto-bot-project` only  
**Date:** 2026-08-03  

## Objective
Stand up a **draft → edit → publish** cycle for Daily Dose using existing **content-editor** and **publisher** profiles, without importing SEO/SEM consultancy work.

## Must do
1. Keep machine draft (`run_daily_dose.py`) as D0  
2. Editor produces `daily_dose_edited.json` with APPROVED/REVISE  
3. Publisher produces `daily_dose_publish_ready.txt` (disk); TG off until Brad OK  
4. Kanban on **crypto-bot-project**; assignees content-editor / publisher / crypto-engineer  
5. Isolation tests stay green  

## Must not
- marketing-consultancy board  
- seo-specialist / sem-specialist cards  
- Trade signals / sentiment_cache writes  
- Live Telegram without Brad OK  

## Deliverables
- Cycle spec (done)  
- Kanban epic + impl cards  
- Editor template path in handoff or `docs/features/`  
- Optional: `run_daily_dose_publish.py` stub  

## Success
Dated first-week cards can run end-to-end disk publish with editor gate.


## Kanban IDs (crypto-bot-project)
| Card | ID | Assignee |
|------|-----|----------|
| EPIC | t_aa220fdc | crypto-orchestrator |
| IMPL-01 | t_e48e3925 | crypto-engineer |
| TPL-01 editor | t_7c165e91 | content-editor |
| TPL-02 publisher | t_a54c1eae | publisher |


## Implementation (2026-08-03)

| Piece | Path |
|-------|------|
| Core | `phase6/core/daily_dose_publish.py` |
| D1 edit CLI | `phase6/scripts/run_daily_dose_edit.py` |
| D2 publish CLI | `phase6/scripts/run_daily_dose_publish.py` |
| Isolation | `phase6/tests/test_isolation_daily_dose_publish.py` PASS |
| Ops commands | `docs/features/DAILY_DOSE_OPERATOR_COMMANDS.md` |

Smoke: latest → edited APPROVED (5) → publish_ready; REVISE → publish rc 2.
Telegram default OFF (stub only).
