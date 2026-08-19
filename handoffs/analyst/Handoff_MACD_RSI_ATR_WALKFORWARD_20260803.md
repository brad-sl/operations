# Handoff — wf

**Status:** CLOSED (drop)
**Decision:** drop @ 2026-08-03T22:40:52.038506+00:00
**Note:** Brad 2026-08-03: drop. Short-window ~+5% F2 did not survive Coinbase long-tape walk-forward (2021-2026 EW mean -20%, BTC F2 -53%). No standard opt / no live. Keep lessons: kill 4-way AND stack; RSI filter > MACD-only; no Stoch/BB required entry. Residual regime-gate idea only if Brad reopens.

---
(prior content below)

# Handoff — MACD RSI ATR walk-forward

**Status:** REPORT_READY  
**Parent:** TEST-COMBINED-INDICATOR-ABLATION-2026-08  
**Rec:** `unstable_or_no_edge`  
**When:** 2026-08-03T22:38:13.072558+00:00

## Plain English
Long-tape walk-forward **rejects** F2 as a standard ~5% optimization. Multi-year mean **−20%**; BTC **−53%**. Short-window +5% was regime-specific.

## Decide lean
Parent trial: **drop** champion-as-standard-opt, or narrow to pre-registered regime-gate dig only (Brad OK).

## Artifacts
- reports/MACD_RSI_ATR_WF_PLAIN_ENGLISH_2026-08-03.md
- reports/MACD_RSI_ATR_WALKFORWARD_2026-08-03.md
- data/state/trials/TEST_MACD_RSI_ATR_WALKFORWARD.json
