#!/bin/bash
# LEMS ERP — Aprovecho Research Center
# Double-click this file in Finder to launch (macOS)
# Or run:  bash start_lems.command

# ── Change to the directory where this script lives ──────────────────────────
cd "$(dirname "$0")"

# ── Check Python 3 is available ───────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo ""
    echo "ERROR: python3 not found."
    echo "Install Python 3.10+ from https://www.python.org"
    echo ""
    read -p "Press Enter to close..."
    exit 1
fi

# ── Install / update dependencies quietly ────────────────────────────────────
echo "Checking dependencies..."
python3 -m pip install -r requirements.txt --quiet --disable-pip-version-check

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "Starting LEMS ERP..."
echo "Open your browser to:  http://localhost:8000"
echo "Team members on the same network: http://$(hostname -s):8000"
echo "Press Ctrl+C to stop the server."
echo ""
export LEMS_HOST=0.0.0.0
python3 main.py
