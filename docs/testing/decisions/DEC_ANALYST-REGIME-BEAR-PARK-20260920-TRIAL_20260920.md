# Decision packet — ANALYST-REGIME-BEAR-PARK-20260920-TRIAL

| Field | Value |
|-------|--------|
| Trial | `ANALYST-REGIME-BEAR-PARK-20260920-TRIAL` |
| Family | `regime_bear_park` |
| Decided at (UTC) | 2026-09-20T07:10:41.085836+00:00 |
| By | brad |
| Enum | `propose_scoped_experiment` |
| CR | **ACCEPT** `CR-regime-bear-park-20260920` |
| Follow-on | `scoped_shadow` |
| Regimen | `docs/testing/TEST_REGIMEN_E2E.md` |

## Design (summary)
- Hypothesis: QUEUED (strategy)
- Primary window: `bear_historical_slices`
- Success bar (frozen): min_n=15; beat ret+dd=True

## Outcome (measured)
- Primary pass: **True**
- Class: `HIT_CRITERIA`
- N (primary): 442
- Δret vs baseline (pp): None
- ΔDD vs baseline (pp): None
- Report: `reports/REGIME_BEAR_PARK_TEST_20260920.md`
- Plain English: Bear premise HOLDS on 442d / 59 episodes: full park ret=4.2509% dd=0.0% vs tactical ret=-59.9482% dd=60.1954% vs BTC ret=-98.2137% dd=98.2565%.

## Decision rationale
Brad Accept 2026-09-20: HIT_CRITERIA on 442d/59eps (park +4.25%/0DD vs tactical -60%/-60DD). Live fingerprint bear/usdc_park/allow_new_buys=false matches. Accept premise; scoped_shadow only; NO live promote / NO knob change.

## Follow-on
- Mode: `scoped_shadow`
- Detail: Keep full USDC park as episode law under live bear; no tactical deploy promote; continue bear profit-take + ladder shadows measure-only; no regime_cash_policy write.

## Notify
- Inbox: `docs/testing/inbox/DECIDED_ANALYST-REGIME-BEAR-PARK-20260920-TRIAL_20260920.md`
- Packet: `docs/testing/decisions/DEC_ANALYST-REGIME-BEAR-PARK-20260920-TRIAL_20260920.md`

## Live boundary
- Config writes this decision: **none**
