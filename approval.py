import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import ADMIN_IDS, CHANNEL_ID, BOT_USERNAME, MINI_ADMIN_IDS
from db import get_comment_count, get_user_profile
from db_connection import get_db_connection
from submission import get_post_with_media, is_media_post, get_media_info, get_media_type_emoji

# Import ranking system integration
from ranking_integration import award_points_for_confession_approval, RankingIntegration

def approve_post(post_id, message_id, post_number):
    """Approve a post and save channel message ID with sequential post number. Clears edited flag if present."""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        # Clear is_edited flag when approving (it's no longer pending edit)
        cursor.execute(
            f"UPDATE posts SET approved=1, channel_message_id={placeholder}, post_number={placeholder}, is_edited=0, edited_timestamp=NULL WHERE post_id={placeholder}",
            (message_id, post_number, post_id)
        )
        conn.commit()

def get_channel_message_id(post_id):
    """Get the channel message ID for an approved post"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f"SELECT channel_message_id FROM posts WHERE post_id = {placeholder} AND approved = 1",
            (post_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

async def update_channel_message(context, post_id: int, new_content: str, category: str, is_sensitive: bool = False):
    """Update an existing channel message with edited content"""
    from config import CHANNEL_ID, BOT_USERNAME
    from submission import get_media_info, is_media_post
    from html import escape as html_escape
    
    channel_message_id = get_channel_message_id(post_id)
    if not channel_message_id:
        logging.error(f"No channel message found for post {post_id}")
        return False, "Channel message not found"
    
    try:
        # Get media info if this is a media post
        is_media = is_media_post(post_id)
        media_info = get_media_info(post_id) if is_media else None
        
        # Build the updated caption/content
        bot_username_clean = BOT_USERNAME.lstrip('@')
        
        if is_sensitive:
            # For sensitive posts, just update the warning message
            updated_text = (
                f"<b>⚠️ Sensitive Confession # Updated</b>\n\n"
                f"This confession has been edited by the author.\n\n"
                f"Tap the button below to view it privately and anonymously via the bot."
            )
            keyboard = [
                [InlineKeyboardButton("👀 View Confession (18+)", url=f"https://t.me/{bot_username_clean}?start=read_{post_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.edit_message_text(
                chat_id=CHANNEL_ID,
                message_id=channel_message_id,
                text=updated_text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        else:
            # Regular post - update content/media
            if is_media and media_info:
                # For media posts, we need to edit the media caption
                updated_caption = f"<b>Confession # Updated</b>\n\n"
                
                # Add text content if available
                if new_content and new_content.strip():
                    updated_caption += f"{new_content}\n\n"
                
                # Add media caption if available
                if media_info.get('caption') and media_info['caption'] != new_content:
                    updated_caption += f"{media_info['caption']}\n\n"
                
                # Add hashtags
                categories = category
                categories_text = " ".join([f"#{cat.strip().replace(' ', '')}" for cat in categories.split(",")])
                updated_caption += categories_text
                
                # Try to edit the media message
                try:
                    if media_info['type'] == 'photo':
                        await context.bot.edit_message_caption(
                            chat_id=CHANNEL_ID,
                            message_id=channel_message_id,
                            caption=updated_caption,
                            parse_mode="HTML"
                        )
                    elif media_info['type'] in ['video', 'animation']:
                        # For video/animation, we can only edit caption if media stays the same
                        await context.bot.edit_message_caption(
                            chat_id=CHANNEL_ID,
                            message_id=channel_message_id,
                            caption=updated_caption,
                            parse_mode="HTML"
                        )
                    else:
                        # Fallback: delete old message and send new one (complex for documents)
                        logging.warning(f"Cannot edit {media_info['type']} caption, sending replacement")
                        return False, "Media type cannot be edited, requires manual update"
                except Exception as media_edit_error:
                    logging.error(f"Failed to edit media caption: {media_edit_error}")
                    return False, f"Failed to edit media: {media_edit_error}"
            else:
                # Text-only post - simple edit
                updated_text = f"<b>Confession # Updated</b>\n\n{new_content}\n\n{category}"
                keyboard = [
                    [InlineKeyboardButton("💬 Add Comment", url=f"https://t.me/{bot_username_clean}?start=comment_{post_id}")],
                    [InlineKeyboardButton("👀 See Comments", url=f"https://t.me/{bot_username_clean}?start=view_{post_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=channel_message_id,
                    text=updated_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
        
        logging.info(f"Successfully updated channel message {channel_message_id} for post {post_id}")
        return True, "Message updated successfully"
        
    except Exception as e:
        logging.error(f"Error updating channel message for post {post_id}: {e}")
        return False, f"Failed to update: {e}"

def reject_post(post_id, rejection_reason=None, admin_id=None):
    """Reject a post with optional reason and admin ID"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        
        # Update with rejection details
        update_query = f"UPDATE posts SET approved=0, rejection_reason={placeholder}, rejected_by_admin={placeholder}, rejection_timestamp=CURRENT_TIMESTAMP WHERE post_id={placeholder}"
        cursor.execute(update_query, (rejection_reason, admin_id, post_id))
        conn.commit()

def get_next_post_number():
    """Get the next sequential post number for approved posts"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(post_number) FROM posts WHERE post_number IS NOT NULL")
        result = cursor.fetchone()
        return (result[0] + 1) if result[0] is not None else 1

def flag_post(post_id):
    """Flag a post for review"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f"UPDATE posts SET flagged=1 WHERE post_id={placeholder}", (post_id,))
        conn.commit()

def block_user(user_id):
    """Block a user"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f"UPDATE users SET blocked=1 WHERE user_id={placeholder}", (user_id,))
        conn.commit()

def unblock_user(user_id):
    """Unblock a user"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f"UPDATE users SET blocked=0 WHERE user_id={placeholder}", (user_id,))
        conn.commit()

def get_post_by_id(post_id):
    """Get a specific post by ID"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f"SELECT * FROM posts WHERE post_id={placeholder}", (post_id,))
        return cursor.fetchone()

def is_blocked_user(user_id):
    """Check if user is blocked"""
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(f"SELECT blocked FROM users WHERE user_id={placeholder}", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval/rejection callbacks"""
    if not update or not update.callback_query:
        return
    
    query = update.callback_query
    await query.answer()
    
    if not query or not query.data:
        return
    
    data = query.data
    admin_id = None
    if update and update.effective_user:
        admin_id = update.effective_user.id
    
    # Check if user is admin or mini admin
    if admin_id not in ADMIN_IDS and admin_id not in MINI_ADMIN_IDS:
        try:
            await query.edit_message_text("❗ You are not authorized to moderate.")
        except:
            pass
        return
    
    # Handle rejection reason callbacks FIRST (before parsing post ID)
    if data.startswith("reject_reason_"):
        await handle_rejection_reason_callback(update, context)
        return
    
    if data.startswith("reject_custom_"):
        await handle_custom_rejection_callback(update, context)
        return
        
    if data.startswith("reject_cancel_"):
        await handle_rejection_cancel(update, context)
        return
    
    # Handle edited confession approval/rejection callbacks
    if data.startswith("approve_edit_") or data.startswith("reject_edit_") or data.startswith("review_edit_"):
        # Extract post_id from approve_edit_{post_id} or reject_edit_{post_id}
        parts = data.split("_")
        if len(parts) >= 3:
            post_id = int(parts[2])
            # Set is_sensitive to False for edited confessions (will check post later)
            is_sensitive = False
            # Get the post data for edited confessions
            post = get_post_by_id(post_id)
            if not post:
                try:
                    await query.edit_message_text("❗ Post not found.")
                except:
                    pass
                return
            
            # Check if this is an edited confession that was previously approved
            is_edited_callback = data.startswith("approve_edit_") or data.startswith("reject_edit_")
            was_previously_approved = post[5] == 1 if len(post) > 5 else False
            
            # Use helper function to check is_edited status reliably instead of array indexing
            from db import is_post_edited
            is_edited = is_post_edited(post_id)
            
            logging.info(f"Edited confession callback: post_id={post_id}, is_edited={is_edited}, was_approved={was_previously_approved}, post_length={len(post)}")
            
            # Continue with normal approval/rejection flow below - don't return, fall through
        else:
            await query.answer("❗ Invalid callback data")
            return
    elif data.startswith("approve_") or data.startswith("approve18_") or data.startswith("approve_sensitive_"):
        is_sensitive = data.startswith("approve18_") or data.startswith("approve_sensitive_")
        post_id = int(data.split("_")[1])
        post = get_post_by_id(post_id)
        if not post:
            try:
                await query.edit_message_text("❗ Post not found.")
            except:
                pass
            return
        
        # Check if post is already approved (prevent duplicate approvals)
        # Use safe indexing to avoid index out of range errors
        if len(post) > 5 and post[5] == 1:  # approved field is at index 5
            try:
                await query.edit_message_text(
                    "✅ Approved by another admin\\!\n\n"
                    "This post was already approved by a different admin\\. "
                    "You can still view it in the channel\\.",
                    parse_mode="MarkdownV2"
                )
            except:
                pass
            return
        
        # Check if post is already rejected
        if len(post) > 5 and post[5] == 0:  # approved field is at index 5
            try:
                await query.edit_message_text(
                    "❌ Already rejected\\!\n\n"
                    "This post was already rejected by a different admin\\. "
                    "No further action is needed\\.",
                    parse_mode="MarkdownV2"
                )
            except:
                pass
            return
        
        # Get submitter info
        submitter_id = post[4]  # user_id is at index 4
        category = post[2]  # category is at index 2
        content = post[1]  # content is at index 1
        
        # Initialize variables for regular approvals (not edited confessions)
        is_edited_callback = False
        was_previously_approved = False
        
        # Fall through to common approval logic below
    
    # Check if we have a valid post_id from approve callbacks
    if 'post_id' in locals() and (data.startswith("approve_") or data.startswith("approve18_") or data.startswith("approve_sensitive_") or data.startswith("approve_edit_")):
        # Get submitter info if not already set
        if 'submitter_id' not in locals():
            submitter_id = post[4]  # user_id is at index 4
            category = post[2]  # category is at index 2
            content = post[1]  # content is at index 1
        
        # Initialize post_number to None
        post_number = None
        
        try:
            # Get the next sequential post number
            post_number = get_next_post_number()
            
            # Get current comment count
            comment_count = get_comment_count(post_id)
            
            # Create inline buttons for the channel post
            bot_username_clean = BOT_USERNAME.lstrip('@')
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
                            url=f"https://t.me/{bot_username_clean}?start=comment_{post_id}"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            f"👀 See Comments ({comment_count})", 
                            url=f"https://t.me/{bot_username_clean}?start=view_{post_id}"
                        )
                    ]
                ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Test channel access first
            try:
                await context.bot.get_chat(CHANNEL_ID)
                channel_accessible = True
            except Exception as e:
                logging.warning(f"Channel {CHANNEL_ID} not accessible: {e}")
                channel_accessible = False
            
            # Convert categories into hashtags
            categories = post[2]
            categories_text = " ".join(
                [f"#{cat.strip().replace(' ', '')}" for cat in categories.split(",")]
            )

            # Optional profile link for non-sensitive posts
            profile_link_html = ""
            if not is_sensitive:
                try:
                    from html import escape as html_escape
                    author_profile = get_user_profile(submitter_id)
                    if author_profile and author_profile.get('display_name'):
                        bot_username_clean = BOT_USERNAME.lstrip('@')
                        emoji = author_profile.get('emoji') or ''
                        display_name = (author_profile.get('display_name') or '').strip()
                        name_raw = (emoji + ' ' + display_name).strip()
                        if not name_raw:
                            name_raw = "View profile"
                        safe_name = html_escape(name_raw)
                        profile_link_html = (
                            f"\n\nBy: <a href='https://t.me/{bot_username_clean}?start=profile_{submitter_id}'>{safe_name}</a>"
                        )
                except Exception as e:
                    logging.error(f"Error building profile link: {e}")
                    profile_link_html = ""
            
            # Check if this is a media post
            is_media = False
            media_info = None
            try:
                media_info = get_media_info(post_id)
                if media_info and media_info.get('type') and media_info.get('file_id'):
                    is_media = True
            except Exception as e:
                logging.error(f"Error getting media info: {e}")
            
            # Post to channel or update existing message
            msg = None
            channel_update_successful = False
            
            # Check if this is an edited confession that was previously approved
            if was_previously_approved and is_edited_callback:
                logging.info(f"Updating existing channel message for edited post {post_id}")
                success, result = await update_channel_message(
                    context, post_id, content, category, is_sensitive
                )
                if success:
                    logging.info(f"Channel message updated successfully for post {post_id}")
                    # Clear the edited flag but keep existing channel_message_id
                    approve_post(post_id, None, post_number)  # Keep existing message ID
                    channel_update_successful = True
                else:
                    logging.error(f"Failed to update channel message: {result}")
                    # Fallback: treat as new post if update fails
                    was_previously_approved = False
            
            # For new confessions or fallback from failed update
            if not was_previously_approved:
                if channel_accessible:
                    if is_sensitive:
                        warning_text = (
                            f"<b>⚠️ Sensitive Confession # {post_number}</b>\n\n"
                            "This confession contains sexual or explicit content that may not be suiable for all our member.\n\n"
                            "Tap the button below to view it privately and anonymously via the bot."
                        )
                        msg = await context.bot.send_message(
                            chat_id=CHANNEL_ID,
                            text=warning_text,
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                        )
                    elif is_media and media_info:
                        caption_text = f"<b>Confession # {post_number}</b>\n\n"
                        if content and content.strip():
                            caption_text += f"{content}\n\n"
                        if media_info.get('caption') and media_info['caption'] != content:
                            caption_text += f"{media_info['caption']}\n\n"
                        caption_text += categories_text
                        if profile_link_html:
                            caption_text += profile_link_html
                        
                        max_caption_length = 1024
                        if len(caption_text) > max_caption_length:
                            caption_text = caption_text[:max_caption_length-30] + "\n\n[Caption truncated...]"
                        
                        try:
                            if media_info['type'] == 'photo':
                                msg = await context.bot.send_photo(
                                    chat_id=CHANNEL_ID,
                                    photo=media_info['file_id'],
                                    caption=caption_text,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup
                                )
                            elif media_info['type'] == 'video':
                                msg = await context.bot.send_video(
                                    chat_id=CHANNEL_ID,
                                    video=media_info['file_id'],
                                    caption=caption_text,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup
                                )
                            elif media_info['type'] == 'animation':
                                msg = await context.bot.send_animation(
                                    chat_id=CHANNEL_ID,
                                    animation=media_info['file_id'],
                                    caption=caption_text,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup
                                )
                            else:
                                msg = await context.bot.send_document(
                                    chat_id=CHANNEL_ID,
                                    document=media_info['file_id'],
                                    caption=caption_text,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup
                                )
                        except Exception as media_error:
                            logging.error(f"Error sending media: {media_error}")
                            fallback_text = f"<b>Confession # {post_number}</b>\n\n{content}\n\n{categories_text}"
                            msg = await context.bot.send_message(
                                chat_id=CHANNEL_ID,
                                text=fallback_text,
                                parse_mode="HTML",
                                reply_markup=reply_markup,
                                disable_web_page_preview=True
                            )
                    else:
                        profile_suffix = profile_link_html or ""
                        msg = await context.bot.send_message(
                            chat_id=CHANNEL_ID,
                            text=f"<b>Confession # {post_number}</b>\n\n{content}\n\n{categories_text}{profile_suffix}",
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                            disable_web_page_preview=True
                        )
            
            # Update database
            from db import set_post_sensitive
            if msg:
                approve_post(post_id, msg.message_id, post_number)
            else:
                approve_post(post_id, None, post_number)
            
            set_post_sensitive(post_id, is_sensitive)
            
            # Send confirmation to admin
            try:
                prefix = "🔞 Sensitive" if is_sensitive else "✅"
                if channel_update_successful:
                    await query.edit_message_text(
                        f"{prefix} *Edited Confession Updated*!\n\n"
                        f"The channel post has been updated with the new content.\n\n"
                        f"📝 Post ID: #{post_id}\n"
                        f"👤 Author: User {submitter_id}",
                        parse_mode="MarkdownV2"
                    )
                elif channel_accessible and msg:
                    await query.edit_message_text(f"{prefix} approved and posted to channel as Post #{post_number}.")
                elif channel_accessible and not msg:
                    await query.edit_message_text(f"{prefix} approved as Post #{post_number}, but failed to post to channel.")
                else:
                    await query.edit_message_text(f"{prefix} approved as Post #{post_number}. (Channel not accessible)")
            except:
                pass
            
            # Award points and notify submitter
            if admin_id is not None:
                await award_points_for_confession_approval(submitter_id, post_id, admin_id, context)
            
            if submitter_id:
                try:
                    from utils import escape_markdown_text
                    confession_type = f"{get_media_type_emoji(media_info['type'])} {media_info['type'].title()} confession" if is_media and media_info else "confession"
                    
                    channel_link_text = "Check the channel"
                    if msg and msg.message_id:
                        try:
                            if CHANNEL_ID < 0:
                                channel_link_id = str(CHANNEL_ID)[4:] if str(CHANNEL_ID).startswith('-100') else str(abs(CHANNEL_ID))
                                channel_link_text = f"[View in Channel](https://t.me/c/{channel_link_id}/{msg.message_id})"
                            else:
                                chat = await context.bot.get_chat(CHANNEL_ID)
                                if chat.username:
                                    channel_link_text = f"[View in Channel](https://t.me/{chat.username}/{msg.message_id})"
                        except:
                            pass
                    
                    message_text = f"""
✅ *{confession_type.title()} Approved\!*

Your {escape_markdown_text(confession_type)} in category `{escape_markdown_text(category)}` has been approved and posted to the channel\!

🔢 *Post Number:* \#{post_number}

💡 {channel_link_text}

🌟 *Thank you for sharing with us\!*"""
                    
                    keyboard = [
                        [InlineKeyboardButton("🆕 Submit New Confession", callback_data="start_confession")],
                        [InlineKeyboardButton("💬 Reply to Your Confession", callback_data=f"view_post_{post_id}")],
                        [InlineKeyboardButton("📋 View My Stats", callback_data="my_stats")],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
                    ]
                    
                    await context.bot.send_message(
                        chat_id=submitter_id,
                        text=message_text,
                        parse_mode="MarkdownV2",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        disable_web_page_preview=False
                    )
                except Exception as e:
                    logging.warning(f"Could not notify user: {e}")
                    
        except Exception as e:
            logging.error(f"Failed to post to channel: {e}")
            try:
                await query.edit_message_text(f"❗ Failed to post to channel: {e}")
            except:
                pass
    
    # Handle other callback types
    if data.startswith("reject_"):
        # Get post details
        post_id = int(data.split("_")[1])
        post = get_post_by_id(post_id)
        if not post:
            try:
                await query.edit_message_text("❗ Post not found.")
            except:
                pass
            return
        
        # Check if post is already rejected (prevent duplicate rejections)
        # Use safe indexing to avoid index out of range errors
        if len(post) > 5 and post[5] == 0:  # approved field is at index 5
            try:
                # Get post number if it exists
                post_number = None
                try:
                    post_number = get_next_post_number()
                except:
                    pass
                
                await query.edit_message_text(
                    f"❌ This post has already been rejected by another admin\\. \nYou can still view it in the channel as post #{post_number if post_number is not None else 'unknown'}\\.",
                    parse_mode="MarkdownV2"
                )
            except:
                pass
            return

        # Check if post is already approved
        if len(post) > 5 and post[5] == 1:  # approved field is at index 5
            try:
                # Get post number if it exists
                post_number = None
                try:
                    post_number = get_next_post_number()
                except:
                    pass
                
                await query.edit_message_text(
                    f"✅ Already approved by another admin\\!\n\nThis post was already approved and posted to the channel as post #{post_number if post_number is not None else 'unknown'}\\.",
                    parse_mode="MarkdownV2"
                )
            except:
                pass
            return
        
        # Show rejection reason selection instead of directly rejecting
        await show_rejection_reason_menu(query, post_id, context)

    elif data.startswith("flag_"):
        # Handle flagging
        post_id = int(data.split("_")[1])
        flag_post(post_id)
        
        try:
            await query.edit_message_text("🚩 Submission flagged for review.")
        except:
            pass

    elif data.startswith("block_"):
        # Handle blocking. Admin callbacks use the pattern 'block_<user_id>'
        # but we also have profile callbacks like 'block_user_<id>'. We only
        # want to handle the pure admin case here.
        parts = data.split("_")
        if len(parts) == 2 and parts[0] == "block":
            try:
                block_uid = int(parts[1])
            except ValueError:
                # Not a numeric ID; ignore so profile-specific handlers can process it
                return
            block_user(block_uid)
            
            try:
                await query.edit_message_text(f"⛔ User {block_uid} blocked.")
            except:
                pass

    elif data.startswith("unblock_"):
        # Handle unblocking for admin pattern 'unblock_<user_id>' only
        parts = data.split("_")
        if len(parts) == 2 and parts[0] == "unblock":
            try:
                block_uid = int(parts[1])
            except ValueError:
                return
            unblock_user(block_uid)
            
            try:
                await query.edit_message_text(f"✅ User {block_uid} unblocked.")
            except:
                pass

    # Handle other cases


# Rejection reason system
REJECTION_REASONS = {
    "inappropriate": "❌ Inappropriate Content",
    "spam": "🚫  Duplicated confession",
    "low_quality": "📝 Low Quality/Too Short",
    "rules": "📋 Violates Community Rules",
    "offensive": "⚠️ Offensive Language",
    "personal": "🔒 Too Personal/Identifying Info",
    "unclear": "❓ Unclear or Confusing",
    "not_confession": "🎭 Not a Confession/Question",
    "harmful": "💥 Harmful or Dangerous Content",
    "irrelevant": "📌 Off-Topic or Irrelevant",
    "custom": "✏️ Custom Reason..."
}

async def show_rejection_reason_menu(query, post_id, context):
    """Show rejection reason selection menu"""
    text = f"❌ **Rejecting Post #{post_id}**\n\n"
    text += "Please select a reason for rejection:\n\n"
    text += "This will help the user understand why their confession was not approved."
    
    # Create inline keyboard with rejection reasons
    keyboard = []
    
    # Add quick reason buttons (2 per row)
    reasons = list(REJECTION_REASONS.items())
    for i in range(0, len(reasons) - 1, 2):  # Exclude "custom" from regular grid
        row = []
        for j in range(2):
            if i + j < len(reasons) - 1:  # Don't include custom in the regular grid
                reason_key, reason_text = reasons[i + j]
                row.append(InlineKeyboardButton(
                    reason_text, 
                    callback_data=f"reject_reason_{post_id}_{reason_key}"
                ))
        if row:
            keyboard.append(row)
    
    # Add custom reason button on its own row
    keyboard.append([
        InlineKeyboardButton(
            REJECTION_REASONS["custom"], 
            callback_data=f"reject_custom_{post_id}"
        )
    ])
    
    # Add cancel button
    keyboard.append([
        InlineKeyboardButton("🔙 Cancel", callback_data=f"reject_cancel_{post_id}")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # First, determine if this is a media message by checking if it has a caption
    is_media_message = hasattr(query.message, 'caption') and query.message.caption is not None
    
    try:
        if is_media_message:
            # For media messages, edit the caption
            await query.edit_message_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            # For text messages, edit the text
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    except Exception as e:
        # If the first attempt fails, try the other method
        try:
            if is_media_message:
                # Try editing text if caption editing failed
                await query.edit_message_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                # Try editing caption if text editing failed
                await query.edit_message_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        except Exception as e2:
            # If both methods fail, send a new message as fallback
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                # Delete the original message to avoid clutter
                try:
                    await query.message.delete()
                except:
                    pass
                # Answer the callback to prevent "loading" state
                await query.answer("Rejection menu opened")
            except Exception as e3:
                logging.error(f"Failed to show rejection menu after all attempts: {e3}")
                await query.answer("❗ Error showing rejection menu. Please try again.")

async def handle_rejection_reason_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle predefined rejection reason selection"""
    query = update.callback_query
    data = query.data
    admin_id = update.effective_user.id
    
    # Parse callback data: reject_reason_{post_id}_{reason_key}
    parts = data.split("_")
    if len(parts) < 4:
        await query.answer("❗ Invalid rejection data")
        return
    
    post_id = int(parts[2])
    reason_key = parts[3]
    
    if reason_key not in REJECTION_REASONS:
        await query.answer("❗ Invalid rejection reason")
        return
    
    reason_text = REJECTION_REASONS[reason_key].replace("❌ ", "").replace("🚫 ", "").replace("📝 ", "").replace("📋 ", "").replace("⚠️ ", "").replace("🔒 ", "").replace("❓ ", "").replace("🎭 ", "").replace("💥 ", "").replace("📌 ", "")
    
    await execute_rejection(query, post_id, reason_text, admin_id, context)

async def handle_custom_rejection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom rejection reason - ask admin to send message"""
    query = update.callback_query
    data = query.data
    admin_id = update.effective_user.id
    
    # Parse callback data: reject_custom_{post_id}
    parts = data.split("_")
    if len(parts) < 3:
        await query.answer("❗ Invalid rejection data")
        return
    
    post_id = int(parts[2])
    
    # Store the post_id in user context for the next message
    context.user_data['pending_rejection_post_id'] = post_id
    context.user_data['waiting_for_custom_rejection'] = True
    
    text = f"✏️ **Custom Rejection Reason**\n\n"
    text += f"Please type your custom rejection reason for post #{post_id}.\n\n"
    text += "Your message will be sent to the user to help them understand why their confession was rejected.\n\n"
    text += "*Send your message now, or use /cancel to abort.*"
    
    keyboard = [
        [InlineKeyboardButton("🚫 Cancel", callback_data=f"reject_cancel_{post_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Check if this is a media message
    is_media_message = hasattr(query.message, 'caption') and query.message.caption is not None
    
    try:
        if is_media_message:
            # For media messages, edit the caption
            await query.edit_message_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        else:
            # For text messages, edit the text
            await query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    except Exception as e:
        # If the first attempt fails, try the other method
        try:
            if is_media_message:
                # Try editing text if caption editing failed
                await query.edit_message_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
            else:
                # Try editing caption if text editing failed
                await query.edit_message_caption(
                    caption=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        except Exception as e2:
            logging.error(f"Error showing custom rejection input after both attempts: {e2}")
            # Send new message as fallback
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                await query.answer("Custom rejection input opened")
            except Exception as e3:
                logging.error(f"Failed to show custom rejection input: {e3}")
                await query.answer("❗ Error showing custom rejection input. Please try again.")

async def handle_rejection_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle rejection cancellation - go back to original approval interface"""
    query = update.callback_query
    data = query.data
    
    # Parse callback data: reject_cancel_{post_id}
    parts = data.split("_")
    if len(parts) < 3:
        await query.answer("❗ Invalid cancellation data")
        return
    
    post_id = int(parts[2])
    post = get_post_by_id(post_id)
    
    if not post:
        await query.edit_message_text("❗ Post not found.")
        return
    
    # Clear any pending custom rejection state
    context.user_data.pop('pending_rejection_post_id', None)
    context.user_data.pop('waiting_for_custom_rejection', None)
    
    # Recreate the original admin approval interface
    submitter_id = post[4]
    category = post[2]
    content = post[1]
    
    from utils import escape_markdown_text
    
    admin_text = f"""
📝 *New Confession Submission*

*ID:* {escape_markdown_text(f'#{post_id}')}
*Category:* {escape_markdown_text(category)}
*Submitter:* {submitter_id}

*Content:*
{escape_markdown_text(content)}
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton("🔞 Approve 18+", callback_data=f"approve18_{post_id}"),
        ],
        [
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{post_id}")
        ],
        [
            InlineKeyboardButton("🚩 Flag", callback_data=f"flag_{post_id}"),
            InlineKeyboardButton("⛔ Block User", callback_data=f"block_{submitter_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(
            admin_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logging.error(f"Error restoring approval interface: {e}")

async def execute_rejection(query, post_id, rejection_reason, admin_id, context):
    """Execute the rejection with the given reason"""
    post = get_post_by_id(post_id)
    if not post:
        try:
            await query.edit_message_text("❗ Post not found.")
        except:
            try:
                await query.edit_message_caption(caption="❗ Post not found.")
            except:
                pass
        return
    
    submitter_id = post[4]
    category = post[2]
    
    # Reject the post with reason
    reject_post(post_id, rejection_reason, admin_id)
    
    # Update admin interface - handle both text and media messages
    success_message = (
        f"❌ **Submission rejected**\n\n"
        f"**Reason:** {rejection_reason}\n\n"
        f"The user has been notified with this explanation."
    )
    
    # Determine if this is a media message by checking if it has a caption
    is_media_message = hasattr(query.message, 'caption') and query.message.caption is not None
    
    try:
        if is_media_message:
            # For media messages, edit the caption
            await query.edit_message_caption(
                caption=success_message,
                parse_mode="Markdown"
            )
        else:
            # For text messages, edit the text
            await query.edit_message_text(
                success_message,
                parse_mode="Markdown"
            )
    except Exception as e:
        # If the first attempt fails, try the other method
        try:
            if is_media_message:
                # Try editing text if caption editing failed
                await query.edit_message_text(
                    success_message,
                    parse_mode="Markdown"
                )
            else:
                # Try editing caption if text editing failed
                await query.edit_message_caption(
                    caption=success_message,
                    parse_mode="Markdown"
                )
        except Exception as e2:
            # If both methods fail, send a new message as fallback
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=success_message,
                    parse_mode="Markdown"
                )
                # Delete the original message to avoid clutter
                try:
                    await query.message.delete()
                except:
                    pass
                # Answer the callback to prevent "loading" state
                await query.answer("Post rejected successfully")
            except Exception as e3:
                logging.error(f"Failed to send rejection confirmation after all attempts: {e3}")
    
    # Deduct points for rejected confession
    await RankingIntegration.handle_confession_rejected(submitter_id, post_id, admin_id)
    
    # Notify the submitter with the rejection reason
    if submitter_id:
        try:
            from utils import escape_markdown_text
            
            message_text = f"""
❌ *Confession Rejected*

Your confession in category `{escape_markdown_text(category)}` was rejected by the administrators\\.

*Reason:* {escape_markdown_text(rejection_reason)}

💡 *What you can do:*
• Review our community guidelines
• Modify your confession and resubmit
• Ask questions if you need clarification

🔄 You're welcome to submit a new confession anytime\\!
"""
            
            # Create keyboard with helpful buttons
            keyboard = [
                [InlineKeyboardButton("🆕 Submit New Confession", callback_data="start_confession")],
                [InlineKeyboardButton("📞 Contact Admins", callback_data="contact_admin")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=submitter_id,
                text=message_text,
                parse_mode="MarkdownV2",
                reply_markup=reply_markup
            )
        except Exception as e:
            logging.warning(f"Could not notify user {submitter_id}: {e}")

async def handle_custom_rejection_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom rejection reason text input from admin"""
    if not context.user_data.get('waiting_for_custom_rejection'):
        return
    
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_IDS:
        return
    
    post_id = context.user_data.get('pending_rejection_post_id')
    if not post_id:
        await update.message.reply_text("❗ No pending rejection found.")
        return
    
    custom_reason = update.message.text.strip()
    if not custom_reason:
        await update.message.reply_text("❗ Please provide a rejection reason or use /cancel.")
        return
    
    if len(custom_reason) > 500:
        await update.message.reply_text("❗ Rejection reason is too long. Please keep it under 500 characters.")
        return
    
    # Clear the pending state
    context.user_data.pop('pending_rejection_post_id', None)
    context.user_data.pop('waiting_for_custom_rejection', None)
    
    # Execute the rejection
    post = get_post_by_id(post_id)
    if not post:
        await update.message.reply_text("❗ Post not found.")
        return
    
    submitter_id = post[4]
    category = post[2]
    
    # Reject the post with custom reason
    reject_post(post_id, custom_reason, admin_id)
    
    # Notify admin
    await update.message.reply_text(
        f"❌ **Post #{post_id} rejected**\n\n"
        f"**Custom reason:** {custom_reason}\n\n"
        f"The user has been notified with your explanation.",
        parse_mode="Markdown"
    )
    
    # Deduct points for rejected confession
    await RankingIntegration.handle_confession_rejected(submitter_id, post_id, admin_id)
    
    # Notify the submitter with the custom rejection reason
    if submitter_id:
        try:
            from utils import escape_markdown_text
            
            message_text = f"""
❌ *Confession Rejected*

Your confession in category `{escape_markdown_text(category)}` was rejected by the administrators\.

*Admin's explanation:*
_{escape_markdown_text(custom_reason)}_

💡 *What you can do:*
• Review the feedback above
• Modify your confession based on the explanation
• Resubmit with improvements
• Contact admins if you have questions

🔄 You're welcome to submit a new confession anytime\!
"""
            
            # Create keyboard with helpful buttons
            keyboard = [
                [InlineKeyboardButton("🆕 Submit New Confession", callback_data="start_confession")],
                [InlineKeyboardButton("📞 Contact Admins", callback_data="contact_admin")],
                [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=submitter_id,
                text=message_text,
                parse_mode="MarkdownV2",
                reply_markup=reply_markup
            )
        except Exception as e:
            logging.warning(f"Could not notify user {submitter_id}: {e}")
