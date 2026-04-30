import logging
from typing import List, Dict
from db_connection import get_db_connection, execute_query, adapt_query

logger = logging.getLogger(__name__)

class Migration:
    """Database migration system for both SQLite and PostgreSQL"""
    
    def __init__(self):
        self.db_conn = get_db_connection()
        self.placeholder = self.db_conn.get_placeholder()
    
    def run_migrations(self):
        """Run all necessary migrations"""
        try:
            logger.info("Starting database migrations...")
            
            # Create migrations table if it doesn't exist
            self._create_migrations_table()
            
            # Get completed migrations
            completed_migrations = self._get_completed_migrations()
            logger.info(f"Completed migrations: {completed_migrations}")
            
            # Define all migrations
            migrations = [
                {
                    'id': '001_initial_schema',
                    'description': 'Create initial database schema',
                    'function': self._migration_001_initial_schema
                },
                {
                    'id': '002_add_media_support',
                    'description': 'Add media support columns to posts table',
                    'function': self._migration_002_add_media_support
                },
                {
                    'id': '003_add_post_analytics',
                    'description': 'Add analytics columns to posts table',
                    'function': self._migration_003_add_post_analytics
                },
                {
                    'id': '004_update_constraints',
                    'description': 'Update database constraints for PostgreSQL',
                    'function': self._migration_004_update_constraints
                }
            ]
            
            # Run pending migrations
            for migration in migrations:
                if migration['id'] not in completed_migrations:
                    logger.info(f"Running migration: {migration['id']} - {migration['description']}")
                    migration['function']()
                    self._mark_migration_completed(migration['id'], migration['description'])
                    logger.info(f"Completed migration: {migration['id']}")
            
            logger.info("All migrations completed successfully")
            
        except Exception as e:
            logger.error(f"Migration error: {e}")
            raise
    
    def _create_migrations_table(self):
        """Create the migrations tracking table"""
        query = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id VARCHAR(255) PRIMARY KEY,
            description TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        if self.db_conn.use_postgresql:
            query = query.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
        
        execute_query(query)
        logger.info("Migrations table created/verified")
    
    def _get_completed_migrations(self) -> List[str]:
        """Get list of completed migration IDs"""
        try:
            query = "SELECT migration_id FROM schema_migrations"
            results = execute_query(query, fetch='all')
            return [row[0] if isinstance(row, tuple) else row['migration_id'] for row in (results or [])]
        except Exception as e:
            logger.info(f"No migrations table found or empty: {e}")
            return []
    
    def _mark_migration_completed(self, migration_id: str, description: str):
        """Mark a migration as completed"""
        query = f"INSERT INTO schema_migrations (migration_id, description) VALUES ({self.placeholder}, {self.placeholder})"
        execute_query(query, (migration_id, description))
    
    def _migration_001_initial_schema(self):
        """Migration 001: Create initial database schema"""
        
        # Users table
        users_query = """
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            first_name VARCHAR(255),
            last_name VARCHAR(255),
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            questions_asked INTEGER DEFAULT 0,
            comments_posted INTEGER DEFAULT 0,
            blocked INTEGER DEFAULT 0
        )
        """
        
        if self.db_conn.use_postgresql:
            users_query = users_query.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
        
        execute_query(users_query)
        
        # Posts table
        posts_query = """
        CREATE TABLE IF NOT EXISTS posts (
            post_id SERIAL PRIMARY KEY,
            content TEXT NOT NULL,
            category VARCHAR(255) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id BIGINT NOT NULL,
            approved INTEGER DEFAULT NULL,
            channel_message_id BIGINT,
            flagged INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            post_number INTEGER DEFAULT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
        
        if self.db_conn.use_postgresql:
            posts_query = posts_query.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
        else:
            posts_query = posts_query.replace("SERIAL", "INTEGER PRIMARY KEY AUTOINCREMENT")
        
        execute_query(posts_query)
        
        # Comments table
        comments_query = """
        CREATE TABLE IF NOT EXISTS comments (
            comment_id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL,
            user_id BIGINT NOT NULL,
            content TEXT NOT NULL,
            parent_comment_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            likes INTEGER DEFAULT 0,
            dislikes INTEGER DEFAULT 0,
            flagged INTEGER DEFAULT 0,
            FOREIGN KEY(post_id) REFERENCES posts(post_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(parent_comment_id) REFERENCES comments(comment_id)
        )
        """
        
        if self.db_conn.use_postgresql:
            comments_query = comments_query.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
        else:
            comments_query = comments_query.replace("SERIAL", "INTEGER PRIMARY KEY AUTOINCREMENT")
        
        execute_query(comments_query)
        
        # Reactions table
        reactions_query = """
        CREATE TABLE IF NOT EXISTS reactions (
            reaction_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            target_type VARCHAR(50) NOT NULL,
            target_id INTEGER NOT NULL,
            reaction_type VARCHAR(50) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, target_type, target_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
        
        if self.db_conn.use_postgresql:
            reactions_query = reactions_query.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
        else:
            reactions_query = reactions_query.replace("SERIAL", "INTEGER PRIMARY KEY AUTOINCREMENT")
        
        execute_query(reactions_query)
        
        # Reports table
        reports_query = """
        CREATE TABLE IF NOT EXISTS reports (
            report_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            target_type VARCHAR(50) NOT NULL,
            target_id INTEGER NOT NULL,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
        
        if self.db_conn.use_postgresql:
            reports_query = reports_query.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
        else:
            reports_query = reports_query.replace("SERIAL", "INTEGER PRIMARY KEY AUTOINCREMENT")
        
        execute_query(reports_query)
        
        # Admin messages table
        admin_messages_query = """
        CREATE TABLE IF NOT EXISTS admin_messages (
            message_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            admin_id BIGINT,
            user_message TEXT,
            admin_reply TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            replied INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
        """
        
        if self.db_conn.use_postgresql:
            admin_messages_query = admin_messages_query.replace("TIMESTAMP DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT NOW()")
        else:
            admin_messages_query = admin_messages_query.replace("SERIAL", "INTEGER PRIMARY KEY AUTOINCREMENT")
        
        execute_query(admin_messages_query)
        
        logger.info("Initial schema created")
    
    def _migration_002_add_media_support(self):
        """Migration 002: Add media support columns"""
        
        media_columns = [
            ("media_type", "VARCHAR(50)"),
            ("media_file_id", "TEXT"),
            ("media_file_unique_id", "TEXT"),
            ("media_caption", "TEXT"),
            ("media_file_size", "BIGINT"),
            ("media_mime_type", "VARCHAR(255)"),
            ("media_duration", "INTEGER"),
            ("media_width", "INTEGER"),
            ("media_height", "INTEGER"),
            ("media_thumbnail_file_id", "TEXT")
        ]
        
        for column_name, column_type in media_columns:
            try:
                query = f"ALTER TABLE posts ADD COLUMN {column_name} {column_type}"
                execute_query(query)
                logger.info(f"Added column {column_name} to posts table")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    logger.info(f"Column {column_name} already exists, skipping")
                else:
                    logger.warning(f"Could not add column {column_name}: {e}")
    
    def _migration_003_add_post_analytics(self):
        """Migration 003: Add analytics columns to posts"""
        
        analytics_columns = [
            ("status", "VARCHAR(50) DEFAULT 'pending'"),
            ("sentiment_score", "REAL DEFAULT 0.0"),
            ("profanity_detected", "INTEGER DEFAULT 0"),
            ("spam_score", "REAL DEFAULT 0.0")
        ]
        
        if self.db_conn.use_postgresql:
            analytics_columns = [(name, col_type.replace("REAL", "DECIMAL(5,2)")) 
                                for name, col_type in analytics_columns]
        
        for column_name, column_type in analytics_columns:
            try:
                query = f"ALTER TABLE posts ADD COLUMN {column_name} {column_type}"
                execute_query(query)
                logger.info(f"Added analytics column {column_name} to posts table")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    logger.info(f"Column {column_name} already exists, skipping")
                else:
                    logger.warning(f"Could not add analytics column {column_name}: {e}")
    
    def _migration_004_update_constraints(self):
        """Migration 004: Update database constraints for PostgreSQL"""
        
        if not self.db_conn.use_postgresql:
            logger.info("Skipping PostgreSQL-specific constraints for SQLite")
            return
        
        # Add indexes for better performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_posts_approved ON posts(approved)",
            "CREATE INDEX IF NOT EXISTS idx_posts_timestamp ON posts(timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id)",
            "CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_reactions_target ON reactions(target_type, target_id)",
            "CREATE INDEX IF NOT EXISTS idx_reactions_user ON reactions(user_id)",
        ]
        
        for index_query in indexes:
            try:
                execute_query(index_query)
                logger.info(f"Created index: {index_query}")
            except Exception as e:
                logger.warning(f"Could not create index: {e}")

def run_database_migrations():
    """Run all database migrations"""
    migration = Migration()
    migration.run_migrations()

if __name__ == "__main__":
    run_database_migrations()
