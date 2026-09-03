# Discovery retro board (shadow)

**as_of:** `2026-09-03T06:01:09.391483+00:00`  
**status:** research / read-only  
**discovery runs used:** 57 (2026-08-08T19:46:47.219452+00:00 → 2026-09-03T05:15:52.216494+00:00)  

## Plain English

```
Discovery retro board as_of 2026-09-03T06:01:09.391483+00:00
Top gainers scored: 9 (vol≥$100,000, ret≥8.0%).
Lead classes: EARLY=1, MEDIUM=1, SHORT=1, NEVER=6
Week-ahead (EARLY) hits: 1/9.
Why-not: thin_liquidity=5, picked=3, active_basket=1
T-7 forward book: n=27 mean=2.194% hit>0=0.2593 hit>+15%=0.1481.
Shadow only — no config writes, no orders.
```

## Why this exists

Work **backwards** from names exploding today → did we flag them at T−7 / T−3 / T−1?  
Work **forwards** from names we flagged a week ago → did that cohort win?  
That is the only honest test of early-detect. Not a buy signal.

## Gainer lookback (today's rippers × frozen contender lists)

| Pair | 24h % | Vol $ | Lead | Style | Why not | Quiet | T-7 | T-3 | T-1 | T0 | Methods |
|---|---:|---:|---|---|---|---:|---|---|---|---|---|
| EDGEX-USD | 27.1699 | 329229.47 | **NEVER** | absent | `thin_liquidity` | 0.56 | · | · | · | · | — |
| USELESS-USD | 26.7687 | 9932630.8 | **MEDIUM** | episodic | `picked` | 0.20 | · | · | Y | Y | pair_discovery_contenders,discovery_pipeline_eligible,discovery_pipeline_swap_proposal,basket_swap_cf:baseline_hybrid,rel_btc_stable |
| EGLD-USD | 26.1649 | 1503446.2 | **NEVER** | absent | `thin_liquidity` | 0.52 | · | · | · | · | — |
| AERGO-USD | 18.3025 | 374585.66 | **NEVER** | absent | `thin_liquidity` | 0.51 | · | · | · | · | — |
| ARB-USD | 14.8388 | 11156693.12 | **NEVER** | absent | `active_basket` | 0.35 | · | · | · | · | discovery_pipeline_swap_proposal |
| BNKR-USD | 14.477 | 1051151.54 | **NEVER** | absent | `thin_liquidity` | 0.47 | · | · | · | · | — |
| BASECAT-USD | 12.7079 | 1054691.99 | **SHORT** | episodic | `picked` | 0.33 | · | Y | · | · | pair_discovery_contenders,discovery_pipeline_eligible |
| LIGHTER-USD | 10.1815 | 7488097.83 | **EARLY (chronic_watchlist)** | chronic | `picked` | 0.72 | · | Y | Y | Y | pair_discovery_contenders,discovery_pipeline_eligible,discovery_pipeline_swap_proposal,basket_swap_cf:anti_pump,baseline_hybrid,dual_agree,rel_btc_stable,risk_adj_mom |
| APT-USD | 8.2988 | 1992517.39 | **NEVER** | absent | `thin_liquidity` | 0.54 | · | · | · | · | — |

### Why not (detail)

- **EDGEX-USD**: thin_liquidity: 24h quote vol $329,229 < discovery floor $2,000,000
- **USELESS-USD**: picked: named as contender (7 run(s)); lead_class=MEDIUM
- **EGLD-USD**: thin_liquidity: 24h quote vol $1,503,446 < discovery floor $2,000,000
- **AERGO-USD**: thin_liquidity: 24h quote vol $374,586 < discovery floor $2,000,000
- **ARB-USD**: active_basket: already in active basket — excluded from emerging contenders
- **BNKR-USD**: thin_liquidity: 24h quote vol $1,051,152 < discovery floor $2,000,000
- **BASECAT-USD**: picked: named as contender (3 run(s)); lead_class=SHORT
- **LIGHTER-USD**: picked: named as contender (13 run(s)); lead_class=EARLY
- **APT-USD**: thin_liquidity: 24h quote vol $1,992,517 < discovery floor $2,000,000

### Quiet features (research sketch — post-move biased)

| Pair | quiet_early | btc_rel_3d | liq_jump | vol_dry | compress→expand |
|---|---:|---:|---:|---:|---:|
| EDGEX-USD | 0.5625 | 0.3367 | 18.1910 | 0.5043 | 2.7339 |
| USELESS-USD | 0.2000 | 1.1504 | 0.9079 | 2.9977 | 0.5964 |
| EGLD-USD | 0.5210 | 0.4078 | 6.8307 | 1.2330 | 1.8696 |
| AERGO-USD | 0.5125 | -0.0013 | 4.1045 | 0.8273 | 1.8376 |
| ARB-USD | 0.3500 | 0.5247 | 1.8197 | 8.5617 | 0.6182 |
| BNKR-USD | 0.4750 | 0.0282 | 1.9293 | 1.9718 | 1.1186 |
| BASECAT-USD | 0.3250 | 0.0247 | 0.4522 | 2.4343 | 0.5184 |
| LIGHTER-USD | 0.7250 | 0.0593 | 1.6238 | 0.8914 | 0.8919 |
| APT-USD | 0.5365 | 0.1501 | 1.4694 | 1.2770 | 0.9708 |

### Lead class legend

- **EARLY** ≥7d before as_of — only class that could be 'week-ago identify'
- **MEDIUM** 3–7d — early impulse, not full week
- **SHORT** 1–3d — often already moving
- **COINCIDENT** <24h — found during/after the green day
- **NEVER** — exchange tape only; our funnels never named it

### Why-not codes

- `picked` / `coincident_late` / `pump_brake` / `promote_blocked` — funnel saw it
- `thin_liquidity` — below discovery $ vol floor
- `below_prequal_cutoff` — vol ok but lost energy top-N vs peers
- `quality_fail` — made energy screen, failed mom/vol structure
- `contender_cutoff` — quality pass, not top contenders
- `active_basket` — already seated (excluded from emerging list)

## Forward book (T−7 contenders → realized ~7d)

Anchor ~ `2026-08-27T05:15:52.216494+00:00`  
Union size: **27**  

Summary: n=27 · mean=2.194% · hit>0=0.2593 · hit>+15%=0.1481 · best=109.735 · worst=-25.294

| Pair | ~7d ret % |
|---|---:|
| USELESS-USD | 109.73528135397079 |
| SKR-USD | 104.43501735441573 |
| HONEY-USD | 31.203007518796987 |
| MDT-USD | 21.471652593486134 |
| STX-USD | 7.859922178988321 |
| LIGHTER-USD | 4.904338453247092 |
| ZEC-USD | 2.0020242415265788 |
| BOBBOB-USD | -2.0576131687242705 |
| HYPE-USD | -3.034238488783947 |
| JASMY-USD | -4.9281314168378 |
| SWELL-USD | -5.915662650602416 |
| WIF-USD | -7.501840942562598 |
| MAMO-USD | -7.591324200913252 |
| VET-USD | -7.849447320554082 |
| VVV-USD | -8.837394595312398 |
| BADGER-USD | -10.263221444095638 |
| ZRO-USD | -10.36549337384992 |
| MON-USD | -11.031879194630879 |
| PUMP-USD | -11.117936117936122 |
| ENA-USD | -11.16207951070336 |
| TRUMP-USD | -11.831417023113444 |
| POL-USD | -13.002780352177945 |
| TAO-USD | -13.322840842022432 |
| PENGU-USD | -13.62321834331749 |
| BICO-USD | -18.987439019705754 |
| NCT-USD | -24.663978494623663 |
| FARTCOIN-USD | -25.294447560291644 |

## Method hypotheses (not GO)

- Hypotheses to test next (instrumentation → evidence → only then promote path):
- 1. Current discovery is late-by-design on explode days: NEVER=6/9, COINCIDENT=0/9, SHORT/MED=2/9, EARLY≥7d=1/9 (of which true_early=0, chronic_watchlist=1).
- 2. **True** week-ahead explode detection (fresh name, not chronic watchlist) is absent on this tape with energy/mom quality. Do not add buy paths that assume it.
- 2b. Chronic contenders (PUMP/ZEC/HYPE-class) can look EARLY by first-seen clock — that is watchlist persistence, not pre-impulse radar. Score them separately.
- 4. T-7 contender forward book: mean=2.194% hit>0=26% (n=27). If mean≤0 and hit≪50%, contender list is **not** an alpha sleeve — it's an attention list.
- 5. Feature direction worth shadow-testing (no live bind): (a) pre-impulse vol dry-up → expand, (b) relative strength vs BTC on 3–5d *before* energy tops the board, (c) liquidity regime break (quote vol percentile jump) with **muted** 24h ret (catch compression, not the green candle). Board now logs quiet_early_score / btc_rel_3d / liq_jump / vol_dry / compression on each gainer (post-move biased today). pair_discovery_runs schema v2 stores prequal/quality reject ledgers going forward for true why-not.
- 5b. Why-not distribution on this board: thin_liquidity=5, picked=3, active_basket=1. thin_liquidity + below_prequal_cutoff = energy funnel never saw them; quality_fail = saw energy but structure gate; pump_brake/coincident_late = saw but too late to size.
- 5c. quiet_early_score on today's gainers: mean=0.468 (n=9). High after a rip ≠ early — score must be validated on T−3/T−7 frozen snapshots before trusting.
- 6. Process bar for 'game changer': standing forward book must beat liquid-universe base rate on 7d excess **and** survive fees/SL shadow before any seat path.

## SSOT / safety

- Writes **only**: `data/state/discovery_retro_board_*.json*` + this report
- Does **not** write `config/*`, live basket, exit automation, or runner state
- Gainers source: Coinbase public stats (same family as discovery prequal)
- Contender truth: frozen `pair_discovery_runs.jsonl` (no hindsight re-rank)

*Generated by `phase6.core.discovery_retro_board` · 2026-09-03T06:01:09.391483+00:00*
