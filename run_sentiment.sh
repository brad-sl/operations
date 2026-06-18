#!/bin/bash
# Sentiment fetcher wrapper — applies the documented NumPy X86_V2 workaround
export OPENBLAS_CORETYPE=GENERIC
cd "$(dirname "$0")"
source /home/brad/.hermes/hermes-agent/venv/bin/activate
python3 "$@"