#!/bin/bash
# Sentiment fetcher wrapper — uses project .venv + documented NumPy X86_V2 workaround for this CPU
export OPENBLAS_CORETYPE=GENERIC
cd "$(dirname "$0")"
source .venv/bin/activate
python3 "$@"
