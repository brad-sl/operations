# Preserve Venue Probe Plan (G1)

**Task:** `PRESERVE-FUNDAMENTALS-GATE-20260802`  
**Script:** `phase6/research/probe_paxg_stops.py`  
**Product:** `PAXG-USD`

## Procedure
1. Dry-run: `PYTHONPATH=. .venv/bin/python phase6/research/probe_paxg_stops.py`
2. Execute micro: `... probe_paxg_stops.py --execute --max-buy-usd 25`
3. Cleanup is automatic (cancel probe stops + market sell residual unless `--keep-inventory`).

## Tests
| ID | Check |
|----|--------|
| T1 | Metadata + price |
| T0 | Buy ≤ $25 PAXG if inventory insufficient |
| T2 | Single stop-limit SELL GTC (~−12% resting) |
| T4 | Second concurrent stop (~−18%) |
| T5 | Third concurrent stop (~−32%) |
| Cleanup | Cancel all + unwind |

## Result labels
- **A:** ≥2 concurrent OK  
- **B:** single only  
- **C:** cannot place / unreliable  

## Outputs
- `reports/PRESERVE_VENUE_PROBE_YYYY-MM-DD.md`
- `data/state/preserve_venue_probe_latest.json`
