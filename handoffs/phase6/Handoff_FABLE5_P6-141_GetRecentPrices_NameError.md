# Handoff: FABLE5-P6-141 (P1 — pre-paper blocker)

**Title**: get_recent_prices crashes on cache-hit path (NameError: name 'datetime' is not defined) — deterministic on any repeat pair within 5 min

**From**: Fable 5 Batch 4 closure pass (explicit #1 pre-start blocker for paper).

**Objective**: Make second (and subsequent) calls for the same pair inside the cache window succeed. One-line hygiene: promote the local import to module level or restructure so the name is always in scope on the cache-hit branch.

**Files**:
- phase6/core/exchange_client.py (the get_recent_prices function).
- Any callers (ATR calculator, risk signals, hybrid, runner trace).

**Must Do**:
- Add `from datetime import datetime` at the top of the module (or inside a helper import guard).
- Write a tiny standalone isolation test: `scripts/test_fable5_p6_141_recent_prices_cache.py` that calls the function twice for the same pair (second within 300s) and asserts no exception + cached result on second hit.
- Confirm that ATR / other consumers that hit the same key don't blow up the loop.
- Scotty runs the test in shadow + adds sign-off comment.

**Must Not Do**:
- Leave the import inside the try of the fresh path only.
- Allow the cache-hit branch to reference an undefined name.

**Success criteria**:
- Isolation test passes cleanly (call 1 → miss; call 2 < 5min → hit, no crash).
- Scotty comment + link to test output.
- Paper harness can now survive a full cycle with repeat price queries.

**Created**: 2026-06-10 (Batch 4 closure ingest, small batch follow-on).

**Reference**: Fable 5 Batch 4 §1 (P6-141 table + gate G1 conditional), punch-list Day 1 item #1.