# Stand-down filter C — shadow board

**As of:** 2026-09-03T18:20:06.395635+00:00  
**Mode:** shadow only · **no orders · no config**  
**Primary rule:** process entry would-block when `r24 ≥ 5.0%`

## Plain English

- Would-block now (primary): **7** pairs
- Soft elevated: **10** pairs
- Strict heat: **0** pairs
- Edge class (from dig): `ATTENTION_ONLY_less_loss_path`
- Live gate: **NO** (shadow log only)

C is a **less-loss stand-down** candidate, not a money printer.

## Would-block (primary)

- **SOL-USD** r24=5.286963513920995 r6=3.0699596575814336 rsi=None · r24=5.3>=5, soft_r24=5.3, soft_r6=3.1
- **XRP-USD** r24=9.069230195990752 r6=5.583609868705808 rsi=None · r24=9.1>=5, soft_r24=9.1, soft_r6=5.6
- **DOGE-USD** r24=9.846531614487407 r6=6.995933987084424 rsi=None · r24=9.8>=5, soft_r24=9.8, soft_r6=7.0
- **PENGU-USD** r24=8.779182879377444 r6=5.707196029776673 rsi=None · r24=8.8>=5, soft_r24=8.8, soft_r6=5.7
- **LINK-USD** r24=5.888699091971605 r6=3.1800262812089475 rsi=None · r24=5.9>=5, soft_r24=5.9, soft_r6=3.2
- **UNI-USD** r24=6.310503701402914 r6=-1.3324791800128133 rsi=None · r24=6.3>=5, soft_r24=6.3
- **ARB-USD** r24=8.703703703703702 r6=0.014815912289800615 rsi=None · r24=8.7>=5, soft_r24=8.7

## Caveats

- Shadow only — does not block live fills
- Primary rule frozen at r24>=5 from 90d dig; N elevated exits was small
- Calm process was also red on dig sample — C is less-loss on heat, not a printer
- No capital-reuse path CF; fees still dominate churn
- No evaluate_buy_entry / runner / knobs wiring without Brad GO

## Artifacts

- `data/state/standdown_filter_c_shadow_latest.json`
- `data/state/standdown_filter_c_shadow_events.jsonl`
- `reports/STANDDOWN_FILTER_C_SHADOW_LATEST.md`

