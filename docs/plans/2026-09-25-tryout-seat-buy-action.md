# TryoutSeatBuyAction + RSI-event composer (2026-09-25)

## Intent
Narrow path for **one** quality-tryout `$shell` seat when RSI unlocks mid-cycle and gate-grade sent clears — **not** full book rebalance.

## Schedule (2026-09-25 Brad)
- **Primary:** `scripts/refresh_rsi_prices.py` calls the composer **immediately after** a successful full/partial 15m RSI write (`post_rsi=True`).
- **TG approval:** Hermes `phase6-rsi-event-tryout-seat-composer` @ `2,17,32,47 * * * *` deliver=**telegram** — quiet card only when dual-clear dry_would_buy (empty=silent).
- **Universe:** all **production tryout-eligible** doors under current regime (not full bag; not ballast).
- **RSI door:** `quality_tryout.max_rsi` (live, often 55) — not shadow-only 40.
- **Approval ladder:** first **2** live Brad GOs (`--go --live`); then `--arm-auto` for 24×7 autonomous. Policy: `data/state/rsi_event_tryout_seat_brad_policy.json`.
- **Paid X:** `COMPOSER_GO_X=1` default on post-RSI path (budget-capped).
- **Opt-out / kill:** `POST_RSI_COMPOSER=0` · `data/state/rsi_event_tryout_seat_KILL` · `run_rsi_event_tryout_seat_policy.py --disarm --kill`

## Split (unchanged doctrine)
| Owner | Job |
|-------|-----|
| `book_rebalance` | Held weights / cash / protectives — **refuses** new seats |
| dual_agree + Brad GO | Roster REMOVE→ADD |
| **`tryout_seat_buy`** | Single new tryout seat at `abs_cap_usd` |

## Ship
- Domain: `phase6/domain/actions/tryout_seat_buy.py`
- Composer: `phase6/core/rsi_event_tryout_seat_composer.py` (shadow → optional X probe → seat)
- CLIs:
  - `scripts/phase6/run_tryout_seat_buy.py`
  - `scripts/phase6/run_rsi_event_tryout_seat_composer.py`
- Isolation: `scripts/phase6/test_isolation_tryout_seat_buy_action.py`

## Money fence
- Default **dry_run**.
- Money only when **`go=True` AND `dry_run=False`** (CLI: `--go` + `--live`).
- Shell = `quality_tryout.abs_cap_usd` (today $25), hard max `$75`.
- `evaluate_buy_entry` SSOT; kill switch; max one pair per call.
- Free/tee cannot unlock — caller passes paid X / latch eng.

## Operator
```bash
# Isolation
PYTHONPATH=. python3 scripts/phase6/test_isolation_tryout_seat_buy_action.py

# Direct seat plan (dry)
PYTHONPATH=. python3 scripts/phase6/run_tryout_seat_buy.py \
  --pair LINK-USD --sentiment 0.40 --rsi 28

# Composer: sense only
PYTHONPATH=. python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py

# Composer: paid X if wash+budget (still no orders)
PYTHONPATH=. python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py --go-x

# Composer: GO seat intent still dry without --live
PYTHONPATH=. python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py --go-x --go-buy

# Money (explicit Brad GO only)
PYTHONPATH=. python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py --go-x --go-buy --live
```

## Non-goals / not this ship
- Cron auto-money
- Full rebalance / force flag
- Stacking event X on top of 2× forever without cutover plan
- Knife R1 reclaim automation

## Status
PARTIAL SHIP — domain + dry CLI green. Live money remains Brad `--go --live` only.
