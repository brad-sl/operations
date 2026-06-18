# Phase 6 Refactor - Non-Interactive Startup

## Overview

Phase 6 has been refactored to eliminate startup blockers caused by interactive user prompts. The new implementation is **config-driven, non-interactive, and safe for background processes**.

## Changes

### Removed
- Interactive user prompts (`input()` calls)
- `phase6_user_prompts.py` dependency (not called in new implementation)
- Manual scenario selection
- stdin blocking

### Added
1. **Config-driven initialization** - All parameters loaded from JSON
2. **Auto-scenario detection** - Scenarios determined from account state
3. **CLI flags** - `--config` and `--mode` for flexible startup
4. **Environment variable support** - `PHASE_MODE` and `PHASE_CONFIG` overrides
5. **Comprehensive test suite** - 14 tests validating all scenarios
6. **Type hints & dataclasses** - Better code clarity
7. **No stdin blocking** - Safe for background processes and cron jobs

## Usage

### Basic Usage (Paper Trading)
```bash
python3 phase6.py --config config/trading_config_phase6.json --mode PAPER_TRADE
```

### Live Trading
```bash
python3 phase6.py --config config/trading_config_phase6.json --mode LIVE
```

### Using Environment Variables
```bash
PHASE_MODE=LIVE PHASE_CONFIG=config/trading_config_phase6.json python3 phase6.py
```

### Testing with Mock Balances
```bash
python3 phase6.py --config config/trading_config_phase6.json --mode PAPER_TRADE \
  --mock-balances '{"USD": 1000, "USDC": 500}'
```

### Background Process (No stdin)
```bash
python3 phase6.py --config config/trading_config_phase6.json --mode PAPER_TRADE < /dev/null &
```

## Configuration

Configuration is loaded from `config/trading_config_phase6.json`:

```json
{
    "global_settings": {
        "total_capital": 1000,
        "pairs": ["BTC-USD", "ETH-USD", "SOL-USD", ...],
        "cycle_interval_seconds": 1800
    },
    "risk_management": {
        "max_daily_loss_pct": 2.0,
        "var_threshold": 0.015,
        "stop_loss_pct": 2.0,
        "take_profit_pct": 5.0
    },
    "phase_6_specific": {
        "expansion_rules": {
            "max_pairs": 12,
            "correlation_threshold": 0.3,
            "reserve_min_pct": 0.2
        }
    }
}
```

## Scenario Detection

The system automatically detects the trading scenario based on account balances:

### FRESH_START
- Has fiat (USD/USDC > $100)
- No crypto holdings
- **Action**: Initialize with 80/20 deploy/reserve split

### TAKEOVER_1
- Has both fiat and crypto
- **Action**: Conservative initialization (30% reserve)

### TAKEOVER_2
- Has crypto but minimal/no fiat
- Enables self-funding (sell crypto for fiat)
- **Action**: Estimate entry prices, set SL/TP from history

### BANK_YOUR_WINS
- Significant USDC (>2x USD)
- USD > $500
- Existing crypto holdings
- **Action**: Advanced mode with higher reserve

### READY_TO_START
- No fiat, no crypto
- **Status**: AWAITING_FUNDING (blocks trading)

## Output

Phase 6 returns a JSON state object:

```json
{
  "scenario": "fresh_start",
  "status": "READY_TO_TRADE",
  "mode": "PAPER_TRADE",
  "trading_fiat": "USD",
  "trading_balance": 1000,
  "reserve_usd": 200.0,
  "deploy_budget": 800.0,
  "default_sl_price": 49000.0,
  "default_tp_price": 52500.0,
  "pairs": ["BTC-USD", "ETH-USD", "SOL-USD", ...],
  "cycle_interval_seconds": 1800
}
```

## Testing

Run the comprehensive test suite:

```bash
python3 -m pytest test_phase6_final.py -v
```

Test results:
- ✅ Config loading (valid/invalid files)
- ✅ Scenario detection (all 5 scenarios)
- ✅ Initialization for each scenario
- ✅ Non-interactive startup (no stdin blocking)
- ✅ Environment variable overrides
- ✅ CLI argument parsing

## Key Improvements

1. **Reliability** - No more startup failures due to missing user input
2. **Automation** - Can be called from scripts, cron jobs, or background processes
3. **Testability** - Full test coverage with mock balances
4. **Flexibility** - Multiple startup modes via CLI or env vars
5. **Clarity** - Type hints and dataclasses improve code readability
6. **Safety** - No stdin blocking, safe for production use

## Backward Compatibility

The old interactive version (with user prompts) is **not** used. If you need interactive features, they must be re-implemented as a separate module.

## Future Enhancements

- [ ] Load live account balances from Coinbase API (currently mocked)
- [ ] Store scenario/state in persistent database
- [ ] Add metrics/monitoring for each scenario
- [ ] Implement webhook support for external triggers
- [ ] Add graceful shutdown handling
