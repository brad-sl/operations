#!/bin/bash
# Wrapper script to run Apify Reddit test in virtual environment

# Change to the script's directory
cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Run the Python script
python3 apify_reddit_test.py

# Deactivate virtual environment
deactivate