"""
Trending and Popular Posts Module
Handles fetching of trending posts, most commented posts, and rising posts
"""

from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from db_connection import get_db, get_db_connection
from logger import get_logger

logger = get_logger('trending')

def get_most_commented_posts_24h(limit: int = 10) -> List[Tuple]:
    """Get posts with most comments in the last 24 hours"""
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get posts from last 24 hours ordered by comment count
            yesterday = (datetime.now() - timedelta(days=1))
            
            cursor.execute(f"""
                SELECT p.post_id, p.content, p.category, p.timestamp, 
                       COUNT(c.comment_id) as comment_count,
                       p.approved, p.channel_message_id, p.post_number,
                       p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                       p.media_file_size, p.media_mime_type, p.media_duration, 
                       p.media_width, p.media_height, p.media_thumbnail_file_id
                FROM posts p 
                LEFT JOIN comments c ON p.post_id = c.post_id 
                WHERE p.approved = 1 
                AND p.timestamp >= {placeholder}
                GROUP BY p.post_id 
                ORDER BY comment_count DESC, p.timestamp DESC 
                LIMIT {placeholder}
            """, (yesterday, limit))
            
            return cursor.fetchall()
            
    except Exception as e:
        logger.error(f"Error getting most commented posts (24h): {e}")
        return []

def get_posts_with_most_liked_comments(limit: int = 10) -> List[Tuple]:
    """Get posts that have comments with the most likes"""
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get posts ordered by total likes on their comments
            cursor.execute(f"""
                SELECT p.post_id, p.content, p.category, p.timestamp,
                       COUNT(c.comment_id) as comment_count,
                       COALESCE(SUM(c.likes), 0) as total_comment_likes,
                       p.approved, p.channel_message_id, p.post_number,
                       p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                       p.media_file_size, p.media_mime_type, p.media_duration, 
                       p.media_width, p.media_height, p.media_thumbnail_file_id
                FROM posts p 
                LEFT JOIN comments c ON p.post_id = c.post_id 
                WHERE p.approved = 1 
                GROUP BY p.post_id 
                HAVING COALESCE(SUM(c.likes), 0) > 0
                ORDER BY total_comment_likes DESC, comment_count DESC, p.timestamp DESC
                LIMIT {placeholder}
            """, (limit,))
            
            return cursor.fetchall()
            
    except Exception as e:
        logger.error(f"Error getting posts with most liked comments: {e}")
        return []

def get_rising_posts(limit: int = 10) -> List[Tuple]:
    """Get posts that are gaining traction fast (recent posts with growing engagement) - optimized"""
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get posts from last 12 hours ordered by engagement rate
            twelve_hours_ago = datetime.now() - timedelta(hours=12)
            six_hours_ago = datetime.now() - timedelta(hours=6)
            twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
            
            # Optimized query using subqueries instead of JOIN for better performance
            if db_conn.use_postgresql:
                cursor.execute(f'''
                    SELECT p.post_id, p.content, p.category, p.timestamp,
                           COALESCE(cc.comment_count, 0) as comment_count,
                           COALESCE(cl.total_likes, 0) as total_comment_likes,
                           p.approved, p.channel_message_id, p.post_number,
                           -- Calculate engagement score based on recency and activity
                           (COALESCE(cc.comment_count, 0) * 2 + COALESCE(cl.total_likes, 0)) * 
                           (CASE 
                               WHEN p.timestamp >= {placeholder} THEN 3
                               WHEN p.timestamp >= {placeholder} THEN 2
                               ELSE 1
                           END) as engagement_score,
                           p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                           p.media_file_size, p.media_mime_type, p.media_duration, 
                           p.media_width, p.media_height, p.media_thumbnail_file_id
                    FROM posts p
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) as comment_count
                        FROM comments c
                        WHERE c.post_id = p.post_id
                    ) cc ON true
                    LEFT JOIN LATERAL (
                        SELECT COALESCE(SUM(likes), 0) as total_likes
                        FROM comments c
                        WHERE c.post_id = p.post_id
                    ) cl ON true
                    WHERE p.approved = 1 
                    AND p.timestamp >= {placeholder}
                    AND (COALESCE(cc.comment_count, 0) > 0 OR COALESCE(cl.total_likes, 0) > 0)
                    ORDER BY engagement_score DESC, p.timestamp DESC 
                    LIMIT {placeholder}
                ''', (twelve_hours_ago, six_hours_ago, twenty_four_hours_ago, limit))
            else:
                cursor.execute('''
                    SELECT p.post_id, p.content, p.category, p.timestamp,
                           (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.post_id) as comment_count,
                           (SELECT COALESCE(SUM(likes), 0) FROM comments c WHERE c.post_id = p.post_id) as total_comment_likes,
                           p.approved, p.channel_message_id, p.post_number,
                           -- Calculate engagement score based on recency and activity
                           ((SELECT COUNT(*) FROM comments c WHERE c.post_id = p.post_id) * 2 + 
                            (SELECT COALESCE(SUM(likes), 0) FROM comments c WHERE c.post_id = p.post_id)) * 
                           (CASE 
                               WHEN p.timestamp >= datetime('now', '-12 hours') THEN 3
                               WHEN p.timestamp >= datetime('now', '-6 hours') THEN 2
                               ELSE 1
                           END) as engagement_score,
                           p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                           p.media_file_size, p.media_mime_type, p.media_duration, 
                           p.media_width, p.media_height, p.media_thumbnail_file_id
                    FROM posts p 
                    WHERE p.approved = 1 
                    AND p.timestamp >= datetime('now', '-24 hours')
                    AND ((SELECT COUNT(*) FROM comments c WHERE c.post_id = p.post_id) > 0 
                         OR (SELECT COALESCE(SUM(likes), 0) FROM comments c WHERE c.post_id = p.post_id) > 0)
                    ORDER BY engagement_score DESC, p.timestamp DESC 
                    LIMIT ?
                ''', (limit,))
            
            return cursor.fetchall()
            
    except Exception as e:
        logger.error(f"Error getting rising posts: {e}")
        return []

def get_trending_posts(limit: int = 15) -> List[Tuple]:
    """Get overall trending posts - combination of most commented and rising"""
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get trending posts from last 48 hours with weighted scoring
            two_days_ago = datetime.now() - timedelta(days=2)
            twelve_hours_ago = datetime.now() - timedelta(hours=12)
            twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
            forty_eight_hours_ago = datetime.now() - timedelta(hours=48)
            
            # Build query with database-specific time comparisons
            if db_conn.use_postgresql:
                cursor.execute(f"""
                    SELECT p.post_id, p.content, p.category, p.timestamp,
                           COUNT(c.comment_id) as comment_count,
                           COALESCE(SUM(c.likes), 0) as total_comment_likes,
                           p.approved, p.channel_message_id, p.post_number,
                           -- Trending score: comments worth more than likes, recent posts get bonus
                           (COUNT(c.comment_id) * 5 + COALESCE(SUM(c.likes), 0) * 2) * 
                           (CASE 
                               WHEN p.timestamp >= {placeholder} THEN 2.5
                               WHEN p.timestamp >= {placeholder} THEN 2.0
                               WHEN p.timestamp >= {placeholder} THEN 1.5
                               ELSE 1.0
                           END) as trending_score,
                           p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                           p.media_file_size, p.media_mime_type, p.media_duration, 
                           p.media_width, p.media_height, p.media_thumbnail_file_id
                    FROM posts p 
                    LEFT JOIN comments c ON p.post_id = c.post_id 
                    WHERE p.approved = 1 
                    AND p.timestamp >= {placeholder}
                    GROUP BY p.post_id 
                    HAVING (COUNT(c.comment_id) * 5 + COALESCE(SUM(c.likes), 0) * 2) > 0
                    ORDER BY trending_score DESC, p.timestamp DESC 
                    LIMIT {placeholder}
                """, (twelve_hours_ago, twenty_four_hours_ago, forty_eight_hours_ago, two_days_ago, limit))
            else:
                cursor.execute("""
                    SELECT p.post_id, p.content, p.category, p.timestamp,
                           COUNT(c.comment_id) as comment_count,
                           COALESCE(SUM(c.likes), 0) as total_comment_likes,
                           p.approved, p.channel_message_id, p.post_number,
                           -- Trending score: comments worth more than likes, recent posts get bonus
                           (COUNT(c.comment_id) * 5 + COALESCE(SUM(c.likes), 0) * 2) * 
                           (CASE 
                               WHEN p.timestamp >= datetime('now', '-12 hours') THEN 2.5
                               WHEN p.timestamp >= datetime('now', '-24 hours') THEN 2.0
                               WHEN p.timestamp >= datetime('now', '-48 hours') THEN 1.5
                               ELSE 1.0
                           END) as trending_score,
                           p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                           p.media_file_size, p.media_mime_type, p.media_duration, 
                           p.media_width, p.media_height, p.media_thumbnail_file_id
                    FROM posts p 
                    LEFT JOIN comments c ON p.post_id = c.post_id 
                    WHERE p.approved = 1 
                    AND p.timestamp >= datetime('now', '-2 days')
                    GROUP BY p.post_id 
                    HAVING trending_score > 0
                    ORDER BY trending_score DESC, p.timestamp DESC 
                    LIMIT ?
                """, (limit,))
            
            return cursor.fetchall()
            
    except Exception as e:
        logger.error(f"Error getting trending posts: {e}")
        return []

def get_popular_today_posts(limit: int = 15) -> List[Tuple]:
    """Get today's most popular posts"""
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get today's posts ordered by engagement
            today = datetime.now().date()
            
            if db_conn.use_postgresql:
                cursor.execute(f"""
                    SELECT p.post_id, p.content, p.category, p.timestamp,
                           COUNT(c.comment_id) as comment_count,
                           COALESCE(SUM(c.likes), 0) as total_comment_likes,
                           p.approved, p.channel_message_id, p.post_number,
                           -- Today's popularity score
                           (COUNT(c.comment_id) * 3 + COALESCE(SUM(c.likes), 0)) as popularity_score,
                           p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                           p.media_file_size, p.media_mime_type, p.media_duration, 
                           p.media_width, p.media_height, p.media_thumbnail_file_id
                    FROM posts p 
                    LEFT JOIN comments c ON p.post_id = c.post_id 
                    WHERE p.approved = 1 
                    AND DATE(p.timestamp) = {placeholder}
                    GROUP BY p.post_id 
                    ORDER BY popularity_score DESC, comment_count DESC, p.timestamp DESC 
                    LIMIT {placeholder}
                """, (today, limit))
            else:
                cursor.execute("""
                    SELECT p.post_id, p.content, p.category, p.timestamp,
                           COUNT(c.comment_id) as comment_count,
                           COALESCE(SUM(c.likes), 0) as total_comment_likes,
                           p.approved, p.channel_message_id, p.post_number,
                           -- Today's popularity score
                           (COUNT(c.comment_id) * 3 + COALESCE(SUM(c.likes), 0)) as popularity_score,
                           p.media_type, p.media_file_id, p.media_file_unique_id, p.media_caption,
                           p.media_file_size, p.media_mime_type, p.media_duration, 
                           p.media_width, p.media_height, p.media_thumbnail_file_id
                    FROM posts p 
                    LEFT JOIN comments c ON p.post_id = c.post_id 
                    WHERE p.approved = 1 
                    AND DATE(p.timestamp) = DATE('now')
                    GROUP BY p.post_id 
                    ORDER BY popularity_score DESC, comment_count DESC, p.timestamp DESC 
                    LIMIT ?
                """, (limit,))
            
            return cursor.fetchall()
            
    except Exception as e:
        logger.error(f"Error getting popular today posts: {e}")
        return []

def get_post_engagement_stats(post_id: int) -> Optional[dict]:
    """Get engagement statistics for a specific post"""
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT 
                    COUNT(c.comment_id) as comment_count,
                    COALESCE(SUM(c.likes), 0) as total_likes,
                    COALESCE(SUM(c.dislikes), 0) as total_dislikes,
                    COUNT(DISTINCT c.user_id) as unique_commenters
                FROM comments c 
                WHERE c.post_id = {placeholder}
            """, (post_id,))
            
            result = cursor.fetchone()
            if result:
                return {
                    'comment_count': result[0],
                    'total_likes': result[1],
                    'total_dislikes': result[2],
                    'unique_commenters': result[3],
                    'engagement_ratio': result[1] / max(result[2], 1)  # likes/dislikes ratio
                }
            return None
            
    except Exception as e:
        logger.error(f"Error getting engagement stats for post {post_id}: {e}")
        return None
