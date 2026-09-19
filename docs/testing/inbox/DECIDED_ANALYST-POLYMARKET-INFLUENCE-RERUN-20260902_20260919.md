# Decision — ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902

- **decision:** `extend_trial`
- **CR:** **NO_CR**
- **by:** brad
- **at:** 2026-09-19T18:02:12.086035+00:00
- **note:** Brad 2026-09-19: lack of trades makes window incomplete for edge relevance. Sensor OK but crypto n=10 / risk_on n=0. Extend collect until crypto-N and bucket coverage clear relevance bar (or hard stop). No live promote.
- **follow_on:** `extend` child ANALYST-POLYMARKET-INFLUENCE-EXT-20260919; gates: crypto_joined>=15 OR (risk_on_n>=5 AND neutral_n>=5); hard_stop final_at +21d; ex-stable sells only for edge; live_promote=false
- **packet:** `docs/testing/decisions/DEC_ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902_20260919.md`
- **unblocks:** []
- **regimen:** `docs/testing/TEST_REGIMEN_E2E.md`
