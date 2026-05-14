#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting Crypto Trading Bot Dashboard..."
echo "📊 Available at: http://localhost:8501"
echo ""

# Use absolute path to venv streamlit to avoid activation issues
"${SCRIPT_DIR}/venv/bin/streamlit" run dashboard.py --server.port 8501 --server.address 0.0.0.0
