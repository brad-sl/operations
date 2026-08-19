# Free / Cheap Agent Routing Strategy — Hermes + Kanban

**Date:** 2026-07-20  
**Scope:** LLM / agent token surface only (Surface B). Social data (X / Apify) is covered in `COST_REDUCTION_EXECUTION_PLAN_2026-07-20.md` and sentiment research pack.  
**Goal:** Route day-to-day agent work to **free tiers, subscription-backed OAuth capacity, and `no_agent` scripts** so ops quality stays high while pushing **combined stack toward ≤$15/day** (stretch ≤$10).  
**Status:** Research + policy design only. **No live config changes** in this document.

**Pack siblings:**
- `docs/research/COST_REDUCTION_EXECUTION_PLAN_2026-07-20.md` — umbrella plan
- `docs/research/COST_60D_ATTRIBUTION_2026-07-20.md` — $ attribution
- `docs/research/FREE_SENTIMENT_OPTIONS_2026-07-20.md` — data surface

**Standing playbooks (do not regress):**
- `hermes-operations` → Grok cost playbook, model-routing pack, OR Sonnet trap
- Memory: **OR = aux flash only; set key daily limit**
- X sentiment: **2×/day 08:50/20:50 PT** only

---

## 1. Executive summary

| Finding | Implication |
|---------|-------------|
| Most Hermes crons are already **`no_agent`** | Good baseline; remaining burn is **interactive Telegram**, **daily ops-triage agent**, and **Kanban `--goal` 25-turn workers** |
| Default + delegation = `grok-composer-2.5-fast` (xai-oauth) | High-quality coding path but **long sessions ≈ 95k in/call** dominate token totals in `agent.log` |
| Profiles crypto-* = `grok-build-0.1` (xai-oauth) | Prefer **build** for all Kanban / long tool loops; keep composer for short interactive chat |
| code-reviewer = OpenRouter `moonshotai/kimi-k2.7-code` | Paid when used; OK as **gated gate**, not volume worker |
| OpenRouter key **`limit: null`** | **No auto stop** on runaway day — set daily cap immediately |
| Host: Core2 Duo E8400, 2 CPU, ~10 GB RAM, **no NVIDIA driver, no Ollama, no llama.cpp** | **Local free models are not day-1 capacity** — Phase 2+ only |
| SuperGrok / xai-oauth | Treat as **limited free/sub quota**, not unlimited API |

**Biggest cheap wins (effort × impact):**
1. Kanban: **stop default `--goal --goal-max-turns 25`** on every ops card  
2. Convert **`phase6-ops-triage-daily`** to script-first + agent only on medium/high  
3. Telegram: **session hygiene** (`/new` when in≫40k; demote flagship after hard tasks)  
4. OpenRouter **hard daily key limit** + keep main off OR  
5. Align `delegation.model` → `grok-build-0.1` for multi-turn children  

---

## 2. What counts as “free” in this stack (2026-07)

### 2.1 Tier map (operational definition)

| Tier | Meaning for us | Examples | Reliability for ops |
|------|----------------|----------|---------------------|
| **F0 — True free / $0 tokens** | No LLM billed | `no_agent` scripts, rule engines, `ops_engineer.py`, intel report generator (deterministic), RSI/dashboard refreshers | **Production default** |
| **F1 — Sub / OAuth included** | Subscription-backed capacity; still finite rate + soft overage risk | xAI OAuth: `grok-composer-2.5-fast`, `grok-build-0.1`, occasional `grok-4.5` | **Primary agent path** — treat as budgeted free, not infinite |
| **F2 — Metered free remote** | $0/token but hard RPD/RPM; queue/rotate | OpenRouter `:free` models (~22 free IDs as of 2026-07-20); Gemini AI Studio free Flash RPD caps | **Aux / titles / triage drafts only** — not trading or unsupervised fix loops |
| **P1 — Cheap paid** | Cents–low $ | OR `google/gemini-2.5-flash` aux; kimi code-reviewer sparingly | Aux + review gates |
| **P2 — Expensive paid** | Avoid for volume | Claude Sonnet/Opus via OR; long `grok-4.5` tool loops; 25-turn goal workers on medium issues | **Ban for main/Kanban volume** |

### 2.2 Provider reality checks (researched 2026-07-20)

**xAI / Grok (OAuth + API)**
- Consumer SuperGrok (~$30/mo) raises app limits; **API/OAuth agent usage is still capacity- and policy-bound** — treat OAuth as F1, not infinite F0.
- Public API list prices (reference only; OAuth may differ): flagship Grok 4.5 ~$2/$6 per 1M in/out; Build-class models exist for coding agent work.
- Rate tiers on API spend exist (Tier 0+); console is source of truth.
- **Policy:** volume = `grok-composer-2.5-fast` or `grok-build-0.1`; escalate to `grok-4.5` then **demote**.

**OpenRouter**
- Free models: **20 RPM**; **50 RPD** if credits purchased &lt; $10 lifetime; **1000 RPD** after ≥$10 credits.
- Live free IDs include (rotates): `openrouter/free`, `tencent/hy3:free`, `nvidia/nemotron-3-* :free`, `poolside/laguna-*:free`, `cohere/north-mini-code:free`, `google/gemma-4-*:free`, `openai/gpt-oss-20b:free`, etc.
- **This account (live probe):** `limit: null`, `usage_daily` ≈ $0.07, monthly paid usage small; **BYOK history large** — key is **not free-tier locked** but also **uncapped**.
- Memory rule: **Sonnet-as-main burned ~$500 (Apr 2026)**. OR stays **aux flash only**.

**Gemini (Google AI Studio)**
- Free tier still exists for Flash-class models with tight **RPM + RPD** (order of ~10 RPM / hundreds–1500 RPD depending on model/docs snapshot — **confirm in AI Studio rate-limit UI**).
- Not currently wired as Hermes main; optional F2 for titles/compress if OR flash restricted.
- No `GEMINI_API_KEY` observed in Hermes env inventory today (aux goes through OR).

**Ollama / llama.cpp / local**
- **Not installed** on this host (`ollama` missing; no llama-cli/server on PATH).
- **NVIDIA-SMI fails** (no driver); CPU is **Intel Core2 Duo E8400 @ 3.0 GHz, 2 cores, ~9.6 GiB RAM**.
- Verdict: **local F0 agent is not viable for interactive Telegram or Kanban** without hardware upgrade. Optional later: tiny CPU model for title-only via llama.cpp (slow, best-effort).

### 2.3 Host inventory (2026-07-20)

| Check | Result |
|-------|--------|
| GPU | nvidia-smi: driver not communicating |
| Ollama | not installed |
| llama.cpp | not found |
| CPU / RAM | 2× Core2 Duo, ~10 GB |
| Hermes default | `grok-composer-2.5-fast` / `xai-oauth` |
| delegation | same composer / xai-oauth; `max_concurrent_children=3`; `max_iterations=50` |
| auxiliary | OR `google/gemini-2.5-flash` (vision, compression, approval, titles) |
| fallback | `claude-haiku-4.5` (outage only — keep that way) |
| OpenRouter key limit | **`null` — fix** |

---

## 3. Day-to-day usage patterns → route

### 3.1 Live schedule inventory (token relevance)

**Already F0 (`no_agent`) — keep:**

| Job | Schedule | Script |
|-----|----------|--------|
| Daily Kanban Backup | 03:00 | `backup-kanban.sh` |
| rsi-15min-refresher | */15 | `refresh_rsi_prices.py` |
| daily-git-hermes-management | 04:30 | `git-daily-management.sh` |
| Phase6 Analyst OPT Weekly | Sun 04:00 | `phase6/research/run_analyst_opt_weekly.sh` |
| Phase6 Shadow Drift Monitor | 05:00 | `phase6/research/run_shadow_drift_check.sh` |
| twice-daily-trading-intelligence-v2 | 09:00, 21:00 | `cron_intelligence_telegram.sh` (deterministic report) |
| dashboard-live-state-5m | */5 | `refresh_dashboard_live_state.sh` |
| ops-issue-loop | 07:15, 13:15, 19:15 | `run_ops_issue_loop.sh` (**script is free; dispatch may spawn paid workers**) |
| system: ops_engineer.py | */30 | deterministic monitor |
| system: monitors / sentiment refresh | various | data plane |

**Still agent / token-heavy:**

| Job / pattern | Cadence | Cost shape | Target route |
|---------------|---------|------------|--------------|
| **phase6-ops-triage-daily** | 06:00 daily | Full skill agent, multi-tool | **F0 script first**; agent only if findings ≥ medium |
| **Kanban workers** (crypto-engineer / orchestrator) | on dispatch | Profile `grok-build-0.1`; **`--goal` 25 turns** default in ops_issue_loop | High only → goal 8–12; medium → single-shot; overnight block medium |
| **Telegram main chat** | continuous | composer-fast, huge context | F1 short sessions; `/new` hygiene; escalate/demote |
| **code-reviewer** | on gate tasks | OR kimi (P1) | Gate only; not auto on every card |
| **crypto-monitor profile** | rarely scheduled | OR `google/gemini-2.0-flash` | Prefer F0 ops_engineer; monitor profile = optional |
| **RSI vs StochRSI review** | once 2026-07-24 | agent once | Accept F1 once; then archive |
| **delegate_task children** | ad hoc | still composer-fast | Switch to **build-0.1** |

### 3.2 Observed load signals (from sister pack + live)

- Busy days in `agent.log`: **15–45M tokens/day**, overwhelmingly `grok-composer-2.5-fast`.
- Quieter days: ~3–5M tokens.
- Kanban board currently **0 open tasks** in SQLite status breakdown at probe time, but ops loop had **1 in_progress** medium SL card with worker path active earlier same day.
- ops_issue_loop **always** appends `--goal --goal-max-turns 25` unless `--no-goal` (see `scripts/phase6/ops_issue_loop.py`).

---

## 4. Routing matrix (task class → free / cheap / paid)

Use this as the **standing policy** for humans + agents + crons.

| Task class | Examples | Route | Model / mechanism | Max turns / notes |
|------------|----------|-------|-------------------|-------------------|
| **T0 Routine ops health** | process up?, stale RSI, dual-write, dashboard port | **F0** | `ops_engineer.py`, monitors, audit scripts | 0 LLM |
| **T0 Signal refresh** | RSI 15m, dashboard 5m, sentiment 2× | **F0** | existing no_agent crons | 0 LLM |
| **T0 Intelligence brief** | twice-daily Telegram brief | **F0** | `generate_trading_intelligence_report*` + `hermes send` | 0 LLM (persona flavor only) |
| **T0 Research OPT / shadow** | weekly OPT, drift check | **F0** | shell + Python research scripts | Agent only if script red 2× |
| **T1 Ops discovery** | morning “what broke?” | **F0→F1** | Prefer `scripts/phase6` discovery script writing `ops_triage.md`; **agent skill only if open medium/high** | Agent ≤12 turns if needed |
| **T1 Ticket promote / close** | registry, gh issue | **F0** | `ops_triage_tasks.py`, `ops_issue_loop.py` | 0 LLM |
| **T2 Ops fix — high** | runner down class, missing exchange SL material $, AttrError blocking rebalance | **F1 goal** | Kanban → `crypto-engineer` / `grok-build-0.1` | **goal max 12** (not 25); skills forced |
| **T2 Ops fix — medium** | git ATTENTION, stale cron, one-off audit | **F1 single-shot** | Kanban **without `--goal`** or max 6 turns; human-hours 07–19 PT | No overnight auto-spawn |
| **T2 Ops fix — low** | docs, unpushed commits | **F0 or queue** | No auto Kanban; human or weekly batch | — |
| **T3 Implementation epic** | multi-file features | **F1** | default chat or engineer profile build/composer; plan → small cards | Prefer card size ≤1 session |
| **T3 Architecture thrash** | multi-system design | **F1 escalate** | `/model grok-4.5` then demote | Short; write plan to disk |
| **T4 Code review gate** | PR / handoff review | **P1** | `code-reviewer` + kimi | One-shot `-Q`; never main |
| **T5 Aux (vision, compress, titles, approval)** | gateway internals | **P1/F2** | OR `gemini-2.5-flash`; optional `:free` for titles only | Never trading decisions |
| **T5 Fallback outage** | xAI down | **P1** | Haiku fallback only | Not quality upgrade path |
| **T6 Marketing / creative profiles** | ad-copy, SEO, etc. | **F1/F2** | Separate from trading; prefer off-peak; free OR only if non-critical | Cap concurrency 1 |
| **T7 Trading decisions** | size, entries, SL policy | **F0 rules + human** | Runner + config; agents propose only | No free-model autonomy |

### 4.1 Model preference order (when an LLM is required)

1. **`no_agent` script** if the procedure is checklistable  
2. **`grok-build-0.1` + xai-oauth** — multi-turn tools, Kanban, implementers  
3. **`grok-composer-2.5-fast` + xai-oauth** — interactive coding chat (short context)  
4. **`grok-4.5` + xai-oauth** — rare hard problems; demote after  
5. **OR `google/gemini-2.5-flash`** — aux only  
6. **OR kimi (code-reviewer)** — review gates  
7. **OR `:free` / `openrouter/free`** — titles, draft triage prose, non-critical experiments  
8. **Never** Sonnet/Opus as main or Kanban worker via OR  

---

## 5. Kanban policy (crypto-bot-project)

### 5.1 Goal mode rules

| Priority | Auto-create from ops-issue-loop | `--goal` | `goal-max-turns` | Auto-dispatch |
|----------|----------------------------------|----------|------------------|---------------|
| **high** (rank ≤1) | yes | **yes** | **12** (cap; was 25) | yes 07:00–21:00 PT; overnight only if label `critical` |
| **medium** (rank 2–3) | yes | **no** (single-shot / default worker) | n/a or ≤6 if goal forced | **yes daytime only**; **block overnight 22:00–07:00 PT** |
| **low** (rank ≥4) | optional / batch | no | — | human promote only |

**Code touchpoint (do not apply in this research pass):**  
`scripts/phase6/ops_issue_loop.py` → `_kanban_create` always does `--goal` + `25` unless `--no-goal`.

**Recommended behavior:**
```text
default: --no-goal
if priority_rank <= 1 and not overnight_quiet_hours:
    --goal --goal-max-turns 12
elif priority_rank <= 3 and daytime:
    single-shot worker (no --goal)
else:
    create card ready but do not dispatch until daytime or human
```

Cron wrapper options:
```bash
# daytime ticks — allow dispatch, no default goal
ops_issue_loop.py run --gh-assign --dispatch --no-goal

# optional: env OPS_GOAL_HIGH_ONLY=1 once implemented
```

### 5.2 Concurrency

| Knob | Current | Target |
|------|---------|--------|
| `delegation.max_concurrent_children` | 3 | **1–2** for cost weeks |
| Kanban simultaneous running ops cards | unbounded by policy | **max 1** overnight; **max 2** daytime |
| `max_runtime` on ops cards | 45m | keep 45m high; **30m** medium |
| Spawn depth | 1 | keep 1 (no nested swarms for ops) |

### 5.3 Skills force (always on ops fix cards)

Keep forcing via `--skill` (already):
- `phase6-ops-triage` / trading-bot-operations references as needed  
- `delegation-sanity-check` mindset in card body  
- domain skills from router table in `docs/OPS_ISSUE_LOOP.md`

**Do not** attach marketing/creative skills to ops cards.

### 5.4 Assignee routing (unchanged, cost-aware)

| Pattern | Profile | Model (profile pin) |
|---------|---------|---------------------|
| SL / rebalance / runner / dashboard | `crypto-engineer` | `grok-build-0.1` |
| docs / MASTER / boundary | `crypto-orchestrator` | `grok-build-0.1` |
| review gate only | `code-reviewer` | kimi (P1) — **manual** |
| never auto | marketing-* | — |

### 5.5 Swarm / decompose

- **Ban auto-swarm** on ops-issue-loop created cards.  
- `hermes kanban decompose` / swarm only for human-initiated epics.  
- Decomposer aux model stays auto/flash — do not point at Sonnet.

---

## 6. Cron policy — agent → no_agent

### 6.1 Conversion candidates

| Job | Today | Target | How |
|-----|-------|--------|-----|
| **phase6-ops-triage-daily** | Agent + skill `phase6-ops-triage` | **F0 primary** | New `scripts/phase6/run_ops_triage_discovery.sh` encoding Read→table write from skill procedure; Telegram only if medium/high rows; optional second job: agent if `ops_triage.md` has open medium/high |
| ops-issue-loop | no_agent script (good) | keep | Change flags: `--no-goal`; conditional dispatch |
| twice-daily intelligence | no_agent (good) | keep | Already deterministic + cache |
| RSI / dashboard / git / shadow / OPT | no_agent (good) | keep | Fix script errors without agent crons |
| RSI vs StochRSI once | agent once | accept once | After run: disable/archive |
| crypto-monitor agent cron | yaml exists; not in active list | **do not enable** as agent | Rely on ops_engineer + monitors |
| Any future “LLM summary every N min” | — | **reject** | Summarize offline or on demand |

### 6.2 Two-stage morning triage (recommended design)

```
06:00  no_agent: run_ops_triage_discovery.sh
         → writes data/state/ops_triage.md
         → exit 0 + OPS_TRIAGE_OK if no medium/high
         → exit 10 if medium/high open

06:05  agent job (optional, only if exit 10 or file flag):
         short prompt: "load ops_triage.md; promote missing registry rows; do not fix"
         max ~8–12 turns, grok-build-0.1 profile or default with skill force
```

Until the discovery script exists, **thin the agent prompt** to: read sources → max 3 findings → write file → stop (no promote loops, no Kanban create inside triage — leave to ops_issue_loop).

### 6.3 System crontab hygiene (LLM-adjacent)

- `ops_engineer.py` every 30m = **correct** (F0). Do not reintroduce agent ops every 10m.  
- Do not schedule Hermes agent “health chats.”  
- Marketing/creative profiles: no always-on agent crons.

---

## 7. Telegram chat cost control

Long Telegram sessions are the **#1 suspected LLM burn** when agent.log shows ~100k input tokens/call.

| Pattern | Do | Don't |
|---------|----|-------|
| Session length | `/new` after major deliverable or when context feels heavy; prefer handoff files | Infinite thread across days |
| Model | Stay on composer-fast; `/model grok-4.5` only for hard debug then demote | Leave flagship on overnight |
| Scope | One problem per session; point at paths + scripts | “Also while you’re here…” multi-epic |
| Ops alerts | Script → short Telegram (ops_engineer / triage OK line) | Full agent re-diagnose every alert |
| Gateway | Single Telegram poller (Hermes default only) | Multi-profile gateways / OpenClaw dual poll |
| Tools | Prefer terminal scripts that dump state files | Paste entire logs into chat repeatedly |
| Compression | Keep aux flash; threshold 0.70; hygiene_hard_message_limit 2500+ | hygiene 400 (forces thrash compact) |
| Subagents | `max_concurrent_children` 1–2; build-0.1 | 3× parallel composer children on chat |

**User-facing micro-policy (copy for MEMORY if desired):**
1. Ops questions first → “run ops_engineer / triage script” before full agent deep dive.  
2. After any Kanban epic completes → new chat.  
3. Never “set main to Sonnet to go faster.”

---

## 8. OpenRouter guardrails (mandatory)

| Control | Current | Required |
|---------|---------|----------|
| Main / delegation provider | xai-oauth ✓ | keep |
| Aux models | gemini-2.5-flash ✓ | keep; no upgrade to Pro/Sonnet |
| Key **daily limit** | **`null`** | Set e.g. **$2–5/day** in OR dashboard (hard stop) |
| Free models for main | unused | Optional titles only; never Kanban implementer |
| code-reviewer | kimi | Review-only; no auto-dispatch on every ops card |
| fallback | Haiku | outage only |

**Probe command (safe):**
```bash
curl -sS https://openrouter.ai/api/v1/key \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" | jq '{limit, limit_remaining, usage_daily, usage_monthly}'
```

---

## 9. Free remote models — approved uses only

| Use | Model suggestion | Not for |
|-----|------------------|---------|
| Title generation | `openrouter/free` or gemma-4 free / flash | Code edits |
| Draft GH issue body | free coder mini (north-mini-code / laguna-xs) | Live runner changes |
| Compress if flash 429 | gemini free / flash lite | Long agent loops (RPD death) |
| Experiment / eval | rotate free IDs | Production SL / exchange |

**Caveats:** free endpoints rotate (“going away” dates), train-on-inputs policies vary (Poolside free notes training), tool-calling quality uneven — **never sole production implementer**.

---

## 10. Seven-day execution plan (effort × impact)

Target: **LLM surface contribution** compatible with **≤$15/day stack** (with sentiment pack).  
**Read-only note:** phases below are for human/agent implementation sessions — this research file alone changes nothing live.

### Day 0–1 — Measure + hard stops (effort: S, impact: XL)

| # | Action | Effort | Impact | Owner hint |
|---|--------|--------|--------|------------|
| 0.1 | Confirm $: xAI/SuperGrok, OR, X, Apify (7d) | S | XL | Brad |
| 0.2 | Set OpenRouter **key daily limit** ($2–5) | S | XL | Brad dashboard |
| 0.3 | Ship `llm_token_daily_rollup.py` from agent.log → `data/state/llm_token_daily.jsonl` | M | H | agent |
| 0.4 | MEMORY one-liner: Kanban no default goal; OR limit set | S | M | agent |

**Exit:** primary burn surface labeled; OR cannot runaway.

### Day 1–2 — Stop agent bleed (effort: M, impact: XL)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 1.1 | Patch ops_issue_loop: **default `--no-goal`**; goal only rank≤1; max turns **12** | M | XL |
| 1.2 | Cron wrapper: `run --gh-assign --dispatch --no-goal`; document overnight no-dispatch for medium | S | H |
| 1.3 | `hermes config set delegation.model grok-build-0.1` (default profile) | S | H |
| 1.4 | Thin phase6-ops-triage-daily prompt or dual-stage flag file | M | H |
| 1.5 | Telegram: after any long fix, `/new`; demote if on 4.5 | S | H |

**Exit:** no new 25-turn medium cards; delegation ≠ composer for children.

### Day 2–3 — F0 triage script (effort: M–L, impact: H)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 2.1 | Implement discovery script from skill procedure (pgrep, tails, hermes cron list, write ops_triage.md) | L | H |
| 2.2 | Wire Hermes cron: no_agent discovery @06:00; conditional agent @06:05 | M | H |
| 2.3 | Sync `~/.hermes/scripts/` copies | S | M |
| 2.4 | Verify: dry run produces table matching skill quality bar | M | H |

**Exit:** most mornings = **zero LLM** for triage.

### Day 3–4 — Concurrency + profile polish (effort: S–M, impact: M–H)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 3.1 | `max_concurrent_children` → 1 or 2 | S | M |
| 3.2 | Kanban policy doc in OPS_ISSUE_LOOP.md | S | M |
| 3.3 | code-reviewer: confirm not on auto path; kimi only on explicit review cards | S | M |
| 3.4 | crypto-monitor: leave disabled as agent; ops_engineer owns ticks | S | M |
| 3.5 | Optional: aux titles → `:free` if flash spend annoying | S | L |

### Day 4–5 — Quality gates under cheap routing (effort: M, impact: H)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 4.1 | Isolation test: high SL card still completes with goal-12 | M | H |
| 4.2 | Medium card completes single-shot or human follow-up SLA &lt;24h | M | H |
| 4.3 | Compare token rollup D0 vs D4 (target ≤5M tokens busy day) | S | H |
| 4.4 | Ensure ops quality: no skipped medium SL (registry + GH still promoted) | M | XL |

### Day 5–7 — Stabilize + optional free tier experiments (effort: M, impact: M)

| # | Action | Effort | Impact |
|---|--------|--------|--------|
| 5.1 | Weekly review of OR usage_daily + xAI feel | S | M |
| 5.2 | If still hot: force all Kanban to build-0.1; composer chat-only | S | H |
| 5.3 | Experiment free model for **title_generation only** (1 day) | S | L |
| 5.4 | Document go/no-go on local LLM (requires hardware — default **no**) | S | L |
| 5.5 | Align with sentiment pack cutover decisions (separate $) | M | XL stack |

**Day-7 success criteria**

| Metric | Target |
|--------|--------|
| Busy-day agent.log tokens | ≤ **5M** (from 15–45M peaks) |
| OR key limit | non-null; daily &lt; cap |
| Ops triage LLM days/week | ≤ **2–3** agent runs (rest F0) |
| Goal-25 medium cards | **0** |
| Concurrent overnight Kanban workers | **0** unless critical |
| Ops quality | medium/high still in registry + GH within 24h; no silent naked SL |

---

## 11. Risk register

| Risk | Mitigation |
|------|------------|
| Single-shot workers leave medium issues open | Daytime re-dispatch; human Telegram nudge; promote SLA |
| F0 triage misses subtle bugs | Keep weekly human skim; agent fallback on exit 10 |
| grok-build quality &lt; composer for some fixes | Allow per-card override to composer; measure reopen rate |
| Free OR models poison tool loops | Never assign `:free` as Kanban implementer |
| SuperGrok soft caps / OAuth throttle | Queue work; no parallel 3 children; prefer scripts |
| Cost moves to X/Apify while LLM drops | Sister packs; don’t declare victory on LLM alone |
| Local LLM fantasy delays real cuts | Explicit: **no GPU → skip local until hardware** |

---

## 12. Implementation checklist (copy into tickets)

When implementing (separate session; not this file):

- [ ] OR dashboard: set daily key limit  
- [ ] `ops_issue_loop.py`: goal policy by priority + hours  
- [ ] `run_ops_issue_loop.sh`: pass `--no-goal` (or new flags)  
- [ ] Sync `~/.hermes/scripts/phase6/run_ops_issue_loop.sh`  
- [ ] `docs/OPS_ISSUE_LOOP.md` policy section update  
- [ ] default `delegation.model` → `grok-build-0.1`  
- [ ] optional `delegation.max_concurrent_children` → 2  
- [ ] F0 `run_ops_triage_discovery.sh` + cron split  
- [ ] `llm_token_daily_rollup.py` + optional Telegram one-liner  
- [ ] MEMORY.md: routing one-pager  
- [ ] Verify: `hermes cron list` + `crontab -l` + OR key JSON  

---

## 13. Appendix A — Profile model pins (live)

| Profile | Provider | Default model |
|---------|----------|---------------|
| default | xai-oauth | grok-composer-2.5-fast |
| crypto-engineer | xai-oauth | grok-build-0.1 |
| crypto-analyst | xai-oauth | grok-build-0.1 |
| crypto-orchestrator | xai-oauth | grok-build-0.1 |
| code-reviewer | openrouter | moonshotai/kimi-k2.7-code |
| crypto-monitor | openrouter | google/gemini-2.0-flash |

## 14. Appendix B — Quick decision tree

```
Need automation?
├─ Checklistable from logs/state/scripts? → no_agent script (F0)
├─ Discover only? → F0 triage script; agent if medium/high
├─ Fix production ops?
│  ├─ high + daytime → Kanban goal ≤12, build-0.1
│  ├─ medium + daytime → Kanban single-shot, build-0.1
│  └─ overnight medium → queue card, no worker
├─ Interactive coding with Brad → composer-fast, short session
├─ Hard architecture → grok-4.5 briefly → demote
├─ Review gate → code-reviewer kimi once
└─ Titles/compress → flash aux; free only if needed
Never → OR Sonnet main, free model unsupervised exchange changes, 25-turn medium overnight
```

## 15. Appendix C — Evidence commands (re-run anytime)

```bash
# Crons
hermes cron list
crontab -l

# Models
python3 -c "import yaml; print(yaml.safe_load(open('$HOME/.hermes/config.yaml'))['model'])"
for p in crypto-engineer crypto-analyst crypto-orchestrator code-reviewer; do
  echo $p: $(python3 -c "import yaml; print(yaml.safe_load(open('$HOME/.hermes/profiles/$p/config.yaml'))['model'])")
done

# Local free capacity
command -v ollama; nvidia-smi; nproc; free -h

# OpenRouter cap
curl -sS https://openrouter.ai/api/v1/key -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('limit'), d.get('usage_daily'))"

# Ops queue
python3 /home/brad/projects/crypto-trading-bot/scripts/phase6/ops_issue_loop.py status
```

---

## Document control

| Ver | Date | Note |
|-----|------|------|
| 1.0 | 2026-07-20 | Initial free/cheap routing matrix from live inventory + provider research; no live config edits |

**Related skills:** `hermes-operations`, `ops-engineer`, `phase6-ops-triage`, `kanban-orchestrator`  
**Related code:** `scripts/phase6/ops_issue_loop.py`, `scripts/ops/ops_engineer.py`, `docs/OPS_ISSUE_LOOP.md`
