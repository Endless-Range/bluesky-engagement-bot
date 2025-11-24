"""
SQLite database for persistent storage of seen posts and rate limiting data
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from contextlib import contextmanager

class Database:
    """Manages persistent storage for bot state"""

    def __init__(self, db_path: str = "data/bluesky_bot.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_database(self):
        """Create tables if they don't exist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Seen posts/tweets table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS seen_posts (
                    post_id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    author_handle TEXT,
                    seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    responded BOOLEAN DEFAULT 0
                )
            ''')

            # Rate limiting table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rate_limits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL,
                    reply_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Response log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS response_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    author_handle TEXT,
                    sentiment TEXT,
                    response_text TEXT,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (post_id) REFERENCES seen_posts(post_id)
                )
            ''')

            # Pending approvals table for Slack interactive approvals
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    action TEXT NOT NULL,
                    post_data TEXT NOT NULL,
                    decision_data TEXT NOT NULL,
                    reply_text TEXT,
                    slack_message_ts TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    responded_at TIMESTAMP
                )
            ''')

            # Create indices for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_seen_posts_platform
                ON seen_posts(platform, seen_at)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_rate_limits_platform_time
                ON rate_limits(platform, reply_time)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_pending_approvals_status
                ON pending_approvals(status, created_at)
            ''')

    def has_seen_post(self, post_id: str, platform: str) -> bool:
        """Check if we've already seen this post"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT 1 FROM seen_posts WHERE post_id = ? AND platform = ?',
                (post_id, platform)
            )
            return cursor.fetchone() is not None

    def mark_post_seen(self, post_id: str, platform: str, author_handle: str, responded: bool = False):
        """Mark a post as seen"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO seen_posts (post_id, platform, author_handle, responded, seen_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (post_id, platform, author_handle, responded))

    def record_reply(self, post_id: str, platform: str, author_handle: str,
                     sentiment: str, response_text: str):
        """Record a reply in the database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Update seen_posts to mark as responded
            cursor.execute('''
                UPDATE seen_posts
                SET responded = 1
                WHERE post_id = ? AND platform = ?
            ''', (post_id, platform))

            # Log the response
            cursor.execute('''
                INSERT INTO response_log (post_id, platform, author_handle, sentiment, response_text)
                VALUES (?, ?, ?, ?, ?)
            ''', (post_id, platform, author_handle, sentiment, response_text))

            # Record for rate limiting
            cursor.execute('''
                INSERT INTO rate_limits (platform) VALUES (?)
            ''', (platform,))

    def get_reply_count(self, platform: str, hours: int = 1) -> int:
        """Get number of replies sent in the last N hours"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(hours=hours)
            cursor.execute('''
                SELECT COUNT(*) FROM rate_limits
                WHERE platform = ? AND reply_time > ?
            ''', (platform, cutoff))
            return cursor.fetchone()[0]

    def get_reply_timestamps(self, platform: str, hours: int = 24) -> List[datetime]:
        """Get timestamps of recent replies"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(hours=hours)
            cursor.execute('''
                SELECT reply_time FROM rate_limits
                WHERE platform = ? AND reply_time > ?
                ORDER BY reply_time DESC
            ''', (platform, cutoff))
            return [datetime.fromisoformat(row[0]) for row in cursor.fetchall()]

    def cleanup_old_data(self, days: int = 30):
        """Clean up old seen posts and rate limit data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(days=days)

            cursor.execute(
                'DELETE FROM seen_posts WHERE seen_at < ?',
                (cutoff,)
            )

            cursor.execute(
                'DELETE FROM rate_limits WHERE reply_time < ?',
                (cutoff,)
            )

            deleted = cursor.rowcount
            return deleted

    def get_stats(self, platform: str = None) -> dict:
        """Get statistics about bot activity"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # Total posts seen
            if platform:
                cursor.execute(
                    'SELECT COUNT(*) FROM seen_posts WHERE platform = ?',
                    (platform,)
                )
            else:
                cursor.execute('SELECT COUNT(*) FROM seen_posts')
            stats['total_seen'] = cursor.fetchone()[0]

            # Total responses
            if platform:
                cursor.execute(
                    'SELECT COUNT(*) FROM response_log WHERE platform = ?',
                    (platform,)
                )
            else:
                cursor.execute('SELECT COUNT(*) FROM response_log')
            stats['total_responses'] = cursor.fetchone()[0]

            # Responses today
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if platform:
                cursor.execute('''
                    SELECT COUNT(*) FROM response_log
                    WHERE platform = ? AND posted_at > ?
                ''', (platform, today))
            else:
                cursor.execute(
                    'SELECT COUNT(*) FROM response_log WHERE posted_at > ?',
                    (today,)
                )
            stats['responses_today'] = cursor.fetchone()[0]

            return stats

    def create_pending_approval(self, post_id: str, platform: str, action: str,
                                post_data: dict, decision_data: dict, reply_text: str = None,
                                slack_message_ts: str = None) -> int:
        """Create a pending approval record"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO pending_approvals
                (post_id, platform, action, post_data, decision_data, reply_text, slack_message_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (post_id, platform, action, json.dumps(post_data), json.dumps(decision_data), reply_text, slack_message_ts))
            return cursor.lastrowid

    def get_pending_approval(self, approval_id: int) -> Optional[dict]:
        """Get a pending approval by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM pending_approvals WHERE id = ?
            ''', (approval_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row['id'],
                    'post_id': row['post_id'],
                    'platform': row['platform'],
                    'action': row['action'],
                    'post_data': json.loads(row['post_data']),
                    'decision_data': json.loads(row['decision_data']),
                    'reply_text': row['reply_text'],
                    'slack_message_ts': row['slack_message_ts'],
                    'status': row['status'],
                    'created_at': row['created_at'],
                    'responded_at': row['responded_at']
                }
            return None

    def update_approval_status(self, approval_id: int, status: str):
        """Update the status of a pending approval"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE pending_approvals
                SET status = ?, responded_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, approval_id))

    def get_pending_approvals(self, platform: str = None) -> List[dict]:
        """Get all pending approvals"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if platform:
                cursor.execute('''
                    SELECT * FROM pending_approvals
                    WHERE status = 'pending' AND platform = ?
                    ORDER BY created_at DESC
                ''', (platform,))
            else:
                cursor.execute('''
                    SELECT * FROM pending_approvals
                    WHERE status = 'pending'
                    ORDER BY created_at DESC
                ''')

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['id'],
                    'post_id': row['post_id'],
                    'platform': row['platform'],
                    'action': row['action'],
                    'post_data': json.loads(row['post_data']),
                    'decision_data': json.loads(row['decision_data']),
                    'reply_text': row['reply_text'],
                    'slack_message_ts': row['slack_message_ts'],
                    'status': row['status'],
                    'created_at': row['created_at']
                })
            return results
