"""
Slack notifications for Stand for Hemp bot
Sends notifications when posts need approval
"""

import os
import requests
import json
from typing import Dict, Optional
from datetime import datetime


class SlackNotifier:
    """Send notifications to Slack"""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')

    def send_notification(self, message: str, title: str = None) -> bool:
        """Send a simple text notification"""
        if not self.webhook_url:
            return False

        payload = {
            "text": title or "Stand for Hemp Bot",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": message
                    }
                }
            ]
        }

        try:
            response = requests.post(self.webhook_url, json=payload)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
            return False

    def send_approval_request(self, post_data: Dict, decision: Dict, action: str, reply_text: str = None) -> bool:
        """Send a rich notification for approval requests"""
        if not self.webhook_url:
            return False

        author = post_data['author_handle']
        post_text = post_data['text'][:500]  # Truncate long posts
        sentiment = decision.get('sentiment', 'unknown')
        reason = decision.get('reason', 'N/A')

        # Build the message based on action type
        if action == 'reshare':
            action_emoji = "🔁"
            action_text = f"*RESHARE REQUEST*\n\n"
            action_details = f"Claude recommends resharing this post"
        else:  # reply
            action_emoji = "💬"
            action_text = f"*REPLY REQUEST*\n\n"
            action_details = f"*Proposed Reply:*\n```{reply_text}```"

        message = {
            "text": f"{action_emoji} Approval Needed - @{author}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{action_emoji} Approval Request",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": action_text
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Author:*\n@{author}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Sentiment:*\n{sentiment}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Platform:*\n{post_data.get('platform', 'bluesky')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Score:*\n{decision.get('engagement_score', 'N/A')}/10"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Original Post:*\n>{post_text}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": action_details
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Claude's Reasoning:*\n_{reason}_"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Queued at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Review this post in your dashboard: http://localhost:5000/pending"
                    }
                }
            ]
        }

        try:
            response = requests.post(self.webhook_url, json=message)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
            return False

    def send_ignored_post(self, post_data: Dict, decision: Dict) -> bool:
        """Send notification for ignored posts (FYI only, no approval needed)"""
        if not self.webhook_url:
            return False

        author = post_data['author_handle']
        post_text = post_data['text'][:500]  # Truncate long posts
        sentiment = decision.get('sentiment', 'unknown')
        reason = decision.get('reason', 'N/A')
        engagement_score = decision.get('engagement_score', 'N/A')

        # Get Bluesky post URL
        post_url = self._get_bluesky_url(post_data)

        message = {
            "text": f"⏭️ Post Ignored - @{author}",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⏭️ POST IGNORED - FYI",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Author:*\n@{author}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Sentiment:*\n{sentiment}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Platform:*\n{post_data.get('platform', 'bluesky')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Score:*\n{engagement_score}/10"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Original Post:*\n>{post_text}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Why Ignored:*\n_{reason}_"
                    }
                }
            ]
        }

        # Add post link if available
        if post_url:
            message["blocks"].append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{post_url}|View on Bluesky> • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            })

        try:
            response = requests.post(self.webhook_url, json=message)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
            return False

    def _get_bluesky_url(self, post_data: Dict) -> Optional[str]:
        """Generate URL to Bluesky post"""
        platform = post_data.get('platform', '').lower()

        if platform == 'bluesky':
            author_handle = post_data.get('author_handle', '')
            post_uri = post_data.get('uri', '')

            # Extract post ID from URI (format: at://did:plc:xxx/app.bsky.feed.post/xxx)
            if post_uri and '/app.bsky.feed.post/' in post_uri:
                post_id = post_uri.split('/app.bsky.feed.post/')[-1]
                return f"https://bsky.app/profile/{author_handle}/post/{post_id}"

        return None

    def send_summary(self, posts_found: int, posts_analyzed: int, replies_sent: int, reshares: int) -> bool:
        """Send a summary notification"""
        if not self.webhook_url:
            return False

        message = {
            "text": "🌿 Stand for Hemp - Activity Summary",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "🌿 Bot Activity Summary",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Posts Found:*\n{posts_found}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Analyzed:*\n{posts_analyzed}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Replies Sent:*\n{replies_sent}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Reshares:*\n{reshares}"
                        }
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        }
                    ]
                }
            ]
        }

        try:
            response = requests.post(self.webhook_url, json=message)
            return response.status_code == 200
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
            return False


def test_slack_notification():
    """Test function to verify Slack webhook works"""
    notifier = SlackNotifier()

    if not notifier.webhook_url:
        print("❌ No SLACK_WEBHOOK_URL configured in .env")
        print("\nTo set up:")
        print("1. Go to https://api.slack.com/messaging/webhooks")
        print("2. Create an Incoming Webhook for your workspace")
        print("3. Add SLACK_WEBHOOK_URL=your_webhook_url to .env")
        return False

    print("Sending test notification...")
    success = notifier.send_notification(
        message="✅ Slack notifications are working! You'll receive approval requests here.",
        title="🌿 Stand for Hemp Bot - Test Notification"
    )

    if success:
        print("✅ Test notification sent successfully!")
        return True
    else:
        print("❌ Failed to send notification. Check your webhook URL.")
        return False


if __name__ == "__main__":
    test_slack_notification()
