"""
Admin Report Management for Enhanced Reporting System
Handles admin actions for reported content including deletion and report dismissal
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_IDS, CHANNEL_ID
from utils import escape_markdown_text, truncate_text
from enhanced_reporting import dismiss_reports_for_content
from db_connection import get_db_connection, execute_query, adapt_query

logger = logging.getLogger(__name__)

async def handle_admin_delete_comment(update, context):
    """Handle admin deleting a reported comment"""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data to get comment ID
    comment_id = int(query.data.replace("admin_delete_comment_", ""))
    
    # Get comment details before deletion
    try:
        detail_query = adapt_query("SELECT comment_id, post_id, content FROM comments WHERE comment_id = ?")
        comment_info = execute_query(detail_query, (comment_id,), fetch='one')
    except Exception as e:
        logger.error(f"Error getting comment details: {e}")
        comment_info = None
    
    if not comment_info:
        await query.edit_message_text(
            "❗ **Comment Not Found**\\n\\n"
            "The comment may have already been deleted\\.",
            parse_mode="MarkdownV2"
        )
        return
    
    comment_id, post_id, content = comment_info
    content_preview = truncate_text(content, 100)
    
    # Confirm replacement (not deletion)
    confirm_keyboard = [
        [
            InlineKeyboardButton("🔄 Yes, Replace Content", callback_data=f"confirm_delete_comment_{comment_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_delete_comment_{comment_id}")
        ]
    ]
    confirm_markup = InlineKeyboardMarkup(confirm_keyboard)
    
    await query.edit_message_text(
        f"🔄 *Confirm Comment Replacement*\\n\\n"
        f"*Comment \\#{comment_id}* \\(Post \\#{post_id}\\)\\n"
        f"*Content:* _{escape_markdown_text(content_preview)}_\\n\\n"
        f"⚠️ The comment content will be replaced with a removal message\\. "
        f"The comment structure will be preserved\\. Continue?",
        reply_markup=confirm_markup,
        parse_mode="MarkdownV2"
    )

async def handle_admin_delete_post(update, context):
    """Handle admin deleting a reported post"""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data to get post ID
    post_id = int(query.data.replace("admin_delete_post_", ""))
    
    # Get post details before deletion
    try:
        detail_query = adapt_query("SELECT post_id, content, category, channel_message_id FROM posts WHERE post_id = ?")
        post_info = execute_query(detail_query, (post_id,), fetch='one')
    except Exception as e:
        logger.error(f"Error getting post details: {e}")
        post_info = None
    
    if not post_info:
        await query.edit_message_text(
            "❗ **Post Not Found**\\n\\n"
            "The post may have already been deleted\\.",
            parse_mode="MarkdownV2"
        )
        return
    
    post_id, content, category, channel_message_id = post_info
    content_preview = truncate_text(content, 100)
    
    # Confirm deletion
    confirm_keyboard = [
        [
            InlineKeyboardButton("🗑️ Yes, Delete", callback_data=f"confirm_delete_post_{post_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_delete_post_{post_id}")
        ]
    ]
    confirm_markup = InlineKeyboardMarkup(confirm_keyboard)
    
    await query.edit_message_text(
        f"🗑️ *Confirm Post Deletion*\\n\\n"
        f"*Post \\#{post_id}*\\n"
        f"*Category:* {escape_markdown_text(category)}\\n"
        f"*Content:* _{escape_markdown_text(content_preview)}_\\n\\n"
        f"⚠️ This will delete the post from database and channel\\. Continue?",
        reply_markup=confirm_markup,
        parse_mode="MarkdownV2"
    )

async def handle_confirm_delete_comment(update, context):
    """Handle confirmed comment replacement (not deletion)"""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data to get comment ID
    comment_id = int(query.data.replace("confirm_delete_comment_", ""))
    
    try:
        # Import the replacement function
        from admin_deletion import replace_comment_with_message
        
        # Get admin user ID for logging
        admin_user_id = query.from_user.id
        
        # Replace the comment content instead of deleting
        success, replacement_stats = replace_comment_with_message(
            comment_id=comment_id,
            admin_user_id=admin_user_id,
            replacement_message="[This comment has been removed by moderators]"
        )
        
        if success:
            # Dismiss all reports for this comment (already handled in replace function)
            await query.edit_message_text(
                f"✅ *Comment Replaced Successfully*\\n\\n"
                f"*Comment \\#{comment_id}* content has been replaced with a removal message\\. "
                f"*Comments replaced:* {replacement_stats['comments_replaced']}\\n"
                f"*Replies replaced:* {replacement_stats['replies_replaced']}\\n"
                f"*Reports cleared:* {replacement_stats['reports_cleared']}\\n\\n"
                f"The original comment content has been hidden while preserving the comment structure\\.",
                parse_mode="MarkdownV2"
            )
            
            logger.info(f"Admin replaced comment {comment_id} content with removal message")
        else:
            error_message = replacement_stats.get('error', 'Unknown error')
            await query.edit_message_text(
                f"❗ *Replacement Failed*\\n\\n"
                f"Error: {escape_markdown_text(error_message)}",
                parse_mode="MarkdownV2"
            )
            
    except Exception as e:
        logger.error(f"Error replacing comment {comment_id}: {e}")
        await query.edit_message_text(
            "❗ *Replacement Failed*\\n\\n"
            "There was an error replacing the comment\\. Please try again\\.",
            parse_mode="MarkdownV2"
        )

async def handle_confirm_delete_post(update, context):
    """Handle confirmed post deletion"""
    query = update.callback_query
    await query.answer()
    
    # Parse callback data to get post ID
    post_id = int(query.data.replace("confirm_delete_post_", ""))
    
    try:
        # Delete the post from database
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get post info for logging
            info_query = adapt_query("SELECT content, category, channel_message_id FROM posts WHERE post_id = ?")
            cursor.execute(info_query, (post_id,))
            post_info = cursor.fetchone()
            
            if post_info:
                content, category, channel_message_id = post_info
                
                # Delete the post
                delete_post_query = adapt_query("DELETE FROM posts WHERE post_id = ?")
                cursor.execute(delete_post_query, (post_id,))
                
                # Delete all comments for this post
                delete_comments_query = adapt_query("DELETE FROM comments WHERE post_id = ?")
                cursor.execute(delete_comments_query, (post_id,))
                
                # Delete related reactions for post
                delete_post_reactions_query = adapt_query("DELETE FROM reactions WHERE target_type = 'post' AND target_id = ?")
                cursor.execute(delete_post_reactions_query, (post_id,))
                
                # Delete related reactions for comments
                delete_comment_reactions_query = adapt_query("""
                    DELETE FROM reactions WHERE target_type = 'comment' AND target_id IN 
                    (SELECT comment_id FROM comments WHERE post_id = ?)
                """)
                cursor.execute(delete_comment_reactions_query, (post_id,))
                
                if db_conn.use_postgresql:
                    conn.commit()
                
                # Try to delete from channel if channel_message_id exists
                if channel_message_id and CHANNEL_ID:
                    try:
                        await context.bot.delete_message(
                            chat_id=CHANNEL_ID,
                            message_id=channel_message_id
                        )
                        channel_deleted = "✅ Also deleted from channel"
                    except Exception as e:
                        logger.error(f"Failed to delete post {post_id} from channel: {e}")
                        channel_deleted = "⚠️ Could not delete from channel"
                else:
                    channel_deleted = "ℹ️ No channel message to delete"
                
                # Dismiss all reports for this post
                dismissed_count = dismiss_reports_for_content("post", post_id)
                
                await query.edit_message_text(
                    f"✅ *Post Deleted Successfully*\\n\\n"
                    f"*Post \\#{post_id}* has been permanently deleted\\. "
                    f"*Reports dismissed:* {dismissed_count}\\n\\n"
                    f"{channel_deleted}\\n"
                    f"The post, all comments, and associated data have been removed\\.",
                    parse_mode="MarkdownV2"
                )
                
                logger.info(f"Admin deleted post {post_id} ({category})")
            else:
                await query.edit_message_text(
                    "❗ *Post Not Found*\\n\\n"
                    "The post may have already been deleted\\.",
                    parse_mode="MarkdownV2"
                )
                
    except Exception as e:
        logger.error(f"Error deleting post {post_id}: {e}")
        await query.edit_message_text(
            "❗ *Deletion Failed*\\n\\n"
            "There was an error deleting the post\\. Please try again\\.",
            parse_mode="MarkdownV2"
        )

async def handle_cancel_delete_comment(update, context):
    """Handle cancelled comment replacement"""
    query = update.callback_query
    await query.answer("Replacement cancelled")
    
    comment_id = int(query.data.replace("cancel_delete_comment_", ""))
    
    await query.edit_message_text(
        f"❌ *Replacement Cancelled*\\n\\n"
        f"Comment \\#{comment_id} was not modified\\.",
        parse_mode="MarkdownV2"
    )

async def handle_cancel_delete_post(update, context):
    """Handle cancelled post deletion"""
    query = update.callback_query
    await query.answer("Deletion cancelled")
    
    post_id = int(query.data.replace("cancel_delete_post_", ""))
    
    await query.edit_message_text(
        f"❌ *Deletion Cancelled*\\n\\n"
        f"Post \\#{post_id} was not deleted\\.",
        parse_mode="MarkdownV2"
    )
