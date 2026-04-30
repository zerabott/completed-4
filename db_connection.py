import os
import logging
import sqlite3
import time
import asyncio
from typing import Any, Dict, List, Optional, Tuple, Union
from contextlib import contextmanager
from functools import lru_cache, wraps

try:
    import psycopg2
    import psycopg2.extras
    from psycopg2.pool import SimpleConnectionPool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None

from config import (
    DATABASE_URL, USE_POSTGRESQL, DB_PATH,
    PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD
)

logger = logging.getLogger(__name__)

# Global cache for frequently accessed data
_global_cache = {}
_cache_ttl = 300  # 5 minutes default TTL

class CacheManager:
    """Simple cache manager with TTL support"""
    
    @staticmethod
    def get(key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key in _global_cache:
            value, expiry_time = _global_cache[key]
            if time.time() < expiry_time:
                return value
            else:
                del _global_cache[key]
        return None
    
    @staticmethod
    def set(key: str, value: Any, ttl: int = _cache_ttl):
        """Set value in cache with TTL"""
        _global_cache[key] = (value, time.time() + ttl)
    
    @staticmethod
    def delete(key: str):
        """Delete value from cache"""
        _global_cache.pop(key, None)
    
    @staticmethod
    def delete_pattern(pattern: str):
        """Delete keys matching pattern (simple prefix matching)"""
        keys_to_delete = [k for k in _global_cache.keys() if k.startswith(pattern)]
        for key in keys_to_delete:
            del _global_cache[key]
    
    @staticmethod
    def clear():
        """Clear all cache"""
        _global_cache.clear()
    
    @staticmethod
    def get_stats() -> Dict[str, int]:
        """Get cache statistics"""
        return {
            'cached_items': len(_global_cache),
            'memory_estimate_kb': len(str(_global_cache)) // 1024
        }

# Global cache manager instance
cache_manager = CacheManager()

# Async wrapper utilities for non-blocking database operations
class AsyncDBWrapper:
    """Wrapper to run blocking database operations in thread pool"""
    
    _executor = None
    _initialized = False
    
    @classmethod
    def initialize(cls):
        """Initialize thread pool executor"""
        if not cls._initialized:
            import concurrent.futures
            cls._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=20,  # Optimized for high-concurrency
                thread_name_prefix="db_worker"
            )
            cls._initialized = True
            logger.info("Async DB wrapper initialized with 20 worker threads")
    
    @classmethod
    async def run_sync(cls, func, *args, **kwargs):
        """Run synchronous database function in thread pool"""
        if not cls._initialized:
            cls.initialize()
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(cls._executor, func, *args, **kwargs)

# Decorator to make synchronous database functions async
def make_async(func):
    """Decorator to convert synchronous DB function to async"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await AsyncDBWrapper.run_sync(func, *args, **kwargs)
    return wrapper

# Decorator for caching database queries
def cached_query(cache_key: str, ttl: int = _cache_ttl):
    """Decorator to cache database query results with TTL"""
    def decorator(func):
        from functools import wraps
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key = f"{cache_key}_{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Try to get from cache
            cached_result = cache_manager.get(key)
            if cached_result is not None:
                return cached_result
            
            # Execute query and cache result
            result = func(*args, **kwargs)
            cache_manager.set(key, result, ttl)
            return result
        
        return wrapper
    return decorator

class DatabaseConnection:
    """Database connection manager supporting both SQLite and PostgreSQL with connection pooling"""
    
    def __init__(self):
        self.use_postgresql = USE_POSTGRESQL or DATABASE_URL is not None
        self.connection_pool = None
        self._sqlite_pool = None  # SQLite connection pool
        
        if self.use_postgresql:
            if not PSYCOPG2_AVAILABLE:
                logger.error("PostgreSQL requested but psycopg2 not available. Falling back to SQLite.")
                self.use_postgresql = False
            else:
                self._init_postgresql()
        
        if not self.use_postgresql:
            self._init_sqlite()
    
    def _init_postgresql(self):
        """Initialize PostgreSQL connection pool with optimized settings"""
        try:
            if DATABASE_URL:
                # Parse DATABASE_URL for Render deployment
                connection_string = DATABASE_URL
            else:
                # Build connection string from individual components
                connection_string = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
            
            # Create connection pool with optimized settings for better performance
            self.connection_pool = SimpleConnectionPool(
                minconn=5,      # Minimum connections (increased from 2)
                maxconn=50,     # Maximum connections (increased from 30)
                dsn=connection_string,
                connect_timeout=10  # Connection timeout
            )
            
            # Test connection
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    
            logger.info("PostgreSQL connection pool initialized successfully (5-50 connections)")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {e}")
            logger.info("Falling back to SQLite")
            self.use_postgresql = False
            self._init_sqlite()
    
    def _init_sqlite(self):
        """Initialize SQLite with connection pooling and performance optimizations"""
        self.db_path = DB_PATH
        logger.info(f"Using SQLite database with connection pooling: {self.db_path}")
        
        # Initialize SQLite connection pool
        try:
            from queue import Queue, Empty
            import threading
            
            class SQLiteConnectionPool:
                """Thread-safe SQLite connection pool"""
                def __init__(self, db_path, pool_size=20):
                    self.db_path = db_path
                    self.pool_size = pool_size
                    self._pool = Queue(maxsize=pool_size)
                    self._lock = threading.Lock()
                    self._created_connections = 0
                    
                def get_connection(self):
                    """Get connection from pool or create new one"""
                    try:
                        # Try to get existing connection
                        conn = self._pool.get_nowait()
                        return conn
                    except Empty:
                        # Create new connection if under limit
                        with self._lock:
                            if self._created_connections < self.pool_size:
                                conn = self._create_connection()
                                self._created_connections += 1
                                return conn
                        # Pool exhausted, reuse oldest connection
                        try:
                            return self._pool.get_nowait()
                        except Empty:
                            return self._create_connection()
                
                def return_connection(self, conn):
                    """Return connection to pool"""
                    try:
                        self._pool.put_nowait(conn)
                    except:
                        conn.close()
                
                def _create_connection(self):
                    """Create new SQLite connection with optimizations"""
                    conn = sqlite3.connect(
                        self.db_path,
                        timeout=30.0,
                        check_same_thread=False
                    )
                    # Apply performance optimizations
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA cache_size=10000")  # 10MB cache
                    conn.execute("PRAGMA temp_store=MEMORY")
                    conn.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
                    conn.execute("PRAGMA foreign_keys = ON")
                    return conn
                
                def close_all(self):
                    """Close all connections in pool"""
                    while not self._pool.empty():
                        try:
                            conn = self._pool.get_nowait()
                            conn.close()
                        except:
                            pass
            
            self._sqlite_pool = SQLiteConnectionPool(self.db_path, pool_size=20)
            logger.info("SQLite connection pool initialized (20 connections)")
            
        except Exception as e:
            logger.warning(f"Could not create SQLite connection pool: {e}")
            self._sqlite_pool = None
        
        # Apply SQLite performance optimizations (applied per-connection now)
        logger.info("SQLite performance optimizations configured")
    
    @contextmanager
    def get_connection(self):
        """Get database connection with automatic cleanup from connection pool"""
        if self.use_postgresql:
            conn = None
            try:
                conn = self.connection_pool.getconn()
                yield conn
            finally:
                if conn:
                    self.connection_pool.putconn(conn)
        else:
            # Use SQLite connection pool if available
            if self._sqlite_pool:
                conn = None
                try:
                    conn = self._sqlite_pool.get_connection()
                    yield conn
                finally:
                    if conn:
                        self._sqlite_pool.return_connection(conn)
            else:
                # Fallback to direct connection
                conn = sqlite3.connect(self.db_path)
                conn.execute('PRAGMA foreign_keys = ON')
                try:
                    yield conn
                finally:
                    conn.close()
    
    def execute_query(self, query: str, params: Optional[Tuple] = None, fetch: str = None) -> Optional[List]:
        """
        Execute a query and optionally fetch results
        
        Args:
            query: SQL query to execute
            params: Query parameters
            fetch: 'one', 'all', or None
        
        Returns:
            Query results if fetch is specified, None otherwise
        """
        try:
            with self.get_connection() as conn:
                if self.use_postgresql:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                        cursor.execute(query, params or ())
                        
                        if fetch == 'one':
                            return cursor.fetchone()
                        elif fetch == 'all':
                            return cursor.fetchall()
                        else:
                            conn.commit()
                            return cursor.rowcount
                else:
                    # SQLite
                    cursor = conn.cursor()
                    cursor.execute(query, params or ())
                    
                    if fetch == 'one':
                        return cursor.fetchone()
                    elif fetch == 'all':
                        return cursor.fetchall()
                    else:
                        conn.commit()
                        return cursor.rowcount
                        
        except Exception as e:
            logger.error(f"Database query error: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            raise
    
    def get_placeholder(self) -> str:
        """Get the appropriate parameter placeholder for the database type"""
        return "%s" if self.use_postgresql else "?"
    
    def adapt_query_for_db(self, sqlite_query: str) -> str:
        """
        Adapt SQLite query syntax for PostgreSQL if needed
        
        Args:
            sqlite_query: Original SQLite query
            
        Returns:
            Adapted query for current database type
        """
        if not self.use_postgresql:
            return sqlite_query
        
        # Convert SQLite syntax to PostgreSQL
        query = sqlite_query
        
        # Replace ? placeholders with %s
        placeholder_count = query.count('?')
        for i in range(placeholder_count):
            query = query.replace('?', '%s', 1)
        
        # Handle common SQLite -> PostgreSQL conversions
        replacements = {
            'AUTOINCREMENT': 'SERIAL',
            'INTEGER PRIMARY KEY AUTOINCREMENT': 'SERIAL PRIMARY KEY',
            'CURRENT_TIMESTAMP': 'NOW()',
            'PRAGMA foreign_keys = ON': '',  # Not needed in PostgreSQL
        }
        
        for sqlite_syntax, pg_syntax in replacements.items():
            query = query.replace(sqlite_syntax, pg_syntax)
        
        return query
    
    def close(self):
        """Close database connections"""
        if self.use_postgresql and self.connection_pool:
            self.connection_pool.closeall()
            logger.info("PostgreSQL connection pool closed")
        
        if self._sqlite_pool:
            self._sqlite_pool.close_all()
            logger.info("SQLite connection pool closed")

# Global database connection instance
db_connection = DatabaseConnection()

def get_db_connection():
    """Get the global database connection instance"""
    return db_connection

# Convenience functions for backward compatibility
def get_db():
    """Get database connection (backward compatibility)"""
    return db_connection.get_connection()

def execute_query(query: str, params: Optional[Tuple] = None, fetch: str = None):
    """Execute query using global connection"""
    return db_connection.execute_query(query, params, fetch)

def adapt_query(query: str) -> str:
    """Adapt query for current database type"""
    return db_connection.adapt_query_for_db(query)
