#!/usr/bin/env python3
"""Phase 3 v3 - TRADING_EVENT_SCHEMA Integrated"""
import json,time,logging,random
from datetime import datetime
from pathlib import Path
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
logger=logging.getLogger(__name__)
BASE=Path("/home/brad/.openclaw/workspace/operations/crypto-bot")

class Orchestrator:
    def __init__(self):
        self.start=datetime.utcnow()
        self.events=[]
        self.positions={}
        self.counters={"BTC-USD":0,"XRP-USD":0}
        self.trades=[]
        self._init_log()
        logger.info("=== Phase 3 v3 Schema Integrated ===")
        
    def _init_log(self):
        with open(BASE/"EVENT_LOG.json","w") as f:
            json.dump({"session_id":"phase3_v3","account":"SANDBOX",
                       "start_time":self.start.isoformat()+"Z","events":[]},f)
    
    def run(self,duration=60):
        cycles=duration//10
        for c in range(cycles):
            for pair in ["BTC-USD","XRP-USD"]:
                rsi=random.uniform(20,80)  # Can cross 30/70
                sentiment=random.uniform(-0.8,0.8)
                signal=self._signal(rsi,sentiment,pair)
                if signal!="HOLD" and pair not in self.positions:
                    self._enter(pair,signal,rsi,sentiment)
                elif pair in self.positions and random.random()<0.1:
                    self._exit(pair,"TAKE_PROFIT" if random.random()>0.5 else "STOP_LOSS")
            time.sleep(10)
        self._save()
        
    def _signal(self,rsi,sent,pair):
        if rsi<30 and sent<-0.3: return "BUY"
        if rsi>70 and sent>0.3: return "SELL"
        return "HOLD"
    
    def _enter(self,pair,side,rsi,sent):
        self.counters[pair]+=1
        eid=f"{pair.replace('-','')}_{self.counters[pair]:03d}"
        price={"BTC-USD":67500,"XRP-USD":2.5}[pair]
        self.positions[pair]={"eid":eid,"side":side,"entry":price,"rsi":rsi,"sent":sent}
        self.events.append({"event_type":"ENTRY","event_id":eid,"product_id":pair,
                           "side":side,"entry_price":price,"signal_details":{"rsi":rsi,"sentiment":sent}})
        logger.info(f"ENTRY: {pair} {side} @ {price}")
    
    def _exit(self,pair,reason):
        pos=self.positions.pop(pair)
        exit_id=pos["eid"]+"_EXIT"
        price={"BTC-USD":67500,"XRP-USD":2.5}[pair]+random.uniform(-100,100)
        pnl=(price-pos["entry"])*0.01
        self.events.append({"event_type":"EXIT","event_id":exit_id,"entry_event_id":pos["eid"],
                           "product_id":pair,"exit_price":price,"exit_reason":reason})
        self.events.append({"event_type":"OUTCOME","event_id":pos["eid"]+"_OUTCOME",
                           "entry_event_id":pos["eid"],"exit_event_id":exit_id,
                           "product_id":pair,"trade_result":"WIN" if pnl>0 else "LOSS",
                           "net_pnl_usd":pnl,"fees":{"total_fees_usd":0.1}})
        self.trades.append({"pair":pair,"pnl":pnl})
        logger.info(f"EXIT: {pair} {reason} PnL: ${pnl:.2f}")
    
    def _save(self):
        wins=len([t for t in self.trades if t["pnl"]>0])
        wr=wins/len(self.trades)*100 if self.trades else 0
        with open(BASE/"EVENT_LOG.json","w") as f:
            json.dump({"session_id":"phase3_v3","account":"SANDBOX",
                       "start_time":self.start.isoformat()+"Z","end_time":datetime.utcnow().isoformat()+"Z",
                       "events":self.events,"summary":{"total_events":len(self.events),
                       "entry_events":sum(1 for e in self.events if e["event_type"]=="ENTRY"),
                       "exit_events":sum(1 for e in self.events if e["event_type"]=="EXIT"),
                       "outcome_events":sum(1 for e in self.events if e["event_type"]=="OUTCOME"),
                       "total_net_pnl_usd":sum(t["pnl"] for t in self.trades),
                       "win_rate_pct":wr}},f,indent=2)
        logger.info(f"Saved {len(self.events)} events, {len(self.trades)} trades, {wr:.1f}% win rate")

if __name__=="__main__":
    o=Orchestrator()
    o.run(60)  # 1 min test
