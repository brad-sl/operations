#!/bin/bash
# validation.sh - Verify Admin Agent system is properly set up

set -e

echo "🔍 Admin Agent Validation Script"
echo "================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1 exists"
        return 0
    else
        echo -e "${RED}✗${NC} $1 missing"
        return 1
    fi
}

check_json() {
    if jq empty "$1" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $1 is valid JSON"
        return 0
    else
        echo -e "${RED}✗${NC} $1 is invalid JSON"
        return 1
    fi
}

echo "📦 File Structure:"
check_file "AdminAgent.ts" || exit 1
check_file "admin_schedules.json" || exit 1
check_file "admin_agent_spec.json" || exit 1
check_file "ADMIN_AGENT_SETUP.md" || exit 1
check_file "README.md" || exit 1
echo ""

echo "📋 JSON Validation:"
check_json "admin_schedules.json" || exit 1
check_json "admin_agent_spec.json" || exit 1
echo ""

echo "🔧 Dependencies:"
if command -v ts-node &> /dev/null; then
    echo -e "${GREEN}✓${NC} ts-node is available"
else
    echo -e "${YELLOW}⚠${NC} ts-node not found (run: npm install -g ts-node)"
fi

if command -v jq &> /dev/null; then
    echo -e "${GREEN}✓${NC} jq is available"
else
    echo -e "${YELLOW}⚠${NC} jq not found (needed for log analysis)"
fi

if command -v himalaya &> /dev/null; then
    echo -e "${GREEN}✓${NC} himalaya is available"
else
    echo -e "${YELLOW}⚠${NC} himalaya not found (needed for email integration)"
fi
echo ""

echo "📊 Configuration:"
EMAIL_ACCOUNTS=$(jq '.email_accounts | length' admin_schedules.json)
echo -e "${GREEN}✓${NC} $EMAIL_ACCOUNTS email accounts configured"

THRESHOLDS=$(jq '.thresholds | length' admin_schedules.json)
echo -e "${GREEN}✓${NC} $THRESHOLDS thresholds configured"

AGENTS=$(jq '.specialty_agents | length' admin_schedules.json)
echo -e "${GREEN}✓${NC} $AGENTS specialty agents configured"

POLLING=$(jq '.polling_interval_ms' admin_schedules.json)
echo -e "${GREEN}✓${NC} Polling interval: ${POLLING}ms"
echo ""

echo "✅ Validation Complete!"
echo ""
echo "Next steps:"
echo "1. Update email addresses in admin_schedules.json"
echo "2. Set up himalaya: himalaya --account <name> config:create"
echo "3. Test locally: timeout 10 ts-node AdminAgent.ts || true"
echo "4. Deploy as systemd service (see ADMIN_AGENT_SETUP.md)"

