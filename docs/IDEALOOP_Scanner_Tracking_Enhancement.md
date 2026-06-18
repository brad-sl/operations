# Tracking for Opportunity Scanner + Pair Expansion Pairs (IDEALOOP-002)

**Date:** 2026-06-13  
**Question:** Do we have the ability to track trading pairs that originate via the Opportunity Scanner + Pair Expansion to validate & optimize the method?

**Answer:** **Yes.** We have dedicated, queryable tracking for scanner-originated pairs. Enhanced during the "proceed to live" execution.

## Current Tracking Capabilities (as of live enablement run)
1. **Primary log**: `data/state/opportunity_proposals.jsonl`
   - Every scan logs full proposals with:
     - pair, score, proposal text, reason (RSI, sent, mom, vol, div)
     - gate ("#5 shadow only...")
     - data (real RSI, sent, mom)
     - market context
   - Multiple historical entries for DOGE-USD and SOL-USD.

2. **Dedicated origin tracker** (new enhancement): `data/state/scanner_origins.jsonl`
   - Seeded with all current proposals.
   - Schema:
     {
       "ts": "...",
       "pair": "DOGE-USD",
       "score": 0.468,
       "origin": "opportunity_scanner_IDEALOOP-002",
       "proposal": "Test basket expansion: add DOGE-USD with $36.8 test alloc (score=0.468)",
       "gate": "#5 shadow only...",
       "status": "proposed" | "shadow_applied" | "paper_validated" | "live_deployed"
     }
   - Can be appended when status changes (e.g. when Phase 1 applies in shadow, or live rebalance uses it).

3. **Shadow A/B results**: `data/state/shadow_ab_results.jsonl` (populated on Phase 1 runs with enable_scanner)
   - Includes "proposal_source", delta_deploy, shadow vs baseline for the pair.

4. **Rebalance history**: `data/state/rebalance_history/default.jsonl`
   - Can be cross-referenced by time + pair to see when a scanner pair was added (e.g. "reason": "shadow_ab_scanner_phase1").

5. **Paper validation**: Logs in the Phase 3 harness report include the applied trades with proposal notes.

6. **Live state / positions**: Current `phase6_live_state.json` has positions; we can extend to add "origin" metadata per pair.

## How to Use for Validation & Optimization (#1 + #2 loops)
- Query `scanner_origins.jsonl` for pairs with "origin": "opportunity_scanner_IDEALOOP-002".
- Join with rebalance_history on ts/pair to measure:
  - Time from proposal to deploy.
  - P&L attribution for scanner pairs vs legacy basket.
  - Win rate, executed rate for scanner-originated vs others.
  - Impact on total deploy in lackluster markets.
- Feed into Phase 2 perf calculator for "scanner_method" edge.
- Dashboard can add a "Scanner Pairs" card using the log.
- For optimization: When a proposal succeeds (e.g. positive delta in shadow or live), update status in the tracker and use in #1 param tuning (e.g. boost score for DOGE-like RSI + mom).

## Enhancement Implemented (during live run)
- `data/state/scanner_origins.jsonl` created and seeded.
- Helper function `tag_scanner_origin()` ready to call from runner when a proposal is applied (in shadow or live path).
- Recommendation: In runner, when shadow/live applies a test_alloc from scanner, call the tagger with status="shadow_applied" or "live_deployed".
- This closes the loop for #2 (scanner) and #5 (A/B validation).

## Next for Full Live Tracking
- Patch runner (small) to import and call the tagger on proposal application.
- Add "origin" field to rebalance_event logs when scanner-driven.
- Update Phase 6 dashboard or reports to surface "scanner_originated_pairs".
- In #1 perf feedback: group metrics by origin.

This gives us the ability to validate (did the DOGE proposal improve deploy without gate violations?) and optimize (tune scoring weights based on realized performance of scanner pairs).

All real data, logged durably, queryable with simple jsonl tools or python.

## Evidence
- scanner_origins.jsonl has entries for DOGE and SOL from the proposals.
- Cross with opportunity_proposals.jsonl for full context.
- Integrated with the live run attempt and Phase 1/3 artifacts. 

This directly supports continuous improvement in the lackluster market.