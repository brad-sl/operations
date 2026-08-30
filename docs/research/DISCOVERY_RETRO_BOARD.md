# Discovery retro board — early-detect instrumentation

**Status:** shadow / research only  
**First ship:** 2026-08-29  
**Why-not + quiet features:** 2026-08-30  
**SSOT rule:** writes only its own report + state files. Never config, basket, exits, or runner.

## Question

For names exploding *today*, did any funnel name them at T−7 / T−3 / T−1?  
If **not**, **why not** (stage reject)?  
For names we named a week ago, did that cohort actually win forward?

That is the only honest test of “identify before it launches.” Not a buy signal.

## Run

```bash
cd /home/brad/projects/crypto-trading-bot
python3 scripts/phase6/run_discovery_retro_board.py
# or
~/.hermes/scripts/run_discovery_retro_board.sh
```

Cron: `phase6-discovery-retro-board-daily` · **23:00 PT** · `no_agent` · deliver local.

## Outputs

| Path | Role |
|------|------|
| `reports/DISCOVERY_RETRO_BOARD_LATEST.md` | Human board (lead + **why not** + quiet features) |
| `data/state/discovery_retro_board_latest.json` | Machine board (`schema: discovery_retro_board_v2`) |
| `data/state/discovery_retro_board_runs.jsonl` | Daily scoreboard crumbs |

## Lead classes

| Class | Meaning |
|-------|---------|
| EARLY ≥7d | First contender hit ≥7d before as_of — split into `true_early_flag` vs `chronic_watchlist` |
| MEDIUM 3–7d | Early impulse window |
| SHORT 1–3d | Often already moving |
| COINCIDENT &lt;24h | Found during/after the green day |
| NEVER | Exchange tape only |

## Why-not codes

| Code | Meaning |
|------|---------|
| `picked` | On contender list with usable promote path |
| `coincident_late` | Picked but lead &lt;24h (chase confirmation) |
| `pump_brake` | Contender but promote blocked (extended ret) |
| `promote_blocked` | Contender blocked (e.g. no_upside) |
| `thin_liquidity` | 24h quote vol under discovery floor (~$2M) |
| `below_prequal_cutoff` | Vol ok; lost energy top-N vs peers |
| `quality_fail` | Made energy screen; failed mom/vol quality |
| `contender_cutoff` | Quality pass; not in contender top-N |
| `active_basket` | Already seated — excluded from emerging list |

## Quiet features (research sketch)

Logged per gainer (candles + BTC-rel). **Post-move biased** when measured on explode day:

- `vol_dry_ratio` — prior quiet vol vs longer baseline  
- `liq_jump_24_vs_3d` — last 24h vol vs prior day avg  
- `btc_rel_3d` — 3d mom − BTC 3d mom  
- `compression_then_expand` — range expand after quiet body  
- `quiet_early_score` — composite sketch **not a gate**

Validate on frozen T−3/T−7 snapshots before trusting. Correlation, if any, is likely here — not more energy/mom.

## Discovery logging (feeds better why-not)

`pair_discovery_runs.jsonl` **schema v2** appends:

- `prequal_top` (full prequal window scores)  
- `quality_pass` / `quality_fail` (bounded)  
- `contenders_detail` (promote flags + reasons)

`pair_discovery_latest.json` now keeps **full** prequal window + **all** quality-ranked rows (was top-15 only).

## First snapshot (2026-08-29/30)

- True week-ahead explode hits on top gainers: **0**  
- Chronic EARLY (e.g. PUMP always on list): not pre-impulse radar  
- T−7 contender forward book: mean **~−7%**, hit&gt;0 **~8%**  
- HNT-class melt-up: **COINCIDENT** + pump-brake (working as designed)

## Path to a real method (if one exists)

1. Keep the retro board running (base-rate honesty + why-not distribution).  
2. Accumulate v2 stage ledgers so miss autopsy is evidence, not rebuild.  
3. Shadow-test **compression** arms using quiet features at first_seen (not on green day).  
4. Promote bar: standing forward book beats liquid-universe 7d base rate **and** fees/SL shadow — only then talk seats.

Until (4) clears: contenders remain an **attention list**, not an alpha sleeve.
