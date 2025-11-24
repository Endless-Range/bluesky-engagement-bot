"""
Flask server to handle Slack interactive button clicks for approvals
"""

import os
import json
import hmac
import hashlib
import requests
from flask import Flask, request, jsonify
from utils.database import Database
from utils.logger import setup_logger

# Import platform-specific modules
from bluesky_monitor_v2 import BlueskyMonitor

app = Flask(__name__)
logger = setup_logger(__name__, 'logs/slack_approval_server.log')
db = Database()

# Initialize monitors (will be used to execute approved actions)
bluesky_monitor = None


def init_monitors():
    """Initialize platform monitors"""
    global bluesky_monitor
    try:
        from utils.config import load_config
        config = load_config()
        bluesky_monitor = BlueskyMonitor(config)
        logger.info("Initialized Bluesky monitor")
    except Exception as e:
        logger.error(f"Failed to initialize Bluesky monitor: {e}")


def verify_slack_signature(request_data: bytes, timestamp: str, signature: str) -> bool:
    """Verify that request came from Slack"""
    slack_signing_secret = os.getenv('SLACK_SIGNING_SECRET')
    if not slack_signing_secret:
        logger.warning("No SLACK_SIGNING_SECRET configured - skipping signature verification")
        return True  # Allow in dev mode

    # Create signature base string
    sig_basestring = f"v0:{timestamp}:{request_data.decode('utf-8')}"

    # Create HMAC SHA256 hash
    my_signature = 'v0=' + hmac.new(
        slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    # Debug logging
    logger.debug(f"Slack signature: {signature}")
    logger.debug(f"Our signature: {my_signature}")
    logger.debug(f"Timestamp: {timestamp}")

    # Compare signatures
    is_valid = hmac.compare_digest(my_signature, signature)
    if not is_valid:
        logger.warning(f"Signature mismatch! Expected starts with: {my_signature[:20]}...")
    return is_valid


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200


@app.route('/slack/interactive', methods=['POST'])
def slack_interactive():
    """Handle Slack interactive button clicks"""
    try:
        # Verify Slack signature
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        signature = request.headers.get('X-Slack-Signature', '')

        # Get raw body for signature verification
        # Slack sends form-encoded data, so we need to use get_data() to preserve the raw body
        request_body = request.get_data()

        if not verify_slack_signature(request_body, timestamp, signature):
            logger.warning("Invalid Slack signature")
            return jsonify({'error': 'Invalid signature'}), 403

        # Parse the payload (now safe to access form data)
        payload = json.loads(request.form.get('payload'))

        # Extract action information
        action = payload.get('actions', [{}])[0]
        action_id = action.get('action_id')
        action_value = action.get('value')

        logger.info(f"Received Slack action: {action_id} - {action_value}")

        # Extract approval ID from the value (format: "approve_123" or "reject_123")
        parts = action_value.split('_')
        if len(parts) != 2:
            return jsonify({'error': 'Invalid action value'}), 400

        action_type = parts[0]  # "approve" or "reject"
        approval_id = int(parts[1])

        # Get the pending approval from database
        approval = db.get_pending_approval(approval_id)
        if not approval:
            return jsonify({'error': 'Approval not found'}), 404

        if approval['status'] != 'pending':
            return jsonify({'text': f"This approval has already been {approval['status']}"}), 200

        # Process the approval
        if action_type == 'approve':
            success = process_approval(approval)
            if success:
                db.update_approval_status(approval_id, 'approved')
                response_text = "✅ APPROVED & POSTED"
            else:
                response_text = "❌ FAILED TO POST - Check logs for details"
        else:  # reject
            db.update_approval_status(approval_id, 'rejected')
            response_text = "❌ REJECTED - Will not be posted"

        # Get the message timestamp to reply in thread
        message_ts = payload.get('message', {}).get('ts')
        logger.info(f"Message ts: {message_ts}")
        logger.info(f"Response text: {response_text}")

        # Send threaded reply to show approval/rejection
        if message_ts:
            try:
                # Post as a threaded reply to the original approval message
                webhook_url = os.getenv('SLACK_WEBHOOK_URL')
                if webhook_url:
                    resp = requests.post(webhook_url, json={
                        'text': response_text,
                        'thread_ts': message_ts  # This makes it a threaded reply
                    }, timeout=5)
                    logger.info(f"Thread reply status: {resp.status_code}")
            except Exception as e:
                logger.error(f"Failed to send threaded reply: {e}", exc_info=True)

        # Return 200 OK to acknowledge the interaction
        return '', 200

    except Exception as e:
        logger.error(f"Error processing Slack interaction: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


def process_approval(approval: dict) -> bool:
    """Execute the approved action (reply or reshare)"""
    try:
        platform = approval['platform']
        action = approval['action']
        post_data = approval['post_data']
        post_id = approval['post_id']

        logger.info(f"Processing approval #{approval['id']}: {action} on {platform}")

        if platform == 'bluesky':
            if not bluesky_monitor:
                logger.error("Bluesky monitor not initialized")
                return False

            if action == 'reply':
                reply_text = approval['reply_text']
                success = bluesky_monitor.reply_to_post(post_id, post_data, reply_text)
                if success:
                    # Log the response to database for stats
                    author_handle = post_data.get('author_handle', 'unknown')
                    db.record_reply(post_id, platform, author_handle, reply_text, action)
                    logger.info(f"Successfully posted reply to {post_id}")
                    return True
                else:
                    logger.error(f"Failed to post reply to {post_id}")
                    return False

            elif action == 'reshare':
                success = bluesky_monitor.reshare_post(post_id, post_data)
                if success:
                    # Log the response to database for stats
                    author_handle = post_data.get('author_handle', 'unknown')
                    db.record_reply(post_id, platform, author_handle, None, action)
                    logger.info(f"Successfully reshared {post_id}")
                    return True
                else:
                    logger.error(f"Failed to reshare {post_id}")
                    return False

        logger.warning(f"Unknown platform or action: {platform} / {action}")
        return False

    except Exception as e:
        logger.error(f"Error executing approved action: {e}", exc_info=True)
        return False


if __name__ == '__main__':
    # Initialize monitors
    init_monitors()

    # Get port from environment or use default
    port = int(os.getenv('SLACK_SERVER_PORT', 3000))

    # Run Flask app
    logger.info(f"Starting Slack approval server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
