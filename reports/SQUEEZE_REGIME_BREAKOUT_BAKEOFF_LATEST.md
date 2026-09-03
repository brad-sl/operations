# Squeeze → regime → confirm bake-off
As of `2026-08-19T19:41:09.597673+00:00`

## Plain English

Best squeeze-family arm on 7d: S3_regime_eff mean=+4.28% N=10 FB3d=0.2 C0b breakout+RSI 7d mean=-0.84% N=387 BH BTC always 7d mean=+0.14% Squeeze stack is setup+confirm research; exploit_ready stays false until Brad + stability checks.

## Arms (net of ~20bps RT fee)

| Arm | N | 1d mean/hit | 3d mean/hit | 7d mean/hit | FB 3d |
|-----|--:|------------|------------|------------|------:|
| `C0_breakout_sticky` | 794 | -0.11% / 43% (n=794) | -0.03% / 48% (n=794) | +0.14% / 48% (n=794) | 52% |
| `C0b_breakout_rsi` | 387 | -0.12% / 43% (n=387) | -0.26% / 45% (n=387) | -0.84% / 43% (n=387) | 55% |
| `S1_squeeze_break_confirm` | 13 | +0.72% / 46% (n=13) | +1.15% / 69% (n=13) | +1.76% / 62% (n=13) | 31% |
| `S2_regime` | 13 | +0.72% / 46% (n=13) | +1.15% / 69% (n=13) | +1.76% / 62% (n=13) | 31% |
| `S3_regime_eff` | 10 | +0.99% / 50% (n=10) | +2.48% / 80% (n=10) | +4.28% / 70% (n=10) | 20% |
| `S3b_regime_eff_rsi` | 3 | +1.26% / 67% (n=3) | +1.52% / 33% (n=3) | -0.36% / 67% (n=3) | 67% |
| `M2_coil_then_b4` | 39 | -0.12% / 38% (n=39) | +0.65% / 51% (n=39) | +1.92% / 46% (n=39) | 49% |
| `BH_btc_always` | 1965 | -0.15% / 45% (n=1965) | -0.05% / 50% (n=1965) | +0.14% / 49% (n=1965) | — |
| `BH_ew_always` | 1965 | -0.11% / 49% (n=1965) | +0.06% / 50% (n=1965) | +0.44% / 50% (n=1965) | — |

## Decision

- primary_paper: `None`
- exploit_ready: **False**

Spec: `docs/research/SQUEEZE_REGIME_BREAKOUT_RESEARCH.md`
JSON: `data/state/squeeze_regime_breakout_bakeoff_latest.json`

