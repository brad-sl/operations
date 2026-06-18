# Handoff Document: Canonical Sentiment Refresh Pipeline + 30min Cron (No-Fabrication + Unification)

**Task ID**: RSI-SENT-003 (from RSI_SENTIMENT_RELIABILITY_PLAN.md)  
**Priority**: P0-Critical  
**Created**: 2026-06-11  
**Owner**: Autonomous execution (Scotty)  
**Status**: Ready for implementation (Phase 2 of plan)  
**Related**: Past P6-121/122 fabrication handoff; SENTIMENT_SYSTEM_SPEC.md; current run_sentiment_system.py

## Objective
Establish a **single, reliable, scheduled** sentiment refresh pipeline that matches the spec (standalone system, 30min aggregation, decay, no fabrication of fresh neutrals on zero results) and feeds all shared consumers (runner, rebalancer, reports, etc.).

Directly fix: No consistent 30min Hermes cron; code duplication across fetchers/scorers; monitor staleness; ensure real data + proper gates.

## Background / Root Causes
- Spec (SENTIMENT_SYSTEM_SPEC.md v1.1): Standalone X + Reddit fetchers → Scorer (decay: X 15min HL, Reddit 60min) → Cache. Max age 60min. Native Apify preferred. Public interface via scorer. 30min in pipeline diagrams.
- Handoff P6-121/122 (critical): Writer fabricating 0.0 + fresh ts on zero posts; bad Apify dataset parsing; legacy schema; must preserve prior timestamp + mark insufficient; isolation test required; kill other writers.
- Current: `run_sentiment_system.py` (recent, Jun 11) + `run_sentiment.sh` (NumPy workaround) exists and has updated canonical cache with real scores. But **no 30min job** in Hermes cron (only twice-daily report). Duplication: phase6/core/sentiment/*, root fetch_*.py, archived/, multiple scorers, phase6/scripts/.
- `sentiment_monitor_state.json` stale.
- Runner often uses placeholder sentiment=0.0; scorer is called successfully in some attempts.
- Rebalancer (HybridRebalancer) is a consumer (explicitly integrates time-decayed sentiment).

**Answer embedded**: Unify on one canonical orchestrator (`run_sentiment_system.py` as base or promoted), enforce gates, add the cron.

## Must Do
1. Designate **single canonical entry point**: Promote/harden `run_sentiment_system.py` (or move to `phase6/scripts/fetch_sentiment_canonical.py`). It must:
   - Call the fetchers in phase6/core/sentiment/ (or consolidate the best X + Reddit).
   - Use proper Apify dataset iteration (per old handoff).
   - Combine with decay via the canonical `sentiment_scorer`.
   - On zero posts or error: **Do not write fresh ts + 0.0**. Preserve prior entry's timestamp + add status="insufficient_data" or "error".
   - Enforce post-count gate (e.g., require >=5-10 posts per pair or mark low confidence).
   - Write to the single canonical `sentiment_cache.json` with consistent schema (v3: schema_version, sentiment: {pair: {score, posts, timestamp, sources, confidence, age_minutes?}}).
2. Add / enhance Hermes cron job: 30min schedule (`*/30 * * * *` or "30m") calling the canonical script (no_agent preferred for reliability). Deliver to local or appropriate channel on errors.
3. Unify readers: All code must go through `phase6/core/sentiment_scorer.py` (or the one in phase6/core/sentiment/). Update runner, hybrid_rebalancer, reports, etc. to use load_sentiment_scores + get_aged_... exclusively. Loudly reject unknown schemas.
4. Refresh/enhance monitor: Update or run `monitor_canonical_sentiment.py` (or equivalent) every 30min. Write actionable state (age, post counts, stale flag). Alert on age >180min.
5. **Code Isolation Test** (mandatory): Test zero-results case — simulate Apify returning 0 items → cache must retain previous timestamp + marker; no fresh neutral. Also test normal run, aging, and scorer integration.
6. Clean duplication: Move or archive non-canonical fetchers/scorers (root fetch_*.py, archived/, duplicate scorers) after verifying the chosen path works. Update imports.
7. Wire into consumers: Ensure runner passes real (aged) sentiment to SignalGenerator and HybridRebalancer.evaluate(). Remove "placeholder" comments.
8. Logging/observability: Structured logs with #posts per source, final score, duration, any fallbacks.
9. Update live cache + reports to reflect proper freshness.
10. Document the unified interface (align with spec's "get_sentiment_scores" future pattern).

## Must Not Do
- Do not stamp current time + neutral score when fetch returns insufficient data.
- Do not leave multiple writers hitting the canonical cache.
- Do not skip the post-count + timestamp gate.
- Avoid changing public scorer API without migration.

## Files in Scope
- Primary: `run_sentiment_system.py`, `run_sentiment.sh`, `phase6/core/sentiment_scorer.py` (and phase6/core/sentiment/ subdir files)
- New/Modify: Hermes cron (via tool or jobs.json)
- Modify: `phase6/core/phase6_runner.py`, `phase6/core/rebalancing/hybrid_rebalancer.py`, `phase6/scripts/generate_trading_intelligence_report.py`
- Test: Isolation test in phase6/core/test_isolation.py or new test file
- Archive: Legacy sentiment scripts after validation
- Docs: This handoff, plan, MASTER_TASK_TRACKING.md, possibly update SENTIMENT_SYSTEM_SPEC.md

## Shared Consumers (Confirmed)
- **Runner / SignalGenerator**: Direct consumer of load_sentiment_scores + adjusted weights.
- **HybridRebalancer**: Yes — explicitly "Integrates time-decayed sentiment from the restored sentiment system (15min X, 60min Reddit half-life)".
- Intelligence reports, dashboards (serve_live), backtests, allocation.
- Future multi-user via shared cache/provider.

## Success Criteria
- 30min Hermes cron job active and succeeding (cache timestamp updates every ~30min with real data).
- Zero-result simulation in isolation test: prior timestamp preserved + explicit marker (no fresh 0.0).
- Canonical cache uses consistent v3-ish schema; all readers go through scorer.
- Runner and rebalancer use fresh/aged sentiment (logs + no placeholder 0.0 in signal paths).
- Monitor state updated and non-stale.
- Duplication reduced (at least legacy writers archived or disabled).
- Reports show accurate freshness labels.
- No rate-limit or quota explosions in normal runs (combined queries).

## Standing Constraints
- Real data only (X via Apify/direct, Reddit via Apify native fields preferred).
- Align with full SENTIMENT_SYSTEM_SPEC.md (decay, batch efficiency, public interface).
- Code Isolation Testing before sign-off.
- Update master list.

## References
- RSI_SENTIMENT_RELIABILITY_PLAN.md (full phases, especially sentiment path verification)
- phase6/specs/SENTIMENT_SYSTEM_SPEC.md (architecture, decay, 30min, interface)
- handoffs/phase6/Handoff_FABLE5_P6-121_122_Sentiment_Fabrication.md (exact no-fab rules)
- Current files: run_sentiment_system.py, sentiment_cache.json, phase6/core/sentiment_scorer.py, hybrid_rebalancer.py, runner logs
- Existing (partial) monitor: trading-signal-pipeline skill references if relevant

## Deliverables
1. Hardened canonical refresh script + active 30min cron.
2. Passing zero-result + normal isolation test + run output.
3. Unified consumption in runner + rebalancer.
4. Cleaned duplication + updated monitor.
5. Master tracking + plan updates.
6. Evidence: Recent cache with proper timestamps + post counts; successful cron run log.

**Verification**:
```bash
# Manual run
python run_sentiment_system.py
# Check cache
cat sentiment_cache.json | jq .
# Cron addition via hermes tools
```

Ready for implementation. Pass this handoff + plan context to any sub-agent.

**Note on Rebalancer**: Confirmed as shared consumer — ensure aged sentiment flows to its evaluate() call.