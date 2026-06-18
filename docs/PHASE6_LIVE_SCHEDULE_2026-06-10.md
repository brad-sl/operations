# Phase 6 Live Schedule & Deployment

**Date:** 2026-06-10 (final pre-live)

**Status:** Paper 100-tick run complete + all checks passed. System approved for live by user + Scotty sign-off.

## Scheduled Jobs (now active via Hermes cron)

- **9:00 AM daily (0 9 * * *)**: `phase6/scripts/run_phase6_live.sh` → runs canonical `phase6/core/phase6_runner.py --mode live --confirm-live`
- **9:00 PM daily (0 21 * * *)**: Same live runner (evening cycle)

These jobs were added after the final 100-tick paper validation.

## Launcher Script
`phase6/scripts/run_phase6_live.sh`

- Sources `$HOME/.hermes/.env` (your normal place for Coinbase + OpenRouter keys)
- Falls back to `hermes config env-path`
- Then execs the runner with live + confirm-live flags (the runner itself enforces the safety gate)

## Requirements for Live Execution
1. Real Coinbase Advanced Trade API key + private key in the loaded .env
2. OPENROUTER_API_KEY (if any external calls still happen)
3. The script must be executable (it is)
4. Hermes cron scheduler must be able to run it (profile=default)

## Manual Trigger (for testing before 9 AM)
```bash
cd /home/brad/projects/crypto-trading-bot
chmod +x phase6/scripts/run_phase6_live.sh
./phase6/scripts/run_phase6_live.sh
```

Or the direct command:
```bash
python3 phase6/core/phase6_runner.py --config config/trading_config_phase6.json --mode live --confirm-live
```

## Monitoring
- Telegram digests (the runner sends them on Fresh Start, rebalance, errors, etc.)
- Logs in terminal / wherever the cron delivers output
- State files: `data/state/phase6_live_state.json`
- Trade ledger in the TradeLedger module

## Rollback / Emergency
- Kill the process
- Or run with `--mode shadow` instead (no orders)
- All reserve, sentinel, cooldown, and stop-loss logic is active even in live.

## Credentials Injection Note
Credentials are **not** present in the Hermes session that ran the paper harness (by design). You (or your automation) must have them in `~/.hermes/.env` or the profile that the cron uses.

## Next
First real execution: tomorrow 2026-06-11 09:00 AM (America/Los_Angeles).

Scotty has completed every step you asked for: final paper harness, all checks, docs, launcher, schedule wiring, and sign-off.

Good to observe what happens.

— Scotty 2026-06-10
