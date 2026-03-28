#!/usr/bin/env python3
"""Phase 3 Schema - Dual pair test (BTC + XRP)"""
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
        
    def run(self,cycles=24):
        logger.info(f"=== Dual Pair Test: BTC + XRP ({cycles} cycles) ===")
        for c in range(cycles):
            for pair in ["BTC-USD","XRP-USD"]:
                # Different RSI ranges for each pair (per spec)
                rsi=random.uniform(15,85)
                sentiment=random.uniform(-0.9,0.9)
                
                # BTC: 30/70 thresholds, XRP: 35/65 thresholds
                if pair=="BTC-USD":
                    signal="BUY" if rsi<30 and sentiment<-0.2 else ("SELL" if rsi>70 and sentiment>0.2 else "HOLD")
                else:
                    signal="BUY" if rsi<35 and sentiment<-0.2 else ("SELL" if rsi>65 and sentiment>0.2 else "HOLD")
                
                if signal!="HOLD" and pair not in self.positions:
                    self._enter(pair,signal,rsi,sentiment)
                elif pair in self.positions and random.random()<0.20:
                    self._exit(pair,"TAKE_PROFIT" if random.random()>0.4 else "STOP_LOSS")
            time.sleep(5)
        
        for pair in list(self.positions.keys()): self._exit(pair,"TIMEOUT")
        self._save()
        
    def _enter(self,pair,side,rsi,sent):
        self.counters[pair]+=1
        eid=f"{pair.replace('-','')}_{self.counters[pair]:03d}"
        price={"BTC-USD":67500,"XRP-USD":2.5}[pair]
        qty=0.01
        self.positions[pair]={"eid":eid,"side":side,"entry":price,"qty":qty,"time":time.time()}
        self.events.append({"event_type":"ENTRY","event_id":eid,"product_id":pair,"side":side,"entry_price":price,"entry_quantity":qty,"signal_details":{"rsi":round(rsi,1),"sentiment":round(sent,2),"confidence":0.75}})
        logger.info(f"✓ ENTRY {pair:7} {side:4} @ ${price}")
    
    def _exit(self,pair,reason):
        pos=self.positions.pop(pair)
        exit_id=pos["eid"]+"_EXIT"
        price=pos["entry"]+(random.uniform(-200,200) if pair=="BTC-USD" else random.uniform(-0.1,0.1))
        pnl=(price-pos["entry"])*pos["qty"]
        fees=0.1
        net_pnl=pnl-fees
        result="WIN" if net_pnl>0 else "LOSS"
        
        self.events.append({"event_type":"EXIT","event_id":exit_id,"entry_event_id":pos["eid"],"product_id":pair,"exit_price":price,"exit_reason":reason})
        self.events.append({"event_type":"OUTCOME","event_id":pos["eid"]+"_OUTCOME","entry_event_id":pos["eid"],"exit_event_id":exit_id,"product_id":pair,"trade_result":result,"net_pnl_usd":round(net_pnl,2),"fees":{"total_fees_usd":fees}})
        self.trades.append({"pair":pair,"pnl":net_pnl,"result":result})
        logger.info(f"✓ EXIT  {pair:7} {reason:12} {result:4} ${net_pnl:+.2f}")
    
    def _save(self):
        wins=len([t for t in self.trades if t["result"]=="WIN"])
        losses=len([t for t in self.trades if t["result"]=="LOSS"])
        wr=wins/len(self.trades)*100 if self.trades else 0
        total_pnl=sum(t["pnl"] for t in self.trades)
        
        # Pair stats
        pair_stats={}
        for pair in ["BTC-USD","XRP-USD"]:
            pt=[t for t in self.trades if t["pair"]==pair]
            pair_stats[pair]={"trades":len(pt),"wins":len([t for t in pt if t["result"]=="WIN"]),"total_pnl":sum(t["pnl"] for t in pt)}
        
        with open(BASE/"EVENT_LOG.json","w") as f:
            json.dump({"session_id":"dual_pair_test","start_time":self.start.isoformat()+"Z","end_time":datetime.utcnow().isoformat()+"Z","events":self.events,"summary":{"total_trades":len(self.trades),"wins":wins,"losses":losses,"win_rate_pct":round(wr,1),"total_net_pnl_usd":round(total_pnl,2),"pair_stats":pair_stats}},f,indent=2)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"RESULTS: {len(self.trades)} trades | {wr:.0f}% WR | ${total_pnl:+.2f} P&L")
        logger.info(f"  BTC: {pair_stats['BTC-USD']['trades']} trades, ${pair_stats['BTC-USD']['total_pnl']:+.2f}")
        logger.info(f"  XRP: {pair_stats['XRP-USD']['trades']} trades, ${pair_stats['XRP-USD']['total_pnl']:+.2f}")
        logger.info(f"{'='*50}")

o=Orchestrator()
o.run(24)  # 2 min test
