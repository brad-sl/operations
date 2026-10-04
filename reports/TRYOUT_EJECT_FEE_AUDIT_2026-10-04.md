# Tryout eject fee audit

**As of:** 2026-10-04T22:29:45.659534+00:00  
**Schema:** `tryout_eject_fee_audit_v1`  
**N ejects:** 8  
**Taker rate:** 0.009 (Intro · fee_tier_snapshot_latest)  
**Live fetch:** True  

## Scoreboard (fee-blind vs fee-aware)

| Metric | Value |
|--------|-------|
| Gross PnL sum | $0.299341 |
| RT fees sum | $3.284718 |
| **Net PnL sum** | **$-2.985377** |
| Fee-blind green | 6 (WR 0.75) |
| Fee-aware green | 0 (WR 0.0) |
| Gross-green → net-red | 6 |
| Sell fee exchange truth | 8 |
| Entry fee exchange truth | 4 |

**Product rule:** Profit measurement on ejects must use fee-aware net. Gross-only green that nets red is process tax, not a win.

## Cohort

| ts | pair | gross | RT fee | net | wiped? | sell_src | entry_src |
|----|------|-------|--------|-----|--------|----------|-----------|
| 2026-10-01T05:29:54 | TIA-USD | 0.207764 | 0.445574 | -0.23781 | YES | exchange_sell | est_taker_entry |
| 2026-10-01T05:29:58 | LINK-USD | 0.11591 | 0.347128 | -0.231218 | YES | exchange_sell | exchange_entry_prorated |
| 2026-10-01T14:41:49 | LINK-USD | 0.11725 | 0.34903 | -0.23178 | YES | exchange_sell | exchange_entry_prorated |
| 2026-10-01T14:41:54 | TIA-USD | -0.656307 | 0.444015 | -1.100322 |  | exchange_sell | est_taker_entry |
| 2026-10-02T04:45:43 | HYPE-USD | 0.17984 | 0.450364 | -0.270524 | YES | exchange_sell | est_taker_entry |
| 2026-10-02T22:45:43 | HYPE-USD | -0.35687 | 0.446546 | -0.803416 |  | exchange_sell | est_taker_entry |
| 2026-10-03T22:45:44 | LINK-USD | 0.32041 | 0.353319 | -0.032909 | YES | exchange_sell | exchange_entry_prorated |
| 2026-10-04T16:45:46 | SOL-USD | 0.371344 | 0.448742 | -0.077398 | YES | exchange_sell | exchange_entry_prorated |

## Notes

- Protected market exits historically omitted total_fees on ledger SELL rows.
- stamp_sell_pnl nets fees only when present — fee-blind gross was the default stamp.
- Live tier taker used for estimates: 0.009 (fee_tier_snapshot_latest).
