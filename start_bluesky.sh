#!/bin/bash

# BlueSky Engagement Agent Startup Script

echo "╔════════════════════════════════════════════════════════╗"
echo "║         BlueSky Engagement Agent Bot                   ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo ""
    echo "Please create .env file with your credentials:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    exit 1
fi

# Check if dependencies are installed
python3 -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 Installing dependencies..."
    python3 -m pip install -r requirements.txt
    echo ""
fi

# Run setup test
echo "🔍 Testing setup..."
python3 test_setup_v2.py
if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Setup test failed. Please fix the issues above."
    exit 1
fi

echo ""
echo "✅ Setup test passed!"
echo ""
echo "Choose an option:"
echo "  1) Start bot with terminal approval (recommended for testing)"
echo "  2) Start bot with web dashboard approval (user-friendly)"
echo "  3) Start bot in auto mode (no approval required)"
echo "  4) Just start web dashboard (view stats only)"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        echo ""
        echo "Starting BlueSky Engagement Agent with manual terminal approval..."
        echo "You'll approve each post by typing 'y', 'n', or 'e'"
        echo ""
        python3 bluesky_monitor_v2.py --manual
        ;;
    2)
        echo ""
        echo "Starting web dashboard and BlueSky Engagement Agent..."
        echo "Dashboard will be available at: http://localhost:5000"
        echo ""
        echo "Opening two terminals:"
        echo "  - Terminal 1: Web dashboard"
        echo "  - Terminal 2: BlueSky Engagement Agent"
        echo ""

        # Check if running in screen or tmux
        if [ -n "$STY" ] || [ -n "$TMUX" ]; then
            echo "Detected screen/tmux session"
            echo "Please run these commands in separate windows:"
            echo "  Window 1: python3 web_dashboard.py"
            echo "  Window 2: python3 bluesky_monitor_v2.py --auto"
        else
            # Try to open in separate terminal windows (macOS)
            if [[ "$OSTYPE" == "darwin"* ]]; then
                osascript <<EOF
                tell application "Terminal"
                    do script "cd $(pwd) && python3 web_dashboard.py"
                    do script "cd $(pwd) && sleep 3 && python3 bluesky_monitor_v2.py --auto"
                end tell
EOF
            else
                echo "Please run these commands in separate terminals:"
                echo "  Terminal 1: python3 web_dashboard.py"
                echo "  Terminal 2: python3 bluesky_monitor_v2.py --auto"
            fi
        fi
        ;;
    3)
        echo ""
        echo "⚠️  WARNING: Auto mode will post replies without approval!"
        echo "This is only recommended after testing with manual approval."
        echo ""
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" == "yes" ]; then
            echo ""
            echo "Starting BlueSky Engagement Agent in AUTO mode..."
            python3 bluesky_monitor_v2.py --auto
        else
            echo "Cancelled."
            exit 0
        fi
        ;;
    4)
        echo ""
        echo "Starting web dashboard only..."
        echo "Visit: http://localhost:5000"
        echo ""
        python3 web_dashboard.py
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac
