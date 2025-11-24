#!/usr/bin/env python3
"""
Test script for Stand for Hemp V2 setup
Validates configuration, database, and API connections
"""

import sys
import os
from pathlib import Path

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text):
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{text:^60}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")


def print_success(text):
    print(f"{GREEN}✓{RESET} {text}")


def print_error(text):
    print(f"{RED}✗{RESET} {text}")


def print_warning(text):
    print(f"{YELLOW}⚠{RESET} {text}")


def test_imports():
    """Test that all required modules can be imported"""
    print_header("Testing Python Dependencies")

    required_modules = {
        'anthropic': 'Anthropic Claude API',
        'atproto': 'Bluesky AT Protocol',
        'dotenv': 'Environment variable loading'
    }

    all_ok = True
    for module, description in required_modules.items():
        try:
            __import__(module)
            print_success(f"{module:15} - {description}")
        except ImportError:
            print_error(f"{module:15} - {description} (MISSING)")
            all_ok = False

    return all_ok


def test_utils():
    """Test that utils modules are available"""
    print_header("Testing Utils Modules")

    try:
        from utils import setup_logger, Database, exponential_backoff
        print_success("utils.logger")
        print_success("utils.database")
        print_success("utils.retry")

        from utils.config import load_config
        print_success("utils.config")

        from utils.base_monitor import BaseMonitor, ClaudeDecisionEngine, RateLimiter
        print_success("utils.base_monitor")

        return True
    except ImportError as e:
        print_error(f"Failed to import utils: {e}")
        return False


def test_directories():
    """Test that required directories exist or can be created"""
    print_header("Testing Directories")

    directories = ['logs', 'data']
    all_ok = True

    for directory in directories:
        path = Path(directory)
        if path.exists():
            print_success(f"{directory}/ directory exists")
        else:
            try:
                path.mkdir(exist_ok=True)
                print_success(f"{directory}/ directory created")
            except Exception as e:
                print_error(f"Failed to create {directory}/ directory: {e}")
                all_ok = False

    return all_ok


def test_env_file():
    """Test .env file exists and has required variables"""
    print_header("Testing Environment Configuration")

    if not Path('.env').exists():
        print_error(".env file not found")
        print("   Run: cp .env.example .env")
        print("   Then edit .env and add your API keys")
        return False

    print_success(".env file exists")

    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    # Check permissions
    from utils.config import check_env_file_permissions
    if check_env_file_permissions():
        print_success(".env file has secure permissions")
    else:
        print_warning(".env file permissions should be tightened (run: chmod 600 .env)")

    # Check required variables
    required = {
        'ANTHROPIC_API_KEY': 'Required for Claude AI',
        'BLUESKY_HANDLE': 'Required for Bluesky'
    }

    anthropic_ok = bool(os.getenv('ANTHROPIC_API_KEY'))
    bluesky_ok = all([
        os.getenv('BLUESKY_HANDLE'),
        os.getenv('BLUESKY_APP_PASSWORD')
    ])

    if anthropic_ok:
        print_success("Anthropic API key configured")
    else:
        print_error("Anthropic API key missing")

    if bluesky_ok:
        print_success("Bluesky credentials configured")
    else:
        print_error("Bluesky credentials missing")

    return anthropic_ok and bluesky_ok


def test_database():
    """Test database initialization"""
    print_header("Testing Database")

    try:
        from utils.database import Database

        db = Database()
        print_success("Database initialized")

        # Test basic operations
        db.mark_post_seen('test_post_123', 'test_platform', 'test_user')
        if db.has_seen_post('test_post_123', 'test_platform'):
            print_success("Database read/write working")
        else:
            print_error("Database read/write failed")
            return False

        stats = db.get_stats()
        print_success(f"Database stats: {stats['total_seen']} seen, {stats['total_responses']} responses")

        return True
    except Exception as e:
        print_error(f"Database test failed: {e}")
        return False


def test_api_connections():
    """Test API connections (if credentials available)"""
    print_header("Testing API Connections")

    from dotenv import load_dotenv
    load_dotenv()

    # Test Anthropic
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            print_success("Anthropic API connection successful")
        except Exception as e:
            print_error(f"Anthropic API connection failed: {e}")
            return False
    else:
        print_warning("Skipping Anthropic API test (no key configured)")

    # Test Bluesky
    bluesky_handle = os.getenv('BLUESKY_HANDLE')
    if bluesky_handle:
        try:
            from atproto import Client
            client = Client()
            client.login(bluesky_handle, os.getenv('BLUESKY_APP_PASSWORD'))
            print_success(f"Bluesky connection successful (@{bluesky_handle})")
        except Exception as e:
            print_error(f"Bluesky connection failed: {e}")
            print_warning("Check your Bluesky credentials")
    else:
        print_warning("Skipping Bluesky test (no credentials configured)")

    return True


def main():
    """Run all tests"""
    print_header("Stand for Hemp V2 - Setup Test")

    results = {
        'Python Dependencies': test_imports(),
        'Utils Modules': test_utils(),
        'Directories': test_directories(),
        'Environment Config': test_env_file(),
        'Database': test_database(),
        'API Connections': test_api_connections()
    }

    # Summary
    print_header("Test Summary")

    all_passed = True
    for test_name, result in results.items():
        if result:
            print_success(f"{test_name:25} PASSED")
        else:
            print_error(f"{test_name:25} FAILED")
            all_passed = False

    print()

    if all_passed:
        print_success("All tests passed! You're ready to run the bots.")
        print()
        print("Next steps:")
        print("  1. Review keywords in .env or use --config")
        print("  2. Start X monitor:      python x_monitor_v2.py --manual")
        print("  3. Start Bluesky monitor: python bluesky_monitor_v2.py --manual")
        print()
        return 0
    else:
        print_error("Some tests failed. Please fix the issues above.")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
