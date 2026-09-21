# Crypto Process Lifecycle

| Field | Value |
|-------|--------|
| **ID** | `FEAT-CRYPTO-PROCESS-LIFECYCLE-2026-09` |
| **Status** | `DRAFT` · living coverage map (not a ship commit) |
| **Class** | FEAT / PRODUCT VOICE |
| **Owner** | Brad + platform |
| **Updated** | 2026-09-19 |
| **Supersedes for navigation** | Do **not** implement from `docs/FUNCTIONAL_SPEC.md` (LEGACY). Prefer this + `docs/SPECS_INDEX.md` + live config. |
| **Companions** | [`CRYPTO_PROCESS_TRADER_VOICE.md`](./CRYPTO_PROCESS_TRADER_VOICE.md) (client copy) · [`TAKEOVER_NORMALIZE_PLAYBOOK.md`](./TAKEOVER_NORMALIZE_PLAYBOOK.md) (ops) · `docs/faq/Internal_Trading_Platform_FAQ.md` · `docs/plans/2026-09-11-platform-completeness.md` · `docs/plans/2026-09-15-luck-ladder-platform-refine.md` · `docs/SPECS_CODE_GAP.md` |

---

## 0. Purpose

Single **operator/product outline** of the crypto trading lifecycle:

1. How a trader **gets on** (Fresh vs Takeover)
2. What the system does in **steady state** (Manage)
3. How risk **grows, rotates, learns, and closes**
4. What is **LIVE / ARMED / SHADOW / GAP / OUT** as of the updated date

This is a **coverage map**, not alpha claims and not multi-tenant GA.

**Mission order:** trust → less-loss proof → net edge → scale multi-book.  
North star remains deposit-adj take-home; process tax (SL leakage/fees) is first-class, not “missing alpha.”

---

## 1. Onboarding modes (product concept)

Two entry products. Same **Manage** machinery after the book is coherent; different **Provision** paths.

### 1.1 Fresh (cash-first) — preferred economics in backtests

| | |
|--|--|
| **Definition** | Trader starts (or resets) with **cash / USDC-dominant** book. Platform **allocates** into the process-controlled universe under size/risk shells. |
| **Story** | “We build the book clean.” |
| **Evidence posture** | Historical backtests favored **dynamic Fresh / clean init** over legacy static or messy inherited books (see archive comparison notes; treat as **directional lab evidence**, not a live multi-tenant SLA). |
| **Why it wins (hypothesis)** | No toxic inherited bags; episode/lot identity clean from first fill; tryout→exit→graduate ladder can run without ghost peaks / wrong SL / emotional bags. |
| **Platform hooks** | `fresh_start` scenario · allocator / ARCH-4 deploy path · tryout shell · park unused cash (Smart Park / powder). |
| **Status** | **PARTIAL_LIVE** on operator book (single-tenant Phase 6). **Not** self-serve SaaS onboarding. |

**Fresh provision sequence (target):**

```text
deposit / connect
  → detect Fresh (cash-dominant, no unmanaged alt soup)
  → optional Smart Park on undeployed cash
  → roster = process basket (membership)
  → deploy only via qualify gates (tryout / graduated rules)
  → every lot gets SL + bag_id from first fill
  → enter Manage
```

### 1.2 Takeover (existing Coinbase book)

| | |
|--|--|
| **Definition** | Trader already holds **allocated crypto** on Coinbase. Platform **inherits** positions and must **respect, protect, then gradually process-normalize** — not instantly “make it Fresh.” |
| **Story** | “We take the wheel without a forced fire-sale.” |
| **Hard truth** | Takeover is **harder and usually less clean** than Fresh: mixed lots, no bag_id history, possible naked bags, user attachment, wrong size vs shell, names outside universe. |
| **Platform hooks** | `takeover` / `takeover_2` style detection · holdings-respected init · protectives reattach · liquidate/trim non-process names over time (GO) · never silent full dump on day one unless user chooses Close Down. |
| **Status** | **PARTIAL_LIVE** detection + “holdings respected” paths exist in lineage; **no** polished product takeover playbook as a closed FEAT. |

**Takeover provision sequence (target):**

```text
connect + read balances
  → classify: keep / tryout-eligible / non-process / ballast (e.g. PAXG)
  → attach protectives (fail-closed where naked)
  → optional: user picks “normalize toward Fresh” speed (slow trim vs GO liquidate)
  → new risk only via same Qualify/Open rules as Fresh
  → inherited bags: Care first, Graduate later (no auto size-up on junk)
  → enter Manage
```

### 1.3 Product rules (onboarding)

| Rule | Why |
|------|-----|
| **Prefer Fresh for new capital** when the user can choose | Backtests + process control; cleaner episodes |
| **Offer Takeover without shame** | Real users have bags; refusing them is not a product |
| **Never imply Takeover = Fresh edge** | Different starting entropy; claims must stay mode-tagged |
| **No auto-promote membership or full redeploy on Takeover day 1** | Trust product; Brad/user GO for violent normalize |
| **Park is valid in both modes** | Idle cash ≠ failure; control arm while Manage/repair runs |
| **Multi-tenant OAuth onboarding** | **OUT** of this doc’s LIVE scope (Scaling-1000); concept only |

---

## 2. Lifecycle stages (steady vocabulary)

```text
PROVISION → QUALIFY → OPEN → CARE → GROW → ROTATE → LEARN → GRADUATE/DEMOTE → CLOSE
```

Learn runs **continuously** beside Care/Grow (not only at the end).

### Status tags

| Tag | Meaning |
|-----|---------|
| **LIVE** | On operator money/ops path today |
| **ARMED** | Path built + decision on; money still explicit GO/CLI |
| **SHADOW** | Measure / would-fire; no orders from that path |
| **PARTIAL** | Code or ops exist; incomplete proof or UX |
| **GAP** | Needed for honest E2E product; not closed |
| **OUT** | Explicit non-goal near-term |

---

### 2.1 Provision

| Step | Meaning | Status |
|------|---------|--------|
| Initial deposit / capital event | Cash appears; deposit-adj KPIs | **LIVE** |
| Mode detect Fresh vs Takeover | Scenario classification | **PARTIAL** |
| Smart Park / powder / PAXG micro | Undeployed cash control arm | **LIVE** (micro; full package careful) |
| Roster (basket seats) | Who *may* sit — not who is bought | **LIVE** (manual/dual_agree GO; auto swaps **OFF**) |
| Initial deploy policy | Size shells, seats/day, tryout vs full | **LIVE** ($25×4 tryout shell as of 2026-09-19 door package; confirm live config) |

**Gap:** one operator “onboarding wizard” that chooses Fresh vs Takeover and shows plain-English consequences.

---

### 2.2 Qualify (doors — not buys)

| Step | Meaning | Status |
|------|---------|--------|
| Tryout / thaw / ledger / hard-block doors | Eligible to *compete* for a seat | **LIVE** |
| RSI wash / structure | Washed enough to consider | **LIVE** gate + **SHADOW** event path (R0) |
| Knife vs wash | Avoid falling knife | **SHADOW** (R1) |
| Sent real (fresh X / latch ≥ floor) | Decision-quality sentiment | **LIVE** primary X; free/Jev **SHADOW** |
| Rank top doors | Cap concurrent new risk | **LIVE** (seat counters; stables excluded from tryout seat burn) |

**Happy path strip** (target process, not a claim fills always flow):  
`door → wash → knife OK → sent real → rank → open`

---

### 2.3 Open (new risk)

| Step | Meaning | Status |
|------|---------|--------|
| Buy **new** pair (tryout) | Micro shell + limit-first + SL | **LIVE** (path proven intermittently; funnel still chokes) |
| Buy **established** pair | Graduated / normal ticket | **PARTIAL** (first_fill graduate + size rules; not full printer) |
| Naked-bag fail-closed (A1) | No unprotected lot | **LIVE** code |
| Episode / bag_id (A2) | Lot-true lifecycle | **LIVE** code · **PARTIAL** live N proof |

**Established means packet, not tenure:** clean RTs, not missfire-locked, size step rules, Brad GO where required — **not** “been in basket a while.”

---

### 2.4 Care (held book)

| Step | Meaning | Status |
|------|---------|--------|
| Exchange SL | Hard floor | **LIVE** |
| Take profit / trail / software exit | Bank progress | **LIVE** (tax vs bank still contested) |
| Rebalance **held** weights | Trim/top book only — no new tryout invent | **LIVE** / evolving (BookRebalance dry arch) |
| Protective reattach (CR-03) | After rebalance; preserve pairs safe | **LIVE** (PAXG deep E1 discipline) |
| Cooloff after wound | Post-SL rebuy block | **LIVE** |
| Liquidate non-performing (discretionary) | Beyond SL | **PARTIAL** (operator hard-exit; not full product) |

---

### 2.5 Grow (add to winners / shells)

| Step | Meaning | Status |
|------|---------|--------|
| Mid-flight scale-up (R5) | One step add on tryout bag | **SHADOW** + **ARMED** live path |
| Approval ping | TG when `n_planned > 0` | **LIVE** cron (plan only) |
| Money apply | CLI `--apply --go --no-dry-run` | **ARMED** · not auto |
| CF / waive budget | Evidence bar or capped waive | **PARTIAL** (waive seeds path data ≠ edge) |

**Rule:** Grow ≠ Open. Adds are Manage, not Provision.

---

### 2.6 Rotate (roster)

| Step | Meaning | Status |
|------|---------|--------|
| Add / remove basket names | Membership | **LIVE** via GO swap tools; **auto OFF** |
| Novelty class gate | Time-bounded probation, not permanent ban | **LIVE** shortlist layer |
| Dual_agree paper write | Seriously-consider signal | **LIVE** paper / TG hygiene |

---

### 2.7 Learn (continuous)

| Step | Meaning | Status |
|------|---------|--------|
| Ledger RT / attribution | Tax vs edge | **PARTIAL** (boards; habit/N) |
| Luck ladder R0–R6 | Controllable luck factors | **SHADOW** fleet (R5 path armed) |
| Platform metrics spine | Funnel choke board | **LIVE** measure |
| Analyst trials + closeout watchdog | Forced decide, no quiet death | **LIVE** ops |
| Jev judgment lab | Fuzzy noul/score layer | **SHADOW** · not money path |

---

### 2.8 Graduate / Demote

| Step | Meaning | Status |
|------|---------|--------|
| Name graduation | May keep sitting / exit tier-C jail | **PARTIAL** (ledger, thaw, force-eligible, novelty) |
| Size graduation | Shell → larger ticket | **PARTIAL** / **ARMED** (R5 + first_fill) |
| Promote shadow arm → live | Evidence + Brad GO | **GAP** (PC-08); auto-promote **OFF** |
| Demote / block (funnel) | Missfire, post-SL 72h, same-day seat, novelty restricted | **LIVE** · default path |
| Perma-block (`buy_block_pairs`) | Nuclear never-buy — toxic **beyond** funnel | **LIVE** · **rare** (scars: RAVE, UNI) |

**Funnel-first:** filter toxicity in qualify / missfire / novelty / process locks.  
**Do not** grow `buy_block_pairs` into a second membership jail.  
**Do not auto-advance “old pairs.”** Re-qualify or packet + GO.

---

### 2.9 Close Down

| Step | Meaning | Status |
|------|---------|--------|
| Flatten alts | Liquidate trading risk | **PARTIAL** (manual/operator) |
| Move to cash / park | USDC / Preserve / PAXG | **LIVE** micro paths |
| Kill switches | e.g. scale-up KILL, door expiry | **LIVE** where wired |
| Stop minting seats | Freeze Open | **LIVE** (blocks, armor, kill) |

**Gap:** first-class “wind down this trader book” one-call action (Fresh-end or Takeover exit).

---

## 3. Map: user draft → lifecycle

| Your draft bullet | Stage | Notes |
|-------------------|-------|--------|
| Initial deposit | Provision | Capital event |
| Allocate to trading pairs | Provision | Split **roster** vs **deploy** |
| Take profits | Care | Trail/TP |
| SL out | Care | Exchange SL |
| Add free capital to existing pairs | Grow | R5 scale-up |
| Liquidate non-performing | Care / Close | SL auto; discretionary **GAP**/partial |
| Add/remove potential pairs | Rotate | GO; auto off |
| Buy new with new pairs | Open (tryout) | Micro shell |
| Buy new with established pairs | Open (graduated) | Packet-defined |
| Test new pairs | Qualify + Open tryout | Not “basket = bought” |
| Test old pairs? | Learn + Graduate/Demote | **No auto-advance** |
| Liquidation + move to cash | Close | Wind-down **GAP** as productized flow |

---

## 4. Fresh vs Takeover through the lifecycle

| Stage | Fresh | Takeover |
|-------|-------|----------|
| Provision | Allocate clean under shells | Inventory + protect + classify; slow normalize |
| Qualify / Open | All new risk from cash | New risk same gates; inherited ≠ graduated |
| Care | Standard | Priority: naked bags, wrong SL, dust, non-universe names |
| Grow | After tryout packet | **Stricter** — don’t scale inherited junk |
| Rotate | Build roster deliberately | Often **remove** non-process names first |
| Learn | Clean episodes | Tag RTs `inherited` vs `process_open` |
| Close | Flatten process book | User may keep ballast; define “done” |

**Backtest lesson (product voice, honest):**  
Fresh path looked **much more profitable** in historical init comparisons. That supports **selling Fresh as the default high-trust path** and Takeover as **“we’ll stabilize, then process-normalize”** — not as the same expected edge on day one.

---

## 5. Coverage scoreboard (honest, dated 2026-09-19)

| Area | Grade | One-line |
|------|-------|----------|
| Provision (operator single book) | B | Deposits/park/roster work; no self-serve wizard |
| Fresh economics as product default | B− | Concept + lab evidence; not SaaS GA |
| Takeover as product | C | Detect/respect holdings; normalize playbook thin |
| Qualify doors | B+ | Tryout/thaw/sent live; knife still shadow |
| Open tryout | B | Path works in windows; funnel reliability not solved |
| Care exits | B− | Stack live; **process tax not won** |
| Grow scale-up | B− | Armed + approval TG; money E2E unproven |
| Rotate membership | B | GO tools; auto correctly OFF |
| Learn / luck ladder | B | Rich shadows; promote still human |
| Graduate/promote | C+ | Partial size/name; PC-08 gap |
| Close down product | C | Manual; no one-call wind-down |
| Multi-trader onboarding | D | Scaling-1000 **OUT** near-term |

**Overall:** lifecycle is **specified enough to steer**; **not** “functional complete E2E.” Closest prior epic: platform completeness PC-01…09 + luck ladder.

---

## 6. Non-goals (this FEAT)

- Auto membership swaps or auto-promote from paper green  
- Claiming Takeover matches Fresh backtest edge without mode tags  
- Jev / free sentiment as live primary  
- Multi-tenant GA / GHL paid funnel (separate epic)  
- Implementing from LEGACY `FUNCTIONAL_SPEC.md`

---

## 7. Staff-next (when Brad prioritizes)

1. Keep proving **Fresh-like** money path on operator book (funnel → exit tax → R5 GO adds).  
2. ~~Write **Takeover normalize playbook**~~ → **DONE draft:** [`TAKEOVER_NORMALIZE_PLAYBOOK.md`](./TAKEOVER_NORMALIZE_PLAYBOOK.md).  
3. ~~Trader-facing one-pager~~ → **DONE draft:** [`CRYPTO_PROCESS_TRADER_VOICE.md`](./CRYPTO_PROCESS_TRADER_VOICE.md).  
4. Productize **Close Down** one-call (shared Fresh/Takeover).  
5. Implement playbook T0–T2 state artifact + naked-bag dashboard tile (see playbook §9).  
6. Refresh FAQ happy path numbers ($25×4, door dates, R5 approval).  
7. Only then: Scaling-1000 onboarding UX that offers Fresh (default) vs Takeover (advanced).

---

## 8. Revision log

| Date | Change |
|------|--------|
| 2026-09-19 | Initial draft from Brad lifecycle outline + Fresh/Takeover onboarding concept; coverage tags vs live Phase 6. |
| 2026-09-19 | Child specs: trader voice one-pager + Takeover normalize playbook; companions linked. |
