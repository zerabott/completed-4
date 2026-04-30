"""
Admin Deletion Functions
Handles permanent deletion of posts, comments, and associated data
"""

import logging
from datetime import datetime
from db_connection import get_db_connection
from config import CHANNEL_ID

logger = logging.getLogger(__name__)

def delete_post_completely(post_id: int, admin_user_id: int) -> tuple[bool, dict]:
    """
    Completely delete a post and all associated data including:
    - Comments and their replies
    - All reactions on comments
    - All reports related to the post and its comments
    - The post itself
    
    Returns (success, deletion_stats)
    """
    try:
        logger.info(f"Starting complete deletion of post {post_id} by admin {admin_user_id}")
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # First, verify the post exists and get its details
            cursor.execute(f"SELECT post_id, content, category, approved, channel_message_id FROM posts WHERE post_id = {placeholder}", (post_id,))
            post_data = cursor.fetchone()
            
            if not post_data:
                logger.warning(f"Post {post_id} not found for deletion")
                return False, f"Post #{post_id} not found or may have already been deleted"
            
            post_id_db, content, category, approved, channel_message_id = post_data
            logger.info(f"Found post {post_id}: category={category}, approved={approved}")
            
            # Start transaction
            try:
                if db_conn.use_postgresql:
                    cursor.execute("BEGIN")
                    logger.debug("Started PostgreSQL transaction for post deletion")
                else:
                    cursor.execute("BEGIN TRANSACTION")
                    logger.debug("Started SQLite transaction for post deletion")
            except Exception as e:
                logger.error(f"Failed to start transaction for post {post_id}: {e}")
                return False, f"Failed to start database transaction: {str(e)}"
            
            try:
                # Get all comment IDs associated with this post (including replies)
                logger.debug(f"Fetching comments for post {post_id}")
                cursor.execute(f"SELECT comment_id FROM comments WHERE post_id = {placeholder}", (post_id,))
                comment_ids = [row[0] for row in cursor.fetchall()]
                logger.debug(f"Found {len(comment_ids)} comments to delete")
                
                deletion_stats = {
                    'comments_deleted': len(comment_ids),
                    'reactions_deleted': 0,
                    'reports_deleted': 0
                }
                
                if comment_ids:
                    # Delete all reactions on these comments (from reactions table)
                    logger.debug(f"Deleting reactions on {len(comment_ids)} comments")
                    placeholders_str = ','.join([placeholder for _ in comment_ids])
                    cursor.execute(f"SELECT COUNT(*) FROM reactions WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", comment_ids)
                    reactions_count = cursor.fetchone()[0]
                    deletion_stats['reactions_deleted'] = reactions_count
                    logger.debug(f"Found {reactions_count} comment reactions to delete")
                    
                    cursor.execute(f"DELETE FROM reactions WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", comment_ids)
                    
                    # Delete all reports on these comments
                    logger.debug(f"Deleting reports on {len(comment_ids)} comments")
                    cursor.execute(f"SELECT COUNT(*) FROM reports WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", comment_ids)
                    comment_reports_count = cursor.fetchone()[0]
                    deletion_stats['reports_deleted'] += comment_reports_count
                    logger.debug(f"Found {comment_reports_count} comment reports to delete")
                    
                    cursor.execute(f"DELETE FROM reports WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", comment_ids)
                    
                    # Delete all comments
                    logger.debug(f"Deleting {len(comment_ids)} comments")
                    cursor.execute(f"DELETE FROM comments WHERE post_id = {placeholder}", (post_id,))
                    actual_comments_deleted = cursor.rowcount
                    if actual_comments_deleted != len(comment_ids):
                        logger.warning(f"Expected to delete {len(comment_ids)} comments but deleted {actual_comments_deleted}")
                
                # Delete reports on the post itself
                logger.debug(f"Deleting reports on post {post_id}")
                cursor.execute(f"SELECT COUNT(*) FROM reports WHERE target_type = 'post' AND target_id = {placeholder}", (post_id,))
                post_reports_count = cursor.fetchone()[0]
                deletion_stats['reports_deleted'] += post_reports_count
                logger.debug(f"Found {post_reports_count} post reports to delete")
                
                cursor.execute(f"DELETE FROM reports WHERE target_type = 'post' AND target_id = {placeholder}", (post_id,))
                
                # Delete any reactions on the post (if they exist)
                logger.debug(f"Deleting reactions on post {post_id}")
                cursor.execute(f"DELETE FROM reactions WHERE target_type = 'post' AND target_id = {placeholder}", (post_id,))
                post_reactions_deleted = cursor.rowcount
                deletion_stats['reactions_deleted'] += post_reactions_deleted
                logger.debug(f"Deleted {post_reactions_deleted} post reactions")
                
                # Finally, delete the post itself
                logger.debug(f"Deleting post {post_id} record")
                cursor.execute(f"DELETE FROM posts WHERE post_id = {placeholder}", (post_id,))
                if cursor.rowcount == 0:
                    raise Exception(f"Post {post_id} could not be deleted - it may have been deleted by another admin")
                logger.debug(f"Successfully deleted post {post_id} record")
                
                # Log the deletion action
                try:
                    log_admin_deletion(
                        admin_user_id=admin_user_id,
                        action_type="DELETE_POST",
                        target_type="post",
                        target_id=post_id,
                        details={
                            "content_preview": content[:100] + "..." if len(content) > 100 else content,
                            "category": category,
                            "was_approved": bool(approved),
                            "channel_message_id": channel_message_id,
                            "deletion_stats": deletion_stats,
                            "reason": "Admin deletion"
                        }
                    )
                    logger.debug(f"Logged admin deletion action for post {post_id}")
                except Exception as e:
                    logger.warning(f"Failed to log admin deletion for post {post_id}: {e}")
                    # Don't fail the entire deletion for logging issues
                
                # Commit the transaction
                try:
                    if db_conn.use_postgresql:
                        cursor.execute("COMMIT")
                        logger.debug("Committed PostgreSQL transaction")
                    else:
                        cursor.execute("COMMIT")
                        logger.debug("Committed SQLite transaction")
                        
                    conn.commit()  # Also call conn.commit() for safety
                    logger.debug("Called conn.commit() for safety")
                except Exception as e:
                    logger.error(f"Failed to commit transaction for post {post_id}: {e}")
                    raise e
                
                logger.info(f"Successfully completed deletion of post {post_id}: {deletion_stats}")
                return True, deletion_stats
                
            except Exception as e:
                logger.error(f"Error during post deletion transaction for post {post_id}: {e}")
                try:
                    if db_conn.use_postgresql:
                        cursor.execute("ROLLBACK")
                        logger.debug("Rolled back PostgreSQL transaction")
                    else:
                        cursor.execute("ROLLBACK")
                        logger.debug("Rolled back SQLite transaction")
                    conn.rollback()
                    logger.debug("Called conn.rollback()")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction for post {post_id}: {rollback_error}")
                    
                # Provide more specific error messages based on error type
                error_str = str(e).lower()
                if "foreign key" in error_str or "constraint" in error_str:
                    error_msg = f"Database constraint error - there may be related data preventing deletion: {str(e)}"
                elif "permission" in error_str or "access denied" in error_str:
                    error_msg = f"Database permission error - insufficient privileges: {str(e)}"
                elif "connection" in error_str or "timeout" in error_str or "network" in error_str:
                    error_msg = f"Database connection error - network or timeout issue: {str(e)}"
                elif "lock" in error_str or "deadlock" in error_str:
                    error_msg = f"Database lock error - resource temporarily unavailable: {str(e)}"
                elif "syntax" in error_str:
                    error_msg = f"Database query error - please contact administrator: {str(e)}"
                else:
                    error_msg = f"Database error during deletion: {str(e)}"
                    
                return False, error_msg
            
    except Exception as e:
        logger.error(f"Outer error deleting post {post_id}: {e}")
        # Provide more specific error messages for outer exceptions too
        error_str = str(e).lower()
        if "connection" in error_str or "network" in error_str:
            error_msg = f"Database connection failed - check network connectivity: {str(e)}"
        elif "permission" in error_str or "access" in error_str:
            error_msg = f"Database access error - check permissions: {str(e)}"
        elif "module" in error_str or "import" in error_str:
            error_msg = f"System configuration error - missing dependencies: {str(e)}"
        else:
            error_msg = f"System error during post deletion: {str(e)}"
        return False, error_msg


def delete_comment_completely(comment_id: int, admin_user_id: int) -> tuple[bool, dict]:
    """
    Completely delete a comment and all associated data including:
    - All replies to this comment
    - All reactions on the comment and its replies
    - All reports related to the comment and its replies
    
    Returns (success, deletion_stats)
    """
    try:
        logger.info(f"Starting complete deletion of comment {comment_id} by admin {admin_user_id}")
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # First, verify the comment exists and get its details
            cursor.execute(f"SELECT comment_id, post_id, content, parent_comment_id FROM comments WHERE comment_id = {placeholder}", (comment_id,))
            comment_data = cursor.fetchone()
            
            if not comment_data:
                logger.warning(f"Comment {comment_id} not found for deletion")
                return False, f"Comment #{comment_id} not found or may have already been deleted"
            
            comment_id_db, post_id, content, parent_comment_id = comment_data
            logger.info(f"Found comment {comment_id}: post_id={post_id}, is_reply={bool(parent_comment_id)}")
            
            # Start transaction
            try:
                if db_conn.use_postgresql:
                    cursor.execute("BEGIN")
                    logger.debug("Started PostgreSQL transaction for comment deletion")
                else:
                    cursor.execute("BEGIN TRANSACTION")
                    logger.debug("Started SQLite transaction for comment deletion")
            except Exception as e:
                logger.error(f"Failed to start transaction for comment {comment_id}: {e}")
                return False, f"Failed to start database transaction: {str(e)}"
        
            try:
                deletion_stats = {
                    'comments_deleted': 1,  # The main comment
                    'replies_deleted': 0,
                    'reactions_deleted': 0,
                    'reports_deleted': 0
                }
                
                # Get all reply IDs to this comment
                logger.debug(f"Fetching replies for comment {comment_id}")
                cursor.execute(f"SELECT comment_id FROM comments WHERE parent_comment_id = {placeholder}", (comment_id,))
                reply_ids = [row[0] for row in cursor.fetchall()]
                deletion_stats['replies_deleted'] = len(reply_ids)
                logger.debug(f"Found {len(reply_ids)} replies to delete")
                
                # Collect all comment IDs that will be deleted (main comment + replies)
                all_comment_ids = [comment_id] + reply_ids
                logger.debug(f"Total comments to delete: {len(all_comment_ids)} (1 main + {len(reply_ids)} replies)")
                
                if all_comment_ids:
                    # Delete all reactions on these comments (from reactions table)
                    logger.debug(f"Deleting reactions on {len(all_comment_ids)} comments")
                    placeholders_str = ','.join([placeholder for _ in all_comment_ids])
                    cursor.execute(f"SELECT COUNT(*) FROM reactions WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", all_comment_ids)
                    reactions_count = cursor.fetchone()[0]
                    deletion_stats['reactions_deleted'] = reactions_count
                    logger.debug(f"Found {reactions_count} reactions to delete")
                    
                    cursor.execute(f"DELETE FROM reactions WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", all_comment_ids)
                    
                    # Delete all reports on these comments
                    logger.debug(f"Deleting reports on {len(all_comment_ids)} comments")
                    cursor.execute(f"SELECT COUNT(*) FROM reports WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", all_comment_ids)
                    reports_count = cursor.fetchone()[0]
                    deletion_stats['reports_deleted'] = reports_count
                    logger.debug(f"Found {reports_count} reports to delete")
                    
                    cursor.execute(f"DELETE FROM reports WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", all_comment_ids)
                    
                    # Delete all replies first
                    if reply_ids:
                        logger.debug(f"Deleting {len(reply_ids)} replies")
                        cursor.execute(f"DELETE FROM comments WHERE parent_comment_id = {placeholder}", (comment_id,))
                        actual_replies_deleted = cursor.rowcount
                        if actual_replies_deleted != len(reply_ids):
                            logger.warning(f"Expected to delete {len(reply_ids)} replies but deleted {actual_replies_deleted}")
                    
                    # Delete the main comment
                    logger.debug(f"Deleting main comment {comment_id}")
                    cursor.execute(f"DELETE FROM comments WHERE comment_id = {placeholder}", (comment_id,))
                    if cursor.rowcount == 0:
                        raise Exception(f"Comment {comment_id} could not be deleted - it may have been deleted by another admin")
                    logger.debug(f"Successfully deleted comment {comment_id} record")
                
                # Log the deletion action
                try:
                    log_admin_deletion(
                        admin_user_id=admin_user_id,
                        action_type="DELETE_COMMENT",
                        target_type="comment",
                        target_id=comment_id,
                        details={
                            "post_id": post_id,
                            "content_preview": content[:100] + "..." if len(content) > 100 else content,
                            "is_reply": bool(parent_comment_id),
                            "parent_comment_id": parent_comment_id,
                            "deletion_stats": deletion_stats,
                            "reason": "Admin deletion"
                        }
                    )
                    logger.debug(f"Logged admin deletion action for comment {comment_id}")
                except Exception as e:
                    logger.warning(f"Failed to log admin deletion for comment {comment_id}: {e}")
                    # Don't fail the entire deletion for logging issues
                
                # Commit the transaction
                try:
                    if db_conn.use_postgresql:
                        cursor.execute("COMMIT")
                        logger.debug("Committed PostgreSQL transaction")
                    else:
                        cursor.execute("COMMIT")
                        logger.debug("Committed SQLite transaction")
                        
                    conn.commit()  # Also call conn.commit() for safety
                    logger.debug("Called conn.commit() for safety")
                except Exception as e:
                    logger.error(f"Failed to commit transaction for comment {comment_id}: {e}")
                    raise e
                
                logger.info(f"Successfully completed deletion of comment {comment_id}: {deletion_stats}")
                return True, deletion_stats
                
            except Exception as e:
                logger.error(f"Error during comment deletion transaction for comment {comment_id}: {e}")
                try:
                    if db_conn.use_postgresql:
                        cursor.execute("ROLLBACK")
                        logger.debug("Rolled back PostgreSQL transaction")
                    else:
                        cursor.execute("ROLLBACK")
                        logger.debug("Rolled back SQLite transaction")
                    conn.rollback()
                    logger.debug("Called conn.rollback()")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction for comment {comment_id}: {rollback_error}")
                    
                # Provide more specific error messages based on error type
                error_str = str(e).lower()
                if "foreign key" in error_str or "constraint" in error_str:
                    error_msg = f"Database constraint error - there may be related data preventing deletion: {str(e)}"
                elif "permission" in error_str or "access denied" in error_str:
                    error_msg = f"Database permission error - insufficient privileges: {str(e)}"
                elif "connection" in error_str or "timeout" in error_str or "network" in error_str:
                    error_msg = f"Database connection error - network or timeout issue: {str(e)}"
                elif "lock" in error_str or "deadlock" in error_str:
                    error_msg = f"Database lock error - resource temporarily unavailable: {str(e)}"
                elif "syntax" in error_str:
                    error_msg = f"Database query error - please contact administrator: {str(e)}"
                else:
                    error_msg = f"Database error during deletion: {str(e)}"
                    
                return False, error_msg
                
    except Exception as e:
        logger.error(f"Outer error deleting comment {comment_id}: {e}")
        # Provide more specific error messages for outer exceptions too
        error_str = str(e).lower()
        if "connection" in error_str or "network" in error_str:
            error_msg = f"Database connection failed - check network connectivity: {str(e)}"
        elif "permission" in error_str or "access" in error_str:
            error_msg = f"Database access error - check permissions: {str(e)}"
        elif "module" in error_str or "import" in error_str:
            error_msg = f"System configuration error - missing dependencies: {str(e)}"
        else:
            error_msg = f"System error during comment deletion: {str(e)}"
        return False, error_msg


def log_admin_deletion(admin_user_id: int, action_type: str, target_type: str, target_id: int, details: dict):
    """
    Log admin deletion actions for audit purposes
    """
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create admin_actions table if it doesn't exist
            if db_conn.use_postgresql:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS admin_actions (
                        id SERIAL PRIMARY KEY,
                        admin_user_id INTEGER NOT NULL,
                        action_type VARCHAR(255) NOT NULL,
                        target_type VARCHAR(255) NOT NULL,
                        target_id INTEGER NOT NULL,
                        details TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS admin_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        admin_user_id INTEGER NOT NULL,
                        action_type TEXT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id INTEGER NOT NULL,
                        details TEXT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            # Insert the log entry
            import json
            cursor.execute(f"""
                INSERT INTO admin_actions (admin_user_id, action_type, target_type, target_id, details)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, (admin_user_id, action_type, target_type, target_id, json.dumps(details)))
            
            conn.commit()
            
        logger.info(f"Admin {admin_user_id} performed {action_type} on {target_type} #{target_id}")
        
    except Exception as e:
        logger.error(f"Error logging admin deletion: {e}")


def get_post_details_for_deletion(post_id: int) -> dict:
    """
    Get post details for deletion confirmation
    """
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT p.post_id, p.content, p.category, p.timestamp, p.approved, 
                       p.channel_message_id, p.post_number,
                       COUNT(c.comment_id) as comment_count
                FROM posts p
                LEFT JOIN comments c ON p.post_id = c.post_id
                WHERE p.post_id = {placeholder}
                GROUP BY p.post_id, p.content, p.category, p.timestamp, p.approved, p.channel_message_id, p.post_number
            """, (post_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return None
            
            post_data = {
                'id': result[0],
                'content': result[1],
                'category': result[2],
                'timestamp': result[3],
                'approved': result[4],
                'channel_message_id': result[5],
                'post_number': result[6],
                'comment_count': result[7]
            }
            
            return post_data
        
    except Exception as e:
        logger.error(f"Error getting post details: {e}")
        return None


def get_comment_details_for_deletion(comment_id: int) -> dict:
    """
    Get comment details for deletion confirmation
    """
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(f"""
                SELECT c.comment_id, c.post_id, c.content, c.timestamp, c.parent_comment_id,
                       COUNT(replies.comment_id) as reply_count
                FROM comments c
                LEFT JOIN comments replies ON c.comment_id = replies.parent_comment_id
                WHERE c.comment_id = {placeholder}
                GROUP BY c.comment_id, c.post_id, c.content, c.timestamp, c.parent_comment_id
            """, (comment_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return None
            
            comment_data = {
                'id': result[0],
                'post_id': result[1],
                'content': result[2],
                'timestamp': result[3],
                'parent_comment_id': result[4],
                'reply_count': result[5]
            }
            
            return comment_data
        
    except Exception as e:
        logger.error(f"Error getting comment details: {e}")
        return None


def clear_reports_for_content(target_type: str, target_id: int) -> tuple[bool, int]:
    """
    Clear all reports for a specific piece of content without deleting the content
    """
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Count reports before deletion
            cursor.execute(f"SELECT COUNT(*) FROM reports WHERE target_type = {placeholder} AND target_id = {placeholder}", (target_type, target_id))
            report_count = cursor.fetchone()[0]
            
            if report_count == 0:
                return True, 0
            
            # Delete the reports
            cursor.execute(f"DELETE FROM reports WHERE target_type = {placeholder} AND target_id = {placeholder}", (target_type, target_id))
            
            # Log the action (using dummy admin user ID since it's not passed)
            log_admin_deletion(
                admin_user_id=0,  # Dummy admin user ID
                action_type="CLEAR_REPORTS",
                target_type=target_type,
                target_id=target_id,
                details={
                    "reports_cleared": report_count,
                    "reason": "Admin cleared reports"
                }
            )
            
            conn.commit()
        
        return True, report_count
        
    except Exception as e:
        logger.error(f"Error clearing reports: {e}")
        return False, 0


def replace_comment_with_message(comment_id: int, admin_user_id: int, replacement_message: str = "[This comment has been removed by moderators]") -> tuple[bool, dict]:
    """
    Replace a comment's content with a removal message while preserving the comment structure.
    Also replaces any replies to preserve the conversation flow.
    
    Returns (success, replacement_stats)
    """
    try:
        db_conn = get_db_connection()
        placeholder = db_conn.get_placeholder()
        
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # First, verify the comment exists and get its details
            cursor.execute(f"SELECT comment_id, post_id, content, parent_comment_id FROM comments WHERE comment_id = {placeholder}", (comment_id,))
            comment_data = cursor.fetchone()
            
            if not comment_data:
                return False, {"error": f"Comment #{comment_id} not found"}
            
            comment_id_db, post_id, original_content, parent_comment_id = comment_data
            
            # Start transaction
            if db_conn.use_postgresql:
                cursor.execute("BEGIN")
            else:
                cursor.execute("BEGIN TRANSACTION")
            
            try:
                replacement_stats = {
                    'comments_replaced': 0,
                    'replies_replaced': 0,
                    'reports_cleared': 0
                }
                
                # Replace the main comment content
                cursor.execute(f"UPDATE comments SET content = {placeholder}, flagged = 1 WHERE comment_id = {placeholder}", (replacement_message, comment_id))
                replacement_stats['comments_replaced'] = 1
                
                # Get all reply IDs to this comment
                cursor.execute(f"SELECT comment_id FROM comments WHERE parent_comment_id = {placeholder}", (comment_id,))
                reply_ids = [row[0] for row in cursor.fetchall()]
                
                # Replace content of all replies too (to maintain conversation flow)
                if reply_ids:
                    placeholders_str = ','.join([placeholder for _ in reply_ids])
                    cursor.execute(f"UPDATE comments SET content = {placeholder}, flagged = 1 WHERE comment_id IN ({placeholders_str})", ["[This reply has been removed by moderators]"] + reply_ids)
                    replacement_stats['replies_replaced'] = len(reply_ids)
                
                # Clear all reports on the comment and its replies
                all_comment_ids = [comment_id] + reply_ids
                
                if all_comment_ids:
                    # Count reports before clearing them
                    placeholders_str = ','.join([placeholder for _ in all_comment_ids])
                    cursor.execute(f"SELECT COUNT(*) FROM reports WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", all_comment_ids)
                    reports_count = cursor.fetchone()[0]
                    replacement_stats['reports_cleared'] = reports_count
                    
                    # Clear the reports
                    cursor.execute(f"DELETE FROM reports WHERE target_type = 'comment' AND target_id IN ({placeholders_str})", all_comment_ids)
                
                # Log the replacement action
                log_admin_deletion(
                    admin_user_id=admin_user_id,
                    action_type="REPLACE_COMMENT",
                    target_type="comment",
                    target_id=comment_id,
                    details={
                        "post_id": post_id,
                        "original_content_preview": original_content[:100] + "..." if len(original_content) > 100 else original_content,
                        "replacement_message": replacement_message,
                        "is_reply": bool(parent_comment_id),
                        "parent_comment_id": parent_comment_id,
                        "replacement_stats": replacement_stats,
                        "reason": "Admin content replacement due to reports"
                    }
                )
                
                # Commit the transaction
                if db_conn.use_postgresql:
                    cursor.execute("COMMIT")
                else:
                    cursor.execute("COMMIT")
                    
                conn.commit()  # Also call conn.commit() for safety
                
                return True, replacement_stats
                
            except Exception as e:
                if db_conn.use_postgresql:
                    cursor.execute("ROLLBACK")
                else:
                    cursor.execute("ROLLBACK")
                conn.rollback()
                logger.error(f"Error during comment replacement transaction: {e}")
                return False, {"error": f"Database error during replacement: {str(e)}"}
                
    except Exception as e:
        logger.error(f"Error replacing comment {comment_id}: {e}")
        return False, {"error": f"Error replacing comment: {str(e)}"}


async def delete_channel_message(context, channel_message_id: int) -> tuple[bool, str]:
    """
    Delete a message from the channel
    """
    try:
        if not channel_message_id:
            return True, "No channel message to delete"
        
        await context.bot.delete_message(
            chat_id=CHANNEL_ID,
            message_id=channel_message_id
        )
        
        return True, "Channel message deleted"
        
    except Exception as e:
        logger.warning(f"Could not delete channel message {channel_message_id}: {e}")
        return False, f"Could not delete channel message: {str(e)}"
