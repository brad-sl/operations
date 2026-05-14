#!/bin/bash
cd $(dirname $0)
echo \"Starting Phase 5 paper trading...\"
./venv/bin/python phase5_multi_pair.py --paper --capital 1000 --pairs BTC-USD,ETH-USD,XRP-USD,DOGE-USD,SOL-USD,ADA-USD --logfile phase5_live.log
