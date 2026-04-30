"""
Enhanced Startup Script for University Confession Bot
"""

import sys
import os
import logging
from pathlib import Path

# Add the bot directory to Python path
bot_dir = Path(__file__).parent
sys.path.insert(0, str(bot_dir))

def check_dependencies():
    """Check if core required dependencies are installed"""
    critical_packages = [
        'telegram', 'schedule'
    ]
    
    missing_packages = []
    
    for package in critical_packages:
        try:
            if package == 'telegram':
                import telegram.ext
            else:
                __import__(package)
        except ImportError:
            if package == 'telegram':
                missing_packages.append('python-telegram-bot')
            else:
                missing_packages.append(package)
    
    if missing_packages:
        print("❌ Missing critical packages:")
        for package in missing_packages:
            print(f"   - {package}")
        print("\n🔧 To install missing packages, run:")
        print("   pip install -r requirements.txt")
        return False
    
    print("✅ Core dependencies are installed!")
    return True

def check_configuration():
    """Check if configuration is properly set"""
    from config import BOT_TOKEN, CHANNEL_ID, ADMIN_IDS
    
    issues = []
    
    if not BOT_TOKEN or "YOUR_" in BOT_TOKEN:
        issues.append("❌ BOT_TOKEN is not properly set in Replit secrets")
    
    if not CHANNEL_ID:
        issues.append("❌ CHANNEL_ID is not set in Replit secrets")
    
    if not ADMIN_IDS:
        issues.append("❌ No admin IDs configured in Replit secrets")
    
    if issues:
        print("🔧 Configuration Issues Found:")
        for issue in issues:
            print(f"   {issue}")
        return False
    
    print("✅ Configuration looks good!")
    print(f"   📱 Bot Token: {BOT_TOKEN[:10]}...")
    print(f"   📢 Channel ID: {CHANNEL_ID}")
    print(f"   👤 Admin IDs: {len(ADMIN_IDS)} admin(s)")
    return True

def main():
    """Main startup function"""
    print("🤖 Starting University Confession Bot...")
    print("=" * 50)
    
    # Check dependencies
    print("1️⃣  Checking dependencies...")
    if not check_dependencies():
        print("\n❌ Startup failed due to missing dependencies.")
        return False
    
    # Check configuration
    print("\n2️⃣  Checking configuration...")
    if not check_configuration():
        print("\n❌ Startup failed due to configuration issues.")
        return False
    
    # Check database
    print("\n3️⃣  Initializing database...")
    try:
        from db import init_db
        init_db()
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        return False
    
    # Check migrations
    print("\n4️⃣  Running database migrations...")
    try:
        from migrations import run_migrations
        if run_migrations():
            print("✅ Database migrations completed!")
        else:
            print("⚠️  Some migrations may have failed, but continuing...")
    except Exception as e:
        print(f"⚠️  Migration error (continuing anyway): {e}")
    
    # Run accepting_contacts migration
    print("\n5️⃣  Running profile migrations...")
    try:
        from db_connection import get_db_connection
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            if db_conn.use_postgresql:
                cursor.execute('ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS accepting_contacts BOOLEAN DEFAULT TRUE')
            else:
                try:
                    cursor.execute('ALTER TABLE user_profiles ADD COLUMN accepting_contacts INTEGER DEFAULT 1')
                except:
                    pass  # Column already exists
            conn.commit()
        print("✅ Profile migrations completed!")
    except Exception as e:
        print(f"⚠️  Profile migration error (continuing anyway): {e}")
    
    # Start the bot
    print("\n6️⃣  Starting the bot...")
    try:
        from bot import main as bot_main
        print("✅ All systems ready!")
        print("🚀 Starting University Confession Bot...")
        print("=" * 50)
        print("📝 Bot Features:")
        print("   • Anonymous confessions & questions")
        print("   • Comment system with likes/dislikes")
        print("   • Admin moderation panel")
        print("   • Rate limiting & spam protection")
        print("   • Analytics & reporting")
        print("   • Automated backups")
        print("   • Advanced error handling")
        print("=" * 50)
        print("ℹ️  Press Ctrl+C to stop the bot")
        print()
        
        bot_main()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Bot stopped by user.")
        return True
    except Exception as e:
        print(f"\n❌ Bot startup failed: {e}")
        logging.exception("Bot startup error")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        input("\nPress Enter to exit...")
        sys.exit(1)
