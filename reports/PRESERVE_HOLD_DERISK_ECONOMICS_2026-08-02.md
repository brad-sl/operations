# Preserve Hold vs DeRisk economics — 2026-08-02

**Status:** OFFLINE G2a/G2b — not live
**JSON:** `/home/brad/projects/crypto-trading-bot/data/state/preserve_hold_derisk_economics_latest.json`

## Decisions
- Hold E1 (−32%) non-fire on 2026 −28% arm-at-peak path: **True**
- **Default product: Hold**
- **DeRisk: disabled by default** (`KEEP_DISABLED_DEFAULT`)

## Ugly path — arm at 2026-01-28 peak
```json
{
  "label": "ugly_arm_at_2026-01-28",
  "start": "2026-01-28",
  "end": "2026-08-02",
  "gold_dd_from_arm_pct": -28.067,
  "static20": {
    "ret": -5.359,
    "dd": -5.609
  },
  "hold_e1": {
    "ret": -5.359,
    "dd": -5.609,
    "fired": "none"
  },
  "derisk": {
    "ret": -4.1,
    "dd": -4.188,
    "fired": "S1@3,S2@51",
    "term_w": 0.0611
  },
  "verdict_fragment": "DeRisk realizes sells into drawdown; Hold keeps gold unless -32% from arm."
}
```

## Ugly path — arm at 2022-03-08 peak
```json
{
  "label": "ugly_arm_at_2022-03-08",
  "start": "2022-03-08",
  "end": "2022-10-26",
  "gold_dd_from_arm_pct": -21.14,
  "static20": {
    "ret": -3.854,
    "dd": -4.225
  },
  "hold_e1": {
    "ret": -3.854,
    "dd": -4.225,
    "fired": "none"
  },
  "derisk": {
    "ret": -3.609,
    "dd": -3.745,
    "fired": "S1@119,S2@191",
    "term_w": 0.067
  },
  "verdict_fragment": "DeRisk realizes sells into drawdown; Hold keeps gold unless -32% from arm."
}
```

## Windows (summary)
### full (2020-08-28 → 2026-08-02, n=2166)
Gold path max DD: -28.067% | end vs start: 105.295%
| Arm | Return% | MaxDD% | Fired | Term gold wt |
|-----|--------:|-------:|-------|-------------:|
| USDC_0 | 0.0 | 0.0 | n/a | 0.0 |
| USDC_4apy | 26.172 | 0.0 | n/a | 0.0 |
| static_20pct | 21.018 | -11.554 | none | 0.2 |
| hold_e1_m32 | 21.018 | -11.554 | none | 0.3389 |
| derisk_ladder | 6.483 | -5.588 | S1@185,S2@759 | 0.1541 |
| static_100pct | 105.089 | -28.067 | none | 1.0 |

### d2022_gold_dd (2022-03-01 → 2023-01-01, n=307)
Gold path max DD: -21.14% | end vs start: -5.394%
| Arm | Return% | MaxDD% | Fired | Term gold wt |
|-----|--------:|-------:|-------|-------------:|
| USDC_0 | 0.0 | 0.0 | n/a | 0.0 |
| USDC_4apy | 3.34 | 0.0 | n/a | 0.0 |
| static_20pct | -1.098 | -4.441 | none | 0.2 |
| hold_e1_m32 | -1.098 | -4.441 | none | 0.1911 |
| derisk_ladder | -1.449 | -4.264 | S1@184 | 0.1439 |
| static_100pct | -5.489 | -21.14 | none | 1.0 |

### d2026_gold_dd (2026-01-20 → 2026-08-02, n=195)
Gold path max DD: -28.067% | end vs start: -15.52%
| Arm | Return% | MaxDD% | Fired | Term gold wt |
|-----|--------:|-------:|-------|-------------:|
| USDC_0 | 0.0 | 0.0 | n/a | 0.0 |
| USDC_4apy | 2.105 | 0.0 | n/a | 0.0 |
| static_20pct | -3.121 | -6.275 | none | 0.2 |
| hold_e1_m32 | -3.121 | -6.275 | none | 0.1742 |
| derisk_ladder | -2.962 | -6.045 | S1@140 | 0.1305 |
| static_100pct | -15.604 | -28.067 | none | 1.0 |

### last_12m (2025-08-02 → 2026-08-02, n=366)
Gold path max DD: -28.067% | end vs start: 20.781%
| Arm | Return% | MaxDD% | Fired | Term gold wt |
|-----|--------:|-------:|-------|-------------:|
| USDC_0 | 0.0 | 0.0 | n/a | 0.0 |
| USDC_4apy | 3.997 | 0.0 | n/a | 0.0 |
| static_20pct | 4.132 | -8.185 | none | 0.2 |
| hold_e1_m32 | 4.132 | -8.185 | none | 0.2317 |
| derisk_ladder | 4.132 | -8.185 | none | 0.2317 |
| static_100pct | 20.66 | -28.067 | none | 1.0 |

### last_18m (2025-01-31 → 2026-08-02, n=549)
Gold path max DD: -28.067% | end vs start: 44.767%
| Arm | Return% | MaxDD% | Fired | Term gold wt |
|-----|--------:|-------:|-------|-------------:|
| USDC_0 | 0.0 | 0.0 | n/a | 0.0 |
| USDC_4apy | 6.061 | 0.0 | n/a | 0.0 |
| static_20pct | 8.924 | -9.273 | none | 0.2 |
| hold_e1_m32 | 8.924 | -9.273 | none | 0.2655 |
| derisk_ladder | 8.924 | -9.273 | none | 0.2655 |
| static_100pct | 44.622 | -28.067 | none | 1.0 |

## Plain English
- **Hold + E1−32%** matches static hold on paths that never reach −32% from entry (including the measured −28% 2026 episode if armed at that peak).
- **DeRisk** sells into the hole; compare return/DD on ugly paths before ever enabling.
- Behavioral value of Preserve remains: ballast while crypto parked — not gold day-trading.
