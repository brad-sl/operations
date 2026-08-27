# Handoff P6-DUAL-PEAK-NO-RED-EPISODE-20260826

## Done
- No dual/extension half-trim when mark < entry*(1+min_green)
- dual_peak_max_trims_per_lot=1; rearm only if peak_price > peak_at_last_dual_peak
- Legacy last_trim_kind=dual_peak counts as spent
- SL unchanged for downside

## Verify
PYTHONPATH=. python3 scripts/phase6/test_isolation_dual_peak_p0_gates.py
