# Preferred-arm auto membership (Brad GO path A) — 2026-09-26

## Call
Brad: approval without decline criteria is theater; post-seat filters handle money.
**Do A:** auto-seat on **preferred-arm** seriously-consider only.

## Behavior
When `phase6-basket-swap-cf-shadow` runs and preferred arm (`rel_btc_stable` SSOT) writes a **new** membership-potential-OK swap:

1. Auto-apply via `promote_basket_proposal` (membership only)
2. TG notice: applied / refused / daily-cap (not a GO ask)
3. dual_agree still TG “needs GO” if it fires
4. `live_membership_swaps` stays **false** (narrow gate ≠ free-for-all)
5. No orders, no force rebalance

## Gates
- policy `preferred_arm_auto_membership.enabled` (ON)
- kill file `data/state/preferred_arm_auto_membership_KILL`
- membership_potential_ok
- REMOVE in basket, ADD not in, not BTC/ETH sticky, held &lt; **$5 dust-only** (not full $25 tryout shells)
- missfire hard-block (no auto override)
- novelty: seat-only override allowed (logged)
- **≤1 successful apply / UTC day**

## Files
| Piece | Path |
|-------|------|
| Core | `phase6/core/preferred_arm_auto_membership.py` |
| CLI | `scripts/phase6/run_preferred_arm_auto_membership.py` |
| Isolation | `scripts/phase6/test_isolation_preferred_arm_auto_membership.py` |
| Cron hook | `~/.hermes/scripts/run_basket_swap_shadow_cf.sh` |
| Receipt | `data/state/preferred_arm_auto_membership_latest.json` |
| Crumbs | `data/state/preferred_arm_auto_membership_crumbs.jsonl` |
| Decision | `basket_swap_brad_decision.json` → `preferred_arm_auto_membership` |

## Ops
```bash
# status
python3 scripts/phase6/run_preferred_arm_auto_membership.py
# kill / unkill
python3 scripts/phase6/run_preferred_arm_auto_membership.py --kill
python3 scripts/phase6/run_preferred_arm_auto_membership.py --unkill
# disable without kill file
python3 scripts/phase6/run_preferred_arm_auto_membership.py --disable
```

## dual_agree
Unchanged: still needs Brad GO via `basket_swap.sh --go`.
