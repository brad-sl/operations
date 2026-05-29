#!/bin/bash
# Wrapper to run Phase 6 backtests on this CPU (avoids X86_V2 NumPy crash)
export OPENBLAS_CORETYPE=GENERIC
exec python3 "$@"
