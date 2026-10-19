# E-ALT-SHELL-SL-CAREER (2026-10-19)

**W-PROCESS-TAX-ALT-SHELL-SL / E-ALT-SHELL-SL-CAREER**

One honest career packet for this week's dominant process-tax line (ADA / TIA / LINK exchange stops).
Measure-only. **No knobs flipped. No orders. No runner restarts.**

**Window:** 2026-10-12 → 2026-10-19 UTC (TIA entry 2026-10-11 and LINK re-seat chain included).

## Verdict (10 lines)

1. Week primary tax −$12.03 WR 0/6 is these three exchange stops (+dust), not TP meat.
2. Ledger chain PnL ADA −$5.93 · TIA −$4.09 · LINK −$2.01 · sum −$12.03 (SL −$11.87 + dust −$0.17 ) ≈ weekly primary.
3. Roles are **not the same**: ADA = liquid flat-cap first stack ~$75; TIA = paper-kindled tryout ~$50 after TP proofs; LINK = $25 tryout shell.
4. All three SLs are exchange STOP_LIMIT at **~8%** (NEEDLE-04 live_default 8%). Not a 3% fuse. Buy stamps on ADA/TIA showed `sl_attached=false` (naked at fill); stop still filled later as exchange SL.
5. LINK is the re-seat leak: same-day buy→SL Oct 12, dwell demote 72h ban, then two ~$25 buys Oct 16 (ban just expired) + Oct 17.
6. TIA demote-on-SL fired correctly; no post-SL reseat. ADA never tryout-lot; no demote; no reseat.
7. CF 3% vs actual would have lost ~$7.00 less on these three (dead-path tags) but MFE before 3% touch was &lt;1% on all three — W2 *class*, not a live GO. TIA later printed +3.5% MFE-to-exit (3% would have cut a path that went green).
8. **Already shipped** C2/D2/intake (2026-10-17) and dwell demote (2026-10-06) cover the two biggest process levers (don't reseat shells under-ballast; don't restack after proof then SL). This week's seats mostly **predate** the 10/17 GO.
9. Default from this packet: **no SL knob**. Watch next week under live D2+intake. W2 stays shadow. Bank-trail stays Sunday-gated.
10. Explicit never: global 8%→3%, PAXG, Kelly, dual_agree auto, blow flat $75, edge claim from N=3.

## Cross-cut

| Pair | Size band | Role | Notional | Hold_h | SL PnL | SL % | MFE&lt;3% | Reseats after SL | Dwell demote |
|------|-----------|------|----------|--------|--------|------|---------|------------------|--------------|
| ADA-USD | flat_cap_near_75 | `liquid_flat_cap_first_stack` | ~$75 | 47.99 | −$5.89 | -8.01% | 0.57% | 0 | False |
| TIA-USD | mid_30_60 | `tryout_shell_paper_kindled` | ~$51 | 24.0 | −$4.01 | -8.10% | 0.71% | 0 | True |
| LINK-USD | tryout_leq_30 | `tryout_shell` | ~$25 | 10.51 | −$1.96 | -8.03% | 0.94% | 2 | True |

Week tax check: SL sum −$11.87 + dust −$0.17 = −$12.03 vs weekly primary −$12.03.

## Careers

### ADA-USD

**Role:** `liquid_flat_cap_first_stack` · size_band `flat_cap_near_75` · ~$75 notional at flat B cap $75; tryout_lot noop_absent; NOT $25 tryout shell. order_executor_buy, RSI-oversold + sentiment.

| Step | Timestamp (UTC) | Price | Qty | Notional / PnL | Note |
|------|-----------------|-------|-----|----------------|------|
| Entry | 2026-10-12T16:01:50.387546Z | 0.24319 | 308.39449824 | ~$74.9985 | order_executor_buy · rsi 23.16 sent 0.963391 |
| SL attach | post-buy (NEEDLE-04) | — | — | 8% band | buy stamp sl_attached=false (naked at fill); SL later realized as exchange STOP_LIMIT |
| SL hit | 2026-10-14T16:01:05.960069Z | 0.2237 | 302.22660827 | −$5.89 (-8.01%) | stop_loss_exchange · STOP_LIMIT · oid 3897e10a-362b-427c-ba16-dd5ce0ecf2ff |
| Dust | 2026-10-15T02:24:02.234432Z | 0.21992 | 6.16788997 | −$0.04 | dust_sweep_after_sl |
| Hold | 47.99 h | — | — | chain −$5.93 | buy→SL |

**CF (sl_width_3v8, this SL ts):** era `post_needle_8pct` · tag `3pct_helped_dead_path` · MFE before 3% touch 0.57% · MFE to actual exit 0.57% · sim 3% PnL -2.4254501325509876 · delta 3%−actual 3.4649468674490125 · went_green≥1% False

**Dwell:** demoted_on_sl=False · demote_ts=None · tryout_ban_until=None · current=None/None

**Re-seat / cooloff:**
- No re-seat after SL in window
- Hours SL→first reseat: None
- Ban vs reseat: n/a (no reseat)

Ledger oids: buy `53a1c507-93ca-429c-b85f-89f242fd5747` · SL `3897e10a-362b-427c-ba16-dd5ce0ecf2ff` · bag `ADA-USD:53a1c507-93ca-429c-b85f-89f242fd5747`

### TIA-USD

**Role:** `tryout_shell_paper_kindled` · size_band `mid_30_60` · ~$51 notional (~2×$25 step). paper_scaled=True live_scaled=False; post-proof graduated then re-seated; sentiment-led.

| Step | Timestamp (UTC) | Price | Qty | Notional / PnL | Note |
|------|-----------------|-------|-----|----------------|------|
| Entry | 2026-10-11T16:01:58.067417Z | 0.5877 | 86.0 | ~$50.5422 | order_executor_buy · rsi 53.64 sent 0.362557 |
| SL attach | post-buy (NEEDLE-04) | — | — | 8% band | buy stamp sl_attached=false (naked at fill); SL later realized as exchange STOP_LIMIT |
| SL hit | 2026-10-12T16:01:56.125752Z | 0.5401 | 84.28 | −$4.01 (-8.10%) | stop_loss_exchange · STOP_LIMIT · oid adfe983e-9028-45d4-9c05-04d93c325298 |
| Dust | 2026-10-12T21:35:47.148029Z | 0.5413 | 1.72 | −$0.08 | dust_sweep_after_sl |
| Hold | 24.0 h | — | — | chain −$4.09 | buy→SL |

**CF (sl_width_3v8, this SL ts):** era `post_needle_8pct` · tag `3pct_helped_dead_path` · MFE before 3% touch 0.71% · MFE to actual exit 3.47% · sim 3% PnL -1.6345347480000054 · delta 3%−actual 2.3771932519999943 · went_green≥1% True

**Dwell:** demoted_on_sl=True · demote_ts=2026-10-12T21:35:44.119899Z · tryout_ban_until=2026-10-15T21:35:44.119899Z · current=demoted/tryout_shell

**Re-seat / cooloff:**
- No re-seat after SL in window
- Hours SL→first reseat: None
- Ban vs reseat: n/a (no reseat)

Ledger oids: buy `096fdd85-3f02-44cd-8fb3-4f071d918f8c` · SL `adfe983e-9028-45d4-9c05-04d93c325298` · bag `TIA-USD:096fdd85-3f02-44cd-8fb3-4f071d918f8c`

### LINK-USD

**Role:** `tryout_shell` · size_band `tryout_leq_30` · ~$25 notional limit_first_buy; tryout_lot noop_absent; classic ≤$30 unproven shell.

| Step | Timestamp (UTC) | Price | Qty | Notional / PnL | Note |
|------|-----------------|-------|-----|----------------|------|
| Entry | 2026-10-12T05:31:32.056993Z | 13.365 | 1.87 | ~$24.9926 | limit_first_buy · rsi 53.64 sent 0.043422 |
| SL attach | post-buy (NEEDLE-04) | — | — | 8% band | SL attach at buy unknown; exit is exchange stop |
| SL hit | 2026-10-12T16:02:04.619658Z | 12.292098360655737 | 1.83 | −$1.96 (-8.03%) | stop_loss_exchange · STOP_LIMIT · oid 6effe3e5-754a-4315-ae48-270a7d496234 |
| Dust | 2026-10-13T00:53:42.207633Z | 12.323 | 0.04 | −$0.04 | dust_sweep_orphan |
| Hold | 10.51 h | — | — | chain −$2.01 | buy→SL |

**CF (sl_width_3v8, this SL ts):** era `post_needle_8pct` · tag `3pct_helped_dead_path` · MFE before 3% touch 0.94% · MFE to actual exit 0.94% · sim 3% PnL -0.8071123499999998 · delta 3%−actual 1.1562976500000004 · went_green≥1% False

**Dwell:** demoted_on_sl=True · demote_ts=2026-10-13T00:52:23.459950Z · tryout_ban_until=2026-10-16T00:52:23.459950Z · current=demoted/tryout_shell

**Re-seat / cooloff:**
- Re-seat BUY 2026-10-16T04:02:27.472617Z qty 2.01 entry 12.396 notional ~$24.916 reason limit_first_buy oid ccc5d9a2-9691-48c3-9e5c-722b4d45e8a6
- Re-seat BUY 2026-10-17T04:01:21.508554Z qty 2.02 entry 12.316 notional ~$24.8783 reason order_executor_buy oid e1670f53-28b1-4cb0-a37b-b128e756194e
- Hours SL→first reseat: 84.01
- Ban vs reseat: ban until 2026-10-16T00:52:23.459950Z; first reseat 2026-10-16T04:02:27.472617Z; hours after ban 3.17; expired=True

Ledger oids: buy `2cd329af-b5fc-4731-89d1-9164384217b3` · SL `6effe3e5-754a-4315-ae48-270a7d496234` · bag `LINK-USD:2cd329af-b5fc-4731-89d1-9164384217b3`


## LINK re-seat chain (cooloff / intake facts)

1. 2026-10-11 02:16 limit_first ~$25 then 04:46 **scale-window eject** −$0.34 (prior-day, not this week's primary tax).
2. 2026-10-12 05:31 limit_first ~$25 → 16:02 exchange SL −$1.96 (~10.5h, same calendar day). Dust orphan 10-13 00:53 −$0.04.
3. Dwell demote `sl_exit` 2026-10-13T00:52 · `tryout_ban_until` 2026-10-16T00:52 (72h, matches config `demote.post_sl_cooloff_hours=72`).
4. 2026-10-16 04:02 limit_first ~$25 — **~3.2h after ban expired** (not a ban breach; an immediate re-seat at expiry).
5. 2026-10-17 04:01 order_executor_buy ~$25, `sl_attached=false` at stamp — second lot (book later shows LINK ~$48).
6. Scale-window post-eject cooloff is 24h and applies to **eject**, not SL. SL path uses dwell 72h ban. Intake hygiene + D2 went live **later the same day** as the second reseat (2026-10-17 GO ~23:38). Honest read: this leak is **pre-GO residual**, not proof that live D2/intake failed.

## Optimize returns / reduce losses (ranked)

**1. Intake / cooloff / same-name re-seat after SL** — `ALREADY_LIVE_WATCH`
- Evidence: LINK same-day buy→SL Oct 12 (~10.5h, −$1.96). Dwell demote-on-SL fired; tryout_ban_until 2026-10-16T00:52; first re-seat 2026-10-16T04:02 (~3h after ban expired) then second ~$25 lot 2026-10-17T04:01. TIA did not re-seat after SL. ADA did not re-seat.
- Do not re-implement. D2 ballast-before-shell + intake hygiene went LIVE 2026-10-17 (after these LINK reseats). Next week: if same-name reseat still prints under D2, then a later GO could extend post-SL pair cooloff — measure first.

**2. Role mis-size: ADA $75 liquid first-stack vs $25 tryout shell** — `ALREADY_LIVE`
- Evidence: ADA notional ~$75 (flat B cap), tryout_lot noop_absent, order_executor_buy. SL −$5.89 is the week's largest tax line because size was cap-full on an unproven alt while ETH$0 / BTC~$53.
- D2 flat_deploy_priority live_apply=true (reserve_before_shell). C2 ballast floor live. Do not re-implement. Do not blow cap $75.

**3. TIA post-proof dwell then re-seat then SL demote** — `ALREADY_LIVE`
- Evidence: TIA TP-trail proofs Oct 6 (+$0.64) and Oct 8 (+$0.59), graduated, re-seated Oct 11 ~$50 (paper_scaled=true, live_scaled=false), SL Oct 12 −$4.01, demote-on-SL + 72h tryout ban. No post-SL reseat in window.
- post_proof_dwell live_apply already ON (GO 2026-10-06). Do not touch dwell knobs.

**4. 3% fuse on unproven shells that never printed ≥+2% MFE (W2 class)** — `GO_LATER_AFTER_SHADOW`
- Evidence: CF tags all three week SLs 3pct_helped_dead_path. Numeric 3% vs actual ≈ +$7.00 (ADA ~+$3.46, TIA ~+$2.38, LINK ~+$1.16). MFE before 3% touch: ADA +0.57%, TIA +0.71%, LINK +0.94% — none ≥+2%. TIA later printed +3.47% MFE-to-exit (would have been cut by 3%). Thin N=3. Not an edge claim.
- W2 already WIRED_SHADOW_PENDING_14D live_apply=false (started ~2026-10-13). This packet supports the *class*, not a live_apply flip. Never global 0.08→0.03.

**5. Bank/trail vs wide SL on green-then-die** — `MEASURE_ONLY`
- Evidence: None of the three printed ≥+2% MFE before a 3% fuse would cut. TIA had modest later green (+3.47% MFE-to-exit) then died to 8%. ETH prior-week career is the green-then-die ballast case (do not mix). Bank-trail-while-green remains MEASURE_ONLY / Sunday N_INSUFFICIENT.
- Do not GO bank-trail from this packet. Keep Sunday gate. Prefer already-live trail+dwell.

**6. Door quality / intake hygiene** — `ALREADY_LIVE`
- Evidence: ADA RSI 23.16 + sentiment 0.96 (not sentiment-only). TIA sentiment-only. LINK Oct 12 RSI 53.64 / sent 0.043 (weak sent, limit_first). Intake bars raised Brad GO 2026-10-17 (eng≥0.40 / setup≥1.7 / conf≥0.60) after these seats.
- Do not re-implement tryout_decision_discipline. Watch next week under raised bars + D2.


## GO / already-live / NO-GO

### Already shipped (do not duplicate)

- C2 ballast_under_target_floor live_apply=true (2026-10-17)
- D2 flat_deploy_priority live_apply=true reserve_before_shell (2026-10-17)
- tryout_decision_discipline intake bars raised + live_apply (2026-10-17)
- post_proof_dwell live_apply ON + demote on_sl (GO 2026-10-06)
- tryout_scale_window live + 24h post-eject cooloff (not the SL path)
- E-ETH-BALLAST-SL-CAREER 2026-10-12 (no SL knob)
- W2 3% shell fuse wired shadow, live_apply=false
- bank-trail-while-green MEASURE_ONLY

### What Brad could GO later (not this card)

- W2 live_apply only after 14d shadow gate + Brad letter GO — not from this packet
- If next week still reseats LINK/ADA after D2+intake, measure an extended post-SL pair cooloff
- Bank-trail-while-green only via Sunday gate, not this RCA

### Never from this packet

- global stop_loss_pct 0.08 → 0.03
- PAXG preserve / scale_path
- Kelly / deploy_pct promote
- dual_agree auto-promote
- blow flat cap $75
- live_apply flips in this card
- edge/promote claim from N=3
- re-implement C2/D2/intake/dwell

### Default GO

**no SL knob · no live_apply flips · CAREER_DONE measure**

Watch one more week under already-live D2 + intake. If LINK/ADA still reseat after SL while ETH$0, then a **new** measure card on post-SL cooloff length — still not a global 8→3.

## Attachments

- W-PROCESS-TAX-ALT-SHELL-SL
- E-ALT-SHELL-SL-CAREER
- Weekly: reports/ANALYST_WEEKLY_TRADE_REVIEW_AGENT_LATEST.md
- ETH context (not this week's $): reports/E_ETH_BALLAST_SL_CAREER_2026-10-12.md
- CF: data/state/sl_width_3v8_cf_latest.json
- Dwell: data/state/post_proof_dwell.json
- Verify-close (C2/D2/intake already LIVE): reports/WEEKLY_SUGGESTIONS_VERIFY_CLOSE_2026-10-19.md

## Data artifact

See `data/state/e_alt_shell_sl_career_latest.json` (rebuilt by this script).

## Notepad (measure notes)

- open_suggestions: W-PROCESS-TAX-ALT-SHELL-SL → **CAREER_DONE** (this packet); other weekly IDs already LIVE/CAREER_DONE per verify-close.
- go_queue: nothing new from this RCA. Do not enqueue global SL, PAXG, Kelly, dual_agree, cap $75.

---
Script: scripts/phase6/run_alt_shell_sl_career.py (one-call rebuild)
Run: 2026-10-19T23:18:27.119444+00:00
No live orders touched. No config mutated.
