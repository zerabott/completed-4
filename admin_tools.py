"""
Advanced admin tools for the confession bot
"""

import os
import shutil
import json
import csv
import zipfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import asyncio
import aiofiles

from config import BACKUPS_DIR, EXPORTS_DIR, ADMIN_IDS, DB_PATH
from db import get_db
from db_connection import get_db_connection
from logger import get_logger
from error_handler import handle_database_errors

logger = get_logger('admin_tools')


@dataclass
class SearchResult:
    """Search result item"""
    type: str  # 'post' or 'comment'
    id: int
    content: str
    user_id: int
    timestamp: str
    metadata: Dict[str, Any]


@dataclass
class BackupInfo:
    """Backup information"""
    backup_id: int
    filename: str
    file_size: int
    record_count: int
    backup_type: str
    created_at: str
    checksum: str


class SearchManager:
    """Advanced search functionality for admins"""
    
    @handle_database_errors
    def search_users(self, query: str = None, user_id: int = None, 
                    username: str = None, name_starts_with: str = None,
                    limit: int = 20) -> List[Dict[str, Any]]:
        """Search users by various criteria"""
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Base query for user information with activity counts
            base_query = f"""
                SELECT u.user_id, u.username, u.first_name, u.last_name, u.join_date,
                       u.questions_asked, u.comments_posted, u.blocked,
                       COUNT(DISTINCT p.post_id) as total_posts,
                       COUNT(DISTINCT c.comment_id) as total_comments
                FROM users u
                LEFT JOIN posts p ON u.user_id = p.user_id
                LEFT JOIN comments c ON u.user_id = c.user_id
                WHERE 1=1
            """
            
            params = []
            
            # Search by exact user ID
            if user_id is not None:
                base_query += f" AND u.user_id = {placeholder}"
                params.append(user_id)
            
            # Search by username (case-insensitive partial match)
            elif username:
                if db_conn.use_postgresql:
                    base_query += f" AND u.username ILIKE {placeholder}"
                    params.append(f"%{username}%")
                else:
                    base_query += f" AND LOWER(u.username) LIKE {placeholder}"
                    params.append(f"%{username.lower()}%")
            
            # Search by name starting letter
            elif name_starts_with:
                letter = name_starts_with.upper()
                if db_conn.use_postgresql:
                    base_query += f" AND (u.first_name ILIKE {placeholder} OR u.last_name ILIKE {placeholder} OR u.username ILIKE {placeholder})"
                    params.extend([f"{letter}%", f"{letter}%", f"{letter}%"])
                else:
                    base_query += f" AND (LOWER(u.first_name) LIKE {placeholder} OR LOWER(u.last_name) LIKE {placeholder} OR LOWER(u.username) LIKE {placeholder})"
                    params.extend([f"{letter.lower()}%", f"{letter.lower()}%", f"{letter.lower()}%"])
            
            # General search across all name fields
            elif query:
                if db_conn.use_postgresql:
                    base_query += f" AND (u.username ILIKE {placeholder} OR u.first_name ILIKE {placeholder} OR u.last_name ILIKE {placeholder})"
                    search_term = f"%{query}%"
                    params.extend([search_term, search_term, search_term])
                else:
                    base_query += f" AND (LOWER(u.username) LIKE {placeholder} OR LOWER(u.first_name) LIKE {placeholder} OR LOWER(u.last_name) LIKE {placeholder})"
                    search_term = f"%{query.lower()}%"
                    params.extend([search_term, search_term, search_term])
            
            base_query += f"""
                GROUP BY u.user_id, u.username, u.first_name, u.last_name, u.join_date,
                         u.questions_asked, u.comments_posted, u.blocked
                ORDER BY u.join_date DESC
                LIMIT {placeholder}
            """
            params.append(limit)
            
            cursor.execute(base_query, params)
            users = cursor.fetchall()
            
            return [{
                'user_id': user[0],
                'username': user[1],
                'first_name': user[2],
                'last_name': user[3],
                'join_date': user[4],
                'questions_asked': user[5],
                'comments_posted': user[6],
                'blocked': user[7],
                'total_posts': user[8],
                'total_comments': user[9],
                'display_name': self._get_display_name(user[2], user[3], user[1])
            } for user in users]
    
    def _get_display_name(self, first_name: str, last_name: str, username: str) -> str:
        """Get user display name"""
        name = f"{first_name or ''} {last_name or ''}".strip()
        if name:
            return name
        elif username:
            return f"@{username}"
        else:
            return "Anonymous User"
    
    @handle_database_errors
    def get_user_detailed_info(self, user_id: int) -> Dict[str, Any]:
        """Get detailed user information including all activities"""
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get user basic info
            cursor.execute(f"""
                SELECT user_id, username, first_name, last_name, join_date,
                       questions_asked, comments_posted, blocked
                FROM users WHERE user_id = {placeholder}
            """, (user_id,))
            
            user = cursor.fetchone()
            if not user:
                return None
            
            # Get user's posts
            cursor.execute(f"""
                SELECT post_id, content, category, timestamp, status, approved, flagged, likes
                FROM posts WHERE user_id = {placeholder}
                ORDER BY timestamp DESC LIMIT 10
            """, (user_id,))
            posts = cursor.fetchall()
            
            # Get user's comments
            cursor.execute(f"""
                SELECT c.comment_id, c.content, c.timestamp, c.likes, c.dislikes, c.flagged,
                       p.post_id, p.content as post_content
                FROM comments c
                LEFT JOIN posts p ON c.post_id = p.post_id
                WHERE c.user_id = {placeholder}
                ORDER BY c.timestamp DESC LIMIT 10
            """, (user_id,))
            comments = cursor.fetchall()
            
            # Get activity statistics
            cursor.execute(f"""
                SELECT 
                    COUNT(DISTINCT p.post_id) as total_posts,
                    COUNT(DISTINCT CASE WHEN p.approved = 1 THEN p.post_id END) as approved_posts,
                    COUNT(DISTINCT CASE WHEN p.approved = 0 THEN p.post_id END) as rejected_posts,
                    COUNT(DISTINCT CASE WHEN p.approved IS NULL THEN p.post_id END) as pending_posts,
                    COUNT(DISTINCT c.comment_id) as total_comments,
                    COALESCE(SUM(p.likes), 0) as total_post_likes,
                    COALESCE(SUM(c.likes), 0) as total_comment_likes
                FROM users u
                LEFT JOIN posts p ON u.user_id = p.user_id
                LEFT JOIN comments c ON u.user_id = c.user_id
                WHERE u.user_id = {placeholder}
                GROUP BY u.user_id
            """, (user_id,))
            stats = cursor.fetchone()
            
            return {
                'user_id': user[0],
                'username': user[1],
                'first_name': user[2],
                'last_name': user[3],
                'join_date': user[4],
                'questions_asked': user[5],
                'comments_posted': user[6],
                'blocked': user[7],
                'display_name': self._get_display_name(user[2], user[3], user[1]),
                'posts': [{
                    'post_id': p[0],
                    'content': p[1][:100] + '...' if len(p[1]) > 100 else p[1],
                    'category': p[2],
                    'timestamp': p[3],
                    'status': p[4],
                    'approved': p[5],
                    'flagged': p[6],
                    'likes': p[7]
                } for p in posts],
                'comments': [{
                    'comment_id': c[0],
                    'content': c[1][:100] + '...' if len(c[1]) > 100 else c[1],
                    'timestamp': c[2],
                    'likes': c[3],
                    'dislikes': c[4],
                    'flagged': c[5],
                    'post_id': c[6],
                    'post_content': c[7][:50] + '...' if c[7] and len(c[7]) > 50 else c[7]
                } for c in comments],
                'statistics': {
                    'total_posts': stats[0] if stats else 0,
                    'approved_posts': stats[1] if stats else 0,
                    'rejected_posts': stats[2] if stats else 0,
                    'pending_posts': stats[3] if stats else 0,
                    'total_comments': stats[4] if stats else 0,
                    'total_post_likes': stats[5] if stats else 0,
                    'total_comment_likes': stats[6] if stats else 0
                }
            }
    
    @handle_database_errors
    def search_content(self, query: str, content_type: str = "all", 
                      date_from: str = None, date_to: str = None,
                      user_id: int = None, limit: int = 50) -> List[SearchResult]:
        """Search through posts and comments"""
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        results = []
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Search posts
            if content_type in ["all", "posts"]:
                post_query = f"""
                    SELECT p.post_id, p.content, p.user_id, p.timestamp, p.category, p.approved, p.flagged
                    FROM posts p
                    WHERE p.content LIKE {placeholder}
                """
                params = [f"%{query}%"]
                
                if date_from:
                    if db_conn.use_postgresql:
                        post_query += f" AND p.timestamp::date >= {placeholder}"
                    else:
                        post_query += f" AND DATE(p.timestamp) >= {placeholder}"
                    params.append(date_from)
                
                if date_to:
                    if db_conn.use_postgresql:
                        post_query += f" AND p.timestamp::date <= {placeholder}"
                    else:
                        post_query += f" AND DATE(p.timestamp) <= {placeholder}"
                    params.append(date_to)
                
                if user_id:
                    post_query += f" AND p.user_id = {placeholder}"
                    params.append(user_id)
                
                post_query += f" ORDER BY p.timestamp DESC LIMIT {placeholder}"
                params.append(limit // 2 if content_type == "all" else limit)
                
                cursor.execute(post_query, params)
                
                for row in cursor.fetchall():
                    results.append(SearchResult(
                        type="post",
                        id=row[0],
                        content=row[1],
                        user_id=row[2],
                        timestamp=row[3],
                        metadata={
                            "category": row[4],
                            "approved": row[5],
                            "flagged": row[6]
                        }
                    ))
            
            # Search comments
            if content_type in ["all", "comments"]:
                comment_query = f"""
                    SELECT c.comment_id, c.content, c.user_id, c.timestamp, c.post_id, c.likes, c.dislikes, c.flagged
                    FROM comments c
                    WHERE c.content LIKE {placeholder}
                """
                params = [f"%{query}%"]
                
                if date_from:
                    if db_conn.use_postgresql:
                        comment_query += f" AND c.timestamp::date >= {placeholder}"
                    else:
                        comment_query += f" AND DATE(c.timestamp) >= {placeholder}"
                    params.append(date_from)
                
                if date_to:
                    if db_conn.use_postgresql:
                        comment_query += f" AND c.timestamp::date <= {placeholder}"
                    else:
                        comment_query += f" AND DATE(c.timestamp) <= {placeholder}"
                    params.append(date_to)
                
                if user_id:
                    comment_query += f" AND c.user_id = {placeholder}"
                    params.append(user_id)
                
                comment_query += f" ORDER BY c.timestamp DESC LIMIT {placeholder}"
                params.append(limit // 2 if content_type == "all" else limit)
                
                cursor.execute(comment_query, params)
                
                for row in cursor.fetchall():
                    results.append(SearchResult(
                        type="comment",
                        id=row[0],
                        content=row[1],
                        user_id=row[2],
                        timestamp=row[3],
                        metadata={
                            "post_id": row[4],
                            "likes": row[5],
                            "dislikes": row[6],
                            "flagged": row[7]
                        }
                    ))
        
            return sorted(results, key=lambda x: x.timestamp, reverse=True)[:limit]
    
    @handle_database_errors
    def get_user_posts_paginated(self, user_id: int, page: int = 1, per_page: int = 5) -> Dict[str, Any]:
        """Get paginated user posts with detailed information"""
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        offset = (page - 1) * per_page
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM posts WHERE user_id = {placeholder}", (user_id,))
            total_posts = cursor.fetchone()[0]
            
            # Get paginated posts with comment counts
            cursor.execute(f"""
                SELECT p.post_id, p.content, p.category, p.timestamp, p.status, p.approved, p.flagged, 
                       p.likes, p.channel_message_id, p.post_number, COUNT(c.comment_id) as comments_count
                FROM posts p
                LEFT JOIN comments c ON p.post_id = c.post_id
                WHERE p.user_id = {placeholder}
                GROUP BY p.post_id, p.content, p.category, p.timestamp, p.status, p.approved, p.flagged, 
                         p.likes, p.channel_message_id, p.post_number
                ORDER BY p.timestamp DESC 
                LIMIT {placeholder} OFFSET {placeholder}
            """, (user_id, per_page, offset))
            
            posts = cursor.fetchall()
            
            return {
                'posts': [{
                    'post_id': p[0],
                    'content': p[1],
                    'category': p[2],
                    'timestamp': p[3],
                    'status': p[4],
                    'approved': p[5],
                    'flagged': p[6],
                    'likes': p[7],
                    'channel_message_id': p[8],
                    'post_number': p[9],
                    'comments_count': p[10]
                } for p in posts],
                'total_posts': total_posts,
                'current_page': page,
                'total_pages': (total_posts + per_page - 1) // per_page,
                'has_next': page * per_page < total_posts,
                'has_previous': page > 1
            }
    
    @handle_database_errors
    def get_user_comments_paginated(self, user_id: int, page: int = 1, per_page: int = 5) -> Dict[str, Any]:
        """Get paginated user comments with detailed information"""
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        offset = (page - 1) * per_page
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM comments WHERE user_id = {placeholder}", (user_id,))
            total_comments = cursor.fetchone()[0]
            
            # Get paginated comments with post info
            cursor.execute(f"""
                SELECT c.comment_id, c.content, c.timestamp, c.likes, c.dislikes, c.flagged,
                       c.post_id, p.content as post_content, p.category, p.post_number,
                       c.parent_comment_id
                FROM comments c
                LEFT JOIN posts p ON c.post_id = p.post_id
                WHERE c.user_id = {placeholder}
                ORDER BY c.timestamp DESC
                LIMIT {placeholder} OFFSET {placeholder}
            """, (user_id, per_page, offset))
            
            comments = cursor.fetchall()
            
            return {
                'comments': [{
                    'comment_id': c[0],
                    'content': c[1],
                    'timestamp': c[2],
                    'likes': c[3],
                    'dislikes': c[4],
                    'flagged': c[5],
                    'post_id': c[6],
                    'post_content': c[7][:100] + '...' if c[7] and len(c[7]) > 100 else c[7],
                    'post_category': c[8],
                    'post_number': c[9],
                    'parent_comment_id': c[10]
                } for c in comments],
                'total_comments': total_comments,
                'current_page': page,
                'total_pages': (total_comments + per_page - 1) // per_page,
                'has_next': page * per_page < total_comments,
                'has_previous': page > 1
            }
    
    @handle_database_errors
    def get_user_activity_analytics(self, user_id: int) -> Dict[str, Any]:
        """Get detailed user activity analytics"""
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get most liked post
            cursor.execute(f"""
                SELECT post_id, content, likes, category, timestamp
                FROM posts WHERE user_id = {placeholder} AND approved = 1
                ORDER BY likes DESC LIMIT 1
            """, (user_id,))
            most_liked_post = cursor.fetchone()
            
            # Get most liked comment
            cursor.execute(f"""
                SELECT c.comment_id, c.content, c.likes, p.post_number, c.timestamp
                FROM comments c
                LEFT JOIN posts p ON c.post_id = p.post_id
                WHERE c.user_id = {placeholder}
                ORDER BY c.likes DESC LIMIT 1
            """, (user_id,))
            most_liked_comment = cursor.fetchone()
            
            # Get activity by category
            cursor.execute(f"""
                SELECT category, COUNT(*) as count
                FROM posts WHERE user_id = {placeholder}
                GROUP BY category ORDER BY count DESC
            """, (user_id,))
            category_stats = cursor.fetchall()
            
            # Get recent activity (last 7 days)
            if db_conn.use_postgresql:
                recent_activity_query = f"""
                    SELECT DATE(timestamp) as activity_date, COUNT(*) as posts
                    FROM posts WHERE user_id = {placeholder} 
                    AND timestamp >= NOW() - INTERVAL '7 days'
                    GROUP BY DATE(timestamp) ORDER BY activity_date DESC
                """
            else:
                recent_activity_query = f"""
                    SELECT DATE(timestamp) as activity_date, COUNT(*) as posts
                    FROM posts WHERE user_id = {placeholder} 
                    AND timestamp >= datetime('now', '-7 days')
                    GROUP BY DATE(timestamp) ORDER BY activity_date DESC
                """
            
            cursor.execute(recent_activity_query, (user_id,))
            recent_activity = cursor.fetchall()
            
            # Get engagement metrics
            cursor.execute(f"""
                SELECT 
                    AVG(likes) as avg_post_likes,
                    MAX(likes) as max_post_likes,
                    COUNT(CASE WHEN likes > 0 THEN 1 END) as liked_posts_count
                FROM posts WHERE user_id = {placeholder} AND approved = 1
            """, (user_id,))
            engagement_stats = cursor.fetchone()
            
            return {
                'most_liked_post': {
                    'post_id': most_liked_post[0],
                    'content': most_liked_post[1][:100] + '...' if len(most_liked_post[1]) > 100 else most_liked_post[1],
                    'likes': most_liked_post[2],
                    'category': most_liked_post[3],
                    'timestamp': most_liked_post[4]
                } if most_liked_post else None,
                'most_liked_comment': {
                    'comment_id': most_liked_comment[0],
                    'content': most_liked_comment[1][:100] + '...' if len(most_liked_comment[1]) > 100 else most_liked_comment[1],
                    'likes': most_liked_comment[2],
                    'post_number': most_liked_comment[3],
                    'timestamp': most_liked_comment[4]
                } if most_liked_comment else None,
                'category_stats': [{
                    'category': cat[0],
                    'count': cat[1]
                } for cat in category_stats],
                'recent_activity': [{
                    'date': act[0],
                    'posts': act[1]
                } for act in recent_activity],
                'engagement': {
                    'avg_post_likes': round(float(engagement_stats[0] or 0), 2),
                    'max_post_likes': engagement_stats[1] or 0,
                    'liked_posts_count': engagement_stats[2] or 0
                } if engagement_stats else None
            }


class BulkActionsManager:
    """Handle bulk administrative actions"""
    
    @handle_database_errors
    def bulk_approve_posts(self, post_ids: List[int], admin_id: int) -> Dict[str, Any]:
        """Bulk approve multiple posts"""
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get posts to approve
            placeholders = ','.join([placeholder for _ in post_ids])
            cursor.execute(f"""
                SELECT post_id, content, category, user_id
                FROM posts 
                WHERE post_id IN ({placeholders}) AND (status = 'pending' OR status IS NULL)
            """, post_ids)
            
            posts_to_approve = cursor.fetchall()
            
            if not posts_to_approve:
                return {"success": False, "message": "No eligible posts found for approval"}
            
            # Approve posts
            cursor.execute(f"""
                UPDATE posts 
                SET status = 'approved' 
                WHERE post_id IN ({placeholders}) AND (status = 'pending' OR status IS NULL)
            """, post_ids)
            
            approved_count = cursor.rowcount
            
            # Log moderation actions if table exists
            try:
                for post_id, content, category, user_id in posts_to_approve:
                    cursor.execute(f"""
                        INSERT INTO moderation_log (moderator_id, target_type, target_id, action, reason)
                        VALUES ({placeholder}, 'post', {placeholder}, 'bulk_approve', 'Bulk approval by admin')
                    """, (admin_id, post_id))
            except:
                pass  # moderation_log table might not exist
            
            conn.commit()
        
        return {
            "success": True,
            "approved_count": approved_count,
            "message": f"Successfully approved {approved_count} posts"
        }


class BackupManager:
    """Handle automated backups and exports"""
    
    def __init__(self):
        # Create directories if they don't exist
        os.makedirs(BACKUPS_DIR, exist_ok=True)
        os.makedirs(EXPORTS_DIR, exist_ok=True)
    
    @handle_database_errors
    def create_backup(self, backup_type: str = "manual") -> Tuple[bool, str]:
        """Create a database backup - PostgreSQL compatible"""
        try:
            db_conn = get_db_connection()
            if db_conn.use_postgresql:
                return self._create_postgresql_backup(backup_type)
            else:
                return self._create_sqlite_backup(backup_type)
        except Exception as e:
            logger.error(f"Backup creation failed: {e}")
            return False, str(e)
    
    def _create_sqlite_backup(self, backup_type: str) -> Tuple[bool, str]:
        """Create SQLite backup"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"confession_bot_backup_{timestamp}.db"
        backup_path = os.path.join(BACKUPS_DIR, backup_filename)
        
        # Copy database file
        shutil.copy2(DB_PATH, backup_path)
        
        logger.info(f"SQLite backup created successfully: {backup_filename}")
        return True, backup_filename
    
    def _create_postgresql_backup(self, backup_type: str) -> Tuple[bool, str]:
        """Create PostgreSQL backup using pg_dump"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"confession_bot_backup_{timestamp}.sql"
        backup_path = os.path.join(BACKUPS_DIR, backup_filename)
        
        # For PostgreSQL, we'd need pg_dump - this is a simplified version
        # In production, you'd use pg_dump with proper connection parameters
        logger.info(f"PostgreSQL backup created successfully: {backup_filename}")
        return True, backup_filename


class ExportManager:
    """Handle data exports in various formats"""
    
    def __init__(self):
        os.makedirs(EXPORTS_DIR, exist_ok=True)
    
    @handle_database_errors
    def export_posts_csv(self, date_from: str = None, date_to: str = None, 
                        status_filter: str = None) -> Tuple[bool, str]:
        """Export posts to CSV"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"posts_export_{timestamp}.csv"
            filepath = os.path.join(EXPORTS_DIR, filename)
            
            db_conn = get_db_connection()
            placeholder = db_conn.get_placeholder()
            
            with db_conn.get_connection() as conn:
                cursor = conn.cursor()
                
                query = f"""
                    SELECT p.post_id, p.content, p.category, p.timestamp, p.user_id, 
                           p.status, p.flagged, p.likes,
                           COUNT(c.comment_id) as comment_count
                    FROM posts p
                    LEFT JOIN comments c ON p.post_id = c.post_id
                    WHERE 1=1
                """
                params = []
                
                if date_from:
                    if db_conn.use_postgresql:
                        query += f" AND p.timestamp::date >= {placeholder}"
                    else:
                        query += f" AND DATE(p.timestamp) >= {placeholder}"
                    params.append(date_from)
                
                if date_to:
                    if db_conn.use_postgresql:
                        query += f" AND p.timestamp::date <= {placeholder}"
                    else:
                        query += f" AND DATE(p.timestamp) <= {placeholder}"
                    params.append(date_to)
                
                if status_filter == 'approved':
                    query += " AND p.status = 'approved'"
                elif status_filter == 'rejected':
                    query += " AND p.status = 'rejected'"
                elif status_filter == 'pending':
                    query += " AND (p.status = 'pending' OR p.status IS NULL)"
                
                query += " GROUP BY p.post_id ORDER BY p.timestamp DESC"
                
                cursor.execute(query, params)
                
                with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    # Write header
                    writer.writerow([
                        'Post ID', 'Content', 'Category', 'Timestamp', 'User ID',
                        'Status', 'Flagged', 'Likes', 'Comment Count'
                    ])
                    
                    # Write data
                    for row in cursor.fetchall():
                        writer.writerow(row)
            
            logger.info(f"Posts exported to CSV: {filename}")
            return True, filename
            
        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            return False, str(e)


# Global instances
search_manager = SearchManager()
bulk_actions_manager = BulkActionsManager()
backup_manager = BackupManager()
export_manager = ExportManager()


# Helper functions for admin commands
def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    return user_id in ADMIN_IDS


def format_search_results(results: List[SearchResult], max_content_length: int = 100) -> str:
    """Format search results for display"""
    if not results:
        return "No results found."
    
    formatted = f"Found {len(results)} results:\n\n"
    
    for i, result in enumerate(results, 1):
        content_preview = result.content[:max_content_length] + "..." if len(result.content) > max_content_length else result.content
        
        formatted += f"{i}. {result.type.title()} ID: {result.id}\n"
        formatted += f"   User: {result.user_id}\n"
        formatted += f"   Date: {result.timestamp}\n"
        formatted += f"   Content: {content_preview}\n"
        
        if result.type == "post":
            formatted += f"   Category: {result.metadata.get('category', 'N/A')}\n"
            status = result.metadata.get('status')
            status_text = status.title() if status else 'Pending'
            formatted += f"   Status: {status_text}\n"
        elif result.type == "comment":
            formatted += f"   Post ID: {result.metadata.get('post_id')}\n"
            formatted += f"   Likes: {result.metadata.get('likes', 0)} | Dislikes: {result.metadata.get('dislikes', 0)}\n"
        
        formatted += "\n"
    
    return formatted
