# Handoff: Automated Daily X Brief for Audience Building & Subscriptions

**Task ID:** X-DAILY-BRIEF-001  
**Parent / Category:** Marketing_Business_Development_Ideas (idea #1)  
**Assigned To:** Content/automation focus (crypto-analyst + creative + xurl skills)  
**Date:** 2026-06-27  
**Goal:** Mostly-automated pipeline that turns the existing intelligence brief + sentiment + logging into a refined, short daily X (Twitter) brief. Builds followers with consistent value. CTAs drive to subscriptions (Substack/newsletter) or waitlist. Long-term: paid tier for deeper access.

**Status:** Ready for implementation. Most components exist (report, brief JSON, sentiment, cron, posting capability via Hermes xurl, TradeLedger for proof points).

### Objective (Measurable)
- Daily (once/day) concise, engaging X content (1 post or 3-5 tweet thread) featuring:
  - Polymarket regime (bias, confidence, sample event, influence).
  - Key X/Reddit signals (top assets, aged scores).
  - One insight or tie-in to logged impact.
  - Strong CTA + link (free full brief → paid subs).
- Automation level: 80-90% (generate + post; human review gate initially).
- Success: Audience growth + measurable clicks/subs after 30-60 days. Use regime impact data (from ANALYST-20260627-024 logging) as credibility proof.

### Context & Existing Assets
- **Data sources** (ready today):
  - `phase6/scripts/generate_trading_intelligence_report.py` → `data/state/intel_strategic_brief.json` (polymarket full section + influence).
  - Sentiment: `sentiment_scorer` (X with decay, Reddit fallback).
  - Impact proof: TradeLedger + `analyze_regime_impact()` + stack snapshots in `influence_stack_log.jsonl`.
- **Delivery**: Existing report runs, cron support (Hermes profile), Telegram notifier.
- **Posting**: Hermes `xurl` skill (or API wrapper). Fetch patterns already exist (fetch_x_sentiment.py).
- **No major new infra needed** for MVP. The generator script + cron glue is the gap.
- Market fit: Aligns with demand for concise sentiment/regime updates. Differentiator = volume-weighted Polymarket + transparent logging (vs pure social tools).

From full ideas doc: This is the highest-probability, lowest-friction starting point while the trading platform matures.

### Scope & Boundaries
**Must Do:**
- Create `phase6/scripts/generate_daily_x_brief.py` (or equivalent in scripts/).
- Produce X-optimized output (thread or single post) from latest brief + sentiment snapshot.
- Automate via Hermes cron (recommended) or phase6 cron: generate → (notify draft) → post.
- Log every generated/posted brief (`data/state/x_posts_log.jsonl` with timestamp, text, post_id if available).
- Include CTAs + link to Substack/waitlist/premium.
- Start in shadow mode (generate + Telegram notify only).
- Update MASTER_TASK_TRACKING.md + this handoff folder.
- Style guide or prompt for consistent, valuable, non-spammy tone (numbers first, regime prominent, one clear insight, CTA).
- Tie in real data from impact logging once available.

**Must Not / Out of Scope (initial):**
- Full auto-posting without review gate for first 7-14 days.
- Paid content gating (future phase).
- Image generation or advanced visuals (text + emoji first; add later via creative skill).
- Follower analytics scraping (manual or simple later).
- Multi-platform (X only to start).

**Nice-to-Have (stretch):**
- A/B config for thread vs single post formats.
- Weekly "X performance + best briefs" section in the intelligence report.
- Delegate_task wrapper for "refine this for X" using creative skill.

### Detailed Workflow (End-to-End)
1. **Trigger** (cron, daily 07:30-08:00 UTC or chosen audience peak time):
   - Ensure fresh brief: Call report script (or load cached latest).
   - Capture current sentiment snapshot + (optional) recent regime impact summary.

2. **Generate**:
   - Script loads JSON.
   - Applies template + refinement (rules or light LLM/creative prompt for punchiness).
   - Example output structure (refined short brief):
     Tweet 1 (hook): "Polymarket Risk-On Bias: 0.62 (conf 0.85 | 3 high-vol mkts, $XXM total). Volume-weighted crowd view tilting bullish."
     Tweet 2 (signals): "Top X sentiment: SOL +0.42 (51 posts), ADA +0.85, LINK +0.78. Reddit quiet. Regime multiplier active in allocator."
     Tweet 3 (insight + proof): "High-vol BTC $150k-by-June-30 market still neutral but vol spiking. Our logged stack snapshots show [brief tie to past performance when bias extreme]."
     CTA: "Full daily brief + regime logs + impact analysis → [link]. Daily at 8am. Follow for the edge. #Crypto #Sentiment #Polymarket"
   - Save draft + metadata.

3. **Review/Gate**:
   - Telegram notification with draft text + "Approve / Edit / Skip".
   - Human (quick) review.
   - Script waits or has a manual override flag.

4. **Post**:
   - Call xurl (or equivalent) to post thread or single post.
   - Capture post ID / URL.
   - Append to x_posts_log + influence stack if relevant.

5. **Track & Close Loop**:
   - Log success/failure.
   - (Future) Pull basic engagement (manual or tool) and correlate with regime strength on that day.
   - Weekly: Review what performed (use in content or analyzer).

### Automation Details & Schedule
- **Cron (Hermes preferred)**:
  - Use Hermes cronjob tool or edit `~/.hermes/profiles/crypto-orchestrator/cron/jobs.json`.
  - Schedule example: `30 7 * * *` (daily).
  - Prompt/skills: Load file, creative (for polish), xurl (post). Run generator script.
  - Deliver: To origin chat or dedicated channel for review.
  - Flags: `--shadow` (generate only), `--post`, `--notify`.
- **Alternative**: Phase6 runner/cron extension or simple shell + timer.
- **Initial cadence**: Shadow for 1-2 weeks → gated auto → full auto (with logging).
- **Error handling**: Fallback neutral post; Telegram alert on failure. Never spam.

**Dependencies**:
- Fresh intel_brief (tie to existing report cron if any).
- X credentials via xurl/Hermes config.
- Link target: Substack (or placeholder) for subs.

### Agent / Orchestrator Proposal
We already have most pieces. Two clean options:

**Primary Recommendation (Simple & Fast)**: Hermes cron job (can be LLM-driven prompt or pure script).
- Self-contained prompt or Python entrypoint.
- Loads: Latest brief + sentiment snapshot.
- Outputs ready-to-post text.
- Skills: file (read data), creative (humanize/refine tone per style guide), xurl (post), terminal (run report).
- `no_agent=True` for deterministic script run if preferred.
- Bonus: Pass recent `analyze_regime_impact()` snippet for credibility line.

**Autonomous Agent Option**: Lightweight dedicated agent via `delegate_task`.
- Name: "daily-x-brief-agent" or "content-brief-orchestrator".
- Role: "Turn the latest regime + sentiment data into a high-engagement short X thread. Prioritize clarity, numbers, and one actionable insight. Always include CTA to subs."
- Context injected: Paths to brief, recent stack log, style examples.
- Tools: file, creative, xurl.
- Trigger: Cron or on-demand.
- Can be called from the generator script or standalone.
- Output: Structured (posts list) + confirmation. Logs to handoff-style or data/.

Start with cron + script. Promote to full agent once we have 1-2 weeks of real posts and want smarter variation (e.g., "make this thread punchier based on yesterday's engagement").

Existing parallels: Crypto-analyst tasks, creative for content, xurl for social.

### Files & Changes
**New:**
- `phase6/scripts/generate_daily_x_brief.py` (core: load, template, refine, write draft/post).
- `data/state/x_posts_log.jsonl` (timestamp, text, post_id, regime_bias_at_post, engagement notes).
- Style guide (optional): `docs/X_Daily_Brief_Style.md` (examples + rules).

**Updates:**
- `handoffs/ideas/Marketing_Business_Development_Ideas.md` (full list saved).
- `docs/MASTER_TASK_TRACKING.md` (add dated entry for this task + evidence).
- Report script (optional `--export-x-brief` flag for convenience).
- Hermes cron (via tool).
- (Future) Link the X log back to regime impact analysis.

**Handoff Artifacts**:
- This doc.
- The generator script (to be written in next step).

### Verification & Milestones
- **Milestone 1 (shadow)**: Script runs, produces good draft from current brief, notifies. Manual review.
- **Milestone 2**: First live posts (gated). Logs captured.
- **Milestone 3 (2-4 weeks)**: Audience metrics + first sub conversions. Review `analyze_regime_impact()` correlation with post days.
- Test: Run generator against today's `intel_strategic_brief.json`. Inspect output.

### Next Actions (Ready to Execute)
1. Write + test the generator script (skeleton + run against live brief).
2. Create Hermes cron in shadow mode + test notification.
3. Draft 1-2 real X briefs from current data for user approval.
4. Set up placeholder Substack or link target.
5. Update MASTER + any Kanban.
6. Enable posting after review.

This is grounded in what already runs daily. The automation will be reliable and low-maintenance once the small generator + cron are in place.

Confirm direction or specific details (exact post time, thread length preference, sample output tone, Substack link) and I'll implement the script + cron immediately.