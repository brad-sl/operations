# Membership Manager Phase 1 — Brad GO 2026-10-03

## Product
Self-regulating bag membership: find contenders, dismiss weak ones, seat the best name in place of a flat deadbeat. **Brad is not on the happy path.** History (career ledger) lets cold names return.

## What shipped
| Piece | Path |
|-------|------|
| Config | `config/membership_manager.json` (`enabled`+`live_apply` true) |
| Core | `phase6/core/membership_manager.py` |
| CLI | `scripts/phase6/run_membership_manager.py` |
| Cron script | `phase6/scripts/run_membership_manager_cron.sh` |
| Hermes wrapper | `~/.hermes/scripts/run_membership_manager.sh` |
| CF hook | `~/.hermes/scripts/run_basket_swap_shadow_cf.sh` → manager after CF |
| Isolation | `scripts/phase6/test_isolation_membership_manager.py` (8/8) |
| Career | `data/state/membership_career_ledger.json` |
| Receipt | `data/state/membership_manager_latest.json` |
| Kill | `data/state/membership_manager_KILL` (+ honors preferred-arm kill) |
| Panel | Promote lifecycle: open/closed eps, mgr badge, h→fill = latency not queue |
| API | `/api/membership-manager` + mm blob on `/api/promote-graduation` |

## Gates (always)
- ≤1 apply / UTC day (shared with preferred-arm crumbs)
- REMOVE held < **$5** protect (dust-only — never eject live tryout shells)
- Sticky BTC/ETH never removed
- M-gate OK required (strict preferred-arm OK writes only)
- Meme/pump names blocked by default
- Novelty may override **seat-only**; missfire never auto
- **No orders**, no force rebalance, `live_membership_swaps` stays false
- **dual_agree still manual GO**

## Promote panel honesty
- Terminal stages (`filled_win` / `filled_loss` / `stale_no_signal`) → **closed**
- `hours_to_first_fill` labeled historical latency, not queue age
- Live rebuild: **open_eps=9 · closed_eps=4** (ICP/ZEC closed history, not waiting 400h)

## Live dry-run (2026-10-03)
- Preferred-arm: no membership-OK write (last CF was SOL→PUMP M3 fail + meme blocked)
- Contender path: ADA→SAND refused M1 extended_24h/3d (honest refuse, not silent skip)
- Status path working; no basket mutation on dry-run

## Ops
- Standalone cron: **10:05 / 16:05 / 22:05 PT** TG only on apply/refuse/cap/kill
- CF cron still **11:30 / 23:30 PT** and now runs manager after arms
- Kill: `touch data/state/membership_manager_KILL`

## Honesty
Seat ≠ fill ≠ win. Buy still needs RSI / sent / seats / run-phase.
