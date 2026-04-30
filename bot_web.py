#!/usr/bin/env python3
"""
Web Service Wrapper for Telegram Bot on Render
Runs bot.py in a background subprocess and exposes health check endpoints
"""

from flask import Flask, jsonify
import os
import sys
import logging
from datetime import datetime, timezone
import subprocess
import threading

# ------------------- Logging -------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ------------------- Environment -------------------
required_vars = ["BOT_TOKEN", "CHANNEL_ID", "BOT_USERNAME", "ADMIN_ID_1"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    logger.error(f"❌ Missing environment variables: {missing_vars}")
    sys.exit(1)

# ------------------- Bot Status -------------------
bot_status = {"running": False, "start_time": None, "last_activity": None}

# ------------------- Flask App -------------------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    """Basic health check"""
    return jsonify({
        "status": "healthy",
        "service": "Telegram Confession Bot",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "bot_running": bot_status["running"],
        "uptime": (datetime.now(timezone.utc) - bot_status["start_time"]).total_seconds() if bot_status["start_time"] else 0
    })

@app.route("/health", methods=["GET"])
def health():
    """Detailed health check"""
    return jsonify({
        "status": "ok" if bot_status["running"] else "error",
        "bot_status": bot_status,
        "environment": {var: bool(os.getenv(var)) for var in required_vars}
    })

@app.route("/ping", methods=["GET"])
def ping():
    """Simple ping endpoint"""
    return "pong"

@app.route("/bot-logs", methods=["GET"])
def bot_logs():
    """View recent bot logs for debugging"""
    try:
        with open('bot_output.log', 'r') as f:
            logs = f.read()
        return f"<pre>{logs[-5000:]}</pre>"  # Last 5000 chars
    except Exception as e:
        return f"No logs available: {e}"

# ------------------- Database Setup -------------------
def setup_database():
    """Run database migrations and setup"""
    try:
        logger.info("🗄️ Setting up database...")
        
        # Import and run migrations
        from migration import run_database_migrations
        run_database_migrations()
        
        logger.info("✅ Database setup completed")
        
        # Run accepting_contacts migration
        logger.info("👤 Running profile migrations...")
        try:
            from db_connection import get_db_connection
            db_conn = get_db_connection()
            with db_conn.get_connection() as conn:
                cursor = conn.cursor()
                if db_conn.use_postgresql:
                    cursor.execute('ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS accepting_contacts BOOLEAN DEFAULT TRUE')
                    logger.info("✅ Added accepting_contacts column (PostgreSQL)")
                else:
                    try:
                        cursor.execute('ALTER TABLE user_profiles ADD COLUMN accepting_contacts INTEGER DEFAULT 1')
                        logger.info("✅ Added accepting_contacts column (SQLite)")
                    except:
                        logger.info("ℹ️ Column accepting_contacts already exists")
                conn.commit()
            logger.info("✅ Profile migrations completed!")
        except Exception as e:
            logger.warning(f"⚠️ Profile migration error (continuing anyway): {e}")
            
    except Exception as e:
        logger.error(f"❌ Database setup failed: {e}")
        raise

# ------------------- Start Bot -------------------
def run_bot():
    """Start bot.py as a non-blocking subprocess"""
    try:
        logger.info("🚀 Starting Telegram bot subprocess...")
        bot_status["start_time"] = datetime.now(timezone.utc)
        bot_status["running"] = True

        # Start bot.py with output redirected to stdout so we can see errors
        import subprocess
        
        # Create a log file to capture bot output
        log_file = open('bot_output.log', 'w')
        
        bot_process = subprocess.Popen(
            [sys.executable, "bot.py"],
            stdout=subprocess.PIPE,  # Capture output
            stderr=subprocess.STDOUT,  # Merge stderr with stdout
            universal_newlines=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}  # Ensure immediate output
        )
        
        logger.info(f"✅ Bot subprocess started with PID: {bot_process.pid}")
        logger.info("📝 Bot logs are being captured")
        
        # Read bot output in real-time and log it
        def read_bot_output():
            import time
            with open('bot_output.log', 'w') as log:
                for line in bot_process.stdout:
                    line = line.strip()
                    if line:
                        # Write to log file
                        log.write(line + '\n')
                        log.flush()  # Ensure immediate write
                        
                        # Log every line from bot immediately
                        if "ERROR" in line or "error" in line.lower():
                            logger.error(f"🤖 {line}")
                        elif "WARNING" in line or "warning" in line.lower():
                            logger.warning(f"🤖 {line}")
                        else:
                            logger.info(f"🤖 {line}")
        
        # Start thread to read output
        import threading
        output_thread = threading.Thread(target=read_bot_output, daemon=True)
        output_thread.start()
        
        # Monitor the bot process
        def monitor_bot():
            import time
            startup_time = time.time()
            
            while True:
                poll_result = bot_process.poll()
                if poll_result is not None:
                    elapsed = time.time() - startup_time
                    logger.error(f"❌ Bot subprocess exited after {elapsed:.1f}s with code: {poll_result}")
                    bot_status["running"] = False
                    sys.exit(1)  # Exit the whole process if bot dies
                
                # Check if bot has been running for too long without activity
                elapsed = time.time() - startup_time
                if elapsed > 120 and not bot_status.get("last_activity"):
                    logger.error(f"⏱️ Bot subprocess appears hung - no activity for {elapsed:.0f}s")
                    logger.error("📋 Checking bot_output.log for last output...")
                    try:
                        with open('bot_output.log', 'r') as f:
                            logs = f.read()
                            if logs:
                                logger.error(f"📄 Last bot output:\n{logs[-2000:]}")
                    except:
                        pass
                    bot_status["running"] = False
                    sys.exit(1)
                
                bot_status["last_activity"] = datetime.now(timezone.utc)
                time.sleep(5)
        
        monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
        monitor_thread.start()

    except Exception as e:
        logger.error(f"❌ Bot subprocess error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        bot_status["running"] = False
        raise

# ------------------- Main -------------------
if __name__ == "__main__":
    # First setup database
    setup_database()
    
    # Start bot in a background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start Flask server immediately so Render detects the open port
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Starting web server on 0.0.0.0:{port}")
    
    # Keep the main thread alive forever
    try:
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("👋 Shutting down...")
        sys.exit(0)


