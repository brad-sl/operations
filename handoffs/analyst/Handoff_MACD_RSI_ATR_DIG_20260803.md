# Handoff — macd dig

**Status:** CLOSED (drop)
**Decision:** drop @ 2026-08-03T22:40:52.038506+00:00
**Note:** Brad 2026-08-03: drop. Short-window ~+5% F2 did not survive Coinbase long-tape walk-forward (2021-2026 EW mean -20%, BTC F2 -53%). No standard opt / no live. Keep lessons: kill 4-way AND stack; RSI filter > MACD-only; no Stoch/BB required entry. Residual regime-gate idea only if Brad reopens.

---
(prior content below)

# Handoff — MACD× RSI ATR dig (child of combined ablation)

**Status:** REPORT_READY
**Parent MASTER:** TEST-COMBINED-INDICATOR-ABLATION-2026-08
**Trial parent:** TEST-COMBINED-INDICATOR-ABLATION-20260803-TRIAL
**Generated:** 2026-08-03T22:29:33.999351+00:00

## Recipe locked
MACD bullish cross + RSI(14)&lt;40 → exit 2×ATR trail + MACD-death; no Stoch/BB; skip deep-bear/weak names when universe expands.

## Plain English
- Pattern **solid** as structure.
- **Not** a clean 10–20% portfolio edge yet (core4 mean ~+5%).
- Selective 10%+ pickup: **SOL +13.7%** only.
- RSI filter mandatory; MACD-only dies.
- Do not promote live; shadow OK.

## Artifacts
- Brief: `reports/MACD_RSI_ATR_PATTERN_BRIEF_2026-08-03.md`
- Dig report: reports/MACD_RSI_ATR_DIG_2026-08-03.md
- JSON: data/state/trials/TEST_COMBINED_MACD_RSI_ATR_DIG.json
- Runner: phase6/research/macd_rsi_atr_dig.py

## Suggested parent decide posture
Keep parent `dig_further` with champion arm **F2**; do not claim 10–20% standard opt until longer tape or multi-TF confirm.
