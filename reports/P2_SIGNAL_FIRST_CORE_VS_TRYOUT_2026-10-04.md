# P2 — Signal-first (core vs tryout by RSI+sent+TP path)

**Brad GO:** 2026-10-04  
**Replaces:** flat ballast-before-shell as the primary capital rule  
**Product law:** Go to the pair with **strong aged eng + sane RSI + TP path**. Core vs tryout is a **role**, not a priority queue. Powder/USDC/PAXG only when **nothing** clears the bar.

## Evidence (why)

Stamped TP winners (not edge claim — n thin):

| Pair | Entry RSI | Entry sent | Exit | PnL |
|------|-----------|------------|------|-----|
| LINK | ~46 | **0.54** | trail TP | +$2.36 (+ earlier fixed TP) |
| SOL | ~39 | **0.38** | trail TP | +$2.43 |
| ZEC | ~48 | **0.89** | fixed TP | +$1.48 |

Weak-sent opens (TIA/HYPE ~0.02–0.03) → scale-window eject tax.  
Attribution weekly: edge claim still **OFF** (need ~20 clean RTs).

## Live changes

1. **`quality_tryout.min_sentiment` 0.30 → 0.35** (`config/regime_cash_policy.json`)  
   - Door-package shell block aligned to 0.35  
   - Composer floor resolves from this SSOT  
2. **Decision discipline** (`config/tryout_decision_discipline.json` + code)  
   - Hard veto: `min_eng_absolute=0.35` → `STAND_DOWN` / `skip_seat` when live_apply  
   - `min_sent_clear_noul` 0.30 → 0.55  
   - Setup mix weights eng higher (0.40 sent)  
3. **Seat ranker** `select_buy_candidate`  
   - Was: deep wash first (`(rsi_max-rsi)*2 + eng*10`)  
   - Now: **eng×120 + wash + mid-RSI TP-band bonus (30–52)**  
   - Strong mid-RSI beats weak deep-wash when both clear floor  
4. **Not changed:** shell $25, seats 6, SL+trail, no auto-promote, USDC powder (P1), kindling eject rules, dual_agree promote

## Operator read

- Empty board (sent ~0 like 2026-10-04 afternoon) → **honest wait / powder**, not force shell  
- Next aged X with eng≥0.35 + RSI door → seat that pair even if tryout (not “BTC first”)  
- Rollback: min_sentiment 0.30; discipline thresholds to pre-P2; ranker formula comment in git

## Proof

```bash
PYTHONPATH=. .venv/bin/python scripts/phase6/test_isolation_tryout_decision_discipline.py
PYTHONPATH=. .venv/bin/python scripts/phase6/test_isolation_tryout_seat_buy_action.py
# live floor:
PYTHONPATH=. .venv/bin/python -c "from phase6.core.rsi_event_tryout_seat_composer import _regime_tryout_params; print(_regime_tryout_params())"
```

## Out of scope

- No membership swap / dual_agree  
- No force rebalance  
- No permanent door package  
- No edge claim from thin N  
