#!/bin/bash
# Launch Streamlit dashboard for Phase 3 monitoring
# Usage: ./run-dashboard.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting Crypto Trading Bot Dashboard..."
echo "📊 Dashboard will be available at: http://localhost:8501"
echo ""

# Activate venv and run streamlit
source venv/bin/activate
streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0
