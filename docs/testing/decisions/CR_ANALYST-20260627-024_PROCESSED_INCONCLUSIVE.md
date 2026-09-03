# CR — ANALYST-20260627-024

**Title:** Polymarket regime influence backtest  
**Processed:** 2026-09-02 (re-sealed after glitch + sensor_preflight bake-in)  
**Status:** processed_sensor_fail  
**Live promote:** **No** (Brad GO required; not requested)

## Result (offline backtest + sensor gate)

**Outcome: `sensor_degenerate`** (historical influence log)  
**Recommendation: `fix_sensor_or_data_pipeline` — do not promote allocator influence.**

### Plain English
1. **Historical `influence_stack_log` is a dead meter** for WR/ROI: risk_on_bias stuck at 0.5 (unique≈1, stdev=0) and event yes_p stamps also stuck at 0.5. Preflight **blocks scoreboard** — this is **not** “no edge,” it is **broken/degenerate sensor**.
2. **Root cause (fixed in code, not in old log):** Gamma `outcomePrices` often arrives as a JSON **string**; naive `[0]` indexing returned `'['` → fallback 0.5. Also polarity keywords missed Fed rate-cut framing so many markets collapsed to neutral sent_p.
3. **Live overlay after fix (2026-09-02 smoke):** bias left 0.5 (example ~**0.359** on 33 markets). Parser + polarity seal verified by isolation. **Historical log is not rewritten** — need fresh stamps / entry-time bias before any influence lift claim.
4. **Do not promote** allocator haircut / influence from 024.

### Bias stats (historical log)
```json
{
  "n_snapshots": "~168+",
  "n_unique_bias_3dp": 1,
  "bias_min": 0.5,
  "bias_max": 0.5,
  "bias_stdev": 0.0,
  "note": "preflight gates scoreboard"
}
```

### Artifacts
- Report: `reports/POLYMARKET_INFLUENCE_BACKTEST_20260902.md`
- JSON: `data/state/analyst_polymarket_influence_backtest_latest.json`
- Preflight: `data/state/sensor_preflight_polymarket_024_latest.json`
- Runner: `phase6/research/run_polymarket_influence_backtest.py`
- Sensor lib: `phase6/research/sensor_preflight.py`
- Isolation: `phase6/research/test_isolation_sensor_preflight.py`
- Overlay: `hermes/skills/crypto_analyst/polymarket_overlay.py`

### Process lesson (Test Validation)
**Scoreboards after sensor check only.** Degenerate/stuck feature ≠ inconclusive edge. Named classes: `sensor_broken` | `sensor_degenerate` | `sensor_thin` | `method_invalid`. See `docs/testing/TEST_REGIMEN_E2E.md` + `PROTOCOL_OFFLINE.md`.

### Follow-on (Brad GO 2026-09-02)
**Queued re-run trial:** `ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902`  
- Protocol: `docs/testing/trials/ANALYST-POLYMARKET-INFLUENCE-RERUN-20260902_PROTOCOL.md`  
- Why: bad 024 sensor data (stuck 0.5); post-fix stamps only; no reopen 024 as HIT  
- Also preferred later: entry-time bias on decision_context  
- Ops note: keep `~/.hermes/skills/crypto_analyst/polymarket_overlay.py` **in sync** with project copy (intel stamp path can load Hermes skill).

### Live promote
**No.**
