#!/usr/bin/env python3
"""Generates dashboard.py with Phase 3 / Phase 4b toggle."""
from pathlib import Path

CODE = r'''#!/usr/bin/env python3
"""
Streamlit Dashboard - Phase 3 / Phase 4b toggle
"""
import streamlit as st
import pandas as pd
import json, re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import plotly.graph_objects as go

st.set_page_config(page_title="Crypto Bot", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
st.markdown('<style>.positive{color:#0cce6b;font-weight:bold}.negative{color:#ff4454;font-weight:bold}</style>', unsafe_allow_html=True)

BASE_DIR = Path(__file__).parent

with st.sidebar:
    st.title("⚙️ Environment")
    env = st.radio("Select:", ["🔵 Phase 4b — Live Test", "🟣 Phase 3 — Historical"], index=0)
    st.divider()
    refresh = st.slider("Auto-refresh (s)", 5, 60, 10)

IS_4B = env.startswith("🔵")

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
    st.subheader("📈 RSI Over Time")
    if cycles:
        fig = go.Figure()
        for pair, color, label in [("BTC-USD","#f7931a","BTC buy=30"),("XRP-USD","#346aa9","XRP buy=35")]:
            pts = [(c["ts"],c["rsi"]) for c in cycles if c["pair"]==pair]
            if pts:
                fig.add_trace(go.Scatter(x=[p[0] for p in pts],y=[p[1] for p in pts],mode="lines",name=f"{pair} RSI",line=dict(color=color)))
        fig.add_hline(y=30,line_dash="dash",line_color="green",annotation_text="BTC buy=30")
        fig.add_hline(y=35,line_dash="dot",line_color="#346aa9",annotation_text="XRP buy=35")
        fig.add_hline(y=70,line_dash="dash",line_color="red",annotation_text="sell=70")
        fig.update_layout(height=320,xaxis_title="Time",yaxis_title="RSI",hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
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

if IS_4B:
    render_4b()
else:
    render_p3()

st.markdown(f'<meta http-equiv="refresh" content="{refresh}">', unsafe_allow_html=True)
'''

out = Path(__file__).parent / "dashboard.py"
out.write_text(CODE)
print(f"Written {out.stat().st_size} bytes to {out}")
