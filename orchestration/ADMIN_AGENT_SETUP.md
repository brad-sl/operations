# Admin Agent Setup Guide

**Status:** ✅ Production-Ready (2025-03-18)

This guide walks through setting up the Admin Agent orchestrator system that monitors email, ad accounts, and spawns specialty agents on schedule.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Email Forwarding Configuration](#email-forwarding-configuration)
4. [Telegram Bot Setup](#telegram-bot-setup)
5. [Local Testing](#local-testing)
6. [Systemd Service Installation](#systemd-service-installation)
7. [Monitoring & Logs](#monitoring--logs)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

The Admin Agent operates as a persistent orchestrator that:

- **Runs every 5 minutes** in an event loop
- **Checks email** on both `admanbot@uncorkedcanvas.com` and personal Gmail
- **Parses form submissions** and logs to `leads.jsonl`
- **Monitors thresholds** (CPA >75, daily spend >150, CTR <0.5%)
- **Spawns specialty agents** on schedule:
  - 9 AM daily: GAM Monitor (Google Ad Manager performance)
  - Friday 6 PM: Creative Optimizer (ad fatigue detection)
  - Monday 12 PM: Budget Allocator (ROAS-based rebalancing)
  - Tuesday 6 AM: Keyword Auditor (negative keyword review)
- **Sends Telegram alerts** for high-priority items
- **Logs all events** to `admin_activity.jsonl` and `leads.jsonl`

State machine: `idle → checking_email → parsing_forms → evaluating_thresholds → spawning_agents → reporting → sleeping`

---

## Prerequisites

### Required

- **Node.js 18+** (TypeScript compilation)
- **OpenClaw** (with `himalaya` skill for email integration)
- **Adspirer API credentials** (for ad metrics)
- **Git** (for version control)

### Optional but Recommended

- **Telegram Bot Token** (for alerts)
- **SystemD** (for service management)

### Installation

```bash
# Install Node dependencies
npm install typescript ts-node @types/node node-cron dotenv

# Verify himalaya CLI is available
himalaya --version

# Verify adspirer tools are accessible
openclaw adspirer status
```

---

## Email Forwarding Configuration

### Step 1: Set Up Email Account on admanbot@uncorkedcanvas.com

This is where form submissions and alerts will be forwarded.

**Gmail/IMAP Setup:**

```bash
# 1. Enable IMAP in Gmail settings:
#    https://myaccount.google.com/security → 2-Step Verification → App passwords
#    Create "Mail" app password (16-char code)

# 2. Configure himalaya for this account:
himalaya --account admanbot config:create
# When prompted:
#   Account name: admanbot
#   Email: admanbot@uncorkedcanvas.com
#   IMAP host: imap.gmail.com
#   IMAP port: 993
#   SMTP host: smtp.gmail.com
#   SMTP port: 587
#   Password: [paste 16-char app password]

# 3. Test connection:
himalaya --account admanbot mailbox:list
```

### Step 2: Configure Personal Gmail

```bash
# Repeat the process for your personal Gmail:
himalaya --account personal config:create
# When prompted:
#   Account name: personal
#   Email: brad@gmail.com
#   [same IMAP/SMTP config as above]

# 3. Test connection:
himalaya --account personal mailbox:list
```

### Step 3: Update admin_schedules.json

Edit `/home/brad/.openclaw/workspace/operations/orchestration/admin_schedules.json` and update the email accounts:

```json
"email_accounts": [
  {
    "address": "admanbot@uncorkedcanvas.com",
    "provider": "himalaya"
  },
  {
    "address": "brad@gmail.com",
    "provider": "himalaya"
  }
]
```

---

## Telegram Bot Setup

### Step 1: Create Telegram Bot

```bash
# 1. Open Telegram and search for @BotFather
# 2. Send /start, then /newbot
# 3. Choose a name (e.g., "Admin Agent Alerts")
# 4. BotFather will give you a token like:
#    123456789:ABCDefGHIJKlmnoPQRstuvWXYZ1234567890

# Save this token securely
export TELEGRAM_BOT_TOKEN="123456789:ABCDefGHIJKlmnoPQRstuvWXYZ1234567890"
```

### Step 2: Get Your Chat ID

```bash
# 1. Send any message to your bot in Telegram
# 2. Run this command to get chat ID:
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates" | jq '.result[0].message.chat.id'

# Result will be a number like: 123456789
export TELEGRAM_CHAT_ID="123456789"
```

### Step 3: Update admin_schedules.json

```json
"telegram": {
  "enabled": true,
  "webhook_url": "https://api.telegram.org/bot123456789:ABCDefGHIJKlmnoPQRstuvWXYZ1234567890/sendMessage",
  "chat_id": "123456789",
  "alert_levels": {
    "critical": 1,
    "warning": 2,
    "info": 3
  }
}
```

### Step 4: Test Telegram

```bash
# Send a test message:
curl -X POST "${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{
    "chat_id": "'${TELEGRAM_CHAT_ID}'",
    "text": "✅ Admin Agent Telegram integration working!"
  }'
```

---

## Local Testing

### Test 1: Verify Configuration

```bash
cd /home/brad/.openclaw/workspace/operations/orchestration

# Check config loads without errors:
ts-node -e "import AdminAgent from './AdminAgent'; const a = new AdminAgent('./admin_schedules.json', './test-logs'); console.log('✓ Config loaded')"
```

### Test 2: Email Integration

```bash
# List emails from admanbot account:
himalaya --account admanbot message:list --mailbox INBOX --limit 5

# Check for form submissions:
himalaya --account admanbot message:read --mailbox INBOX --message-id 1 --headers-only
```

### Test 3: Adspirer Connection

```bash
# Verify ad platform connections:
openclaw adspirer status

# Test Google Ads performance fetch:
openclaw list_campaigns

# Test Meta Ads:
openclaw get_meta_campaign_performance
```

### Test 4: Dry Run Agent (5 seconds)

```bash
# This will run one poll cycle and exit
cat > /tmp/test-admin.ts << 'EOF'
import AdminAgent from './AdminAgent';
const agent = new AdminAgent('./admin_schedules.json', './test-logs');
agent.start();
setTimeout(() => agent.stop().then(() => process.exit(0)), 5000);
EOF

ts-node /tmp/test-admin.ts
```

### Test 5: Check Logs

```bash
# After any test, check the activity log:
tail -f test-logs/admin_activity.jsonl

# Pretty-print the last few entries:
tail -20 test-logs/admin_activity.jsonl | jq '.'
```

---

## Systemd Service Installation

### Step 1: Create Service File

```bash
sudo tee /etc/systemd/system/openclaw-admin-agent.service > /dev/null << 'SYSTEMD_EOF'
[Unit]
Description=OpenClaw Admin Agent Orchestrator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=brad
WorkingDirectory=/home/brad/.openclaw/workspace/operations/orchestration
Environment="ADMIN_CONFIG=/home/brad/.openclaw/workspace/operations/orchestration/admin_schedules.json"
Environment="ADMIN_LOG_DIR=/home/brad/.openclaw/workspace/operations/orchestration/logs"
Environment="NODE_ENV=production"

# Use npx to run with ts-node
ExecStart=/usr/bin/npx ts-node AdminAgent.ts

# Restart policy
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

# Resource limits
MemoryLimit=500M
CPUQuota=50%

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF
```

### Step 2: Enable and Start Service

```bash
# Reload systemd daemon
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable openclaw-admin-agent.service

# Start the service
sudo systemctl start openclaw-admin-agent.service

# Check status
sudo systemctl status openclaw-admin-agent.service

# View logs
sudo journalctl -u openclaw-admin-agent.service -f
```

### Step 3: Verify Running

```bash
# Check if running
ps aux | grep AdminAgent

# Check memory usage
systemctl status openclaw-admin-agent.service

# Last 50 log entries (pretty-printed)
sudo journalctl -u openclaw-admin-agent.service -n 50 | jq '.'
```

---

## Monitoring & Logs

### Log Files Location

```
/home/brad/.openclaw/workspace/operations/orchestration/logs/
├── admin_activity.jsonl    # All agent events (structured)
├── leads.jsonl             # Form submissions (structured)
└── error.log               # Errors only (unstructured)
```

### Log Format

Each line in `admin_activity.jsonl` is a JSON object:

```json
{
  "timestamp": "2025-03-18T11:45:30.123Z",
  "event_type": "Email check complete",
  "status": "success",
  "details": {
    "formSubmissions": 3,
    "duration_ms": 2450
  }
}
```

### Query Logs

```bash
# Last 10 events:
tail -10 /home/brad/.openclaw/workspace/operations/orchestration/logs/admin_activity.jsonl | jq '.'

# Events from last 1 hour:
jq 'select(.timestamp > now - 3600)' /home/brad/.openclaw/workspace/operations/orchestration/logs/admin_activity.jsonl

# All errors:
jq 'select(.status == "error")' /home/brad/.openclaw/workspace/operations/orchestration/logs/admin_activity.jsonl

# Count events by type:
jq '.event_type' /home/brad/.openclaw/workspace/operations/orchestration/logs/admin_activity.jsonl | sort | uniq -c
```

### Create Monitoring Dashboard

```bash
# Real-time tail with pretty-printing:
watch -n 5 'tail -20 /home/brad/.openclaw/workspace/operations/orchestration/logs/admin_activity.jsonl | jq -r "[\(.timestamp), .status, .event_type] | @csv"'
```

---

## Troubleshooting

### Issue: "himalaya: command not found"

**Solution:**
```bash
# Ensure himalaya is installed
cargo install himalaya

# Add to PATH:
export PATH="~/.cargo/bin:$PATH"

# Verify:
himalaya --version
```

### Issue: "Config file not found"

**Solution:**
```bash
# Verify file path:
ls -la /home/brad/.openclaw/workspace/operations/orchestration/admin_schedules.json

# If missing, copy template:
cp admin_schedules.json.template admin_schedules.json
```

### Issue: "Email account authentication failed"

**Solution:**
```bash
# Re-authenticate with himalaya:
himalaya --account admanbot config:create

# Verify credentials work:
himalaya --account admanbot mailbox:list

# For Gmail, ensure App Password is generated (not regular password)
# https://myaccount.google.com/apppasswords
```

### Issue: "Telegram alert not sending"

**Solution:**
```bash
# Verify token and chat ID:
echo "Token: $TELEGRAM_BOT_TOKEN"
echo "Chat ID: $TELEGRAM_CHAT_ID"

# Test API manually:
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "'${TELEGRAM_CHAT_ID}'", "text": "Test"}'

# If 400 error, check chat_id format (should be numeric)
```

### Issue: "Service won't start (systemd)"

**Solution:**
```bash
# Check logs:
sudo journalctl -u openclaw-admin-agent.service -n 20

# Check for syntax errors:
ts-node -c "import AdminAgent from './AdminAgent'"

# Verify working directory exists:
ls -la /home/brad/.openclaw/workspace/operations/orchestration/

# Try running manually:
cd /home/brad/.openclaw/workspace/operations/orchestration
ts-node AdminAgent.ts
```

### Issue: "High memory usage"

**Solution:**
```bash
# Check current usage:
ps aux | grep AdminAgent | awk '{print $6" MB"}'

# Reduce polling interval in admin_schedules.json:
"polling_interval_ms": 600000  # Increase from 300000 (5 min) to 10 min

# Reduce log retention:
"log_retention_days": 7  # Keep only 7 days of logs

# Restart service:
sudo systemctl restart openclaw-admin-agent.service
```

---

## Quick Reference

### Start/Stop Agent

```bash
# Start
sudo systemctl start openclaw-admin-agent.service

# Stop
sudo systemctl stop openclaw-admin-agent.service

# Restart
sudo systemctl restart openclaw-admin-agent.service

# Status
sudo systemctl status openclaw-admin-agent.service
```

### View Real-Time Logs

```bash
# Follow system logs
sudo journalctl -u openclaw-admin-agent.service -f

# Pretty-print
sudo journalctl -u openclaw-admin-agent.service -f | jq '.'
```

### Update Configuration

```bash
# Edit config
nano /home/brad/.openclaw/workspace/operations/orchestration/admin_schedules.json

# Restart to apply changes
sudo systemctl restart openclaw-admin-agent.service
```

---

**Next Step:** Run local tests to verify everything works before deploying as systemd service.

