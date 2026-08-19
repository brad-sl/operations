# Emerging pair discovery funnel

**Status:** Shadow implemented 2026-08-08  
**Code:** `phase6/core/pair_discovery.py`  
**CLI:** `scripts/phase6/run_pair_discovery_shadow.py`  
**Feeds:** `data/state/pair_discovery_contenders.json` → `pool_cycling` candidate source  

## Goal

Find **emerging high-energy** pairs with real upside potential — not rotate a fixed mediocre list for incremental reallocation.

## Stages (budget discipline)

| Stage | Name | Data (cost) | What it does |
|-------|------|-------------|--------------|
| 0 | Universe | Coinbase public `/products` (**free**) | ~USD online tradable spot; drop stables/wrappers |
| 1 | Prequal | Public `/stats` per product (**free**, parallel) | 24h notional volume floor, return, range → **energy** rank; top N only |
| 2 | Quality | Public hourly `/candles` on shortlist only (**free**) | 3d/7d momentum, vol expansion, volume acceleration |
| 3 | Deep | RSI / X sentiment (**paid — OFF by default**) | Only top K after quality; opt-in `--deep` (hook reserved) |
| 4 | Promote | Operator / `pool_cycling` shadow | Displace weak **active** basket names; never auto-apply live |

**Sentiment is never spent on the wide pass.**

## Promote gates (stage 4 eligibility)

- Passed quality min score  
- Not already in active basket (default)  
- Upside impulse: (mild 3d floor + non-negative 24h) **or** strong 3d mom ≥ +5%  
- Sticky core (BTC/ETH) never auto-ejected by cycler  

## Run

```bash
cd /home/brad/projects/crypto-trading-bot
. .venv/bin/activate
# Full pipeline (discover → RSI warm contenders → cycle shadow)
python scripts/phase6/run_discovery_pipeline_shadow.py
# Discovery only
python scripts/phase6/run_pair_discovery_shadow.py
```

### Cron (prove-out)
- Job: `phase6-discovery-pipeline-shadow`
- When: **10:15 and 22:15 PT** (Hermes `15 10,22 * * *`, local PT)
- Wrapper: `~/.hermes/scripts/run_discovery_pipeline_shadow.sh`
- Delivery: Telegram only if swap proposed or failure; full logs under `logs/discovery_pipeline_*.log`

## Outputs

- `data/state/pair_discovery_latest.json` — full report  
- `data/state/pair_discovery_contenders.json` — promote-eligible IDs for cycler  
- `data/state/pair_discovery_runs.jsonl` — run log  

## Non-goals (for now)

- Auto-mutate `global_settings.pairs`  
- Paid sentiment on 300+ names  
- Correlation/segment matrix (PAIR_SELECTION_MATRIX) — can layer on stage 2 later  
