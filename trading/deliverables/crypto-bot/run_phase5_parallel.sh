#!/bin/bash
cd /home/brad/.openclaw/workspace/operations/crypto-bot/
mkdir -p phase5_logs

# Common args
PAIRS="BTC-USD,XRP-USD,DOGE-USD,ETH-USD"
CAPITAL=1000
SL=2
TP=2
DAILY_CAP=50
CYCLES=100
LOG_BASE="phase5_logs/phase5_var"

# Var1
nohup python3 phase5_multi_pair.py --rsi-buy 30 --rsi-sell 70 --sentiment-weight 3 --pairs $PAIRS --capital $CAPITAL --sl-pct $SL --tp-pct $TP --daily-loss $DAILY_CAP --cycles $CYCLES > ${LOG_BASE}1.log 2>&1 &

# Var2
nohup python3 phase5_multi_pair.py --rsi-buy 35 --rsi-sell 65 --sentiment-weight 3 --pairs $PAIRS --capital $CAPITAL --sl-pct $SL --tp-pct $TP --daily-loss $DAILY_CAP --cycles $CYCLES > ${LOG_BASE}2.log 2>&1 &

# Var3
nohup python3 phase5_multi_pair.py --rsi-buy 30 --rsi-sell 70 --sentiment-weight 4 --pairs $PAIRS --capital $CAPITAL --sl-pct $SL --tp-pct $TP --daily-loss $DAILY_CAP --cycles $CYCLES > ${LOG_BASE}3.log 2>&1 &

# Var4
nohup python3 phase5_multi_pair.py --rsi-buy 35 --rsi-sell 65 --sentiment-weight 4 --pairs $PAIRS --capital $CAPITAL --sl-pct $SL --tp-pct $TP --daily-loss $DAILY_CAP --cycles $CYCLES > ${LOG_BASE}4.log 2>&1 &

# Var5: Assume --kelly supported or skip if not; fallback to standard
nohup python3 phase5_multi_pair.py --rsi-buy 30 --rsi-sell 70 --sentiment-weight 3 --kelly --pairs $PAIRS --capital $CAPITAL --sl-pct $SL --tp-pct $TP --daily-loss $DAILY_CAP --cycles $CYCLES > ${LOG_BASE}5.log 2>&1 &

# Var6
nohup python3 phase5_multi_pair.py --rsi-buy 35 --rsi-sell 65 --sentiment-weight 3 --kelly --pairs $PAIRS --capital $CAPITAL --sl-pct $SL --tp-pct $TP --daily-loss $DAILY_CAP --cycles $CYCLES > ${LOG_BASE}6.log 2>&1 &

echo "Launched 6 parallel Phase 5 variants. Logs in phase5_logs/. Monitor with 'tail -f phase5_logs/*.log' or ps aux | grep phase5"
sleep 3600  # Wait 1h for completion, then echo summary command
echo "Completed. Run python3 summarize_phase5.py for analysis."  # Assume summary script later