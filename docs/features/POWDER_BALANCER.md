# Powder balancer (USDC ↔ USD wave reserve)

**Shipped 2026-09-06** — automates cash **availability** vs **yield** under micro-deploy / quality_tryout.

## Goal

Keep enough **USD powder** for the next tryout/deploy wave; park the **structural stub** (cash the 2×$75 machine cannot absorb) in **USDC** for exchange yield. Never sell crypto alts to do this.

## Behavior

| Signal | Action |
|--------|--------|
| Full **park** (`strategy_mode=usdc_park`, etc.) | Legacy path: may sell alts → USDC |
| **Deploy** + `powder_balancer.enabled` | Maintain USD reserve; USD→USDC or USDC→USD only |
| Deploy + powder **off** | Legacy redeploy unwind / armed wait |

### Reserve formula (default)

```
wave = abs_cap_usd × max_new_seats_per_day   # e.g. 75 × 2 = 150
target_usd = clamp(wave × reserve_waves + buffer, floor=150, ceiling=400)
# default → 150 + 50 = $200
```

- If `USD > target + hysteresis` → **park_to_usdc** (excess)
- If `USD < target − …` and USDC available → **topup_from_usdc**
- Else **hold**

Same daily rebalance continues into ARCH-4 / tryout buys after balance (top-up first when short).

## Config

`config/trader_accounts.json` → account → `live_usdc_park.powder_balancer`:

| Knob | Default | Meaning |
|------|---------|---------|
| `enabled` | **true** (primary) | Master for this layer |
| `auto_reserve_from_tryout` | true | Size reserve from quality_tryout |
| `reserve_waves` | 1.0 | Multiplier on wave notional |
| `usd_reserve_floor_usd` | 150 | Never keep less than this target |
| `usd_reserve_buffer_usd` | 50 | Extra dust / fee headroom |
| `usd_reserve_ceiling_usd` | 400 | Cap idle USD |
| `min_action_usd` | 25 | Min trade size |
| `hysteresis_usd` | 20 | Avoid thrash |
| `do_not_sell_alts` | true | Hard product rule |

Requires `live_usdc_park.enabled=true`.

## Ops

```bash
cd /home/brad/projects/crypto-trading-bot
OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 scripts/phase6/powder_balancer_status.py
OPENBLAS_CORETYPE=GENERIC .venv/bin/python3 phase6/core/test_isolation_powder_balancer.py
```

Status: `data/state/powder_balancer_status.json`  
History: `data/state/powder_balancer_history.jsonl`  
Logs: `[POWDER]` prefix

Hot-reload: **config knobs only** (`trader_accounts.json`). Any change under `phase6/core/*.py` needs a **runner restart** (Python does not reload modules). Force path: `touch data/state/force_rebalance.flag`.

### Venue path (live dig 2026-09-06)

Trading Bot is a **CONSUMER** portfolio. Force-rebalance caught:

1. No spot `USDC-USD` → `Invalid product_id`
2. Native Convert API only on **Default** portfolio → 403 on this API key
3. Working hop: **USD → market buy USDT-USD → limit sell USDT-USDC (limit-only book) → USDC**
4. Unwind reverse: USDC → limit buy USDT-USDC → market sell USDT-USD

Implemented in `phase6/core/usdc_convert.py` (powder + park + redeploy unwind).

## Honesty / monthly goal

- Powder balancer **does not** put more crypto in play by itself.
- Max concurrent tryout notional stays **~$150** until seat/cap policy changes.
- USDC yield on ~$2k stub is ~cents/day — harvests idle time; **not** the path to ~5%/mo.
- Raising crypto-in-play = raise tryout seats/size or exit recovery — **separate Brad GO**.

## Rollback

Set `powder_balancer.enabled: false` on the account (or defaults). Next cycle returns to legacy deploy (USD-heavy / full redeploy unwind on park→deploy edge).

## Code map

- `phase6/core/powder_balancer.py`
- `phase6/core/usdc_convert.py` (native Convert → USDT hop fallback)
- `phase6/core/usdc_park_transitions.py` (`PHASE_POWDER_BALANCED` + redeploy unwind)
- `phase6/core/usdc_park_executor.py` (park convert uses same hop)
- `phase6/core/rebalance_coordinator.py` (record `path=powder_balance`, continue to buys)
- `phase6/core/trader_account_config.py` (defaults)
- `phase6/core/test_isolation_powder_balancer.py`
