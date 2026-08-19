# SCALING-1000 Phase A-01 — Brand / Domain / Identity Decision Pack

**Task:** `t_cff262a8` (PHASE-A-01)  
**Date:** 2026-07-16  
**Owner:** Marketing Strategist (R) · **Accountable:** Brad (A)  
**Status:** RECOMMENDED — awaiting Brad sign-off (do **not** purchase domain or publish public brand yet)  
**Related:** MKT plan, UNIFIED roadmap Q1, REV01 gap #1  

---

## 1. Decision needed from Brad (sign here)

| # | Decision | Recommendation | Brad choice |
|---|----------|----------------|-------------|
| D1 | Public product name | **ARCH Automation** | [ ] Approve · [ ] Alt: ________ |
| D2 | Primary domain | **arch-automation.com** | [ ] Approve · [ ] Alt: ________ |
| D3 | App / connect host | **app.arch-automation.com** (after host + cert) | [ ] Approve · [ ] Alt: ________ |
| D4 | Support inbox | **support@arch-automation.com** | [ ] Approve · [ ] Alt: ________ |
| D5 | Ops / noreply | **ops@** (internal) · **noreply@** (transactional) | [ ] Approve |
| D6 | GHL Location display name | **ARCH Automation — Pilot** | [ ] Approve |
| D7 | Legal entity line (footer) | TBD with counsel (use “ARCH Automation” as DBA/product until entity formalized) | [ ] Note |
| D8 | Logo kit | Accept draft kit in `docs/marketing/brand/assets/` | [ ] Approve · [ ] Revise |

**Sign-off block**

```
Brad decision date: ________
Approved name: ________
Approved domain: ________
Notes / constraints: ________
```

Until D1–D2 are signed, copy/funnel/SEO treat name as **working placeholder** (already true in MKT plan).

---

## 2. Recommendation summary (executive)

**Lock “ARCH Automation”** as the public product brand, separate from Brad’s personal Phase 6 bot identity.  
**Primary domain: `arch-automation.com`** (DNS probe + RDAP 404 as of 2026-07-16: no live nameservers observed; treat as *likely available* — re-check at registrar before buy).  
**Support: `support@arch-automation.com`** via domain email forward or Google Workspace / Zoho after domain is owned.  
**GHL Location:** rename/display as **ARCH Automation — Pilot** so CRM identity matches product, not personal Telegram/ops.

This unblocks funnel copy, SEO brand terms, SaaS product labels, OAuth connect URL host planning, and GHL Location branding without bleeding Brad’s live wallet into marketing.

**Do not purchase domain or point public ads** until legal/host readiness (task constraint + UNIFIED).

---

## 3. Name analysis

### 3.1 Working name: ARCH Automation

| Lens | Assessment |
|------|------------|
| Meaning | “Arch” = structure / gateway / architecture of disciplined automation; “Automation” = category clarity for SaaS |
| Fit to product | Matches MKT positioning: software + automation access on trader’s Coinbase, not a fund |
| Memorability | Strong short first word; full name is descriptive (good for trust / compliance-adjacent category) |
| SEO | Exact-ish “arch automation” is workable; pair with high-intent non-brand later (“Coinbase Advanced automation”, “Coinbase OAuth portfolio bot”) |
| Separation from personal | Clear product noun; not “Brad’s bot” |

### 3.2 Collision / crowding notes (research, not legal opinion)

Public “Arch” brands exist in other verticals (e.g. private markets **Arch** / arch.co; manufacturing **Arch Systems** / archsys.io; contractor marketing **Arch** / getarch.com). UK/industrial entities also use “Arch Automation” style names.  

**Implication:** We are not alone on the word “Arch.” Risk is **confusion in search and trademarks**, not automatic block. Mitigations:

1. Always use full **ARCH Automation** in first mention + domain `arch-automation.com`.  
2. Category tagline on every surface: *Coinbase portfolio automation software*.  
3. Avoid bare “Arch” in ads/legal without “Automation.”  
4. Optional counsel trademark search before heavy paid spend (Phase C / post-T1).  

**Not a reason to abandon** the working name unless Brad prefers a more unique coined name.

### 3.3 Alternatives (if Brad rejects ARCH Automation)

| Option | Domain ideas (research only) | Pros | Cons |
|--------|------------------------------|------|------|
| **A. ARCH Automation** (rec) | arch-automation.com | Continuity with all plan docs; clear | “Arch” crowded; industrial name collisions |
| **B. Arch Rebalance** | archrebalance.com (likely free on dig) | Product-specific verb | Longer; still Arch-prefix |
| **C. CoinArch** | coinarch.app (probe) | Crypto-native | Generic; trademark noise; less “software” |
| **D. ArchTrade** | archtrade.io (probe) | Short | Sounds exchange/broker-y (compliance risk) |
| **E. Coined** (e.g. Rebalis, Portstack) | TBD | Unique trademark path | Loses plan continuity; more rename work |

**Marketing default if silent:** Option A.

---

## 4. Domain research (2026-07-16) — research only, no purchase

Method: public DNS (`dig` NS/A) + RDAP where reachable. **Not** a registrar cart guarantee. Re-verify at Namecheap/Cloudflare/Google Domains at purchase time.

| Domain | DNS probe | RDAP note | Recommendation |
|--------|-----------|-----------|----------------|
| **arch-automation.com** | No NS/A observed | HTTP 404 / empty (not registered looking) | **Primary pick** |
| use-arch.com | Flaky / no clear A | 404-looking | Backup short brand URL |
| archtrade.io | No NS/A observed | empty | Alt if rebrand to ArchTrade |
| coinarch.app | No NS/A (partial timeout) | incomplete | Weak alt |
| archrebalance.com | No NS/A observed | incomplete | Alt B |
| archautomation.com | Resolves (NameBright parking) | — | Avoid / expensive aftermarket |
| getarch.com | Live (contractor Arch product) | — | Do not use |
| archops.com | Resolves | — | Taken |
| runarch.com / archrunner.com / archstack.com / archport.com | Resolve / park | — | Taken |

**Host map (post-purchase, after dedicated host task):**

| Host | Purpose |
|------|---------|
| `arch-automation.com` | Marketing site / GHL funnel custom domain |
| `www.arch-automation.com` | Redirect → apex or GHL |
| `app.arch-automation.com` | Integration gateway: `/connect/coinbase`, status, webhooks |
| `status.arch-automation.com` (optional later) | Public status page |

Aligns with epic connect URL pattern `https://app.<brand>/connect/coinbase?...`.

---

## 5. Support@ and email identity

| Address | Use | Setup path (after domain owned) |
|---------|-----|----------------------------------|
| **support@arch-automation.com** | Customer support (GHL Conversations or shared inbox) | Forward → GHL email / Google Group; or Workspace mailbox |
| **noreply@arch-automation.com** | Transactional (receipts, dunning, digests) | GHL/SMTP verified domain |
| **ops@arch-automation.com** | Internal fleet / vendor only | Forward to Brad + ops Telegram bridge; **never** customer-facing as personal |
| **legal@** (optional) | Counsel / privacy requests | Forward when ToS live |

**Rules (anti-bleed):**

- Customer mail never routes into personal trading Telegram.  
- Support signatures: “ARCH Automation Support” — not personal name as the brand.  
- GHL Location from-name matches brand.

**Pre-domain interim:** GHL default Location email + documented alias plan only (no public support@ claim until domain live).

---

## 6. GHL Location identity checklist (manual — Ops/Mkt)

When GHL pilot Location is created/updated (`GHL-T0` / prereq card):

- [ ] Location **name**: `ARCH Automation — Pilot`  
- [ ] Business name / DBA fields: ARCH Automation  
- [ ] Logo: upload `logo-mark-primary.png` or SVG-exported PNG from brand kit  
- [ ] Brand colors: Navy `#0B1F2A`, Teal `#14B8A6`, Off-white `#F4F7F9`  
- [ ] Favicon / social if GHL supports  
- [ ] SaaS product display names: `ARCH Starter` / `ARCH Pro` / `ARCH Elite` (or “ARCH Automation — Starter” etc.)  
- [ ] Email templates from-name: ARCH Automation  
- [ ] SMS from-name compliance: brand short code / 10DLC when used (later)  
- [ ] Custom domain on funnel: after DNS + host ready  

**Cannot complete GHL UI from this agent run** — checklist only; execute on Location access.

---

## 7. Separation from Brad personal brand

| Surface | Product (public) | Personal / internal |
|---------|------------------|---------------------|
| Domain | arch-automation.com | Personal sites / Hermes / private ops |
| Logo | ARCH mark + wordmark | No personal photo as product logo |
| Support | support@ product | Ops Telegram fleet health |
| Proof | Opt-in pilot case studies only | No Brad Phase 6 P&L screenshots in funnels |
| Social | Product handles TBD after domain | Personal builder posts OK with process framing, not wallet hero |

---

## 8. Doc / system update plan after sign-off

| Artifact | Action after Brad locks D1–D2 |
|----------|-------------------------------|
| `SCALING_1000_MARKETING_PLAN.md` | Replace “placeholder” with locked name/domain; keep claims policy |
| UNIFIED roadmap header | Working name → locked |
| MASTER task table | Mark brand prereq decided; link this pack |
| Copy pack (`docs/marketing/copy/`) | Use locked strings (dependent card) |
| GHL Location | Apply §6 checklist |
| Host / cert card | Bind domain to dedicated host when ready |
| Legal / ToS | Entity + DBA line |

**This run:** staged brand kit + decision pack + MKT/MASTER pointers as *pending sign-off* (not fake-locked).

---

## 9. Pre-publish brand checklist (tie-in)

Use before any public page, email, SMS, or ad creative ships:

- [ ] Name matches signed D1  
- [ ] Domain/links match signed D2 (or clearly unlisted staging URL)  
- [ ] support@ only if mailbox/forward live  
- [ ] Logo from approved kit (no random AI variants)  
- [ ] Disclaimer block present (MKT §1.4)  
- [ ] No Brad personal P&L / wallet screenshots  
- [ ] No “guaranteed”, fixed monthly %, custody language  
- [ ] GHL vs Coinbase roles clear in copy  
- [ ] UTM uses brand parameter consistently (`utm_source` / `utm_campaign` dictionary later)  

Full claims policy still owned by dedicated Phase A policy card; this is brand-only gate.

---

## 10. Assets delivered this pack

| Path | Contents |
|------|----------|
| `docs/marketing/brand/BRAND_DECISION_PACK.md` | This document |
| `docs/marketing/brand/BRAND_KIT.md` | Colors, type, usage |
| `docs/marketing/brand/SUPPORT_AND_GHL_IDENTITY.md` | Support@ + GHL steps |
| `docs/marketing/brand/PREPUBLISH_BRAND_CHECKLIST.md` | Short gate checklist |
| `docs/marketing/brand/assets/*.svg` | Mark, wordmark, mono, favicon, social, banner |
| Workspace mirror | `.../workspaces/t_cff262a8/brand/` |

PNG exports: generate locally from SVG when rsvg/ImageMagick available; SVG is source of truth.

---

## 11. Open dependencies

| Dependency | Owner | Blocks |
|------------|-------|--------|
| Brad D1–D2 sign-off | Brad | Copy finalization, SEO brand, domain buy |
| Domain purchase + DNS | Brad/Ops | support@, GHL custom domain, app host |
| Dedicated host + HTTPS | Ops (host card) | app. subdomain, webhooks |
| Legal entity / ToS | Brad + counsel | Footer legal line, public paid |
| GHL Location admin | Ops/Mkt | Location rename + logo |

---

## 12. Recommendation one-liner for Brad

> Approve **ARCH Automation** + **arch-automation.com** + **support@arch-automation.com** + GHL Location **ARCH Automation — Pilot**, accept draft logo kit, hold purchase until host/legal ready, then buy domain and wire DNS/email.

---

*End of decision pack. Research-only domain status; not a trademark legal opinion.*
