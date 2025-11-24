#!/usr/bin/env python3
"""
Quick setup checker for BlueSky Listening Agent bot
Runs before the main bot to verify everything is configured
"""

import os
import sys

def check_env_vars():
    """Check if all required environment variables are set"""
    required_vars = [
        'BLUESKY_HANDLE',
        'BLUESKY_APP_PASSWORD',
        'SLACK_WEBHOOK_URL',
        'SLACK_SIGNING_SECRET',
        'ANTHROPIC_API_KEY',
        'WEBSITE_URL',
        'KEYWORDS'
    ]
    
    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    return missing

def check_packages():
    """Check if required packages are installed"""
    packages = ['atproto', 'anthropic']
    missing = []

    for package in packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    return missing

def main():
    print("BlueSky Engagement Agent - Setup Checker\n")
    
    # Check .env file exists
    if not os.path.exists('.env'):
        print("❌ No .env file found!")
        print("\n📝 Next steps:")
        print("   1. Copy the template: cp .env.example .env")
        print("   2. Edit .env and add your API keys")
        print("   3. Run this script again")
        return False
    
    # Load .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ .env file loaded")
    except ImportError:
        print("⚠️  python-dotenv not installed (optional but helpful)")
    
    # Check environment variables
    missing_vars = check_env_vars()
    if missing_vars:
        print(f"\n❌ Missing environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n📝 Add these to your .env file")
        return False
    else:
        print("✅ All API credentials found")
    
    # Check packages
    missing_packages = check_packages()
    if missing_packages:
        print(f"\n❌ Missing Python packages:")
        for pkg in missing_packages:
            print(f"   - {pkg}")
        print("\n📝 Install with: pip install -r requirements.txt")
        return False
    else:
        print("✅ All Python packages installed")
    
    # Test API connections
    print("\n🔌 Testing API connections...")

    try:
        from atproto import Client
        client = Client()
        client.login(os.getenv('BLUESKY_HANDLE'), os.getenv('BLUESKY_APP_PASSWORD'))
        print(f"✅ Bluesky connected: {os.getenv('BLUESKY_HANDLE')}")
    except Exception as e:
        print(f"❌ Bluesky connection failed: {e}")
        print("   Check your Bluesky credentials")
        return False
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        # Simple test message
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )
        print(f"✅ Anthropic API connected")
    except Exception as e:
        print(f"❌ Anthropic connection failed: {e}")
        print("   Check your Anthropic API key")
        return False
    
    # All checks passed
    print("\n✅ All systems ready!")
    print("\n🚀 Next steps:")
    print("   1. Review keywords in your bot configuration")
    print("   2. Start bot: python bluesky_listener.py")
    print("   3. Bot will ask for approval before posting (MANUAL_APPROVAL=true)")
    print("   4. Once comfortable, set MANUAL_APPROVAL=false for auto mode")
    print("\n💡 Tip: Run in a 'screen' session on a server for 24/7 operation")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
