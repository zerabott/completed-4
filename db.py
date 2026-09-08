import sqlite3
import datetime
import time
import asyncio
import concurrent.futures
import psycopg2
from config import DB_PATH
from db_connection import get_db_connection, cache_manager, make_async, AsyncDBWrapper
import logging

logger = logging.getLogger(__name__)

# Initialize async wrapper on module load
AsyncDBWrapper.initialize()

# Keep backward compatibility
def get_db():
    """Get database connection (backward compatibility)"""
    db_conn = get_db_connection()
    return db_conn.get_connection()

def init_db():
    """Initialize database with enhanced schema and performance indexes"""
    db_conn = get_db_connection()
    use_pg = getattr(db_conn, "use_postgresql", False)

    with db_conn.get_connection() as conn:
        cursor = conn.cursor()

        # Users table
        if use_pg:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                questions_asked INT DEFAULT 0,
                comments_posted INT DEFAULT 0,
                blocked INT DEFAULT 0
            )''')
        else:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TEXT DEFAULT CURRENT_TIMESTAMP,
                questions_asked INTEGER DEFAULT 0,
                comments_posted INTEGER DEFAULT 0,
                blocked INTEGER DEFAULT 0
            )''') 
            # User Profiles table (for enhanced profile system)
        if use_pg:
            # PostgreSQL Schema
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id BIGINT PRIMARY KEY,
                display_name TEXT NOT NULL,
                emoji TEXT,
                bio TEXT,
                is_active INT DEFAULT 1,
                gender TEXT,
                age INTEGER,
                department TEXT,
                year TEXT,
                religion TEXT,
                relationship_status TEXT,
                other_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )''')
        else:
            # SQLite Schema
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                display_name TEXT NOT NULL,
                emoji TEXT,
                bio TEXT,
                is_active INTEGER DEFAULT 1,
                gender TEXT,
                age INTEGER,
                department TEXT,
                year TEXT,
                religion TEXT,
                relationship_status TEXT,
                other_info TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )''')
            # Add index for faster profile lookups
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id)")

        # Posts table
        if use_pg:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                post_id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_id BIGINT NOT NULL,
                approved INT DEFAULT NULL,
                channel_message_id INT,
                flagged INT DEFAULT 0,
                likes INT DEFAULT 0,
                post_number INT DEFAULT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
        else:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER NOT NULL,
                approved INTEGER DEFAULT NULL,
                channel_message_id INTEGER,
                flagged INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                post_number INTEGER DEFAULT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')

        # Comments table
        if use_pg:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                comment_id SERIAL PRIMARY KEY,
                post_id INT NOT NULL,
                user_id BIGINT NOT NULL,
                content TEXT NOT NULL,
                parent_comment_id INT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                likes INT DEFAULT 0,
                dislikes INT DEFAULT 0,
                flagged INT DEFAULT 0,
                FOREIGN KEY(post_id) REFERENCES posts(post_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(parent_comment_id) REFERENCES comments(comment_id)
            )''')
        else:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                parent_comment_id INTEGER,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                likes INTEGER DEFAULT 0,
                dislikes INTEGER DEFAULT 0,
                flagged INTEGER DEFAULT 0,
                FOREIGN KEY(post_id) REFERENCES posts(post_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(parent_comment_id) REFERENCES comments(comment_id)
            )''')

        # Reactions table
        if use_pg:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reactions (
                reaction_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                target_type TEXT NOT NULL,
                target_id INT NOT NULL,
                reaction_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, target_type, target_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
        else:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reactions (
                reaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                reaction_type TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, target_type, target_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')

        # Reports table
        if use_pg:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                report_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                target_type TEXT NOT NULL,
                target_id INT NOT NULL,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
        else:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                target_type TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                reason TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')

        # Admin messages table
        if use_pg:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_messages (
                message_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                admin_id BIGINT,
                user_message TEXT,
                admin_reply TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                replied INT DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
        else:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                admin_id INTEGER,
                user_message TEXT,
                admin_reply TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                replied INTEGER DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')

        # Ranking system tables
        if use_pg:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_rankings (
                user_id BIGINT PRIMARY KEY,
                total_points INTEGER DEFAULT 0,
                weekly_points INTEGER DEFAULT 0,
                monthly_points INTEGER DEFAULT 0,
                current_rank_id INTEGER DEFAULT 1,
                rank_progress REAL DEFAULT 0.0,
                total_achievements INTEGER DEFAULT 0,
                highest_rank_achieved INTEGER DEFAULT 1,
                consecutive_days INTEGER DEFAULT 0,
                last_login_date TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS point_transactions (
                transaction_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                points_change INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                reference_id INTEGER,
                reference_type TEXT,
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_achievements (
                achievement_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                achievement_type TEXT NOT NULL,
                achievement_name TEXT NOT NULL,
                achievement_description TEXT,
                points_awarded INTEGER DEFAULT 0,
                is_special INTEGER DEFAULT 0,
                metadata TEXT,
                achieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
        else: # For SQLite
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_rankings (
                user_id INTEGER PRIMARY KEY,
                total_points INTEGER DEFAULT 0,
                weekly_points INTEGER DEFAULT 0,
                monthly_points INTEGER DEFAULT 0,
                current_rank_id INTEGER DEFAULT 1,
                rank_progress REAL DEFAULT 0.0,
                total_achievements INTEGER DEFAULT 0,
                highest_rank_achieved INTEGER DEFAULT 1,
                consecutive_days INTEGER DEFAULT 0,
                last_login_date TEXT,
                last_activity TEXT DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS point_transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                points_change INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                reference_id INTEGER,
                reference_type TEXT,
                description TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
            
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_achievements (
                achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                achievement_type TEXT NOT NULL,
                achievement_name TEXT NOT NULL,
                achievement_description TEXT,
                points_awarded INTEGER DEFAULT 0,
                is_special INTEGER DEFAULT 0,
                metadata TEXT,
                achieved_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS rank_definitions (
            rank_id SERIAL PRIMARY KEY,
            rank_name TEXT NOT NULL,
            rank_emoji TEXT NOT NULL,
            min_points INTEGER NOT NULL,
            max_points INTEGER,
            special_perks TEXT,
            is_special INTEGER DEFAULT 0
        )''')
        
        # Insert default ranks, handling potential schema mismatch
        try:
            cursor.execute('''
                INSERT INTO rank_definitions (rank_id, rank_name, rank_emoji, min_points, max_points, special_perks, is_special)
                VALUES 
                    (1, 'Freshman', '🥉', 0, 99, '{}', 0),
                    (2, 'Sophomore', '🥈', 100, 249, '{}', 0),
                    (3, 'Junior', '🥇', 250, 499, '{}', 0),
                    (4, 'Senior', '🏆', 500, 999, '{"daily_confessions": 8}', 0),
                    (5, 'Graduate', '🎓', 1000, 1999, '{"daily_confessions": 10, "priority_review": true}', 0),
                    (6, 'Master', '👑', 2000, 4999, '{"daily_confessions": 15, "priority_review": true, "comment_highlight": true}', 1),
                    (7, 'Legend', '🌟', 5000, NULL, '{"all_perks": true, "unlimited_daily": true, "legend_badge": true}', 1)
                ON CONFLICT (rank_id) DO NOTHING
            ''')
            conn.commit()
            
        except (sqlite3.OperationalError, psycopg2.errors.UndefinedColumn, psycopg2.errors.SyntaxError) as e:
            if "no such column: min_points" in str(e):
                logger.warning("Warning: rank_definitions table exists but has old schema. Run migrations to fix.")
            else:
                logger.error(f"Failed to insert rank definitions, rolling back: {e}")
                conn.rollback() # Rollback to clear aborted transaction state
                
        except Exception as e:
            logger.error(f"Failed to insert rank definitions, rolling back: {e}")
            conn.rollback()
        
        # Analytics tables
        if use_pg:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_activity_log (
                log_id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                activity_type TEXT NOT NULL,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
        else:
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_activity_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                details TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_stats (
            stat_date TEXT PRIMARY KEY,
            new_users INTEGER DEFAULT 0,
            total_confessions INTEGER DEFAULT 0,
            approved_confessions INTEGER DEFAULT 0,
            rejected_confessions INTEGER DEFAULT 0,
            total_comments INTEGER DEFAULT 0,
            active_users INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Add missing columns to posts table for analytics / media / sensitivity
        if not use_pg:
            # SQLite path: keep full backfill logic for backward compatibility
            try:
                cursor.execute("ALTER TABLE posts ADD COLUMN status TEXT DEFAULT 'pending'")
            except (sqlite3.OperationalError, psycopg2.errors.DuplicateColumn):
                pass  # Column already exists
            except Exception as e:
                logger.error(f"Failed to add 'status' column, rolling back: {e}")
                conn.rollback()
            
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN sentiment_score REAL DEFAULT 0.0')
            except (sqlite3.OperationalError, psycopg2.errors.DuplicateColumn):
                pass
            except Exception as e:
                logger.error(f"Failed to add 'sentiment_score' column, rolling back: {e}")
                conn.rollback()
            
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN profanity_detected INTEGER DEFAULT 0')
            except (sqlite3.OperationalError, psycopg2.errors.DuplicateColumn):
                pass
            except Exception as e:
                logger.error(f"Failed to add 'profanity_detected' column, rolling back: {e}")
                conn.rollback()
            
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN spam_score REAL DEFAULT 0.0')
            except (sqlite3.OperationalError, psycopg2.errors.DuplicateColumn):
                pass
            except Exception as e:
                logger.error(f"Failed to add 'spam_score' column, rolling back: {e}")
                conn.rollback()
            
            # Media support columns (SQLite legacy)
            for col_sql, col_name in [
                ("ALTER TABLE posts ADD COLUMN media_type TEXT", "media_type"),
                ("ALTER TABLE posts ADD COLUMN media_file_id TEXT", "media_file_id"),
                ("ALTER TABLE posts ADD COLUMN media_file_unique_id TEXT", "media_file_unique_id"),
                ("ALTER TABLE posts ADD COLUMN media_caption TEXT", "media_caption"),
                ("ALTER TABLE posts ADD COLUMN media_file_size INTEGER", "media_file_size"),
                ("ALTER TABLE posts ADD COLUMN media_mime_type TEXT", "media_mime_type"),
                ("ALTER TABLE posts ADD COLUMN media_duration INTEGER", "media_duration"),
                ("ALTER TABLE posts ADD COLUMN media_width INTEGER", "media_width"),
                ("ALTER TABLE posts ADD COLUMN media_height INTEGER", "media_height"),
                ("ALTER TABLE posts ADD COLUMN media_thumbnail_file_id TEXT", "media_thumbnail_file_id"),
            ]:
                try:
                    cursor.execute(col_sql)
                except (sqlite3.OperationalError, psycopg2.errors.DuplicateColumn):
                    pass
                except Exception as e:
                    logger.error(f"Failed to add '{col_name}' column, rolling back: {e}")
                    conn.rollback()

            # Sensitive content flag (SQLite)
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN is_sensitive INTEGER DEFAULT 0')
            except (sqlite3.OperationalError, psycopg2.errors.DuplicateColumn):
                pass
            except Exception as e:
                logger.error(f"Failed to add 'is_sensitive' column, rolling back: {e}")
                conn.rollback()

            # Edited confession tracking columns
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN is_edited INTEGER DEFAULT 0')
            except (sqlite3.OperationalError, psycopg2.errors.DuplicateColumn):
                pass
            except Exception as e:
                logger.error(f"Failed to add 'is_edited' column, rolling back: {e}")
                conn.rollback()
            
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN edited_timestamp TEXT')
            except (sqlite3.OperationalError, psycopg2.errors.DuplicateColumn):
                pass
            except Exception as e:
                logger.error(f"Failed to add 'edited_timestamp' column, rolling back: {e}")
                conn.rollback()

            # Update existing posts to have proper status
            cursor.execute('''
                UPDATE posts 
                SET status = CASE 
                    WHEN approved = 1 THEN 'approved'
                    WHEN approved = 0 THEN 'rejected'
                    ELSE 'pending'
                END 
                WHERE status IS NULL OR status = 'pending'
            ''')
        else:
            # PostgreSQL path: only ensure the is_sensitive column exists
            # and that rejected_by_admin can store full Telegram admin IDs.
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN is_sensitive INTEGER DEFAULT 0')
            except psycopg2.errors.DuplicateColumn:
                # Column already exists, safe to ignore
                conn.rollback()
            except Exception as e:
                logger.error(f"Failed to add 'is_sensitive' column for PostgreSQL, rolling back: {e}")
                conn.rollback()

            # Make sure rejected_by_admin is BIGINT (Telegram IDs are large)
            try:
                cursor.execute('ALTER TABLE posts ALTER COLUMN rejected_by_admin TYPE BIGINT')
            except Exception as e:
                # If the column does not exist yet or type is already BIGINT, ignore
                logger.warning(f"Could not alter rejected_by_admin to BIGINT (may already be correct or missing): {e}")
                conn.rollback()

            # Edited confession tracking columns for PostgreSQL
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN IF NOT EXISTS is_edited INTEGER DEFAULT 0')
            except Exception as e:
                logger.error(f"Failed to add 'is_edited' column for PostgreSQL: {e}")
                conn.rollback()
            
            try:
                cursor.execute('ALTER TABLE posts ADD COLUMN IF NOT EXISTS edited_timestamp TIMESTAMP')
            except Exception as e:
                logger.error(f"Failed to add 'edited_timestamp' column for PostgreSQL: {e}")
                conn.rollback()

        conn.commit()

        # Profile and contact system tables
        # User profiles (display name, emoji, bio, extended fields)
        if use_pg:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id BIGINT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    emoji TEXT,
                    bio TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    gender TEXT,
                    age INTEGER,
                    department TEXT,
                    year TEXT,
                    religion TEXT,
                    relationship_status TEXT,
                    other_info TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id INTEGER PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    emoji TEXT,
                    bio TEXT,
                    is_active INTEGER DEFAULT 1,
                    gender TEXT,
                    age INTEGER,
                    department TEXT,
                    year TEXT,
                    religion TEXT,
                    relationship_status TEXT,
                    other_info TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

        # Profile contacts (chat sessions between two users)
        if use_pg:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profile_contacts (
                    id SERIAL PRIMARY KEY,
                    user_a_id BIGINT NOT NULL,
                    user_b_id BIGINT NOT NULL,
                    status TEXT NOT NULL,
                    initiator_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_message_at TIMESTAMP,
                    UNIQUE (user_a_id, user_b_id),
                    FOREIGN KEY (user_a_id) REFERENCES users (user_id),
                    FOREIGN KEY (user_b_id) REFERENCES users (user_id)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profile_contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_a_id INTEGER NOT NULL,
                    user_b_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    initiator_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_message_at TEXT,
                    UNIQUE (user_a_id, user_b_id),
                    FOREIGN KEY (user_a_id) REFERENCES users (user_id),
                    FOREIGN KEY (user_b_id) REFERENCES users (user_id)
                )
            ''')

        # Profile blocks (one-way block between two users)
        if use_pg:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profile_blocks (
                    blocker_id BIGINT NOT NULL,
                    blocked_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (blocker_id, blocked_id),
                    FOREIGN KEY (blocker_id) REFERENCES users (user_id),
                    FOREIGN KEY (blocked_id) REFERENCES users (user_id)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profile_blocks (
                    blocker_id INTEGER NOT NULL,
                    blocked_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (blocker_id, blocked_id),
                    FOREIGN KEY (blocker_id) REFERENCES users (user_id),
                    FOREIGN KEY (blocked_id) REFERENCES users (user_id)
                )
            ''')

        # Profile messages counter (for daily message limits)
        if use_pg:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profile_message_counts (
                    user_id BIGINT NOT NULL,
                    message_date DATE NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, message_date),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
        else:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS profile_message_counts (
                    user_id INTEGER NOT NULL,
                    message_date TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, message_date),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

        # ADD PERFORMANCE INDEXES - Optimized for common query patterns
        try:
            # Indexes for comments table
            if use_pg:
                # PostgreSQL indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_timestamp ON comments(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON comments(parent_comment_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_timestamp ON comments(post_id, timestamp)")
                
                # NEW: Indexes for popular comments and comment sorting
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_likes ON comments(post_id, likes DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_user_timestamp ON comments(user_id, timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_flagged ON comments(flagged) WHERE flagged = 1")
                
                # Indexes for posts table
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_approved ON posts(approved)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_approved_timestamp ON posts(approved, timestamp) WHERE approved = 1")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_approved ON posts(user_id, approved)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_media ON posts(media_type, media_file_id) WHERE media_type IS NOT NULL")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_sensitive ON posts(is_sensitive) WHERE is_sensitive = 1")
                
                # NEW: Composite indexes for common queries
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_approved_time ON posts(user_id, approved, timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_category_approved_time ON posts(category, approved, timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_likes ON posts(likes DESC) WHERE approved = 1")
                
                # Indexes for users table
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_blocked ON users(blocked)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_join_date ON users(join_date)")
                
                # Indexes for reactions table
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reactions_target ON reactions(target_type, target_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reactions_user_target ON reactions(user_id, target_type, target_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reactions_timestamp ON reactions(timestamp DESC)")
                
                # Indexes for reports table
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_target ON reports(target_type, target_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_timestamp ON reports(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user_id, timestamp DESC)")
            else:
                # SQLite indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_timestamp ON comments(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON comments(parent_comment_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_timestamp ON comments(post_id, timestamp)")
                
                # NEW: Indexes for popular comments
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_likes ON comments(post_id, likes DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_user_timestamp ON comments(user_id, timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_comments_flagged ON comments(flagged)")
                
                # Indexes for posts table
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_approved ON posts(approved)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_category ON posts(category)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_approved_timestamp ON posts(approved, timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_approved ON posts(user_id, approved)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_media ON posts(media_type, media_file_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_sensitive ON posts(is_sensitive)")
                
                # NEW: Composite indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_user_approved_time ON posts(user_id, approved, timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_category_approved_time ON posts(category, approved, timestamp DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_likes ON posts(likes DESC)")
                
                # Indexes for users table
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_blocked ON users(blocked)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_join_date ON users(join_date)")
                
                # Indexes for reactions table
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reactions_target ON reactions(target_type, target_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reactions_user_target ON reactions(user_id, target_type, target_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reactions_timestamp ON reactions(timestamp DESC)")
                
                # Indexes for reports table
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_target ON reports(target_type, target_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_timestamp ON reports(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_user ON reports(user_id, timestamp DESC)")
            
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Could not create database indexes: {e}")

        conn.commit()

def add_user(user_id, username=None, first_name=None, last_name=None):
    """Add or update user information - optimized with batch operations"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        if db_conn.use_postgresql:
            # PostgreSQL doesn't support INSERT OR REPLACE, use ON CONFLICT instead
            cursor.execute(f'''
                INSERT INTO users (user_id, username, first_name, last_name, join_date, questions_asked, comments_posted, blocked)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, CURRENT_TIMESTAMP, 0, 0, 0)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name
            ''', (user_id, username, first_name, last_name))
        else:
            cursor.execute(f'''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, join_date, questions_asked, comments_posted, blocked)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, 
                    COALESCE((SELECT join_date FROM users WHERE user_id = {placeholder} AND join_date IS NOT NULL), CURRENT_TIMESTAMP),
                    COALESCE((SELECT questions_asked FROM users WHERE user_id = {placeholder}), 0),
                    COALESCE((SELECT comments_posted FROM users WHERE user_id = {placeholder}), 0),
                    COALESCE((SELECT blocked FROM users WHERE user_id = {placeholder}), 0)
                )
            ''', (user_id, username, first_name, last_name, user_id, user_id, user_id, user_id))
        conn.commit()
    
    # Invalidate user cache
    cache_manager.delete(f'user_info_{user_id}')
    cache_manager.delete(f'user_blocked_{user_id}')

def get_user_info(user_id):
    """Get complete user information - optimized with caching"""
    # Check cache first
    cache_key = f'user_info_{user_id}'
    cached = cache_manager.get(cache_key)
    if cached is not None:
        return cached
    
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f'''
            SELECT user_id, username, first_name, last_name, join_date, 
                   questions_asked, comments_posted, blocked
            FROM users WHERE user_id = {placeholder}
        ''', (user_id,))
        result = cursor.fetchone()
        
        # Cache for 5 minutes
        if result:
            cache_manager.set(cache_key, result, 300)
        
        return result

def get_all_users():
    """Get all users from the database"""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, username, first_name, last_name, join_date, 
                   questions_asked, comments_posted, blocked
            FROM users
            ORDER BY join_date DESC
        ''')
        return cursor.fetchall()


def get_comment_count(post_id):
    """Get total comment count for a post - optimized with caching and index"""
    # Check cache first
    cache_key = f'comment_count_{post_id}'
    cached = cache_manager.get(cache_key)
    if cached is not None:
        return cached
    
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        # Index on comments(post_id) makes this very fast
        cursor.execute(f'SELECT COUNT(*) FROM comments WHERE post_id = {placeholder}', (post_id,))
        result = cursor.fetchone()
        count = result[0] if result else 0
        
        # Cache for 2 minutes (comments change frequently)
        cache_manager.set(cache_key, count, 120)
        
        return count

def is_blocked_user(user_id):
    """Check if user is blocked - optimized with caching"""
    # Check cache first
    cache_key = f'user_blocked_{user_id}'
    cached = cache_manager.get(cache_key)
    if cached is not None:
        return cached
    
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f'SELECT blocked FROM users WHERE user_id = {placeholder}', (user_id,))
        result = cursor.fetchone()
        blocked = result and result[0] == 1
        
        # Cache for 1 minute (block status can change)
        cache_manager.set(cache_key, blocked, 60)
        
        return blocked

# ============================================================
# ASYNC WRAPPERS - Non-blocking database operations
# ============================================================

async def add_user_async(user_id, username=None, first_name=None, last_name=None):
    """Async wrapper for add_user - prevents blocking the event loop"""
    return await asyncio.to_thread(add_user, user_id, username, first_name, last_name)

async def get_user_info_async(user_id):
    """Async wrapper for get_user_info"""
    return await asyncio.to_thread(get_user_info, user_id)

async def is_blocked_user_async(user_id):
    """Async wrapper for is_blocked_user"""
    return await asyncio.to_thread(is_blocked_user, user_id)

async def get_comment_count_async(post_id):
    """Async wrapper for get_comment_count"""
    return await asyncio.to_thread(get_comment_count, post_id)

async def get_user_posts_async(user_id, limit=10):
    """Async wrapper for get_user_posts"""
    return await asyncio.to_thread(get_user_posts, user_id, limit)

async def get_post_author_id_async(post_id):
    """Async wrapper for get_post_author_id"""
    return await asyncio.to_thread(get_post_author_id, post_id)

async def get_user_profile_async(user_id):
    """Async wrapper for get_user_profile"""
    return await asyncio.to_thread(get_user_profile, user_id)

async def get_all_users_async():
    """Async wrapper for get_all_users"""
    return await asyncio.to_thread(get_all_users)

async def update_user_post_async(post_id: int, user_id: int, new_content: str) -> bool:
    """Async wrapper for update_user_post"""
    return await asyncio.to_thread(update_user_post, post_id, user_id, new_content)

async def delete_user_post_async(post_id: int, user_id: int) -> bool:
    """Async wrapper for delete_user_post"""
    return await asyncio.to_thread(delete_user_post, post_id, user_id)

def get_user_posts(user_id, limit=10):
    """Get user's posts with status, comment count, and media information"""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        # Optimized query using a subquery for comment count to avoid large GROUP BY
        if db_conn.use_postgresql:
            cursor.execute(f'''
                SELECT p.post_id, p.content, p.category, p.timestamp, p.approved,
                       COALESCE(cc.comment_count, 0) as comment_count, p.post_number,
                       p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                       p.media_file_size, p.media_mime_type, p.media_duration, 
                       p.media_width, p.media_height, p.media_thumbnail_file_id
                FROM posts p
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) as comment_count
                    FROM comments c
                    WHERE c.post_id = p.post_id
                ) cc ON true
                WHERE p.user_id = {placeholder}
                ORDER BY p.timestamp DESC
                LIMIT {placeholder}
            ''', (user_id, limit))
        else:
            # SQLite version - use simple subquery
            cursor.execute(f'''
                SELECT p.post_id, p.content, p.category, p.timestamp, p.approved,
                       (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.post_id) as comment_count, 
                       p.post_number,
                       p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                       p.media_file_size, p.media_mime_type, p.media_duration, 
                       p.media_width, p.media_height, p.media_thumbnail_file_id
                FROM posts p
                WHERE p.user_id = {placeholder}
                ORDER BY p.timestamp DESC
                LIMIT {placeholder}
            ''', (user_id, limit))
        
        return cursor.fetchall()
        
def get_post_author_id(post_id):
    """Get the user_id of the post author"""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f'SELECT user_id FROM posts WHERE post_id = {placeholder}', (post_id,))
        result = cursor.fetchone()
        return result[0] if result else None

def update_user_post(post_id: int, user_id: int, new_content: str) -> bool:
    """Update a user's post content. Keeps approved status but marks as edited for re-review."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        # First check current state
        cursor.execute(f'SELECT approved, is_edited FROM posts WHERE post_id = {placeholder}', (post_id,))
        current_state = cursor.fetchone()
        logging.info(f"Before update: post_id={post_id}, approved={current_state[0] if current_state else 'N/A'}, is_edited={current_state[1] if current_state else 'N/A'}")
        
        # Update content and mark as edited (keep approved=1 to show it was previously approved)
        cursor.execute(f'''
            UPDATE posts 
            SET content = {placeholder}, 
                is_edited = 1,
                edited_timestamp = CURRENT_TIMESTAMP,
                timestamp = CURRENT_TIMESTAMP
            WHERE post_id = {placeholder} AND user_id = {placeholder}
        ''', (new_content, post_id, user_id))
        
        rows_affected = cursor.rowcount
        
        # Verify the update
        cursor.execute(f'SELECT approved, is_edited FROM posts WHERE post_id = {placeholder}', (post_id,))
        new_state = cursor.fetchone()
        logging.info(f"After update: post_id={post_id}, approved={new_state[0] if new_state else 'N/A'}, is_edited={new_state[1] if new_state else 'N/A'}")
        
        conn.commit()
        return rows_affected > 0

def delete_user_post(post_id: int, user_id: int) -> bool:
    """Delete a user's post (only if user is the author)"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        # Delete the post only if user is the author
        cursor.execute(f'''
            DELETE FROM posts 
            WHERE post_id = {placeholder} AND user_id = {placeholder}
        ''', (post_id, user_id))
        
        conn.commit()
        return cursor.rowcount > 0


def set_post_sensitive(post_id: int, is_sensitive: bool = True) -> bool:
    """Mark a post as sensitive/explicit (is_sensitive = 1) or clear the flag."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        value = 1 if is_sensitive else 0
        cursor.execute(
            f'UPDATE posts SET is_sensitive = {placeholder} WHERE post_id = {placeholder}',
            (value, post_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def is_post_sensitive(post_id: int) -> bool:
    """Return True if the given post is marked as sensitive/explicit."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        try:
            cursor.execute(
                f'SELECT is_sensitive FROM posts WHERE post_id = {placeholder}',
                (post_id,),
            )
            result = cursor.fetchone()
            return bool(result and result[0] == 1)
        except Exception:
            # Column might not exist on very old DBs; treat as not sensitive
            return False

def is_post_edited(post_id: int) -> bool:
    """Return True if the post has been edited by the user."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        try:
            cursor.execute(
                f'SELECT is_edited FROM posts WHERE post_id = {placeholder}',
                (post_id,),
            )
            result = cursor.fetchone()
            logging.info(f"is_post_edited check: post_id={post_id}, is_edited={result[0] if result else 'N/A'}")
            return bool(result and result[0] == 1)
        except Exception as e:
            # Column might not exist yet; treat as not edited
            logging.warning(f"Failed to check is_edited for post {post_id}: {e}")
            return False

def clear_edited_flag(post_id: int) -> bool:
    """Clear the edited flag after approval (post is no longer pending edit)."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'UPDATE posts SET is_edited = 0, edited_timestamp = NULL WHERE post_id = {placeholder}',
            (post_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

def search_user_by_id(user_id):
    """Search for a user by their exact user ID"""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f'''
            SELECT user_id, username, first_name, last_name, join_date, 
                   questions_asked, comments_posted, blocked
            FROM users WHERE user_id = {placeholder}
        ''', (user_id,))
        result = cursor.fetchone()
        return [result] if result else []

def search_users_by_name(search_term, limit=10):
    """Search for users by username, first name, or last name (case-insensitive partial match)"""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        # Use ILIKE for PostgreSQL (case-insensitive) or LIKE with LOWER for SQLite
        if db_conn.use_postgresql:
            search_pattern = f'%{search_term}%'
            cursor.execute(f'''
                SELECT user_id, username, first_name, last_name, join_date, 
                       questions_asked, comments_posted, blocked
                FROM users 
                WHERE username ILIKE {placeholder} 
                   OR first_name ILIKE {placeholder} 
                   OR last_name ILIKE {placeholder}
                ORDER BY join_date DESC
                LIMIT {placeholder}
            ''', (search_pattern, search_pattern, search_pattern, limit))
        else:
            search_pattern = f'%{search_term.lower()}%'
            cursor.execute(f'''
                SELECT user_id, username, first_name, last_name, join_date, 
                       questions_asked, comments_posted, blocked
                FROM users 
                WHERE LOWER(username) LIKE {placeholder} 
                   OR LOWER(first_name) LIKE {placeholder} 
                   OR LOWER(last_name) LIKE {placeholder}
                ORDER BY join_date DESC
                LIMIT {placeholder}
            ''', (search_pattern, search_pattern, search_pattern, limit))
        
        return cursor.fetchall()

def get_recent_users(limit=10):
    """Get recently joined users"""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f'''
            SELECT user_id, username, first_name, last_name, join_date, 
                   questions_asked, comments_posted, blocked
            FROM users 
            ORDER BY join_date DESC
            LIMIT {placeholder}
        ''', (limit,))
        return cursor.fetchall()

def get_active_users(limit=10):
    """Get users with recent activity (posts or comments)"""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        if db_conn.use_postgresql:
            cursor.execute(f'''
                SELECT DISTINCT u.user_id, u.username, u.first_name, u.last_name, u.join_date, 
                       u.questions_asked, u.comments_posted, u.blocked
                FROM users u
                LEFT JOIN posts p ON u.user_id = p.user_id
                LEFT JOIN comments c ON u.user_id = c.user_id
                WHERE (p.timestamp >= NOW() - INTERVAL '7 days' OR c.timestamp >= NOW() - INTERVAL '7 days')
                   OR (u.questions_asked > 0 OR u.comments_posted > 0)
                ORDER BY GREATEST(COALESCE(MAX(p.timestamp), '1970-01-01'::timestamp), COALESCE(MAX(c.timestamp), '1970-01-01'::timestamp)) DESC
                LIMIT {placeholder}
            ''', (limit,))
        else:
            cursor.execute(f'''
                SELECT DISTINCT u.user_id, u.username, u.first_name, u.last_name, u.join_date, 
                       u.questions_asked, u.comments_posted, u.blocked
                FROM users u
                LEFT JOIN posts p ON u.user_id = p.user_id
                LEFT JOIN comments c ON u.user_id = c.user_id
                WHERE (p.timestamp >= datetime('now', '-7 days') OR c.timestamp >= datetime('now', '-7 days'))
                   OR (u.questions_asked > 0 OR u.comments_posted > 0)
                ORDER BY MAX(COALESCE(p.timestamp, '1970-01-01'), COALESCE(c.timestamp, '1970-01-01')) DESC
                LIMIT {placeholder}
            ''', (limit,))
        return cursor.fetchall()

def block_user(user_id):
    """Block a user"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f'UPDATE users SET blocked = 1 WHERE user_id = {placeholder}', (user_id,))
        conn.commit()
        return cursor.rowcount > 0

def unblock_user(user_id):
    """Unblock a user"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f'UPDATE users SET blocked = 0 WHERE user_id = {placeholder}', (user_id,))
        conn.commit()
        return cursor.rowcount > 0

# ---------------------------------------------------------------------------
# Profile system helpers
# ---------------------------------------------------------------------------


PROFILE_CACHE_TTL = 60


def invalidate_user_profile_cache(user_id) -> None:
    """Drop cached profile data for a user."""
    cache_manager.delete(f'user_profile_{user_id}')


def get_user_profile(user_id):
    """Return user's profile as a dict or None if not set."""
    cache_key = f'user_profile_{user_id}'
    cached = cache_manager.get(cache_key)
    if cached is not None:
        return cached if cached != 'none' else None

    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'''SELECT user_id, display_name, emoji, bio, is_active, gender, age, 
                       department, year, religion, relationship_status, other_info, accepting_contacts
                FROM user_profiles WHERE user_id = {placeholder}''',
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            cache_manager.set(cache_key, 'none', PROFILE_CACHE_TTL)
            return None
        profile = {
            'user_id': row[0],
            'display_name': row[1],
            'emoji': row[2],
            'bio': row[3] or '',
            'is_active': bool(row[4]),
            'gender': row[5] or '',
            'age': row[6],
            'department': row[7] or '',
            'year': row[8] or '',
            'religion': row[9] or '',
            'relationship_status': row[10] or '',
            'other_info': row[11] or '',
            'accepting_contacts': bool(row[12]) if row[12] is not None else True,
        }
        cache_manager.set(cache_key, profile, PROFILE_CACHE_TTL)
        return profile


def delete_user_profile(user_id: int) -> bool:
    """Permanently delete a user's profile. Returns True if a row was removed."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'DELETE FROM user_profiles WHERE user_id = {placeholder}',
            (user_id,),
        )
        conn.commit()
        invalidate_user_profile_cache(user_id)
        return cursor.rowcount > 0


def upsert_user_profile(user_id, display_name, emoji, bio, is_active=True, gender='', age=None, 
                        department='', year='', religion='', relationship_status='', other_info=''):
    """Create or update a user's profile."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        active_value = 1 if is_active else 0

        if db_conn.use_postgresql:
            cursor.execute(
                f'''
                INSERT INTO user_profiles (user_id, display_name, emoji, bio, is_active, gender, age,
                                           department, year, religion, relationship_status, other_info,
                                           created_at, updated_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder}, NOW(), NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    emoji = EXCLUDED.emoji,
                    bio = EXCLUDED.bio,
                    is_active = EXCLUDED.is_active,
                    gender = EXCLUDED.gender,
                    age = EXCLUDED.age,
                    department = EXCLUDED.department,
                    year = EXCLUDED.year,
                    religion = EXCLUDED.religion,
                    relationship_status = EXCLUDED.relationship_status,
                    other_info = EXCLUDED.other_info,
                    updated_at = NOW()
                ''',
                (user_id, display_name, emoji, bio, is_active, gender, age, department, year,
                 religion, relationship_status, other_info),
            )
        else:
            cursor.execute(
                f'''
                INSERT OR REPLACE INTO user_profiles
                    (user_id, display_name, emoji, bio, is_active, gender, age, department, year,
                     religion, relationship_status, other_info, created_at, updated_at)
                VALUES (
                    {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                    {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder},
                    {placeholder}, {placeholder},
                    COALESCE((SELECT created_at FROM user_profiles WHERE user_id = {placeholder}), CURRENT_TIMESTAMP),
                    CURRENT_TIMESTAMP
                )
                ''',
                (user_id, display_name, emoji, bio, active_value, gender, age, department, year,
                 religion, relationship_status, other_info, user_id),
            )
        conn.commit()
        invalidate_user_profile_cache(user_id)
        return True


def set_profile_visibility(user_id, is_active: bool) -> bool:
    """Enable or disable visibility of a user's profile.

    For PostgreSQL we must use a proper boolean, for SQLite we continue
    to use integer 0/1 for compatibility with the existing schema.
    """
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()

        if db_conn.use_postgresql:
            # Use a real boolean in Postgres
            value = bool(is_active)
            cursor.execute(
                f'UPDATE user_profiles SET is_active = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE user_id = {placeholder}',
                (value, user_id),
            )
        else:
            # SQLite continues to store 0/1
            value = 1 if is_active else 0
            cursor.execute(
                f'UPDATE user_profiles SET is_active = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE user_id = {placeholder}',
                (value, user_id),
            )

        conn.commit()
        invalidate_user_profile_cache(user_id)
        return cursor.rowcount > 0


def set_profile_accepting_contacts(user_id, accepting: bool) -> bool:
    """Enable or disable accepting contact requests for a user's profile.

    For PostgreSQL we use a proper boolean, for SQLite we use integer 0/1.
    """
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()

        if db_conn.use_postgresql:
            value = bool(accepting)
            cursor.execute(
                f'UPDATE user_profiles SET accepting_contacts = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE user_id = {placeholder}',
                (value, user_id),
            )
        else:
            value = 1 if accepting else 0
            cursor.execute(
                f'UPDATE user_profiles SET accepting_contacts = {placeholder}, updated_at = CURRENT_TIMESTAMP WHERE user_id = {placeholder}',
                (value, user_id),
            )

        conn.commit()
        invalidate_user_profile_cache(user_id)
        return cursor.rowcount > 0


def _normalize_pair(a: int, b: int):
    """Return a stable ordering of a pair of user IDs for contacts."""
    return (a, b) if a <= b else (b, a)


def get_profile_contact(user1_id: int, user2_id: int):
    """Get existing profile contact between two users, or None."""
    db_conn = get_db_connection()
    a_id, b_id = _normalize_pair(user1_id, user2_id)
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'''SELECT id, user_a_id, user_b_id, status, initiator_id, created_at, last_message_at
                FROM profile_contacts
                WHERE user_a_id = {placeholder} AND user_b_id = {placeholder}''',
            (a_id, b_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            'id': row[0],
            'user_a_id': row[1],
            'user_b_id': row[2],
            'status': row[3],
            'initiator_id': row[4],
            'created_at': row[5],
            'last_message_at': row[6],
        }


def create_profile_contact(user1_id: int, user2_id: int, initiator_id: int, status: str = 'pending') -> int:
    """Create a new profile contact between two users and return its ID."""
    db_conn = get_db_connection()
    a_id, b_id = _normalize_pair(user1_id, user2_id)
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()

        if db_conn.use_postgresql:
            cursor.execute(
                f'''
                INSERT INTO profile_contacts (user_a_id, user_b_id, status, initiator_id, created_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, NOW())
                ON CONFLICT (user_a_id, user_b_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    initiator_id = EXCLUDED.initiator_id,
                    created_at = NOW()
                RETURNING id
                ''',
                (a_id, b_id, status, initiator_id),
            )
            contact_id = cursor.fetchone()[0]
        else:
            cursor.execute(
                f'''
                INSERT OR REPLACE INTO profile_contacts
                    (id, user_a_id, user_b_id, status, initiator_id, created_at)
                VALUES (
                    COALESCE((SELECT id FROM profile_contacts WHERE user_a_id = {placeholder} AND user_b_id = {placeholder}), NULL),
                    {placeholder}, {placeholder}, {placeholder}, {placeholder}, CURRENT_TIMESTAMP
                )
                ''',
                (a_id, b_id, a_id, b_id, status, initiator_id),
            )
            contact_id = cursor.lastrowid
        conn.commit()
        return contact_id


def update_profile_contact_status(contact_id: int, status: str) -> bool:
    """Update the status of a profile contact."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        if db_conn.use_postgresql:
            cursor.execute(
                f'UPDATE profile_contacts SET status = {placeholder}, last_message_at = NOW() WHERE id = {placeholder}',
                (status, contact_id),
            )
        else:
            cursor.execute(
                f'UPDATE profile_contacts SET status = {placeholder}, last_message_at = CURRENT_TIMESTAMP WHERE id = {placeholder}',
                (status, contact_id),
            )
        conn.commit()
        return cursor.rowcount > 0


def touch_profile_contact(contact_id: int) -> None:
    """Update last_message_at for a profile contact."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        if db_conn.use_postgresql:
            cursor.execute(
                f'UPDATE profile_contacts SET last_message_at = NOW() WHERE id = {placeholder}',
                (contact_id,),
            )
        else:
            cursor.execute(
                f'UPDATE profile_contacts SET last_message_at = CURRENT_TIMESTAMP WHERE id = {placeholder}',
                (contact_id,),
            )
        conn.commit()


# ============================================================
# ASYNC OPTIMIZED DATABASE FUNCTIONS (Non-blocking)
# ============================================================

async def async_add_user(user_id, username=None, first_name=None, last_name=None):
    """Async version of add_user - non-blocking"""
    return await make_async(add_user)(user_id, username, first_name, last_name)

async def async_is_blocked_user(user_id):
    """Async version of is_blocked_user - non-blocking"""
    return await make_async(is_blocked_user)(user_id)

async def async_get_user_info(user_id):
    """Async version of get_user_info - non-blocking"""
    return await make_async(get_user_info)(user_id)

async def async_get_user_posts_count(user_id):
    """Async version of get_user_posts_count - non-blocking"""
    return await make_async(get_user_posts_count)(user_id)

async def async_get_user_comments_count(user_id):
    """Async version of get_user_comments_count - non-blocking"""
    return await make_async(get_user_comments_count)(user_id)

async def async_get_post_by_id(post_id):
    """Async version of get_post_by_id - non-blocking"""
    return await make_async(get_post_by_id)(post_id)

async def async_get_comments_for_post(post_id, include_pending=False):
    """Async version of get_comments_for_post - non-blocking"""
    return await make_async(get_comments_for_post)(post_id, include_pending)

async def async_get_comment_count(post_id):
    """Async version of get_comment_count - non-blocking"""
    return await make_async(get_comment_count)(post_id)

async def async_get_post_like_count(post_id):
    """Async version of get_post_like_count - non-blocking"""
    return await make_async(get_post_like_count)(post_id)

async def async_has_user_liked_post(user_id, post_id):
    """Async version of has_user_liked_post - non-blocking"""
    return await make_async(has_user_liked_post)(user_id, post_id)

async def async_get_post_likes(post_id):
    """Async version of get_post_likes - non-blocking"""
    return await make_async(get_post_likes)(post_id)

async def async_increment_user_questions(user_id):
    """Async version of increment_user_questions - non-blocking"""
    return await make_async(increment_user_questions)(user_id)

async def async_increment_user_comments(user_id):
    """Async version of increment_user_comments - non-blocking"""
    return await make_async(increment_user_comments)(user_id)

# Export async functions
__all__ = [
    # ... existing exports ...
    'async_add_user',
    'async_is_blocked_user',
    'async_get_user_info',
    'async_get_user_posts_count',
    'async_get_user_comments_count',
    'async_get_post_by_id',
    'async_get_comments_for_post',
    'async_get_comment_count',
    'async_get_post_like_count',
    'async_has_user_liked_post',
    'async_get_post_likes',
    'async_increment_user_questions',
    'async_increment_user_comments',
]

def block_profile_user(blocker_id: int, blocked_id: int) -> bool:
    """Block another profile user (one-way)."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        if db_conn.use_postgresql:
            cursor.execute(
                f'''
                INSERT INTO profile_blocks (blocker_id, blocked_id, created_at)
                VALUES ({placeholder}, {placeholder}, NOW())
                ON CONFLICT (blocker_id, blocked_id) DO NOTHING
                ''',
                (blocker_id, blocked_id),
            )
        else:
            cursor.execute(
                f'''
                INSERT OR IGNORE INTO profile_blocks (blocker_id, blocked_id, created_at)
                VALUES ({placeholder}, {placeholder}, CURRENT_TIMESTAMP)
                ''',
                (blocker_id, blocked_id),
            )
        conn.commit()
        return True


def is_profile_blocked(blocker_id: int, other_id: int) -> bool:
    """Return True if blocker_id has blocked other_id."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'''SELECT 1 FROM profile_blocks
                WHERE blocker_id = {placeholder} AND blocked_id = {placeholder}
                LIMIT 1''',
            (blocker_id, other_id),
        )
        return cursor.fetchone() is not None


def is_profile_blocked_either_way(user1_id: int, user2_id: int) -> bool:
    """Return True if either user has blocked the other."""
    return is_profile_blocked(user1_id, user2_id) or is_profile_blocked(user2_id, user1_id)


def unblock_profile_user(blocker_id: int, blocked_id: int) -> bool:
    """Unblock a previously blocked user."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'''DELETE FROM profile_blocks
                WHERE blocker_id = {placeholder} AND blocked_id = {placeholder}''',
            (blocker_id, blocked_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_blocked_users(blocker_id: int):
    """Get list of all users blocked by this user."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'''SELECT blocked_id, created_at
                FROM profile_blocks
                WHERE blocker_id = {placeholder}
                ORDER BY created_at DESC''',
            (blocker_id,),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                'blocked_id': row[0],
                'created_at': row[1],
            })
        return result


def get_profile_contact_by_id(contact_id: int):
    """Get a profile contact row by its ID, or None if not found."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'''SELECT id, user_a_id, user_b_id, status, initiator_id, created_at, last_message_at
                FROM profile_contacts
                WHERE id = {placeholder}''',
            (contact_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            'id': row[0],
            'user_a_id': row[1],
            'user_b_id': row[2],
            'status': row[3],
            'initiator_id': row[4],
            'created_at': row[5],
            'last_message_at': row[6],
        }


def get_user_profile_stats(user_id: int):
    """Return simple stats for a profile: number of confessions and comments."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()

        # Approved confessions and comments (replies included) in one round trip
        cursor.execute(
            f'''SELECT
                    (SELECT COUNT(*) FROM posts WHERE user_id = {placeholder} AND approved = 1),
                    (SELECT COUNT(*) FROM comments WHERE user_id = {placeholder})''',
            (user_id, user_id),
        )
        row = cursor.fetchone()

        return {
            'confessions': row[0] if row else 0,
            'comments': row[1] if row else 0,
        }


def get_user_active_chats(user_id: int):
    """Get all active profile chats for a user."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'''SELECT id, user_a_id, user_b_id, status, initiator_id, created_at, last_message_at
                FROM profile_contacts
                WHERE (user_a_id = {placeholder} OR user_b_id = {placeholder})
                AND status = 'active'
                ORDER BY last_message_at DESC NULLS LAST''',
            (user_id, user_id),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'user_a_id': row[1],
                'user_b_id': row[2],
                'status': row[3],
                'initiator_id': row[4],
                'created_at': row[5],
                'last_message_at': row[6],
            })
        return result


def get_user_pending_requests(user_id: int):
    """Get all pending incoming contact requests for a user (where user is NOT the initiator)."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f'''SELECT id, user_a_id, user_b_id, status, initiator_id, created_at, last_message_at
                FROM profile_contacts
                WHERE (user_a_id = {placeholder} OR user_b_id = {placeholder})
                AND status = 'pending'
                AND initiator_id != {placeholder}
                ORDER BY created_at DESC''',
            (user_id, user_id, user_id),
        )
        rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'user_a_id': row[1],
                'user_b_id': row[2],
                'status': row[3],
                'initiator_id': row[4],
                'created_at': row[5],
                'last_message_at': row[6],
            })
        return result

def get_user_daily_message_count(user_id: int) -> int:
    """Get the number of messages sent by a user today."""
    db_conn = get_db_connection()
    with db_conn.get_connection(readonly=True) as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        if db_conn.use_postgresql:
            cursor.execute(
                f'''SELECT message_count 
                    FROM profile_message_counts 
                    WHERE user_id = {placeholder} 
                    AND message_date = CURRENT_DATE''',
                (user_id,)
            )
        else:
            cursor.execute(
                f'''SELECT message_count 
                    FROM profile_message_counts 
                    WHERE user_id = {placeholder} 
                    AND message_date = DATE('now')''',
                (user_id,)
            )
        
        row = cursor.fetchone()
        return row[0] if row else 0


def increment_user_daily_message_count(user_id: int) -> None:
    """Increment the daily message count for a user."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        if db_conn.use_postgresql:
            cursor.execute(
                f'''INSERT INTO profile_message_counts (user_id, message_date, message_count)
                    VALUES ({placeholder}, CURRENT_DATE, 1)
                    ON CONFLICT (user_id, message_date) 
                    DO UPDATE SET message_count = profile_message_counts.message_count + 1''',
                (user_id,)
            )
        else:
            # For SQLite, we need to handle the insert or update manually
            cursor.execute(
                f'''SELECT message_count 
                    FROM profile_message_counts 
                    WHERE user_id = {placeholder} 
                    AND message_date = DATE('now')''',
                (user_id,)
            )
            
            row = cursor.fetchone()
            if row:
                # Update existing count
                cursor.execute(
                    f'''UPDATE profile_message_counts 
                        SET message_count = message_count + 1
                        WHERE user_id = {placeholder} 
                        AND message_date = DATE('now')''',
                    (user_id,)
                )
            else:
                # Insert new count
                cursor.execute(
                    f'''INSERT INTO profile_message_counts (user_id, message_date, message_count)
                        VALUES ({placeholder}, DATE('now'), 1)''',
                    (user_id,)
                )
        
        conn.commit()

