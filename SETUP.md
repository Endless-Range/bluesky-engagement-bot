# Setup Guide

Complete setup guide for the BlueSky Engagement Agent.

## Prerequisites

- Python 3.8+
- A Bluesky account
- Anthropic API key (for Claude AI)
- (Optional) Slack workspace for notifications

---

## Step 1: Get Your Credentials

### Bluesky (5 minutes)

1. Create account at [bsky.app](https://bsky.app) (if you don't have one)
   - Choose your preferred handle
2. Generate app password:
   - Go to [bsky.app/settings/app-passwords](https://bsky.app/settings/app-passwords)
   - Click "Add App Password"
   - Name it: `BlueSky Engagement Agent`
   - Click "Create App Password"
   - **Copy the password immediately** (format: `xxxx-xxxx-xxxx-xxxx`)

### Anthropic Claude (5 minutes)

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Sign up or login
3. Navigate to API Keys section
4. Create a new key
5. Copy the key (starts with `sk-ant-`)

### Slack (Optional - 5 minutes)

Choose one option:

#### Option A: Simple Notifications

Get notifications in Slack, approve via terminal or auto-mode.

1. Go to [https://api.slack.com/messaging/webhooks](https://api.slack.com/messaging/webhooks)
2. Click **"Create your Slack app"** → **"From scratch"**
3. Name it: `BlueSky Engagement Bot`
4. Select your workspace → **"Create App"**
5. Click **"Incoming Webhooks"** → Toggle **ON**
6. **"Add New Webhook to Workspace"**
7. Choose channel (create `#bluesky-bot` if needed) → **"Allow"**
8. **Copy the webhook URL** (like `https://hooks.slack.com/services/T.../B.../XXX`)

#### Option B: Interactive Slack (Advanced)

Approve posts with clickable buttons directly in Slack. See [Slack Interactive Setup](#slack-interactive-setup-advanced) below.

---

## Step 2: Install Dependencies

```bash
# Clone the repository
git clone <your-repo-url> bluesky-engagement-agent
cd bluesky-engagement-agent

# Install Python dependencies
pip install -r requirements.txt
```

---

## Step 3: Configure Environment

```bash
# Create your .env file
cp .env.example .env

# Edit .env file
nano .env
```

**Add your credentials:**

```bash
# Bluesky (Required)
BLUESKY_HANDLE=yourhandle.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

# Anthropic Claude (Required)
ANTHROPIC_API_KEY=sk-ant-xxxxx

# Slack (Optional - for notifications)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Bot settings
MANUAL_APPROVAL=true  # Set to false for auto-mode
MAX_REPLIES_PER_HOUR=20
MAX_REPLIES_PER_DAY=150
```

**Save the file** (`Ctrl+X`, `Y`, `Enter` in nano)

---

## Step 4: Test Your Setup

```bash
# Run the test script
python3 test_setup_v2.py
```

You should see:
```
✓ All dependencies installed
✓ Credentials configured
✓ Database working
✓ Bluesky API connection successful
✓ Claude API connection successful
```

**Test Slack (if configured):**
```bash
python3 utils/slack_notifications.py
```

Check your Slack channel for a test message.

---

## Step 5: Run the Bot

### Local Testing (Manual Approval)

```bash
python3 bluesky_monitor_v2.py --manual
```

When the bot finds a post:
```
⚠️  MANUAL APPROVAL REQUIRED
Post from @someuser: Example post text here...
Proposed reply: Example reply here...

Post this reply? (y/n/e=edit):
```

**Options:**
- `y` - Post the reply
- `n` - Skip this post
- `e` - Edit the reply before posting

### Auto Mode (Trusted Operation)

After testing, enable auto mode:

```bash
python3 bluesky_monitor_v2.py --auto
```

Or edit `.env`:
```bash
MANUAL_APPROVAL=false
```

### Run 24/7 with Screen

```bash
# Start screen session
screen -S bluesky-bot

# Run the bot
python3 bluesky_monitor_v2.py --auto

# Detach with Ctrl+A then D
# Bot keeps running in background

# Reattach later
screen -r bluesky-bot
```

---

## Customization

### Change Keywords

Edit `utils/config.py` around line 45:

```python
'keywords': [
    "keyword1",
    "keyword2",
    "keyword3",
    "your custom keywords here"
]
```

### Change Claude's Decision Logic

Edit `utils/base_monitor.py` around line 104 to customize when Claude should reply or reshare.

### Command-Line Options

```bash
# Check every 2 minutes instead of 5
python3 bluesky_monitor_v2.py --interval 120

# Debug mode
python3 bluesky_monitor_v2.py --log-level DEBUG

# Combine options
python3 bluesky_monitor_v2.py --auto --interval 300 --log-level INFO
```

---

## Monitoring

### View Logs

```bash
# Real-time log viewing
tail -f logs/bluesky_monitor_v2.log

# Last 50 lines
tail -n 50 logs/bluesky_monitor_v2.log
```

### Check Database Stats

```bash
sqlite3 data/bluesky_bot.db

# Total posts seen
SELECT COUNT(*) FROM seen_posts WHERE platform='bluesky';

# Total replies sent
SELECT COUNT(*) FROM response_log;

# Replies in the last hour
SELECT COUNT(*) FROM response_log
WHERE posted_at > datetime('now', '-1 hour');

# Recent activity
SELECT posted_at, author_handle, sentiment, response_text
FROM response_log
ORDER BY posted_at DESC
LIMIT 10;

# Exit
.quit
```

---

## Slack Interactive Setup (Advanced)

For **clickable approve/reject buttons** in Slack:

### 1. Create Slack App (if you haven't)

Follow Option A above, then continue below.

### 2. Enable Interactive Components

1. In your Slack app settings, go to **"Interactivity & Shortcuts"**
2. Toggle **"Interactivity"** to ON
3. **Request URL**: Enter your public server URL + `/slack/interactive`
   - Using ngrok: `https://abc123.ngrok.io/slack/interactive`
   - Using public IP: `http://YOUR_IP:3000/slack/interactive`
   - Using domain: `https://bot.yourdomain.com/slack/interactive`
4. **"Save Changes"**

### 3. Get Signing Secret

1. In app settings, go to **"Basic Information"**
2. Scroll to **"App Credentials"**
3. Find **"Signing Secret"** → Click **"Show"**
4. Copy it

### 4. Update .env

```bash
# Add these to your .env
SLACK_SIGNING_SECRET=your_signing_secret_here
SLACK_INTERACTIVE_MODE=true
SLACK_SERVER_PORT=3000
MANUAL_APPROVAL=false
```

### 5. Make Your Server Publicly Accessible

**Option A: ngrok (easiest for testing)**

```bash
# Install ngrok
brew install ngrok  # macOS
# OR download from https://ngrok.com/download

# Start tunnel
ngrok http 3000

# Use the https URL in Slack app settings
```

**Option B: Public IP**

If your server has a public IP:

```bash
# Open firewall port
sudo ufw allow 3000

# Use in Slack app settings
http://YOUR_SERVER_IP:3000/slack/interactive
```

**Option C: Domain with HTTPS**

See [DEPLOYMENT.md](DEPLOYMENT.md) for production setup.

### 6. Deploy

```bash
docker-compose up -d
```

This runs both:
- `bluesky-bot` - Monitors Bluesky
- `slack-approval-server` - Receives button clicks

### 7. Test

Wait for a post to be found, then:
1. Slack notification with buttons appears
2. Click **"Approve"** or **"Reject"**
3. Bot posts (if approved) and updates Slack message

---

## Troubleshooting

### "Bluesky connection failed"

- Check your handle includes `.bsky.social`
- Regenerate app password if needed
- Make sure you copied the FULL password (with dashes)

### "No posts found"

- Your keywords might not be trending right now (that's normal!)
- Try more frequent checks: `--interval 60`
- Keywords might be too specific - adjust in `utils/config.py`

### "Rate limited"

Bot tracks this automatically. Adjust if needed:
```bash
MAX_REPLIES_PER_HOUR=10  # Lower limit
```

### "Slack signature verification failed"

- Check `SLACK_SIGNING_SECRET` in `.env`
- Copy it exactly from Slack app settings
- Restart after changing: `docker-compose restart`

### "Slack Request URL verification failed"

- Make sure server is running: `docker ps`
- Test health endpoint: `curl http://localhost:3000/health`
- Check firewall: `sudo ufw status`
- If using ngrok, verify it's running: `ngrok http 3000`

---

## What's Next?

- For Docker deployment: See [DEPLOYMENT.md](DEPLOYMENT.md)
- For production server setup: See [DEPLOYMENT.md](DEPLOYMENT.md)
- For understanding the codebase: Check `archive/` for technical docs

---

**You're ready! Start monitoring Bluesky and mobilizing grassroots action. 🌿**
