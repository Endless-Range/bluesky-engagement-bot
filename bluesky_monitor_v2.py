"""
Bluesky Monitor & Engagement Agent (Version 2)
Improved with logging, persistence, better error handling
"""

import argparse
import sys
import time
from datetime import datetime
from typing import List, Dict
from atproto import Client, models, client_utils

from utils.logger import setup_logger
from utils.base_monitor import BaseMonitor
from utils.config import load_config, validate_bluesky_config, validate_anthropic_config
from utils.retry import exponential_backoff

logger = setup_logger(__name__)


class BlueskyMonitor(BaseMonitor):
    """Bluesky monitoring and reply system"""

    def __init__(self, config: Dict):
        super().__init__('bluesky', config)
        self.setup_client()

    def setup_client(self):
        """Initialize Bluesky client"""
        logger.info("Initializing Bluesky client...")

        self.client = Client()

        try:
            # Login is super simple - just handle and app password
            self.client.login(
                self.config['bluesky_handle'],
                self.config['bluesky_app_password']
            )
            logger.info(f"Logged into Bluesky as @{self.config['bluesky_handle']}")

        except Exception as e:
            logger.error(f"Failed to login to Bluesky: {e}")
            logger.error("Make sure you:")
            logger.error("1. Created account at bsky.app")
            logger.error("2. Generated app password at bsky.app/settings/app-passwords")
            logger.error("3. Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD in .env")
            raise

    @exponential_backoff(max_retries=3, base_delay=5.0)
    def search_recent_posts(self) -> List[Dict]:
        """Search for recent posts from keywords"""

        results = []
        keywords = self.config.get('keywords', [])

        for keyword in keywords:
            try:
                logger.debug(f"Searching for: {keyword}")

                # Bluesky's search is simpler than Twitter's
                response = self.client.app.bsky.feed.search_posts(
                    params={'q': keyword, 'limit': 10}
                )

                if not response.posts:
                    continue

                for post in response.posts:
                    post_uri = post.uri
                    post_cid = post.cid

                    # Check if already in database
                    if self.db.has_seen_post(post_uri, 'bluesky'):
                        logger.debug(f"Already seen post {post_uri}")
                        continue

                    # Get post details
                    author = post.author
                    record = post.record

                    # Skip posts that are replies (only engage with root/top-level posts)
                    # This prevents butting into existing conversations
                    if hasattr(record, 'reply') and record.reply:
                        logger.debug(f"Skipping reply post from @{author.handle}")
                        continue

                    # Check post age
                    created_at = datetime.fromisoformat(record.created_at.replace('Z', '+00:00'))
                    post_age = datetime.now(created_at.tzinfo) - created_at
                    max_age_hours = self.config.get('max_post_age_hours', 3)

                    if post_age.total_seconds() > max_age_hours * 3600:
                        logger.debug(f"Post too old: {post_age}")
                        continue

                    # Check follower count - need to fetch full profile since search results
                    # don't include followers_count
                    min_followers = self.config.get('min_followers_to_reply', 5)
                    try:
                        profile = self.client.app.bsky.actor.get_profile({'actor': author.handle})
                        follower_count = getattr(profile, 'followers_count', 0) or 0
                    except Exception as e:
                        logger.debug(f"Could not fetch profile for @{author.handle}: {e}")
                        follower_count = 0  # Skip filter if profile fetch fails

                    if follower_count > 0 and follower_count < min_followers:
                        logger.debug(
                            f"Author @{author.handle} has too few followers "
                            f"({follower_count})"
                        )
                        continue

                    # Extract OG image URL from embed if present (for duplicate detection)
                    og_image_url = None
                    if hasattr(post, 'embed') and post.embed:
                        embed = post.embed
                        # Check for external embed (link cards)
                        if hasattr(embed, 'external') and embed.external:
                            if hasattr(embed.external, 'thumb') and embed.external.thumb:
                                og_image_url = embed.external.thumb
                        # Check for record with media embed (quote posts with links)
                        elif hasattr(embed, 'media') and embed.media:
                            if hasattr(embed.media, 'external') and embed.media.external:
                                if hasattr(embed.media.external, 'thumb'):
                                    og_image_url = embed.media.external.thumb

                    results.append({
                        'id': post_uri,  # Use URI as ID
                        'uri': post_uri,
                        'cid': post_cid,
                        'text': record.text,
                        'author_did': author.did,
                        'author_handle': author.handle,
                        'author_followers': follower_count,
                        'likes': post.like_count or 0,
                        'shares': post.repost_count or 0,
                        'created_at': created_at.isoformat(),  # Convert datetime to string for JSON
                        'og_image_url': og_image_url  # OG image for duplicate detection
                    })

                # Small delay between keyword searches
                time.sleep(1)

            except Exception as e:
                logger.error(f"Search error for '{keyword}': {e}", exc_info=True)
                continue

        logger.info(f"Found {len(results)} relevant posts")
        return results

    @exponential_backoff(max_retries=2, base_delay=3.0)
    def post_reply(self, post_id: str, reply_text: str, post_data: Dict) -> bool:
        """Post a reply to a post"""

        post_uri = post_data['uri']
        post_cid = post_data['cid']

        # Bluesky allows 300 chars
        if len(reply_text) > 300:
            logger.warning(f"Reply too long ({len(reply_text)} chars), truncating")
            reply_text = reply_text[:297] + "..."

        try:
            logger.debug(f"Posting reply to {post_uri}: {reply_text}")

            # Extract URL from reply text to make it clickable
            website_url = self.config.get('website_url', 'https://example.com')

            # Build rich text with clickable link
            if website_url in reply_text:
                # Split text around the URL
                parts = reply_text.split(website_url)
                text_builder = client_utils.TextBuilder()

                # Add text before URL
                if parts[0]:
                    text_builder.text(parts[0])

                # Add clickable link
                text_builder.link(website_url, website_url)

                # Add text after URL (if any)
                if len(parts) > 1 and parts[1]:
                    text_builder.text(parts[1])

                rich_text = text_builder
            else:
                # No URL in text, use plain text
                rich_text = reply_text

            # Create reply
            self.client.send_post(
                text=rich_text,
                reply_to=models.AppBskyFeedPost.ReplyRef(
                    parent=models.ComAtprotoRepoStrongRef.Main(
                        uri=post_uri,
                        cid=post_cid
                    ),
                    root=models.ComAtprotoRepoStrongRef.Main(
                        uri=post_uri,
                        cid=post_cid
                    )
                )
            )

            logger.info("Reply posted successfully")
            return True

        except Exception as e:
            logger.error(f"Reply failed: {e}", exc_info=True)
            return False

    @exponential_backoff(max_retries=2, base_delay=3.0)
    def reshare_post(self, post_id: str, post_data: Dict) -> bool:
        """Reshare/repost a post on Bluesky"""

        post_uri = post_data['uri']
        post_cid = post_data['cid']

        try:
            logger.debug(f"Resharing post {post_uri}")

            # Bluesky repost
            self.client.like(uri=post_uri, cid=post_cid)  # Like it
            self.client.repost(uri=post_uri, cid=post_cid)  # Repost it

            logger.info("Post reshared successfully")
            return True

        except Exception as e:
            logger.error(f"Reshare failed: {e}", exc_info=True)
            return False

    def reply_to_post(self, post_id: str, post_data: Dict, reply_text: str) -> bool:
        """
        Wrapper for post_reply that approval server can call
        Just calls the parent class post_reply method
        """
        return self.post_reply(post_id, reply_text, post_data)


def main():
    """Entry point"""

    parser = argparse.ArgumentParser(
        description='Bluesky Engagement Agent'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to JSON config file (optional)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Check interval in seconds (default: 300)'
    )
    parser.add_argument(
        '--manual',
        action='store_true',
        help='Enable manual approval mode'
    )
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Disable manual approval mode'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )

    args = parser.parse_args()

    # Setup logging with specified level
    import logging
    logger.setLevel(getattr(logging, args.log_level))

    logger.info("Bluesky Engagement Agent v2")

    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Validate required credentials
    if not validate_bluesky_config(config):
        logger.error("Invalid Bluesky configuration. Please check your .env file.")
        sys.exit(1)

    if not validate_anthropic_config(config):
        logger.error("Invalid Anthropic configuration. Please check your .env file.")
        sys.exit(1)

    # Override manual approval if specified
    if args.manual:
        config['manual_approval'] = True
    elif args.auto:
        config['manual_approval'] = False

    logger.info(f"Manual approval mode: {config['manual_approval']}")

    # Adjust rate limits for Bluesky (more relaxed)
    config['max_replies_per_hour'] = config.get('max_replies_per_hour', 20)
    config['max_replies_per_day'] = config.get('max_replies_per_day', 150)
    config['min_seconds_between_replies'] = config.get('min_seconds_between_replies', 120)
    config['max_reply_chars'] = config.get('max_reply_chars_bluesky', 300)

    # Print banner
    keywords_list = config.get('keywords', [])
    keywords_display = ', '.join(keywords_list) if keywords_list else 'None configured'

    print(f"""
╔════════════════════════════════════════════════════════╗
║  🦋 BLUESKY ENGAGEMENT AGENT v2 🦋            ║
╠════════════════════════════════════════════════════════╣
║  Account: @{config['bluesky_handle']:<44} ║
║  Keywords: {keywords_display:<48} ║
║  Check interval: {args.interval}s                                  ║
║  Max replies/hour: {config['max_replies_per_hour']}                             ║
║  Manual approval: {str(config['manual_approval']):<5}                           ║
╚════════════════════════════════════════════════════════╝
    """)

    # Start monitoring
    try:
        monitor = BlueskyMonitor(config)
        monitor.run_monitoring_loop(interval_seconds=args.interval)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
