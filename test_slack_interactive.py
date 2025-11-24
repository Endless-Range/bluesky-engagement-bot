#!/usr/bin/env python3
"""
Test script for Slack interactive approvals

This helps you test the interactive Slack setup before deploying.
"""

import os
import sys
from dotenv import load_dotenv
from utils.database import Database
from utils.slack_interactive import SlackInteractive

def test_database_tables():
    """Test that pending_approvals table exists"""
    print("\n1. Testing database schema...")

    try:
        db = Database()

        # Try to query pending approvals table
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_approvals'")
            result = cursor.fetchone()

            if result:
                print("   ✅ pending_approvals table exists")
            else:
                print("   ❌ pending_approvals table NOT found")
                return False

        return True

    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False


def test_slack_config():
    """Test that Slack environment variables are set"""
    print("\n2. Testing Slack configuration...")

    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    signing_secret = os.getenv('SLACK_SIGNING_SECRET')
    interactive_mode = os.getenv('SLACK_INTERACTIVE_MODE', 'false')

    if not webhook_url:
        print("   ❌ SLACK_WEBHOOK_URL not set in .env")
        return False
    else:
        print(f"   ✅ SLACK_WEBHOOK_URL set")

    if not signing_secret:
        print("   ⚠️  SLACK_SIGNING_SECRET not set (required for interactive mode)")
        print("      Get this from: https://api.slack.com/apps → Your App → Basic Information")
    else:
        print(f"   ✅ SLACK_SIGNING_SECRET set")

    print(f"   ℹ️  SLACK_INTERACTIVE_MODE = {interactive_mode}")

    return True


def test_create_approval():
    """Test creating a pending approval"""
    print("\n3. Testing pending approval creation...")

    try:
        db = Database()

        # Create test approval
        test_post_data = {
            'id': 'test_post_123',
            'text': 'This is a test post about the hemp ban',
            'author': 'test_user',
            'platform': 'bluesky',
            'sentiment': 'against_ban'
        }

        test_decision = {
            'action': 'reply',
            'sentiment': 'against_ban',
            'score': 8,
            'reasoning': 'Test approval - real person expressing concern'
        }

        approval_id = db.create_pending_approval(
            post_id='test_post_123',
            platform='bluesky',
            action='reply',
            post_data=test_post_data,
            decision_data=test_decision,
            reply_text='Test reply: You can help fight this at https://standforhemp.com'
        )

        print(f"   ✅ Created test approval #{approval_id}")

        # Retrieve it
        approval = db.get_pending_approval(approval_id)
        if approval:
            print(f"   ✅ Retrieved approval #{approval_id}")
            print(f"      Status: {approval['status']}")
            print(f"      Action: {approval['action']}")
        else:
            print(f"   ❌ Could not retrieve approval #{approval_id}")
            return False

        # Clean up
        db.update_approval_status(approval_id, 'test_completed')
        print(f"   ✅ Updated status to 'test_completed'")

        return True

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_send_slack_message():
    """Test sending interactive Slack message"""
    print("\n4. Testing Slack message send...")

    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url:
        print("   ⚠️  Skipping - SLACK_WEBHOOK_URL not set")
        return True

    try:
        slack = SlackInteractive()

        test_post_data = {
            'id': 'test_post_456',
            'text': 'Another test post about hemp industry regulations',
            'author': 'test_farmer',
            'platform': 'bluesky',
            'sentiment': 'against_ban',
            'url': 'https://bsky.app/profile/test'
        }

        test_decision = {
            'action': 'reply',
            'sentiment': 'against_ban',
            'score': 9,
            'reasoning': 'TEST MESSAGE - This is a test of the interactive approval system'
        }

        test_reply = 'TEST REPLY - You can help fight this: https://standforhemp.com'

        # Create test approval in database first
        db = Database()
        approval_id = db.create_pending_approval(
            post_id='test_post_456',
            platform='bluesky',
            action='reply',
            post_data=test_post_data,
            decision_data=test_decision,
            reply_text=test_reply
        )

        # Send to Slack
        result = slack.send_approval_request(
            approval_id=approval_id,
            post_data=test_post_data,
            decision=test_decision,
            action='reply',
            reply_text=test_reply
        )

        if result:
            print(f"   ✅ Test message sent to Slack!")
            print(f"   ℹ️  Check your Slack channel for approval #{approval_id}")
            print(f"   ℹ️  NOTE: Buttons won't work until you complete full Slack app setup")

            # Clean up test approval
            db.update_approval_status(approval_id, 'test_sent')
        else:
            print(f"   ❌ Failed to send message")
            return False

        return True

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("Slack Interactive Approvals - Test Suite")
    print("=" * 60)

    # Load environment
    load_dotenv()

    results = []

    # Run tests
    results.append(("Database Schema", test_database_tables()))
    results.append(("Slack Config", test_slack_config()))
    results.append(("Create Approval", test_create_approval()))
    results.append(("Send Slack Message", test_send_slack_message()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10} {test_name}")

    all_passed = all(result[1] for result in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed!")
        print("\nNext steps:")
        print("1. Complete Slack app setup: See SETUP.md")
        print("2. Set up ngrok or public URL")
        print("3. Add SLACK_SIGNING_SECRET to .env")
        print("4. Set SLACK_INTERACTIVE_MODE=true in .env")
        print("5. Deploy: docker-compose up -d")
    else:
        print("❌ Some tests failed - see errors above")
        print("\nCheck:")
        print("- .env file has required variables")
        print("- Database is accessible")
        print("- Slack webhook URL is correct")
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
