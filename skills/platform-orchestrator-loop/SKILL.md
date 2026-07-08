---
name: platform-orchestrator-loop
description: Slice-based epic delivery for Hermes coding agents — isolation harnesses, file-backed memory, shadow-before-live, skills that evolve from pitfalls. Copy to ~/.hermes/skills/ for any long-running platform build.
---

# Platform orchestrator loop (Hermes coding agent)

A **manageable** pattern for turning a messy codebase into a **working platform** with Hermes as orchestrator + coding agent. Battle-tested on a live trading stack; **domain-agnostic** — swap paths and nouns for your project.

## Core idea

| Principle | What it means |
|-----------|----------------|
| **Slices, not big bangs** | Ship R0→R1→… epics; each slice has one exit test and one handoff |
| **Files are SoT for facts** | Run IDs, metrics, leaderboards → `data/state/*.json` + append-only `*.jsonl` |
| **Hermes memory for taste** | User prefs, conventions, “never fake data” — not numeric outcomes |
| **Shadow before live** | In-memory or overlay config; drift monitor; explicit user approval for production writes |
| **Honest agent voice** | Lead with measured truth; cite artifacts; no promotion hype |
| **Skills compound** | After each verified workflow, patch pitfalls into this skill |

## Three roles (one human, one or more Hermes profiles)

```
OVERSIGHT (human):     risk budget, live promotion, “proceed R3”
ORCHESTRATOR (Hermes): plan slices, delegate, verify, handoffs, MASTER
EXECUTION (code/cron): deterministic runners; no LLM in the hot path
```

## Repo layout (template)

```
docs/
  epics/YOUR-EPIC.md          # phases R0, R1, … with ✅ criteria
  MASTER_TASK_TRACKING.md     # dated one-liners; human scan surface
  research/MEMORY_AND_LEARNING.md  # artifact chain + Hermes vs file memory
handoffs/<area>/Handoff_*.md  # per-slice “what shipped, how to re-run”
data/state/                   # gitignore runtime; regenerate via scripts
  *_latest.json               # “current answer” for agents
  *_runs.jsonl                # append-only audit trail
config/                       # versioned policy (gates, knob maps)
<module>/research/            # scenario packs, harnesses, isolation tests
<module>/scripts/             # cron-facing entrypoints
```

## The delivery loop (repeat per slice)

1. **Define slice** in epic: scope, success command, explicit “does not” list (no live orders, no prod config without approval).
2. **Build smallest harness** that produces a **verifiable artifact** (JSON + exit 0), not a chat summary.
3. **Isolation test** `test_isolation_<feature>.py` — fast, no network, no side effects; run before every commit claim.
4. **Handoff** one markdown file: commands, paths, known blockers.
5. **MASTER** one dated line.
6. **Optional cron** `cronjob` for weekly/daily — `no_agent: true` for watchdogs; self-contained prompt for analyst jobs.
7. **Patch skill** pitfalls when something burned you twice.

## Hermes tool discipline

| Task | Tool |
|------|------|
| 3+ independent reads/searches | Batch in one turn (parallel tool calls) |
| Mechanical multi-step fetch/transform | `execute_code` + `hermes_tools` |
| Heavy reasoning subtask | `delegate_task` (background); **verify** side effects yourself |
| Durable work after `/new` | `cronjob` or scripts — not background delegate |
| Targeted code edit | `patch` / `write_file` — not `sed` in terminal |
| Math, dates, git state | `terminal` — never from memory |

**Finish rule:** Deliverable = **tool output**, not a plan. If blocked, say so; never invent results.

## Promotion gates (generic pattern)

Before any “turn this on in production”:

```python
# promotion_gates.py pattern
def evaluate_promotion_gates(leaderboard: dict) -> GateResult:
    # failures: negative primary metric, missing baseline beat, calendar mismatch, etc.
    ...
```

- Proposals must cite `run_id` from jsonl ledger.
- Ingest script refuses when gates fail.

## Shadow / overlay pattern

- **Never** patch production config on disk for experiments.
- Write `data/state/*_overlay.json`; runner merges in-memory.
- Drift check compares live metrics to backtest expectation → auto rollback flag.
- Regime or A/B: **detect** → **map** to knob set from scorecard → swap overlay only.

## Scenario / optimization pattern (optional but powerful)

| Piece | Purpose |
|-------|---------|
| `scenarios/*.json` | Declarative knob matrix |
| `run_*_leaderboard.py` | Rank configs → `*_latest.json` + jsonl |
| `compare-production` | Honest overlap with live period |
| `run_regime_scorecard.py` | Bull/bear/flat windows — don’t trust one window |
| `analyst_narrative.py` | Brief text from files, not vibes |

## Persona snippet (paste into SOUL.md or project doc)

See `references/persona-snippet.md` in this skill folder.

## Bootstrap prompt (first session on a new repo)

Copy `QUICK_START_ORCHESTRATOR_PROMPT.md` in this folder; replace `{{PROJECT}}` and `{{EPIC}}`.

## Verification checklist (agent self-audit)

- [ ] Epic slice has explicit success command
- [ ] Isolation test exists and was run this session
- [ ] Handoff + MASTER updated if user-facing behavior changed
- [ ] No secrets in git; state files gitignored where appropriate
- [ ] Promotion path goes through gates + shadow
- [ ] Skill pitfalls updated if new failure mode

## Pitfalls (seed list — extend via `skill_manage(patch)`)

- **Compaction:** Latest user message wins; re-read files after context summary.
- **Bull-only winners:** Stress multiple time windows before trusting optimization.
- **Calendar mismatch:** Pack dates ≠ live period → separate headlines; no fake “beats production.”
- **Subagent reports:** Treat delegate summaries as self-reports; verify URLs/paths/HTTP yourself.
- **Cross-profile edits:** Don’t patch another Hermes profile’s skills without explicit user ask.

## Installing for another Hermes user

```bash
mkdir -p ~/.hermes/skills/platform-orchestrator-loop
cp SKILL.md ~/.hermes/skills/platform-orchestrator-loop/
# Optional: copy QUICK_START_ORCHESTRATOR_PROMPT.md to project docs/
```

In chat: `skill_view(name='platform-orchestrator-loop')` before large build sessions.

## Reference implementation

In the [crypto-trading-bot](https://github.com) repository: `docs/epics/ANALYST-OPT_EPIC.md` and `skills/crypto-analyst-scenario-run/` — concrete names for every abstract step above.