# Environment Notes – Phase 6 Backtesting

## CPU Compatibility Issue (X86_V2 / AVX2)

This machine has an older CPU that does not support the X86_V2 instruction set (AVX2).  
NumPy wheels built with these optimizations will crash on import.

### Solution

Always run backtest scripts with `OPENBLAS_CORETYPE=GENERIC`:

```bash
OPENBLAS_CORETYPE=GENERIC python3 phase6_backtest.py --days 365 --real-data
```

### Recommended Wrapper

Use the provided helper script:

```bash
./run_backtest.sh phase6_backtest.py --days 365 --real-data
```

This sets the required environment variable automatically.

### Persistence

- `export OPENBLAS_CORETYPE=GENERIC` has been added to `~/.bashrc`
- The wrapper script `run_backtest.sh` is the preferred method for explicit, documented execution.

### Verification

- Tested successfully with `phase6_backtest.py --days 30` and `--days 90`
- No more `RuntimeError: NumPy was built with baseline optimizations: (X86_V2)`

Last updated: 2026-05-25
