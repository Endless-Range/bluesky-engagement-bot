"""
Base classes for social media monitors
"""

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import anthropic

from .logger import setup_logger
from .database import Database
from .retry import exponential_backoff, is_rate_limit_error
from .slack_notifications import SlackNotifier
from .slack_interactive import SlackInteractive


class RateLimiter:
    """
    Tracks reply rate with database persistence
    """

    def __init__(self, database: Database, platform: str,
                 max_per_hour: int, max_per_day: int, min_seconds_between: int):
        self.db = database
        self.platform = platform
        self.max_per_hour = max_per_hour
        self.max_per_day = max_per_day
        self.min_seconds_between = min_seconds_between
        self.last_reply_time = None
        self.logger = setup_logger(f"{__name__}.RateLimiter")

    def can_reply(self) -> bool:
        """Check if we can send a reply now"""
        now = datetime.now()

        # Get recent replies from database
        hourly_count = self.db.get_reply_count(self.platform, hours=1)
        daily_count = self.db.get_reply_count(self.platform, hours=24)

        # Check hourly limit
        if hourly_count >= self.max_per_hour:
            self.logger.warning(
                f"Hourly limit reached: {hourly_count}/{self.max_per_hour}"
            )
            return False

        # Check daily limit
        if daily_count >= self.max_per_day:
            self.logger.warning(
                f"Daily limit reached: {daily_count}/{self.max_per_day}"
            )
            return False

        # Check minimum time between replies
        recent_timestamps = self.db.get_reply_timestamps(self.platform, hours=1)
        if recent_timestamps:
            last_reply = recent_timestamps[0]
            seconds_since_last = (now - last_reply).total_seconds()
            if seconds_since_last < self.min_seconds_between:
                self.logger.debug(
                    f"Too soon since last reply: {seconds_since_last:.0f}s < {self.min_seconds_between}s"
                )
                return False

        return True

    def record_reply(self):
        """Record that we sent a reply (handled by database)"""
        self.last_reply_time = datetime.now()

    def get_stats(self) -> Dict:
        """Get current rate limiting stats"""
        return {
            "replies_last_hour": self.db.get_reply_count(self.platform, hours=1),
            "replies_today": self.db.get_reply_count(self.platform, hours=24),
            "can_reply_now": self.can_reply()
        }


class ClaudeDecisionEngine:
    """
    Uses Claude to analyze posts and generate responses
    """

    def __init__(self, api_key: str, bot_username: str, website_url: str, bluesky_handle: str = None, model: str = None):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.bot_username = bot_username
        self.website_url = website_url
        self.bluesky_handle = bluesky_handle
        # Use the latest stable Claude model
        self.model = model or "claude-sonnet-4-20250514"
        self.logger = setup_logger(f"{__name__}.ClaudeDecisionEngine")

    @exponential_backoff(
        max_retries=3,
        base_delay=2.0,
        exceptions=(anthropic.APIError, anthropic.APIConnectionError)
    )
    def decide_engagement(self, post_data: Dict) -> Dict:
        """
        Stage 1: Decides if we should engage with this post at all
        Returns: {"should_engage": bool, "reason": str, "sentiment": str}
        """

        prompt = f"""You are analyzing a social media post to decide if an engagement account (@{self.bot_username}) should engage with it AT ALL.

POST CONTENT:
Author: @{post_data['author_handle']} ({post_data['author_followers']} followers)
Text: {post_data['text']}
Likes: {post_data.get('likes', 0)} | Shares: {post_data.get('shares', 0)}

MISSION: Engage with relevant posts based on configured keywords and sentiment.

ENGAGE when the post is:
- About topics relevant to our keywords
- From a real person (not spam, not bot)
- Expressing genuine interest, concern, or sharing information
- In English
- NOT from @{self.bluesky_handle} (that's us!)

IGNORE when:
- Trolls or inflammatory posts
- Spam or low-quality content
- Not in English
- From @{self.bluesky_handle} (our own posts)
- Off-topic (not relevant to our keywords)

Respond with a JSON object:
{{
  "should_engage": true or false,
  "sentiment": "positive" or "negative" or "neutral" or "unclear" or "news" or "advocacy",
  "reason": "brief explanation"
}}

DO NOT OUTPUT ANYTHING OTHER THAN VALID JSON."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text.strip()
            # Strip markdown if present
            result_text = result_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(result_text)

            self.logger.debug(
                f"Stage 1 decision for @{post_data['author_handle']}: "
                f"should_engage={result.get('should_engage')}, sentiment={result.get('sentiment')}"
            )

            return result

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse Claude Stage 1 response as JSON: {e}")
            return {"should_engage": False, "reason": "parse_error", "sentiment": "error"}
        except Exception as e:
            self.logger.error(f"Claude Stage 1 decision error: {e}")
            return {"should_engage": False, "reason": "error", "sentiment": "error"}

    @exponential_backoff(
        max_retries=3,
        base_delay=2.0,
        exceptions=(anthropic.APIError, anthropic.APIConnectionError)
    )
    def decide_engagement_type(self, post_data: Dict, sentiment: str) -> Dict:
        """
        Stage 2: Decides HOW to engage (reply with CTA, reply casual, or reshare)
        Only called if Stage 1 determined we should engage
        Returns: {"action": str, "reason": str, "engagement_score": int}
        """

        prompt = f"""You are deciding HOW to engage with a social media post. We've already decided to engage - now determine the BEST way.

POST CONTENT:
Author: @{post_data['author_handle']} ({post_data['author_followers']} followers)
Text: {post_data['text']}
Likes: {post_data.get('likes', 0)} | Shares: {post_data.get('shares', 0)}
Sentiment: {sentiment}

MISSION: Engage with relevant posts based on configured keywords and sentiment.

YOUR OPTIONS:

1. RESHARE - Amplify this content by resharing/reposting it
   Choose this when:
   - Positive news or updates related to our topics
   - People already sharing {self.website_url} or similar resources
   - Quality educational content
   - Influential voices speaking out
   - Good statistics/facts that support the cause

2. REPLY_CASUAL - Engage conversationally without a call-to-action
   Choose this when:
   - Author is ALREADY engaged (explicitly mentions taking action, organizing)
   - Influential account with high follower count (hard sell would be inappropriate)
   - Another advocacy account or activist (they already know what to do)
   - Author seems very engaged but a hard CTA would feel pushy or redundant

3. REPLY_WITH_CTA - Reply with a call-to-action
   Choose this when:
   - Author expresses concern or interest
   - Real person expressing genuine interest
   - Would likely take action if asked
   - NOT already engaged or taking action
   - Could benefit from knowing about our resources
   - Receptive to being asked to help

IMPORTANT: Default to REPLY_WITH_CTA for interested people who haven't mentioned taking action yet. Only use REPLY_CASUAL if they've explicitly shown they're already engaged or if they're influential/advocacy accounts.

Respond with a JSON object:
{{
  "action": "reshare" or "reply_casual" or "reply_with_cta",
  "reason": "brief explanation of why this is the best approach",
  "engagement_score": 1-10
}}

DO NOT OUTPUT ANYTHING OTHER THAN VALID JSON."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text.strip()
            # Strip markdown if present
            result_text = result_text.replace('```json', '').replace('```', '').strip()
            result = json.loads(result_text)

            action = result.get('action', 'reply_with_cta')
            self.logger.debug(
                f"Stage 2 decision for @{post_data['author_handle']}: "
                f"action={action}, score={result.get('engagement_score')}"
            )

            return result

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse Claude Stage 2 response as JSON: {e}")
            return {"action": "reply_with_cta", "reason": "parse_error", "engagement_score": 5}
        except Exception as e:
            self.logger.error(f"Claude Stage 2 decision error: {e}")
            return {"action": "reply_with_cta", "reason": "error", "engagement_score": 5}

    @exponential_backoff(
        max_retries=3,
        base_delay=2.0,
        exceptions=(anthropic.APIError, anthropic.APIConnectionError)
    )
    def should_respond(self, post_data: Dict) -> Dict:
        """
        Two-stage decision process:
        Stage 1: Should we engage at all?
        Stage 2: If yes, how should we engage?

        Returns: {"should_respond": bool, "action": str, "reason": str, "sentiment": str, "engagement_score": int}
        """

        # Stage 1: Should we engage at all?
        self.logger.debug(f"Stage 1: Checking if we should engage with @{post_data['author_handle']}")
        stage1_result = self.decide_engagement(post_data)

        should_engage = stage1_result.get('should_engage', False)
        sentiment = stage1_result.get('sentiment', 'unknown')
        stage1_reason = stage1_result.get('reason', '')

        if not should_engage:
            # Don't engage - return ignore action
            self.logger.info(
                f"Stage 1: IGNORE - sentiment={sentiment}, reason={stage1_reason}"
            )
            return {
                "should_respond": False,
                "action": "ignore",
                "sentiment": sentiment,
                "reason": stage1_reason,
                "engagement_score": 0
            }

        # Stage 2: How should we engage?
        self.logger.debug(f"Stage 2: Deciding how to engage with @{post_data['author_handle']}")
        stage2_result = self.decide_engagement_type(post_data, sentiment)

        action = stage2_result.get('action', 'reply_with_cta')
        stage2_reason = stage2_result.get('reason', '')
        engagement_score = stage2_result.get('engagement_score', 5)

        # Combine reasons from both stages
        combined_reason = f"Stage1: {stage1_reason} | Stage2: {stage2_reason}"

        self.logger.info(
            f"Decision: action={action}, sentiment={sentiment}, score={engagement_score}"
        )

        return {
            "should_respond": True,
            "action": action,
            "sentiment": sentiment,
            "reason": combined_reason,
            "engagement_score": engagement_score
        }

    @exponential_backoff(
        max_retries=3,
        base_delay=2.0,
        exceptions=(anthropic.APIError, anthropic.APIConnectionError)
    )
    def generate_response(self, post_data: Dict, action_type: str = 'reply_with_cta', max_chars: int = 280) -> str:
        """
        Generates a personalized reply for the post based on action type

        Args:
            post_data: Dictionary containing post information
            action_type: Either 'reply_with_cta' or 'reply_casual'
            max_chars: Maximum character limit for the reply
        """

        if action_type == 'reply_casual':
            # Casual engagement - no CTA, no URL
            prompt = f"""You are @{self.bot_username}, a social engagement account.

THEIR POST:
@{post_data['author_handle']}: {post_data['text']}

TASK: Write a SHORT, authentic reply (max {max_chars} chars) that:
1. Engages with their point conversationally
2. Shows support and solidarity
3. Acknowledges their concern or perspective
4. NO call-to-action, NO links (they'll see info in your bio)

TONE:
- Friendly, genuine, person-to-person
- Supportive and empathetic
- Natural conversation, not promotional
- Minimal hashtags/emojis unless they used them

EXAMPLES:
"Totally agree - this is such an important topic that needs more attention."

"You're spot on about this. So many people are affected."

"Really appreciate you speaking up about this. The more voices the better."

"Exactly. The timing couldn't be more critical."

Write ONLY the reply text, nothing else."""
        else:
            # Reply with CTA - include website URL and ask them to take action
            prompt = f"""You are @{self.bot_username}, a social engagement account.

THEIR POST:
@{post_data['author_handle']}: {post_data['text']}

TASK: Write a SHORT, authentic reply (max {max_chars} chars) that:
1. Acknowledges their concern empathetically
2. Empowers them to take action
3. Mentions our resource/tool
4. Includes this link: {self.website_url}

TONE:
- Friendly, not corporate
- Urgent but hopeful
- Person-to-person, not brand-to-consumer
- Minimal hashtags/emojis unless they used them

EXAMPLES:
"I hear you. The good news? You can actually do something about it. Check out: {self.website_url}"

"Same here. That's why I built this tool - makes it super easy to get involved: {self.website_url}"

"You're right to be concerned. Here's how you can help: {self.website_url}"

Write ONLY the reply text, nothing else."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            reply = response.content[0].text.strip()

            # Ensure it's not too long
            if len(reply) > max_chars:
                reply = reply[:max_chars - 3] + "..."

            self.logger.debug(f"Generated response ({len(reply)} chars): {reply[:50]}...")

            return reply

        except Exception as e:
            self.logger.error(f"Claude generation error: {e}")
            # Fallback generic message based on action type
            if action_type == 'reply_casual':
                return "This is such an important topic. Thanks for speaking up about it."
            else:
                return f"You can help make a difference. Check out: {self.website_url}"


class BaseMonitor(ABC):
    """
    Abstract base class for social media monitoring bots
    """

    def __init__(self, platform: str, config: Dict):
        self.platform = platform
        self.config = config
        self.logger = setup_logger(f"{__name__}.{platform}Monitor")
        self.db = Database()
        self.claude = ClaudeDecisionEngine(
            api_key=config['anthropic_api_key'],
            bot_username=config.get('bot_username', 'BlueSkyBot'),
            website_url=config.get('website_url', 'https://example.com'),
            bluesky_handle=config.get('bluesky_handle'),
            model=config.get('claude_model')
        )
        self.rate_limiter = RateLimiter(
            database=self.db,
            platform=platform,
            max_per_hour=config.get('max_replies_per_hour', 15),
            max_per_day=config.get('max_replies_per_day', 100),
            min_seconds_between=config.get('min_seconds_between_replies', 180)
        )
        self.manual_approval = config.get('manual_approval', True)
        self.slack_interactive_mode = config.get('slack_interactive_mode', False)
        self.slack = SlackNotifier()  # Initialize Slack notifier
        self.slack_interactive = SlackInteractive()  # Initialize interactive Slack

    @abstractmethod
    def setup_client(self):
        """Initialize platform-specific API client"""
        pass

    @abstractmethod
    def search_recent_posts(self) -> List[Dict]:
        """Search for recent posts matching keywords"""
        pass

    @abstractmethod
    def post_reply(self, post_id: str, reply_text: str, post_data: Dict) -> bool:
        """Post a reply to a post"""
        pass

    @abstractmethod
    def reshare_post(self, post_id: str, post_data: Dict) -> bool:
        """Reshare/repost a post"""
        pass

    def process_post(self, post_data: Dict):
        """Analyze and potentially reply to a post"""

        post_id = str(post_data['id'])
        author = post_data['author_handle']

        self.logger.info(f"Analyzing post from @{author}")
        self.logger.debug(f"Text: {post_data['text'][:100]}...")

        # Check if already seen
        if self.db.has_seen_post(post_id, self.platform):
            self.logger.debug(f"Already seen post {post_id}")
            return

        # Mark as seen
        self.db.mark_post_seen(post_id, self.platform, author, responded=False)

        # Check rate limits
        if not self.rate_limiter.can_reply():
            self.logger.warning("Rate limited - skipping")
            return

        # Ask Claude
        decision = self.claude.should_respond(post_data)
        action = decision.get('action', 'ignore')

        self.logger.info(
            f"Decision: action={action}, "
            f"sentiment={decision.get('sentiment')}, reason={decision.get('reason')}"
        )

        if action == 'ignore':
            # Send ignored posts to Slack as FYI
            post_data['platform'] = self.platform
            post_data['sentiment'] = decision.get('sentiment', 'unknown')
            self.slack.send_ignored_post(post_data, decision)
            self.logger.info("Post ignored - sent FYI to Slack")
            return

        # Handle RESHARE
        if action == 'reshare':
            self.logger.info("Claude recommends resharing this post")

            # Add platform to post_data
            post_data['platform'] = self.platform

            # Slack Interactive Mode
            if self.slack_interactive_mode:
                # Create pending approval in database
                approval_id = self.db.create_pending_approval(
                    post_id=post_id,
                    platform=self.platform,
                    action='reshare',
                    post_data=post_data,
                    decision_data=decision
                )

                # Send interactive Slack message with buttons
                self.slack_interactive.send_approval_request(
                    approval_id, post_data, decision, action='reshare'
                )

                self.logger.info(f"Sent interactive approval request #{approval_id} to Slack")
                return  # Don't post yet - wait for button click

            # Terminal Manual Approval Mode
            elif self.manual_approval:
                # Send regular Slack notification
                self.slack.send_approval_request(post_data, decision, action='reshare')

                self.logger.info("Manual approval required")
                print(f"\n🔁 RESHARE APPROVAL REQUIRED")
                print(f"Post from @{author}: {post_data['text'][:200]}...")
                print(f"Reason: {decision.get('reason', 'N/A')}")

                approval = input("\nReshare this post? (y/n): ").strip().lower()

                if approval != 'y':
                    self.logger.info("Reshare skipped by user")
                    return
            else:
                # Auto mode - send notification only
                self.slack.send_approval_request(post_data, decision, action='reshare')

            # Post reshare
            success = self.reshare_post(post_id, post_data)

            if success:
                self.logger.info("Post reshared successfully")
                self.db.record_reply(
                    post_id,
                    self.platform,
                    author,
                    decision.get('sentiment', 'unknown'),
                    "[RESHARED]"
                )
            else:
                self.logger.error("Reshare failed")

            return

        # Handle REPLY (both types: reply_with_cta and reply_casual)
        if action in ['reply_with_cta', 'reply_casual']:
            # Generate response with appropriate style
            self.logger.info(f"Generating {action} response...")
            max_chars = self.config.get('max_reply_chars', 280)
            reply_text = self.claude.generate_response(post_data, action_type=action, max_chars=max_chars)

            self.logger.info(f"Generated {action} reply: {reply_text}")

            # Add platform to post_data
            post_data['platform'] = self.platform

            # Slack Interactive Mode
            if self.slack_interactive_mode:
                # Create pending approval in database
                approval_id = self.db.create_pending_approval(
                    post_id=post_id,
                    platform=self.platform,
                    action=action,  # Store specific action type (reply_with_cta or reply_casual)
                    post_data=post_data,
                    decision_data=decision,
                    reply_text=reply_text
                )

                # Send interactive Slack message with buttons
                self.slack_interactive.send_approval_request(
                    approval_id, post_data, decision, action=action, reply_text=reply_text
                )

                self.logger.info(f"Sent interactive approval request #{approval_id} to Slack")
                return  # Don't post yet - wait for button click

            # Terminal Manual Approval Mode
            elif self.manual_approval:
                # Send regular Slack notification
                self.slack.send_approval_request(post_data, decision, action=action, reply_text=reply_text)

                self.logger.info("Manual approval required")
                action_emoji = "💬" if action == "reply_with_cta" else "💭"
                action_label = "CTA" if action == "reply_with_cta" else "CASUAL"
                print(f"\n{action_emoji} REPLY APPROVAL REQUIRED ({action_label})")
                print(f"Post from @{author}: {post_data['text'][:100]}...")
                print(f"Proposed reply: {reply_text}")

                approval = input("\nPost this reply? (y/n/e=edit): ").strip().lower()

                if approval == 'e':
                    reply_text = input("Enter new reply: ").strip()
                    approval = 'y'

                if approval != 'y':
                    self.logger.info("Reply skipped by user")
                    return
            else:
                # Auto mode - send notification only
                self.slack.send_approval_request(post_data, decision, action=action, reply_text=reply_text)

            # Post reply
            success = self.post_reply(post_id, reply_text, post_data)

            if success:
                self.logger.info("Reply posted successfully")
                self.db.record_reply(
                    post_id,
                    self.platform,
                    author,
                    decision.get('sentiment', 'unknown'),
                    reply_text
                )
            else:
                self.logger.error("Reply failed")

    def run_monitoring_loop(self, interval_seconds: int = 300):
        """Main monitoring loop"""

        self.logger.info(f"Starting {self.platform} monitor")
        self.logger.info(f"Check interval: {interval_seconds}s")
        self.logger.info(f"Keywords: {len(self.config.get('keywords', []))}")

        stats = self.db.get_stats(self.platform)
        self.logger.info(
            f"Stats: {stats['total_seen']} seen, {stats['total_responses']} responses"
        )

        while True:
            try:
                self.logger.info(f"Searching for posts... ({datetime.now().strftime('%H:%M:%S')})")

                # Get rate limiter stats
                rate_stats = self.rate_limiter.get_stats()
                self.logger.info(
                    f"Rate limits: {rate_stats['replies_last_hour']}/hr, "
                    f"{rate_stats['replies_today']}/day"
                )

                # Search for posts
                posts = self.search_recent_posts()
                self.logger.info(f"Found {len(posts)} new posts to analyze")

                # Process each post
                for post in posts:
                    try:
                        self.process_post(post)
                        time.sleep(2)  # Small delay between processing
                    except Exception as e:
                        self.logger.error(f"Error processing post: {e}", exc_info=True)
                        continue

                # Wait before next check
                self.logger.info(f"Next check in {interval_seconds} seconds...")
                time.sleep(interval_seconds)

            except KeyboardInterrupt:
                self.logger.info("Monitoring stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                self.logger.info("Retrying in 60 seconds...")
                time.sleep(60)
