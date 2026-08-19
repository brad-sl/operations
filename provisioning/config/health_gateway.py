#!/usr/bin/env python3
"""
Minimal webhook gateway stub for GHL + health checks.
For dedicated VPS: run via gunicorn or in Docker.
Endpoints:
- GET /health -> 200 OK + basic status (for uptime monitoring)
- POST /ghl/webhook -> verify (stub sig), log, return 200 (idempotent test)
- GET / -> info

DO NOT use in prod without signature verification, rate limit, auth, full impl.
Placeholder for T0/GHL-01.
"""
import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

# TODO: real sig verify with GHL secret (from env)
GHL_WEBHOOK_SECRET = os.environ.get("GHL_WEBHOOK_SECRET", "placeholder-secret")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "ghl-webhook-gateway-stub",
        "version": "phase-a-02-stub",
        "uptime_note": "Basic stub - replace with full integration gateway"
    }), 200

@app.route("/ghl/webhook", methods=["POST"])
def ghl_webhook():
    # Stub: log payload, pretend process (idempotency key stub)
    payload = request.get_json(silent=True) or {}
    headers = dict(request.headers)
    webhook_id = payload.get("webhookId") or headers.get("X-GHL-Signature", "no-id")
    
    logger.info(f"Received webhook: id={webhook_id} type={payload.get('type', 'unknown')}")
    logger.debug(f"Headers: {headers}")
    logger.debug(f"Payload: {json.dumps(payload)[:500]}...")
    
    # TODO: HMAC verify, dedup, enqueue job, route by type
    # For test: always 200
    return jsonify({
        "received": True,
        "webhookId": webhook_id,
        "processed": "stub-ok",
        "note": "Test endpoint. Full impl in T0/GHL-01. Do not point prod GHL yet."
    }), 200

@app.route("/", methods=["GET"])
def root():
    return jsonify({
        "service": "ARCH Automation Integration Gateway (stub)",
        "endpoints": ["/health", "/ghl/webhook"],
        "status": "research-posture-stub",
        "docs": "See GHL_INTEGRATION.md and provisioning docs"
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
