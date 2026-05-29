#!/bin/bash
# Start Phase 6 Runner in background with logging

cd "$(dirname "$0")/../.."

mkdir -p logs

echo "Starting Phase 6 Runner..."
nohup python3 -m phase6.core.phase6_runner --mode live --confirm-live >> logs/phase6_runner.log 2>&1 &
echo $! > logs/phase6_runner.pid

echo "Runner started with PID $(cat logs/phase6_runner.pid)"
echo "Logs: logs/phase6_runner.log"