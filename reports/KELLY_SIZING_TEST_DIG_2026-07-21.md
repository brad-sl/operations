# Kelly dig-further — 2026-07-21

**Trial:** `ANALYST-KELLY-SIZING-TEST-20260721-TRIAL`  
**Parent report:** `reports/KELLY_SIZING_TEST_2026-07-21.md`  
**Real data only:** True · **Live writes:** False

## Plain-English verdict

### No opportunity to promote Kelly sizing — out-of-sample edge failed.

The first report’s high Half-Kelly growth used the same trades to both estimate luck and size the bets (like grading a test with the answer key). When we only use early trades to set size and later trades to judge, Kelly does not beat careful small sizing. Do not turn on a Kelly shadow.

- **Recommendation enum:** `drop`
- **Shadow go?** **False**

### Why (short bullets)

- Train-period Kelly full fraction was 0.410; test-period edge Kelly was 0.000.
- On the later half of trades, measured edge was zero/negative — any size from early wins would have been betting a cold streak.
- Classic trap: early good results → large Kelly → later losses get amplified if you had sized up.
- Even with loose caps, half and full paths still look almost identical — edge on test is too weak for Kelly fraction to matter.
- Score growth−0.5×DD on test (loose): base=-30.1176, quarter=-69.1311, half=-69.1311, full=-69.1311
- Score growth−1.0×DD on test (loose): base=-41.9651, quarter=-95.2528, half=-95.2528, full=-95.2528
- Score growth−2.0×DD on test (loose): base=-65.66, quarter=-147.4962, half=-147.4962, full=-147.4962
- With live-like envelopes on test: half growth=-32.786 DD=41.1512 vs baseline growth=-18.2702 DD=23.6949.
- July+ slice: n=37, win rate p=0.189189, Kelly full=0.0 (if ≤0, recent book should not size up).

## What we added vs the first report

| Dig | Why it matters |
|-----|----------------|
| Walk-forward | Stops using the same trades to both invent Kelly and grade it |
| Scores growth−λ×DD | λ=2 = you hate drawdowns more; λ=0.5 = growth-chasing |
| Loose envelopes | Lets half vs full Kelly actually differ (first report caps made them identical) |
| Haircut grid | Concurrent multi-pair book needs smaller effective f |
| Time slices | Early vs July+ shows if edge died |

## Walk-forward summary

- Train n=35 (2026-05-01T00:02:17.854358Z → 2026-07-04T01:05:49.927862Z)
- Test n=35 (2026-07-04T16:13:39.269357Z → 2026-07-21T06:37:24.277277Z)
- Train: p=0.685714 b=1.141499 f_full=0.410387
- Test:  p=0.171429 b=1.283576 f_full=0.0

### Test window paths — size from **train** only, **loose** caps

| Path | Growth % | Max DD % | score λ=0.5 | λ=1 | λ=2 |
|------|----------|----------|-------------|-----|-----|
| baseline_1pct_risk | -18.2702 | 23.6949 | -30.1176 | -41.9651 | -65.66 |
| quarter_kelly | -43.0094 | 52.2434 | -69.1311 | -95.2528 | -147.4962 |
| half_kelly | -43.0094 | 52.2434 | -69.1311 | -95.2528 | -147.4962 |
| full_kelly | -43.0094 | 52.2434 | -69.1311 | -95.2528 | -147.4962 |

### Test window — size from train, **live-like** envelopes

| Path | Growth % | Max DD % | score λ=1 |
|------|----------|----------|-----------|
| baseline_1pct_risk | -18.2702 | 23.6949 | -41.9651 |
| quarter_kelly | -32.786 | 41.1512 | -73.9372 |
| half_kelly | -32.786 | 41.1512 | -73.9372 |
| full_kelly | -32.786 | 41.1512 | -73.9372 |

## Time-slice edge (crude regime proxy)

```json
{
  "pre_2026-07": {
    "n": 33,
    "edge": {
      "n": 33,
      "n_wins": 23,
      "n_losses": 10,
      "p": 0.69697,
      "b": 1.102731,
      "mean_win_r": 0.092003,
      "mean_loss_r": -0.083432,
      "f_full": 0.42217,
      "f_half": 0.211085,
      "f_quarter": 0.105542,
      "insufficient": false,
      "reason": null
    }
  },
  "from_2026-07": {
    "n": 37,
    "edge": {
      "n": 37,
      "n_wins": 7,
      "n_losses": 30,
      "p": 0.189189,
      "b": 1.148835,
      "mean_win_r": 0.031926,
      "mean_loss_r": -0.02779,
      "f_full": 0.0,
      "f_half": 0.0,
      "f_quarter": 0.0,
      "insufficient": false,
      "reason": null
    }
  },
  "full": {
    "n": 70,
    "edge": {
      "n": 70,
      "n_wins": 30,
      "n_losses": 40,
      "p": 0.428571,
      "b": 1.870122,
      "mean_win_r": 0.077985,
      "mean_loss_r": -0.041701,
      "f_full": 0.123015,
      "f_half": 0.061507,
      "f_quarter": 0.030754,
      "insufficient": false,
      "reason": null
    }
  }
}
```

## Haircut sensitivity (full sample, diagnostic)

See JSON for full grid. Rule of thumb: if only haircut=1 (no multi-asset cut) looks good, ignore it for live.

## Decide (Brad)

First report already leaned `drop`. Dig-further is the tie-breaker:

```bash
python3 phase6/research/trial_cycle.py decide ANALYST-KELLY-SIZING-TEST-20260721-TRIAL drop --note 'dig-further reports/KELLY_SIZING_TEST_DIG_*.md'
```

## Files

- `reports/KELLY_SIZING_TEST_DIG_2026-07-21.md`
- `reports/KELLY_SIZING_TEST_DIG_2026-07-21.json`

