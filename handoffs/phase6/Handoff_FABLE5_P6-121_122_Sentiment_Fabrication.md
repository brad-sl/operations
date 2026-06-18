# Handoff: FABLE5-P6-121 + P6-122 (P1-Critical)

**Title**: Canonical sentiment writer fabricates fresh neutral (0.0) data every run; live cache is divergent legacy schema (P6-108 blocker)

**From**: Fable 5 Batch 2

**Objective**: Fix the v3 Apify writer so that it actually retrieves results (via dataset), treats zero-post runs as failure (preserve prior timestamped data), and writes a consistent versioned schema that matches what the live cache and HybridRebalancer expect. Kill any legacy writer that is still producing the old per-pair format.

**Must Do**:
- In `run_full_sentiment_v3.py`: Replace `getattr(run, \"output\", {})` with proper Apify dataset iteration: `client.dataset(run[\"defaultDatasetId\"]).iterate_items()`.
- On zero results or error: do **not** write fresh timestamp with 0.0. Either skip the write or explicitly mark `status: \"error\"` / keep previous cache entry's timestamp.
- Add `posts >= N` (configurable, e.g. 5–10) + fresh-timestamp joint gate; readers must enforce it.
- Unify writer output schema: add `\"schema_version\": 3`, always use tz-aware UTC ISO timestamps, consistent nested structure (`sentiment: {pair: {score, posts, timestamp, quality?}}`).
- Migrate the existing `sentiment_cache.json` (or replace it) to the new schema.
- Locate and disable (or delete) any other cron/script that is still writing the old per-pair + ADA-USD + tz-naive format.
- Update `phase6/core/sentiment_scorer.py` (load + aging) and `HybridRebalancer._load_sentiment` to reject unknown schema versions loudly and respect the new fields.
- Add Code Isolation Test that simulates a writer run with 0 posts → verifies prior data is preserved (or error marker) and no fresh neutral is injected.

**Must Not Do**:
- Do not stamp current time + 0.0 when the actor returned no usable data.
- Do not keep a second legacy pipeline writing a different schema behind the canonical path.

**Files in scope**:
- run_full_sentiment_v3.py
- sentiment_cache.json (and any other cache files)
- phase6/core/sentiment_scorer.py
- phase6/core/rebalancing/hybrid_rebalancer.py (_load_sentiment)
- Any cron / systemd / script that calls sentiment collection (search for it)
- scripts/ related to sentiment

**Deliverables**:
1. Fixed writer that actually pulls dataset results and handles zero-result gracefully.
2. Versioned unified schema + migration of live cache.
3. Reader updates + loud rejection of bad/old data.
4. Isolation test proving "no data" does not fabricate neutral with fresh timestamp.
5. MASTER ingest + Kanban card.
6. Confirmation that legacy writer is dead + P6-108 assessment can advance.

**Success Criteria**:
- A writer run that receives 0 usable posts leaves the cache with the *previous* timestamp (or explicit error) rather than now+0.0.
- HybridRebalancer and sentiment_scorer can parse the new schema and correctly gate on freshness + post count.
- Live `sentiment_cache.json` is in the v3 writer format after the fix run.
- P6-121/122 findings marked closed after Scotty verification.

**Standing Constraints**: Real data only. Sentiment integrity is foundational for signals and rebalancing.

**References**: Fable 5 Batch 2 P6-121, P6-122, prior P6-108.

**Priority**: P1-Critical (P6-108 is now worse; blocks reliable signal use).