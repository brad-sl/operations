# P2 — Fee audit on eject cohort

**Brad note:** fees must not be ignored for profit measurement.  
**Shipped:** 2026-10-04  
**Status:** measure + ledger honesty live; no new money knobs

## Bottom line

| | Fee-blind (old) | Fee-aware (truth) |
|--|-----------------|-------------------|
| N scale-window ejects | 8 | 8 |
| Gross PnL sum | **+$0.30** | — |
| RT fees sum | ignored | **$3.28** |
| Net PnL sum | — | **−$2.99** |
| “Green” count / WR | 6 / **75%** | **0 / 0%** |
| Gross-green → net-red | — | **6 wiped** |

**Product law:** eject “wins” are **fee-aware net** only. Gross-only green that nets red is **process tax**, not profit.

## Why

- Protected market exits logged exit price/qty but **dropped `total_fees`**.
- `stamp_sell_pnl` could net fees only when present → default stamp was **gross**.
- Weekly analyst + scoreboards read those gross “greens” as wins.
- Live Coinbase Intro taker is **0.9%**/side (~$0.22–0.23 on a $25 shell). RT ≈ **$0.45** before any edge. A +$0.32 gross LINK eject is still red.

## What shipped

1. **`phase6/core/tryout_eject_fee_audit.py`** — cohort audit  
   - Exchange fill `total_fees` when order_id present  
   - Entry fee pro-rated when parent lot larger than shell  
   - Else live tier taker estimate (labeled)  
   - Scoreboard: blind WR vs aware WR + wiped count  
2. **CLI** `scripts/phase6/run_tryout_eject_fee_audit.py --fetch-live [--backfill --go]`  
3. **Ledger backfill** — 8 eject rows stamped `pnl_stamp=fee_audit_net_rt`, `rt_fee_usd`, net `pnl`  
   - Backup: `trades/phase6_trades.jsonl.bak_fee_audit_20261004T222945Z`  
4. **Forward path** — `protected_market_exit` now stamps `sell_fee_usd` / `total_fees` from fill details into the ledger  
5. **`stamp_sell_pnl`** — nets sell + entry fees (no double-count aliases); sets `rt_fee_usd`  
6. **Config** `rt_fee_rate_per_side` **0.006 → 0.009** (Intro live SSOT; estimates only)  
7. Isolation: `test_isolation_tryout_eject_fee_audit.py` (4/4)

## Artifacts

- `data/state/tryout_eject_fee_audit_latest.json`  
- `reports/TRYOUT_EJECT_FEE_AUDIT_LATEST.md`  
- `reports/TRYOUT_EJECT_FEE_AUDIT_2026-10-04.md`

## Not claimed

- No edge from ejecting more/less  
- No seat-cap or cooloff change from this audit  
- Entry fee missing on 4/8 rows still uses tier estimate on the buy leg (sell leg is exchange truth on all 8)

## Operator read

Dead-kindling kill loop is still correct **risk hygiene**. It is **not** a PnL printer at $25 shells on Intro 0.9% taker until average gross clearance clears ~RT (~1.8% round-trip) with room for slip.
