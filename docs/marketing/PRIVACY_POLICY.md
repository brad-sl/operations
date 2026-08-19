# PRIVACY POLICY — ARCH Automation

**Version:** 1.0 (Draft — Subject to Legal Review)
**Date:** 2026-07-16
**Effective Date:** [Date TBD — upon public launch]

---

## 1. Introduction

ARCH Automation ("we," "us," or "our") provides automated trading software for Coinbase Advanced accounts. This Privacy Policy explains how we collect, use, disclose, and safeguard your personal information when you use our website, subscribe to our Service, or interact with us.

**This is software access — not a financial service.** We do not collect or have access to your Coinbase API keys, private keys, or trading account passwords. We use OAuth (a secure authorization protocol) to connect to your Coinbase account with limited scopes (view + trade only — no transfer scope).

---

## 2. Information We Collect

### 2.1 Information You Provide

| Category | Examples | Purpose |
|----------|----------|---------|
| **Account Information** | Name, email address, phone number | Account creation, subscription management, support |
| **Billing Information** | Payment card details (processed by Stripe via GoHighLevel) | Subscription fee processing |
| **Communication Preferences** | Email/SMS opt-in choices | Lifecycle and marketing communications |
| **Support Communications** | Messages sent to support@ | Customer support and issue resolution |

### 2.2 Information Collected Automatically

| Category | Examples | Purpose |
|----------|----------|---------|
| **Usage Data** | Pages visited, features used, time spent | Service improvement, analytics |
| **Device/Technical Data** | IP address, browser type, operating system | Security, troubleshooting |
| **Cookies and Tracking** | Session cookies, analytics cookies | Authentication, analytics |

### 2.3 Information from Coinbase (via OAuth)

When you connect your Coinbase Advanced account via OAuth, we receive:
- A unique OAuth token (access token + refresh token) — **encrypted and stored in our backend, never in our CRM**
- Portfolio UUID for order routing
- Read-only account information necessary to execute your configured trading parameters

**We do NOT receive or store:**
- Your Coinbase password or API keys
- Full transaction history beyond what is needed for current operations
- Beneficial ownership information

---

## 3. How We Use Your Information

We use your information to:
- Provide, maintain, and improve the Service
- Process subscription payments and manage billing
- Send lifecycle communications (onboarding, status updates, support)
- Monitor Service performance and security
- Comply with legal obligations
- Send marketing communications (only with your consent; you may opt out at any time)

**We do NOT use your information for:**
- Trading on your account without your authorization
- Selling your personal data to third parties
- Sharing your trading activity or performance with other users

---

## 4. Legal Bases for Processing (GDPR — for EU users)

If you are located in the European Economic Area, we process your personal information based on:
- **Contractual necessity** — to provide the Service you subscribed to
- **Consent** — for marketing communications and optional data collection
- **Legitimate interests** — for security, analytics, and service improvement
- **Legal obligation** — where required by applicable law

---

## 5. Information Sharing and Disclosure

### 5.1 Service Providers

We share your information with trusted service providers who help us operate the Service:

| Provider | Purpose | Data Shared |
|----------|---------|-------------|
| **GoHighLevel** | CRM, billing, email/SMS communications | Name, email, phone, subscription details (NO OAuth tokens or trading data) |
| **Stripe** | Payment processing | Payment card details (tokenized; we do not store full card numbers) |
| **Coinbase** | Trading execution | OAuth token (initially granted by user; we submit orders to your Coinbase account) |
| **Cloud infrastructure** | Hosting and data storage | Encrypted data at rest |

### 5.2 Legal Requirements

We may disclose your information if required by law, court order, or governmental regulation, or if we believe in good faith that disclosure is necessary to protect our rights, your safety, or the safety of others.

### 5.3 Business Transfers

If we are acquired by or merged with another company, or if we sell our business assets, your information may be transferred as part of that transaction. We will notify you of any such change.

### 5.4 No Sale of Personal Information

**We do not sell your personal information** for monetary or other valuable consideration. This includes under the California Consumer Privacy Act (CCPA) definition of "sale."

---

## 6. Data Security

### 6.1 Security Measures

We implement industry-standard security measures to protect your information:
- OAuth tokens are **encrypted at rest** using AES-256 or equivalent
- All communications use TLS/SSL encryption
- Access controls and least-privilege principles
- Regular security reviews

### 6.2 What We Don't Store

We deliberately minimize sensitive data exposure:
- **No API keys** stored in our CRM (GoHighLevel)
- **No full card numbers** — Stripe handles payment tokenization
- **No private keys** or wallet seeds
- **No full balance/precision** in GHL — only rounded status fields

### 6.3 No Security Guarantee

While we take reasonable measures to protect your information, no security system is impenetrable. We cannot guarantee the absolute security of your data.

---

## 7. Data Retention

We retain your personal information for as long as your account is active or as needed to provide the Service. After account termination:
- Encrypted OAuth tokens are deleted or revoked within 30 days
- Account information is retained for up to 12 months for tax/legal purposes
- Anonymized/aggregated data may be retained indefinitely for analytics

---

## 8. Your Rights and Choices

### 8.1 Access and Update

You can access and update your account information through your account settings.

### 8.2 Communication Preferences

- **Lifecycle emails/SMS:** Transactional (onboarding, billing, status) are necessary for the Service
- **Marketing emails:** You can opt out at any time via unsubscribe link or account settings
- **SMS:** Reply STOP to opt out of SMS messages

### 8.3 Account Deletion

You may delete your account by contacting support. Upon deletion:
- We will stop all trading activity
- Your OAuth tokens will be invalidated
- Your personal data will be deleted or anonymized (subject to legal retention requirements)

### 8.4 California Privacy Rights (CCPA/CPRA)

If you are a California resident, you have the right to:
- Know what personal information we collect, use, and share
- Request deletion of your personal information
- Opt out of the sale of your personal information (we do not sell)
- Non-discrimination for exercising your privacy rights

To exercise these rights, contact us at privacy@[brand-domain].

### 8.5 European Privacy Rights (GDPR)

If you are located in the EEA, you have the right to:
- Access your personal data
- Rectify inaccurate data
- Erase your data (right to be forgotten)
- Restrict processing
- Data portability
- Object to processing

---

## 9. Cookies and Tracking

We use essential cookies for authentication and session management. We may use analytics cookies to understand usage patterns. You can control cookie preferences through your browser settings.

| Type | Purpose | Duration |
|------|---------|----------|
| Essential | Authentication, session management | Session / persistent |
| Analytics | Usage patterns, feature adoption | Up to 12 months |
| Marketing | Not currently used | N/A |

---

## 10. Children's Privacy

The Service is not intended for individuals under 18 years of age. We do not knowingly collect personal information from minors.

---

## 11. International Data Transfers

If you are located outside the United States, your information may be transferred to and processed in the United States. We will ensure appropriate safeguards are in place for such transfers.

---

## 12. Changes to This Privacy Policy

We may update this Privacy Policy from time to time. We will notify you of material changes via email or through the Service. Your continued use of the Service after the effective date constitutes your acceptance of the updated policy.

---

## 13. Contact

For privacy-related inquiries:

ARCH Automation
Email: privacy@[brand-domain]
[Physical address if required]

---

## Document Control

| Version | Date | Author | Notes |
|---------|------|--------|-------|
| 1.0 | 2026-07-16 | Legal Department | Draft Privacy Policy for counsel review before public paid checkout |

**Canonical path:** `docs/marketing/PRIVACY_POLICY.md`
**Related:** `docs/marketing/TERMS_OF_SERVICE.md`, `docs/marketing/RISK_DISCLOSURES.md`

*This is a draft document pending qualified legal counsel review. Do not publish or present to users before counsel approval.*