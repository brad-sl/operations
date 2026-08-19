#!/bin/bash
# Test script for webhook endpoint
# Usage: ./test-webhook.sh https://your-domain.com  or IP for http test

DOMAIN=${1:-http://localhost:8000}
URL="${DOMAIN}/ghl/webhook"

echo "Testing webhook at $URL ..."
curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "X-GHL-Signature: test-sig-$(date +%s)" \
  -d '{
    "webhookId": "test-'$(date +%s)'",
    "type": "contact.create",
    "payload": {"contact": {"id": "test123", "email": "test@example.com"}}
  }' | jq . || echo "curl or jq issue; raw:"
curl -s -X POST "$URL" -H "Content-Type: application/json" -d '{"test":true}'

echo ""
echo "Health check:"
curl -s "${DOMAIN}/health" | jq . || curl -s "${DOMAIN}/health"

echo ""
echo "Test complete. Check logs on server."
