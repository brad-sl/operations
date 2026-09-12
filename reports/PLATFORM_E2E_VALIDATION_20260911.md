# Platform E2E validation — 2026-09-12T02:09:41.295824+00:00

**SHA:** `dcb1bbb9` (PC-02/03) · A2 `cec08fd8`

## Verdict

**CONDITIONAL lab GO / money-path NO-GO scale.** Infra + integrity slices landed; funnel drought + exit tax + a few proof loops still inhibit ~5%/mo realization.

> tryout can_buy=`False` · NO-GO further live exit knob expansion without Brad

## OK

- runner pid=654873
- sensor not broken
- paper_primary=rel_btc_stable swaps_off

## Ranked missing / inhibiting functionality

### 1. [P0_money] 30d SL tax still material vs TP bank
- **id:** `G-EXIT-TAX`
- **detail:** SL $-84.61 vs TP $88.38 counts 6:9 n_sell=42
- **inhibits:** month_path less-loss / exit quality trust

### 2. [P0_ops] Tryout open but eng sent below floor — no seat can fill
- **id:** `G-FUNNEL-SENT`
- **detail:** Sleeve membership open but no eng-cleared door (AVAX-USD, ETH-USD, XRP-USD). Free/tee is not a green light.
- **inhibits:** green-day pickup / tryout BUY→SL proof

### 3. [P0_ops] Runner may predate A1/A2 deploy
- **id:** `G-RUNNER-RESTART`
- **detail:** pid=654873; restart to load bag_id+settle
- **inhibits:** protect next tryout fill

### 4. [P1] Recent BUYs lack bag_id (need runner reload or no post-A2 fills)
- **id:** `G-BAGID-ADOPTION`
- **detail:** 0/11
- **inhibits:** live lot-bind proof

### 5. [P1] L2 deployability scorer missing (PC-04)
- **id:** `G-L2-DEPLOY`
- **detail:** no would-runner-buy on paper ADDs
- **inhibits:** honest arm promote

### 6. [P1] Limit-first evidence starved (PC-05)
- **id:** `G-LIMIT-EVIDENCE`
- **detail:** zero tryout attempts → no fill-rate denominator
- **inhibits:** execution maturity

### 7. [P1] Attribution weekly RT loop not staffed (PC-06)
- **id:** `G-ATTR-LOOP`
- **detail:** stamps exist in code; weekly table/process not closed
- **inhibits:** learn tax vs edge

### 8. [P1_watch] 14d process book still WATCH (PC-09)
- **id:** `G-PROCESS-BOOK`
- **detail:** need manufactured SL leakage calendar
- **inhibits:** claim money-path complete

### 9. [P2] Shadow→live promote gate packet missing (PC-08)
- **id:** `G-PROMOTE-GATE`
- **detail:** auto_promote=false only
- **inhibits:** safe scale

### 10. [P2_parked] Portfolio risk kernel multi-file (PC-07)
- **id:** `G-RISK-KERNEL`
- **detail:** caps/tryout/park not one SSOT
- **inhibits:** multi-book

## Snapshots
- tryout: `{"can_buy": false, "eligible": ["AVAX-USD", "ETH-USD", "XRP-USD"], "floor": 0.35, "sensor_broken": false, "mode": "x_reddit_bridge", "cash": 200.00589129516365}`
- exits: `{"headline": "NO-GO further live exit knob expansion without Brad", "tp_bank": 88.381, "sl_bank": -84.6149, "tp_sl": "6:9", "blank": 0, "n_sell": 42}`
- ledger_7d: `{"buys": 11, "sells": 14, "buy_bag_id": "0/11"}`
- paper: `{"arm": "rel_btc_stable", "live_swaps": false}`

## Staff next (recommended)
1. Runner restart (A1/A2 load) — Brad OK
2. PC-04 L2 deployability
3. PC-05 limit-first counters (honest zero-attempt OK)
4. PC-06 attribution weekly
5. PC-09 14d process book watch
6. Hold PC-07/08 until above green
