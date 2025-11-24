# BlueSky Engagement Agent

Automated Bluesky monitoring and engagement bot for social media interactions.

**Simple. Effective. Runs anywhere.**

## What It Does

- 🔍 Monitors Bluesky for relevant discussions
- 🤖 Uses Claude AI to analyze sentiment
- 💬 Replies to posts based on configured criteria
- 🔁 Reshares content based on your preferences
- 📱 Sends Slack notifications for remote approval
- 💾 Tracks everything in SQLite (never replies twice)

## Quick Start

### Local Testing

```bash
# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
nano .env  # Add your credentials

# Test
python3 test_setup_v2.py

# Run
python3 bluesky_monitor_v2.py --manual
```

### Docker (Home Server / Hetzner)

```bash
# Setup
git clone your-repo bluesky-engagement-agent
cd bluesky-engagement-agent
cp .env.example .env
nano .env  # Add credentials

# Run
docker-compose up -d

# Monitor
docker-compose logs -f
```

**Full guides:** [SETUP.md](SETUP.md) | [DEPLOYMENT.md](DEPLOYMENT.md)

## Required Credentials

Add to `.env`:

```bash
# Bluesky (5 min setup)
BLUESKY_HANDLE=yourhandle.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Slack (optional - for remote notifications)
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
```

**Get Bluesky app password:** bsky.app/settings/app-passwords
**Get Anthropic key:** console.anthropic.com
**Get Slack webhook:** See [SETUP.md](SETUP.md)

## Server Recommendations

### ✅ Hetzner VPS 

- $3-5/month
- More reliable uptime
- Public IP if needed

Either works great!

## How It Works

```
Search Bluesky every 5 min
  ↓
Find posts matching your keywords
  ↓
Claude analyzes each post
  ↓
Decides: REPLY / RESHARE / IGNORE
  ↓
Send Slack notification (optional)
  ↓
You approve (or auto-approve)
  ↓
Bot posts + saves to database
```

**Smart features:**
- Never replies to same post twice (database)
- Rate limiting (20/hour max)
- Quality filters (ignores spam, old posts)
- Exponential backoff on errors

## Customization

### Change Keywords

Edit your `.env` file:
```bash
KEYWORDS=keyword1,keyword2,keyword3,your keywords here
```

Keywords are comma-separated. The bot will monitor Bluesky for posts containing any of these terms.

### Change Claude's Logic

Edit `utils/base_monitor.py` line 104:
```python
RESHARE when:
- Positive industry news
- Add your criteria here
```

## Command-Line Options

```bash
# Manual approval (terminal)
python3 bluesky_monitor_v2.py --manual

# Auto mode (for servers)
python3 bluesky_monitor_v2.py --auto

# Check every 2 minutes instead of 5
python3 bluesky_monitor_v2.py --interval 120

# Debug mode
python3 bluesky_monitor_v2.py --log-level DEBUG
```

## Slack Integration

Two modes available:

**Interactive Mode** - Click approve/reject buttons in Slack (no SSH needed!)
**Simple Mode** - Get notifications, approve via terminal or auto-mode

**Setup guide:** [SETUP.md](SETUP.md#slack-interactive-setup-advanced)

## Monitoring

```bash
# View logs
tail -f logs/bluesky_monitor_v2.log

# Docker logs
docker-compose logs -f

# Check database
sqlite3 data/bluesky_bot.db
SELECT COUNT(*) FROM response_log;
```

## Project Structure

```
bluesky-engagement-agent/
├── bluesky_monitor_v2.py   # Main bot
├── .env                     # Your credentials
├── requirements.txt         # Dependencies
├── Dockerfile              # Docker setup
├── docker-compose.yml      # Docker Compose
│
├── utils/                  # Core modules
│   ├── base_monitor.py     # Bot logic
│   ├── config.py           # Configuration
│   ├── database.py         # SQLite
│   ├── slack_notifications.py  # Slack
│   └── ...
│
├── data/                   # Database (auto-created)
├── logs/                   # Log files (auto-created)
│
└── archive/                # Unused features
    ├── x-twitter/          # X/Twitter bot
    ├── web-dashboard/      # Web UI
    └── old-versions/       # V1 files
```

## Documentation

- **[SETUP.md](SETUP.md)** - Complete setup guide (credentials, configuration, customization)
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment (Docker, servers, monitoring)

## Troubleshooting

**No posts found?**
Normal! Your keywords might not be trending. Bot keeps checking.

**Bluesky connection failed?**
Check credentials in `.env`. Regenerate app password if needed.

**Docker container restarting?**
Check logs: `docker-compose logs`

## License

MIT - Use for any purpose.

---

**Deploy to your server with Docker. Get Slack notifications. Done.**
