#!/usr/bin/env python3
"""
Streamlit Dashboard - Phase 3 / Phase 4b toggle
"""
import streamlit as st
import pandas as pd
import json, re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

st.set_page_config(page_title="Crypto Bot", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown('<style>.positive{color:#0cce6b;font-weight:bold}.negative{color:#ff4454;font-weight:bold}</style>', unsafe_allow_html=True)

BASE_DIR = Path(__file__).parent

with st.sidebar:
    st.title("⚙️ Environment")
    env = st.radio("Select:", ["🟢 Phase 4c — Short Test", "🟢 Phase 4c — 24h Test", "🔵 Phase 4b — Live Test", "🟣 Phase 3 — Historical"], index=0)
    st.divider()
    refresh = st.slider("Auto-refresh (s)", 5, 60, 10)

IS_4C_SHORT = env.startswith("🟢 Phase 4c — Short")
IS_4C_LONG = env.startswith("🟢 Phase 4c — 24h")
IS_4B = env.startswith("🔵")
IS_4C = IS_4C_SHORT or IS_4C_LONG

@st.cache_data(ttl=10)
def load_4c_short():
    """Load Phase 4c short test data."""
    log = BASE_DIR / "phase4c_short_test_*.log"
    import glob
    paths = glob.glob(str(BASE_DIR / "phase4c_short_test_*.log"))
    path = sorted(paths)[-1] if paths else None
    if not path:
        return {"cycles":[], "trades":[], "pnl":{"BTC-USD":0.0,"XRP-USD":0.0,"DOGE-USD":0.0,"ETH-USD":0.0}, "complete":False, "path":"No short test log"}
    path = paths[-1]
    if not path.exists():
        return {"cycles":[], "trades":[], "pnl":{"BTC-USD":0.0,"XRP-USD":0.0,"DOGE-USD":0.0,"ETH-USD":0.0}, "complete":False, "path":str(path)}
    cycles, trades = [], []
    pnl = {"BTC-USD":0.0, "XRP-USD":0.0, "DOGE-USD":0.0, "ETH-USD":0.0}
    complete = False
    cr = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?Pair: ([\w-]+) \| Price: ([\d.]+) \| RSI: ([\d.]+) \| Regime: (\w+) \| Thresholds: ([\w=/]+) \| Sig: (\w+) \(conf=([\d.]+)\) \| Mult: ([\d.]+)x \| Weighted: ([\d.]+) \| Sentiment: ([+-]?[\d.]+)")
    or_ = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?OPEN BUY ([\w-]+) @ \$([\d.]+) \| notional=\$([\d.]+)")
    er  = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?EXIT \[(\w+)\] ([\w-]+) @ \$([\d.]+) \| PnL=\$([+-]?[\d.]+)")
    pr  = re.compile(r"Final Daily PnL: BTC=\$([+-]?[\d.]+) \| XRP=\$([+-]?[\d.]+) \| DOGE=\$([+-]?[\d.]+) \| ETH=\$([+-]?[\d.]+)")
    for line in path.read_text().splitlines():
        m = cr.search(line)
        if m:
            cycles.append({"ts":m.group(1),"pair":m.group(2),"price":float(m.group(3)),"rsi":float(m.group(4)),"regime":m.group(5),"signal":m.group(7),"conf":float(m.group(8)),"weighted":float(m.group(10)),"sentiment":float(m.group(11))})
            continue
        m = or_.search(line)
        if m:
            trades.append({"ts":m.group(1),"pair":m.group(2),"type":"OPEN","price":float(m.group(3)),"notional":float(m.group(4)),"pnl":None})
            continue
        m = er.search(line)
        if m:
            trades.append({"ts":m.group(1),"type":"EXIT","reason":m.group(2),"pair":m.group(3),"price":float(m.group(4)),"pnl":float(m.group(5))})
            continue
        m = pr.search(line)
        if m:
            pnl = {"BTC-USD":float(m.group(1)),"XRP-USD":float(m.group(2)),"DOGE-USD":float(m.group(3)),"ETH-USD":float(m.group(4))}
        if "PHASE 4C COMPLETE" in line:
            complete = True
    return {"cycles":cycles,"trades":trades,"pnl":pnl,"complete":complete,"path":str(path)}

@st.cache_data(ttl=10)
def load_4b():
    log  = BASE_DIR / "PHASE4B_SMOKE_TEST.log"
    run  = BASE_DIR / "phase4b_24h_run.txt"
    path = run if (run.exists() and run.stat().st_mtime > (log.stat().st_mtime if log.exists() else 0)) else log
    if not path.exists():
        return {"cycles":[], "trades":[], "pnl":{"BTC-USD":0.0,"XRP-USD":0.0}, "complete":False, "path":str(path)}
    cycles, trades = [], []
    pnl = {"BTC-USD":0.0, "XRP-USD":0.0}
    complete = False
    cr = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?Pair: ([\w-]+) \| Price: ([\d.]+) \| RSI: ([\d.]+) \| Regime: (\w+) \| Thresholds: ([\w=/]+) \| Sig: (\w+) \(conf=([\d.]+)\) \| Mult: ([\d.]+)x \| Weighted: ([\d.]+) \| Sentiment: ([+-]?[\d.]+)")
    or_ = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?OPEN BUY ([\w-]+) @ \$([\d.]+) \| notional=\$([\d.]+)")
    er  = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?EXIT \[(\w+)\] ([\w-]+) @ \$([\d.]+) \| PnL=\$([+-]?[\d.]+)")
    pr  = re.compile(r"Final Daily PnL: BTC=\$([+-]?[\d.]+) \| XRP=\$([+-]?[\d.]+)")
    for line in path.read_text().splitlines():
        m = cr.search(line)
        if m:
            cycles.append({"ts":m.group(1),"pair":m.group(2),"price":float(m.group(3)),"rsi":float(m.group(4)),"regime":m.group(5),"signal":m.group(7),"conf":float(m.group(8)),"weighted":float(m.group(10)),"sentiment":float(m.group(11))})
            continue
        m = or_.search(line)
        if m:
            trades.append({"ts":m.group(1),"pair":m.group(2),"type":"OPEN","price":float(m.group(3)),"notional":float(m.group(4)),"pnl":None})
            continue
        m = er.search(line)
        if m:
            trades.append({"ts":m.group(1),"type":"EXIT","reason":m.group(2),"pair":m.group(3),"price":float(m.group(4)),"pnl":float(m.group(5))})
            continue
        m = pr.search(line)
        if m:
            pnl = {"BTC-USD":float(m.group(1)),"XRP-USD":float(m.group(2))}
        if "SMOKE TEST COMPLETE" in line:
            complete = True
    return {"cycles":cycles,"trades":trades,"pnl":pnl,"complete":complete,"path":str(path)}

@st.cache_data(ttl=10)
def load_p3():
    p = BASE_DIR / "EVENT_LOG.json"
    if not p.exists(): return {"events":[],"summary":{}}
    try:
        return json.loads(p.read_text())
    except: return {"events":[],"summary":{}}

def render_4b():
    d = load_4b()
    cycles, trades, pnl, complete = d["cycles"], d["trades"], d["pnl"], d["complete"]
    st.title("📊 Phase 4b — Live Test Monitor")
    st.caption(f"Source: `{d['path']}`")
    exits = [t for t in trades if t["type"]=="EXIT"]
    wins  = [t for t in exits if (t.get("pnl") or 0) > 0]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Status", "✅ Done" if complete else "🔄 Running")
    c2.metric("Total PnL", f"${sum(pnl.values()):+.2f}")
    c3.metric("Cycles", len(set((c["ts"][:16],c["pair"]) for c in cycles)))
    c4.metric("Trades", len(exits))
    st.divider()
    a,b = st.columns(2)
    a.metric("BTC-USD PnL", f"${pnl.get('BTC-USD',0):+.2f}")
    b.metric("XRP-USD PnL", f"${pnl.get('XRP-USD',0):+.2f}")
    if exits:
        st.metric("Win Rate", f"{len(wins)/len(exits):.1%}", f"{len(wins)}W / {len(exits)-len(wins)}L")
    st.divider()
    st.subheader("📋 Recent Cycles")
    if cycles:
        df = pd.DataFrame(cycles[-40:])[["ts","pair","price","rsi","regime","signal","weighted","sentiment"]]
        df.columns = ["Time","Pair","Price","RSI","Regime","Signal","Weighted","Sentiment"]
        st.dataframe(df, use_container_width=True, height=320)
    else:
        st.info("No cycles yet.")
    st.subheader("📈 RSI Over Time (BTC=orange / XRP=blue | buy<30/35, sell>70)")
    if cycles:
        btc_rsi = {c["ts"]: c["rsi"] for c in cycles if c["pair"]=="BTC-USD"}
        xrp_rsi = {c["ts"]: c["rsi"] for c in cycles if c["pair"]=="XRP-USD"}
        all_ts = sorted(set(btc_rsi) | set(xrp_rsi))
        chart_df = pd.DataFrame({"BTC-USD RSI": [btc_rsi.get(t) for t in all_ts], "XRP-USD RSI": [xrp_rsi.get(t) for t in all_ts]}, index=all_ts)
        st.line_chart(chart_df, height=280)
        st.caption("Thresholds: BTC buy<30 / XRP buy<35 / Sell>70")
    st.subheader("💱 Trades")
    if trades:
        st.dataframe(pd.DataFrame(trades), use_container_width=True, height=220)
    else:
        st.info("No trades yet — waiting for RSI crossover signal.")
    st.caption(f"🔄 {datetime.now().strftime('%H:%M:%S')} | refresh={refresh}s")

def render_p3():
    d = load_p3()
    s = d.get("summary",{})
    events = d.get("events",[])
    st.title("📊 Phase 3 — Historical Monitor")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Session", d.get("session_id","N/A"))
    c2.metric("Account", d.get("account","SANDBOX"))
    c3.metric("X API", "✅" if d.get("x_api_ready") else "❌")
    c4.metric("Trades", int(s.get("total_trades",0)))
    st.divider()
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Win Rate", f"{s.get('win_rate',0):.1%}")
    m2.metric("Total P&L", f"${s.get('total_pnl',0):.2f}")
    m3.metric("Wins", int(s.get("wins",0)))
    m4.metric("Losses", int(s.get("losses",0)))
    st.divider()
    trades = [e for e in events if e.get("type")=="trade"]
    if trades:
        rows = [{"Time":e.get("timestamp","")[:19],"Pair":e.get("pair"),"Signal":e.get("signal","").upper(),"Entry":f"${e.get('entry_price',0):.2f}","Exit":f"${e.get('exit_price',0):.2f}","P&L":f"${e.get('pnl',0):.2f}","":"✅" if e.get("pnl",0)>0 else "❌"} for e in trades[-30:]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)
    else:
        st.info("No trades in EVENT_LOG.json.")
    st.caption(f"🔄 {datetime.now().strftime('%H:%M:%S')}")

if IS_4C:
    # Phase 4c — 24h test
    d = load_4c()
    cycles, trades, pnl, complete = d["cycles"], d["trades"], d["pnl"], d["complete"]
    st.title("📊 Phase 4c — 24h Test Monitor")
    st.caption(f"Source: `{d['path']}`")
    exits = [t for t in trades if t["type"]=="EXIT"]
    wins  = [t for t in exits if (t.get("pnl") or 0) > 0]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Status", "✅ Done" if complete else "🔄 Running")
    c2.metric("Total PnL", f"${sum(pnl.values()):+.2f}")
    c3.metric("Cycles", len(set((c["ts"][:16],c["pair"]) for c in cycles)))
    c4.metric("Trades", len(exits))
    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("BTC-USD PnL", f"${pnl.get('BTC-USD',0):+.2f}")
    col2.metric("XRP-USD PnL", f"${pnl.get('XRP-USD',0):+.2f}")
    col3.metric("DOGE-USD PnL", f"${pnl.get('DOGE-USD',0):+.2f}")
    col4.metric("ETH-USD PnL", f"${pnl.get('ETH-USD',0):+.2f}")
    if exits:
        st.metric("Win Rate", f"{len(wins)/len(exits):.1%}", f"{len(wins)}W / {len(exits)-len(wins)}L")
    st.divider()
    st.subheader("📋 Recent Cycles")
    if cycles:
        df = pd.DataFrame(cycles[-50:])[["ts","pair","price","rsi","regime","signal","weighted","sentiment"]]
        df.columns = ["Time","Pair","Price","RSI","Regime","Signal","Weighted","Sentiment"]
        st.dataframe(df, use_container_width=True, height=320)
    else:
        st.info("No cycles yet.")
    st.subheader("📈 RSI Over Time (Dynamic Thresholds)")
    if cycles:
        all_pairs = list(set(c["pair"] for c in cycles))
        chart_data = {pair: {c["ts"]: c["rsi"] for c in cycles if c["pair"]==pair} for pair in all_pairs}
        all_ts = sorted(set().union(*(cd.keys() for cd in chart_data.values())))
        chart_df = pd.DataFrame({pair: [chart_data[pair].get(t) for t in all_ts] for pair in all_pairs}, index=all_ts)
        st.line_chart(chart_df, height=280)
        st.caption("Dynamic RSI Thresholds applied per regime")
    st.subheader("💱 Trades")
    if trades:
        st.dataframe(pd.DataFrame(trades), use_container_width=True, height=220)
    else:
        st.info("No trades yet — waiting for RSI crossover signals.")
    st.caption(f"🔄 {datetime.now().strftime('%H:%M:%S')} | refresh={refresh}s | 24h test in progress")
elif IS_4B:
    render_4b()
else:
    render_p3()

st.markdown(f'<meta http-equiv="refresh" content="{refresh}">', unsafe_allow_html=True)
