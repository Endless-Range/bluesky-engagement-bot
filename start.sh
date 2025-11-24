#!/bin/bash
# BlueSky Engagement Agent - Quick Startup Script
# Run this to start the bot with one command

echo "BlueSky Engagement Agent - Bot Launcher"
echo "========================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ No .env file found!"
    echo ""
    echo "First time setup:"
    echo "  1. Copy the template: cp .env.example .env"
    echo "  2. Edit .env and add your API keys: nano .env"
    echo "  3. Run this script again: ./start.sh"
    echo ""
    exit 1
fi

# Check if Python packages are installed
if ! python3 -c "import atproto" 2>/dev/null; then
    echo "📦 Installing Python packages..."
    pip3 install -r requirements.txt
    echo ""
fi

# Verify setup
echo "🔍 Verifying setup..."
python3 check_setup.py
SETUP_OK=$?

if [ $SETUP_OK -ne 0 ]; then
    echo ""
    echo "❌ Setup verification failed!"
    echo "Fix the issues above and try again."
    exit 1
fi

echo ""
echo "=================================="
echo "🚀 Starting bot in 3 seconds..."
echo "   Press Ctrl+C now to cancel"
echo "=================================="
sleep 3

# Start the bot
python3 bluesky_monitor_v2.py
