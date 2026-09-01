---
name: hermes-operations
description: Best practices for working with Hermes CLI, cron jobs, gateway, and persistent agent workflows. Captures execution preferences and common pitfalls.
version: 1.0.0
---

# Hermes Operations

## Execution Preference
**Strong user preference:** When possible, run commands directly using the `terminal` tool instead of telling the user to copy-paste and run them. Only give the user commands when absolutely required (e.g., long-running services like `hermes gateway start`).

**Telegram delivery (Brad 2026-08-28):** Long fenced mega-scripts **split into multiple bubbles** and become unusable. Prefer: (1) fix agent shell and run yourself, (2) short ≤~15-line paste blocks, (3) a single host path script the user can `python3 path/to/script.py`. Never dump multi-hundred-line inline Python on Telegram as the primary plan.

**Aggressive go-ahead:** If Brad says kick off / no need to wait for approval on a planned gate chain, **execute** end-to-end (e.g. venue probe → economics → MVP docs) without re-asking mid-stream. Still no silent live product enable or large capital moves beyond agreed probe micro-caps.

**Plain English for gates/PRDs:** Lead with implications (Hold vs DeRisk, E1, venue A/B/C, G1–G3) — opaque shorthand without translation frustrates Brad.

## Terminal backend (local vs SSH) — agent shell broken

**Symptom:** Every `terminal` / host `execute_code` fails with:
`ValueError: SSH environment requires ssh_host and ssh_user to be configured`

**Cause (not Linux permissions):** `terminal.backend: ssh` in `~/.hermes/config.yaml` without `terminal.ssh_host` / `terminal.ssh_user` (or `TERMINAL_SSH_*` env). Agent tools try SSH; Brad's interactive shell on the box still works fine.

**Same-host setup (Telegram gateway + trade host on one Linux box — Brad default):**
```bash
hermes config get terminal.backend
hermes config set terminal.backend local
# clear leftovers if present
grep TERMINAL_SSH ~/.hermes/.env || true
systemctl --user restart hermes-gateway
# prove from a *new* agent turn: whoami; pwd; hermes config get terminal.backend
```

**True remote SSH backend** only when agent process ≠ trade host:
```bash
hermes config set terminal.backend ssh
hermes config set terminal.ssh_host <host>
hermes config set terminal.ssh_user <user>
# passwordless key auth required
```

**Pitfalls:**
- Desktop Windows SSH client ≠ gateway `terminal.backend` — different path.
- Gateway restart drops in-flight tool state; re-check `pgrep -af phase6.core.phase6_runner` (runner may have been under gateway cgroup).
- Cron probe saying "gateway not running" can be stale while `systemctl --user status hermes-gateway` is active — trust systemd/pgrep.
- Do **not** invent "permissions" narratives when the error names missing `ssh_host`/`ssh_user`.

Detail: `references/terminal-backend-local-vs-ssh.md`.

## Independent review crons (frontier pass)
- One-shot `cronjob` + fresh session + stronger model for adversarial PRD review; write full report path + short exec brief to origin.
- If stream dies (`Codex stream produced no SSE…` / empty), **do not leave empty**: produce the adversarial report in-session (note independence limits) and/or reschedule on OpenRouter alternate.
- Pin `provider`+`model`; toolsets `file,terminal` (+`web`); `workdir` = project root.

## Profiles for one-shot tasks (alternate model)

Profiles are separate Hermes homes (`~/.hermes/profiles/<name>/`). Each can pin its own `model.provider` + `model.default`.

### Cheap multi-bot fleet (vs Grok Bot) — 2026-08-31

When Brad wants a **full agent team** without flagship-everywhere cost:

- Prefer **Hermes profiles + Desktop Bot Mode** (`hermes-bots` plugin) over a separate Grok Bot product.
- Pin **leaf** marketing profiles to OpenRouter **Gemini Flash**; keep `default` on Composer; mid-tier only on orchestrator.
- Biz SSOT: `~/projects/revenue-ops/docs/MASTER_REVENUE.md` + Kanban `revenue-ops`.
- Playbook: `marketing-consultancy-team` → `references/revenue-ops-hermes-desk.md`.
- **Do not** answer "Grok Bot too expensive" by setting global `delegation.model: grok-4.5` for SEO leaves.

**Pattern (coding gates):** Parent session uses fast default model + `delegate_task` for implementers; **deploy / code-review gate** runs as a one-shot in another profile:

```bash
hermes profile alias code-reviewer    # creates ~/.local/bin/code-reviewer → hermes -p code-reviewer
code-reviewer config set model.provider openrouter
code-reviewer config set model.default moonshotai/kimi-k2.7-code
code-reviewer chat -Q -q '<self-contained packet>' -t file,terminal
```

`-Q` = quiet/non-interactive for scripts. Do not conflate this with `delegation.model` (global for all subagents). See `agent-delegation` → `references/hermes-hybrid-implementer-profile-reviewer.md`.

## Cron Job Creation
Hermes cron creation is finicky with argument parsing. Preferred pattern:

1. Try the clean one-liner first.
2. If argument parsing fails, fall back to writing a YAML file in `~/.hermes/cron/<name>.yaml`.
3. The gateway must be running (`hermes gateway start`) for scheduled jobs to execute.

## Using the `cronjob` Agent Tool (cronjob.create)
When using the agent's `cronjob` tool (distinct from raw `hermes cron` CLI):

- **schedule is MANDATORY for action="create"**. Always pass it explicitly as a named parameter:
  - RSI refresher: schedule="*/15 * * * *"
  - Sentiment: schedule="*/30 * * * *"
- Omitting `schedule` produces the exact error "schedule is required for create" and triggers repeated-identical-call loops that hit max-iterations.
- Scripts must be placed in `~/.hermes/scripts/` (the tool resolves relative paths from there). Use `cp <project-script> ~/.hermes/scripts/` before create.
- For env-sensitive scripts (NumPy on constrained CPUs, sentiment with Apify): create a thin `.sh` wrapper in `~/.hermes/scripts/` that does `export OPENBLAS_CORETYPE=GENERIC; cd /project; python3 run_....py` and point the cron at the `.sh`.
- After create, always verify with `hermes cron list` (via terminal tool) — the list is the source of truth.
- Long-running external calls (Apify Reddit/X sentiment) can timeout in interactive verification; the cron itself will execute the script in its own context.

## Stale no_agent Script Copies + Project Package Import Side Effects
For `no_agent: true` cron jobs that reference a `script:` (e.g. report generators, refreshers) and import project modules:

**Core rule**: The file at `~/.hermes/scripts/<...>` is what actually executes. It is a copy that can (and will) become stale after project changes.

**Common trigger pattern** (observed 2026-06-23):
- Script does `sys.path.insert(...) ; from phase6.core.xxx import ...`
- This executes `phase6/core/__init__.py` (which does unconditional imports of runner etc.).
- A downstream module has runtime-evaluated type annotation using a name only available under `TYPE_CHECKING` (e.g. `plan: TradePlan` in order_executor).
- Result: NameError on cron run even if the script "looks fine".

**Debugging sequence (mandatory)**:
1. `cronjob list` → note exact `script:` path and job_id.
2. `cat ~/.hermes/scripts/<exact path>` (compare timestamp/size to project source).
3. `python3 ~/.hermes/scripts/<exact path> 2>&1 | cat` (full traceback; user notifications truncate).
4. Trace the import (here: sentiment_scorer → core/__init__.py → phase6_runner → order_executor).
5. Fix source (add `from __future__ import annotations` at top of affected file; make annotations stringified if needed).
6. Sync: `cp <project script> ~/.hermes/scripts/<target dir>/`
7. In the hermes copy, prefer absolute project root for sys.path (relative `Path(__file__).parent...` often resolves to ~/.hermes/... instead of project).
8. Re-run direct python + confirm cron next execution or manual trigger.
9. Cross-check `crontab -l` + hermes list.

**Pitfalls**:
- Assuming the project `phase6/scripts/xxx.py` is what the cron runs.
- Evolving a report/analyzer script (adding SL risk, Polymarket, strategic proposals with IDs, decision approval section) without syncing the hermes copy → silent feature loss.
- Package `__init__.py` eager imports turn "type only" dependencies into runtime requirements.
- Relative paths in scripts copied to hermes locations.
- Stale copies lose all recent analyst/strategic output.

See `references/cron-no-agent-script-desync-and-project-imports-2026-06-23.md` for the exact traceback, commands used, and the 2026-06-23 fix (future annotations + copy + absolute path).

**Nested paths** (`script: phase6/research/run_analyst_opt_weekly.sh`): file must live at `~/.hermes/scripts/phase6/research/...` with **absolute `ROOT=/home/brad/projects/crypto-trading-bot`** in the wrapper — `workdir` on the job does not substitute for a missing hermes copy. See `references/cron-nested-phase6-research-scripts.md`.

**Standing practice**: After any change to a `no_agent` script or anything it imports (especially under phase6.core), immediately sync the hermes copy and run it directly from the hermes path as verification. Combine with code-isolation-testing for the report logic itself.

Update this section whenever a new desync or import-side-effect incident occurs. Prefer `workdir` on the cron job + direct project script where possible for future jobs to reduce copy surface.

**2026-07-21 — RSI refresher desync killed Stoch trial data:** Hermes job `rsi-15min-refresher` ran a *stale* `~/.hermes/scripts/refresh_rsi_prices.py` (6-pair FIXED_UNIVERSE, no StochRSI) that continuously overwrote `rsi_cache.json`, while the project `scripts/refresh_rsi_prices.py` already had full-basket + Stoch. Fix pattern: make the hermes file a **thin wrapper** (`runpy.run_path` / exec) pointing at the absolute project script so cron cannot drift. Verify with `python3 ~/.hermes/scripts/refresh_rsi_prices.py` and assert cache has `stoch_k` for full basket. Related trial cycle: project `docs/testing/ANALYST_TEST_CYCLE.md`.

## Common Pitfalls
- Using `--prompt` or `--schedule` flags with `hermes cron create` often fails due to CLI parsing.
- Dropping YAML files in `~/.hermes/cron/` does not always auto-register the job.
- The gateway must be running for any cron work to fire.
- **cronjob tool loop trap**: calling create without `schedule` 50+ times in a row (identical args) triggers the exact tool-loop warning seen in max-iteration sessions. Always include the parameter on the first attempt.

## Cron Hygiene & Redundancy Avoidance
**Strong user preference (reinforced in multiple sessions):** Explicitly verify system-level crontab in addition to Hermes cron list / cronjob tool. Run `crontab -l` (and `crontab -l | grep ...` for specific jobs) alongside any Hermes cron inspection. This catches raw system entries that may overlap or be legacy.

Before adding or retaining diagnostic / smoke / access-check crons:
- Audit whether the primary runner, refresher jobs (RSI 15m, sentiment 30m), monitors, or main loops already exercise the same code paths (e.g. `_ensure_live_client()`, `get_holdings_verified()`, live client init).
- In trading bot contexts, the runner + signal refreshers usually provide frequent enough coverage of access, connectivity, and basic state. Dedicated hourly diagnostics are frequently overkill/redundant.

When the user indicates a scheduled job is "overkill", "redundant", or "I don’t really care":
- Treat as a first-class signal to immediately remove the cron entry.
- Update any documentation, comments, or SKILL references that describe the schedule.
- Proactively decommission rather than leave "just in case".

Example (from session): Hourly RobustSmokeTest.py (system crontab `0 * * * *`) for access/SL logic was removed after user noted the runner already exercises the paths frequently enough. The file was retained as manual-only with updated header.

**2026-08-13 — Linux crontab cutover (Phase 6):** User crontab is **comment-only**. SSOT `docs/HERMES_CRON_SSOT.md`. Do **not** add `refresh_sentiment`, `fetch_x`, Apify, or runner monitors back to `crontab -e`. New jobs → Hermes `cronjob` on the **default** gateway. `no_agent` scripts must `export PATH=$HOME/.local/bin:$PATH`. `hermes send` = stdin + `-t telegram` only. Dropped: `phase6_rebalance_monitor.sh` (obsolete flags).

### Report crons must not be control planes (2026-08-29)

Brad: **limited sources of truth**; dashboard/cron **surfaces** only.

1. **`no_agent` reporters never write production settings** (`config/*`) or runner runtime SSOT owned by live loops.
2. After a feature **promotes live**, **pause/archive** its pre-promote validation cron — do not leave “ready for review / Live OFF” bodies that contradict config.
3. **Remove** completed one-shots (installers, one-off dumps, spent reminds) with `hermes cron remove <id>`; pause dead-profile jobs in place.
4. Phase 6 keep/archive classes: repo `docs/HERMES_CRON_SSOT.md` + `reports/CRON_ARCHIVE_AND_SSOT_2026-08-29.md`. Exit dual-writer detail: skill `phase6-exit-automation` → `references/status-ssot-and-validation-archive-20260829.md`.
5. If a report must evaluate live logic, pass **`persist=False`** (or read status JSON only) — never default-persist from cron.

**Verification pattern after any cron change:**
1. `crontab -l` — must show **no executable Phase 6 lines**
2. Hermes cron list (via tool or terminal)
3. `ps aux | grep -E 'phase|runner|smoke'` (or equivalent)
4. Confirm no unintended overlap with trading paths.
5. For reporters: confirm they cannot write `config/` or named runtime SSOT paths.

See `references/cron-hygiene-redundancy-avoidance.md` for the full session transcript (smoke test removal), removal commands, example of updated script docstring, and the standing checklist.

Add a "Cron Hygiene" review to any long-lived trading bot cron setup or monitor profile. Prefer fewer, higher-signal scheduled jobs. Runner activity is the default coverage for access checks.

## External API + Agent Cost Control (multi-vendor)

**Trigger**: User reports high bills (X Developer, Apify, OpenRouter, xAI) while running Hermes + trading bot. **Never conflate vendors** — each has its own console.

### Vendor attribution first (2026-07-21 evidence)

| Provider | Typical role | Example evidence | Default stance |
|----------|--------------|------------------|----------------|
| **Apify** | Reddit scrapers (pay-per-event) | ~**$70.66**/period; scrapesmith results dominated | **OFF** — `SENTIMENT_REDDIT_APIFY_ENABLED=0` |
| **X Developer** | `fetch_x_sentiment` Twitter search | Stacked 30m jobs historically $50+/day | **2×/day only** 08:50/20:50 PT |
| **OpenRouter** | Aux flash / rare tools | **~$0.75/7d** Gemini Flash | Keep aux-only; set **daily key limit** |
| **xAI OAuth** | Main chat + agents | Multi‑M tokens/day busy | `delegation`→`grok-build-0.1`; no 25-turn goal default |

Full pack: project `docs/research/AI_CHARGES_BY_PROVIDER_2026-07-21.md`, `docs/research/COST_REDUCTION_EXECUTION_PLAN_2026-07-20.md`, `references/multi-vendor-cost-attribution-and-free-sentiment.md`.

### Diagnosis pattern (always both crontabs)

```bash
crontab -l | grep -E 'fetch|sentiment|reddit|apify|refresh'
hermes cron list
rg -n 'apify|Actor|SENTIMENT_REDDIT' phase6/scripts/refresh_sentiment.py fetch_reddit_sentiment.py
```

**Pitfall:** Disabling a **standalone** 2h Reddit cron while `refresh_sentiment.py` still calls Apify 2×/day → bill continues. Kill **all call sites**, not just one crontab line.

### Canonical Phase 6 sentiment schedule (do not regress)

| When (PT) | Job | Live? | Notes |
|-----------|-----|-------|-------|
| **08:40 / 20:40** | `scripts/phase6/run_free_sentiment_shadow.sh` | Free file | OKX funding + F&G + RSS → `sentiment_cache_free.json` |
| **08:50 / 20:50** | `phase6/scripts/refresh_sentiment.py` | **Live** | X attempt; on fail/0 posts → **free → live canonical**; Reddit OFF unless env=1 |
| Rebalance | 09:00 / 21:00 | Live | Prefer warm X; else free_fallback scores via scorer |

- **Paused/disabled:** Hermes `sentiment-30min-refresh`; `fetch_x` 2h; old half-hourly refresh; standalone `fetch_reddit` 2h; **Apify in refresh** (default off).
- Docs: `docs/X_SENTIMENT_COST_CONTROL.md`, `docs/FREE_SENTIMENT_SHADOW.md`.
- X lead-time: ~**10 min** before rebalance (not 30m) — Reddit-dominance / decay math; see `references/x-sentiment-pre-rebalance-2x-day.md`.

### Apify Reddit — kill-switch (mandatory after 2026-07 overage)

```bash
# Default OFF everywhere
export SENTIMENT_REDDIT_APIFY_ENABLED=0   # or omit; code defaults to 0
# Re-enable ONLY with explicit budget + free-shadow gates:
# SENTIMENT_REDDIT_APIFY_ENABLED=1
```

- `fetch_reddit_sentiment.py` hard no-ops unless env ∈ {1,true,yes,on}.
- `refresh_sentiment.py` skips Reddit when off.
- **Do not** raise Apify monthly limit to “unstick” production — leave actors disabled; use free hybrid + X.
- **Do not** treat Apify as the cheap alternative to X for high-frequency pair scrapes (pay-per-event scales with results × starts × pairs). Older playbooks that said “switch X to Apify” are **superseded for Reddit volume**.

### Free sentiment + live free_fallback (Phase 3 on 2026-07-22)

1. Fetchers: `fetch_fng_sentiment.py`, `fetch_funding_sentiment.py` (**OKX** primary; Bybit/Binance often geo-blocked), `fetch_rss_sentiment.py`.
2. Merge free file: `phase6/scripts/refresh_sentiment_free.py` → `data/state/sentiment_cache_free.json`.
3. **Live fallback (default):** `sentiment.primary=x_with_free_fallback` in `trading_config_phase6.json`. When X fails or total posts=0, `refresh_sentiment.py` **promotes free → live** `sentiment_cache.json`; scorer mode=`free_fallback`. Kill: `SENTIMENT_FREE_FALLBACK=0`.
4. Full X-off cutover still optional (`primary=free_hybrid`) after multi-day correlation; do **not** leave dashboard at all-zero while free is healthy.
5. Class skill: **`phase6-sentiment-pipeline`** (refs: free-fallback cutover + spend-cap zeros).
6. X hard fail: `fetch_x_sentiment` exit **2**, no zero-clobber of X cache.

### Agent / LLM cost (separate from data APIs)

1. `delegation.model` → **`grok-build-0.1`** (not composer-fast for multi-turn workers).
2. **Kanban / `ops_issue_loop`:** default **no `--goal`**; `--goal` only rank≤1 max **12** turns; `--force-goal` rare.
3. Morning triage: prefer **`ops_triage_discover.py` no_agent** over full LLM skill every day.
4. OpenRouter = **aux flash only**; never main Sonnet (historical multi-$100/day trap).
5. Telemetry: `scripts/ops/llm_token_daily_rollup.py` → `data/state/llm_token_daily.jsonl`.
6. code-reviewer: if `provider: openrouter`, **clear** wrong `base_url: https://api.x.ai/v1`.

**Standing rules**:
- Attribute $ from **vendor dashboards**, not guesses; update AI_CHARGES doc when user pastes CSVs/screenshots.
- Always `crontab -l` + Hermes list.
- Prefer free/public market data + shadow correlate before paid social scrapers.
- Document MASTER + cost docs on every kill-switch or cadence change.

See also: `references/hermes-grok-build-cost-playbook.md`, `references/multi-vendor-cost-attribution-and-free-sentiment.md`. Older X-only throttle notes: `references/x-api-cost-control-sentiment-throttling.md` (superseded for cadence by 2×/day pre-rebalance).


## Telegram "Provider authentication failed" (recurring)

**Trigger:** User says the auth banner keeps happening / replies to that warning.

**Class truth:** User-facing text is a **mask** from `_GATEWAY_AUTH_ERROR_RE` (matches incorrect/invalid API key **or bare `401`**). Not always OAuth death.

**Checklist (2026-08-31 incident):**
1. `hermes status` + `hermes -z 'reply exactly: ok' --provider xai-oauth` — if OK, primary OAuth is fine.
2. Probe/disable **poisoned `XAI_API_KEY`** in `~/.hermes/.env` (REST often HTTP 400 Incorrect API key while OAuth works). Pool entry under `credential_pool.xai` can still fire.
3. `hermes fallback list` — bare-string entries like `- claude-haiku-4.5` are **ignored**; need `{provider, model}` objects.
4. Fix fallback via CLI only (patch tool **refuses** `config.yaml`):
   ```bash
   hermes config set fallback_providers '[{"provider":"openrouter","model":"google/gemini-2.5-flash"},{"provider":"anthropic","model":"claude-haiku-4-5"}]'
   ```
5. After `.env` change: Brad must `hermes gateway restart` in a **separate shell** (in-gateway agent cannot self-restart).
6. Distinguish log classes: `APIConnectionError`/`ConnectError` = reachability (fallback should catch); `Incorrect API key` = real auth path.

Detail: `references/provider-auth-failed-telegram-mask.md`.

## xAI model availability (SuperGrok OAuth)

Probe access with a one-shot call — `~/.hermes/provider_models_cache.json` can lag behind live `/v1/models`:

```bash
hermes -z 'reply exactly: ok' -m grok-4.5 --provider xai-oauth
```

- `grok-composer-2.5-fast` = coding default; `grok-4.5` = flagship. Switch: `hermes config set model.default grok-4.5`.
- Refresh picker (interactive TTY): `hermes model --refresh`.
- Invalid `XAI_API_KEY` on REST does not disprove OAuth access.

See `references/xai-oauth-grok-model-probe-2026-07-08.md` · `references/xai-api-key-vs-oauth-research-tools.md`.

## Model routing pack (default profile)

No auto hard→flagship router. Layers: `model.default` = `grok-composer-2.5-fast` (volume chat); hard work = `/model grok-4.5` then demote; `delegation.model` = **`grok-build-0.1`** (Phase1 cost — not composer for multi-turn workers); `auxiliary.vision|compression|approval|titles` = OpenRouter `google/gemini-2.5-flash`; `fallback_providers` = **outage only**, each entry **must** be `{provider, model}` (bare model strings are silently ignored — verify with `hermes fallback list`). Prefer OpenRouter Flash then Anthropic Haiku. YAML + CLI set: `references/model-routing-and-compaction-resilience.md`.


**OpenRouter Sonnet-class trap:** Main agent on `anthropic/claude-sonnet-*` via OpenRouter + high-iteration Kanban/tool loops → multi-hundred-$ days (user ~$500 Apr 2026; Apr 2–3 export ~99% Sonnet). Keep main/deleg on **xAI OAuth**; OpenRouter = **cheap aux only**. Prefer a hard **key daily limit** when `limit: null`. Never chase marketplace bot ROI screenshots by buying flagship models.

## Context compression resilience

Rapid “resets” often = aggressive compact, not wiped MEMORY.md. Prefer `threshold: 0.70`, `target_ratio: 0.30`, `protect_last_n: 40`, **`hygiene_hard_message_limit: 2500+`** (not **400** — that count-forces compact on tool loops). Detail: same reference.

## Auxiliary summarizer (context compression)

When `openrouter/owl-alpha` (or any aux model) 404s, compaction degrades. **Prefer** `auxiliary.compression` → OpenRouter `google/gemini-2.5-flash`. Alternate: `xai-oauth` + `grok-4.5`. Audit `grep owl-alpha ~/.hermes/config.yaml`. Playbooks: `references/auxiliary-compression-owl-alpha-fix-2026-07-08.md`, `references/model-routing-and-compaction-resilience.md`.

**Analyst Report Output Caching & Live Verification Patterns (2026-06-24 extension)**
The Phase 6 `generate_trading_intelligence_report.py` (and Hermes copies) is now largely deterministic Python (rule-based assessment, evolution notes, and strategic proposals from learnings + heuristics + live data). The ANALYST_PERSONA is flavor only; no direct LLM calls inside the script. Real cost is in the Hermes crypto-analyst gateway context + repeated manual re-runs.

**Patterns**:
- **Live verification test**: `timeout 180 python3 phase6/scripts/generate_trading_intelligence_report.py 2>&1 | tee /tmp/intel_report_live_test.log | head -N`. Inspect for real data (Polymarket bias, coverage stats, signals, SL risks), new ANALYST- IDs, persistence to backlog/MASTER, and "Report complete".
- **Dual caching layer** (to trim fat on repeated invocations):
  - Full report cache: `data/state/intel_report_cache.json` keyed on date + basket + rounded poly bias + high-risk count + coverage (12h TTL). Stores generated text + meta.
  - Compact strategic brief: `data/state/intel_strategic_brief.json` (regime bias, coverage, high-SL-risk pairs, top 3 proposals, last rebalance). Runner/allocator can consume without full text. Directly realizes one of the proposals generated in the same cycle.
- Compute key with stable fingerprint (avoid date-only to catch regime shifts).
- On cache hit: short-circuit with note or serve cached text/brief.
- Always save both at end of generation (even on full run).
- Tie to proposals: the brief artifact was proposed as ANALYST-20260624-006 in the live run that created the cache.

**Live run example outcomes** (for pattern reference):
- Polymarket: bias 0.4, 4 markets.
- Coverage 10/11 FULL.
- New proposals: 005 (SL pre-flight + ticks), 006 (strategic brief).
- High SL risk on many low-priced names due to preview failures.
- 48h observation follow-ups printed for prior items.

**Standing practice**: After any report/script change or cost model switch, run the live test + confirm real data (not mocks) + cache files updated. Update MASTER with key stats. See `references/report-caching-and-live-verification-2026-06-24.md`.

Add cache helpers to the report script (or a shared util) and sync Hermes copies. Combine with code-isolation-testing for the generator logic.

## Monitoring Setup
When setting up persistent monitors (e.g. `crypto-monitor`), always:
- Create the profile in `~/.hermes/profiles/`
- Write a clean `~/.hermes/cron/<name>.yaml` with prompt and schedule
- Test manually first before relying on the schedule

## Custom Dashboards as Systemd Services
When turning a custom Python HTTP dashboard (e.g. `serve_dashboard.py`) into a reliable always-on service:

1. Prefer **user** units under `~/.config/systemd/user/` with bind **127.0.0.1** unless remote is intentional and auth exists.
2. If using system unit: `WorkingDirectory`, full `ExecStart` path, `User=`, `Restart=always`.
3. After `daemon-reload`, `enable` + `start`.
4. "Address already in use" → identify **which unit** owns the port (`ss -lntp` + cgroup) before kill — another unit may respawn.
5. Do **not** default to `ufw allow` + `0.0.0.0` for agent admin UIs (see Phase A host security above).
6. Store unit templates under project `references/` when useful.

Hermes-specific dual-unit trap: system `hermes-dashboard` on `:8080 --insecure` vs user unit on `:9119` — see `references/host-security-phase-a-balanced.md`.

## Telegram Integration
Always store bot token and chat ID in the project's `.env` file. Use `load_dotenv()` with explicit path when running from outside the project directory.

### Outbound cron / shell scripts (`hermes send`)
**Do not use** `--target` or `--message` with `hermes send` — current CLI rejects them (exit 2).

**Correct:** pipe report/body on stdin and pass target only:
```bash
phase6/scripts/generate_trading_intelligence_report.py 2>&1 | hermes send -t telegram
```

Use repo wrapper `phase6/scripts/cron_intelligence_telegram.sh` for twice-daily crypto-analyst briefs; log to `logs/intelligence_cron.log`. If users report missing Telegram briefs but syslog shows cron fired, **first** reproduce the crontab pipe — `|| true` on a broken `hermes send` causes silent no-delivery.

See `references/hermes-send-cli-cron-intelligence-2026-07-08.md`.

## Telegram single-owner conflicts (Hermes multi-profile + OpenClaw)
**Class pattern**: More than one process long-polls the same Telegram bot token (`getUpdates`). Telegram allows **one** consumer per token.

### Symptom families (do not confuse)
| What you see | Likely cause |
|--------------|--------------|
| Startup errors: token already in use (PID …), gateway restart loop | Multiple Hermes `gateway run` / `hermes-gateway-*.service` on same token |
| **Outbound works** (`hermes send`, bot messages arrive) **but user replies do nothing** | Second poller still active (often **OpenClaw** `channels.telegram.enabled` + Hermes both polling) |
| `Connected to Telegram (polling mode)` then **hours of zero inbound log lines** | Split-brain polling: Hermes thinks connected while another client steals updates |
| `urllib`/API **HTTP 409 Conflict** on `getUpdates` | Definitive dual-poller signal |

**Diagnosis** (run via terminal; probe script: `scripts/tg-bot-diag.py`):
```bash
ps aux | grep -E 'hermes.*gateway run|openclaw.*gateway' | grep -v grep
ls ~/.config/systemd/user/hermes-gateway*.service
systemctl --user list-units 'hermes-gateway*' --plain --no-legend
tail -100 ~/.hermes/logs/gateway.log | grep -iE 'telegram|conflict|enqueue|Sending response'
python3 ~/.hermes/skills/hermes-operations/scripts/tg-bot-diag.py
```

**Hermes multi-profile fix (permanent)** — `hermes update` restarts all active `hermes-gateway*` units; stopping without **uninstall** lets conflicts return:
```bash
for p in code-reviewer crypto-analyst crypto-engineer crypto-orchestrator; do
  hermes --profile "$p" gateway uninstall
done
systemctl --user daemon-reload && systemctl --user restart hermes-gateway
hermes gateway list
```

**OpenClaw same-token fix** when Hermes owns the home bot: set `plugins.entries.telegram.enabled` and `channels.telegram.enabled` to `false` in `~/.openclaw/openclaw.json`, then `openclaw gateway restart`, wait ~25s, `systemctl --user restart hermes-gateway`, re-run `tg-bot-diag.py`, then send + **user reply** test (not send-only).

**Pitfalls**: `hermes send` success does not prove inbound; do not `gateway install` on profiles sharing `TELEGRAM_BOT_TOKEN`; OpenClaw may run for other work with Telegram disabled.

See `references/telegram-gateway-multi-profile-conflicts.md` (2026-06-19 + 2026-07-04). Optional user note: `~/.hermes/TELEGRAM_GATEWAY_SINGLETON.md`.

## Dedicated Monitoring Agent Profiles (crypto-monitor pattern)
For long-running trading infrastructure, create isolated profiles (e.g. `crypto-monitor`) rather than overloading the default agent:

- Profile lives at `~/.hermes/profiles/crypto-monitor/`
- `profile.yaml` declares: provider/model (prefer cheaper OpenRouter model), toolsets (`file`, `terminal`, `cron`, `skills`), Telegram config, schedule, and the full monitoring prompt.
- `SOUL.md` is custom-written for the role: "Crypto Monitor Agent" with explicit mandate for process inspection, safe restarts, evidence-based escalation to primary agent, production-safety rules, and structured Telegram + Kanban handoffs.
- Cron definition at `~/.hermes/cron/crypto-monitor.yaml` (or inline in profile.yaml) uses the profile name and a prompt that encodes:
  1. `ps aux` inspection for trading/paper/bot/phase*/orchestrator processes.
  2. Log scanning for ERROR/CRASH patterns.
  3. Safe restart attempts (background python or service commands; never live trading without evidence).
  4. Escalation path: detailed evidence bundle → Telegram to main chat + Kanban task creation with "Must Do/Must Not Do".
  5. Always produce concise structured report (Status / Processes / Actions / Escalations).

This gives a dedicated, scheduled "free AI" monitor that keeps scripts alive and surfaces real problems without polluting the primary agent's context. Update both the profile prompt and the cron yaml in lockstep when evolving the behavior. See also `trading-bot-operations` for related trading-specific monitoring patterns.

## Hermes Web Dashboard (Control Panel) + host security (Phase A)

### Default safe posture
| Mode | Bind | When |
|------|------|------|
| **Loopback + tunnel** | `127.0.0.1:9119` | SSH/Tailscale tunnel to localhost works |
| **Tailscale-bind (Brad 2026-08-27+)** | `100.64.33.2:9119` only | Desktop **SSH client** broken; use Remote gateway URL |
| **Forbidden default** | `0.0.0.0` + `--insecure` | Never casual — open admin without gate |

- Drop-in: `~/.config/systemd/user/hermes-dashboard.service.d/phase-a-bind.conf`
- Remote URL: `http://100.64.33.2:9119` · basic auth on · **not** open LAN
- Full playbook: `references/dashboard-tailscale-bind-and-basic-auth.md` · Phase A: `references/host-security-phase-a-balanced.md`

### Basic auth (app ≠ OS)
- Username often `brad` but **password is not** the Linux account password.
- Stored as scrypt `password_hash` only; reset via `~/.hermes/scripts/reset_dashboard_basic_auth.py` (user types in SSH — never put password in chat).
- Verify: `~/.hermes/scripts/verify_dashboard_basic_auth.py` (Hermes venv / `hermes config get`).
- **Stable sessions:** set `dashboard.basic_auth.secret` + `HERMES_DASHBOARD_BASIC_AUTH_SECRET` in `.env` + unit `EnvironmentFile`; TTL prefer **604800** for remote Desktop. Missing secret → random per-process key → sudden logout / `session resume cancelled`.

### Orphan `hermes dashboard` swarm
Desktop SSH reconnects can leave dozens of `127.0.0.1:<random>` dashboards alongside the systemd Tailscale instance. Clean with **python PID scan** only — **`pkill -f 'hermes dashboard'` kills the agent shell** (cmdline contains those words). Then restart user unit; assert one listener on `100.64.33.2:9119`.

### Do NOT casually recommend
```bash
hermes dashboard --host 0.0.0.0 --insecure   # opens admin on LAN/Tailscale without auth gate
```
Only if Brad explicitly accepts that exposure.

### Dual unit trap (2026-08-08)
| Unit | Typical | Risk |
|------|---------|------|
| `~/.config/systemd/user/hermes-dashboard.service` | `:9119` Tailscale or loopback | OK if auth + not `0.0.0.0` |
| **`/etc/systemd/system/hermes-dashboard.service`** | `0.0.0.0:8080 --insecure` | **High** — `Restart=always` respawns after kill |

Finish (sudo once, **outside** gateway agent):  
`bash ~/.hermes/scripts/phase_a_security_finish.sh`

### Approvals UX (do not re-lock files)
| Fact | Implication |
|------|-------------|
| File `read_file` / `write_file` | **Never** go through approval prompts |
| Shell | `approvals.mode: smart` (not `manual` / not `off`) |
| Fat `command_allowlist` | Hollows smart mode — prefer **`[]`** |
| `HERMES_EXEC_ASK=1` | Prompt spam — set **0** via gateway drop-in |
| `delegation.subagent_auto_approve` | Prefer **false** |
| Trading `.env` | Mode **600** |

### Gateway cannot self-restart
Agent terminal **blocks** restarting `hermes-gateway` from inside the gateway process. For EXEC_ASK/env/unit changes: Brad runs finish script in a **local shell**. Do not loop on blocked restart attempts.

### Agent traps (indirect prompt injection)
Partial defenses (untrusted web framing, private URL block, policy rails). Not a full shield. Prefer structured APIs; money/config apply stays human-gated. Project review: `docs/security/reviews/2026-08-08_hermes-host_vuln_review_patch_plan.md`.

**Note:** Legacy `hermes gateway run --host ... --port ...` is not the dashboard path — use `hermes dashboard`.

### `hermes update` Node/npm mixed state (web UI fail)

**Symptom after update:** mixed-state Node deps + Web UI npm install failed (Python agent may still work).

**Cause:** `engine-strict=true` + `engines.npm: "<11.10.0 || >=11.17.0"`. npm **11.10–11.16** banned. Fix PATH npm **and** `~/.hermes/node`.

**Fix (agent runs it):**
```bash
npm install -g npm@11.17.0
test -x "$HOME/.hermes/node/bin/npm" && \
  "$HOME/.hermes/node/bin/npm" install -g npm@11.17.0 --prefix "$HOME/.hermes/node"
cd ~/.hermes/hermes-agent && export PATH="$HOME/.hermes/node/bin:$PATH"
npm install --no-fund --no-audit --prefer-offline --progress=false --workspaces=false
npm install --no-fund --no-audit --prefer-offline --progress=false --workspace ui-tui --workspace web
npm run build --workspace web
```
Verify: `hermes doctor` → ✓ web. Detail: `references/hermes-update-npm-engine-strict-mixed-state.md`.

### Desktop SSH (Windows client → Linux host) — failure classes

| Desktop message | Class | Playbook |
|-----------------|-------|----------|
| `paused while its managed update is in progress` | Update fence | `references/desktop-ssh-managed-update-pause.md` |
| `Update Hermes on the remote host…` (`sshErrUpdateRequired`) | Ownership flags missing on remote `hermes serve` | same pause ref (ownership probe) |
| Version probe OK, then `SSH operation … timed out` / half-open (~20s) | Serve bootstrap timeout | `references/desktop-ssh-serve-timeout-web-dist.md` |
| Local WS session token reject | Local backend token | `references/desktop-session-token-ws-reject.md` |

**Two update fences (pause class):**
1. **Remote:** `~/.hermes/.hermes-update-in-progress` (+ optional `.update_launch_intent.*` / `.update_exit_code.*` / `.mutex`)
2. **Windows userData:** `managed-ssh-update-recovery.json` under Electron `userData` (`%APPDATA%\Hermes\` or `%LOCALAPPDATA%\Hermes\`) — **not** the install tree under `Local\hermes\hermes-agent\`

**Class rules for Brad's setup (Win Desktop SSH → this Linux box):**
- Linux `apps/desktop/release` / `hermes desktop --build-only` / electron-builder does **not** fix the Windows client; aborting a stuck pack to clear the marker is correct when core is already current.
- Quarantine incomplete `~/.hermes/hermes-agent/apps/desktop/release` so future `hermes update` skips Electron grind.
- Clearing only the remote marker is **insufficient** if Windows still holds recovery for that connection id — rename the recovery JSON, full-quit Desktop, reconnect.
- Do **not** re-click Desktop Update until both fences are clear (re-journals recovery and re-locks dials).
- `update-required` (ownership flags) ≠ pause: probe `hermes serve --help` for `--ssh-session-token-file` / `--ssh-owner-nonce`.

**Timeout-after-version class (post-pause):**
- Desktop SSH **exec budget ~20s** for remote `hermes serve --isolated`.
- Missing `hermes_cli/web_dist/` → cold Vite rebuild (~30s) → timeout even when SSH auth works.
- Failed retries pile `hermes-update-mutex` + `serve --isolated` + `.connect.lock` → more timeouts until zombies cleared.
- Ready signal is **`HERMES_BACKEND_READY`** (not dashboard-ready). Healthy probe ~5–8s after web_dist exists.
- Token files must live under **`$HOME/.hermes/desktop-ssh/<32hex>/<16hex>.token`** (64-hex body); not `/tmp`, not profile `HERMES_HOME`.
- **SSH mode** expects tunnel to local serve — do not open `:9119` from Windows *for SSH mode*. When Desktop SSH is broken, switch to **Remote gateway** on Tailscale-bind `http://100.64.33.2:9119` (see `references/dashboard-tailscale-bind-and-basic-auth.md`) instead of spamming Connect.
- Full-quit Desktop (tray) before cleanup; **one** reconnect after fix — spam Connect worsens mutex pile-up **and** spawns orphan loopback `hermes dashboard` processes.

Full playbooks: `references/desktop-ssh-managed-update-pause.md`, `references/desktop-ssh-serve-timeout-web-dist.md`. Related: `references/desktop-session-token-ws-reject.md`.

## Git-Enabled Operationalization and Resilience
When hardening Hermes on legacy hardware or building migration/resilience, treat git (operations repo) as the durable source of truth for Hermes state.

**Core Pattern (from Phase 1 baseline + plan):**
1. Before major operational work (long audits, phase kickoffs, migration planning): emit a recovery-packet (see recovery-packet skill).
2. Perform baseline inventory:
   - Use direct `hermes cron list` (source of truth), `hermes profile list` (or filesystem ls on ~/.hermes/profiles/), targeted cat of profile.yaml/SOUL.md (sanitize secrets).
   - Inspect processes (`ps aux` for gateways, runners, dashboards), hardware (uptime, df, journalctl), git status/log/ls-files for Hermes references.
3. Export sanitized artifacts to a git-tracked `hermes-state/` (or `hermes-state/` under project):
   - Subdirs: cron/, profiles/, skills/, hardware/, with README.
   - Include: full cron list output, key profile yamls, skills inventory (all + relevant like hermes-operations/ops-engineer), hardware snapshot, sanitized config.
   - Add: recovery packet, verification script (isolation test that re-runs inspections and diffs vs exports), concise PHASE_GOALS.md or equivalent.
4. Update primary record (MASTER_TASK_TRACKING.md) with detailed evidence block using ops-engineer style: real snippets, exact verify commands (`hermes cron list`, `python3 hermes-state/verify_baseline.py`, `ps aux | grep ...`), impact, suggested next.
5. Commit the hermes-state/ artifacts + updates.

**Git Mirroring & Sync (Phase 2 core):**
- Create `scripts/hermes/sync-hermes-state.sh` (selective rsync of non-secret parts + git add/commit/push).
- Run via Hermes cron (daily or on profile/cron change).
- Bidirectional: git pull + apply on recovery/start; push on changes.
- Use project-specific `.hermes/resume-packets/` (per recovery-packet skill) and git worktrees for safe experiments.
- Integrate restore into VPS_MIGRATION_PLAYBOOK: `git clone`; `./scripts/hermes/restore-hermes.sh`.

**Enhanced Git Workflows for Agents (Phase 3):**
- Standardize agent-driven git: always start on feature branch `feat/<id>-<desc>` or `hermes/<profile>-<change>`.
- Conventional commits linking MASTER ticket / Kanban card / plan (e.g. "hermes: add agent git workflows (Phase 3)").
- Every handoff (per agent-delegation) must include "Git Commands for Apply/Verify/Rollback" section with cherry-pick, git status, isolation test commands, and MASTER update requirement.
- Create `hermes/git-workflows/AGENT_GIT_WORKFLOWS.md` as canonical reference (branching, hooks, PR via gh or delegation to code-reviewer).
- Add git-enhanced handoff template (HANDOFF_GIT_ENHANCED.md).
- Pre-commit examples: run isolation tests (e.g. hermes-state/verify_baseline.py), check for handoff git sections, update MASTER.
- Demonstrate live on branch then merge after completion (use gh issue create for tracking).
- Integrate with codebase-inspection (pygount) + git blame for audits during agent work.
- Use `github-code-review` patterns and gh CLI for PRs/issues where available.

**Resilience, Monitoring & Migration (Phase 4):**
- Add git health checks (e.g. scripts/hermes/git/git-health-check.sh): repo status, unpushed commits, hermes/ mirror cleanliness, last sync age from README/commit.
- Enhance ops-engineer_state and crypto-monitor prompts/crons to include "git status in hermes/, last sync, dirty repo?".
- Update VPS_MIGRATION_PLAYBOOK.md with dedicated "Hermes Agent + Git Resilience" section: restore steps (`./scripts/hermes/restore-hermes.sh`), hybrid legacy+cloud, daily sync cron, restore drills in /tmp, reference to hermes/git-workflows/.
- Run restore drills (dry + real in temp HERMES_HOME) as verification; always backup live ~/.hermes first.
- Schedule sync + health via Hermes cron or system crontab; store recovery packets in git.
- Tag stable "Hermes + Phase 6" releases; use git pull + restore for Hermes updates on target (fast/ versioned vs full Docker for bot).

**Verification loops (cross-phase):**
- After any change: re-run `hermes cron list`, `ls hermes/git-workflows/`, `./scripts/hermes/sync-hermes-state.sh --dry`, health check, restore --dry.
- Append real evidence (commit hashes, file lists, tool output snippets) to MASTER under the GIT_HERMES_OPS-XXX ticket.
- Always leave the user on the canonical branch (phase-6.1) after demo branches are merged.

See `references/phase-progression-and-chaining.md` for user-specific patterns on high-level "proceed to phase X" signals leading to immediate chaining through remaining work + next phase without additional prompts. This was observed and operationalized in the 2026-06-14 GIT_HERMES multi-phase execution.

**Concise Phase Goals Pattern:**
When user requests delineation of phase goals (or at plan creation), produce a compact `PHASE_GOALS.md` (or section) with one high-level goal + 3-5 bullet success criteria per phase. Keep under 1 page. See hermes-state/PHASE_GOALS.md for example from this pattern.

**Verification:**
- Always run the isolation verification script post-export/commit.
- Re-verify with `hermes cron list`, profile yaml checks, `git status`, process counts.
- Append "VERIFIED" notes to MASTER.

See `references/git-operationalization-patterns.md` for condensed session transcripts, example artifacts layout, and full phase goals.

**Daily repo automation (2026-07-06):** Load skill **`git-repo-management`** and `docs/GIT_REPO_DAILY_MANAGEMENT.md`. Hermes job `daily-git-hermes-management` (`92d0bbe12216`, `30 4 * * *`) must appear in `hermes cron list` — YAML files under `~/.hermes/cron/` alone are insufficient.

## OpenClaw Maintenance (absorbed from openclaw-maintenance)

Handle OpenClaw version drift, duplicate plugins, gateway blocks, and multi-install conflicts:

### Common Symptoms
- "Config was last written by a newer OpenClaw"
- Gateway restart refused due to version mismatch
- Duplicate plugin warnings for `openclaw-adspirer`

### Diagnostics
```bash
which -a openclaw
ls -l ~/.npm-global/bin/openclaw ~/.nvm/versions/node/*/bin/openclaw 2>/dev/null
openclaw doctor --fix
```

### Version Conflict Resolution
```bash
OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS=1 openclaw update --yes --tag latest
openclaw gateway restart --force
```

### Duplicate Plugin Cleanup
```bash
rm -rf ~/.openclaw/npm/node_modules/openclaw-adspirer \
       ~/.openclaw/npm/package.json \
       ~/.openclaw/npm/package-lock.json
```

After fixes: `openclaw adspirer status && openclaw gateway status`

If Hermes is the primary Telegram bot, disable OpenClaw Telegram polling (`channels.telegram.enabled` and `plugins.entries.telegram.enabled` in `~/.openclaw/openclaw.json`) — same `botToken` as Hermes causes HTTP 409 and inbound silence while outbound send still works.

---

## Loaded Skills Context
This skill should be consulted whenever heavy Hermes CLI interaction or persistent agent setup is required. Consult it for any git-backed resilience, state versioning, or operational baseline work on Hermes.