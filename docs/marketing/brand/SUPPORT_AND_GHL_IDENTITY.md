# Support@ and GHL identity setup (ARCH Automation)

**Status:** Plan only until domain purchased + GHL Location access  
**Depends on:** Brad brand sign-off (D1–D2), domain ownership, GHL admin  

---

## 1. Support@ setup options

### Option A — Forwarder only (fast pilot)

1. Buy `arch-automation.com` at chosen registrar (after Brad OK).  
2. Create email forward: `support@` → Brad ops inbox or shared Gmail.  
3. Create `noreply@` as send-only via GHL SMTP or transactional provider once domain authenticated (SPF/DKIM).  
4. Point GHL Location “reply-to” / from-name to brand.

**Pros:** Cheap, fast. **Cons:** Less professional for scale; shared personal inbox risk if not careful.

### Option B — Google Workspace / Zoho (preferred by T1 pilot)

1. Domain verify in Workspace (or Zoho Mail).  
2. Mailboxes: `support@`, `noreply@` (or group), optional `ops@`.  
3. GHL: authenticate domain for email; use Conversations for support@ if preferred.  
4. Shared label/SLA doc (support hours TBD — UNIFIED Q8).

### Option C — GHL-native only

- Use GHL-provided sending domain / custom domain mail if Location supports it.  
- Still need branded domain for trust and `app.` host separation.

**Recommendation:** A for week-1 after domain buy → B before public paid checkout.

---

## 2. DNS records (template — fill after purchase)

| Type | Name | Value (examples) | Purpose |
|------|------|------------------|---------|
| A / CNAME | `@` / `www` | GHL funnel or static host | Marketing |
| CNAME | `app` | Dedicated host / LB | Connect + webhooks |
| MX | `@` | Provider MX | Mail |
| TXT | `@` | SPF | Mail auth |
| TXT | selector._domainkey | DKIM | Mail auth |
| TXT | `_dmarc` | DMARC policy (start p=none) | Mail auth |
| CAA | optional | Let’s Encrypt / issuer | Cert hygiene |

Exact values come from host + mail provider. Host card owns `app` + cert.

---

## 3. GHL Location branding steps

1. Settings → Company / Business info → name **ARCH Automation — Pilot**.  
2. Upload logo (`logo-mark-primary` PNG export).  
3. Theme colors: navy / teal.  
4. Email builder: header logo + footer disclaimer (MKT §1.4).  
5. SaaS products: name with ARCH prefix.  
6. Pipelines/tags unchanged functionally; display strings use brand.  
7. Custom domain: after DNS (funnels).  
8. Verify Private Integration still scoped to this Location.

---

## 4. Acceptance checks

- [ ] Customer email arrives at support path within 5 minutes  
- [ ] Outbound GHL email shows ARCH Automation, not personal name only  
- [ ] No customer thread in personal trading Telegram  
- [ ] Location logo matches brand kit  
- [ ] `app.` host plan documented even if not live  

---

## 5. Owners

| Step | R | A |
|------|---|---|
| Sign brand/domain | Mkt pack | Brad |
| Purchase domain | Ops/Brad | Brad |
| Mail + DNS | Ops | Brad |
| GHL Location UI | Mkt/Ops | Brad |
| app host + cert | Ops/Eng | Brad |
