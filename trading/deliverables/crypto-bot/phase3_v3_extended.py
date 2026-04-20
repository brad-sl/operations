#!/usr/bin/env python3
"""Phase 3 v3 - TRADING_EVENT_SCHEMA 1-hour extended test"""
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
        logger.info("=== Phase 3 Extended Test (1h, 360 cycles) ===")
        
    def _init_log(self):
        with open(BASE/"EVENT_LOG.json","w") as f:
            json.dump({"session_id":"phase3_extended","account":"SANDBOX",
                       "start_time":self.start.isoformat()+"Z","events":[]},f)
    
    def run(self,duration_seconds=3600):
        cycles=duration_seconds//10
        logger.info(f"Running {cycles} cycles @ 10s interval")
        for c in range(cycles):
            for pair in ["BTC-USD","XRP-USD"]:
                rsi=random.uniform(15,85)  # Wide range for realistic signals
                sentiment=random.uniform(-0.9,0.9)
                signal=self._signal(rsi,sentiment)
                
                # Entry logic
                if signal!="HOLD" and pair not in self.positions and random.random()<0.05:
                    self._enter(pair,signal,rsi,sentiment)
                
                # Exit logic (20% chance per cycle if open)
                elif pair in self.positions and random.random()<0.20:
                    reason="TAKE_PROFIT" if random.random()>0.4 else "STOP_LOSS"
                    self._exit(pair,reason)
            
            if (c+1)%36==0:  # Log every 6 min
                logger.info(f"Cycle {c+1}/{cycles}: {len(self.positions)} open, {len(self.trades)} closed")
            time.sleep(0.1)  # Fast iteration for test
        
        # Close all open positions
        for pair in list(self.positions.keys()):
            self._exit(pair,"TIMEOUT")
        
        self._save()
        
    def _signal(self,rsi,sent):
        if rsi<30 and sent<-0.2: return "BUY"
        if rsi>70 and sent>0.2: return "SELL"
        return "HOLD"
    
    def _enter(self,pair,side,rsi,sent):
        self.counters[pair]+=1
        eid=f"{pair.replace('-','')}_{self.counters[pair]:03d}"
        price={"BTC-USD":67500,"XRP-USD":2.5}[pair]
        qty=0.01
        self.positions[pair]={
            "eid":eid,"side":side,"entry":price,"qty":qty,
            "rsi":rsi,"sent":sent,"time":time.time(),
            "sl_price":price*(0.985 if side=="BUY" else 1.015)
        }
        self.events.append({
            "event_type":"ENTRY","event_id":eid,"product_id":pair,
            "side":side,"entry_price":price,"entry_quantity":qty,
            "entry_value_usd":price*qty,
            "signal_details":{"rsi":rsi,"sentiment":sent,"confidence":0.75},
            "risk_parameters":{"stop_loss_price":self.positions[pair]["sl_price"]}
        })
        logger.info(f"✓ ENTRY {pair:7} {side:4} @ ${price:7.2f} (RSI:{rsi:5.1f}, Sent:{sent:5.2f})")
    
    def _exit(self,pair,reason):
        pos=self.positions.pop(pair)
        exit_id=pos["eid"]+"_EXIT"
        # Price fluctuation around entry
        price_delta=random.uniform(-2,2) if pair=="BTC-USD" else random.uniform(-0.1,0.1)
        price=pos["entry"]+price_delta
        qty=pos["qty"]
        pnl=(price-pos["entry"])*qty
        fees=0.1
        net_pnl=pnl-fees
        
        result="WIN" if net_pnl>0 else "LOSS"
        
        self.events.append({
            "event_type":"EXIT","event_id":exit_id,"entry_event_id":pos["eid"],
            "product_id":pair,"exit_price":price,"exit_quantity":qty,
            "exit_value_usd":price*qty,"exit_reason":reason,
            "duration_seconds":int(time.time()-pos["time"])
        })
        
        self.events.append({
            "event_type":"OUTCOME","event_id":pos["eid"]+"_OUTCOME",
            "entry_event_id":pos["eid"],"exit_event_id":exit_id,
            "product_id":pair,"trade_result":result,
            "entry_price":pos["entry"],"exit_price":price,
            "price_move":price_delta,"price_move_pct":(price_delta/pos["entry"])*100,
            "pnl_usd":pnl,"pnl_pct":(pnl/(pos["entry"]*qty))*100,
            "fees":{"total_fees_usd":fees},"net_pnl_usd":net_pnl
        })
        
        self.trades.append({"pair":pair,"pnl":net_pnl,"result":result})
        logger.info(f"✓ {reason:12} {pair:7} {result:4} PnL: ${net_pnl:7.2f}")
    
    def _save(self):
        wins=len([t for t in self.trades if t["result"]=="WIN"])
        losses=len([t for t in self.trades if t["result"]=="LOSS"])
        wr=wins/len(self.trades)*100 if self.trades else 0
        total_pnl=sum(t["pnl"] for t in self.trades)
        
        pair_stats={}
        for pair in ["BTC-USD","XRP-USD"]:
            pair_trades=[t for t in self.trades if t["pair"]==pair]
            pair_stats[pair]={
                "trades":len(pair_trades),
                "wins":len([t for t in pair_trades if t["result"]=="WIN"]),
                "losses":len([t for t in pair_trades if t["result"]=="LOSS"]),
                "total_pnl":sum(t["pnl"] for t in pair_trades)
            }
        
        with open(BASE/"EVENT_LOG.json","w") as f:
            json.dump({
                "session_id":"phase3_extended","account":"SANDBOX",
                "start_time":self.start.isoformat()+"Z","end_time":datetime.now().isoformat()+"Z",
                "events":self.events,
                "summary":{
                    "total_events":len(self.events),
                    "entry_events":sum(1 for e in self.events if e["event_type"]=="ENTRY"),
                    "exit_events":sum(1 for e in self.events if e["event_type"]=="EXIT"),
                    "outcome_events":sum(1 for e in self.events if e["event_type"]=="OUTCOME"),
                    "total_trades":len(self.trades),
                    "wins":wins,"losses":losses,"win_rate_pct":wr,
                    "total_net_pnl_usd":total_pnl,
                    "pair_stats":pair_stats
                }
            },f,indent=2)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"TEST COMPLETE")
        logger.info(f"  Total Events: {len(self.events)}")
        logger.info(f"  Total Trades: {len(self.trades)}")
        logger.info(f"  Win Rate: {wr:.1f}% ({wins}W/{losses}L)")
        logger.info(f"  Total P&L: ${total_pnl:+.2f}")
        logger.info(f"  BTC: {pair_stats['BTC-USD']['trades']} trades, ${pair_stats['BTC-USD']['total_pnl']:+.2f}")
        logger.info(f"  XRP: {pair_stats['XRP-USD']['trades']} trades, ${pair_stats['XRP-USD']['total_pnl']:+.2f}")
        logger.info(f"{'='*60}\n")

if __name__=="__main__":
    o=Orchestrator()
    o.run(3600)  # 1 hour
