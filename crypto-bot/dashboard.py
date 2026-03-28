#!/usr/bin/env python3
"""
Streamlit Dashboard for Phase 3 Crypto Trading Bot
Monitors live trades, P&L, RSI signals, and X sentiment data
"""

import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
import plotly.graph_objects as go
from collections import defaultdict

# Configure Streamlit
st.set_page_config(
    page_title="Crypto Trading Bot Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 8px;
        margin: 10px 0;
    }
    .positive { color: #0cce6b; font-weight: bold; }
    .negative { color: #ff4454; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Paths
BASE_DIR = Path(__file__).parent
EVENT_LOG_PATH = BASE_DIR / "EVENT_LOG.json"
PHASE3_LOG_PATH = BASE_DIR / "phase3_48h.log"

@st.cache_data(ttl=10)  # Refresh every 10 seconds
def load_event_log():
    """Load EVENT_LOG.json with live trading data"""
    if not EVENT_LOG_PATH.exists():
        return {
            "session_id": "phase3_v4",
            "account": "SANDBOX",
            "start_time": datetime.utcnow().isoformat() + "Z",
            "end_time": None,
            "sentiment_mode": "real_x_api",
            "x_api_ready": True,
            "events": [],
            "summary": {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "break_even": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_pnl_per_trade": 0.0
            }
        }
    
    try:
        with open(EVENT_LOG_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def format_pnl(value):
    """Format P&L with color"""
    if value > 0:
        return f'<span class="positive">+${value:.2f}</span>'
    elif value < 0:
        return f'<span class="negative">${value:.2f}</span>'
    else:
        return f'${value:.2f}'

def parse_timestamp(ts):
    """Parse ISO timestamp"""
    try:
        if ts.endswith('Z'):
            ts = ts[:-1]
        return datetime.fromisoformat(ts)
    except:
        return None

# ============================================================================
# MAIN DASHBOARD
# ============================================================================

st.title("📊 Crypto Trading Bot — Phase 3 Monitor")

# Load data
event_data = load_event_log()
summary = event_data.get("summary", {})
events = event_data.get("events", [])

# Session info
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Session",
        event_data.get("session_id", "N/A"),
        "SANDBOX"
    )

with col2:
    st.metric(
        "Account",
        event_data.get("account", "N/A"),
        "No real funds"
    )

with col3:
    st.metric(
        "X API",
        "✅ Ready" if event_data.get("x_api_ready") else "❌ Offline",
        "Real sentiment"
    )

with col4:
    st.metric(
        "Sentiment Mode",
        event_data.get("sentiment_mode", "N/A").replace("_", " ").title()
    )

st.divider()

# ============================================================================
# KEY METRICS
# ============================================================================

st.subheader("📈 Trading Summary")

m1, m2, m3, m4, m5 = st.columns(5)

with m1:
    st.metric(
        "Total Trades",
        int(summary.get("total_trades", 0)),
        "Completed"
    )

with m2:
    st.metric(
        "Win Rate",
        f"{summary.get('win_rate', 0):.1%}",
        f"✅ {summary.get('wins', 0)} wins"
    )

with m3:
    pnl = summary.get("total_pnl", 0)
    delta_color = "inverse" if pnl < 0 else "off"
    st.metric(
        "Total P&L",
        f"${pnl:.2f}",
        delta=f"${pnl:.2f}",
        delta_color=delta_color
    )

with m4:
    avg_pnl = summary.get("avg_pnl_per_trade", 0)
    st.metric(
        "Avg P&L/Trade",
        f"${avg_pnl:.2f}",
        "Per trade"
    )

with m5:
    losses = summary.get("losses", 0)
    st.metric(
        "Losses",
        f"❌ {losses}",
        "Trades in loss"
    )

st.divider()

# ============================================================================
# RECENT TRADES
# ============================================================================

st.subheader("📋 Recent Trades")

if events:
    # Filter for trade events only
    trades = [e for e in events if e.get("type") == "trade"]
    
    if trades:
        # Convert to DataFrame
        trade_data = []
        for trade in trades[-20:]:  # Last 20 trades
            timestamp = parse_timestamp(trade.get("timestamp", ""))
            trade_data.append({
                "Time": timestamp.strftime("%H:%M:%S") if timestamp else "N/A",
                "Pair": trade.get("pair", "N/A"),
                "Signal": trade.get("signal", "N/A").upper(),
                "Entry Price": f"${trade.get('entry_price', 0):.2f}",
                "Exit Price": f"${trade.get('exit_price', 0):.2f}",
                "P&L": f"${trade.get('pnl', 0):.2f}",
                "Win": "✅" if trade.get("pnl", 0) > 0 else "❌",
                "Sentiment": f"{trade.get('sentiment_score', 0):.2f}",
                "RSI": f"{trade.get('rsi_value', 0):.1f}"
            })
        
        df_trades = pd.DataFrame(trade_data)
        
        # Color the P&L column
        def color_pnl(val):
            if "+" in val or val.startswith("$0"):
                return "color: #0cce6b; font-weight: bold;"
            else:
                return "color: #ff4454; font-weight: bold;"
        
        styled_df = df_trades.style.applymap(color_pnl, subset=["P&L"])
        st.dataframe(styled_df, use_container_width=True, height=400)
    else:
        st.info("No trades yet. Waiting for first signal...")
else:
    st.warning("No events recorded yet. Test may still be initializing.")

st.divider()

# ============================================================================
# SIGNAL BREAKDOWN
# ============================================================================

st.subheader("🎯 Signal Analysis")

signals = defaultdict(int)
for trade in [e for e in events if e.get("type") == "trade"]:
    signal = trade.get("signal", "unknown").upper()
    signals[signal] += 1

if signals:
    col1, col2 = st.columns(2)
    
    with col1:
        # Signal distribution pie chart
        fig_signals = go.Figure(data=[
            go.Pie(
                labels=list(signals.keys()),
                values=list(signals.values()),
                hole=0.3,
                marker=dict(colors=['#0cce6b', '#ff4454', '#fbbf24'])
            )
        ])
        fig_signals.update_layout(
            title="Signals by Type",
            height=400,
            showlegend=True
        )
        st.plotly_chart(fig_signals, use_container_width=True)
    
    with col2:
        # Pair breakdown
        pairs = defaultdict(int)
        for trade in [e for e in events if e.get("type") == "trade"]:
            pair = trade.get("pair", "unknown")
            pairs[pair] += 1
        
        fig_pairs = go.Figure(data=[
            go.Bar(x=list(pairs.keys()), y=list(pairs.values()), marker_color=['#1f77b4', '#ff7f0e'])
        ])
        fig_pairs.update_layout(
            title="Trades by Pair",
            xaxis_title="Pair",
            yaxis_title="Count",
            height=400,
            showlegend=False
        )
        st.plotly_chart(fig_pairs, use_container_width=True)
else:
    st.info("Signals will appear as trades are generated.")

st.divider()

# ============================================================================
# SENTIMENT TRACKING
# ============================================================================

st.subheader("💬 X Sentiment Tracking")

sentiment_data = [
    e for e in events 
    if e.get("type") == "sentiment" and e.get("pair")
]

if sentiment_data:
    # Group by pair
    btc_sentiment = [e for e in sentiment_data if e.get("pair") == "BTC-USD"]
    xrp_sentiment = [e for e in sentiment_data if e.get("pair") == "XRP-USD"]
    
    col1, col2 = st.columns(2)
    
    with col1:
        if btc_sentiment:
            latest_btc = btc_sentiment[-1].get("sentiment_score", 0)
            st.metric("BTC-USD Sentiment", f"{latest_btc:.2f}", "Latest score")
            
            # Sentiment history chart
            btc_scores = [e.get("sentiment_score", 0) for e in btc_sentiment[-50:]]
            fig_btc = go.Figure()
            fig_btc.add_trace(go.Scatter(
                y=btc_scores,
                mode='lines',
                name='BTC Sentiment',
                line=dict(color='#f7931a')
            ))
            fig_btc.update_layout(
                title="BTC-USD Sentiment History",
                xaxis_title="Time",
                yaxis_title="Sentiment Score",
                height=300,
                showlegend=False,
                hovermode='x'
            )
            st.plotly_chart(fig_btc, use_container_width=True)
    
    with col2:
        if xrp_sentiment:
            latest_xrp = xrp_sentiment[-1].get("sentiment_score", 0)
            st.metric("XRP-USD Sentiment", f"{latest_xrp:.2f}", "Latest score")
            
            # Sentiment history chart
            xrp_scores = [e.get("sentiment_score", 0) for e in xrp_sentiment[-50:]]
            fig_xrp = go.Figure()
            fig_xrp.add_trace(go.Scatter(
                y=xrp_scores,
                mode='lines',
                name='XRP Sentiment',
                line=dict(color='#23292f')
            ))
            fig_xrp.update_layout(
                title="XRP-USD Sentiment History",
                xaxis_title="Time",
                yaxis_title="Sentiment Score",
                height=300,
                showlegend=False,
                hovermode='x'
            )
            st.plotly_chart(fig_xrp, use_container_width=True)
else:
    st.info("Sentiment data will appear as X API fetches real tweets.")

st.divider()

# ============================================================================
# PHASE 3 TEST STATUS
# ============================================================================

st.subheader("⏱️ Test Status")

start_time = parse_timestamp(event_data.get("start_time", ""))
end_time = parse_timestamp(event_data.get("end_time", ""))

if start_time:
    elapsed = datetime.utcnow() - start_time.replace(tzinfo=None)
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Start", start_time.strftime("%Y-%m-%d %H:%M PT"))
    
    with col2:
        st.metric("Expected End", "2026-03-28 22:12 PT")
    
    with col3:
        st.metric("Elapsed", f"{int(elapsed.total_seconds() / 3600)}h {int((elapsed.total_seconds() % 3600) / 60)}m")

# Auto-refresh indicator
st.caption("🔄 Auto-refreshing every 10 seconds | Last updated: " + datetime.now().strftime("%H:%M:%S"))
