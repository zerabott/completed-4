import time
from functools import lru_cache
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import COMMENTS_PER_PAGE, CHANNEL_ID, BOT_USERNAME
from text_utils import escape_markdown_text
from db import get_comment_count, get_user_profile, get_post_author_id
from submission import is_media_post, get_media_info
from db_connection import get_db_connection, execute_query, adapt_query
from ranking_integration import RankingIntegration
import logging

logger = logging.getLogger(__name__)

# Simple in-memory cache for user profiles and ranks
_profile_cache = {}
_rank_cache = {}
_cache_expiry = 300  # 5 minutes cache expiry

def get_cached_user_profile(user_id):
    """Get user profile with caching"""
    current_time = time.time()
    
    # Check if we have a cached profile that's still valid
    if user_id in _profile_cache:
        profile_data, expiry_time = _profile_cache[user_id]
        if current_time < expiry_time:
            return profile_data
    
    # Fetch fresh profile
    try:
        profile = get_user_profile(user_id)
        _profile_cache[user_id] = (profile, current_time + _cache_expiry)
        return profile
    except Exception as e:
        logger.error(f"Error fetching profile for user {user_id}: {e}")
        return None

def get_cached_user_rank(user_id):
    """Get user rank with caching"""
    current_time = time.time()
    
    # Check if we have a cached rank that's still valid
    if user_id in _rank_cache:
        rank_data, expiry_time = _rank_cache[user_id]
        if current_time < expiry_time:
            return rank_data
    
    # Fetch fresh rank
    try:
        user_rank = get_user_rank_for_comment(user_id)
        _rank_cache[user_id] = (user_rank, current_time + _cache_expiry)
        return user_rank
    except Exception as e:
        logger.error(f"Error getting rank for user {user_id}: {e}")
        # Return default rank on error
        default_rank = {
            'rank_name': 'Freshman',
            'rank_emoji': '🥉',
            'total_points': 0,
            'is_special_rank': False
        }
        return default_rank

def get_user_rank_for_comment(user_id):
    """Get user's rank information for displaying under comments"""
    try:
        from ranking_integration import ranking_manager
        user_rank = ranking_manager.get_user_rank(user_id)
        
        if user_rank:
            return {
                'rank_name': user_rank.rank_name,
                'rank_emoji': user_rank.rank_emoji,
                'total_points': user_rank.total_points,
                'is_special_rank': user_rank.is_special_rank
            }
        else:
            # Default rank for new users
            return {
                'rank_name': 'Freshman',
                'rank_emoji': '🥉',
                'total_points': 0,
                'is_special_rank': False
            }
    except Exception as e:
        logger.error(f"Error getting user rank for {user_id}: {e}")
        # Return default rank on error
        return {
            'rank_name': 'Freshman',
            'rank_emoji': '🥉',
            'total_points': 0,
            'is_special_rank': False
        }

def save_comment(post_id, content, user_id, parent_comment_id=None):
    """Save a comment to the database"""
    try:
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # First, validate that the post exists
            post_check_query = adapt_query("SELECT post_id FROM posts WHERE post_id = ? AND approved = 1")
            cursor.execute(post_check_query, (post_id,))
            post_exists = cursor.fetchone()
            
            if not post_exists:
                logger.error(f"Cannot save comment: Post {post_id} does not exist or is not approved")
                return None, f"Post {post_id} not found or not approved"
            
            # Validate parent comment if provided
            if parent_comment_id:
                parent_check_query = adapt_query("SELECT comment_id FROM comments WHERE comment_id = ?")
                cursor.execute(parent_check_query, (parent_comment_id,))
                parent_exists = cursor.fetchone()
                
                if not parent_exists:
                    logger.error(f"Cannot save comment: Parent comment {parent_comment_id} does not exist")
                    return None, f"Parent comment {parent_comment_id} not found"
            
            # Insert comment using proper database abstraction
            if db_conn.use_postgresql:
                # PostgreSQL: use RETURNING clause to get the ID
                insert_query = adapt_query("INSERT INTO comments (post_id, content, user_id, parent_comment_id) VALUES (?, ?, ?, ?) RETURNING comment_id")
                cursor.execute(insert_query, (post_id, content, user_id, parent_comment_id))
                comment_id = cursor.fetchone()[0]
            else:
                # SQLite: use lastrowid
                insert_query = adapt_query("INSERT INTO comments (post_id, content, user_id, parent_comment_id) VALUES (?, ?, ?, ?)")
                cursor.execute(insert_query, (post_id, content, user_id, parent_comment_id))
                comment_id = cursor.lastrowid

            # Update user stats
            update_query = adapt_query("UPDATE users SET comments_posted = comments_posted + 1 WHERE user_id = ?")
            cursor.execute(update_query, (user_id,))
            
            # Invalidate comment count cache so channel message gets updated count
            from db_connection import cache_manager
            cache_manager.delete(f'comment_count_{post_id}')
            
            # Commit the transaction for both PostgreSQL and SQLite
            conn.commit()
            
            return comment_id, None
    except Exception as e:
        logger.error(f"Error saving comment: {e}")
        return None, f"Database error: {str(e)}"

async def save_comment_with_points(post_id, content, user_id, context, parent_comment_id=None):
    """Save a comment and award points"""
    # Save comment first
    comment_id, error = save_comment(post_id, content, user_id, parent_comment_id)
    
    if comment_id and not error:
        # Award points for the comment
        try:
            await RankingIntegration.handle_comment_posted(user_id, post_id, comment_id, content, context)
            logger.info(f"Awarded comment points to user {user_id} for comment {comment_id}")
        except Exception as e:
            logger.error(f"Error awarding comment points: {e}")
    
    return comment_id, error

def get_post_with_channel_info(post_id):
    """Get post information including channel message ID"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f"SELECT post_id, content, category, channel_message_id, approved FROM posts WHERE post_id = {placeholder}",
            (post_id,)
        )
        return cursor.fetchone()

def get_comments_paginated(post_id, page=1):
    """Get comments for a post in flat structure like Telegram native replies - OPTIMIZED VERSION"""
    offset = (page - 1) * COMMENTS_PER_PAGE

    try:
        # Get total count using the existing function
        total_comments = get_comment_count(post_id)

        # Get paginated comments in flat structure
        db_conn = get_db_connection()

        # Get the original confessor (post author) for this post once
        post_author_id = None
        try:
            with db_conn.get_connection() as conn_info:
                cursor_info = conn_info.cursor()
                placeholder = db_conn.get_placeholder()
                cursor_info.execute(
                    f"SELECT user_id FROM posts WHERE post_id = {placeholder}",
                    (post_id,)
                )
                row = cursor_info.fetchone()
                if row:
                    post_author_id = row[0]
        except Exception as e:
            logger.error(f"Error fetching post author for post {post_id}: {e}")

        if db_conn.use_postgresql:
            # PostgreSQL version with ROW_NUMBER() and user_id for rank display
            query = f"""
                SELECT comment_id, content, timestamp, likes, dislikes, flagged, parent_comment_id, user_id,
                       ROW_NUMBER() OVER (ORDER BY timestamp ASC) as comment_number
                FROM comments 
                WHERE post_id = {db_conn.get_placeholder()}
                ORDER BY timestamp ASC
                LIMIT {db_conn.get_placeholder()} OFFSET {db_conn.get_placeholder()}
            """
        else:
            # SQLite version with ROW_NUMBER() and user_id for rank display
            query = f"""
                SELECT comment_id, content, timestamp, likes, dislikes, flagged, parent_comment_id, user_id,
                       ROW_NUMBER() OVER (ORDER BY timestamp ASC) as comment_number
                FROM comments 
                WHERE post_id = {db_conn.get_placeholder()}
                ORDER BY timestamp ASC
                LIMIT {db_conn.get_placeholder()} OFFSET {db_conn.get_placeholder()}
            """
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (post_id, COMMENTS_PER_PAGE, offset))
            comments = cursor.fetchall()

            # Transform into simplified flat structure
            comments_flat = []
            comment_ids = []
            parent_comment_ids = []
            
            for comment in comments or []:
                comment_id = comment[0]
                content = comment[1]
                timestamp = comment[2]
                likes = comment[3]
                dislikes = comment[4]
                flagged = comment[5]
                parent_comment_id = comment[6]
                comment_user_id = comment[7]  # user_id for rank lookup
                comment_number = comment[8]  # ROW_NUMBER now at index 8

                # Determine if this comment was made by the original confessor
                is_confessor_comment = (
                    post_author_id is not None and comment_user_id == post_author_id
                )
                
                # Debug logging
                if is_confessor_comment:
                    logger.info(f"✍️ DETECTED: Comment {comment_id} by user {comment_user_id} is by post author {post_author_id}")
                
                comment_data = {
                    'comment_id': comment_id,
                    'content': content,
                    'timestamp': timestamp,
                    'likes': likes,
                    'dislikes': dislikes,
                    'flagged': flagged,
                    'parent_comment_id': parent_comment_id,
                    'user_id': comment_user_id,  # Add user_id for rank lookup
                    'comment_number': comment_number,
                    'is_reply': parent_comment_id is not None,
                    'is_confessor_comment': is_confessor_comment,
                }
                
                comments_flat.append(comment_data)
                comment_ids.append(comment_id)
                if parent_comment_id:
                    parent_comment_ids.append(parent_comment_id)

            # Batch fetch all parent comments if there are any replies
            original_comments_map = {}
            if parent_comment_ids:
                placeholders = ', '.join([db_conn.get_placeholder()] * len(parent_comment_ids))
                cursor.execute(
                    f"SELECT comment_id, content, timestamp FROM comments WHERE comment_id IN ({placeholders})",
                    tuple(parent_comment_ids)
                )
                original_comments = cursor.fetchall()
                original_comments_map = {row[0]: {'comment_id': row[0], 'content': row[1], 'timestamp': row[2]} 
                                       for row in original_comments}

            # Attach original comment data to replies
            for comment_data in comments_flat:
                if comment_data['parent_comment_id'] and comment_data['parent_comment_id'] in original_comments_map:
                    comment_data['original_comment'] = original_comments_map[comment_data['parent_comment_id']]

            total_pages = (total_comments + COMMENTS_PER_PAGE - 1) // COMMENTS_PER_PAGE

            return comments_flat, page, total_pages, total_comments
    except Exception as e:
        print(f"Error getting paginated comments: {e}")
        return [], 1, 1, 0

def get_comment_by_id(comment_id):
    """Get a specific comment by ID"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f"SELECT * FROM comments WHERE comment_id = {placeholder}",
            (comment_id,)
        )
        return cursor.fetchone()

def react_to_comment(user_id, comment_id, reaction_type):
    """Add or update reaction to a comment"""
    try:
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            placeholder = db_conn.get_placeholder()
            
            # Check existing reaction
            cursor.execute(
                f"SELECT reaction_type FROM reactions WHERE user_id = {placeholder} AND target_type = 'comment' AND target_id = {placeholder}",
                (user_id, comment_id)
            )
            existing = cursor.fetchone()
            
            if existing:
                if existing[0] == reaction_type:
                    # Remove reaction if same type
                    cursor.execute(
                        f"DELETE FROM reactions WHERE user_id = {placeholder} AND target_type = 'comment' AND target_id = {placeholder}",
                        (user_id, comment_id)
                    )
                    # Update comment counts
                    if reaction_type == 'like':
                        cursor.execute(
                            f"UPDATE comments SET likes = likes - 1 WHERE comment_id = {placeholder}",
                            (comment_id,)
                        )
                    else:
                        cursor.execute(
                            f"UPDATE comments SET dislikes = dislikes - 1 WHERE comment_id = {placeholder}",
                            (comment_id,)
                        )
                    action = "removed"
                else:
                    # Update reaction type
                    cursor.execute(
                        f"UPDATE reactions SET reaction_type = {placeholder} WHERE user_id = {placeholder} AND target_type = 'comment' AND target_id = {placeholder}",
                        (reaction_type, user_id, comment_id)
                    )
                    # Update comment counts
                    if existing[0] == 'like':
                        cursor.execute(
                            f"UPDATE comments SET likes = likes - 1, dislikes = dislikes + 1 WHERE comment_id = {placeholder}",
                            (comment_id,)
                        )
                    else:
                        cursor.execute(
                            f"UPDATE comments SET likes = likes + 1, dislikes = dislikes - 1 WHERE comment_id = {placeholder}",
                            (comment_id,)
                        )
                    action = "changed"
            else:
                # Add new reaction
                cursor.execute(
                    f"INSERT INTO reactions (user_id, target_type, target_id, reaction_type) VALUES ({placeholder}, 'comment', {placeholder}, {placeholder})",
                    (user_id, comment_id, reaction_type)
                )
                # Update comment counts
                if reaction_type == 'like':
                    cursor.execute(
                        f"UPDATE comments SET likes = likes + 1 WHERE comment_id = {placeholder}",
                        (comment_id,)
                    )
                else:
                    cursor.execute(
                        f"UPDATE comments SET dislikes = dislikes + 1 WHERE comment_id = {placeholder}",
                        (comment_id,)
                    )
                action = "added"
            
            conn.commit()
            
            # Return current counts along with action
            cursor.execute(
                f"SELECT likes, dislikes FROM comments WHERE comment_id = {placeholder}",
                (comment_id,)
            )
            counts = cursor.fetchone()
            current_likes = counts[0] if counts else 0
            current_dislikes = counts[1] if counts else 0
            
            return True, action, current_likes, current_dislikes
    except Exception as e:
        return False, str(e), 0, 0

async def react_to_comment_with_points(user_id, comment_id, reaction_type, context):
    """Add or update reaction to a comment and award points"""
    # First, handle the reaction
    success, action, likes, dislikes = react_to_comment(user_id, comment_id, reaction_type)
    
    if success and action in ['added', 'changed']:
        # Get comment owner for point awarding
        try:
            db_conn = get_db_connection()
            with db_conn.get_connection() as conn:
                cursor = conn.cursor()
                placeholder = db_conn.get_placeholder()
                cursor.execute(
                    f"SELECT user_id FROM comments WHERE comment_id = {placeholder}",
                    (comment_id,)
                )
                result = cursor.fetchone()
                if result:
                    comment_owner_id = result[0]
                    
                    # Award points to the person giving the reaction
                    await RankingIntegration.handle_reaction_given(
                        user_id, comment_id, 'comment', reaction_type
                    )
                    
                    # Award points to the person receiving the reaction (only for likes)
                    if reaction_type == 'like' and comment_owner_id != user_id:
                        await RankingIntegration.handle_reaction_received(
                            comment_owner_id, comment_id, 'comment', reaction_type, context
                        )
                        logger.info(f"Awarded reaction points: giver={user_id}, receiver={comment_owner_id}")
        except Exception as e:
            logger.error(f"Error awarding reaction points: {e}")
    
    return success, action, likes, dislikes

def flag_comment(comment_id):
    """Flag a comment for review"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f"UPDATE comments SET flagged = 1 WHERE comment_id = {placeholder}", (comment_id,))
        conn.commit()

def get_user_reaction(user_id, comment_id):
    """Get user's reaction to a specific comment"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f"SELECT reaction_type FROM reactions WHERE user_id = {placeholder} AND target_type = 'comment' AND target_id = {placeholder}",
            (user_id, comment_id)
        )
        result = cursor.fetchone()
        return result[0] if result else None

def get_comment_sequential_number(comment_id):
    """Get the sequential number of a comment within its post"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        # First get the comment's post_id and check if it's a reply
        cursor.execute(
            f"SELECT post_id, parent_comment_id FROM comments WHERE comment_id = {placeholder}",
            (comment_id,)
        )
        comment_info = cursor.fetchone()
        
        if not comment_info:
            return None
        
        post_id, parent_comment_id = comment_info
        
        if parent_comment_id:  # This is a reply
            # Get the sequential reply number within the parent comment
            cursor.execute(f"""
                SELECT COUNT(*) FROM comments 
                WHERE parent_comment_id = {placeholder} AND comment_id <= {placeholder}
            """, (parent_comment_id, comment_id))
            result = cursor.fetchone()
            return result[0] if result else 1
        else:  # This is a main comment
            # Get the sequential comment number within the post
            cursor.execute(f"""
                SELECT COUNT(*) FROM comments 
                WHERE post_id = {placeholder} AND parent_comment_id IS NULL AND comment_id <= {placeholder}
            """, (post_id, comment_id))
            result = cursor.fetchone()
            return result[0] if result else 1

def get_parent_comment_for_reply(comment_id):
    """Get the parent comment details for a reply comment"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        # Get the reply comment details
        cursor.execute(
            f"SELECT parent_comment_id FROM comments WHERE comment_id = {placeholder}",
            (comment_id,)
        )
        result = cursor.fetchone()
        
        if not result or not result[0]:
            return None  # Not a reply
        
        parent_comment_id = result[0]
        
        # Get the parent comment details
        cursor.execute(
            f"SELECT comment_id, post_id, content, timestamp FROM comments WHERE comment_id = {placeholder}",
            (parent_comment_id,)
        )
        parent_comment = cursor.fetchone()
        
        if parent_comment:
            # Get the sequential number of the parent comment
            parent_sequential_number = get_comment_sequential_number(parent_comment_id)
            return {
                'comment_id': parent_comment[0],
                'post_id': parent_comment[1],
                'content': parent_comment[2],
                'timestamp': parent_comment[3],
                'sequential_number': parent_sequential_number
            }
        
        return None


def replace_comment_with_notice(comment_id: int, notice: str = "This comment was removed due to multiple reports.") -> bool:
    """Replace a comment's content with a standard removal notice and flag it.
    Returns True on success.
    """
    try:
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            placeholder = db_conn.get_placeholder()
            cursor.execute(
                f"UPDATE comments SET content = {placeholder}, flagged = 1 WHERE comment_id = {placeholder}",
                (notice, comment_id)
            )
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error replacing comment {comment_id} with notice: {e}")
        return False

def get_comment_reply_level(comment_id):
    """Get the reply level of a comment (0 = main comment, 1 = first reply, 2 = second reply)"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        # Check if it's a main comment
        cursor.execute(
            f"SELECT parent_comment_id FROM comments WHERE comment_id = {placeholder}",
            (comment_id,)
        )
        result = cursor.fetchone()
        
        if not result or not result[0]:
            return 0  # Main comment
        
        parent_comment_id = result[0]
        
        # Check if parent is a main comment or a reply
        cursor.execute(
            f"SELECT parent_comment_id FROM comments WHERE comment_id = {placeholder}",
            (parent_comment_id,)
        )
        parent_result = cursor.fetchone()
        
        if not parent_result or not parent_result[0]:
            return 1  # First-level reply (reply to main comment)
        else:
            return 2  # Second-level reply (reply to first-level reply)

def get_comment_type_prefix(comment_id):
    """Get the appropriate prefix for a comment based on its reply level"""
    # In flat structure, all comments are just "comment" regardless of level
    return "comment"

# Format replies to look like Telegram's native reply feature
def format_reply(parent_text, child_text, parent_author="Anonymous"):
    """Format reply messages to look like Telegram's native reply feature with blockquote"""
    # Truncate parent text if too long for better display
    if len(parent_text) > 150:
        parent_text = parent_text[:150] + "..."
    
    # Use Telegram's native blockquote styling with expandable feature
    return f"<blockquote expandable>{parent_text}</blockquote>\n\n{child_text}"

def format_comment_display(comment_data, user_id, current_page, comment_index):
    """Format a comment for display with optimized data fetching"""
    from html import escape as html_escape
    from utils import format_date_only_html
    from config import COMMENTS_PER_PAGE
    
    comment_id = comment_data['comment_id']
    content = comment_data['content'] or ""
    flagged = comment_data.get('flagged', 0)
    timestamp = comment_data['timestamp']
    likes = comment_data['likes'] if 'likes' in comment_data else 0
    dislikes = comment_data['dislikes'] if 'dislikes' in comment_data else 0
    is_reply = comment_data.get('is_reply', False)
    comment_user_id = comment_data.get('user_id')  # Get commenter's user_id for rank & profile
    is_confessor_comment = comment_data.get('is_confessor_comment', False)
    
    # Debug logging to check if confessor badge will show
    if is_confessor_comment:
        logger.info(f"🖋️ AUTHOR BADGE: Comment {comment_id} by user {comment_user_id} is marked as confessor comment")
    
    # Optional profile link line (deep link back to the bot)
    profile_link_html = ""
    if comment_user_id:
        # Use a simple module-level cache so we only hit the DB once per user per process
        profile = get_cached_user_profile(comment_user_id)
        if profile and profile.get('is_active'):
            try:
                bot_username_clean = BOT_USERNAME.lstrip('@')
                name_raw = ((profile.get('emoji') or '') + ' ' + (profile.get('display_name') or '')).strip()
                if not name_raw:
                    name_raw = "View profile"
                safe_name = html_escape(name_raw)
                # Use inline text link without URL preview
                profile_link_html = f'<a href="https://t.me/{bot_username_clean}?start=profile_{comment_user_id}">{safe_name}</a>'
            except Exception as e:
                logger.error(f"Error building profile link for user {comment_user_id}: {e}")
                profile_link_html = ""
    
    # Calculate sequential comment number based on page and position
    sequential_comment_number = (current_page - 1) * COMMENTS_PER_PAGE + comment_index + 1
    
    # Get user reaction to current comment
    user_reaction = get_user_reaction(user_id, comment_id)
    like_emoji = "👍✅" if user_reaction == "like" else "👍"
    dislike_emoji = "👎✅" if user_reaction == "dislike" else "👎"
    
    # Get commenter's rank for display
    rank_text = ""
    if comment_user_id:
        try:
            user_rank = get_cached_user_rank(comment_user_id)
            if user_rank:
                rank_emoji = user_rank['rank_emoji']
                rank_name = user_rank['rank_name']
                # Format rank with special styling for special ranks
                if user_rank['is_special_rank']:
                    rank_text = f"\n<i>✨ {rank_emoji} {html_escape(rank_name)} ✨</i>"
                else:
                    rank_text = f"\n<i>{rank_emoji} {html_escape(rank_name)}</i>"
        except Exception as e:
            logger.error(f"Error getting rank for user {comment_user_id}: {e}")
            # Don't show rank if there's an error
            rank_text = ""
    
    # Build the text with proper reply formatting
    date_text = format_date_only_html(timestamp)

    # Short label for comments made by the original confessor (shown at the very end)
    confessor_label_suffix = ""
    if is_confessor_comment:
        # Always show author badge, even if profile doesn't exist
        confessor_emoji = '👤'  # Default emoji
        
        # Try to get profile for custom emoji
        try:
            confessor_profile = get_cached_user_profile(comment_user_id)
            if confessor_profile and confessor_profile.get('emoji'):
                confessor_emoji = confessor_profile['emoji']
        except Exception as e:
            logger.error(f"Error getting confessor profile for badge: {e}")
        
        # Show prominent author badge
        confessor_label_suffix = f"\n\n🖋️ <b>{confessor_emoji} Author's Comment</b>"
    
    if is_reply and comment_data.get('original_comment'):
        parent_text = comment_data['original_comment']['content'] or ""
        # Use HTML escaping for safety and format as reply with blockquote
        formatted = format_reply(html_escape(parent_text), html_escape(content))
        # Position rank at bottom right by combining it with comment number
        bottom_line = f"<code>comment# {sequential_comment_number}</code>"
        if rank_text:
            # Add rank to the right side of the bottom line
            bottom_line += f"                    {rank_text.strip()}"
        # Optional profile link line right under the bottom line
        profile_line = f"\n {profile_link_html}" if profile_link_html else ""
        # Confessor label is appended at the very end after the date line
        comment_text = f"{formatted}\n\n{bottom_line}{profile_line}\n{date_text}{confessor_label_suffix}"
    else:
        # If flagged/removed, show standard notice
        if flagged:
            display_content = html_escape("This comment was removed due to multiple reports.")
            # Don't show rank for removed comments
            rank_text = ""
        else:
            display_content = html_escape(content)
        
        # Position rank at bottom right by combining it with date
        bottom_line = date_text
        if rank_text:
            # Add rank to the right side of the bottom line with proper spacing
            bottom_line = f"{date_text}                    {rank_text.strip()}"
        
        # Optional profile link line under the date/rank line
        profile_line = f"\n {profile_link_html}" if profile_link_html else ""
        
        # Confessor label is appended at the very end after date/rank + profile line
        comment_text = f"<b>comment# {sequential_comment_number}</b>\n\n{display_content}\n\n{bottom_line}{profile_line}{confessor_label_suffix}"
    
    # Create standardized reaction buttons with consistent layout
    comment_keyboard = [
        [
            InlineKeyboardButton(f"{like_emoji} {likes}", callback_data=f"like_comment_{comment_id}"),
            InlineKeyboardButton(f"{dislike_emoji} {dislikes}", callback_data=f"dislike_comment_{comment_id}")
        ],
        [
            InlineKeyboardButton("💬 Reply", callback_data=f"reply_comment_{comment_id}"),
            InlineKeyboardButton("⚠️ Report", callback_data=f"report_comment_{comment_id}")
        ]
    ]
    
    return {
        'text': comment_text,
        'reply_markup': InlineKeyboardMarkup(comment_keyboard),
        'parse_mode': 'HTML'
    }

def format_comments_header(total_comments, current_page, total_pages):
    """Format consistent header for comments display"""
    return f"<b>💬 Comments ({total_comments} total)</b>\nPage {current_page} of {total_pages}"

def find_comment_page(comment_id):
    """Find which page a comment is on for navigation"""
    try:
        # Get comment info
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            placeholder = db_conn.get_placeholder()
            cursor.execute(
                f"SELECT post_id, timestamp FROM comments WHERE comment_id = {placeholder}",
                (comment_id,)
            )
            comment_info = cursor.fetchone()
            
            if not comment_info:
                return None
                
            post_id, timestamp = comment_info
            
            # Count comments before this one (chronological order)
            cursor.execute(f"""
                SELECT COUNT(*) FROM comments 
                WHERE post_id = {placeholder} AND timestamp < {placeholder}
                ORDER BY timestamp ASC
            """, (post_id, timestamp))
            comments_before = cursor.fetchone()[0]
            page = (comments_before // COMMENTS_PER_PAGE) + 1
            
            return {
                'page': page,
                'post_id': post_id,
                'comment_id': comment_id
            }
    except Exception as e:
        print(f"Error finding comment page: {e}")
        return None

async def update_channel_message_comment_count(context, post_id):
    """Update the comment count on the channel message.

    IMPORTANT: when we edit the channel message after new comments, we must
    preserve the confessor's profile link line so their name never disappears
    from the post.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Starting update_channel_message_comment_count for post_id: {post_id}")
    logger.info(f"CHANNEL_ID configured as: {CHANNEL_ID}")

    try:
        # Get post info including channel message ID and post_number
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            placeholder = db_conn.get_placeholder()
            cursor.execute(
                f"SELECT post_id, content, category, channel_message_id, approved, post_number FROM posts WHERE post_id = {placeholder}",
                (post_id,),
            )
            post_info = cursor.fetchone()

        if not post_info or not post_info[3]:  # No channel_message_id
            logger.warning(f"No post info or channel_message_id found for post_id: {post_id}")
            return False, "No channel message found"

        post_id, content, category, channel_message_id, approved, post_number = post_info

        if approved != 1:  # Not approved
            logger.warning(f"Post {post_id} is not approved (approved value: {approved}), skipping comment count update")
            return False, "Post not approved"

        # Get current comment count
        comment_count = get_comment_count(post_id)
        logger.info(f"Retrieved comment count for post {post_id}: {comment_count}")

        # Create updated inline buttons with new comment count
        # Strip @ symbol from BOT_USERNAME for URL
        bot_username_clean = BOT_USERNAME.lstrip('@')

        from db import is_post_sensitive
        is_sensitive = is_post_sensitive(post_id)

        # Build updated inline keyboard based on sensitivity
        if is_sensitive:
            keyboard = [
                [
                    InlineKeyboardButton(
                        "👀 View Confession (18+)",
                        url=f"https://t.me/{bot_username_clean}?start=read_{post_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"💬 See Comments ({comment_count})",
                        url=f"https://t.me/{bot_username_clean}?start=view_{post_id}",
                    )
                ],
            ]
        else:
            keyboard = [
                [
                    InlineKeyboardButton(
                        "💬 Add Comment",
                        url=f"https://t.me/{bot_username_clean}?start=comment_{post_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        f"👀 See Comments ({comment_count})",
                        url=f"https://t.me/{bot_username_clean}?start=view_{post_id}",
                    )
                ],
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # For sensitive posts, NEVER replace the warning text/caption.
        # Only update the inline keyboard so the warning message stays forever.
        if is_sensitive:
            logger.info(f"Updating sensitive post {post_id} with comment count {comment_count}")
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=CHANNEL_ID,
                    message_id=channel_message_id,
                    reply_markup=reply_markup,
                )
                logger.info(f"Successfully updated reply markup for sensitive post {post_id}")
            except Exception as e:
                error_msg = f"Failed to update reply markup for sensitive post {post_id}: {e}"
                logger.error(error_msg, exc_info=True)
                # Check if it's a specific Telegram API error
                if hasattr(e, 'message'):
                    logger.error(f"Telegram API error message: {e.message}")
                if hasattr(e, '__dict__'):
                    logger.error(f"Error attributes: {e.__dict__}")
                return False, f"Failed to update channel message: {str(e)}"

            return True, f"Updated comment count to {comment_count} (sensitive post)"

        # ------------------------------------------------------------------
        # Non-sensitive posts: update text/caption BUT keep the profile link
        # exactly like we did when approving the post in approval.py.
        # ------------------------------------------------------------------

        # Convert categories into hashtags
        categories_text = " ".join(
            [f"#{cat.strip().replace(' ', '')}" for cat in category.split(",")]
        )

        # Build the optional profile link HTML for the original confessor
        profile_link_html = ""
        try:
            from html import escape as html_escape

            author_id = get_post_author_id(post_id)
            if author_id:
                author_profile = get_user_profile(author_id)
                if author_profile and author_profile.get('is_active'):
                    name_raw = (
                        (author_profile.get('emoji') or '')
                        + ' '
                        + (author_profile.get('display_name') or '')
                    ).strip()
                    if not name_raw:
                        name_raw = "View profile"
                    safe_name = html_escape(name_raw)
                    profile_link_html = (
                        f"\n\n<a href=\"tg://resolve?domain={bot_username_clean}&start=profile_{author_id}\">{safe_name}</a>"
                    )
        except Exception as e:
            logger.error(
                f"Error building profile link for post {post_id} while updating comments: {e}"
            )
            profile_link_html = ""

        # Check if this is a media post
        logger.info(f"Updating non-sensitive post {post_id} with comment count {comment_count}")
        if is_media_post(post_id):
            # Get media information
            media_info = get_media_info(post_id)
            logger.info(f"Media post detected for post {post_id}, media_info: {media_info}")

            if media_info:
                # Prepare caption with post number, text content, hashtags and profile link
                caption_text = f"<b>Confess # {post_number}</b>\n\n"

                # Add text content if available
                if content and content.strip():
                    caption_text += f"{content}\n\n"

                # Add media caption if available and different from main content
                if media_info.get('caption') and media_info['caption'] != content:
                    caption_text += f"{media_info['caption']}\n\n"

                # Add hashtags
                caption_text += categories_text

                # Append profile link if available (same behavior as approval.py)
                if profile_link_html:
                    caption_text += profile_link_html

                logger.info(f"Updating media message caption for post {post_id}")
                # Update media message caption
                try:
                    await context.bot.edit_message_caption(
                        chat_id=CHANNEL_ID,
                        message_id=channel_message_id,
                        caption=caption_text,
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                    )
                    logger.info(f"Successfully updated media message caption for post {post_id}")
                except Exception as e:
                    error_msg = f"Failed to update media message caption for post {post_id}: {e}"
                    logger.error(error_msg, exc_info=True)
                    if hasattr(e, 'message'):
                        logger.error(f"Telegram API error message: {e.message}")
                    if hasattr(e, '__dict__'):
                        logger.error(f"Error attributes: {e.__dict__}")
                    raise
            else:
                # Media info not found, try as text message fallback
                logger.info(f"Media info not found for post {post_id}, using text message fallback")
                profile_suffix = profile_link_html or ""
                try:
                    await context.bot.edit_message_text(
                        chat_id=CHANNEL_ID,
                        message_id=channel_message_id,
                        text=(
                            f"<b>Confess # {post_number}</b>\n\n"
                            f"{content}\n\n"
                            f"{categories_text}{profile_suffix}"
                        ),
                        parse_mode="HTML",
                        reply_markup=reply_markup,
                        disable_web_page_preview=True
                    )
                    logger.info(f"Successfully updated text message for post {post_id} (fallback)")
                except Exception as e:
                    error_msg = f"Failed to update text message for post {post_id} (fallback): {e}"
                    logger.error(error_msg, exc_info=True)
                    if hasattr(e, 'message'):
                        logger.error(f"Telegram API error message: {e.message}")
                    if hasattr(e, '__dict__'):
                        logger.error(f"Error attributes: {e.__dict__}")
                    raise
        else:
            # Text-only post - use edit_message_text, keep profile suffix
            logger.info(f"Text-only post detected for post {post_id}")
            profile_suffix = profile_link_html or ""
            try:
                await context.bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=channel_message_id,
                    text=(
                        f"<b>Confess # {post_number}</b>\n\n"
                        f"{content}\n\n"
                        f"{categories_text}{profile_suffix}"
                    ),
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
                logger.info(f"Successfully updated text message for post {post_id}")
            except Exception as e:
                error_msg = f"Failed to update text message for post {post_id}: {e}"
                logger.error(error_msg, exc_info=True)
                if hasattr(e, 'message'):
                    logger.error(f"Telegram API error message: {e.message}")
                if hasattr(e, '__dict__'):
                    logger.error(f"Error attributes: {e.__dict__}")
                raise

        logger.info(f"Successfully completed update_channel_message_comment_count for post {post_id} with comment count {comment_count}")
        return True, f"Updated comment count to {comment_count}"

    except Exception as e:
        logger.error(f"Exception in update_channel_message_comment_count for post {post_id}: {e}", exc_info=True)
        return False, f"Failed to update channel message: {str(e)}"
