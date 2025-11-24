"""
Configuration management with environment variables and config files
"""

import os
import json
import stat
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from .logger import setup_logger

logger = setup_logger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing"""
    pass


def check_env_file_permissions():
    """
    Check that .env file has secure permissions (not world-readable)
    Note: In Docker containers, volume mounts may show different permissions
    than the host file system. This check is informational only.
    """
    env_path = Path('.env')

    if not env_path.exists():
        return True  # No .env file to check

    # Skip permission check if running in Docker
    # (Docker volume mounts can show misleading permissions)
    if os.path.exists('/.dockerenv'):
        logger.debug(".env file permissions not checked in Docker container")
        return True

    # Get file permissions
    file_stat = env_path.stat()
    mode = file_stat.st_mode

    # Check if file is readable by others (last 3 bits of permissions)
    if mode & stat.S_IROTH:
        logger.warning(
            ".env file is world-readable! This is a security risk. "
            "Run: chmod 600 .env"
        )
        return False

    # Check if file is readable by group
    if mode & stat.S_IRGRP:
        logger.warning(
            ".env file is group-readable. For better security, "
            "run: chmod 600 .env"
        )
        return False

    logger.info(".env file has secure permissions")
    return True


def load_config(config_file: Optional[str] = None, check_permissions: bool = True) -> Dict[str, Any]:
    """
    Load configuration from environment variables and optional config file

    Args:
        config_file: Optional path to JSON config file
        check_permissions: Whether to check .env file permissions

    Returns:
        Dictionary of configuration values

    Raises:
        ConfigurationError: If required config is missing
    """

    # Load .env file
    load_dotenv()

    # Check .env file permissions
    if check_permissions:
        check_env_file_permissions()

    # Start with defaults
    config = {
        # Platform credentials
        'bluesky_handle': os.getenv('BLUESKY_HANDLE', ''),
        'bluesky_app_password': os.getenv('BLUESKY_APP_PASSWORD', ''),

        'anthropic_api_key': os.getenv('ANTHROPIC_API_KEY', ''),

        # Bot behavior
        'website_url': os.getenv('WEBSITE_URL', 'https://example.com'),
        'bot_username': os.getenv('BOT_USERNAME', 'BlueSkyBot'),
        'manual_approval': os.getenv('MANUAL_APPROVAL', 'true').lower() == 'true',
        'slack_interactive_mode': os.getenv('SLACK_INTERACTIVE_MODE', 'false').lower() == 'true',

        # Claude model
        'claude_model': os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-20250514'),

        # Keywords - Load from environment variable (comma-separated)
        'keywords': [
            kw.strip()
            for kw in os.getenv('KEYWORDS', 'keyword1,keyword2,keyword3').split(',')
            if kw.strip()
        ],

        # Rate limiting (Conservative - Bluesky API allows 1,666/hour, 11,666/day)
        'max_replies_per_hour': int(os.getenv('MAX_REPLIES_PER_HOUR', '20')),
        'max_replies_per_day': int(os.getenv('MAX_REPLIES_PER_DAY', '150')),
        'min_seconds_between_replies': int(os.getenv('MIN_SECONDS_BETWEEN_REPLIES', '120')),

        # Quality filters
        'min_followers_to_reply': int(os.getenv('MIN_FOLLOWERS_TO_REPLY', '10')),
        'skip_verified_politicians': os.getenv('SKIP_VERIFIED_POLITICIANS', 'true').lower() == 'true',
        'max_post_age_hours': int(os.getenv('MAX_POST_AGE_HOURS', '2')),

        # Platform-specific
        'max_reply_chars_bluesky': 300,
    }

    # Load from config file if provided
    if config_file:
        config_path = Path(config_file)
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    file_config = json.load(f)
                config.update(file_config)
                logger.info(f"Loaded config from {config_file}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse config file {config_file}: {e}")
                raise ConfigurationError(f"Invalid JSON in config file: {e}")
        else:
            logger.warning(f"Config file {config_file} not found, using defaults")

    return config


def validate_bluesky_config(config: Dict[str, Any]) -> bool:
    """Validate Bluesky credentials are present"""
    required = ['bluesky_handle', 'bluesky_app_password']

    missing = [key for key in required if not config.get(key)]

    if missing:
        logger.error(f"Missing Bluesky credentials: {', '.join(missing)}")
        return False

    return True


def validate_anthropic_config(config: Dict[str, Any]) -> bool:
    """Validate Anthropic API key is present"""
    if not config.get('anthropic_api_key'):
        logger.error("Missing ANTHROPIC_API_KEY")
        return False

    return True
