# ARCH Automation — Member area placeholder (post-pay)
# Surfaces: GHL custom menu / iframe host / app.arch-automation.com later
# Phase A: unlisted member steps — Connect + Status only

## Page: Connect Coinbase
H1: Connect your Coinbase Advanced account  
Body: Authorize ARCH Automation with OAuth so the software can place trades under your configured rules.  
- Funds stay in your Coinbase account  
- View + trade scopes only — no transfer  
- We never ask for API keys on this page  

PRIMARY CTA: Connect with Coinbase → {{connect_link}}  
Help: {{support_email}}  
Status if already connected: Connected · {{coinbase_status}}

Disclaimer strip: Trading involves substantial risk of loss. Software access only. Not investment advice.

## Page: Status
H1: Automation status  
Fields (process only):
- Runner health: {{runner_health}}  
- Coinbase: {{coinbase_status}}  
- Tier: {{tier_name}}  
- Config summary: {{config_summary}}  
- Next window: {{next_rebalance_window}}  

FORBIDDEN on this page in marketing mode: live personal P&L hero numbers presented as product proof.

CTA if disconnected: Connect  
CTA if needs_attention: Contact support  

## Page: Billing (GHL portal link)
Manage payment method · Cancel subscription  
Note: Canceling pauses software access; revoke Coinbase app after cancel.

## Empty / loading states
- “Checking connection…”  
- “Insufficient data” / N/A — never fake 0% returns  
- “Sample interface — not actual trading data” only on mocks
