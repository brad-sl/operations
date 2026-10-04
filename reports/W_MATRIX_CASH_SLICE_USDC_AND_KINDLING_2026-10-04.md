# W-MATRIX-CASH-SLICE-USDC + kindling structure + repeat eject

**Date:** 2026-10-04  
**Brad GO:** structure plumbing (prior) + USDC = deployable free cash (this message)

## Product rules locked

1. **USDC is idle yield park, not a seat.** It *is* usable for trades.
2. **Liquidate in chunks** (powder top-up wave) when USD reserve is short; refill USDC when quiet.
3. **Better than nothing in bear/flat** — counting only fiat USD as free cash starved add-risk while ~$1.7k USDC sat parked.

## What was wrong

| Surface | Before | After |
|---------|--------|-------|
| `load_add_room_by_pair_for_dashboard` | `cash_usd` ≈ **$225** (USD leg only) | **~$1,915** = USD + USDC |
| Matrix / max_add narrative | bags `max_add=$0` via **cash_slice** while powder rich | cash_slice ~**$133** after reserve; binding often **thin open profit**, not fake zero cash |
| Kindling live plan | paper-scaled skip left `structure_ok=None` → `structure_unknown` fail-closed | resolve phase/structure on paper skip; live re-read `detail.phase_struct` |
| Repeat dead shells | always 24h cooloff | 2nd eject in 7d → **72h** cooloff (hygiene, not edge) |
| Eject fee honesty | measure helper | `estimate_rt_fees_usd` on eject receipt when fees missing |

## Code

- `phase6/core/add_risk_sizer.py` — `resolve_deployable_cash_usd()`; dashboard + runner plan paths
- `phase6/core/tryout_scale_up_shadow.py` — structure on paper_scaled early-return
- `phase6/core/tryout_scale_up_live.py` — `_structure_ok_from_row` + re-resolve
- `phase6/core/tryout_scale_window.py` — repeat cooloff + fee measure
- `config/tryout_scale_window.json` — repeat_eject_* + rt_fee_rate_per_side

## Live check (2026-10-04)

```
deployable ≈ $1914.57  (USD ~225 + USDC ~1689)
BTC/ETH cash_slice budget ≈ $133 (after min reserve on equity)
BTC max_add still tiny — binding = profit/heat budgets, not "no cash"
```

**Execution note:** sizing now sees USDC. Actual Coinbase buys still spend **USD**; powder balancer remains the chunk USDC→USD top-up when reserve short. No FOMO dump of full USDC pile.

## Tests

- `test_isolation_tryout_scale_up_live` PASS (incl. structure tests)
- `test_isolation_add_risk_sizer` PASS (incl. USDC deployable)
- `test_isolation_tryout_scale_window` PASS 12/12 (repeat cooloff + fee est)
- `test_isolation_stamp_sell_pnl` PASS

## Not done / not claimed

- Intake seat-cap tighten (NO-GO — insufficient N)
- Automatic full USDC liquidation
- Edge from repeat cooloff (hygiene only)
