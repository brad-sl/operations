# Review Handoff: Live Validation of Aggressive Low-Basket Recovery (ARCH-2 + Integration)

**Date**: 2026-06-19 (Reviewer: code-reviewer)
**Role**: Review. Confirm the <4 / <=2 active pairs aggressive logic is present, correct, and ready for live when flag enabled.

## Context
ARCHITECTURE and earlier handoffs called for "more aggressive when basket drops below 4 (or ≤2) active pairs".

## Evidence from Code Audit + Live Run
In phase6/core/allocator.py (RotationStrategy):
- emergency_recovery = len(current_allocs) <= 2
- active_pair_count = sum(1 for v in ... if v > min_move)
- if <=2: emergency_recovery = True
- Relaxed: min_buy_score = 0.3 (recovery) vs 0.55
- max_strong = 3 if emergency else 2
- Hard stops on low conviction
- Weak exit → opportunistic redeploy

Live Allocator run (low current sentiment):
- Produced plan (tilt/fallback)
- No emergency triggered because holdings empty in the test snapshot.

## Reviewer Findings
- Logic **is implemented** in the new Allocator (good).
- Not yet exercised in runner (because flag=False and legacy path dominates).
- Needs test case with simulated low basket + positions.
- Hard stops still use score proxy, not real price/ATR drawdown.
- Integration with deploy_capital fallback observed in live output.

## Gaps / Recommendations
- Add low-basket simulation to integrated tests.
- When wiring ARCH-4, ensure aggressive path is taken when conditions met.
- Verify with forced low active count + high-score proposals.
- Capture evidence: "Emergency Recovery Mode Active" log + resulting plan actions.

## Verification Steps
1. Run Allocator with mocked current_allocs = {'SOL-USD': 100} (low basket).
2. Force high sentiment proposals.
3. Confirm relaxed gates and larger redeploy.
4. Append output to MASTER + this handoff.

References: allocator.py lines ~102-134 (emergency logic), previous ARCH-Aggressive-Basket-Logic.md handoff, evaluate_universe live runs.
