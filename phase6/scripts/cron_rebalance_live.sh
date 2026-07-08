# Enforces data flow per docs/DATA_FLOW_AND_LOCATIONS.md
#!/bin/bash
# Thin launcher for Hermes no_agent cron
# Runs the Phase6 cron_rebalance in live mode
cd /home/brad/projects/crypto-trading-bot  # canonical root per DATA_FLOW
exec python3 phase6/scripts/cron_rebalance.py --live
