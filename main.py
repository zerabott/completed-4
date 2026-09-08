#!/usr/bin/env python3
"""
Main entry point for Replit deployment
This file will be automatically run by Replit
"""

import os
import sys
import logging
from datetime import datetime

# Load environment variables from .env file if not running on Replit
DOTENV_AVAILABLE = True
try:
    from dotenv import load_dotenv
    load_dotenv()  # Load .env file
except ImportError:
    DOTENV_AVAILABLE = False

# Set up logging for Replit
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def check_environment():
    """Check if all required environment variables are set"""
    required_vars = [
        'BOT_TOKEN',
        'CHANNEL_ID', 
        'BOT_USERNAME',
        'ADMIN_ID_1'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {missing_vars}")
        if not DOTENV_AVAILABLE:
            logger.error(
                "python-dotenv is not installed, so a .env file cannot be read. "
                "Install it with: pip install python-dotenv"
            )
        elif not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')):
            logger.error(
                "No .env file found. Copy .env.example to .env and fill in your values."
            )
        logger.error(
            "Set them in your .env file (local runs) or in the host's secrets/environment "
            "variables (Replit, Render, etc.)."
        )
        return False
    
    logger.info("✅ All required environment variables are set")
    return True

def main():
    """Main startup function"""
    logger.info("🚀 Starting Telegram Confession Bot on Replit")
    logger.info(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info("=" * 50)
    
    # Check environment variables
    if not check_environment():
        sys.exit(1)
    
    # Import and run the bot
    try:
        logger.info("📱 Initializing bot...")
        from bot import main as bot_main
        logger.info("✅ Bot modules loaded successfully")
        
        logger.info("🔄 Starting bot polling...")
        bot_main()
        
    except Exception as e:
        logger.error(f"❌ Fatal error starting bot: {e}")
        logging.exception("Fatal error during bot startup")
        sys.exit(1)

if __name__ == "__main__":
    main()
