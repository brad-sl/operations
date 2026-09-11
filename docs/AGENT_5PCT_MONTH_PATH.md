# 5%/mo take-home path (agent SSOT)

**Mission (read first):** `docs/PLATFORM_MISSION.md` — reliable automated when/what/how → net profitability → scale. Lab R&D, not quick-cash gambling.

**MASTER card:** `P6-5PCT-MONTH-PATH-20260909` in `docs/MASTER_TASK_TRACKING.md`  
**Plan:** `docs/plans/2026-09-09-platform-opt-after-3w-patches.md`  
**Brad GO:** 2026-09-09 (this session)

## What “5% per month take-home” means

Deposit-adjusted NAV, **not** raw wallet %. Target ≈ **+$115/mo on ~$2.3k**.  
Scoreboard: `reports/MONTH_PATH_SCOREBOARD_LATEST.md`.  
Edge class until proven: **`ATTENTION_ONLY_less_loss_path`** — stop process tax first. This is **not** a printer guarantee.

## Why we are not at 5%

Closed months: Jun −25%, Jul −28%, Aug −3.3%. SL banks red faster than TP banks green. Leaks: post-SL reentry, post-TP rebuy, same-day churn, pile-on, elevated-RSI large tickets, **stale SL ratchet**, **72h config with empty cooldown** (`get_recent_trades(hours=)` TypeError).

## Live stance (do not “fix” by adding alts)

- Regime **flat B**, cap **$75** (config SSOT now matches policy)
- Max 2 new seats/day, tryout size
- **LINK-USD** on `buy_block_pairs` until 72h after 2026-09-09T04:07Z SL (clear after **2026-09-12T04:07Z** unless Brad extends)
- Leave current LINK lot + PAXG MICRO — **no flatten**
- Limit-first: unfilled = **skip** (`market_fallback_max_usd=0`)
- Live TP trail 4/2 + fixed 6% stays on
- UNI/RAVE stay blocked
- Do **not** live-gate sweet-rule CF
- Do **not** grind volume for Advanced 1 (0.8% taker)

## Code gates future agents must not bypass

1. `evaluate_buy_entry` → `pair_process_tax_lockout_reasons` (72h SL / 24h TP / same-day pair)
2. `TradeLedger.get_recent_trades(limit=, hours=)` — hours **must** work
3. Ratchet: `usable_existing_stop_for_ratchet` — no ghost `existing_stop` on fresh buys
4. Deny lists only count if `collect_buy_block_pairs` + evaluate path fire

## Proof commands

```bash
cd /home/brad/projects/crypto-trading-bot
bash scripts/hermes/pre_ship_quality.sh
```

Quality SSOT: `docs/AGENT_QUALITY_GATES.md`. Bounce runner only after PASS.

## 14-day watch (then talk size, not before)

- process_tax MTD ≈ 0
- fleet same-session wound 7d = 0 new
- no LINK BUY while block listed
- month_path gap shrinking via **less leak**, not more util

If 14d red **and** process_tax ≈ 0 → then staff util/size with Brad. Not this week.
