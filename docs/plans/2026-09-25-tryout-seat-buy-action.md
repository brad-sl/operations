# TryoutSeatBuyAction + RSI-event composer (system loop)

## Intent
Narrow path for **one** quality-tryout `$shell` seat when RSI unlocks mid-cycle and gate-grade sent clears — **not** full book rebalance.

**Product (Brad 2026-09-26):** RSI → sent refresh → buy is a **system**, not a petition. No Brad GO required once system-armed.

## Schedule
- **Primary:** `scripts/refresh_rsi_prices.py` calls the composer **immediately after** a successful 15m RSI write (`post_rsi=True`).
- **Safety-net cron:** Hermes `phase6-rsi-event-tryout-seat-composer` @ `2,17,32,47 * * * *`.
- **Universe:** all **production tryout-eligible** doors under current regime.
- **RSI door:** `quality_tryout.max_rsi` (live, often 55).
- **Policy:** `data/state/rsi_event_tryout_seat_brad_policy.json`
  - **system arm:** `python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py --system`
  - money ON when `mode=autonomous` + `auto_armed=true` (no re-check of GO count)
- **Paid X:** on by default on post-RSI path (budget-capped; RSI lane ≤8 pair-queries/day, cooldown 3h).
- **Latch TTL:** 180m (hold gate-grade clear across eng age until next X cycle).
- **Kill:** `touch data/state/rsi_event_tryout_seat_KILL` or `--disarm --kill` · `POST_RSI_COMPOSER=0`

## Split (doctrine)
| Owner | Job |
|-------|-----|
| `book_rebalance` | Held weights / cash / protectives — **refuses** new seats |
| dual_agree + Brad GO | Roster REMOVE→ADD |
| **`tryout_seat_buy`** | Single new tryout seat at `abs_cap_usd` |

## Ship
- Domain: `phase6/domain/actions/tryout_seat_buy.py`
- Composer: `phase6/core/rsi_event_tryout_seat_composer.py`
- Policy: `phase6/core/rsi_event_tryout_seat_policy.py`
- CLIs: `run_tryout_seat_buy.py`, `run_rsi_event_tryout_seat_composer.py`, `run_rsi_event_tryout_seat_policy.py`

## Money fence
- Money when **system/autonomous armed** on post-RSI path, or explicit CLI `--go` + `--live`.
- Shell = `quality_tryout.abs_cap_usd` (today $25), hard max `$75`.
- `evaluate_buy_entry` SSOT; free/tee cannot unlock.
- Composer re-holds latch on dual-clear so readiness doesn't fall to aged eng zeros.

## Operator
```bash
# Arm closed loop (once)
PYTHONPATH=. python3 scripts/phase6/run_rsi_event_tryout_seat_policy.py --system

# Isolation
PYTHONPATH=. python3 scripts/phase6/test_isolation_tryout_seat_buy_action.py

# Sense / dry
PYTHONPATH=. python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py

# Force one post-RSI tick (money if armed)
PYTHONPATH=. python3 scripts/phase6/run_rsi_event_tryout_seat_composer.py --post-rsi
```

## First live proof
2026-09-26 system arm → LINK-USD $25 fill (order `cf6483b0-…`, SL on, scale-up lot registered).

## Non-goals
- Full rebalance / force flag for new seats
- Free/tee unlock
- dual_agree auto without Brad GO
