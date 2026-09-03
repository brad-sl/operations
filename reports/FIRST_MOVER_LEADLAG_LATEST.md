# First-mover / lead-lag cohort dig
As of `2026-08-19T18:55:14.980149+00:00`

## Plain English

BTC/ETH (and LINK/SOL) are co-movement anchors — mean same-day corr to others ~0.68. Tight beta cohort (min corr≥0.5 vs BTC&ETH): 17 names (DOGE, LINK, AVAX, ADA, SOL, AAVE, …). That is a real 'moves together' pack, not a proof of next-day pull. After fixing session alignment (no listing-gap jumps), BTC next-session lift on +2% days is ~0.4pp on hit-rate — weak as a standalone 'buy the satellite tomorrow' rule. Strong next-session pairs (ret+lift bar): 15. Literature: spillover largely contemporaneous; volume can mark leaders intraday. Use as membership beta context / basket diversity check; not live first-mover entries. exploit_ready=false.

## Leader rank (who moves *with* the tape)

| Leader | Mean same-day corr | Lift same-day on +2% | Lift next-day on +2% | Frac pairs with lead edge |
|--------|-------------------:|---------------------:|---------------------:|--------------------------:|
| ETH-USD | 0.729 | 43.0% | -1.1% | 0.0% |
| LINK-USD | 0.718 | 39.7% | -0.1% | 0.0% |
| BTC-USD | 0.678 | 42.0% | 0.4% | 50.0% |
| SOL-USD | 0.674 | 39.1% | 0.4% | 22.2% |
| XRP-USD | 0.613 | 33.4% | 2.6% | 33.3% |

## Beta cohort (followers tightly tied to BTC+ETH)

### Tight (min corr ≥ 0.5 to both)

| Follower | Mean corr | Min corr |
|----------|----------:|---------:|
| DOGE-USD | 0.777 | 0.769 |
| ARB-USD | 0.735 | 0.661 |
| LINK-USD | 0.729 | 0.689 |
| MATIC-USD | 0.720 | 0.682 |
| AVAX-USD | 0.717 | 0.700 |
| ADA-USD | 0.714 | 0.703 |
| SOL-USD | 0.711 | 0.702 |
| AAVE-USD | 0.706 | 0.651 |
| DOT-USD | 0.700 | 0.664 |
| UNI-USD | 0.688 | 0.641 |
| OP-USD | 0.681 | 0.613 |
| BCH-USD | 0.680 | 0.665 |

### Loose (mean corr ≥ 0.55)

| Follower | Mean corr | Min corr |
|----------|----------:|---------:|
| DOGE-USD | 0.777 | 0.769 |
| ARB-USD | 0.735 | 0.661 |
| LINK-USD | 0.729 | 0.689 |
| MATIC-USD | 0.720 | 0.682 |
| AVAX-USD | 0.717 | 0.700 |
| ADA-USD | 0.714 | 0.703 |
| SOL-USD | 0.711 | 0.702 |
| AAVE-USD | 0.706 | 0.651 |
| DOT-USD | 0.700 | 0.664 |
| UNI-USD | 0.688 | 0.641 |
| OP-USD | 0.681 | 0.613 |
| BCH-USD | 0.680 | 0.665 |
| APT-USD | 0.673 | 0.647 |
| NEAR-USD | 0.671 | 0.648 |
| ATOM-USD | 0.658 | 0.633 |

## Next-session after leader +2% (aligned, gap≤3d)

Ranked by mean follower return next session. Lift = up-rate vs base.

| Leader | Follower | Same-day corr | Mean next ret | Next lift | Next up | N |
|--------|----------|--------------:|--------------:|----------:|--------:|--:|
| BTC-USD | XRP-USD | 0.643 | +1.06% | 3.4% | 51.4% | 146 |
| BTC-USD | ADA-USD | 0.703 | +0.72% | 2.9% | 48.6% | 146 |
| XRP-USD | AVAX-USD | 0.659 | +0.56% | 6.4% | 53.8% | 195 |
| XRP-USD | APT-USD | 0.534 | +0.52% | 5.4% | 50.8% | 195 |
| XRP-USD | OP-USD | 0.566 | +0.48% | 4.7% | 49.2% | 195 |
| BTC-USD | APT-USD | 0.647 | +0.46% | 4.0% | 49.3% | 146 |
| XRP-USD | DOT-USD | 0.645 | +0.45% | 5.6% | 49.7% | 195 |
| XRP-USD | LINK-USD | 0.673 | +0.43% | 3.2% | 51.8% | 195 |
| XRP-USD | LTC-USD | 0.647 | +0.42% | 3.4% | 53.3% | 195 |
| XRP-USD | ATOM-USD | 0.613 | +0.39% | 3.4% | 49.2% | 195 |
| XRP-USD | NEAR-USD | 0.546 | +0.37% | 4.3% | 50.8% | 195 |
| XRP-USD | AAVE-USD | 0.565 | +0.34% | 3.4% | 50.8% | 195 |
| XRP-USD | SOL-USD | 0.631 | +0.27% | 5.5% | 54.9% | 195 |
| SOL-USD | APT-USD | 0.669 | +0.27% | 4.0% | 49.4% | 235 |
| BTC-USD | OP-USD | 0.613 | +0.26% | 4.8% | 49.3% | 146 |

## Method notes

- Daily close-to-close returns from `backtests/data/long` (+ cache fetch).
- Thrust = leader day ≥ +2%.
- Next session only if calendar gap ≤ 3 days (blocks listing-gap false leads).
- Lift = P(follower up | thrust) − P(follower up unconditionally).
- Lead edge = corr(L_t, F_{t+1}) > corr(L_t, F_{t-1}) + 0.02.
- Not full Granger VAR; not intraday (lit often finds stronger BTC lead inside the day).

## Decision

- first_mover_cohort_exists (beta pack): **True**
- nature: `same_day_beta_pack_weak_next_session_lead`
- strong next-session pairs: **15**
- exploit_ready: **False**

JSON: `data/state/first_mover_leadlag_latest.json`

