"""
Interactive Slack notifications with approval buttons
"""

import os
import json
import requests
from typing import Dict, Optional
from utils.logger import setup_logger

logger = setup_logger(__name__, 'logs/slack_interactive.log')


class SlackInteractive:
    """Handles interactive Slack notifications with approval buttons"""

    def __init__(self):
        self.webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        self.signing_secret = os.getenv('SLACK_SIGNING_SECRET')

        if not self.webhook_url:
            logger.warning("No SLACK_WEBHOOK_URL configured - Slack notifications disabled")

    def send_approval_request(self, approval_id: int, post_data: Dict, decision: Dict,
                             action: str, reply_text: str = None) -> Optional[str]:
        """
        Send interactive approval request to Slack with buttons

        Returns the message timestamp (ts) if successful
        """
        if not self.webhook_url:
            logger.warning("Cannot send Slack notification - no webhook URL configured")
            return None

        try:
            # Build the Slack Block Kit message
            blocks = self._build_approval_blocks(approval_id, post_data, decision, action, reply_text)

            payload = {
                "text": f"{'💬 REPLY' if action == 'reply' else '🔁 RESHARE'} REQUEST - Approval needed",
                "blocks": blocks
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Sent approval request #{approval_id} to Slack")
                # Note: Webhooks don't return message_ts, need to use chat.postMessage with bot token for that
                return "webhook_sent"
            else:
                logger.error(f"Failed to send Slack notification: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            return None

    def _build_approval_blocks(self, approval_id: int, post_data: Dict, decision: Dict,
                              action: str, reply_text: str = None) -> list:
        """Build Slack Block Kit blocks for approval request"""

        emoji = "💬" if action == "reply" else "🔁"
        action_name = "REPLY" if action == "reply" else "RESHARE"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {action_name} REQUEST - Approval #{approval_id}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Author:* @{post_data.get('author_handle', 'unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Sentiment:* {post_data.get('sentiment', 'unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Platform:* {post_data.get('platform', 'unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Score:* {decision.get('score', 'N/A')}/10"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Original Post:*\n> {post_data.get('text', '')[:500]}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": self._get_post_url(post_data)
                    }
                ]
            }
        ]

        # Add reply text if this is a reply action
        if action == "reply" and reply_text:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Proposed Reply:*\n```{reply_text}```"
                }
            })

        # Add Claude's reasoning
        reasoning = decision.get('reason', 'No reasoning provided')
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Claude's Reasoning:*\n_{reasoning}_"
            }
        })

        # Add action buttons
        blocks.append({
            "type": "actions",
            "block_id": f"approval_{approval_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Approve"
                    },
                    "style": "primary",
                    "value": f"approve_{approval_id}",
                    "action_id": "approve_action"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "❌ Reject"
                    },
                    "style": "danger",
                    "value": f"reject_{approval_id}",
                    "action_id": "reject_action"
                }
            ]
        })

        # Add post link if available
        if 'url' in post_data:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"<{post_data['url']}|View original post>"
                    }
                ]
            })

        return blocks

    def send_approval_result(self, approval_id: int, approved: bool, action: str):
        """Send notification that approval was processed"""
        if not self.webhook_url:
            return False

        try:
            emoji = "✅" if approved else "❌"
            status = "APPROVED" if approved else "REJECTED"
            action_name = "REPLY" if action == "reply" else "RESHARE"

            payload = {
                "text": f"{emoji} Approval #{approval_id} {status}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{emoji} *{action_name} {status}*\n\nApproval #{approval_id} has been {status.lower()}."
                        }
                    }
                ]
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )

            return response.status_code == 200

        except Exception as e:
            logger.error(f"Error sending approval result: {e}")
            return False

    def _get_post_url(self, post_data: Dict) -> str:
        """Generate a clickable URL to the original post"""
        platform = post_data.get('platform', '').lower()

        if platform == 'bluesky':
            # Bluesky post URL format: https://bsky.app/profile/handle/post/postid
            author_handle = post_data.get('author_handle', '')
            post_uri = post_data.get('uri', '')

            # Extract post ID from URI (format: at://did:plc:xxx/app.bsky.feed.post/xxx)
            if post_uri and '/app.bsky.feed.post/' in post_uri:
                post_id = post_uri.split('/app.bsky.feed.post/')[-1]
                return f"<https://bsky.app/profile/{author_handle}/post/{post_id}|View on Bluesky>"

        return "URL not available"

    def update_message_with_result(self, message_ts: str, approved: bool):
        """
        Update the original message to show it was approved/rejected
        Note: This functionality is not currently implemented.
        The slack_approval_server.py handles updating messages via response_url.
        """
        # Not needed - the server updates messages directly via Slack's response_url
        # This method is kept for potential future use
        # For now, we'll just send a new message
        pass
