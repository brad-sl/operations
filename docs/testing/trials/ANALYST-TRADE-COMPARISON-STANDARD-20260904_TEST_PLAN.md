# Test plan — ANALYST-TRADE-COMPARISON-STANDARD / TCS-002 shadow CF

**MASTER:** `ANALYST-TRADE-COMPARISON-STANDARD-20260904`  
**Backlog:** `ANALYST-20260904-TCS-001` (method) · `ANALYST-20260904-TCS-002` (shadow)  
**Edge class:** `ATTENTION_ONLY_less_loss_path`  
**Live cooldown gate:** OFF (shadow only)  
**Live LINK ticket:** ON — `rsi_primary_deploy.pair_ticket_caps["LINK-USD"]=150` (flat regime effective **$75** tonight)

---

## Goal

Validate correlation + boundary conditions with a **matched would-block CF**, then run a **shadow logger** long enough to see natural buy attempts — without auto-promoting process cooldowns.

## Hypotheses (testable)

| ID | Hypothesis | Pass signal (7d paper/shadow) |
|----|------------|-------------------------------|
| H1 | Post-SL reentry ≤48–72h raises P(pair SL soon) ~2× vs baseline | CF lift ≥1.5 on multipair; shadow logs fire on real post-SL attempts |
| H2 | Post-TP full-size rebuy is rare but high $ severity | CF n small; $ on sl-path high when present |
| H3 | RSI≥55 large ticket elevates risk when RSI stamped | CF lift ≥1.4 on large+RSI slice; missing RSI ≠ invented block |
| H4 | Pile-on is inventory (14d), not 72h timing OR | CF shows inverse/flat 72h; do not OR into shadow v1 |
| H5 | Alts ≫ majors for post-SL absolute risk | Book split holds on refresh |
| H6 | LINK $150 pair cap binds on rsi_primary path | Isolation + live plan note `pair_ticket_cap=150` if proposed >150 |

## Non-goals

- Live `evaluate_buy_entry` cooldown
- Claiming HIT_10 / printer edge
- Fixing SOL grind via TCS rules
- Force-rebalance to “test” LINK (path-integrity hole)

## Artifacts

| Piece | Path |
|-------|------|
| Core | `phase6/research/trade_comparison_standard.py` |
| Dig | `phase6/research/run_trade_comparison_dig.py` |
| **CF** | `phase6/research/run_trade_comparison_cf.py` → `data/state/trade_comparison_cf_latest.json` |
| **Shadow** | `phase6/research/run_tcs_shadow_would_block.py` → `data/state/tcs_shadow_would_block_latest.json` |
| LINK cap state | `data/state/link_procurement_cap_tonight.json` |
| Reports | `reports/TRADE_COMPARISON_CF_LATEST.md` |

## Runbook (commands)

```bash
cd /home/brad/projects/crypto-trading-bot && . .venv/bin/activate
export OPENBLAS_CORETYPE=GENERIC PYTHONPATH=.

# isolation
python phase6/research/test_isolation_trade_comparison_standard.py
python phase6/core/rsi_primary_deploy.py  # if __main__ smoke exists
python scripts/phase6/test_isolation_rsi_primary_deploy.py

# CF + shadow batch
python phase6/research/run_trade_comparison_cf.py
python phase6/research/run_tcs_shadow_would_block.py --with-cf

# prove LINK pair cap pure function
python - <<'PY'
from phase6.core.rsi_primary_deploy import apply_buy_size_gates, load_rsi_primary_config
import json
cfg=load_rsi_primary_config(json.load(open('config/trading_config_phase6.json')))
g=apply_buy_size_gates('LINK-USD', 500, rsi=44, sentiment=0.4, equity_usd=2300,
    current_pair_usd=0, rebalance_cap_usd=200, free_cash_usd=800, cfg=cfg)
assert g.final_usd <= 150, g
print('LINK cap OK', g.final_usd, g.notes)
PY
```

## Monitoring window

| Window | What to watch |
|--------|----------------|
| Tonight / next rebalance | LINK fill ≤ min(regime_cap, 150). Flat → **$75**. Log reason tags. |
| 48–72h | Any post-SL rebuy attempts → shadow would-block reasons if logger cron’d |
| 7d | Refresh CF; compare lift stability; false-positive majors |
| End | finalize-report → Brad `decide` (default: stay shadow) |

## Cadence

- **Once now:** CF + shadow replay + runner restart after pair_ticket_caps ship  
- **Daily Hermes cron (live):** `phase6-tcs-shadow-would-block` job_id `dd16da710656`  
  - schedule `25 12 * * *` PT · `no_agent` · `deliver=local` · `failure_deliver=origin`  
  - wrapper `~/.hermes/scripts/run_tcs_shadow_would_block.sh` → project `phase6/scripts/run_tcs_shadow_would_block.sh`  
  - writes CF + shadow latest JSON + `logs/tcs_shadow_would_block_latest.log`  
  - success = empty stdout (silent TG); FAIL line only on error  
- **Do not** TG-spam baseline scout heat

## Decision gate (Brad)

| Result | Action |
|--------|--------|
| CF lift decays / unstable | drop live cooldown; keep dig skill |
| Shadow fires cleanly, majors FP high | alt-only A48 shadow continue |
| LINK cap bypassed (fill >150) | path-integrity incident — fix wire, not dig |
| Want live A48 | separate GO after 7d + CR |

## Honesty

Process hygiene ≠ alpha. Dollar “saved” in CF is **notional on sl-path**, not banked PnL.
