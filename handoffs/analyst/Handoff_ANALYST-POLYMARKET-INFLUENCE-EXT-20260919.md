# Handoff — ANALYST-POLYMARKET-INFLUENCE-EXT-20260919

## Mission
Extend Polymarket influence collect after parent `ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902` proved **sensor OK** but **edge N incomplete** (crypto n=10, risk_on n=0).

## Brad GO
2026-09-19: "A lack of trades renders the trial incomplete… Extend until we have enough data for relevance."

## Hard gates
- fix_cutoff: `2026-09-02T22:00:00+00:00`
- edge universe: **ex-stable** sells only
- relevance: crypto_joined≥15 OR (risk_on_n≥5 AND neutral_n≥5)
- hard_stop: `2026-10-10T18:03:08.367111+00:00`
- live_promote: **false**

## Commands
```bash
cd /home/brad/projects/crypto-trading-bot
PYTHONPATH=. .venv/bin/python3 phase6/research/run_polymarket_influence_health.py --verbose
PYTHONPATH=. .venv/bin/python3 phase6/research/run_polymarket_influence_backtest.py --rerun
PYTHONPATH=. .venv/bin/python3 phase6/research/trial_cycle.py status ANALYST-POLYMARKET-INFLUENCE-EXT-20260919
```

## Do not
- Live knobs / allocator influence wiring
- Infinite extend past hard_stop without new Brad GO
- Count USDT rotations as edge N
