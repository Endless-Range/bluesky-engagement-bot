# Deployment Guide

Production deployment options for BlueSky Engagement Agent.

---

## Deployment Options

### Option 1: Home Server (Recommended)

**Pros:**
- Free
- You already have Docker
- Full control
- No latency issues

**Cons:**
- Depends on your internet connection
- Manual updates required

### Option 2: Hetzner VPS

**Pros:**
- Reliable uptime
- $3-5/month
- Public IP included
- Professional setup

**Cons:**
- Monthly cost
- Requires server management

**Note:** Location doesn't matter - Bluesky API works globally!

---

## Docker Deployment

The easiest way to deploy on any server with Docker.

### Quick Start

```bash
# 1. Clone repo
cd /path/to/your/apps
git clone <your-repo-url> bluesky-engagement-agent
cd bluesky-engagement-agent

# 2. Configure
cp .env.example .env
nano .env  # Add your credentials

# 3. Start
docker-compose up -d

# 4. Monitor
docker-compose logs -f
```

### Docker Commands Reference

```bash
# View real-time logs
docker-compose logs -f

# View last 50 lines
docker-compose logs --tail=50

# Restart bot
docker-compose restart

# Stop bot
docker-compose stop

# Stop and remove containers
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Check container status
docker ps | grep bluesky

# Resource usage
docker stats bluesky-bot
```

### Data Persistence

Files persist on your host machine:
- `./data/bluesky_bot.db` - SQLite database
- `./logs/` - Log files

These remain even if you recreate containers.

### Testing in Docker

For manual approval testing:

Edit `docker-compose.yml`:
```yaml
command: python3 bluesky_monitor_v2.py --manual --log-level DEBUG
```

Then run without detaching:
```bash
docker-compose up
```

Type `y`/`n` in terminal to approve/reject.

---

## Production Server Setup

### Prerequisites

- Server with Docker installed
- (Optional) Domain name
- (Optional) Reverse proxy (Caddy/nginx)

### Basic Setup

```bash
# SSH to your server
ssh user@your-server-ip

# Install Docker (if not installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose (if not installed)
sudo apt install docker-compose

# Clone and deploy
git clone <your-repo-url> bluesky-engagement-agent
cd bluesky-engagement-agent
cp .env.example .env
nano .env  # Add credentials
docker-compose up -d
```

### With Domain Name (HTTPS)

If you have a domain like `bot.yourdomain.com`:

#### Using Caddy (Recommended)

**1. Add DNS A Record:**
```
Type: A
Name: bot (or bluesky-bot)
Value: YOUR_SERVER_IP
TTL: 3600
```

**2. Install Caddy (if not already):**
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

**3. Configure Caddy:**
```bash
sudo nano /etc/caddy/Caddyfile
```

Add:
```
bot.yourdomain.com {
    reverse_proxy localhost:3000
}
```

**4. Reload Caddy:**
```bash
sudo systemctl reload caddy
sudo systemctl status caddy
```

**5. Update Slack App Settings:**

If using interactive Slack, update Request URL to:
```
https://bot.yourdomain.com/slack/interactive
```

**6. Test:**
```bash
curl https://bot.yourdomain.com/health
# Should return: {"status":"healthy"}
```

#### Using nginx

**1. Install nginx:**
```bash
sudo apt install nginx certbot python3-certbot-nginx
```

**2. Create nginx config:**
```bash
sudo nano /etc/nginx/sites-available/bluesky-bot
```

Add:
```nginx
server {
    listen 80;
    server_name bot.yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**3. Enable site:**
```bash
sudo ln -s /etc/nginx/sites-available/bluesky-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

**4. Get SSL certificate:**
```bash
sudo certbot --nginx -d bot.yourdomain.com
```

---

## Slack Interactive Mode Deployment

For production Slack interactive approvals:

### Configuration

Update `.env`:
```bash
# Slack Interactive
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_SIGNING_SECRET=your_signing_secret
SLACK_INTERACTIVE_MODE=true
SLACK_SERVER_PORT=3000

# Bot settings
MANUAL_APPROVAL=false
```

### Firewall

Open the port (if using public IP without reverse proxy):
```bash
sudo ufw allow 3000
sudo ufw status
```

### Docker Compose

The provided `docker-compose.yml` already includes both services:
- `bluesky-bot` - Monitors Bluesky
- `slack-approval-server` - Handles button clicks

Just run:
```bash
docker-compose up -d
```

### Verify

```bash
# Check both containers running
docker ps

# Test health endpoint
curl http://localhost:3000/health

# Or with domain
curl https://bot.yourdomain.com/health
```

---

## Monitoring

### Check Service Status

```bash
# Container status
docker ps | grep bluesky

# View logs
docker-compose logs -f

# Health check
curl http://localhost:3000/health
```

### Database Monitoring

```bash
# Connect to database
sqlite3 data/bluesky_bot.db

# Quick stats
SELECT
  (SELECT COUNT(*) FROM seen_posts) as total_seen,
  (SELECT COUNT(*) FROM response_log) as total_responses,
  (SELECT COUNT(*) FROM response_log WHERE posted_at > datetime('now', '-1 hour')) as recent_responses;

# Pending approvals (if using interactive mode)
SELECT * FROM pending_approvals WHERE status = 'pending';

# Exit
.quit
```

### System Resources

```bash
# Real-time resource usage
docker stats bluesky-bot

# Disk usage
du -sh data/ logs/
```

---

## Backups

### Automated Daily Backup

Add to crontab:
```bash
crontab -e
```

Add line:
```bash
0 2 * * * cd /path/to/bluesky-engagement-agent && cp data/bluesky_bot.db data/backups/bluesky_bot_$(date +\%Y\%m\%d).db
```

This backs up the database daily at 2 AM.

### Manual Backup

```bash
# Backup database
cp data/bluesky_bot.db data/bluesky_bot_backup_$(date +%Y%m%d).db

# Or entire data directory
tar -czf bluesky_bot_backup_$(date +%Y%m%d).tar.gz data/ logs/
```

### Restore from Backup

```bash
# Stop bot
docker-compose down

# Restore database
cp data/backups/bluesky_bot_20240315.db data/bluesky_bot.db

# Restart
docker-compose up -d
```

---

## Updates

### Pull Latest Changes

```bash
cd bluesky-engagement-agent
git pull
docker-compose up -d --build
```

### Update Dependencies

```bash
# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## Auto-Start on Boot

Docker Compose with `restart: unless-stopped` automatically restarts containers.

Ensure Docker starts on boot:
```bash
sudo systemctl enable docker
```

---

## Resource Requirements

Very lightweight:
- **RAM**: 100-200 MB
- **CPU**: Minimal (checks every 5 minutes)
- **Disk**: 10-50 MB (grows slowly)
- **Network**: Minimal (few API calls per check)

Perfect for running alongside other services!

---

## Security Considerations

### Environment Variables

- Never commit `.env` to git (already in `.gitignore`)
- Keep Slack signing secret private
- Rotate API keys periodically

### Firewall

If exposing port 3000 directly:
```bash
# Only allow from Slack IPs (optional, advanced)
sudo ufw deny 3000
sudo ufw allow from SLACK_IP_RANGE to any port 3000
```

Or use reverse proxy (Caddy/nginx) for better security.

### SSL/TLS

Use HTTPS in production:
- Caddy: Automatic HTTPS
- nginx: Use certbot for Let's Encrypt

---

## Troubleshooting

### Container Keeps Restarting

```bash
# Check logs
docker-compose logs

# Common causes:
# - Missing .env file
# - Invalid credentials
# - Permission issues on data/ or logs/
```

### Fix Permissions

```bash
chmod 755 data logs
chmod 644 data/bluesky_bot.db
```

### Database Locked

```bash
# Stop all containers
docker-compose down

# Check for locks
lsof data/bluesky_bot.db

# Restart
docker-compose up -d
```

### Can't Connect to Slack

```bash
# Test health endpoint
curl http://localhost:3000/health

# Check if port is listening
netstat -tuln | grep 3000

# Check firewall
sudo ufw status

# Check Caddy/nginx logs
sudo journalctl -u caddy -f
sudo journalctl -u nginx -f
```

### High Memory Usage

Unlikely with this bot, but if it happens:
```bash
# Restart containers
docker-compose restart

# Check for database issues
sqlite3 data/bluesky_bot.db "VACUUM;"
```

---

## Complete Deployment Checklist

- [ ] Server with Docker installed
- [ ] Domain DNS configured (if using domain)
- [ ] Reverse proxy configured (if using HTTPS)
- [ ] Slack app created and configured
- [ ] `.env` file with all credentials
- [ ] Firewall ports opened (if needed)
- [ ] `docker-compose up -d` successful
- [ ] Both containers running: `docker ps`
- [ ] Health check passes: `curl http://localhost:3000/health`
- [ ] Slack webhook verified (interactive URL shows green checkmark)
- [ ] Test approval flow works
- [ ] Monitoring/logging verified
- [ ] Backup strategy in place

---

## Example: Complete Hetzner + Caddy Setup

```bash
# 1. DNS - Add A record
# bot.yourdomain.com → HETZNER_IP

# 2. SSH to server
ssh root@HETZNER_IP

# 3. Install dependencies (if needed)
sudo apt update
sudo apt install docker.io docker-compose caddy

# 4. Configure Caddy
sudo nano /etc/caddy/Caddyfile
# Add: bot.yourdomain.com { reverse_proxy localhost:3000 }
sudo systemctl reload caddy

# 5. Deploy bot
git clone <repo-url> /opt/bluesky-engagement-agent
cd /opt/bluesky-engagement-agent
cp .env.example .env
nano .env  # Add all credentials
docker-compose up -d

# 6. Verify
docker ps
curl https://bot.yourdomain.com/health

# 7. Test Slack interactive
# Wait for post, click button in Slack

# Done!
```

---

**Your bot is now running in production!**
