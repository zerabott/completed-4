"""
Enhanced Telegram Confession Bot with Sophisticated Comment System
Features: Pagination, Like/Dislike, Replies, Reporting, and Admin Moderation
"""

import logging
import re
import os
import asyncio
from typing import Optional
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from config import *
from db import init_db, add_user, is_blocked_user, get_user_info
from db import add_user_async, is_blocked_user_async, get_user_info_async
from db import get_comment_count_async, get_user_posts_async, get_post_author_id_async
from db import get_user_profile_async, get_all_users_async
from db import update_user_post_async, delete_user_post_async
from db import upsert_user_profile, get_user_profile, delete_user_profile
from db import set_profile_visibility, set_profile_accepting_contacts
from db import get_user_profile_stats
from db import (
    get_profile_contact,
    get_profile_contact_by_id,
    create_profile_contact,
    update_profile_contact_status,
    touch_profile_contact,
    block_profile_user,
    is_profile_blocked_either_way,
    get_user_daily_message_count,
    increment_user_daily_message_count,
)
from db import (
    async_add_user,
    async_is_blocked_user,
    async_get_user_info,
    async_get_user_posts_count,
    async_get_user_comments_count,
    async_get_post_by_id,
    async_get_comments_for_post,
    async_get_comment_count,
    async_get_post_like_count,
    async_has_user_liked_post,
    async_get_post_likes,
    async_increment_user_questions,
    async_increment_user_comments
)
from db_connection import get_db_connection, cache_manager, make_async, AsyncDBWrapper
from submission import *
from submission import validate_media, validate_caption, get_media_type_emoji
from comments import *
from approval import admin_callback
from moderation import report_abuse, notify_admins_about_reports
from stats import get_user_stats, get_channel_stats
from utils import *
from admin_messaging import send_message_to_admins, get_pending_messages, send_admin_reply_to_user
from admin_deletion import (
    delete_post_completely, 
    delete_comment_completely, 
    get_post_details_for_deletion, 
    get_comment_details_for_deletion,
    clear_reports_for_content,
    delete_channel_message
)

# Import improvement modules
from rate_limiter import rate_limiter, handle_rate_limit_decorator
from error_handler import handle_telegram_errors, global_error_handler
from logger import bot_logger
from migrations import run_migrations
from analytics import analytics_manager
from backup_system import start_backup_system

# Import enhanced ranking system modules
from enhanced_ranking_ui import enhanced_ranking_callback_handler, show_enhanced_ranking_menu
from ranking_integration import (
    award_points_for_confession_submission,
    award_points_for_confession_approval,
    award_points_for_comment,
    award_points_for_reaction_given,
    award_points_for_reaction_received
)

# Import enhanced reporting system
from enhanced_reporting import (
    show_report_reasons,
    handle_report_reason_callback,
    handle_submit_report,
    handle_cancel_report
)

# Import profile helpers
from profile_helpers import (
    handle_emoji_selection,
    show_edit_details_menu,
    show_gender_selection,
    handle_gender_selection,
    show_year_selection,
    handle_year_selection,
    show_relationship_selection,
    handle_relationship_selection,
    show_previous_chats,
    resume_chat
)

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Helper function for sending media posts
async def send_media_post(context, chat_id, post, reply_markup=None, include_hashtag=False):
    """Helper function to send a media post with proper formatting"""
    post_id = post[0]
    content = post[1]
    category = post[2]
    media_type = post[10] if len(post) > 10 else None
    media_file_id = post[11] if len(post) > 11 else None
    media_caption = post[13] if len(post) > 13 else None
    post_number = post[9] if len(post) > 9 and post[9] is not None else post_id
    
    # Prepare caption
    if include_hashtag:
        caption_text = f"#{post_number} | {escape_markdown_text(category)}\n\n"
    else:
        caption_text = f"*{escape_markdown_text(category)}*\n\n"
    
    # Add text content if available
    if content:
        caption_text += f"{escape_markdown_text(content)}"
    elif media_caption:
        caption_text += f"{escape_markdown_text(media_caption)}"
    
    # If it's a media post, send the media
    if media_type and media_file_id:
        try:
            if media_type == 'photo':
                return await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_type == 'video':
                return await context.bot.send_video(
                    chat_id=chat_id,
                    video=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_type == 'animation':
                return await context.bot.send_animation(
                    chat_id=chat_id,
                    animation=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
        except Exception as e:
            logger.error(f"Error sending media post {post_id}: {e}")
            # Fallback to text message
            caption_text += f"\n\n📷 *[Media content unavailable]*"
    
    # Send as text message (either no media or media failed)
    return await context.bot.send_message(
        chat_id=chat_id,
        text=caption_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

# Flexible helper function that works with different query result structures
async def send_trending_media_post(context, chat_id, post, reply_markup=None, stats_text="", query_type="default"):
    """Helper function to send a trending media post with flexible field positions"""
    post_id = post[0]
    content = post[1]
    category = post[2]
    
    # Determine field positions based on query type
    if query_type == "most_commented":
        # get_most_commented_posts_24h structure
        post_number = post[7] if len(post) > 7 and post[7] is not None else post_id
        media_type = post[8] if len(post) > 8 else None
        media_file_id = post[9] if len(post) > 9 else None
        media_caption = post[11] if len(post) > 11 else None
    elif query_type == "most_liked":
        # get_posts_with_most_liked_comments structure
        post_number = post[8] if len(post) > 8 and post[8] is not None else post_id
        media_type = post[9] if len(post) > 9 else None
        media_file_id = post[10] if len(post) > 10 else None
        media_caption = post[12] if len(post) > 12 else None
    else:
        # Default structure (rising, all trending)
        post_number = post[8] if len(post) > 8 and post[8] is not None else post_id
        media_type = post[9] if len(post) > 9 else None
        media_file_id = post[10] if len(post) > 10 else None
        media_caption = post[12] if len(post) > 12 else None
    
    # Prepare caption
    caption_text = f"*{escape_markdown_text(category)}*\n\n"
    
    # Add text content if available
    if content:
        caption_text += f"{escape_markdown_text(content)}"
    elif media_caption:
        caption_text += f"{escape_markdown_text(media_caption)}"
    
    # Add stats if provided
    if stats_text:
        caption_text += f"\n\n*\\#{post_number}* {stats_text}"
    
    # If it's a media post, send the media
    if media_type and media_file_id:
        try:
            if media_type == 'photo':
                return await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_type == 'video':
                return await context.bot.send_video(
                    chat_id=chat_id,
                    video=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_type == 'animation':
                return await context.bot.send_animation(
                    chat_id=chat_id,
                    animation=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
        except Exception as e:
            logger.error(f"Error sending trending media post {post_id}: {e}")
            # Fallback to text message
            caption_text += f"\n\n📷 *[Media content unavailable]*"
    
    # Send as text message (either no media or media failed)
    return await context.bot.send_message(
        chat_id=chat_id,
        text=caption_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

# Menu options (optimized - removed redundant features for better performance)
MAIN_MENU = [
    ["🙊 Confess/Ask Question", "👤 My Profile"],
    ["🏆 My Rank", "📊 My Stats"],
    ["📞 Contact Admin" , "❓ Help/About"]
]

CANCEL_BUTTON = "🚫 Cancel"
MENU_BUTTON = "🏠 Main Menu"

# Set of all reply-keyboard button texts so we don't treat them as user content
BUTTON_TEXTS = {CANCEL_BUTTON, MENU_BUTTON}
for row in MAIN_MENU:
    for item in row:
        BUTTON_TEXTS.add(item)
# Admin dashboard button is only added for admins at runtime
BUTTON_TEXTS.add("🔧 Admin Dashboard")

def is_button_text(text: Optional[str]) -> bool:
    """Return True if the given text matches any known button label.

    This lets us avoid recording button presses as confessions, comments, or admin messages.
    """
    return bool(text) and text in BUTTON_TEXTS

async def clear_user_context(context):
    """Clear user's conversation context - optimized with TTL tracking"""
    keys_to_clear = [
        'state', 'confession_content', 'selected_category', 
        'comment_post_id', 'comment_content', 'admin_action',
        'viewing_post_id', 'reply_to_comment_id', 'current_page',
        'contact_admin_message',
        # Profile & contact system
        'profile_state', 'profile_draft', 'profile_chat_partner', 'profile_contact_id',
        # Cleanup tracking
        'last_activity', 'context_created_at'
    ]
    for key in keys_to_clear:
        context.user_data.pop(key, None)
    
    # Mark context as cleaned
    context.user_data['last_cleanup'] = __import__('time').time()


async def cleanup_stale_contexts(context: ContextTypes.DEFAULT_TYPE, max_age_seconds: int = 1800):
    """Automatically clean up stale user contexts older than max_age_seconds (default 30 min)"""
    import time
    current_time = time.time()
    
    # Check if cleanup is needed for this context
    last_cleanup = context.user_data.get('last_cleanup', 0)
    
    # Auto-clear if context is older than max_age
    context_created = context.user_data.get('context_created_at', current_time)
    if (current_time - context_created) > max_age_seconds:
        await clear_user_context(context)
        context.user_data['context_created_at'] = current_time
        return True
    
    return False

async def show_menu(update, context, text="What would you like to do next?"):
    """Show the main menu - optimized with stale context cleanup"""
    # Check and cleanup stale contexts
    await cleanup_stale_contexts(context)
    
    await clear_user_context(context)
    
    # Get user ID to check if admin
    user_id = None
    if update.callback_query and update.callback_query.from_user:
        user_id = update.callback_query.from_user.id
    elif update.message and update.message.from_user:
        user_id = update.message.from_user.id
    elif update.effective_user:
        user_id = update.effective_user.id
    
    # Create menu based on user type
    menu = MAIN_MENU.copy()
    if user_id and user_id in ADMIN_IDS:
        # Add admin button for admins
        menu.append(["🔧 Admin Dashboard"])
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text="🏠 Returned to main menu.")
        except:
            pass
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=ReplyKeyboardMarkup(menu, resize_keyboard=True)
        )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=ReplyKeyboardMarkup(menu, resize_keyboard=True)
        )

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command and deep links - optimized with context tracking"""
    import time
    
    # Track context creation time for TTL cleanup
    if 'context_created_at' not in context.user_data:
        context.user_data['context_created_at'] = time.time()
    
    user = update.effective_user
    chat = update.effective_chat
    
    # In private chat, require that the user is a member of the channel before continuing
    if chat.type == "private":
        try:
            member = await context.bot.get_chat_member(CHANNEL_ID, user.id)
            status = getattr(member, "status", None)
        except Exception as e:
            logger.error(f"Error checking channel membership for user {user.id}: {e}")
            status = None

        if status not in ("member", "administrator", "creator"):
            # Try to build a join link: prefer CHANNEL_JOIN_LINK from config, fall back to channel username if available
            join_url = None
            try:
                join_url = CHANNEL_JOIN_LINK if 'CHANNEL_JOIN_LINK' in globals() else None
            except Exception:
                join_url = None

            if not join_url:
                try:
                    channel_chat = await context.bot.get_chat(CHANNEL_ID)
                    username = getattr(channel_chat, "username", None)
                    if username:
                        join_url = f"https://t.me/{username}"
                except Exception as e:
                    logger.error(f"Error fetching channel info for join link: {e}")

            # Build keyboard with join button if we have a URL
            keyboard = []
            if join_url:
                keyboard.append([InlineKeyboardButton("🔗 Join Channel", url=join_url)])

            # Instruct user to join and then press /start again (plain text to avoid MarkdownV2 issues)
            text = (
                "👋 Welcome!\n\n"
                "To use this bot, you need to join our channel first.\n\n"
                "1. Tap Join Channel and subscribe.\n"
                "2. Then come back here and press /start again."
            )

            if keyboard:
                await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
            else:
                await update.message.reply_text(
                    text,
                )
            return

    # Log chat information for debugging
    if chat.type in ['group', 'supergroup', 'channel']:
        logger.info(f"🆔 CHAT ID FOR .env: {chat.id}")
        logger.info(f"📝 Chat Title: {chat.title}")
        logger.info(f"🔧 Chat Type: {chat.type}")
        print(f"\n" + "=" * 50)
        print(f"🆔 CHAT ID FOR YOUR .env FILE: {chat.id}")
        print(f"📝 Chat Title: {chat.title}")
        print(f"🔧 Chat Type: {chat.type}")
        print(f"" + "=" * 50 + "\n")
    
    # Use async database operation to prevent blocking
    await add_user_async(user.id, user.username, user.first_name, user.last_name)
    
    # Check for deep links (e.g., /start comment_123, /start view_123)
    if context.args:
        command = context.args[0]
        logger.info(f"Deep link command received: {command}")
        
        try:
            if command.startswith("comment_"):
                post_id = int(command.split("_")[1])
                logger.info(f"Processing comment deep link for post_id: {post_id}")
                await show_post_for_commenting(update, context, post_id)
                return
            elif command.startswith("view_"):
                post_id = int(command.split("_")[1])
                logger.info(f"Processing view comments deep link for post_id: {post_id}")
                await show_comments_directly(update, context, post_id)
                return
            elif command.startswith("read_"):
                post_id = int(command.split("_")[1])
                logger.info(f"Processing sensitive read deep link for post_id: {post_id}")
                await show_sensitive_confession(update, context, post_id)
                return
            elif command.startswith("profile_"):
                profile_user_id = int(command.split("_")[1])
                logger.info(f"Processing profile deep link for user_id: {profile_user_id}")
                await show_profile_card(update, context, profile_user_id)
                return
        except (ValueError, IndexError) as e:
            logger.error(f"Error processing deep link {command}: {e}")
            # Use plain text (no Markdown) to avoid formatting errors here
            await update.message.reply_text(
                "❗ Invalid link. Please try again or use the main menu.",
            )
            await show_menu(update, context)
            return
    
    welcome_text = f"""
🎓 *Welcome to ASTU Confession Bot\\!*

This bot allows you to submit anonymous confessions and questions that will be reviewed by admins before posting to our channel\\.

*What you can do:*
• 🙊 Submit anonymous confessions/questions
• 📰 View recent approved posts
• 💬 Comment on posts with reactions
• 👍👎 Like/dislike comments
• 💬 Reply to specific comments
• 🚩 Report inappropriate content
• 🏆 Climb the ranking system and earn achievements
• 📊 Check your submission stats

*Your privacy matters\\!* 
All submissions and comments are anonymous and your identity is protected\\.

Choose an option from the menu below to get started\\!
"""
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="MarkdownV2",
        reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /menu command"""
    await show_menu(update, context, "🏠 Main Menu")

async def handle_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle main menu choices and media messages"""
    if not update.message or not update.message.from_user:
        return
    
    user_id = update.message.from_user.id
    
    # Handle text messages
    text = update.message.text
    
    # Handle cancel button (only for text messages)
    if text and text == CANCEL_BUTTON:
        await show_menu(update, context, "🏠 Returned to main menu.")
        return
    
    # Check if user is blocked - use async version
    is_blocked = await is_blocked_user_async(user_id)
    if is_blocked:
        await update.message.reply_text(
            "⛔ *Account Blocked*\n\n"
            "Your account has been blocked from submitting confessions\\. "
            "You can still view content but cannot post new confessions\\. "
            "Contact administrators if you believe this is an error\\.",
            parse_mode="MarkdownV2"
        )
        return

    # Handle current conversation states
    state = context.user_data.get('state')
    edit_state = context.user_data.get('edit_state')
    
    # Handle post edit mode (check this FIRST before other states)
    if edit_state == 'waiting_for_new_content':
        await handle_post_edit_content(update, context)
        return
    
    # Check if user is awaiting button selection (after comment submission)
    if state == 'awaiting_button_selection':
        awaiting_post_id = context.user_data.get('awaiting_post_id')
        await update.message.reply_text(
            "⚠️ *Please use the buttons below to continue*\n\n"
            "After submitting a comment, you must choose one of the available options\\. "
            "Text input is disabled until you make a selection\\.",
            parse_mode="MarkdownV2"
        )
        # Re-show the post options
        if awaiting_post_id:
            await show_post_with_options(update, context, awaiting_post_id)
        return
    
    # Handle confession submission (text or media)
    if state == 'writing_confession':
        await handle_confession_submission(update, context)
        return
    elif state == 'writing_comment':
        await handle_comment_submission(update, context)
        return
    elif state == 'contacting_admin':
        await handle_admin_contact(update, context)
        return
    elif state == 'admin_replying':
        await handle_admin_reply_message(update, context)
        return
    elif state == 'admin_searching_user':
        await handle_admin_user_search(update, context)
        return
    elif state == 'profile_editing':
        await handle_profile_text_input(update, context)
        return
    elif state == 'profile_chat':
        await handle_profile_chat_message(update, context)
        return
    elif state == 'admin_broadcast':
        await handle_message(update, context)
        return
    
    # Handle custom rejection reason input
    if context.user_data.get('waiting_for_custom_rejection'):
        from approval import handle_custom_rejection_text
        await handle_custom_rejection_text(update, context)
        return

    # For non-text messages (media) without a specific state, show help message
    if not text:
        await update.message.reply_text(
            "📷 I can see you sent media! To submit a photo/video confession:\n\n"
            "1. Use '🙊 Confess/Ask Question' from the menu\n"
            "2. Select your categories\n"
            "3. Send your photo/video with optional caption\n\n"
            "Please use the menu buttons below to get started!"
        )
        return

    # Handle menu options (text-based) - optimized menu
    if text == "🙊 Confess/Ask Question":
        await start_confession_flow(update, context)
    elif text == "👤 My Profile":
        await my_profile_entry(update, context)
    elif text == "🏆 My Rank":
        await show_enhanced_ranking_menu(update, context)
    elif text == "📊 My Stats":
        await my_stats(update, context)
    elif text == "📞 Contact Admin":
        await start_contact_admin(update, context)
    elif text == "❓ Help/About":
        await update.message.reply_text(HELP_TEXT, parse_mode="MarkdownV2")
        await show_menu(update, context)
    elif text == "🔧 Admin Dashboard":
        await admin_dashboard(update, context)
    elif text == MENU_BUTTON:
        await show_menu(update, context, "🏠 Returned to main menu.")
    else:
        await update.message.reply_text("❗ Please choose an option from the menu below.")
        await show_menu(update, context)


async def my_profile_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the "👤 My Profile" menu option."""
    user = update.effective_user
    profile = get_user_profile(user.id)

    # If no profile exists, start the create wizard directly
    if not profile:
        context.user_data['profile_draft'] = {}
        context.user_data['profile_state'] = 'editing_name'
        context.user_data['state'] = 'profile_editing'

        await update.message.reply_text(
            "👤 *Create Your Profile*\n\n"
            "First, choose an anonymous display name that will appear on your profile\\.\n"
            "It should *not* be your real name to maintain anonymity\\.\n\n"
            "Send your display name \\(2–32 characters\\):",
            parse_mode="MarkdownV2",
        )
        return
    await send_profile_overview(update, context, profile)


async def send_profile_overview(update: Update, context: ContextTypes.DEFAULT_TYPE, profile: dict):
    """Show the user's profile summary with action buttons."""
    name_raw = (profile.get('emoji') or '') + ' ' + (profile.get('display_name') or '')
    name_line = escape_markdown_text(name_raw.strip()) if name_raw.strip() else "(no name)"
    bio = profile.get('bio') or ''
    bio_display = escape_markdown_text(bio) if bio else escape_markdown_text("No bio set yet.")
    status_raw = "🟢 Visible to others" if profile.get('is_active') else "⚪ Hidden (not shown on posts/comments)"
    status = escape_markdown_text(status_raw)

    # Build details block only with non-empty fields
    details_lines = []
    gender = (profile.get('gender') or '').strip()
    age_val = profile.get('age')
    department = (profile.get('department') or '').strip()
    year = (profile.get('year') or '').strip()
    religion = (profile.get('religion') or '').strip()
    relationship = (profile.get('relationship_status') or '').strip()
    other = (profile.get('other_info') or '').strip()

    if gender:
        details_lines.append(f"Gender: {escape_markdown_text(gender)}")
    if age_val is not None:
        details_lines.append(f"Age: {escape_markdown_text(str(age_val))}")
    if department:
        details_lines.append(f"Department: {escape_markdown_text(department)}")
    if year:
        details_lines.append(f"Year: {escape_markdown_text(year)}")
    if religion:
        details_lines.append(f"Religion: {escape_markdown_text(religion)}")
    if relationship:
        details_lines.append(f"Relationship: {escape_markdown_text(relationship)}")
    if other:
        short_other = other[:30] + '...' if len(other) > 30 else other
        details_lines.append(f"Other Info: {escape_markdown_text(short_other)}")

    # Get accepting_contacts status (default to True if not set)
    accepting_contacts = profile.get('accepting_contacts', True)
    accepting_status = "✅ Accepting" if accepting_contacts else "🚫 Not Accepting"
    
    text = (
        "👤 *My Profile*\n\n"
        f"Name: {name_line}\n"
        f"Bio: {bio_display}\n"
        f"Visibility: {status}\n"
        f"Contact Requests: {escape_markdown_text(accepting_status)}"
    )

    if details_lines:
        text += "\n\n*Details:*\n" + "\n".join(details_lines)

    # Main profile buttons: Edit, Previous Chat, Friends, Inbox
    buttons = [
        [InlineKeyboardButton("✏️ Edit Profile", callback_data="profile_edit_menu")],
        [InlineKeyboardButton("💬 Previous Chats", callback_data="profile_previous_chats")],
        [
            InlineKeyboardButton("👥 Friends", callback_data="profile_friends"),
            InlineKeyboardButton("📥 Inbox", callback_data="profile_inbox")
        ],
        [InlineKeyboardButton("🚫 Blocked Users", callback_data="profile_blocked_users")],
    ]
    
    # Toggle buttons for visibility and accepting contacts
    visibility_btn = InlineKeyboardButton(
        "👁️ Hide Profile" if profile.get('is_active') else "👁️ Show Profile",
        callback_data="profile_visibility_off" if profile.get('is_active') else "profile_visibility_on"
    )
    accepting_btn = InlineKeyboardButton(
        "🚫 Stop Accepting Requests" if accepting_contacts else "✅ Accept Requests",
        callback_data="profile_accepting_off" if accepting_contacts else "profile_accepting_on"
    )
    buttons.append([visibility_btn, accepting_btn])
    buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu")])

    reply_markup = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2",
            )
            return
        except Exception:
            # If editing fails (e.g. message too old), fall back to sending a new one
            pass

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def show_profile_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the edit profile menu with options for Name, Emoji, Bio, and Details."""
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    text = (
        "✏️ *Edit Profile*\n\n"
        "Choose what you\'d like to edit:"
    )
    
    buttons = [
        [InlineKeyboardButton("📝 Name", callback_data="edit_name")],
        [InlineKeyboardButton("🎭 Avatar", callback_data="edit_emoji")],
        [InlineKeyboardButton("💬 Bio", callback_data="edit_bio")],
        [InlineKeyboardButton("📄 Details \\(Optional\\)", callback_data="edit_details")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_profile")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2",
        )


async def show_emoji_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show emoji selection menu with avatar-style emoji options."""
    text = (
        "🎭 *Choose Your Avatar*\n\n"
        "Tap an avatar below that represents your style and mood\\."
    )
    
    # Avatar-style emoji options
    buttons = [
        [InlineKeyboardButton("🤠", callback_data="emoji_🤠"),
         InlineKeyboardButton("🤖", callback_data="emoji_🤖"),
         InlineKeyboardButton("🧙‍♂️", callback_data="emoji_🧙‍♂️")],
        [InlineKeyboardButton("🧚‍♀️", callback_data="emoji_🧚‍♀️"),
         InlineKeyboardButton("🧛‍♂️", callback_data="emoji_🧛‍♂️"),
         InlineKeyboardButton("🧜‍♀️", callback_data="emoji_🧜‍♀️")],
        [InlineKeyboardButton("🥷", callback_data="emoji_🥷"),
         InlineKeyboardButton("🤴", callback_data="emoji_🤴"),
         InlineKeyboardButton("👰", callback_data="emoji_👰")],
        [InlineKeyboardButton("👨‍🎤", callback_data="emoji_👨‍🎤"),
         InlineKeyboardButton("👩‍🎤", callback_data="emoji_👩‍🎤"),
         InlineKeyboardButton("🕺", callback_data="emoji_🕺")],
        [InlineKeyboardButton("🧘‍♀️", callback_data="emoji_🧘‍♀️"),
         InlineKeyboardButton("🤸‍♂️", callback_data="emoji_🤸‍♂️"),
         InlineKeyboardButton("🏄‍♀️", callback_data="emoji_🏄‍♀️")],
        [InlineKeyboardButton("🦸", callback_data="emoji_🦸"),
         InlineKeyboardButton("🦹", callback_data="emoji_🦹"),
         InlineKeyboardButton("🧟‍♂️", callback_data="emoji_🧟‍♂️")],
        [InlineKeyboardButton("❌", callback_data="emoji_none")],
        [InlineKeyboardButton("🔙 Back", callback_data="profile_edit_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def show_emoji_selection_for_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show emoji selection menu during profile creation."""
    text = (
        "🎭 *Choose Your Avatar*\n\n"
        "Tap an avatar below that represents your style and mood\\."
    )
    
    # Avatar-style emoji options
    buttons = [
        [InlineKeyboardButton("🤠", callback_data="profile_emoji_🤠"),
         InlineKeyboardButton("🤖", callback_data="profile_emoji_🤖"),
         InlineKeyboardButton("🧙‍♂️", callback_data="profile_emoji_🧙‍♂️")],
        [InlineKeyboardButton("🧚‍♀️", callback_data="profile_emoji_🧚‍♀️"),
         InlineKeyboardButton("🧛‍♂️", callback_data="profile_emoji_🧛‍♂️"),
         InlineKeyboardButton("🧜‍♀️", callback_data="profile_emoji_🧜‍♀️")],
        [InlineKeyboardButton("🥷", callback_data="profile_emoji_🥷"),
         InlineKeyboardButton("🤴", callback_data="profile_emoji_🤴"),
         InlineKeyboardButton("👰", callback_data="profile_emoji_👰")],
        [InlineKeyboardButton("👨‍🎤", callback_data="profile_emoji_👨‍🎤"),
         InlineKeyboardButton("👩‍🎤", callback_data="profile_emoji_👩‍🎤"),
         InlineKeyboardButton("🕺", callback_data="profile_emoji_🕺")],
        [InlineKeyboardButton("🧘‍♀️", callback_data="profile_emoji_🧘‍♀️"),
         InlineKeyboardButton("🤸‍♂️", callback_data="profile_emoji_🤸‍♂️"),
         InlineKeyboardButton("🏄‍♀️", callback_data="profile_emoji_🏄‍♀️")],
        [InlineKeyboardButton("🦸", callback_data="profile_emoji_🦸"),
         InlineKeyboardButton("🦹", callback_data="profile_emoji_🦹"),
         InlineKeyboardButton("🧟‍♂️", callback_data="profile_emoji_🧟‍♂️")],
        [InlineKeyboardButton("❌ No Avatar", callback_data="profile_emoji_none")],
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def start_profile_edit_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, existing_profile: Optional[dict] = None):
    """Initialize the profile edit/create wizard and prompt for display name."""
    draft = {
        'display_name': existing_profile.get('display_name') if existing_profile else '',
        'emoji': existing_profile.get('emoji') if existing_profile else '',
        'bio': existing_profile.get('bio') if existing_profile else '',
    }
    context.user_data['profile_draft'] = draft
    context.user_data['profile_state'] = 'editing_name'
    context.user_data['state'] = 'profile_editing'

    prompt = (
        "✏️ *Edit Profile Name*\n\n" if existing_profile else "👤 *Create Your Profile*\n\n"
    )
    prompt += (
        "Send your display name \\(2–32 characters\\)\\.\n"
        "It should *not* be your real name if you want to stay anonymous\\."
    )

    target_message = update.callback_query.message if update.callback_query else update.message
    await target_message.reply_text(prompt, parse_mode="MarkdownV2")


async def handle_profile_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text inputs for the profile create/edit wizard."""
    text = (update.message.text or "").strip()
    profile_state = context.user_data.get('profile_state')
    draft = context.user_data.get('profile_draft') or {}

    if not profile_state:
        await update.message.reply_text(
            "❗ Profile editing session expired\\. Use '👤 My Profile' from the menu to start again\\."
        )
        context.user_data.pop('state', None)
        return

    # Step 1: display name
    if profile_state == 'editing_name':
        if len(text) < 2 or len(text) > 32:
            await update.message.reply_text(
                "❗ Display name must be between 2 and 32 characters\\. Please try again\\."
            )
            return
        draft['display_name'] = text
        context.user_data['profile_draft'] = draft
        context.user_data['profile_state'] = 'editing_emoji'

        # Offer a small avatar chooser keyboard plus the ability to type a custom one
        emoji_keyboard = [
            ["🤠", "🤖", "🧙‍♂️"],
            ["🧚‍♀️", "🧛‍♂️", "🧜‍♀️"],
            ["skip"],  # Matches the text users can type to skip
        ]

        await update.message.reply_text(
            "🔹 *Emoji (optional)*\n\n"
            "Send 1–2 emoji to show next to your name, or tap one below, or type `skip` to continue without an emoji\\.",
            parse_mode="MarkdownV2",
            reply_markup=ReplyKeyboardMarkup(emoji_keyboard, resize_keyboard=True, one_time_keyboard=True),
        )
        return

    # Step 2: emoji (optional)
    if profile_state == 'editing_emoji':
        # During profile creation, show emoji selection menu instead of accepting text input
        await show_emoji_selection_for_profile(update, context)
        return
    # Step 3: bio
    if profile_state == 'editing_bio':
        if text.lower() in {"skip", "none", "-"}:
            draft['bio'] = ''
        else:
            if len(text) > 250:
                await update.message.reply_text(
                    "❗ Bio is too long\\. Please keep it under 250 characters and try again\\."
                )
                return
            draft['bio'] = text
        context.user_data['profile_draft'] = draft
        context.user_data['profile_state'] = 'confirming'

        # Show confirmation summary
        name_raw = (draft.get('emoji') or '') + ' ' + draft.get('display_name', '')
        name_line = escape_markdown_text(name_raw.strip()) if name_raw.strip() else "(no name)"
        bio_display = escape_markdown_text(draft.get('bio') or "No bio set yet.")

        summary = (
            "👤 *Profile Preview*\n\n"
            f"Name: {name_line}\n"
            f"Bio: {bio_display}\n\n"
            "If everything looks good, press *Save*\\."
        )

        keyboard = [
            [InlineKeyboardButton("✅ Save", callback_data="profile_confirm_save")],
            [InlineKeyboardButton("🔁 Edit Again", callback_data="profile_edit_again")],
            [InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            summary,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2",
        )
        return

    # If somehow in confirming state and user types, remind them to use buttons
    if profile_state == 'confirming':
        await update.message.reply_text(
            "Please use the buttons below to save or edit your profile\\\\."
        )
        return
        return
        
    # New detail fields
    if profile_state == 'editing_age':
        user_id = update.effective_user.id
        profile = get_user_profile(user_id)
        if not profile:
            return
            
        if text.lower() in {"skip", "none", "-"}:
            age = None
        else:
            try:
                age = int(text)
                if age < 10 or age > 150:
                    await update.message.reply_text(
                        "❌ Invalid age\\. Please enter a number between 10 and 150 or type `skip`\\.",
                        parse_mode="MarkdownV2"
                    )
                    return
            except ValueError:
                await update.message.reply_text(
                    "❌ Please enter a valid number or type `skip`\\.",
                    parse_mode="MarkdownV2"
                )
                return
            
        upsert_user_profile(
            user_id, profile['display_name'], profile['emoji'], profile['bio'],
            profile['is_active'], profile.get('gender', ''), age,
            profile.get('department', ''), profile.get('year', ''),
            profile.get('religion', ''), profile.get('relationship_status', ''),
            profile.get('other_info', '')
        )
        context.user_data.pop('profile_state', None)
        context.user_data.pop('state', None)
        await update.message.reply_text(
            "✅ Age updated\\!",
            parse_mode="MarkdownV2"
        )
        await show_edit_details_menu(update, context)
        return
    
    # Handle editing name from edit menu (not creation wizard)
    if profile_state == 'editing_name_only':
        user_id = update.effective_user.id
        profile = get_user_profile(user_id)
        if not profile:
            return
        
        if len(text) < 2 or len(text) > 32:
            await update.message.reply_text(
                "❌ Display name must be between 2 and 32 characters\\. Please try again\\.",
                parse_mode="MarkdownV2"
            )
            return
        
        upsert_user_profile(
            user_id, text, profile['emoji'], profile['bio'],
            profile['is_active'], profile.get('gender', ''), profile.get('age'),
            profile.get('department', ''), profile.get('year', ''),
            profile.get('religion', ''), profile.get('relationship_status', ''),
            profile.get('other_info', '')
        )
        context.user_data.pop('profile_state', None)
        context.user_data.pop('state', None)
        await update.message.reply_text(
            "✅ Name updated\\!",
            parse_mode="MarkdownV2"
        )
        # Show updated profile
        updated_profile = get_user_profile(user_id)
        await send_profile_overview(update, context, updated_profile)
        return
    
    # Handle editing bio from edit menu (not creation wizard)
    if profile_state == 'editing_bio_only':
        user_id = update.effective_user.id
        profile = get_user_profile(user_id)
        if not profile:
            return
        
        if text.lower() in {"skip", "none", "-"}:
            bio = ''
        else:
            if len(text) > 250:
                await update.message.reply_text(
                    "❌ Bio is too long\\. Please keep it under 250 characters and try again\\.",
                    parse_mode="MarkdownV2"
                )
                return
            bio = text
        
        upsert_user_profile(
            user_id, profile['display_name'], profile['emoji'], bio,
            profile['is_active'], profile.get('gender', ''), profile.get('age'),
            profile.get('department', ''), profile.get('year', ''),
            profile.get('religion', ''), profile.get('relationship_status', ''),
            profile.get('other_info', '')
        )
        context.user_data.pop('profile_state', None)
        context.user_data.pop('state', None)
        await update.message.reply_text(
            "✅ Bio updated\\!",
            parse_mode="MarkdownV2"
        )
        # Show updated profile
        updated_profile = get_user_profile(user_id)
        await send_profile_overview(update, context, updated_profile)
        return
        
    if profile_state == 'editing_department':
        user_id = update.effective_user.id
        profile = get_user_profile(user_id)
        if not profile:
            return
            
        department = '' if text.lower() in {"skip", "none", "-"} else text[:100]
            
        upsert_user_profile(
            user_id, profile['display_name'], profile['emoji'], profile['bio'],
            profile['is_active'], profile.get('gender', ''), profile.get('age'),
            department, profile.get('year', ''),
            profile.get('religion', ''), profile.get('relationship_status', ''),
            profile.get('other_info', '')
        )
        context.user_data.pop('profile_state', None)
        context.user_data.pop('state', None)
        await update.message.reply_text(
            "✅ Department updated\\!",
            parse_mode="MarkdownV2"
        )
        await show_edit_details_menu(update, context)
        return
        
    if profile_state == 'editing_religion':
        user_id = update.effective_user.id
        profile = get_user_profile(user_id)
        if not profile:
            return
            
        religion = '' if text.lower() in {"skip", "none", "-"} else text[:50]
            
        upsert_user_profile(
            user_id, profile['display_name'], profile['emoji'], profile['bio'],
            profile['is_active'], profile.get('gender', ''), profile.get('age'),
            profile.get('department', ''), profile.get('year', ''),
            religion, profile.get('relationship_status', ''),
            profile.get('other_info', '')
        )
        context.user_data.pop('profile_state', None)
        context.user_data.pop('state', None)
        await update.message.reply_text(
            "✅ Religion updated\\!",
            parse_mode="MarkdownV2"
        )
        await show_edit_details_menu(update, context)
        return
        
    if profile_state == 'editing_other_info':
        user_id = update.effective_user.id
        profile = get_user_profile(user_id)
        if not profile:
            return
            
        other_info = '' if text.lower() in {"skip", "none", "-"} else text[:500]
            
        upsert_user_profile(
            user_id, profile['display_name'], profile['emoji'], profile['bio'],
            profile['is_active'], profile.get('gender', ''), profile.get('age'),
            profile.get('department', ''), profile.get('year', ''),
            profile.get('religion', ''), profile.get('relationship_status', ''),
            other_info
        )
        context.user_data.pop('profile_state', None)
        context.user_data.pop('state', None)
        await update.message.reply_text(
            "✅ Other info updated\\!",
            parse_mode="MarkdownV2"
        )
        await show_edit_details_menu(update, context)
        return


async def _resolved(value):
    """Awaitable placeholder so a skipped lookup can take part in asyncio.gather."""
    return value


async def show_profile_card(update: Update, context: ContextTypes.DEFAULT_TYPE, profile_user_id: int, back_to_request_contact_id: Optional[int] = None):
    """Show a user's profile card with contact/block options.
    
    Args:
        update: Telegram Update object
        context: Telegram Context object
        profile_user_id: ID of user whose profile to show
        back_to_request_contact_id: Optional contact ID to return to when showing profile from a contact request
    """
    from html import escape as html_escape
    
    viewer_id = update.effective_user.id if update.effective_user else None

    from ranking_integration import ranking_manager

    checks_block = bool(viewer_id and viewer_id != profile_user_id)
    profile, stats, user_rank, is_blocked = await asyncio.gather(
        AsyncDBWrapper.run_sync(get_user_profile, profile_user_id),
        AsyncDBWrapper.run_sync(get_user_profile_stats, profile_user_id),
        AsyncDBWrapper.run_sync(ranking_manager.get_user_rank, profile_user_id),
        AsyncDBWrapper.run_sync(is_profile_blocked_either_way, viewer_id, profile_user_id)
        if checks_block else _resolved(False),
        return_exceptions=True,
    )

    for label, value in (
        ("profile", profile), ("stats", stats),
        ("rank info", user_rank), ("profile blocks", is_blocked),
    ):
        if isinstance(value, Exception):
            logger.error(f"Error fetching {label} for {profile_user_id}: {value}")

    if isinstance(profile, Exception):
        profile = None
    if not profile or not profile.get('is_active'):
        # Simple HTML message when profile is not available
        text = (
            "<b>👤 Profile not available</b>\n\n"
            "This user either has not created a profile or chose to hide it."
        )
        target_message = update.message or (update.callback_query.message if update.callback_query else None)
        if target_message:
            await target_message.reply_text(text, parse_mode="HTML")
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode="HTML",
            )
        return

    # Build safe HTML for profile fields
    name_raw = (profile.get('emoji') or '') + ' ' + (profile.get('display_name') or '')
    name_line = html_escape(name_raw.strip() if name_raw.strip() else "Anonymous")
    bio = profile.get('bio') or ''
    bio_display = html_escape(bio) if bio else "No bio set yet."

    # Build details block only with non-empty fields
    details_lines = []
    gender = (profile.get('gender') or '').strip()
    age_val = profile.get('age')
    department = (profile.get('department') or '').strip()
    year = (profile.get('year') or '').strip()
    religion = (profile.get('religion') or '').strip()
    relationship = (profile.get('relationship_status') or '').strip()
    other = (profile.get('other_info') or '').strip()

    if gender:
        details_lines.append(f"Gender: {html_escape(gender)}")
    if age_val is not None:
        details_lines.append(f"Age: {html_escape(str(age_val))}")
    if department:
        details_lines.append(f"Department: {html_escape(department)}")
    if year:
        details_lines.append(f"Year: {html_escape(year)}")
    if religion:
        details_lines.append(f"Religion: {html_escape(religion)}")
    if relationship:
        details_lines.append(f"Relationship: {html_escape(relationship)}")
    if other:
        short_other = other[:100] + '...' if len(other) > 100 else other
        details_lines.append(f"Other Info: {html_escape(short_other)}")

    # Basic stats for the profile owner
    if isinstance(stats, dict):
        conf_count = stats.get('confessions', 0)
        comm_count = stats.get('comments', 0)
    else:
        conf_count = comm_count = 0

    conf_count_str = html_escape(str(conf_count))
    comm_count_str = html_escape(str(comm_count))
    
    # Get user's rank information
    rank_info = ""
    if user_rank and not isinstance(user_rank, Exception):
        rank_emoji = user_rank.rank_emoji
        rank_name = user_rank.rank_name
        total_points = user_rank.total_points
        
        # Format rank with special styling for special ranks
        if user_rank.is_special_rank:
            rank_info = f"✨ {rank_emoji} <b>{html_escape(rank_name)}</b> ✨\n"
            rank_info += f"💎 <b>{html_escape(str(total_points))}</b> points\n"
        else:
            rank_info = f"{rank_emoji} <b>{html_escape(rank_name)}</b>\n"
            rank_info += f"💎 <b>{html_escape(str(total_points))}</b> points\n"

    lines = [
        "<b>👤 User Profile</b>",
        "",
        f"Name: {name_line}",
        f"Bio: {bio_display}",
    ]
    
    # Add rank information if available
    if rank_info:
        lines.append("")
        lines.append(rank_info.strip())
    
    # Add details if any exist
    if details_lines:
        lines.append("")
        lines.append("<b>Details:</b>")
        lines.extend(details_lines)
    
    lines.extend([
        "",
        f"📨 Confessions: {conf_count_str}",
        f"💬 Comments: {comm_count_str}",
    ])
    
    if viewer_id == profile_user_id:
        lines.append("")
        lines.append("You are viewing <b>your own</b> profile.")
    text = "\n".join(lines)

    buttons = []
    # Add back button if this profile is shown from a contact request
    if back_to_request_contact_id is not None:
        # When showing profile from a contact request, only show the back button
        buttons.append([InlineKeyboardButton("🔙 Back to Request", callback_data=f"view_request_{back_to_request_contact_id}")])
    else:
        # Normal profile view - show all buttons
        if viewer_id and viewer_id != profile_user_id:
            # Check if contact is allowed
            can_contact = not (is_blocked is True)
            if can_contact and profile.get('is_active'):
                buttons.append([InlineKeyboardButton("💬 Contact", callback_data=f"profile_contact_{profile_user_id}")])
            buttons.append([InlineKeyboardButton("🚫 Block user", callback_data=f"profile_block_{profile_user_id}")])
        else:
            # Viewer is owner or unknown; offer edit shortcut
            buttons.append([InlineKeyboardButton("✏️ Edit My Profile", callback_data="profile_edit")])
        buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu")])
    reply_markup = InlineKeyboardMarkup(buttons)

    # Send or edit the message using HTML parse mode
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )


async def handle_profile_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Relay messages between two users in an active profile chat."""
    if not update.message:
        return

    # Only text messages are supported for now
    if not update.message.text:
        await update.message.reply_text(
            "❗ Currently only text messages are supported in profile chats\\\\.\n"
            "Please send a text message, or use the main menu to exit\\\\."
        )
        return

    user_id = update.message.from_user.id
    partner_id = context.user_data.get('profile_chat_partner')
    contact_id = context.user_data.get('profile_contact_id')
    
    # Check if user is trying to use menu commands - allow these to bypass chat state
    text = update.message.text.strip()
    menu_commands = [
        "🙊 Confess/Ask Question",
        "👤 My Profile", 
        "🏆 My Rank",
        "📊 My Stats",
        "🔥 Trending",
        "⭐ Popular Today",
        "📅 Daily Digest",
        "📞 Contact Admin",
        "❓ Help/About",
        "🔧 Admin Dashboard",
        MENU_BUTTON
    ]
    
    if text in menu_commands:
        # Clear chat state and allow normal menu processing
        context.user_data.pop('state', None)
        context.user_data.pop('reply_mode_active', None)
        context.user_data.pop('profile_chat_partner', None)
        context.user_data.pop('profile_contact_id', None)
        # Re-process the message through the main handler
        await handle_menu_choice(update, context)
        return

    # Check if user has clicked the Reply button (reply_mode is active)
    if not context.user_data.get('reply_mode_active'):
        await update.message.reply_text(
            "❗ To send a message, please click the ↩️ Reply button on the message you want to respond to\\."
        )
        return

    if not partner_id or not contact_id:
        await update.message.reply_text(
            "❗ This chat session is not active anymore\\. Use the profile link again to start a new chat\\."
        )
        context.user_data.pop('state', None)
        context.user_data.pop('reply_mode_active', None)
        return

    # Verify contact is still active and not blocked
    contact, is_blocked, daily_count, sender_profile = await asyncio.gather(
        AsyncDBWrapper.run_sync(get_profile_contact_by_id, contact_id),
        AsyncDBWrapper.run_sync(is_profile_blocked_either_way, user_id, partner_id),
        AsyncDBWrapper.run_sync(get_user_daily_message_count, user_id),
        AsyncDBWrapper.run_sync(get_user_profile, user_id),
        return_exceptions=True,
    )

    for label, value in (
        ("contact", contact), ("blocks", is_blocked),
        ("daily message count", daily_count), ("sender profile", sender_profile),
    ):
        if isinstance(value, Exception):
            logger.error(f"Error fetching {label} for profile chat {contact_id}: {value}")

    if isinstance(contact, Exception):
        contact = None
    if isinstance(sender_profile, Exception):
        sender_profile = None

    if not contact or contact.get('status') != 'active':
        await update.message.reply_text(
            "❗ This chat has ended\\\\. You can send a new request from the user's profile\\\\."
        )
        context.user_data.pop('state', None)
        context.user_data.pop('reply_mode_active', None)
        return

    if is_blocked is True:
        await update.message.reply_text(
            "🚫 This chat is no longer available\\\\."
        )
        context.user_data.pop('state', None)
        context.user_data.pop('reply_mode_active', None)
        return

    # Check if user has exceeded daily message limit (10 messages per day)
    if isinstance(daily_count, int) and daily_count >= 20:
        await update.message.reply_text(
            "❗ You've reached your daily message limit \\(10 messages per day\\)\\.\n"
            "Please try again tomorrow\\."
        )
        return

    # Allow any message length (even single letters)
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text(
            "❗ Your message cannot be empty\\. Please write a message\\."
        )
        return

    # Increment message count for the user
    await AsyncDBWrapper.run_sync(increment_user_daily_message_count, user_id)

    # Disable reply mode after sending a message
    context.user_data['reply_mode_active'] = False

    if sender_profile:
        name_raw = (sender_profile.get('emoji') or '') + ' ' + (sender_profile.get('display_name') or '')
        name_line = escape_markdown_text(name_raw.strip() if name_raw.strip() else "Anonymous")
    else:
        name_line = escape_markdown_text("Anonymous")

    relay_text = (
        f"💬 *New message from {name_line}*\n\n"
        f"{escape_markdown_text(text)}"
    )

    # Buttons to end, block, or reply to chat
    keyboard = [
        [
            InlineKeyboardButton("🔚 End Chat", callback_data=f"profile_end_{contact_id}"),
            InlineKeyboardButton("🚫 Block User", callback_data=f"profile_block_chat_{contact_id}"),
        ],
        [
            InlineKeyboardButton("↩️ Reply", callback_data=f"profile_reply_{contact_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=partner_id,
            text=relay_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2",
        )
    except Exception as e:
        logger.error(f"Error relaying profile chat message {contact_id}: {e}")
        await update.message.reply_text(
            "❗ Failed to deliver your message\\\\. Please try again later\\\\."
        )
        # Re-enable reply mode if message failed to send
        context.user_data['reply_mode_active'] = True
        return

    try:
        await AsyncDBWrapper.run_sync(touch_profile_contact, contact_id)
    except Exception as e:
        logger.error(f"Error touching profile contact {contact_id}: {e}")

    await update.message.reply_text(
        "✅ *Message Delivered\\!*\n\n"
        "Your message has been sent successfully\\.\n\n"
        "🔄 *Next steps:*\n"
        "• Click the ↩️ Reply button on any message to respond\n"
        "• Use chat controls below",
        parse_mode="MarkdownV2",
    )


# Confession Flow
async def start_confession_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the simplified confession submission flow"""
    # Directly go to category selection without asking for content type
    await choose_categories_flow(update, context, direct_call=True)

async def choose_categories_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, direct_call=False):
    """Show category selection with max 3 categories limit - 3 column layout"""
    keyboard = []
    # Create three-column layout for categories
    for i in range(0, len(CATEGORIES), 3):
        row = []
        row.append(InlineKeyboardButton(CATEGORIES[i], callback_data=f"category_{i}"))
        if i + 1 < len(CATEGORIES):
            row.append(InlineKeyboardButton(CATEGORIES[i + 1], callback_data=f"category_{i + 1}"))
        if i + 2 < len(CATEGORIES):
            row.append(InlineKeyboardButton(CATEGORIES[i + 2], callback_data=f"category_{i + 2}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("✅ Done Selecting", callback_data="categories_done")])
    keyboard.append([InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.user_data['selected_categories'] = []
    
    # Set content type to flexible for the streamlined flow
    if direct_call:
        context.user_data['content_type'] = 'flexible'  # Accept any media type
    
    MAX_CATEGORIES = 3
    message_text = (
        f"📝 *Choose categories for your confession/question:*\n\n"
        f"You can select up to {MAX_CATEGORIES} categories\. Click on each category you want, then click '✅ Done Selecting' when finished\."
    )
    
    if direct_call:
        # Direct call from menu - send new message
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    else:
        # Callback from content type selection - edit existing message
        content_type = context.user_data.get('content_type', 'text')
        content_type_display = {
            'text': '📝 Text',
            'photo': '📷 Photo',
            'video': '🎥 Video',
            'animation': '🎭 GIF',
            'photo_text': '📷📝 Photo + Text',
            'video_text': '🎥📝 Video + Text'
        }.get(content_type, '📝 Text')
        
        await update.callback_query.edit_message_text(
            f"📝 *Choose categories for your {content_type_display} confession/question:*\n\n"
            f"You can select up to {MAX_CATEGORIES} categories\. Click on each category you want, then click '✅ Done Selecting' when finished\.",
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    
    context.user_data['state'] = 'choosing_category'

async def content_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle content type selection"""
    query = update.callback_query
    await query.answer()
    
    if not query.data:
        return
    
    content_type = query.data.replace("content_type_", "")
    context.user_data['content_type'] = content_type
    
    # Show feedback for selected content type
    content_type_names = {
        'text': '📝 Text Only',
        'photo': '📷 Photo',
        'video': '🎥 Video',
        'animation': '🎭 GIF/Animation',
        'photo_text': '📷📝 Photo + Text',
        'video_text': '🎥📝 Video + Text'
    }
    
    selected_name = content_type_names.get(content_type, 'Unknown')
    await query.answer(f"✅ Selected: {selected_name}")
    
    # Proceed to category selection
    await choose_categories_flow(update, context)

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle multiple category selection with max 3 categories limit"""
    query = update.callback_query
    await query.answer()
    
    if not query.data:
        return
    
    if query.data == "categories_done":
        selected_categories = context.user_data.get('selected_categories', [])
        if not selected_categories:
            await query.answer("❗ Please select at least one category!")
            return
        
        categories_text = ", ".join(selected_categories)
        context.user_data['selected_category'] = categories_text
        
        # Get content type to determine next step
        content_type = context.user_data.get('content_type', 'text')
        
        if content_type == 'text':
            # For text-only confessions, proceed to text writing
            context.user_data['state'] = 'writing_confession'
            
            # Create cancel button for the confession writing interface
            cancel_keyboard = [[InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")]]
            cancel_reply_markup = InlineKeyboardMarkup(cancel_keyboard)
            
            await query.edit_message_text(
                f"📝 *Categories selected: {escape_markdown_text(categories_text)}*\n\n"
                f"Now write your confession or question\. You have up to {MAX_CONFESSION_LENGTH} characters\.\n\n"
                f"Type your message below or use the Cancel button to return to menu\:",
                reply_markup=cancel_reply_markup,
                parse_mode="MarkdownV2"
            )
        elif content_type == 'flexible':
            # For flexible confessions (streamlined flow), accept text or media
            context.user_data['state'] = 'writing_confession'
            
            # Create cancel button for the flexible confession interface
            cancel_keyboard = [[InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")]]
            cancel_reply_markup = InlineKeyboardMarkup(cancel_keyboard)
            
            await query.edit_message_text(
                f"📝 *Categories selected: {escape_markdown_text(categories_text)}*\n\n"
                f"Now send your confession or question\. You can:\n"
                f"• Type text \(up to {MAX_CONFESSION_LENGTH} characters\)\n"
                f"• Send a photo/video/GIF with optional caption\n\n"
                f"Send your content below or use the Cancel button to return to menu\:",
                reply_markup=cancel_reply_markup,
                parse_mode="MarkdownV2"
            )
        else:
            # For media confessions, proceed to media capture
            context.user_data['state'] = 'waiting_for_media'
            
            # Create instructions based on content type
            media_instructions = {
                'photo': '📷 Please send a photo for your confession\.',
                'video': '🎥 Please send a video for your confession\.',
                'animation': '🎭 Please send a GIF or animation for your confession\.',
                'photo_text': '📷 Please send a photo for your confession\. You can add text description after sending the photo\.',
                'video_text': '🎥 Please send a video for your confession\. You can add text description after sending the video\.'
            }
            
            instruction = media_instructions.get(content_type, 'Please send your media\.')
            
            # Create cancel button for the media waiting interface
            cancel_keyboard = [[InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")]]
            cancel_reply_markup = InlineKeyboardMarkup(cancel_keyboard)
            
            await query.edit_message_text(
                f"📝 *Categories selected: {escape_markdown_text(categories_text)}*\n\n"
                f"{instruction}\n\n"
                f"Use the Cancel button below to return to the main menu\.",
                reply_markup=cancel_reply_markup,
                parse_mode="MarkdownV2"
            )
        return
        
    category_idx = int(query.data.replace("category_", ""))
    category = CATEGORIES[category_idx]
    
    selected_categories = context.user_data.get('selected_categories', [])
    
    # Check if trying to add a new category when already at max
    MAX_CATEGORIES = 3
    if category not in selected_categories and len(selected_categories) >= MAX_CATEGORIES:
        await query.answer(f"⚠️ Maximum {MAX_CATEGORIES} categories allowed!\nRemove one to add another.", show_alert=True)
        return
    
    if category in selected_categories:
        selected_categories.remove(category)
        await query.answer(f"❌ Removed: {category}")
    else:
        selected_categories.append(category)
        await query.answer(f"✅ Added: {category}")
    
    context.user_data['selected_categories'] = selected_categories
    
    # Update the keyboard to show selected categories in three columns
    keyboard = []
    # Create three-column layout for categories with selection indicators
    for i in range(0, len(CATEGORIES), 3):
        row = []
        prefix1 = "✅ " if CATEGORIES[i] in selected_categories else ""
        row.append(InlineKeyboardButton(f"{prefix1}{CATEGORIES[i]}", callback_data=f"category_{i}"))
        if i + 1 < len(CATEGORIES):
            prefix2 = "✅ " if CATEGORIES[i + 1] in selected_categories else ""
            row.append(InlineKeyboardButton(f"{prefix2}{CATEGORIES[i + 1]}", callback_data=f"category_{i + 1}"))
        if i + 2 < len(CATEGORIES):
            prefix3 = "✅ " if CATEGORIES[i + 2] in selected_categories else ""
            row.append(InlineKeyboardButton(f"{prefix3}{CATEGORIES[i + 2]}", callback_data=f"category_{i + 2}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("✅ Done Selecting", callback_data="categories_done")])
    keyboard.append([InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    selected_text = f"\n\n*Selected: {', '.join(selected_categories)}*" if selected_categories else ""
    remaining = MAX_CATEGORIES - len(selected_categories)
    remaining_text = f"\n*You can select {remaining} more categor{'y' if remaining == 1 else 'ies'}.*" if remaining > 0 else "\n*Maximum categories reached.*"
    
    await query.edit_message_text(
        f"📝 *Choose categories for your confession/question:*\n\n"
        f"You can select up to {MAX_CATEGORIES} categories\. Click on each category you want, then click '✅ Done Selecting' when finished\.\n"
        f"{escape_markdown_text(selected_text)}{escape_markdown_text(remaining_text)}",
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def handle_confession_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confession text or media submission"""
    # Treat any known button text (menu, cancel, etc.) as navigation, not content
    if update.message.text and is_button_text(update.message.text):
        await show_menu(update, context, "🏠 Confession cancelled. Returned to main menu.")
        return
    
    category = context.user_data.get('selected_category')
    user_id = update.message.from_user.id
    
    # Initialize variables for content and media
    content = ""
    media_file_id = None
    media_type = None
    caption = None
    
    # Handle text messages
    if update.message.text:
        content = sanitize_content(update.message.text)
        if not content:
            await update.message.reply_text(
                "❗ Your message needs to be at least 5 meaningful characters long. "
                "Please write a proper confession or question and try again. "
                "All languages including Amharic are supported!"
            )
            return
        
        if len(content) > MAX_CONFESSION_LENGTH:
            await update.message.reply_text(f"❗ Your confession is too long. Please keep it under {MAX_CONFESSION_LENGTH} characters.")
            return
    
    # Handle media messages
    elif update.message.photo:
        # Handle photo submissions
        largest_photo = max(update.message.photo, key=lambda p: p.file_size or 0)
        media_file_id = largest_photo.file_id
        media_type = "photo"
        
        # Validate photo
        file_info = await context.bot.get_file(media_file_id)
        is_valid, error_msg = validate_media(file_info, "photo")
        
        if not is_valid:
            await update.message.reply_text(f"❗ {error_msg}")
            return
        
        # Get caption if provided
        if update.message.caption:
            caption = sanitize_content(update.message.caption)
            is_valid_caption, caption_error = validate_caption(caption)
            if not is_valid_caption:
                await update.message.reply_text(f"❗ {caption_error}")
                return
        
        content = caption or "[Photo]"
    
    elif update.message.video:
        # Handle video submissions
        video = update.message.video
        media_file_id = video.file_id
        media_type = "video"
        
        # Validate video
        is_valid, error_msg = validate_media(video, "video")
        
        if not is_valid:
            await update.message.reply_text(f"❗ {error_msg}")
            return
        
        # Get caption if provided
        if update.message.caption:
            caption = sanitize_content(update.message.caption)
            is_valid_caption, caption_error = validate_caption(caption)
            if not is_valid_caption:
                await update.message.reply_text(f"❗ {caption_error}")
                return
        
        content = caption or "[Video]"
    
    elif update.message.animation:
        # Handle GIF/animation submissions
        animation = update.message.animation
        media_file_id = animation.file_id
        media_type = "animation"
        
        # Validate animation
        is_valid, error_msg = validate_media(animation, "animation")
        
        if not is_valid:
            await update.message.reply_text(f"❗ {error_msg}")
            return
        
        # Get caption if provided
        if update.message.caption:
            caption = sanitize_content(update.message.caption)
            is_valid_caption, caption_error = validate_caption(caption)
            if not is_valid_caption:
                await update.message.reply_text(f"❗ {caption_error}")
                return
        
        content = caption or "[GIF]"
    
    elif update.message.document:
        # Handle document submissions (optional, if you want to support documents)
        document = update.message.document
        media_file_id = document.file_id
        media_type = "document"
        
        # Validate document
        is_valid, error_msg = validate_media(document, "document")
        
        if not is_valid:
            await update.message.reply_text(f"❗ {error_msg}")
            return
        
        # Get caption if provided
        if update.message.caption:
            caption = sanitize_content(update.message.caption)
            is_valid_caption, caption_error = validate_caption(caption)
            if not is_valid_caption:
                await update.message.reply_text(f"❗ {caption_error}")
                return
        
        content = caption or f"[Document: {document.file_name or 'Unknown'}]"
    
    else:
        await update.message.reply_text("❗ Please send text, photo, video, GIF, or use the cancel button.")
        return
    
    # Save submission with media info
    post_id, error = save_submission(
        user_id, 
        content, 
        category, 
        media_type=media_type,
        file_id=media_file_id,
        caption=caption
    )
    
    if error:
        await update.message.reply_text(f"❗ Error saving confession: {error}")
        return
    
    # Points will be awarded only after admin approval
    # await award_points_for_confession_submission(user_id, post_id, category, context)
    
    # Send to admins for approval with media
    await send_to_admins_for_approval(context, post_id, content, category, user_id, media_file_id, media_type)
    
    # Determine submission type for confirmation message
    submission_type = "confession"
    if media_type:
        emoji = get_media_type_emoji(media_type)
        submission_type = f"{emoji} {media_type} confession"
    
    await update.message.reply_text(
        f"✅ *{submission_type.title()} Submitted\\!*\n\n"
        "Your submission has been sent to administrators for review\\. "
        "You'll be notified once it's approved or if there are any issues\\.",
        parse_mode="MarkdownV2"
    )
    
    await show_menu(update, context)

async def send_to_admins_for_approval(context, post_id, content, category, user_id, media_file_id=None, media_type=None):
    """Send confession to admins for approval (with media support)"""
    admin_text = f"""
📝 *New Confession Submission*

*ID:* {escape_markdown_text(f'#{post_id}')}
*Category:* {escape_markdown_text(category)}
*Submitter:* {user_id}
"""
    
    if media_type:
        media_emoji = get_media_type_emoji(media_type)
        admin_text += f"\n*Type:* {media_emoji} {escape_markdown_text(media_type.title())}"
    
    admin_text += f"\n\n*Content:*\n{escape_markdown_text(content)}"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton("🔞 Approve 18+", callback_data=f"approve18_{post_id}"),
        ],
        [
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{post_id}"),
        ],
        [
            InlineKeyboardButton("🚩 Flag", callback_data=f"flag_{post_id}"),
            InlineKeyboardButton("⛔ Block User", callback_data=f"block_{user_id}")
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send to both full admins and mini admins
    all_admin_ids = ADMIN_IDS + MINI_ADMIN_IDS
    
    for admin_id in all_admin_ids:
        try:
            if media_file_id and media_type:
                # Send media with admin text as caption
                if media_type == 'photo':
                    await context.bot.send_photo(
                        chat_id=admin_id,
                        photo=media_file_id,
                        caption=admin_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif media_type == 'video':
                    await context.bot.send_video(
                        chat_id=admin_id,
                        video=media_file_id,
                        caption=admin_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif media_type == 'gif':
                    await context.bot.send_animation(
                        chat_id=admin_id,
                        animation=media_file_id,
                        caption=admin_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif media_type == 'document':
                    await context.bot.send_document(
                        chat_id=admin_id,
                        document=media_file_id,
                        caption=admin_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                else:
                    # Fallback to text message if media type not recognized
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
            else:
                # Send text message for text-only confessions
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
        except Exception as e:
            logger.error(f"Failed to send to admin {admin_id}: {e}")

async def handle_media_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media submission (photo, video, animation/GIF) with auto-detection"""
    if not update.message:
        return
    
    content_type = context.user_data.get('content_type', 'flexible')
    category = context.user_data.get('selected_category')
    user_id = update.message.from_user.id
    
    # Auto-detect media type from the message
    media_data = None
    detected_type = None
    
    # Check for different media types and auto-detect
    if update.message.photo:
        # Get the largest photo size
        photo = update.message.photo[-1]
        media_data = {
            'type': 'photo',
            'file_id': photo.file_id,
            'file_unique_id': photo.file_unique_id,
            'caption': update.message.caption,
            'file_size': photo.file_size,
            'width': photo.width,
            'height': photo.height
        }
        detected_type = 'photo'
        
    elif update.message.video:
        video = update.message.video
        media_data = {
            'type': 'video',
            'file_id': video.file_id,
            'file_unique_id': video.file_unique_id,
            'caption': update.message.caption,
            'file_size': video.file_size,
            'mime_type': video.mime_type,
            'duration': video.duration,
            'width': video.width,
            'height': video.height,
            'thumbnail_file_id': video.thumbnail.file_id if video.thumbnail else None
        }
        detected_type = 'video'
        
    elif update.message.animation:
        animation = update.message.animation
        media_data = {
            'type': 'animation',
            'file_id': animation.file_id,
            'file_unique_id': animation.file_unique_id,
            'caption': update.message.caption,
            'file_size': animation.file_size,
            'mime_type': animation.mime_type,
            'duration': animation.duration,
            'width': animation.width,
            'height': animation.height,
            'thumbnail_file_id': animation.thumbnail.file_id if animation.thumbnail else None
        }
        detected_type = 'animation'
    
    # For legacy content type selection flow, still check compatibility
    if content_type != 'flexible' and content_type not in ['photo_text', 'video_text']:
        # This is the old flow - check if media matches selected type
        if not media_data:
            # No media detected but media was expected
            media_type_names = {
                'photo': '📷 photo',
                'video': '🎥 video', 
                'animation': '🎭 GIF/animation'
            }
            expected_media = media_type_names.get(content_type, 'media')
            
            await update.message.reply_text(
                f"❗ Please send a {expected_media} as requested. "
                f"You selected '{content_type}' but sent a different type of content."
            )
            return
        
        # Check if detected type matches selected type
        if detected_type != content_type:
            media_type_names = {
                'photo': '📷 photo',
                'video': '🎥 video',
                'animation': '🎭 GIF/animation'
            }
            expected_media = media_type_names.get(content_type, 'media')
            
            await update.message.reply_text(
                f"❗ Please send a {expected_media} as requested. "
                f"You selected '{content_type}' but sent {detected_type}."
            )
            return
    
    elif content_type in ['photo_text', 'video_text']:
        # Handle combo submissions in legacy flow
        base_type = content_type.split('_')[0]  # 'photo' or 'video'
        
        if detected_type != base_type:
            media_type_display = '📷 photo' if base_type == 'photo' else '🎥 video'
            await update.message.reply_text(
                f"❗ Please send a {media_type_display} as requested for {content_type}."
            )
            return
    
    # Handle case where no media was detected
    if not media_data:
        if content_type == 'flexible':
            # For flexible mode, this means they didn't send media - ask them to send media or text
            await update.message.reply_text(
                "📝 I can accept photos, videos, GIFs, or text confessions. "
                "Please send your media or write your text confession!"
            )
            return
        else:
            # For legacy specific modes, show specific error
            media_type_names = {
                'photo': '📷 photo',
                'video': '🎥 video',
                'animation': '🎭 GIF/animation',
                'photo_text': '📷 photo',
                'video_text': '🎥 video'
            }
            expected_media = media_type_names.get(content_type, 'media')
            
            await update.message.reply_text(
                f"❗ Please send a {expected_media} as requested. "
                f"You selected '{content_type}' but sent a different type of content."
            )
            return
    
    # Check if this is a combo type that needs additional text
    if content_type in ['photo_text', 'video_text']:
        # Store media data and ask for text
        context.user_data['media_data'] = media_data
        context.user_data['state'] = 'waiting_for_text_after_media'
        
        media_type_display = '📷 photo' if content_type == 'photo_text' else '🎥 video'
        
        # Create cancel button
        cancel_keyboard = [[InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")]]
        cancel_reply_markup = InlineKeyboardMarkup(cancel_keyboard)
        
        await update.message.reply_text(
            f"✅ *{media_type_display.title()} received\\!*\n\n"
            f"Now please send the text description for your confession\\. "
            f"You have up to {MAX_CONFESSION_LENGTH} characters\\.",
            reply_markup=cancel_reply_markup,
            parse_mode="MarkdownV2"
        )
        return
    
    # For media-only posts, save immediately
    post_id, error = save_submission(user_id, media_data.get('caption'), category, media_data)
    
    if error:
        await update.message.reply_text(f"❗ Error saving confession: {error}")
        return
    
    # Award points for confession submission
    await award_points_for_confession_submission(user_id, post_id, category, context)
    
    # Send to admins for approval
    await send_media_to_admins_for_approval(context, post_id, media_data, category, user_id)
    
    await update.message.reply_text(
        "✅ *Media Confession Submitted\\!*\n\n"
        "Your media confession has been sent to administrators for review\\. "
        "You'll be notified once it's approved or if there are any issues\\.",
        parse_mode="MarkdownV2"
    )
    
    await show_menu(update, context)

async def handle_text_after_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input after media submission for combo posts"""
    # Ignore button presses instead of saving them as text content
    if update.message.text and is_button_text(update.message.text):
        await show_menu(update, context, "🏠 Confession cancelled. Returned to main menu.")
        return
    
    content = sanitize_content(update.message.text)
    if not content:
        await update.message.reply_text(
            "❗ Your message needs to be at least 5 meaningful characters long. "
            "Please write a proper description and try again. "
            "All languages including Amharic are supported!"
        )
        return
    
    if len(content) > MAX_CONFESSION_LENGTH:
        await update.message.reply_text(f"❗ Your text is too long. Please keep it under {MAX_CONFESSION_LENGTH} characters.")
        return
    
    # Get stored data
    media_data = context.user_data.get('media_data')
    category = context.user_data.get('selected_category')
    user_id = update.message.from_user.id
    
    if not media_data:
        await update.message.reply_text("❗ Error: Media data not found. Please start over.")
        await show_menu(update, context)
        return
    
    # Save the combo submission
    post_id, error = save_submission(user_id, content, category, media_data)
    
    if error:
        await update.message.reply_text(f"❗ Error saving confession: {error}")
        return
    
    # Award points for confession submission
    await award_points_for_confession_submission(user_id, post_id, category, context)
    
    # Send to admins for approval
    await send_media_to_admins_for_approval(context, post_id, media_data, category, user_id, content)
    
    await update.message.reply_text(
        "✅ *Media \\+ Text Confession Submitted\\!*\n\n"
        "Your media confession with text has been sent to administrators for review\\. "
        "You'll be notified once it's approved or if there are any issues\\.",
        parse_mode="MarkdownV2"
    )
    
    # Clean up context
    context.user_data.pop('media_data', None)
    
    await show_menu(update, context)

async def send_media_to_admins_for_approval(context, post_id, media_data, category, user_id, text_content=None):
    """Send media confession to admins for approval"""
    # Prepare admin message text
    admin_text = f"""
📝 *New Media Confession Submission*

*ID:* {escape_markdown_text(f'#{post_id}')}
*Category:* {escape_markdown_text(category)}
*Submitter:* {user_id}
*Media Type:* {escape_markdown_text(media_data['type'].upper())}
"""
    
    if text_content:
        admin_text += f"\n*Text Content:*\n{escape_markdown_text(text_content)}\n"
    
    if media_data.get('caption'):
        admin_text += f"\n*Media Caption:*\n{escape_markdown_text(media_data['caption'])}\n"
    
    # Add media information
    if media_data.get('file_size'):
        file_size_mb = media_data['file_size'] / (1024 * 1024)
        admin_text += f"\n*File Size:* {file_size_mb:.2f} MB"
    
    if media_data.get('duration'):
        admin_text += f"\n*Duration:* {media_data['duration']} seconds"
        
    if media_data.get('width') and media_data.get('height'):
        admin_text += f"\n*Dimensions:* {media_data['width']}x{media_data['height']}"
    
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
            InlineKeyboardButton("⛔ Block User", callback_data=f"block_{user_id}")
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send to both full admins and mini admins
    all_admin_ids = ADMIN_IDS + MINI_ADMIN_IDS
    
    # Send to each admin
    for admin_id in all_admin_ids:
        try:
            # First send the media
            if media_data['type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=media_data['file_id'],
                    caption=admin_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_data['type'] == 'video':
                await context.bot.send_video(
                    chat_id=admin_id,
                    video=media_data['file_id'],
                    caption=admin_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_data['type'] == 'animation':
                await context.bot.send_animation(
                    chat_id=admin_id,
                    animation=media_data['file_id'],
                    caption=admin_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
        except Exception as e:
            logger.error(f"Failed to send media to admin {admin_id}: {e}")

# Trending Menu System
async def trending_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show trending categories selection menu"""
    trending_text = """
🔥 *Trending Content*

Choose what type of trending content you'd like to see:

💬 *Most Commented:* Posts with the most discussions \\(24h\\)
🔥 *Hot & Rising:* Posts gaining traction fast
👍 *Most Liked:* Posts with the most liked comments
⭐ *All Trending:* Combined trending algorithm

Select a category below:
"""
    
    keyboard = [
        [
            InlineKeyboardButton("💬 Most Commented", callback_data="trending_most_commented"),
            InlineKeyboardButton("🔥 Hot & Rising", callback_data="trending_rising")
        ],
        [
            InlineKeyboardButton("👍 Most Liked", callback_data="trending_most_liked"),
            InlineKeyboardButton("⭐ All Trending", callback_data="trending_all")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        trending_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

# Individual trending category functions
async def show_most_commented_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show most commented posts from last 24 hours"""
    from trending import get_most_commented_posts_24h
    
    most_commented = get_most_commented_posts_24h(8)
    
    if not most_commented:
        await update.callback_query.edit_message_text(
            "💬 *Most Commented Posts \\(24h\\)*\n\n"
            "No posts with comments in the last 24 hours\\. "
            "Be the first to start a discussion\\!",
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the menu and send header
    await update.callback_query.delete_message()
    
    header_text = f"💬 *Most Commented Posts \\(Last 24h\\)*\n\n📈 {len(most_commented)} most discussed posts"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from datetime import datetime
    
    for post in most_commented:
        post_id = post[0]
        content = post[1]
        category = post[2]
        timestamp = post[3]
        comment_count = post[4]
        post_number = post[7] if len(post) > 7 and post[7] is not None else post_id
        
        # Check if this is a media post (media info starts at index 8)
        media_type = post[8] if len(post) > 8 else None
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_ago = format_time_ago(dt)
            escaped_time = escape_markdown_text(time_ago)
        except:
            escaped_time = escape_markdown_text("recently")
        
        # Create buttons
        keyboard = [
            [
                InlineKeyboardButton(f"💬 Join Discussion \\({comment_count}\\)", callback_data=f"see_comments_{post_id}_1"),
                InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send commented post using flexible helper function for proper media handling
        stats_text = f"💬 {comment_count} comments \\| {escaped_time}"
        try:
            await send_trending_media_post(context, update.effective_chat.id, post, reply_markup, stats_text, "most_commented")
        except Exception as e:
            logger.error(f"Error sending commented media post {post_id}: {e}")
            # Fallback to text message if media sending fails
            commented_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(truncate_text(content or '[Media content]', 120))}\n\n"
            commented_text += f"*\\#{post_number}* 💬 {comment_count} comments \\| {escaped_time}"
            commented_text += f"\n\n📷 *[Media content unavailable]*"
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=commented_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        
        await asyncio.sleep(0.1)
    
    # Send navigation
    await send_trending_navigation(context, update.effective_chat.id)

async def show_rising_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show hot and rising posts"""
    from trending import get_rising_posts
    
    rising = get_rising_posts(8)
    
    if not rising:
        await update.callback_query.edit_message_text(
            "🚀 *Hot & Rising Posts*\n\n"
            "No rising posts found\\. "
            "Posts appear here when they gain traction quickly\\!",
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the menu and send header
    await update.callback_query.delete_message()
    
    header_text = f"🚀 *Hot & Rising Posts*\n\n📈 {len(rising)} posts gaining traction fast"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from datetime import datetime
    
    for post in rising:
        post_id = post[0]
        content = post[1]
        category = post[2]
        timestamp = post[3]
        comment_count = post[4]
        total_likes = post[5] if len(post) > 5 else 0
        post_number = post[8] if len(post) > 8 and post[8] is not None else post_id
        
        # Check if this is a media post (media info starts at index 9)
        media_type = post[9] if len(post) > 9 else None
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_ago = format_time_ago(dt)
            escaped_time = escape_markdown_text(time_ago)
        except:
            escaped_time = escape_markdown_text("recently")
        
        # Create buttons
        keyboard = [
            [
                InlineKeyboardButton(f"💬 View Comments \\({comment_count}\\)", callback_data=f"see_comments_{post_id}_1"),
                InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send rising post using helper function for proper media handling
        try:
            await send_media_post(context, update.effective_chat.id, post, reply_markup, include_hashtag=False)
        except Exception as e:
            logger.error(f"Error sending rising media post {post_id}: {e}")
            # Fallback to text message if media sending fails
            rising_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(truncate_text(content or '[Media content]', 120))}\n\n"
            rising_text += f"*\\#{post_number}* 🚀 💬 {comment_count} comments"
            if total_likes > 0:
                rising_text += f" \\| 👍 {total_likes} likes"
            rising_text += f" \\| {escaped_time}"
            rising_text += f"\n\n📷 *[Media content unavailable]*"
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=rising_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        
        await asyncio.sleep(0.1)
    
    # Send navigation
    await send_trending_navigation(context, update.effective_chat.id)

async def show_most_liked_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show posts with most liked comments"""
    from trending import get_posts_with_most_liked_comments
    
    liked_posts = get_posts_with_most_liked_comments(8)
    
    if not liked_posts:
        await update.callback_query.edit_message_text(
            "👍 *Most Liked Posts*\n\n"
            "No posts with liked comments found\\. "
            "Start liking comments to see posts here\\!",
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the menu and send header
    await update.callback_query.delete_message()
    
    header_text = f"👍 *Most Liked Posts*\n\n💖 {len(liked_posts)} posts with the most liked comments"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from datetime import datetime
    
    for post in liked_posts:
        post_id = post[0]
        content = post[1]
        category = post[2]
        timestamp = post[3]
        comment_count = post[4]
        total_likes = post[5] if len(post) > 5 else 0
        post_number = post[8] if len(post) > 8 and post[8] is not None else post_id
        
        # Check if this is a media post (media info starts at index 9)
        media_type = post[9] if len(post) > 9 else None
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_ago = format_time_ago(dt)
            escaped_time = escape_markdown_text(time_ago)
        except:
            escaped_time = escape_markdown_text("recently")
        
        # Create buttons
        keyboard = [
            [
                InlineKeyboardButton(f"💬 See Liked Comments \\({comment_count}\\)", callback_data=f"see_comments_{post_id}_1"),
                InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send liked post using flexible helper function for proper media handling
        stats_text = f"👍 {total_likes} total likes \\| 💬 {comment_count} comments \\| {escaped_time}"
        try:
            await send_trending_media_post(context, update.effective_chat.id, post, reply_markup, stats_text, "most_liked")
        except Exception as e:
            logger.error(f"Error sending liked media post {post_id}: {e}")
            # Fallback to text message if media sending fails
            liked_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(truncate_text(content or '[Media content]', 120))}\n\n"
            liked_text += f"*\\#{post_number}* 👍 {total_likes} total likes \\| 💬 {comment_count} comments \\| {escaped_time}"
            liked_text += f"\n\n📷 *[Media content unavailable]*"
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=liked_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        
        await asyncio.sleep(0.1)
    
    # Send navigation
    await send_trending_navigation(context, update.effective_chat.id)

async def show_all_trending_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all trending posts using combined algorithm"""
    from trending import get_trending_posts
    
    trending = get_trending_posts(10)
    
    if not trending:
        await update.callback_query.edit_message_text(
            "⭐ *All Trending Posts*\n\n"
            "No trending posts found\\. "
            "Submit confessions and engage with others to see trending content\\!",
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the menu and send header
    await update.callback_query.delete_message()
    
    header_text = f"⭐ *All Trending Posts*\n\n🔥 {len(trending)} hottest posts right now"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from datetime import datetime
    
    for post in trending:
        post_id = post[0]
        content = post[1]
        category = post[2]
        timestamp = post[3]
        comment_count = post[4]
        total_likes = post[5] if len(post) > 5 else 0
        post_number = post[8] if len(post) > 8 and post[8] is not None else post_id
        
        # Check if this is a media post
        media_type = post[10] if len(post) > 10 else None
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            time_ago = format_time_ago(dt)
            escaped_time = escape_markdown_text(time_ago)
        except:
            escaped_time = escape_markdown_text("recently")
        
        keyboard = [
            [
                InlineKeyboardButton(f"💬 See Comments \\({comment_count}\\)", callback_data=f"see_comments_{post_id}_1"),
                InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # If it's a media post, use send_media_post function
        if media_type:
            # Create a post tuple with additional media stats for caption
            media_stats_text = f"🔥 💬 {comment_count} comments"
            if total_likes > 0:
                media_stats_text += f" | 👍 {total_likes} likes"
            media_stats_text += f" | {time_ago}"
            
            # Create modified post tuple with stats in content
            modified_post = list(post)
            if content:
                modified_post[1] = f"{content}\n\n*#{post_number}* {media_stats_text}"
            else:
                modified_post[1] = f"*#{post_number}* {media_stats_text}"
            
            await send_media_post(
                context,
                update.effective_chat.id,
                tuple(modified_post),
                reply_markup=reply_markup
            )
        else:
            # Text-only post, use original method
            trend_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(truncate_text(content, 120))}\n\n"
            trend_text += f"*\\#{post_number}* 🔥 💬 {comment_count} comments"
            if total_likes > 0:
                trend_text += f" \\| 👍 {total_likes} likes"
            trend_text += f" \\| {escaped_time}"
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=trend_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        
        await asyncio.sleep(0.1)
    
    # Send navigation
    await send_trending_navigation(context, update.effective_chat.id)

async def send_trending_navigation(context, chat_id):
    """Send navigation buttons for trending sections"""
    nav_keyboard = [
        [
            InlineKeyboardButton("🔥 Trending Menu", callback_data="back_to_trending"),
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
        ]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )

async def popular_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's popular posts with most liked comments and rising posts"""
    from trending import get_popular_today_posts, get_posts_with_most_liked_comments
    
    # Get today's popular posts
    popular = get_popular_today_posts(10)
    liked_posts = get_posts_with_most_liked_comments(8)
    
    if not popular and not liked_posts:
        await update.message.reply_text(
            "⭐ *No popular posts today yet\\!*\n\n"
            "Posts become popular when they get comments and likes\\. "
            "Check back later or help make some posts popular by commenting\\!",
            parse_mode="MarkdownV2"
        )
        await show_menu(update, context)
        return

    # Send popular posts header
    header_text = "⭐ *Popular Today*\n\n🌟 *Today's Top Posts*"
    await update.message.reply_text(header_text, parse_mode="MarkdownV2")
    
    import asyncio
    from datetime import datetime
    
    # Show today's popular posts
    if popular:
        for post in popular[:6]:  # Show top 6 popular today
            post_id = post[0]
            content = post[1]
            category = post[2]
            timestamp = post[3]
            comment_count = post[4]
            total_likes = post[5] if len(post) > 5 else 0
            post_number = post[8] if len(post) > 8 and post[8] is not None else post_id  # Use post_number if available, fallback to post_id
            
            # Check if this is a media post (media info starts at index 10)
            media_type = post[10] if len(post) > 10 else None
            
            # Format timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%H:%M')
                escaped_time = escape_markdown_text(formatted_time)
            except:
                escaped_time = escape_markdown_text("today")
            
            # Create buttons
            keyboard = [
                [
                    InlineKeyboardButton(f"💬 See Comments \\({comment_count}\\)", callback_data=f"see_comments_{post_id}_1"),
                    InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send popular post using helper function for proper media handling
            try:
                await send_media_post(context, update.effective_chat.id, post, reply_markup, include_hashtag=False)
            except Exception as e:
                logger.error(f"Error sending popular media post {post_id}: {e}")
                # Fallback to text message if media sending fails
                popular_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(truncate_text(content or '[Media content]', 110))}\n\n"
                popular_text += f"*\\#{post_number}* ⭐ 💬 {comment_count} comments"
                if total_likes > 0:
                    popular_text += f" \\| 👍 {total_likes} likes"
                popular_text += f" \\| {escaped_time}"
                popular_text += f"\n\n📷 *[Media content unavailable]*"
                
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=popular_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            
            await asyncio.sleep(0.15)
    
    # Show most liked comments section
    if liked_posts:
        liked_header = "\n💖 *Posts with Most Liked Comments*"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=liked_header,
            parse_mode="MarkdownV2"
        )
        
        for post in liked_posts[:4]:  # Show top 4 posts with most liked comments
            post_id = post[0]
            content = post[1]
            category = post[2]
            comment_count = post[4]
            total_likes = post[5] if len(post) > 5 else 0
            post_number = post[8] if len(post) > 8 and post[8] is not None else post_id  # Use post_number if available, fallback to post_id
            
            # Check if this is a media post (media info starts at index 9 for liked posts query)
            media_type = post[9] if len(post) > 9 else None
            
            # Create buttons
            keyboard = [[
                InlineKeyboardButton(f"👀 See Liked Comments ({comment_count})", callback_data=f"see_comments_{post_id}_1")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send liked post using helper function for proper media handling
            try:
                await send_media_post(context, update.effective_chat.id, post, reply_markup, include_hashtag=False)
            except Exception as e:
                logger.error(f"Error sending liked media post {post_id}: {e}")
                # Fallback to text message if media sending fails
                liked_text = f"*{escape_markdown_text(category)}*\n{escape_markdown_text(truncate_text(content or '[Media content]', 90))}\n"
                liked_text += f"*\\#{post_number}* 💖 💬 {comment_count} comments \\| 👍 {total_likes} total likes"
                liked_text += f"\n\n📷 *[Media content unavailable]*"
                
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=liked_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            
            await asyncio.sleep(0.15)
    
    # Send navigation
    nav_keyboard = [
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )

# Recent Posts and Comments
async def recent_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent approved confessions"""
    try:
        posts = get_recent_posts_with_media(10)
        
        if not posts:
            await update.message.reply_text("📰 No approved confessions available yet.")
            await show_menu(update, context)
            return

        # Send header message
        header_text = f"📰 *Recent Confessions \\({len(posts)}\\)*\n\n📋 Latest approved posts"
        await update.message.reply_text(
            header_text,
            parse_mode="MarkdownV2"
        )
        
        import asyncio
        
        # Send each post individually to handle media properly
        for post in posts:
            post_id = post[0]
            content = post[1]
            category = post[2]
            media_type = post[10] if len(post) > 10 else None
            comment_count = post[-1] if len(post) > 9 else 0
            
            # Create buttons for each post
            keyboard = [[
                InlineKeyboardButton(
                    f"💬 #{post_id} \\({comment_count} comments\\)", 
                    callback_data=f"view_post_{post_id}"
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Use helper function to send media or text post
            try:
                await send_media_post(context, update.effective_chat.id, post, reply_markup, include_hashtag=True)
            except Exception as e:
                logger.error(f"Error sending media post {post_id}: {e}")
                # Fallback to text-only display
                preview = truncate_text(content if content else "[Media content]", 100)
                fallback_text = f"\\#{post_id} \\| {escape_markdown_text(category)}\n{escape_markdown_text(preview)}"
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=fallback_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            
            await asyncio.sleep(0.1)
        
        # Send navigation message at the end
        nav_keyboard = [
            [InlineKeyboardButton(f"{MENU_BUTTON}", callback_data="menu")]
        ]
        nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="📋 *Navigation*",
            reply_markup=nav_reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in recent_posts: {e}")
        await update.message.reply_text(
            "❗ Sorry, there was an issue loading recent confessions. Please try again."
        )
        await show_menu(update, context)

async def show_post_for_commenting(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    """Show direct comment interface (from 'Add Comment' deep link)"""
    post = get_post_by_id(post_id)
    if not post or post[5] != 1:  # Check if approved (approved field is at index 5, value 1 = approved)
        if update.message:
            await update.message.reply_text("❗ Post not found or not available.")
            await show_menu(update, context)
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Post not found or not available."
            )
        return
    
    content = post[1]
    category = post[2]
    comment_count = await async_get_comment_count(post_id)
    
    context.user_data['comment_post_id'] = post_id
    context.user_data['state'] = 'writing_comment'
    context.user_data.pop('reply_to_comment_id', None)  # Clear any reply state
    
    # Show post content and direct comment interface
    post_text = f"""📝 *{escape_markdown_text(category)}*

{escape_markdown_text(content)}

💬 *Add your comment:*

Type your comment below \\(max {MAX_COMMENT_LENGTH} characters\\)\\.

Use the Cancel button below or type 🚫 Cancel to return to main menu\\."""
    
    # Create cancel button for the deep link comment interface
    cancel_keyboard = [[InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")]]
    cancel_reply_markup = InlineKeyboardMarkup(cancel_keyboard)
    
    if update.message:
        await update.message.reply_text(
            post_text,
            reply_markup=cancel_reply_markup,
            parse_mode="MarkdownV2"
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=post_text,
            reply_markup=cancel_reply_markup,
            parse_mode="MarkdownV2"
        )

async def show_comments_directly(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    """Show comments directly via deep link"""
    try:
        logger.info(f"show_comments_directly called with post_id: {post_id}")
        post = get_post_by_id(post_id)
        logger.info(f"Retrieved post: {post}")
        
        if not post or post[5] != 1:  # Check if approved (approved field is at index 5, value 1 = approved)
            await update.message.reply_text("❗ Post not found or not available.")
            await show_menu(update, context)
            return
    except Exception as e:
        logger.error(f"Error in show_comments_directly: {e}")
        await update.message.reply_text("❗ Sorry, there was an issue processing your request. Please try again.")
        await show_menu(update, context)
        return
    
    # Set the post for viewing
    context.user_data['viewing_post_id'] = post_id
    
    # Show comments starting from page 1
    try:
        logger.info(f"Getting paginated comments for post_id: {post_id}")
        comments_data, current_page, total_pages, total_comments = get_comments_paginated(post_id, 1)
        logger.info(f"Retrieved comments: data={len(comments_data) if comments_data else 0}, current_page={current_page}, total_pages={total_pages}, total_comments={total_comments}")
    except Exception as e:
        logger.error(f"Error getting paginated comments: {e}")
        await update.message.reply_text("❗ Sorry, there was an issue loading comments. Please try again.")
        await show_menu(update, context)
        return
    
    if not comments_data:
        keyboard = [
            [InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{post_id}")],
            [InlineKeyboardButton("🔙 Back to Post", callback_data=f"view_post_{post_id}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "💬 No comments yet\\. Be the first to comment\\!",
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        return
    
    user_id = update.effective_user.id
    
    # Send header message using unified formatting
    header_text = format_comments_header(total_comments, current_page, total_pages)
    await update.message.reply_text(
        header_text,
        parse_mode="HTML"
    )
    
    # Send each comment as a separate message
    for comment_index, comment_data in enumerate(comments_data):
        # Use unified comment formatting function
        formatted_comment = format_comment_display(comment_data, user_id, current_page, comment_index)
        
        # Send the comment
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=formatted_comment['text'],
            reply_markup=formatted_comment['reply_markup'],
            parse_mode=formatted_comment['parse_mode'],
            disable_web_page_preview=True
        )
    
    # Send navigation and action buttons at the end
    nav_keyboard = []
    
    # Navigation buttons
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"see_comments_{post_id}_{current_page-1}"))
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"see_comments_{post_id}_{current_page+1}"))
    
    if nav_buttons:
        nav_keyboard.append(nav_buttons)
    
    # Action buttons
    nav_keyboard.append([
        InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{post_id}"),
        InlineKeyboardButton("🔙 Back to Post", callback_data=f"view_post_{post_id}")
    ])
    nav_keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu")])
    
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    # Send navigation message
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )

async def show_sensitive_confession(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    """Show full sensitive confession privately with comment actions (via deep link) - supports media"""
    from db import is_post_sensitive

    post = get_post_by_id(post_id)
    if not post or post[5] != 1:  # approved field is at index 5
        await update.message.reply_text("❗ Post not found or not available.")
        await show_menu(update, context)
        return

    # If not marked sensitive, still allow viewing but note it
    sensitive = is_post_sensitive(post_id)

    content = post[1]
    category = post[2]
    comment_count = await async_get_comment_count(post_id)
    
    # Debug: Print ALL post fields to identify correct media field positions
    logger.info(f"POST {post_id} retrieved with {len(post)} fields")
    
    # CORRECT field positions based on actual database schema:
    # [0]=post_id, [1]=content, [2]=category, [3]=timestamp, [4]=user_id, [5]=approved,
    # [6]=channel_message_id, [7]=flagged, [8]=likes, [9]=post_number,
    # [10]=status, [11]=is_sensitive, [12]=?, [13]=?,
    # [14]=media_type, [15]=media_file_id, [16]=media_file_unique_id, [17]=media_caption, ...
    media_type = post[14] if len(post) > 14 else None
    media_file_id = post[15] if len(post) > 15 else None
    media_caption = post[17] if len(post) > 17 else None

    header = "⚠️ *Sensitive Confession*\n\n" if sensitive else "📝 *Confession*\n\n"
    caption_text = (
        f"{header}"
        f"*Category:* {escape_markdown_text(category)}\n\n"
    )
    
    # Add content or media caption
    if content:
        caption_text += f"{escape_markdown_text(content)}"
    elif media_caption:
        caption_text += f"{escape_markdown_text(media_caption)}"
    
    caption_text += f"\n\n💬 *Comments:* {comment_count}"

    keyboard = [
        [InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{post_id}")],
        [InlineKeyboardButton(f"👀 See Comments ({comment_count})", callback_data=f"see_comments_{post_id}_1")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # If it's a media post, send the media
    if media_type and media_file_id:
        try:
            if media_type == 'photo':
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_type == 'video':
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_type == 'animation':
                await context.bot.send_animation(
                    chat_id=update.effective_chat.id,
                    animation=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            else:
                # Fallback to text for unsupported media types
                logger.warning(f"Unsupported media type: {media_type}")
                await update.message.reply_text(caption_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
        except Exception as e:
            logger.error(f"Error sending sensitive media post {post_id}: {e}")
            # Fallback to text message if media fails
            caption_text += f"\n\n📷 *[Media content unavailable]*"
            await update.message.reply_text(caption_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    else:
        logger.info(f"Sending text post (no media)")
        await update.message.reply_text(caption_text, reply_markup=reply_markup, parse_mode="MarkdownV2")


async def show_post_with_options(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    """Show post with comment and view options (from recent posts list) - supports media"""
    query = update.callback_query
    if query:
        await query.answer()
    
    logger.info(f"Viewing post {post_id} with options")
    
    post = get_post_by_id(post_id)
    logger.info(f"Post retrieved: length={len(post) if post else 0}")
    
    if not post or post[5] != 1:  # Check if approved (approved field is at index 5, value 1 = approved)
        message_text = "❗ Post not found or not available."
        if query:
            await query.edit_message_text(message_text)
        else:
            await update.message.reply_text(message_text)
        return
    
    content = post[1]
    category = post[2]
    comment_count = await async_get_comment_count(post_id)
    
    # CORRECT field positions based on actual database schema:
    # [14]=media_type, [15]=media_file_id, [17]=media_caption
    media_type = post[14] if len(post) > 14 else None
    media_file_id = post[15] if len(post) > 15 else None
    media_caption = post[17] if len(post) > 17 else None
    
    logger.info(f"Viewing post {post_id} with options: media_type={media_type}, media_file_id={media_file_id}")
    
    context.user_data['viewing_post_id'] = post_id
    
    # Prepare caption text
    caption_text = f"""📝 *{escape_markdown_text(category)}*

"""
    
    # Add content or media caption
    if content:
        caption_text += f"{escape_markdown_text(content)}"
    elif media_caption:
        caption_text += f"{escape_markdown_text(media_caption)}"
    
    caption_text += f"""\n\n*Comments:* {comment_count}

Choose what you'd like to do:"""
    
    keyboard = [
        [InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{post_id}")],
        [InlineKeyboardButton(f"👀 See Comments ({comment_count})", callback_data=f"see_comments_{post_id}_1")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # If it's a media post, send the media
    if media_type and media_file_id:
        try:
            if media_type == 'photo':
                if query:
                    await query.delete_message()
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_type == 'video':
                if query:
                    await query.delete_message()
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            elif media_type == 'animation':
                if query:
                    await query.delete_message()
                await context.bot.send_animation(
                    chat_id=update.effective_chat.id,
                    animation=media_file_id,
                    caption=caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            else:
                # Fallback to text for unsupported media types
                logger.warning(f"Unsupported media type: {media_type}")
                if query:
                    await query.edit_message_text(
                        caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                else:
                    await update.message.reply_text(
                        caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
        except Exception as e:
            logger.error(f"Error sending media post {post_id}: {e}")
            # Fallback to text message if media fails
            caption_text += f"\n\n📷 *[Media content unavailable]*"
            if query:
                await query.edit_message_text(
                    caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            else:
                await update.message.reply_text(
                    caption_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
    else:
        logger.info(f"Sending text post (no media)")
        if query:
            await query.edit_message_text(
                caption_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        else:
            await update.message.reply_text(
                caption_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )

async def see_comments_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle see comments callback with performance optimizations"""
    query = update.callback_query
    await query.answer()
    
    try:
        # Parse callback data
        data_parts = query.data.split("_")
        post_id = int(data_parts[2])
        page = int(data_parts[3]) if len(data_parts) > 3 else 1
        
        # Store current page in user_data for pagination reference
        context.user_data['current_page'] = page

        logger.info(f"Getting paginated comments for post_id: {post_id}, page: {page}")
        comments_flat, current_page, total_pages, total_comments = get_comments_paginated(post_id, page)
        logger.info(
            f"Retrieved comments: data={len(comments_flat) if comments_flat else 0}, current_page={current_page}, total_pages={total_pages}, total_comments={total_comments}"
        )
    except Exception as e:
        logger.error(f"Error in see_comments_callback: {e}")
        await query.edit_message_text(
            "❗ Sorry, there was an issue loading comments. Please try again."
        )
        return

    # First, delete the previous message and send header
    try:
        await query.delete_message()
    except Exception:
        pass

    if not comments_flat:
        keyboard = [
            [InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{post_id}")],
            [InlineKeyboardButton("🔙 Back to Post", callback_data=f"view_post_{post_id}")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="💬 No comments yet. Be the first to comment!",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return

    user_id = update.effective_user.id

    # Send header message using unified formatting
    header_text = format_comments_header(total_comments, current_page, total_pages)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="HTML"
    )

    # OPTIMIZATION: Batch send comments to reduce network round trips
    comment_messages = []
    for comment_index, item in enumerate(comments_flat):
        # Use unified comment formatting function
        formatted_comment = format_comment_display(item, user_id, current_page, comment_index)
        comment_messages.append(formatted_comment)
    
    # Send all comments with small delays to avoid rate limiting
    for i, formatted_comment in enumerate(comment_messages):
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=formatted_comment['text'],
                reply_markup=formatted_comment['reply_markup'],
                parse_mode=formatted_comment['parse_mode'],
                disable_web_page_preview=True
            )
            # Small delay between messages to avoid rate limiting but keep it responsive
            if i < len(comment_messages) - 1:  # Don't delay after the last message
                await asyncio.sleep(0.05)  # 50ms delay
        except Exception as e:
            logger.error(f"Error sending comment {i}: {e}")
            # Continue with other comments even if one fails

    # Send navigation and action buttons at the end
    nav_keyboard = []

    # Navigation buttons
    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"see_comments_{post_id}_{current_page-1}"))
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"see_comments_{post_id}_{current_page+1}"))

    if nav_buttons:
        nav_keyboard.append(nav_buttons)

    # Action buttons
    nav_keyboard.append([
        InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{post_id}"),
        InlineKeyboardButton("🔙 Back to Post", callback_data=f"view_post_{post_id}")
    ])
    nav_keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu")])

    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)

    # Send navigation message
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="<b>📋 Navigation</b>",
        reply_markup=nav_reply_markup,
        parse_mode="HTML"
    )




async def add_comment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add comment callback"""
    query = update.callback_query
    await query.answer()
    
    post_id = int(query.data.split("_")[2])
    
    # Validate that the post exists and is approved before allowing comment entry
    from comments import get_post_with_channel_info
    post_info = get_post_with_channel_info(post_id)
    
    if not post_info:
        await query.edit_message_text(
            f"❗ *Post Not Found*\n\n"
            f"Post #{post_id} could not be found\\. It may have been deleted\\.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]]),
            parse_mode="MarkdownV2"
        )
        return
    
    if post_info[4] != 1:  # approved column
        await query.edit_message_text(
            f"❗ *Post Not Available*\n\n"
            f"Post #{post_id} is not approved for comments\\. "
            f"Only approved posts can receive comments\\.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]]),
            parse_mode="MarkdownV2"
        )
        return
    
    context.user_data['comment_post_id'] = post_id
    context.user_data['state'] = 'writing_comment'
    context.user_data.pop('reply_to_comment_id', None)  # Clear any reply state
    
    # Create cancel button for the comment writing interface
    cancel_keyboard = [[InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")]]
    cancel_reply_markup = InlineKeyboardMarkup(cancel_keyboard)
    
    await query.edit_message_text(
        f"💬 *Writing a comment*\n\n"
        f"Type your comment below \\(max {MAX_COMMENT_LENGTH} characters\\)\\.\n\n"
        f"Use the Cancel button below or type {CANCEL_BUTTON} to return to main menu\\.",
        reply_markup=cancel_reply_markup,
        parse_mode="MarkdownV2"
    )

async def handle_comment_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle comment text submission"""
    # Do not save button presses (menu, cancel, etc.) as comments
    if update.message.text and is_button_text(update.message.text):
        await show_menu(update, context, "🏠 Comment cancelled. Returned to main menu.")
        return
    
    content = sanitize_content(update.message.text)
    if not content:
        await update.message.reply_text(
            "❗ Your comment needs to be at least 5 meaningful characters long. "
            "Please write a proper comment and try again. "
            "All languages including Amharic are supported!"
        )
        return
    
    if len(content) > MAX_COMMENT_LENGTH:
        await update.message.reply_text(f"❗ Your comment is too long. Please keep it under {MAX_COMMENT_LENGTH} characters.")
        return
    
    post_id = context.user_data.get('comment_post_id')
    reply_to_comment_id = context.user_data.get('reply_to_comment_id')
    user_id = update.message.from_user.id
    
    # Import the new function that awards points
    from comments import save_comment_with_points
    comment_id, error = await save_comment_with_points(post_id, content, user_id, context, reply_to_comment_id)
    
    if error:
        await update.message.reply_text(f"❗ Error saving comment: {error}")
        return
    
    # Update the comment count on the channel message in the background
    try:
        from comments import update_channel_message_comment_count
        # Fire-and-forget so the user sees a response faster
        async def update_with_logging():
            try:
                success, result = await update_channel_message_comment_count(context, post_id)
                if not success:
                    logger.warning(f"Failed to update channel message comment count for post {post_id}: {result}")
                else:
                    logger.info(f"Successfully updated channel message comment count for post {post_id}: {result}")
            except Exception as e:
                logger.error(f"Error updating channel message comment count for post {post_id}: {e}", exc_info=True)
        
        asyncio.create_task(update_with_logging())
    except Exception as e:
        logger.error(f"Error scheduling channel message update for post {post_id}: {e}")
    
    # Send notifications in the background so they don't block the user response
    try:
        from notifications import notify_comment_on_post
        asyncio.create_task(notify_comment_on_post(context, post_id, content, user_id, comment_id))
    except Exception as e:
        logger.error(f"Error scheduling comment notification for post {post_id}: {e}")
    
    # Clear the writing_comment state to prevent further input being treated as comment
    context.user_data.pop('state', None)
    context.user_data.pop('comment_post_id', None)
    context.user_data.pop('reply_to_comment_id', None)
    
    # Set a special state that requires button selection
    context.user_data['state'] = 'awaiting_button_selection'
    context.user_data['awaiting_post_id'] = post_id
    
    # Message for normal comment vs. reply
    if reply_to_comment_id:
        await update.message.reply_text("✅ Your reply was posted successfully!")
    else:
        await update.message.reply_text("✅ Comment posted successfully!")
    
    # Show the post with options to add more comments or view comments
    await show_post_with_options(update, context, post_id)

# User Stats - FIXED IMPLEMENTATION
async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive user statistics"""
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    if not stats:
        await update.message.reply_text("❗ No statistics available. Submit your first confession!")
        await show_menu(update, context)
        return
    
    join_date = format_join_date(stats['join_date'])
    
    stats_text = f"""
📊 *Your Statistics*

*User Info:*
• User ID: `{stats['user_id']}`
• Joined: {escape_markdown_text(join_date)}
• Status: {'🚫 Blocked' if stats['blocked'] else '✅ Active'}

*Confession Stats:*
• Total Submitted: {stats['total_confessions']}
• Approved: {stats['approved_confessions']}
• Pending: {stats['pending_confessions']}
• Rejected: {stats['rejected_confessions']}

*Comment Stats:*
• Comments Posted: {stats['comments_posted']}
• Likes Received: {stats['likes_received']}
"""
    
    keyboard = [
        [InlineKeyboardButton("📝 View My Confessions", callback_data="view_my_confessions")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def view_my_confessions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's confession history one by one with See Comments buttons"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    from db import get_user_posts as get_user_posts_with_media
    posts = get_user_posts_with_media(user_id, 10)
    
    logger.info(f"View My Confessions: retrieved {len(posts)} posts for user {user_id}")
    if posts:
        sample_post = posts[0]
        logger.info(f"Sample post fields: len={len(sample_post)}, media_type={sample_post[7] if len(sample_post) > 7 else 'N/A'}, media_file_id={sample_post[8] if len(sample_post) > 8 else 'N/A'}")
    
    if not posts:
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Stats", callback_data="back_to_stats")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📝 You haven't submitted any confessions yet\\!\n\n"
            "Use '🙊 Confess/Ask Question' to submit your first confession\\.",
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the original stats message
    try:
        await query.delete_message()
    except:
        pass
    
    # Send header message
    header_text = f"📝 *Your Recent Confessions \\({len(posts)} total\\)*"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    
    # Send each confession as a separate message
    for post in posts:
        post_id = post[0]
        content = post[1]
        category = post[2]
        timestamp = post[3]
        approved = post[4]
        comment_count = post[5]
        post_number = post[6] if len(post) > 6 and post[6] is not None else post_id  # Use post_number if available, fallback to post_id
        media_type = post[7] if len(post) > 7 else None
        media_file_id = post[8] if len(post) > 8 else None
        media_caption = post[10] if len(post) > 10 else None
        
        status_emoji = "✅" if approved == 1 else "⏳" if approved is None else "❌"
        status_text = "Approved" if approved == 1 else "Pending" if approved is None else "Rejected"
        
        # Format timestamp without double escaping
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_timestamp = dt.strftime('%Y-%m-%d %H:%M')
            escaped_timestamp = escape_markdown_text(formatted_timestamp)
        except:
            escaped_timestamp = escape_markdown_text(str(timestamp))
        
        # Create buttons based on approval status
        keyboard = []
        if approved == 1:  # Only approved posts can have comments viewed
            keyboard.append([
                InlineKeyboardButton(f"👀 See Comments ({comment_count})", callback_data=f"see_comments_{post_id}_1")
            ])
        
        # Always show view post button for approved posts
        if approved == 1:
            keyboard.append([
                InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}")
            ])
        
        # Add edit button for user's own posts (only pending or approved)
        if approved == 1 or approved is None:  # Approved or pending
            keyboard.append([
                InlineKeyboardButton("✏️ Edit", callback_data=f"edit_my_post_{post_id}")
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        # Check if this is a media post and send accordingly
        if media_type and media_file_id:
            # This is a media post - first try to send as media
            caption_text = f"*{escape_markdown_text(category)}*\n\n"

            # Add text content if available
            if content and content.strip():
                caption_text += f"{escape_markdown_text(content)}\n\n"
            elif media_caption and media_caption.strip():
                caption_text += f"{escape_markdown_text(media_caption)}\n\n"

            # Add status and stats
            caption_text += f"*\\#{post_number}* {status_emoji} {escape_markdown_text(status_text)} \\| "
            caption_text += f"💬 {comment_count} comments \\| {escaped_timestamp}"

            # Try to send media message based on type
            media_sent_successfully = False
            try:
                if media_type == 'photo':
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=media_file_id,
                        caption=caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                    media_sent_successfully = True
                elif media_type == 'video':
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=media_file_id,
                        caption=caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                    media_sent_successfully = True
                elif media_type == 'animation':
                    await context.bot.send_animation(
                        chat_id=update.effective_chat.id,
                        animation=media_file_id,
                        caption=caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                    media_sent_successfully = True
                elif media_type == 'document':
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=media_file_id,
                        caption=caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                    media_sent_successfully = True
                else:
                    # Unsupported media type - send as text with media indicator
                    logger.warning(f"Unsupported media type '{media_type}' for post {post_id}, sending as text")
                    media_sent_successfully = False
                    
            except Exception as e:
                logger.error(f"Error sending media confession {post_id} in My Stats (media type: {media_type}): {e}")
                media_sent_successfully = False
            
            # If media sending failed, send as text message with media indicator
            if not media_sent_successfully:
                # Determine media emoji based on type
                media_emoji = {
                    'photo': '📷',
                    'video': '🎥', 
                    'animation': '🎭',
                    'document': '📄'
                }.get(media_type, '📎')
                
                fallback_text = f"*{escape_markdown_text(category)}*\n\n"
                
                # Add original content if available, otherwise indicate media type
                if content and content.strip() and content not in ['[Photo]', '[Video]', '[GIF]', '[Document]']:
                    fallback_text += f"{escape_markdown_text(content)}\n\n"
                else:
                    fallback_text += f"{media_emoji} *[{media_type.title()} content]*\n\n"
                
                # Add status and stats
                fallback_text += f"*\\#{post_number}* {status_emoji} {escape_markdown_text(status_text)} \\| "
                fallback_text += f"💬 {comment_count} comments \\| {escaped_timestamp}\n\n"
                fallback_text += f"ℹ️ *Note: Media may no longer be available*"

                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=fallback_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                    logger.info(f"Sent fallback text message for media post {post_id}")
                except Exception as fallback_error:
                    logger.error(f"Failed to send fallback message for post {post_id}: {fallback_error}")
                    # Last resort - send very simple message
                    try:
                        simple_text = f"Post #{post_number} ({category}) - {media_emoji} Media content unavailable"
                        await context.bot.send_message(
                            chat_id=update.effective_chat.id,
                            text=simple_text,
                            reply_markup=reply_markup
                        )
                    except Exception as final_error:
                        logger.error(f"Complete failure sending post {post_id}: {final_error}")
        else:
            # This is a text-only post - send as text message
            confession_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(content)}\n\n"
            confession_text += f"*\\#{post_number}* {status_emoji} {escape_markdown_text(status_text)} \\| "
            confession_text += f"💬 {comment_count} comments \\| {escaped_timestamp}"
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=confession_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        
        # Small delay between confessions (reduced for responsiveness)
        await asyncio.sleep(0.1)
    
    # Send navigation message at the end
    nav_keyboard = [
        [InlineKeyboardButton("🔙 Back to Stats", callback_data="back_to_stats")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )

async def back_to_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to stats from confession history"""
    query = update.callback_query
    await query.answer()
    
    # Simulate calling my_stats but through callback
    user_id = update.effective_user.id
    stats = get_user_stats(user_id)
    
    if not stats:
        await query.edit_message_text("❗ No statistics available.")
        return
    
    join_date = format_join_date(stats['join_date'])
    
    stats_text = f"""
📊 *Your Statistics*

*User Info:*
• User ID: `{stats['user_id']}`
• Joined: {escape_markdown_text(join_date)}
• Status: {'🚫 Blocked' if stats['blocked'] else '✅ Active'}

*Confession Stats:*
• Total Submitted: {stats['total_confessions']}
• Approved: {stats['approved_confessions']}
• Pending: {stats['pending_confessions']}
• Rejected: {stats['rejected_confessions']}

*Comment Stats:*
• Comments Posted: {stats['comments_posted']}
• Likes Received: {stats['likes_received']}
"""
    
    keyboard = [
        [InlineKeyboardButton("📝 View My Confessions", callback_data="view_my_confessions")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        stats_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def edit_my_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle edit button click for user's own post"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    post_id = int(query.data.split('_')[-1])
    
    # Verify ownership
    from db import get_user_posts
    posts = get_user_posts(user_id, 100)  # Get all user posts
    
    post_found = None
    for post in posts:
        if post[0] == post_id:  # post_id matches
            post_found = post
            break
    
    if not post_found:
        await query.edit_message_text("❗ Post not found or you don't have permission to edit it.")
        return
    
    # Check if post is approved or pending (can edit both)
    approved = post_found[4]  # approved field
    if approved == -1:  # Rejected posts can also be edited
        pass  # Allow editing rejected posts too
    
    content = post_found[1]
    category = post_found[2]
    
    # Show edit dialog - escape ALL text for MarkdownV2
    logger.info(f"Edit dialog - Category: {category}, Content length: {len(content) if content else 0}")
    
    # Test escape function directly
    from text_utils import escape_markdown_text as esc
    test_escape = esc("Test with dots. And more.")
    logger.info(f"TEST ESCAPE: '{test_escape}'")
    
    escaped_category = esc(str(category))
    escaped_content = esc(str(content) if content else 'No content')
    
    logger.info(f"Escaped category: {escaped_category}")
    logger.info(f"Escaped content first 100 chars: {escaped_content[:100]}")
    logger.info(f"Content has dots before escape: {'.' in str(content)}")
    has_escaped_dot = "\\." in escaped_content
    logger.info(f"Escaped content has backslash-dot: {has_escaped_dot}")
    
    edit_text = (
        f"✏️ *Edit Your Confession*\n\n"
        f"*Category:* {escaped_category}\n"
        f"*Content:*\n{escaped_content}\n\n"
        f"_Send your new content to update this confession:_"
    )
    
    keyboard = [
        [InlineKeyboardButton("❌ Cancel", callback_data="view_my_confessions")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    logger.info(f"Full edit text length: {len(edit_text)}")
    # Check if there are any unescaped dots in the final text
    import re
    # Find dots that are NOT preceded by backslash
    unescaped_dots = re.findall(r'(?<!\\)\.', edit_text)
    if unescaped_dots:
        logger.error(f"FOUND {len(unescaped_dots)} UNESCAPED DOTS in edit_text!")
        logger.error(f"Full edit text: {edit_text}")
        # Show where the dots are
        for i, char in enumerate(edit_text):
            if char == '.' and (i == 0 or edit_text[i-1] != '\\'):
                logger.error(f"Unescaped dot at position {i}: context='{edit_text[max(0,i-10):i+10]}'")
    else:
        logger.info(f"All dots properly escaped")
    
    try:
        await query.edit_message_text(
            edit_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Failed to send edit dialog: {e}")
        logger.error(f"Problematic text: {edit_text}")
        # If message cannot be edited (same content or other reason), just answer the callback
        if "not modified" in str(e).lower():
            await query.answer("⚠️ This post cannot be edited", show_alert=True)
        else:
            raise
    
    context.user_data['editing_post_id'] = post_id
    context.user_data['edit_state'] = 'waiting_for_new_content'

async def handle_post_edit_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new content submission for post edit"""
    user_id = update.effective_user.id
    new_content = update.message.text
    
    # Check if user is in edit mode
    if context.user_data.get('edit_state') != 'waiting_for_new_content':
        return
    
    post_id = context.user_data.get('editing_post_id')
    if not post_id:
        await update.message.reply_text("❗ Error: No post being edited.")
        context.user_data.pop('edit_state', None)
        return
    
    # Get the original post info before updating
    from submission import get_post_by_id as get_post_from_db
    original_post = get_post_from_db(post_id)
    original_category = original_post[2] if original_post else "Unknown"
    was_approved = original_post[5] if original_post else None
    
    # Update the post
    from db import update_user_post
    success = update_user_post(post_id, user_id, new_content)
    
    if success:
        # Notify admins about the edit (only if it was previously approved)
        if was_approved == 1:
            try:
                from admin_messaging import notify_admins_of_edited_confession
                await notify_admins_of_edited_confession(
                    context, post_id, user_id, new_content, original_category
                )
                logger.info(f"Admins notified about edited confession {post_id}")
            except Exception as e:
                logger.error(f"Failed to notify admins about edited confession {post_id}: {e}")
        
        await update.message.reply_text(
            "✅ *Post Updated Successfully*\n\n"
            "Your confession has been updated and sent for review\.\n"
            "Admins will be notified of your changes\.",
            parse_mode="MarkdownV2"
        )
    else:
        await update.message.reply_text(
            "❗ *Failed to Update Post*\n\n"
            "Unable to update the post. Please try again.",
            parse_mode="MarkdownV2"
        )
    
    # Clear edit state
    context.user_data.pop('edit_state', None)
    context.user_data.pop('editing_post_id', None)

# Contact Admin - FIXED IMPLEMENTATION
async def start_contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start contact admin flow"""
    # Create inline keyboard with cancel button
    keyboard = [
        [InlineKeyboardButton("🚫 Cancel", callback_data="cancel_contact_admin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📞 *Contact Admin*\n\n"
        "Please write your message to the administrators\\. "
        "This could be feedback, suggestions, ideas, or any other message\\.\n\n"
        "Your message will be sent anonymously and admins can reply to you\\.\n\n"
        f"Type your message or use {CANCEL_BUTTON} to return to menu:",
        parse_mode="MarkdownV2",
        reply_markup=reply_markup
    )
    context.user_data['state'] = 'contacting_admin'

async def handle_admin_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin contact message"""
    # Do not record button presses as admin messages
    if update.message.text and is_button_text(update.message.text):
        await show_menu(update, context, "🏠 Contact cancelled. Returned to main menu.")
        return
    
    user_id = update.message.from_user.id
    message = update.message.text
    
    # Save message and send to admins
    success, result = await send_message_to_admins(context, user_id, message)
    
    if success:
        await update.message.reply_text(
            "✅ *Message Sent\\!*\n\n"
            "Your message has been sent to the administrators\\. "
            "They may reply to you anonymously\\.",
            parse_mode="MarkdownV2"
        )
    else:
        await update.message.reply_text(
            f"❌ *Failed to send message:* {result}\n\n"
            "Please try again later or contact the administrators directly\\.",
            parse_mode="MarkdownV2"
        )
    
    await show_menu(update, context)

async def handle_admin_reply_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin typed reply message with duplicate prevention"""
    # Ignore button texts so they are not stored as replies
    if update.message.text and is_button_text(update.message.text):
        await update.message.reply_text("❗ Button text cannot be used as a reply. Please type your reply message.")
        return
    
    user_id = update.message.from_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin features.")
        context.user_data.pop('state', None)
        return
    
    # Check if this is a quick reply (admin_replying state) or regular reply mode
    state = context.user_data.get('state')
    if state == 'admin_replying':
        # This is a quick reply from the admin panel
        # Continue with the reply process
        pass
    else:
        # Check if user has clicked the Reply button (reply mode is active) OR if this is the first message
        if not context.user_data.get('reply_mode_active') and not context.user_data.get('first_message_allowed'):
            await update.message.reply_text(
                "Please use the buttons below to save or edit your profile\\."
            )
            await update.message.reply_text(
                "❗ To send a message, please click the ↩️ Reply button on the message you want to respond to\\."
            )
            return
    
    # Get the message ID we're replying to
    message_id = context.user_data.get('replying_to_message_id')
    if not message_id:
        await update.message.reply_text("❗ Error: No message to reply to found.")
        context.user_data.pop('state', None)
        return
    
    reply_text = update.message.text
    
    try:
        success, result = await send_admin_reply_to_user(context, message_id, user_id, reply_text)
        
        if success:
            await update.message.reply_text(
                "✅ *Reply sent successfully\\!*\n\n"
                f"Your reply has been sent anonymously to the user\\.",
                parse_mode="MarkdownV2"
            )
        else:
            # Check if it was a duplicate issue or other error
            if "already been replied to" in result:
                await update.message.reply_text(
                    f"⚠️ *Duplicate Reply Prevented*\n\n"
                    f"{escape_markdown_text(result)}\n\n"
                    f"Only one admin can reply to each message\\.",
                    parse_mode="MarkdownV2"
                )
            else:
                await update.message.reply_text(
                    f"❗ *Failed to send reply:* {escape_markdown_text(result)}\n\n"
                    "Please try again or use the /reply command\\.",
                    parse_mode="MarkdownV2"
                )
    
    except Exception as e:
        await update.message.reply_text(f"❗ Error sending reply: {str(e)}")
    
    # Clear the admin reply state
    context.user_data.pop('state', None)
    context.user_data.pop('replying_to_message_id', None)

# Daily Digest
async def daily_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's confessions individually with media support"""
    from submission import get_todays_posts_with_media
    posts = get_todays_posts_with_media()
    
    if not posts:
        await update.message.reply_text("📅 No confessions posted today yet\\. Check back later\\!", parse_mode="MarkdownV2")
        await show_menu(update, context)
        return
    
    # Send header message
    header_text = f"📅 *Today's Confessions \\({len(posts)} total\\)*"
    await update.message.reply_text(
        header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from datetime import datetime
    
    # Send each confession as a separate message
    for post in posts:
        post_id = post[0]
        content = post[1]
        category = post[2]
        timestamp = post[3]
        comment_count = post[20]  # Updated index for comment_count in media-aware query
        post_number = post[9] if len(post) > 9 and post[9] is not None else post_id  # post_number is at index 9
        media_type = post[10] if len(post) > 10 else None  # media_type is at index 10
        media_file_id = post[11] if len(post) > 11 else None  # media_file_id is at index 11
        media_caption = post[13] if len(post) > 13 else None  # media_caption is at index 13
        
        # Format timestamp
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_timestamp = dt.strftime('%H:%M')
            escaped_timestamp = escape_markdown_text(formatted_timestamp)
        except:
            escaped_timestamp = escape_markdown_text(str(timestamp))
        
        # Create buttons for each confession
        keyboard = [
            [
                InlineKeyboardButton(f"👀 See Comments ({comment_count})", callback_data=f"see_comments_{post_id}_1"),
                InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Check if this is a media post
        if media_type and media_file_id:
            # For media posts, prepare caption with timestamp and comments info
            caption_text = f"*{escape_markdown_text(category)}*\n\n"
            
            # Add text content if available
            if content and content.strip():
                caption_text += f"{escape_markdown_text(content)}\n\n"
            elif media_caption and media_caption.strip():
                caption_text += f"{escape_markdown_text(media_caption)}\n\n"
            
            # Add post info
            caption_text += f"*\\#{post_number}* \\| 💬 {comment_count} comments \\| {escaped_timestamp}"
            
            # Send media message based on type
            try:
                if media_type == 'photo':
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=media_file_id,
                        caption=caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif media_type == 'video':
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=media_file_id,
                        caption=caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif media_type == 'animation':
                    await context.bot.send_animation(
                        chat_id=update.effective_chat.id,
                        animation=media_file_id,
                        caption=caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                else:
                    # Fallback to text message for unsupported media types
                    fallback_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(content or '[Media content]')}\n\n"
                    fallback_text += f"*\\#{post_number}* \\| 💬 {comment_count} comments \\| {escaped_timestamp}\n\n"
                    fallback_text += f"📷 *[{media_type.title()} content]*"
                    
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=fallback_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
            except Exception as e:
                logger.error(f"Error sending media post {post_id} in daily digest: {e}")
                # Fallback to text message if media sending fails
                fallback_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(content or '[Media content unavailable]')}\n\n"
                fallback_text += f"*\\#{post_number}* \\| 💬 {comment_count} comments \\| {escaped_timestamp}\n\n"
                fallback_text += f"📷 *[Media content unavailable]*"
                
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=fallback_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
        else:
            # Text-only post - use the original format
            confession_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(content)}\n\n"
            confession_text += f"*\\#{post_number}* \\| 💬 {comment_count} comments \\| {escaped_timestamp}"
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=confession_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        
        # Small delay between confessions (reduced for responsiveness)
        await asyncio.sleep(0.1)
    
    # Send navigation message at the end
    nav_keyboard = [
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)

    # Use the current chat as the target instead of an undefined chat_id
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )


async def handle_profile_contact_request(update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
    """Start or reuse a profile contact request from the current user to target_user_id."""
    query = update.callback_query
    user = update.effective_user
    if not user:
        logger.info("No effective user found")
        return
    user_id = user.id
    
    # Add debug logging
    logger.info(f"Handling profile contact request: user_id={user_id}, target_user_id={target_user_id}")

    if user_id == target_user_id:
        logger.info("User tried to contact themselves")
        await query.answer("You can't contact yourself\\.")
        return

    is_blocked, requester_profile, target_profile, contact = await asyncio.gather(
        AsyncDBWrapper.run_sync(is_profile_blocked_either_way, user_id, target_user_id),
        AsyncDBWrapper.run_sync(get_user_profile, user_id),
        AsyncDBWrapper.run_sync(get_user_profile, target_user_id),
        AsyncDBWrapper.run_sync(get_profile_contact, user_id, target_user_id),
        return_exceptions=True,
    )

    for label, value in (
        ("blocks", is_blocked), ("requester profile", requester_profile),
        ("target profile", target_profile), ("existing contact", contact),
    ):
        if isinstance(value, Exception):
            logger.error(f"Error fetching {label} for contact request {user_id}->{target_user_id}: {value}")

    # Respect blocks in either direction
    if is_blocked is True:
        logger.info(f"User {user_id} is blocked from contacting {target_user_id}")
        await query.answer("You cannot contact this user\\.")
        return

    if isinstance(requester_profile, Exception):
        requester_profile = None
    if isinstance(target_profile, Exception):
        target_profile = None
    if isinstance(contact, Exception):
        contact = None
    
    logger.info(f"Requester profile: {requester_profile}")
    logger.info(f"Target profile: {target_profile}")

    if not target_profile or not target_profile.get('is_active'):
        logger.info(f"Target profile not available or not active for user {target_user_id}")
        await query.edit_message_text(
            "👤 *Profile not available*\\!\n\nThis user is not currently accepting contacts\\.",
            parse_mode="MarkdownV2",
        )
        return
    
    # Check if target user is accepting contact requests
    if not target_profile.get('accepting_contacts', True):
        logger.info(f"Target user {target_user_id} is not accepting contact requests")
        await query.edit_message_text(
            "🚫 *Contact requests disabled*\n\nThis user is not currently accepting new contact requests\\.",
            parse_mode="MarkdownV2",
        )
        return

    if not requester_profile or not requester_profile.get('is_active'):
        logger.info(f"Requester profile not available or not active for user {user_id}")
        await query.edit_message_text(
            "👤 *Profile required*\n\nCreate and enable your profile first using '👤 My Profile' in the main menu\\.",
            parse_mode="MarkdownV2",
        )
        return

    if contact:
        status = contact.get('status')
        if status == 'pending':
            if contact.get('initiator_id') == user_id:
                logger.info(f"Contact request already pending from user {user_id}")
                await query.answer("Your request is already pending\\.")
            else:
                logger.info(f"Contact request already pending from user {target_user_id}")
                await query.answer("This user already requested to chat with you\\.")

            return
        if status == 'active':
            logger.info(f"Active chat already exists between {user_id} and {target_user_id}")
            # Reuse existing active chat
            context.user_data['state'] = 'profile_chat'
            context.user_data['profile_chat_partner'] = target_user_id
            context.user_data['profile_contact_id'] = contact['id']
            await query.edit_message_text(
                "✅ *Chat already active*\\!\n\nSend messages here and I'll relay them\\.",
                parse_mode="MarkdownV2",
            )
            return

    # Create new pending contact
    contact_id = await AsyncDBWrapper.run_sync(
        create_profile_contact, user_id, target_user_id, user_id, 'pending'
    )
    
    logger.info(f"Created new contact request: contact_id={contact_id}")

    name_raw = (requester_profile.get('emoji') or '') + ' ' + (requester_profile.get('display_name') or '')
    name_line = escape_markdown_text(name_raw.strip() if name_raw.strip() else "Anonymous")
    bio = requester_profile.get('bio') or ''
    bio_display = escape_markdown_text(bio) if bio else escape_markdown_text("No bio set yet\\.")

    request_text = (
        "💬 *New chat request*\n\n"
        f"From: {name_line}\n"
        f"Bio: {bio_display}\n\n"
        "🤔 *Choose an option below*\."
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"profile_accept_{contact_id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"profile_decline_{contact_id}"),
        ],
        [
            InlineKeyboardButton("🚫 Block", callback_data=f"profile_block_contact_{contact_id}"),
        ],
        [
            InlineKeyboardButton("👤 Show Profile", callback_data=f"profile_show_requester_{user_id}_from_{contact_id}"),
        ],
    ]

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=request_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="MarkdownV2",
        )
        logger.info(f"Sent contact request message to user {target_user_id}")
    except Exception as e:
        logger.error(f"Error sending profile contact request {contact_id} to {target_user_id}: {e}")
        await query.edit_message_text(
            "❗ Failed to send contact request\\. Please try again later\\.",
            parse_mode="MarkdownV2",
        )
        return

    await query.edit_message_text(
        "📩 *Chat request sent*\n\n"
        "I'll notify you when they reply\.\n\n"
        "🔄 *Next*\:\n"
        "• Wait for a reply\n"
        "• Check your inbox\n"
        "• Use the menu below",
        parse_mode="MarkdownV2",
    )
    logger.info(f"Successfully processed contact request from {user_id} to {target_user_id}")


async def handle_profile_contact_decision(update: Update, context: ContextTypes.DEFAULT_TYPE, contact_id: int, action: str):
    """Handle accept/decline/block decisions for a profile contact request."""
    query = update.callback_query
    user = update.effective_user
    if not user:
        return
    user_id = user.id

    contact = await AsyncDBWrapper.run_sync(get_profile_contact_by_id, contact_id)
    if not contact:
        await query.edit_message_text(
            "❗ This chat request is no longer available\\\\.",
            parse_mode="MarkdownV2",
        )
        return

    if user_id not in (contact['user_a_id'], contact['user_b_id']):
        await query.answer("This request is not for you\\\\.")
        return

    partner_id = contact['user_a_id'] if contact['user_a_id'] != user_id else contact['user_b_id']

    if action == 'decline':
        await AsyncDBWrapper.run_sync(update_profile_contact_status, contact_id, 'ended')
        await query.edit_message_text(
            "❌ You declined this chat request\\.",
            parse_mode="MarkdownV2",
        )
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text="❌ *Your chat request was declined\\.*",
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.error(f"Error notifying initiator about declined contact {contact_id}: {e}")
        return

    if action == 'block':
        await AsyncDBWrapper.run_sync(block_profile_user, user_id, partner_id)
        await AsyncDBWrapper.run_sync(update_profile_contact_status, contact_id, 'ended')
        await query.edit_message_text(
            "🚫 You blocked this user\\. They won't be able to contact you through profiles\\.",
            parse_mode="MarkdownV2",
        )
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text="🚫 *This user is not available for chat\\.*",
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.error(f"Error notifying blocked user for contact {contact_id}: {e}")
        return

    if action == 'accept':
        await AsyncDBWrapper.run_sync(update_profile_contact_status, contact_id, 'active')
        # Store mapping in bot_data for quick lookup
        sessions = context.bot_data.setdefault('profile_sessions', {})
        a_id, b_id = contact['user_a_id'], contact['user_b_id']
        key = (min(a_id, b_id), max(a_id, b_id))
        sessions[key] = contact_id

        # Put current user into chat state
        context.user_data['state'] = 'profile_chat'
        context.user_data['profile_chat_partner'] = partner_id
        context.user_data['profile_contact_id'] = contact_id
        # Set reply mode to True so the first message can be sent
        context.user_data['reply_mode_active'] = True

        try:
            partner_profile, viewer_profile = await asyncio.gather(
                AsyncDBWrapper.run_sync(get_user_profile, partner_id),
                AsyncDBWrapper.run_sync(get_user_profile, user_id),
            )

            def _display(p):
                if not p:
                    return escape_markdown_text("Anonymous")
                name_raw = (p.get('emoji') or '') + ' ' + (p.get('display_name') or '')
                return escape_markdown_text(name_raw.strip() if name_raw.strip() else "Anonymous")

            other_name_for_current = _display(partner_profile)
            other_name_for_partner = _display(viewer_profile)

            await query.edit_message_text(
                f"✅ *Chat started*\n\n"
                f"You're now chatting with {other_name_for_current}\.",
                parse_mode="MarkdownV2",
            )
            # Simple instructions for the user
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "💬 *How this chat works*\n\n"
                    "• Type your message and press Send\n"
                    "• I'll deliver it to the other user\n"
                    "• Use the buttons below to end or block"
                ),
                parse_mode="MarkdownV2",
            )
            await context.bot.send_message(
                chat_id=partner_id,
                text=(
                    f"✅ *Chat started*\n\n"
                    f"You're now chatting with {other_name_for_partner}\."
                ),
                parse_mode="MarkdownV2",
            )
            # Simple instructions for the partner
            await context.bot.send_message(
                chat_id=partner_id,
                text=(
                    "💬 *How this chat works*\n\n"
                    "• Type your message and press Send\n"
                    "• I'll deliver it to the other user\n"
                    "• Use the buttons below to end or block"
                ),
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.error(f"Error sending chat start notifications for contact {contact_id}: {e}")
        return


async def handle_profile_chat_control(update: Update, context: ContextTypes.DEFAULT_TYPE, contact_id: int, action: str):
    """Handle in-chat controls: end chat or block from chat UI."""
    query = update.callback_query
    user = update.effective_user
    if not user:
        return
    user_id = user.id

    contact = await AsyncDBWrapper.run_sync(get_profile_contact_by_id, contact_id)
    if not contact:
        await query.edit_message_text(
            "❗ This chat is no longer available\\\\.",
            parse_mode="MarkdownV2",
        )
        return

    if user_id not in (contact['user_a_id'], contact['user_b_id']):
        await query.answer("This chat control is not for you\\\\.")
        return


    partner_id = contact['user_a_id'] if contact['user_a_id'] != user_id else contact['user_b_id']

    if action == 'end':
        await AsyncDBWrapper.run_sync(update_profile_contact_status, contact_id, 'ended')
        # Clear local chat state
        context.user_data.pop('state', None)
        context.user_data.pop('profile_chat_partner', None)
        context.user_data.pop('profile_contact_id', None)
        await query.edit_message_text(
            "🔚 Chat ended\\\\.",
            parse_mode="MarkdownV2",
        )
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text="🔚 *Chat ended by the other user\\\\.*",
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.error(f"Error notifying partner about ended chat {contact_id}: {e}")
        return

    if action == 'block':
        await AsyncDBWrapper.run_sync(block_profile_user, user_id, partner_id)
        await AsyncDBWrapper.run_sync(update_profile_contact_status, contact_id, 'ended')
        context.user_data.pop('state', None)
        context.user_data.pop('profile_chat_partner', None)
        context.user_data.pop('profile_contact_id', None)
        await query.edit_message_text(
            "🚫 You blocked this user and ended the chat\\.",
            parse_mode="MarkdownV2",
        )
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text="🚫 *This user is not available for chat\\\\.*",
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.error(f"Error notifying blocked user for contact {contact_id}: {e}")
        return


# Callback Handlers
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all callback queries"""
    query = update.callback_query
    await query.answer()
    
    if not query.data:
        return
    
    data = query.data
    user_id = update.effective_user.id
    
    # Enhanced logging for debugging deletion button issues
    logger.info(f"Callback received: user={user_id}, data='{data}'")
    
    # Special logging for deletion-related callbacks
    if "delete_post_" in data or "confirm_delete_post_" in data:
        logger.info(f"DELETION CALLBACK: User {user_id} triggered '{data}' - Admin check: {user_id in ADMIN_IDS}")
    
    # Profile unblock must be checked BEFORE admin callbacks (to avoid conflict with admin unblock_)
    if data.startswith("unblock_user_"):
        from db import unblock_profile_user
        blocked_id = int(data.replace("unblock_user_", ""))
        unblock_profile_user(user_id, blocked_id)
        await query.edit_message_text(
            "✅ *User Unblocked*\n\n"
            "This user has been unblocked and can now contact you again\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Blocked List", callback_data="profile_blocked_users")
            ]])
        )
        return
    
    # Admin callbacks (including sensitive/18+ approval variants and full rejection flows)
    if data.startswith((
        "approve18_",
        "approve_sensitive_",
        "approve_",
        "reject_",
        "reject_reason_",
        "reject_custom_",
        "reject_cancel_",
        "flag_",
        "block_",
        "unblock_",
    )):
        await admin_callback(update, context)
        return
    
    # Content type selection
    if data.startswith("content_type_"):
        await content_type_callback(update, context)
        return
    
    # Category selection
    if data.startswith("category_") or data == "categories_done":
        await category_callback(update, context)
        return
    
    # Cancel to menu
    if data == "cancel_to_menu" or data == "menu":
        # Clear all user context including awaiting button selection state
        await clear_user_context(context)
        context.user_data.pop('awaiting_post_id', None)
        await query.edit_message_text("🏠 Returned to main menu\\. Please use the menu below\\.", parse_mode="MarkdownV2")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="What would you like to do next?",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        )
        return
    
    # Profile system callbacks (check BEFORE admin callbacks to avoid conflicts)
    logger.info(f"Checking profile system callbacks for data: {data}")
    if data.startswith("profile_") or data.startswith("edit_") or data.startswith("emoji_") or data.startswith("gender_") or data.startswith("year_") or data.startswith("relationship_") or data.startswith("resume_chat_") or data.startswith("view_request_") or data.startswith("view_friend_") or data.startswith("view_full_profile_") or data.startswith("remove_friend_") or data.startswith("view_blocked_") or data.startswith("unblock_user_") or data == "back_to_profile":
        logger.info(f"Data matched profile system callbacks: {data}")
        # Contact request from a public profile card
        if data.startswith("profile_contact_"):
            logger.info(f"Processing profile_contact_ callback: {data}")
            try:
                target_user_id = int(data.replace("profile_contact_", ""))
                logger.info(f"Extracted target_user_id: {target_user_id}")
                
                # Add more debug info
                logger.info(f"user_id: {user_id}")
                logger.info(f"target_user_id type: {type(target_user_id)}")
                logger.info(f"user_id == target_user_id: {user_id == target_user_id}")
                
            except ValueError as e:
                logger.error(f"Invalid profile contact data: {data}, error: {e}")
                await query.answer("Invalid profile contact data")
                return
            await handle_profile_contact_request(update, context, target_user_id)
            return

        # Decisions on a pending contact request (accept / decline / block)
        if data.startswith("profile_accept_"):
            contact_id = int(data.replace("profile_accept_", ""))
            await handle_profile_contact_decision(update, context, contact_id, "accept")
            return
        if data.startswith("profile_decline_"):
            contact_id = int(data.replace("profile_decline_", ""))
            await handle_profile_contact_decision(update, context, contact_id, "decline")
            return
        if data.startswith("profile_block_contact_"):
            contact_id = int(data.replace("profile_block_contact_", ""))
            await handle_profile_contact_decision(update, context, contact_id, "block")
            return

        # In-chat controls (end / block within an active chat)
        if data.startswith("profile_end_"):
            contact_id = int(data.replace("profile_end_", ""))
            await handle_profile_chat_control(update, context, contact_id, "end")
            return
        if data.startswith("profile_block_chat_"):
            contact_id = int(data.replace("profile_block_chat_", ""))
            await handle_profile_chat_control(update, context, contact_id, "block")
            return
        # Reply button handler
        if data.startswith("profile_reply_"):
            contact_id = int(data.replace("profile_reply_", ""))
            # Set up chat session for replying
            contact = get_profile_contact_by_id(contact_id)
            if contact and contact.get('status') == 'active':
                user_id = update.effective_user.id
                partner_id = contact['user_a_id'] if contact['user_a_id'] != user_id else contact['user_b_id']
                
                # Set up chat session
                context.user_data['state'] = 'profile_chat'
                context.user_data['profile_chat_partner'] = partner_id
                context.user_data['profile_contact_id'] = contact_id
                context.user_data['reply_mode_active'] = True
                
                await query.answer("You can now reply to this message")
                await query.edit_message_text(
                    "↩️ *Reply Mode Activated*\n\n"
                    "Send your reply message below\\.\n\n"
                    "Use the chat controls when you're done\\.",
                    parse_mode="MarkdownV2",
                )
            else:
                await query.answer("This chat is no longer available")
            return

        # One-click block from a profile card (without a chat contact yet)
        if data.startswith("profile_block_"):
            try:
                target_user_id = int(data.replace("profile_block_", ""))
            except ValueError:
                await query.answer("Invalid block data")
                return
            block_profile_user(user_id, target_user_id)
            await query.edit_message_text(
                "🚫 You blocked this user\\. They won't be able to contact you through profiles\\.",
                parse_mode="MarkdownV2",
            )
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="🚫 *This user is not available for chat\\.*",
                    parse_mode="MarkdownV2",
                )
            except Exception as e:
                logger.error(f"Error notifying blocked user {target_user_id}: {e}")
            return

        # Show profile of contact request sender
        if data.startswith("profile_show_requester_"):
            try:
                # Extract requester ID and contact ID from the callback data
                parts = data.replace("profile_show_requester_", "").split("_from_")
                target_user_id = int(parts[0])
                contact_id = int(parts[1]) if len(parts) > 1 else None
            except ValueError:
                await query.answer("Invalid profile data")
                return
            await show_profile_card(update, context, target_user_id, back_to_request_contact_id=contact_id)
            return

        # Start edit wizard from overview
        if data == "profile_edit":
            existing = get_user_profile(user_id)
            await start_profile_edit_wizard(update, context, existing_profile=existing)
            return
        
        # New: Show edit menu with sub-options
        if data == "profile_edit_menu":
            await show_profile_edit_menu(update, context)
            return

        # Edit specific fields
        if data == "edit_all":
            await query.edit_message_text(
                "✏️ *Edit Profile*\n\nType all info and use inline `_``...``_` code syntax if your answer spans more than 30 chars, send *Save Profile*.",
                parse_mode="MarkdownV2",
            )
            return
        
        if data == "edit_name":
            context.user_data['profile_state'] = 'editing_name_only'
            context.user_data['state'] = 'profile_editing'
            await query.edit_message_text(
                "✏️ *Edit Name*\n\nSend your new display name \\(2–32 characters\\):",
                parse_mode="MarkdownV2",
            )
            return
        
        if data == "edit_emoji":
            await show_emoji_selection(update, context)
            return
        
        if data.startswith("emoji_"):
            await handle_emoji_selection(update, context)
            return
        
        # Handle profile emoji selection during profile creation
        if data.startswith("profile_emoji_"):
            logger.info(f"Processing profile emoji selection: {data}")
            # Extract the emoji from the callback data
            emoji_data = data[len("profile_emoji_"):]
            emoji = "" if emoji_data == "none" else emoji_data
            logger.info(f"Extracted emoji data: {emoji_data}, final emoji: {emoji}")
            
            # Answer the callback query to acknowledge the selection
            await query.answer()
            
            # Get the profile draft
            draft = context.user_data.get('profile_draft', {})
            draft['emoji'] = emoji
            context.user_data['profile_draft'] = draft
            context.user_data['profile_state'] = 'editing_bio'
            logger.info(f"Updated draft with emoji: {draft}")
            
            # Remove the emoji selection keyboard
            await query.edit_message_text(
                "💬 *Short Bio*\n\n"
                "Send a short bio \\(up to 250 characters\\) describing yourself, or type `skip` to leave it empty\\.",
                parse_mode="MarkdownV2"
            )
            return        
        if data == "edit_bio":
            context.user_data['profile_state'] = 'editing_bio_only'
            context.user_data['state'] = 'profile_editing'
            await query.edit_message_text(
                "💬 *Edit Bio*\n\nSend your new bio \\(up to 250 characters\\) or type `skip` to leave it empty:\\.",
                parse_mode="MarkdownV2",
            )
            return
        
        if data == "edit_details":
            await show_edit_details_menu(update, context)
            return
        
        # Edit individual detail fields
        if data == "edit_gender":
            await show_gender_selection(update, context)
            return
        
        if data.startswith("gender_"):
            await handle_gender_selection(update, context)
            return
        
        if data == "edit_age":
            context.user_data['profile_state'] = 'editing_age'
            context.user_data['state'] = 'profile_editing'
            await query.edit_message_text(
                "🎂 *Edit Age*\n\nSend your age \\(number only\\) or type `skip` to leave it empty:\\.",
                parse_mode="MarkdownV2",
            )
            return
        
        if data == "edit_department":
            context.user_data['profile_state'] = 'editing_department'
            context.user_data['state'] = 'profile_editing'
            await query.edit_message_text(
                "🎓 *Edit Department*\n\nSend your department/field of study or type `skip` to leave it empty:\\.",
                parse_mode="MarkdownV2",
            )
            return
        
        if data == "edit_year":
            await show_year_selection(update, context)
            return
            
        if data.startswith("year_"):
            await handle_year_selection(update, context)
            return
        
        if data == "edit_religion":
            context.user_data['profile_state'] = 'editing_religion'
            context.user_data['state'] = 'profile_editing'
            await query.edit_message_text(
                "🕌 *Edit Religion*\n\nSend your religion or type `skip` to leave it empty:\\.",
                parse_mode="MarkdownV2",
            )
            return
        
        if data == "edit_relationship":
            await show_relationship_selection(update, context)
            return
        
        if data.startswith("relationship_"):
            await handle_relationship_selection(update, context)
            return

        if data == "edit_other_info":
            context.user_data['profile_state'] = 'editing_other_info'
            context.user_data['state'] = 'profile_editing'
            await query.edit_message_text(
                "📝 *Edit Other Info*\n\nSend any other information about yourself or type `skip` to leave it empty:\\.",
                parse_mode="MarkdownV2",
            )
            return
        
        # Previous Chats
        if data == "profile_previous_chats":
            await show_previous_chats(update, context)
            return
        
        if data.startswith("resume_chat_"):
            await resume_chat(update, context)
            return
        
        # Friends (placeholder for now)
        if data == "profile_friends":
            from profile_helpers import show_friends
            await show_friends(update, context)
            return
        
        # View specific friend
        if data.startswith("view_friend_"):
            from profile_helpers import show_friend_detail
            await show_friend_detail(update, context)
            return
        
        # View full profile of a friend
        if data.startswith("view_full_profile_"):
            friend_user_id = int(data.replace("view_full_profile_", ""))
            await show_profile_card(update, context, friend_user_id)
            return
        
        # Remove friend (end active contact)
        if data.startswith("remove_friend_"):
            contact_id = int(data.replace("remove_friend_", ""))
            contact = get_profile_contact_by_id(contact_id)
            if contact:
                update_profile_contact_status(contact_id, 'ended')
                await query.edit_message_text(
                    "💔 *Friend Removed*\n\n"
                    "This user has been removed from your friends list\\.",
                    parse_mode="MarkdownV2",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Friends", callback_data="profile_friends")
                    ]])
                )
            return
        
        # Inbox (placeholder for now)
        if data == "profile_inbox":
            from profile_helpers import show_inbox
            await show_inbox(update, context)
            return
        
        # View specific contact request
        if data.startswith("view_request_"):
            from profile_helpers import show_contact_request_detail
            await show_contact_request_detail(update, context)
            return
        
        # Block user from a contact request
        if data.startswith("profile_block_requester_"):
            contact_id = int(data.replace("profile_block_requester_", ""))
            contact = get_profile_contact_by_id(contact_id)
            if contact:
                requester_id = contact['initiator_id']
                block_profile_user(user_id, requester_id)
                update_profile_contact_status(contact_id, 'declined')
                await query.edit_message_text(
                    "🚫 *User Blocked*\n\n"
                    "This user has been blocked and the request declined\\.",
                    parse_mode="MarkdownV2",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Back to Inbox", callback_data="profile_inbox")
                    ]])
                )
            return
        
        # Blocked Users list
        if data == "profile_blocked_users":
            from profile_helpers import show_blocked_users
            await show_blocked_users(update, context)
            return
        
        # View specific blocked user
        if data.startswith("view_blocked_"):
            from profile_helpers import show_blocked_user_detail
            await show_blocked_user_detail(update, context)
            return
        
        # Back to profile
        if data == "back_to_profile":
            profile = get_user_profile(user_id)
            if profile:
                await send_profile_overview(update, context, profile)
            else:
                await my_profile_entry(update, context)
            return
        
        # Visibility toggles
        if data == "profile_visibility_on":
            set_profile_visibility(user_id, True)
            profile = get_user_profile(user_id)
            if profile:
                await send_profile_overview(update, context, profile)
            else:
                await my_profile_entry(update, context)
            return
        if data == "profile_visibility_off":
            set_profile_visibility(user_id, False)
            profile = get_user_profile(user_id)
            if profile:
                await send_profile_overview(update, context, profile)
            else:
                await my_profile_entry(update, context)
            return
        
        # Accepting contacts toggles
        if data == "profile_accepting_on":
            set_profile_accepting_contacts(user_id, True)
            profile = get_user_profile(user_id)
            if profile:
                await send_profile_overview(update, context, profile)
            else:
                await my_profile_entry(update, context)
            return
        if data == "profile_accepting_off":
            set_profile_accepting_contacts(user_id, False)
            profile = get_user_profile(user_id)
            if profile:
                await send_profile_overview(update, context, profile)
            else:
                await my_profile_entry(update, context)
            return

        # Delete profile (two-step confirmation)
        if data == "profile_delete":
            keyboard = [
                [InlineKeyboardButton("🗑 Yes, delete", callback_data="profile_delete_confirm")],
                [InlineKeyboardButton("🔙 Back", callback_data="menu")],
            ]
            await query.edit_message_text(
                "⚠️ *Delete Profile*\n\n"
                "This will remove your profile and hide your name from future posts and comments\\.\n\n"
                "Are you sure?",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="MarkdownV2",
            )
            return
        if data == "profile_delete_confirm":
            from db import delete_user_profile

            if delete_user_profile(user_id):
                # Clear wizard state
                context.user_data.pop('profile_state', None)
                context.user_data.pop('profile_draft', None)
                context.user_data.pop('state', None)
                await query.edit_message_text(
                    "✅ *Profile deleted*\n\nYou can always create a new one later from the menu\\.",
                    parse_mode="MarkdownV2",
                )
            else:
                await query.edit_message_text(
                    "❗ Failed to delete profile or it was already deleted\\.",
                    parse_mode="MarkdownV2",
                )
            return

        # Confirmation from wizard
        if data == "profile_confirm_save":
            draft = context.user_data.get('profile_draft') or {}
            if not draft.get('display_name'):
                await query.answer("Profile data missing, please start again\\.")
                await my_profile_entry(update, context)
                return

            existing = get_user_profile(user_id)
            is_active = existing['is_active'] if existing else True
            upsert_user_profile(
                user_id,
                draft.get('display_name', ''),
                draft.get('emoji', ''),
                draft.get('bio', ''),
                is_active=is_active,
            )

            # Clear wizard state
            context.user_data.pop('profile_state', None)
            context.user_data.pop('profile_draft', None)
            context.user_data.pop('state', None)

            profile = get_user_profile(user_id)
            await send_profile_overview(update, context, profile)
            return

        if data == "profile_edit_again":
            # Go back to editing the display name using existing draft
            context.user_data['profile_state'] = 'editing_name'
            context.user_data['state'] = 'profile_editing'
            await query.edit_message_text(
                "✅ *Chat already active*\\!\n\nSend messages here and I'll relay them\\.",
                parse_mode="MarkdownV2",
            )
            return

        # Update profile name
        if query.data == "update_profile_name":
            await query.edit_message_text(
                "✏️ *Update Profile Name*\n\nSend your new display name \\(2–32 characters\\):",
                parse_mode="MarkdownV2",
            )
            return

    # Cancel contact admin
    if data == "cancel_contact_admin":
        # Clear contact admin state
        await clear_user_context(context)
        await query.edit_message_text("🚫 Contact admin cancelled\\. Returned to main menu\\.", parse_mode="MarkdownV2")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="What would you like to do next?",
            reply_markup=ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)
        )
        return
    
    # View post
    if data.startswith("view_post_"):
        post_id = int(data.replace("view_post_", ""))
        await show_post_with_options(update, context, post_id)
        return
    
    # Add comment
    if data.startswith("add_comment_"):
        # Clear awaiting button selection state if user clicks button
        if context.user_data.get('state') == 'awaiting_button_selection':
            context.user_data.pop('state', None)
            context.user_data.pop('awaiting_post_id', None)
        await add_comment_callback(update, context)
        return
    
    # See comments
    if data.startswith("see_comments_"):
        # Clear awaiting button selection state if user clicks button
        if context.user_data.get('state') == 'awaiting_button_selection':
            context.user_data.pop('state', None)
            context.user_data.pop('awaiting_post_id', None)
        await see_comments_callback(update, context)
        return
    
    # User stats functions
    if data == "view_my_confessions":
        await view_my_confessions_callback(update, context)
        return
    
    if data == "back_to_stats":
        await back_to_stats_callback(update, context)
        return
    
    # Edit user's own posts
    if data.startswith("edit_my_post_"):
        await edit_my_post_callback(update, context)
        return
    
    # Like comment
    if data.startswith("like_comment_"):
        comment_id = int(data.replace("like_comment_", ""))
        # Import the new function that awards points
        from comments import react_to_comment_with_points
        success, action, likes, dislikes = await react_to_comment_with_points(user_id, comment_id, "like", context)
        
        if success:
            # Update the current message with new reaction counts
            comment = get_comment_by_id(comment_id)
            if comment:
                # Get updated reaction info
                user_reaction = get_user_reaction(user_id, comment_id)
                like_emoji = "👍✅" if user_reaction == "like" else "👍"
                dislike_emoji = "👎✅" if user_reaction == "dislike" else "👎"
                
                # Get sequential number for display
                sequential_number = get_comment_sequential_number(comment_id)
                
                # Check if this is a reply or main comment
                formatted_date = format_date_only(comment[5])  # Get properly escaped date part
                if comment[4]:  # parent_comment_id exists, so it's a reply
                    comment_text = f"reply\\# {sequential_number}\n\n{escape_markdown_text(comment[3])}\n\n{formatted_date}"
                else:
                    comment_text = f"comment\\# {sequential_number}\n\n{escape_markdown_text(comment[3])}\n\n{formatted_date}"
                
                # Create updated keyboard - Always include Reply button for main comments and replies
                if comment[4]:  # Reply - include reply button for second-level replies too
                    updated_keyboard = [
                        [
                            InlineKeyboardButton(f"{like_emoji} {likes}", callback_data=f"like_comment_{comment_id}"),
                            InlineKeyboardButton(f"{dislike_emoji} {dislikes}", callback_data=f"dislike_comment_{comment_id}"),
                            InlineKeyboardButton("💬 Reply", callback_data=f"reply_comment_{comment_id}"),
                            InlineKeyboardButton("⚠️ Report", callback_data=f"report_comment_{comment_id}")
                        ]
                    ]
                else:  # Main comment
                    updated_keyboard = [
                        [
                            InlineKeyboardButton(f"{like_emoji} {likes}", callback_data=f"like_comment_{comment_id}"),
                            InlineKeyboardButton(f"{dislike_emoji} {dislikes}", callback_data=f"dislike_comment_{comment_id}"),
                            InlineKeyboardButton("💬 Reply", callback_data=f"reply_comment_{comment_id}"),
                            InlineKeyboardButton("⚠️ Report", callback_data=f"report_comment_{comment_id}")
                        ]
                    ]
                
                updated_reply_markup = InlineKeyboardMarkup(updated_keyboard)
                
                try:
                    await query.edit_message_text(
                        comment_text,
                        reply_markup=updated_reply_markup,
                        parse_mode="MarkdownV2"
                    )
                except Exception as e:
                    logger.error(f"Error updating comment message: {e}")
            
            # Show feedback
            if action == "added":
                await query.answer(f"👍 Liked! ({likes})")
            elif action == "removed":
                await query.answer(f"👍 Like removed! ({likes})")
            elif action == "changed":
                await query.answer(f"👍 Changed to like! ({likes})")
        else:
            await query.answer("❗ Error liking comment")
        return
        
        # Refresh the comments view by calling the function directly with proper data
        comment = get_comment_by_id(comment_id)
        if comment:
            post_id = comment[1]
            page = context.user_data.get('current_page', 1)
            
            # Call the comments display directly
            try:
                comments_data, current_page, total_pages, total_comments = get_comments_paginated(post_id, page)
                
                # Build and update the message with refreshed like/dislike counts
                text = f"💬 *Comments \\({total_comments} total\\)*\n*Page {current_page} of {total_pages}*\n\n"
                keyboard = []
                
                for comment_data in comments_data:
                    comment = comment_data['comment']
                    replies = comment_data['replies']
                    total_replies = comment_data['total_replies']
                    
                    comment_id = comment[0]
                    content = comment[1]
                    timestamp = comment[2]
                    likes = comment[3]
                    dislikes = comment[4]
                    
                    # Format comment with proper line spacing
                    text += f"comment\\# {comment_id}\n\n"
                    text += f"{escape_markdown_text(content)}\n\n"
                    formatted_date = format_date_only(timestamp)  # Get properly escaped date part
                    text += f"{formatted_date}\n"
                    
                    # Add replies if any
                    if replies:
                        for reply in replies:
                            reply_content = reply[1]
                            text += f"↳ {escape_markdown_text(truncate_text(reply_content, 60))}\n"
                    
                    if total_replies > len(replies):
                        text += f"↳ \\.\\.\\.\\.\\. and {total_replies - len(replies)} more replies\n"
                    
                    text += "\n"
                    
                    # Add reaction buttons for this comment immediately after it
                    comment_row = [
                        InlineKeyboardButton("👍", callback_data=f"like_comment_{comment_id}"),
                        InlineKeyboardButton("👎", callback_data=f"dislike_comment_{comment_id}"),
                        InlineKeyboardButton("💬", callback_data=f"reply_comment_{comment_id}"),
                        InlineKeyboardButton("⚠️", callback_data=f"report_comment_{comment_id}")
                    ]
                    keyboard.append(comment_row)
                    
                    # Add a separator row between comments (except for the last one)
                    if comment_data != comments_data[-1]:
                        keyboard.append([InlineKeyboardButton("─────", callback_data="separator")])
                
                # Navigation buttons
                nav_buttons = []
                if current_page > 1:
                    nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"see_comments_{post_id}_{current_page-1}"))
                if current_page < total_pages:
                    nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"see_comments_{post_id}_{current_page+1}"))
                
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                # Action buttons
                keyboard.append([
                    InlineKeyboardButton("💬 Add Comment", callback_data=f"add_comment_{post_id}"),
                    InlineKeyboardButton("🔙 Back to Post", callback_data=f"view_post_{post_id}")
                ])
                keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
            except Exception as e:
                logger.error(f"Error refreshing comments view: {e}")
        return
    
    # Dislike comment
    if data.startswith("dislike_comment_"):
        comment_id = int(data.replace("dislike_comment_", ""))
        # Import the new function that awards points
        from comments import react_to_comment_with_points
        success, action, likes, dislikes = await react_to_comment_with_points(user_id, comment_id, "dislike", context)
        
        if success:
            # Update the current message with new reaction counts
            comment = get_comment_by_id(comment_id)
            if comment:
                # Get updated reaction info
                user_reaction = get_user_reaction(user_id, comment_id)
                like_emoji = "👍✅" if user_reaction == "like" else "👍"
                dislike_emoji = "👎✅" if user_reaction == "dislike" else "👎"
                
                # Get sequential number for display
                sequential_number = get_comment_sequential_number(comment_id)
                
                # Check if this is a reply or main comment
                formatted_date = format_date_only(comment[5])  # Get properly escaped date part
                if comment[4]:  # parent_comment_id exists, so it's a reply
                    comment_text = f"reply\\# {sequential_number}\n\n{escape_markdown_text(comment[3])}\n\n{formatted_date}"
                else:
                    comment_text = f"comment\\# {sequential_number}\n\n{escape_markdown_text(comment[3])}\n\n{formatted_date}"
                
                # Create updated keyboard - Always include Reply button for main comments and replies
                if comment[4]:  # Reply - include reply button for second-level replies too
                    updated_keyboard = [
                        [
                            InlineKeyboardButton(f"{like_emoji} {likes}", callback_data=f"like_comment_{comment_id}"),
                            InlineKeyboardButton(f"{dislike_emoji} {dislikes}", callback_data=f"dislike_comment_{comment_id}"),
                            InlineKeyboardButton("💬 Reply", callback_data=f"reply_comment_{comment_id}"),
                            InlineKeyboardButton("⚠️ Report", callback_data=f"report_comment_{comment_id}")
                        ]
                    ]
                else:  # Main comment
                    updated_keyboard = [
                        [
                            InlineKeyboardButton(f"{like_emoji} {likes}", callback_data=f"like_comment_{comment_id}"),
                            InlineKeyboardButton(f"{dislike_emoji} {dislikes}", callback_data=f"dislike_comment_{comment_id}"),
                            InlineKeyboardButton("💬 Reply", callback_data=f"reply_comment_{comment_id}"),
                            InlineKeyboardButton("⚠️ Report", callback_data=f"report_comment_{comment_id}")
                        ]
                    ]
                
                updated_reply_markup = InlineKeyboardMarkup(updated_keyboard)
                
                try:
                    await query.edit_message_text(
                        comment_text,
                        reply_markup=updated_reply_markup,
                        parse_mode="MarkdownV2"
                    )
                except Exception as e:
                    logger.error(f"Error updating comment message: {e}")
            
            # Show feedback
            if action == "added":
                await query.answer(f"👎 Disliked! ({dislikes})")
            elif action == "removed":
                await query.answer(f"👎 Dislike removed! ({dislikes})")
            elif action == "changed":
                await query.answer(f"👎 Changed to dislike! ({dislikes})")

    
    # Reply to comment
    if data.startswith("reply_comment_"):
        comment_id = int(data.replace("reply_comment_", ""))
        comment = get_comment_by_id(comment_id)
        
        if comment:
            post_id = comment[1]
            context.user_data['comment_post_id'] = post_id
            context.user_data['reply_to_comment_id'] = comment_id
            context.user_data['state'] = 'writing_comment'
            
            comment_preview = truncate_text(comment[3], 100)
            
            # Get sequential number for display
            sequential_number = get_comment_sequential_number(comment_id)
            
            # Create cancel button for the reply interface
            reply_cancel_keyboard = [[InlineKeyboardButton("🚫 Cancel", callback_data="cancel_to_menu")]]
            reply_cancel_markup = InlineKeyboardMarkup(reply_cancel_keyboard)
            
            await query.edit_message_text(
                f"💬 *Replying to comment \\#{sequential_number}*\n\n"
                f"*Original:* {escape_markdown_text(comment_preview)}\n\n"
                f"Write your reply \\(max {MAX_COMMENT_LENGTH} characters\\)\\:\n\n"
                f"Type your reply below or use the Cancel button to return to main menu\\.",
                reply_markup=reply_cancel_markup,
                parse_mode="MarkdownV2"
            )
        return
    
    # Report comment - Show reason selection using enhanced reporting
    if data.startswith("report_comment_"):
        comment_id = int(data.replace("report_comment_", ""))
        await show_report_reasons(update, context, 'comment', comment_id)
        return

    # Reporting: generic flows (reasons, submit, cancel, back)
    if data.startswith("report_post_"):
        post_id = int(data.replace("report_post_", ""))
        await show_report_reasons(update, context, 'post', post_id)
        return

    if data.startswith("report_reason_"):
        await handle_report_reason_callback(update, context)
        return

    if data.startswith("submit_report_"):
        await handle_submit_report(update, context)
        return

    if data == "cancel_report":
        await handle_cancel_report(update, context)
        return

    if data.startswith("report_post_") or data.startswith("report_comment_"):
        # Back navigation from confirmation goes here (already handled above for comment; this is a safety net)
        parts = data.split('_')
        if len(parts) >= 3:
            ctype = parts[1]
            cid = int(parts[2])
            await show_report_reasons(update, context, ctype, cid)
            return
    
    
    # Admin dashboard callbacks
    if data == "admin_dashboard":
        await admin_dashboard_callback(update, context)
        return
    
    if data == "admin_analytics":
        await admin_analytics(update, context)
        return
        
    if data == "admin_users":
        await admin_user_management(update, context)
        return
        
    if data == "admin_blocked_users":
        await admin_blocked_users(update, context)
        return
        
    if data == "admin_active_users":
        await admin_active_users(update, context)
        return
        
    if data.startswith("admin_unblock_"):
        await admin_unblock_user_callback(update, context)
        return
        
    if data.startswith("admin_block_"):
        await admin_block_user_callback(update, context)
        return
        
    if data.startswith("admin_user_info_"):
        await admin_user_info_callback(update, context)
        return
        
    if data == "admin_content":
        await admin_content_management(update, context)
        return
        
    if data == "admin_pending_posts":
        await admin_pending_posts(update, context)
        return
        
    if data == "admin_moderation":
        await admin_moderation_panel(update, context)
        return
        
    if data == "admin_messages":
        await admin_messages_panel(update, context)
        return
        
    if data == "admin_broadcast":
        # Ask admin for broadcast message with cancel option
        keyboard = [
            [InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_broadcast")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📢 *Broadcast Message*\n\n"
            "Please type the message you want to send to all users. "
            "This message will be sent to all bot users.\n\n"
            "You can also send a photo, video, or document with a caption.\n\n"
            "Use the cancel button to return to the menu:",
            reply_markup=reply_markup
        )
        context.user_data['state'] = 'admin_broadcast'
        return
        
    if data == "admin_system":
        await admin_system_info(update, context)
        return

    # Trending menu callbacks
    if data == "trending_most_commented":
        await show_most_commented_posts(update, context)
        return
    
    if data == "trending_rising":
        await show_rising_posts(update, context)
        return
    
    if data == "trending_most_liked":
        await show_most_liked_posts(update, context)
        return
    
    if data == "trending_all":
        await show_all_trending_posts(update, context)
        return
    
    if data == "back_to_trending":
        # Go back to trending menu
        trending_text = """
🔥 *Trending Content*

Choose what type of trending content you'd like to see:

💬 *Most Commented:* Posts with the most discussions \\(24h\\)
🔥 *Hot & Rising:* Posts gaining traction fast
👍 *Most Liked:* Posts with the most liked comments
⭐ *All Trending:* Combined trending algorithm

Select a category below:
"""
        
        keyboard = [
            [
                InlineKeyboardButton("💬 Most Commented", callback_data="trending_most_commented"),
                InlineKeyboardButton("🔥 Hot & Rising", callback_data="trending_rising")
            ],
            [
                InlineKeyboardButton("👍 Most Liked", callback_data="trending_most_liked"),
                InlineKeyboardButton("⭐ All Trending", callback_data="trending_all")
            ],
            [
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            trending_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        return

    # Admin message management callbacks
    if data.startswith("admin_reply_"):
        await handle_admin_reply_callback(update, context)
        return

    # Handle admin dismiss report (from immediate notification)
    if data.startswith("admin_dismiss_report_comment_") or data.startswith("admin_dismiss_report_post_"):
        from enhanced_reporting import handle_admin_dismiss_report
        await handle_admin_dismiss_report(update, context)
        return
    
    # Handle admin broadcast cancel
    if data == "admin_cancel_broadcast":
        context.user_data.pop('state', None)
        await admin_messages_panel(update, context)
        return
    
    if data.startswith("admin_history_"):
        await handle_admin_history_callback(update, context)
        return
    
    if data.startswith("admin_read_"):
        await handle_admin_read_callback(update, context)
        return
    
    if data.startswith("admin_ignore_"):
        await handle_admin_ignore_callback(update, context)
        return
        
    # Additional admin panel feature callbacks
    if data == "admin_recent_posts":
        await admin_recent_posts(update, context)
        return
        
    if data == "admin_content_stats":
        await admin_content_stats(update, context)
        return
        
    if data == "admin_content_cleanup":
        await admin_content_cleanup(update, context)
        return
        
    if data == "admin_view_reports":
        await admin_view_reports(update, context)
        return
        
    if data == "admin_mod_stats":
        await admin_mod_stats(update, context)
        return
        
    if data == "admin_mod_settings":
        await admin_mod_settings(update, context)
        return
        
    if data == "admin_audit_log":
        await admin_audit_log(update, context)
        return
        
    if data == "admin_pending_messages":
        await admin_pending_messages(update, context)
        return
        
    if data == "admin_message_history":
        await admin_message_history(update, context)
        return
        
    if data == "admin_auto_reply":
        await admin_auto_reply(update, context)
        return
        
    if data == "admin_message_stats":
        await admin_message_stats(update, context)
        return
        
    if data == "admin_db_stats":
        await admin_db_stats(update, context)
        return
        
    if data == "admin_backup_info":
        await admin_backup_info(update, context)
        return
        
    if data == "admin_search_user":
        await admin_search_user(update, context)
        return
        
    if data == "admin_user_analytics":
        await admin_user_analytics(update, context)
        return
        
    if data == "admin_export":
        await query.answer("Export feature is currently under development.")
        return
    
    # User Search callbacks
    if data == "search_user_by_id":
        await search_user_by_id_callback(update, context)
        return
        
    if data == "search_user_by_username":
        await search_user_by_username_callback(update, context)
        return
        
    if data == "search_user_by_letter":
        await search_user_by_letter_callback(update, context)
        return
        
    if data == "search_user_general":
        await search_user_general_callback(update, context)
        return
        
    if data == "search_user_recent":
        await search_user_recent_callback(update, context)
        return
        
    if data == "search_user_active":
        await search_user_active_callback(update, context)
        return
        
    if data.startswith("admin_user_detail_"):
        # Handle detailed user info view
        user_id_to_view = int(data.replace("admin_user_detail_", ""))
        await admin_user_detailed_info(update, context, user_id_to_view)
        return
    
    # Admin user posts navigation
    if data.startswith("admin_user_posts_"):
        await admin_user_posts_callback(update, context)
        return
    
    # Admin user comments navigation
    if data.startswith("admin_user_comments_"):
        await admin_user_comments_callback(update, context)
        return
    
    # Admin user activity analytics
    if data.startswith("admin_user_activity_analytics_"):
        await admin_user_activity_analytics_callback(update, context)
        return
    
    if data.startswith("admin_user_post_analytics_"):
        await admin_user_post_analytics_callback(update, context)
        return
    
    if data.startswith("admin_user_comment_analytics_"):
        await admin_user_comment_analytics_callback(update, context)
        return
    
    # Backup management callbacks
    if data == "admin_create_backup":
        await admin_create_backup_callback(update, context)
        return
    
    if data == "admin_list_backups":
        await admin_list_backups_callback(update, context)
        return
    
    if data == "admin_cleanup_backups":
        await admin_cleanup_backups_callback(update, context)
        return
    
    # Enhanced ranking callbacks
    if data.startswith("ranking_"):
        await enhanced_ranking_callback_handler(update, context)
        return
    
    # Database management callbacks
    if data == "admin_table_info":
        await admin_table_info_callback(update, context)
        return
    
    if data == "admin_db_maintenance":
        await admin_db_maintenance_callback(update, context)
        return
    
    # Post and comment deletion callbacks
    if data.startswith("admin_delete_post_"):
        await handle_admin_delete_post_callback(update, context)
        return
    
    if data.startswith("admin_delete_comment_"):
        await handle_admin_delete_comment_callback(update, context)
        return

    # Admin action: replace comment content with removal notice (from report notification)
    if data.startswith("admin_replace_comment_"):
        from admin_deletion import replace_comment_with_message
        try:
            comment_id = int(data.replace("admin_replace_comment_", ""))
        except Exception:
            comment_id = None
        
        if comment_id:
            admin_user_id = query.from_user.id
            success, replacement_stats = replace_comment_with_message(
                comment_id=comment_id,
                admin_user_id=admin_user_id,
                replacement_message="[This comment has been removed by moderators due to reports]"
            )
            
            if success:
                await query.answer("✅ Comment replaced with removal notice")
                await query.edit_message_text(
                    f"✅ **Comment Replaced Successfully**\n\n"
                    f"**Comment \\#{comment_id}** has been replaced with a removal notice\\."
                    f"\n\n**Statistics:**\n"
                    f"• Comments replaced: {replacement_stats['comments_replaced']}\n"
                    f"• Replies replaced: {replacement_stats['replies_replaced']}\n"
                    f"• Reports cleared: {replacement_stats['reports_cleared']}\n\n"
                    f"The comment structure has been preserved while hiding inappropriate content\\.",
                    parse_mode="MarkdownV2"
                )
            else:
                error_message = replacement_stats.get('error', 'Unknown error')
                await query.answer("❗ Failed to replace comment")
                await query.edit_message_text(
                    f"❗ **Failed to replace comment \\#{comment_id}**\n\n"
                    f"Error: {escape_markdown_text(error_message)}\n\n"
                    f"Please try again or contact system administrator\\.",
                    parse_mode="MarkdownV2"
                )
        return
        
    # Post and comment deletion confirmation callbacks
    if data.startswith("confirm_delete_post_"):
        await handle_confirm_delete_post_callback(update, context)
        return
    
    if data.startswith("confirm_delete_comment_"):
        await handle_confirm_delete_comment_callback(update, context)
        return
        
    # Clear reports callbacks
    if data.startswith("admin_clear_reports_"):
        await handle_admin_clear_reports_callback(update, context)
        return
        
    # Approve content callbacks
    if data.startswith("admin_approve_"):
        await handle_admin_approve_callback(update, context)
        return
    
    # Handle approval notification button callbacks
    if data == "start_confession":
        # Clear any existing context and start confession flow
        await clear_user_context(context)
        await query.edit_message_text("🙊 *Starting confession submission\\.\\.\\.*", parse_mode="MarkdownV2")
        # Start confession flow with direct message instead of callback
        from telegram import Update as TgUpdate
        from telegram.ext import ContextTypes
        # Create a fake update object to call the start_confession_flow
        fake_update = TgUpdate(update_id=0, message=update.effective_message)
        fake_update._effective_chat = update.effective_chat
        fake_update._effective_user = update.effective_user
        await start_confession_flow(fake_update, context)
        return
    
    if data == "my_stats":
        # Clear any existing context and show user stats
        await clear_user_context(context)
        await query.edit_message_text("📊 *Loading your statistics\\.\\.\\.*", parse_mode="MarkdownV2")
        # Create a fake update object to call my_stats function  
        from telegram import Update as TgUpdate
        fake_update = TgUpdate(update_id=0, message=update.effective_message)
        fake_update._effective_chat = update.effective_chat
        fake_update._effective_user = update.effective_user
        await my_stats(fake_update, context)
        return
    
    if data == "contact_admin":
        # Clear any existing context and start contact admin flow
        await clear_user_context(context)
        await query.edit_message_text("📞 *Starting contact admin\\.\\.\\.*", parse_mode="MarkdownV2")
        # Create a fake update object to call start_contact_admin
        from telegram import Update as TgUpdate
        fake_update = TgUpdate(update_id=0, message=update.effective_message)
        fake_update._effective_chat = update.effective_chat
        fake_update._effective_user = update.effective_user
        await start_contact_admin(fake_update, context)
        return

# Admin message callback handlers
async def handle_admin_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quick reply button press from admin with duplicate prevention"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        await query.answer("❗ You are not authorized to use admin features.")
        return
    
    # Extract message ID from callback data
    message_id = int(query.data.replace("admin_reply_", ""))
    
    # Check if message has already been replied to
    from admin_messaging import check_message_reply_status
    reply_status = check_message_reply_status(message_id)
    
    if reply_status and reply_status['has_reply']:
        replied_by_admin = reply_status['replied_by_admin']
        if replied_by_admin == user_id:
            await query.answer("⚠️ You have already replied to this message!")
            await query.edit_message_text(
                f"⚠️ *Already Replied*\n\n"
                f"You have already replied to message \\#{message_id}\\.",
                parse_mode="MarkdownV2"
            )
        else:
            await query.answer("⚠️ This message has already been replied to by another admin!")
            await query.edit_message_text(
                f"⚠️ *Message Already Handled*\n\n"
                f"Message \\#{message_id} has already been replied to by Admin {replied_by_admin}\\.",
                parse_mode="MarkdownV2"
            )
        return
    
    # Store the message ID in context for reply handling
    context.user_data['replying_to_message_id'] = message_id
    context.user_data['state'] = 'admin_replying'
    
    await query.edit_message_text(
        f"💬 *Quick Reply to Message \\#{message_id}*\n\n"
        f"Please type your reply message\\. It will be sent anonymously to the user\\.",
        parse_mode="MarkdownV2"
    )

async def handle_admin_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle view history button press from admin"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        await query.answer("❗ You are not authorized to use admin features.")
        return
    
    # Extract user ID from callback data
    sender_user_id = int(query.data.replace("admin_history_", ""))
    
    try:
        from admin_messaging import get_user_message_history
        history = get_user_message_history(sender_user_id)
        
        if not history:
            await query.answer("📋 No message history found for this user.")
            return
        
        history_text = f"📋 *Message History for User {sender_user_id}*\n\n"
        
        for i, (msg_id, content, timestamp, replied, reply_text) in enumerate(history[-10:], 1):  # Last 10 messages
            history_text += f"*Message \\#{msg_id}*\n"
            history_text += f"Time: {escape_markdown_text(timestamp[:16])}\n"
            history_text += f"Content: {escape_markdown_text(truncate_text(content, 80))}\n"
            if replied:
                reply_preview = truncate_text(reply_text, 50) if reply_text else "[Reply sent]"
                history_text += f"Reply: {escape_markdown_text(reply_preview)}\n"
            else:
                history_text += "Status: Unread\n"
            history_text += "\n"
        
        # Limit message length
        if len(history_text) > 4000:
            history_text = history_text[:4000] + "\n\n\\.\\.\\. *Message truncated*"
        
        await query.edit_message_text(
            history_text,
            parse_mode="MarkdownV2"
        )
    
    except Exception as e:
        await query.answer(f"❗ Error retrieving message history: {str(e)}")

async def handle_admin_read_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mark as read button press from admin"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        await query.answer("❗ You are not authorized to use admin features.")
        return
    
    # Extract message ID from callback data
    message_id = int(query.data.replace("admin_read_", ""))
    
    try:
        from admin_messaging import mark_message_as_read
        success = mark_message_as_read(message_id)
        
        if success:
            await query.answer("✅ Message marked as read!")
            await query.edit_message_text(
                f"✅ *Message \\#{message_id} marked as read*\n\n"
                f"This message has been marked as handled\\.",
                parse_mode="MarkdownV2"
            )
        else:
            await query.answer("❗ Failed to mark message as read")
    
    except Exception as e:
        await query.answer(f"❗ Error: {str(e)}")

async def handle_admin_ignore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ignore user button press from admin"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_IDS:
        await query.answer("❗ You are not authorized to use admin features.")
        return
    
    # Extract user ID from callback data
    sender_user_id = int(query.data.replace("admin_ignore_", ""))
    
    try:
        from admin_messaging import ignore_user_messages
        success = ignore_user_messages(sender_user_id)
        
        if success:
            await query.answer("🔇 User messages will be ignored!")
            await query.edit_message_text(
                f"🔇 *User {sender_user_id} ignored*\n\n"
                f"Future messages from this user will be automatically marked as ignored\\.",
                parse_mode="MarkdownV2"
            )
        else:
            await query.answer("❗ Failed to ignore user")
    
    except Exception as e:
        await query.answer(f"❗ Error: {str(e)}")

# Admin Commands
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command for administrators"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    admin_text = """
🔧 *Admin Panel*

*Basic Commands:*
• `/stats` \\- View channel statistics
• `/pending` \\- View pending submissions
• `/messages` \\- View pending user messages
• `/reply <message_id> <reply>` \\- Reply to user message
• `/admin` \\- Show this help

*Report Management:*
• `/reports` \\- View reported content

*User Management:*
• `/users [user_id]` \\- View user info or management help
• `/block <user_id>` \\- Block a user
• `/unblock <user_id>` \\- Unblock a user
• `/blocked` \\- List blocked users

*Manual Actions:*
• Use approval buttons when posts are submitted
• Monitor user activity and reports
"""
    
    await update.message.reply_text(admin_text, parse_mode="MarkdownV2")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command for administrators"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    stats = get_channel_stats()
    
    stats_text = f"""
📊 *Channel Statistics*

*Content:*
• Total Posts: {stats['total_posts']}
• Total Comments: {stats['total_comments']}
• Pending Posts: {stats['pending_posts']}

*Users:*
• Total Users: {stats['total_users']}

*Moderation:*
• Flagged Posts: {stats['flagged_posts']}
• Flagged Comments: {stats['flagged_comments']}
• Total Reactions: {stats['total_reactions']}
"""
    
    await update.message.reply_text(stats_text, parse_mode="MarkdownV2")

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pending command to show pending submissions"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    pending_posts = get_pending_submissions()
    
    if not pending_posts:
        await update.message.reply_text("✅ No pending submissions.")
        return
    
    for post in pending_posts[:5]:  # Show first 5 pending posts
        post_id, content, category, timestamp, user_id, approved, channel_message_id, flagged, likes = post
        
        admin_text = f"""
📝 *Pending Submission {escape_markdown_text(f'#{post_id}')}*

*Category:* {escape_markdown_text(category)}
*Submitter:* {user_id}
*Time:* {timestamp[:16] if timestamp else 'Unknown'}

*Content:*
{escape_markdown_text(content)}
"""
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{post_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{post_id}")
            ],
            [
                InlineKeyboardButton("🚩 Flag", callback_data=f"flag_{post_id}"),
                InlineKeyboardButton("⛔ Block User", callback_data=f"block_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            admin_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )

async def messages_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /messages command to show pending user messages"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    pending_messages = get_pending_messages()
    
    if not pending_messages:
        await update.message.reply_text("✅ No pending user messages.")
        return
    
    messages_text = "📨 *Pending User Messages:*\n\n"
    
    for message in pending_messages[:10]:  # Show latest 10 messages
        message_id, sender_id, message_content, timestamp = message
        messages_text += f"*Message {escape_markdown_text(f'#{message_id}')}*\n"
        messages_text += f"From: {sender_id}\n"
        messages_text += f"Time: {escape_markdown_text(timestamp[:16])}\n"
        messages_text += f"Content: {escape_markdown_text(truncate_text(message_content, 100))}\n"
        messages_text += f"Reply with: `/reply {message_id} <your_message>`\n\n"
    
    await update.message.reply_text(messages_text, parse_mode="MarkdownV2")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command for admin broadcast messages"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❗ Usage: /broadcast <your_message>\n\n"
            "Example: /broadcast Hello everyone! This is an important announcement."
        )
        return
    
    message = " ".join(context.args)
    
    # Import the broadcast function
    from admin_messaging import send_broadcast_message
    
    try:
        success, result = await send_broadcast_message(context, message, user_id)
        
        if success:
            await update.message.reply_text(f"✅ {result}")
        else:
            await update.message.reply_text(f"❗ Failed to send broadcast: {result}")
    
    except Exception as e:
        await update.message.reply_text(f"❗ Error sending broadcast: {str(e)}")


async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reply command for admin responses"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❗ Usage: /reply <message_id> <your_reply>")
        return
    
    try:
        message_id = int(context.args[0])
        reply_text = " ".join(context.args[1:])
        
        success, result = await send_admin_reply_to_user(context, message_id, user_id, reply_text)
        
        if success:
            await update.message.reply_text("✅ Reply sent successfully!")
        else:
            await update.message.reply_text(f"❗ Failed to send reply: {result}")
    
    except ValueError:
        await update.message.reply_text("❗ Invalid message ID. Must be a number.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages"""
    user_id = update.message.from_user.id
    
    # Handle current conversation states
    state = context.user_data.get('state')
    edit_state = context.user_data.get('edit_state')
    
    # Handle post edit mode (check this FIRST before other states)
    if edit_state == 'waiting_for_new_content':
        await handle_post_edit_content(update, context)
        return
    
    # Handle admin broadcast message
    if state == 'admin_broadcast':
        # Check if user is admin
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("❗ You are not authorized to use admin features.")
            context.user_data.pop('state', None)
            return
        
        # Check if cancel button was pressed
        if update.callback_query and update.callback_query.data == "admin_messages":
            context.user_data.pop('state', None)
            await admin_messages_panel(update, context)
            return
        
        # Get the broadcast message and check for media
        message = ""  # Initialize message as empty string
        media_file = None
        media_type = None
        
        # Check for text message
        if update.message.text:
            message = update.message.text
        
        # Check for media attachments with captions
        if update.message.photo:
            media_file = update.message.photo[-1].file_id  # Get highest resolution photo
            media_type = 'photo'
            # Check for caption
            if update.message.caption:
                message = update.message.caption
        elif update.message.video:
            media_file = update.message.video.file_id
            media_type = 'video'
            # Check for caption
            if update.message.caption:
                message = update.message.caption
        elif update.message.document:
            media_file = update.message.document.file_id
            media_type = 'document'
            # Check for caption
            if update.message.caption:
                message = update.message.caption
        
        # If no message and no media, prompt again
        if not message and not media_file:
            await update.message.reply_text("Please provide a message or media file to broadcast, or use the cancel button.")
            return
        
        # Import the broadcast function
        from admin_messaging import send_broadcast_message
        
        try:
            success, result = await send_broadcast_message(context, message, user_id, media_file, media_type)
            
            if success:
                await update.message.reply_text(f"✅ {result}")
            else:
                await update.message.reply_text(f"❗ Failed to send broadcast: {result}")
        
        except Exception as e:
            await update.message.reply_text(f"❗ Error sending broadcast: {str(e)}")
        
        # Clear the state and show menu
        context.user_data.pop('state', None)
        await show_menu(update, context)
        return
    
    # Check if user is awaiting button selection (after comment submission)
    if state == 'awaiting_button_selection':
        # Handle button selection for comment submission
        text = update.message.text.strip()
        if text.lower() in ['1', '2', '3', '4', '5']:
            # Process the selected button
            button_index = int(text) - 1
            selected_buttons = context.user_data.get('selected_buttons', [])
            
            if button_index < len(selected_buttons):
                button = selected_buttons[button_index]
                # Process the button action
                await process_button_action(update, context, button)
                return
            else:
                await update.message.reply_text("❗ Invalid button selection. Please choose a valid button number.")
                return
        else:
            await update.message.reply_text("❗ Please select a button by typing its number (1-5) or use the menu.")
            return

async def reports_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reports command to show reported content"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    from moderation import get_reports
    reports = get_reports()
    
    if not reports:
        await update.message.reply_text("✅ No reports found.")
        return
    
    # Group reports by target
    from collections import defaultdict
    reports_by_target = defaultdict(list)
    
    for report in reports:
        report_id, user_id, target_type, target_id, reason, timestamp = report
        reports_by_target[(target_type, target_id)].append(report)
    
    reports_text = "🚩 *Reported Content:*\n\n"
    
    for (target_type, target_id), target_reports in reports_by_target.items():
        report_count = len(target_reports)
        first_report = target_reports[0]
        
        # Get content details
        from moderation import get_content_details
        content_details = get_content_details(target_type, target_id)
        
        if content_details:
            if target_type == 'comment':
                comment_id, post_id, content, timestamp = content_details
                preview = truncate_text(content, 100)
                reports_text += f"📝 *Comment \\#{comment_id}* \\(Post \\#{post_id}\\)\n"
                reports_text += f"Reports: {report_count}\n"
                reports_text += f"Content: {escape_markdown_text(preview)}\n\n"
            else:  # post
                post_id, content, category, timestamp = content_details
                preview = truncate_text(content, 100)
                reports_text += f"📝 *Post \\#{post_id}*\n"
                reports_text += f"Category: {escape_markdown_text(category)}\n"
                reports_text += f"Reports: {report_count}\n"
                reports_text += f"Content: {escape_markdown_text(preview)}\n\n"
        else:
            reports_text += f"❓ *{target_type.title()} \\#{target_id}* \\(Content not found\\)\n"
            reports_text += f"Reports: {report_count}\n\n"
    
    # Split long messages
    if len(reports_text) > 4000:
        reports_text = reports_text[:4000] + "\n\n\\.\\.\\. *Message truncated*"
    
    await update.message.reply_text(reports_text, parse_mode="MarkdownV2")

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /users command to show user management options"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    if context.args:
        # Handle specific user ID
        try:
            target_user_id = int(context.args[0])
            
            db_conn = get_db_connection()
            with db_conn.get_connection() as conn:
                cursor = conn.cursor()
                placeholder = db_conn.get_placeholder()
                cursor.execute(
                    f"SELECT user_id, username, first_name, last_name, join_date, questions_asked, comments_posted, blocked FROM users WHERE user_id = {placeholder}",
                    (target_user_id,)
                )
                user_data = cursor.fetchone()
                
                if not user_data:
                    await update.message.reply_text(f"❗ User {target_user_id} not found in database.")
                    return
                
                uid, username, first_name, last_name, join_date, questions_asked, comments_posted, blocked = user_data
                
                status = "🚫 Blocked" if blocked else "✅ Active"
                name = f"{first_name or ''} {last_name or ''}".strip()
                
                user_text = f"""
👤 *User Information*

*Details:*
• User ID: `{uid}`
• Username: {f"@{escape_markdown_text(username)}" if username else "None"}
• Name: {escape_markdown_text(name) if name else "None"}
• Status: {status}
• Joined: {escape_markdown_text(join_date[:16]) if join_date else "Unknown"}

*Activity:*
• Confessions Posted: {questions_asked}
• Comments Posted: {comments_posted}

*Actions:*
• `/block {uid}` \\- Block user
• `/unblock {uid}` \\- Unblock user
• `/userstats {uid}` \\- View detailed stats
"""
                
                await update.message.reply_text(user_text, parse_mode="MarkdownV2")
                return
                
        except ValueError:
            await update.message.reply_text("❗ Invalid user ID. Must be a number.")
            return
    
    # Show general user management help
    users_text = """
👥 *User Management*

*Commands:*
• `/users <user_id>` \\- View specific user info
• `/block <user_id>` \\- Block a user
• `/unblock <user_id>` \\- Unblock a user
• `/blocked` \\- List blocked users

*Examples:*
• `/users 123456789`
• `/block 123456789`
• `/unblock 123456789`
"""
    
    await update.message.reply_text(users_text, parse_mode="MarkdownV2")

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /block command to block a user"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    if not context.args:
        await update.message.reply_text("❗ Usage: /block <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        from approval import block_user, is_blocked_user
        
        if await async_is_blocked_user(target_user_id):
            await update.message.reply_text(f"❗ User {target_user_id} is already blocked.")
            return
        
        block_user(target_user_id)
        await update.message.reply_text(f"⛔ User {target_user_id} has been blocked.")
        
    except ValueError:
        await update.message.reply_text("❗ Invalid user ID. Must be a number.")
    except Exception as e:
        await update.message.reply_text(f"❗ Error blocking user: {str(e)}")

async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unblock command to unblock a user"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    if not context.args:
        await update.message.reply_text("❗ Usage: /unblock <user_id>")
        return
    
    try:
        target_user_id = int(context.args[0])
        from approval import unblock_user, is_blocked_user
        
        if not await async_is_blocked_user(target_user_id):
            await update.message.reply_text(f"❗ User {target_user_id} is not blocked.")
            return
        
        unblock_user(target_user_id)
        await update.message.reply_text(f"✅ User {target_user_id} has been unblocked.")
        
    except ValueError:
        await update.message.reply_text("❗ Invalid user ID. Must be a number.")
    except Exception as e:
        await update.message.reply_text(f"❗ Error unblocking user: {str(e)}")

async def blocked_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /blocked command to show blocked users"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin commands.")
        return
    
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, username, first_name, last_name, join_date FROM users WHERE blocked = 1 ORDER BY join_date DESC"
        )
        blocked_users = cursor.fetchall()
    
    if not blocked_users:
        await update.message.reply_text("✅ No blocked users found.")
        return
    
    blocked_text = "⛔ *Blocked Users:*\n\n"
    
    for user_data in blocked_users[:20]:  # Show max 20 users
        uid, username, first_name, last_name, join_date = user_data
        name = f"{first_name or ''} {last_name or ''}".strip()
        
        blocked_text += f"• `{uid}` \\- "
        if username:
            blocked_text += f"@{escape_markdown_text(username)}"
        elif name:
            blocked_text += escape_markdown_text(name)
        else:
            blocked_text += "No name"
        blocked_text += f" \\(joined {escape_markdown_text(join_date[:10]) if join_date else 'Unknown'}\\)\n"
    
    blocked_text += f"\n*Total blocked users:* {len(blocked_users)}\n\n"
    blocked_text += "*Use `/unblock <user_id>` to unblock a user\\.*"
    
    await update.message.reply_text(blocked_text, parse_mode="MarkdownV2")

# Admin Dashboard - Interactive Interface
async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive admin dashboard with interactive buttons"""
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin features.")
        return
    
    # Get quick stats
    stats = get_channel_stats()
    pending_posts = len(get_pending_submissions())
    pending_messages = len(get_pending_messages())
    
    dashboard_text = f"""
🔧 *Admin Dashboard*

*Quick Overview:*
• Total Posts: {stats['total_posts']}
• Total Users: {stats['total_users']}
• Pending Posts: {pending_posts}
• Pending Messages: {pending_messages}

Choose a section to manage:
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics"),
            InlineKeyboardButton("👥 User Management", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton("📝 Content Management", callback_data="admin_content"),
            InlineKeyboardButton("🚩 Reports & Moderation", callback_data="admin_moderation")
        ],
        [
            InlineKeyboardButton("💬 Messages", callback_data="admin_messages"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("⚙️ System Info", callback_data="admin_system")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        dashboard_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed analytics and insights"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Get comprehensive analytics
    stats = get_channel_stats()
    
    # Get additional analytics
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        
        # Get user activity trends (last 7 days)
        cursor.execute("""
            SELECT DATE(join_date) as day, COUNT(*) as new_users 
            FROM users 
            WHERE join_date >= DATE('now', '-7 days') 
            GROUP BY DATE(join_date) 
            ORDER BY day DESC
        """)
        user_trends = cursor.fetchall()
        
        # Get post activity trends (last 7 days)
        cursor.execute("""
            SELECT DATE(timestamp) as day, COUNT(*) as posts 
            FROM posts 
            WHERE timestamp >= DATE('now', '-7 days') AND approved = 1
            GROUP BY DATE(timestamp) 
            ORDER BY day DESC
        """)
        post_trends = cursor.fetchall()
        
        # Get most active users
        cursor.execute("""
            SELECT u.first_name, u.username, u.questions_asked, u.comments_posted,
                   (u.questions_asked + u.comments_posted) as total_activity
            FROM users u
            WHERE u.blocked = 0
            ORDER BY total_activity DESC
            LIMIT 5
        """)
        top_users = cursor.fetchall()
        
        # Get category breakdown
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM posts 
            WHERE approved = 1 
            GROUP BY category 
            ORDER BY count DESC
        """)
        category_stats = cursor.fetchall()
    
    analytics_text = f"""
📊 *Detailed Analytics*

*Overall Stats:*
• Total Posts: {stats['total_posts']}
• Total Comments: {stats['total_comments']}
• Total Users: {stats['total_users']}
• Total Reactions: {stats['total_reactions']}

*User Trends \\(7 days\\):*
"""
    
    if user_trends:
        for day, count in user_trends[:3]:
            analytics_text += f"• {escape_markdown_text(str(day))}: {count} new users\n"
    else:
        analytics_text += "• No new users in the last 7 days\n"
    
    analytics_text += "\n*Post Activity \\(7 days\\):*\n"
    if post_trends:
        for day, count in post_trends[:3]:
            analytics_text += f"• {escape_markdown_text(str(day))}: {count} posts\n"
    else:
        analytics_text += "• No posts approved in the last 7 days\n"
    
    analytics_text += "\n*Top Categories:*\n"
    if category_stats:
        for category, count in category_stats[:5]:
            analytics_text += f"• {escape_markdown_text(str(category))}: {count} posts\n"
    
    analytics_text += "\n*Most Active Users:*\n"
    if top_users:
        for i, (name, username, confessions, comments, total) in enumerate(top_users, 1):
            display_name = name or username or "Anonymous"
            analytics_text += f"{i}\\. {escape_markdown_text(display_name)}: {total} activities\n"
    
    keyboard = [
        [
            InlineKeyboardButton("📈 Export Data", callback_data="admin_export"),
            InlineKeyboardButton("🔄 Refresh", callback_data="admin_analytics")
        ],
        [
            InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        analytics_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_user_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user management interface"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Get user statistics
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        
        # Total users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Active users (not blocked)
        cursor.execute("SELECT COUNT(*) FROM users WHERE blocked = 0")
        active_users = cursor.fetchone()[0]
        
        # Blocked users
        cursor.execute("SELECT COUNT(*) FROM users WHERE blocked = 1")
        blocked_users = cursor.fetchone()[0]
        
        # Recent users (last 24 hours) - database agnostic
        db_conn = get_db_connection()
        if db_conn.use_postgresql:
            cursor.execute("SELECT COUNT(*) FROM users WHERE join_date >= NOW() - INTERVAL '1 day'")
        else:
            # SQLite version
            cursor.execute("SELECT COUNT(*) FROM users WHERE join_date >= datetime('now', '-1 day')")
        recent_users = cursor.fetchone()[0]
    
    user_mgmt_text = f"""
👥 *User Management*

*User Statistics:*
• Total Users: {total_users}
• Active Users: {active_users}
• Blocked Users: {blocked_users}
• New Users \\(24h\\): {recent_users}

Choose an action:
"""
    
    keyboard = [
        [
            InlineKeyboardButton(f"👥 Active Users ({active_users})", callback_data="admin_active_users"),
            InlineKeyboardButton(f"⛔ Blocked Users ({blocked_users})", callback_data="admin_blocked_users")
        ],
        [
            InlineKeyboardButton("🔍 Search User", callback_data="admin_search_user"),
            InlineKeyboardButton("📊 User Analytics", callback_data="admin_user_analytics")
        ],
        [
            InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        user_mgmt_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show blocked users with unblock buttons"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, username, first_name, last_name, join_date, questions_asked, comments_posted
            FROM users WHERE blocked = 1 
            ORDER BY join_date DESC LIMIT 10
        """)
        blocked_users = cursor.fetchall()
    
    if not blocked_users:
        blocked_text = "✅ *No Blocked Users*\n\nAll users are currently active\\!"
        keyboard = [[InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            blocked_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        return
    
    blocked_text = f"⛔ *Blocked Users \\({len(blocked_users)} shown\\)*\n\n"
    keyboard = []
    
    for user_data in blocked_users:
        uid, username, first_name, last_name, join_date, questions_asked, comments_posted = user_data
        name = f"{first_name or ''} {last_name or ''}".strip() or username or "Anonymous"
        
        blocked_text += f"*User:* {escape_markdown_text(name)}\n"
        blocked_text += f"*ID:* `{uid}`\n"
        blocked_text += f"*Activity:* {questions_asked} posts, {comments_posted} comments\n"
        if join_date:
            formatted_date = join_date.strftime('%Y-%m-%d') if hasattr(join_date, 'strftime') else str(join_date)[:10]
            blocked_text += f"*Joined:* {escape_markdown_text(formatted_date)}\n"
        blocked_text += "\n"
        
        # Add unblock button for each user
        keyboard.append([
            InlineKeyboardButton(f"✅ Unblock {name[:15]}...", callback_data=f"admin_unblock_{uid}"),
            InlineKeyboardButton(f"👤 Info", callback_data=f"admin_user_info_{uid}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        blocked_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_active_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show active users with management options"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, username, first_name, last_name, join_date, questions_asked, comments_posted
            FROM users WHERE blocked = 0 
            ORDER BY (questions_asked + comments_posted) DESC LIMIT 15
        """)
        active_users = cursor.fetchall()
    
    active_text = f"👥 *Most Active Users \\({len(active_users)} shown\\)*\n\n"
    keyboard = []
    
    for i, user_data in enumerate(active_users, 1):
        uid, username, first_name, last_name, join_date, questions_asked, comments_posted = user_data
        name = f"{first_name or ''} {last_name or ''}".strip() or username or "Anonymous"
        total_activity = questions_asked + comments_posted
        
        active_text += f"{i}\\. *{escape_markdown_text(name)}*\n"
        active_text += f"   ID: `{uid}` \\| Activity: {total_activity}\n"
        if join_date:
            formatted_date = join_date.strftime('%Y-%m-%d') if hasattr(join_date, 'strftime') else str(join_date)[:10]
            active_text += f"   Joined: {escape_markdown_text(formatted_date)}\n"
        active_text += "\n"
        
        # Add management buttons for top users only
        if i <= 5:
            keyboard.append([
                InlineKeyboardButton(f"👤 {name[:10]}... Info", callback_data=f"admin_user_info_{uid}"),
                InlineKeyboardButton(f"⛔ Block", callback_data=f"admin_block_{uid}")
            ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        active_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

# Additional Admin Dashboard Handlers
async def admin_dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin dashboard callback"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Get quick stats
    stats = get_channel_stats()
    pending_posts = len(get_pending_submissions())
    pending_messages = len(get_pending_messages())
    
    dashboard_text = f"""
🔧 *Admin Dashboard*

*Quick Overview:*
• Total Posts: {stats['total_posts']}
• Total Users: {stats['total_users']}
• Pending Posts: {pending_posts}
• Pending Messages: {pending_messages}

Choose a section to manage:
"""
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Analytics", callback_data="admin_analytics"),
            InlineKeyboardButton("👥 User Management", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton("📝 Content Management", callback_data="admin_content"),
            InlineKeyboardButton("🚩 Reports & Moderation", callback_data="admin_moderation")
        ],
        [
            InlineKeyboardButton("💬 Messages", callback_data="admin_messages"),
            InlineKeyboardButton("⚙️ System Info", callback_data="admin_system")
        ],
        [
            InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        dashboard_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_unblock_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin unblock user button"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    target_user_id = int(query.data.replace("admin_unblock_", ""))
    
    try:
        from approval import unblock_user, is_blocked_user
        
        if not await async_is_blocked_user(target_user_id):
            await query.answer("❗ User is not blocked!")
            return
        
        unblock_user(target_user_id)
        await query.answer(f"✅ User {target_user_id} unblocked!")
        
        # Refresh the blocked users list
        await admin_blocked_users(update, context)
        
    except Exception as e:
        await query.answer(f"❗ Error: {str(e)}")

async def admin_block_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin block user button"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    target_user_id = int(query.data.replace("admin_block_", ""))
    
    try:
        from approval import block_user, is_blocked_user
        
        if await async_is_blocked_user(target_user_id):
            await query.answer("❗ User is already blocked!")
            return
        
        block_user(target_user_id)
        await query.answer(f"⛔ User {target_user_id} blocked!")
        
        # Refresh the active users list
        await admin_active_users(update, context)
        
    except Exception as e:
        await query.answer(f"❗ Error: {str(e)}")

async def admin_user_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed user information"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    target_user_id = int(query.data.replace("admin_user_info_", ""))
    
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        placeholder = db_conn.get_placeholder()
        cursor.execute(
            f"SELECT user_id, username, first_name, last_name, join_date, questions_asked, comments_posted, blocked FROM users WHERE user_id = {placeholder}",
            (target_user_id,)
        )
        user_data = cursor.fetchone()
        
        if not user_data:
            await query.answer("❗ User not found!")
            return
        
        uid, username, first_name, last_name, join_date, questions_asked, comments_posted, blocked = user_data
        
        status = "🚫 Blocked" if blocked else "✅ Active"
        name = f"{first_name or ''} {last_name or ''}".strip() or username or "Anonymous"
        
        # Get additional stats - count likes from comments table instead of non-existent comment_reactions table
        cursor.execute(
            f"SELECT COALESCE(SUM(likes), 0) FROM comments WHERE user_id = {placeholder}",
            (target_user_id,)
        )
        likes_received = cursor.fetchone()[0]
        
        user_text = f"""
👤 *User Information*

*Details:*
• Name: {escape_markdown_text(name)}
• ID: `{uid}`
• Username: {f"@{escape_markdown_text(username)}" if username else "None"}
• Status: {status}
• Joined: {escape_markdown_text(join_date.strftime('%Y-%m-%d %H:%M') if join_date and hasattr(join_date, 'strftime') else str(join_date)[:16] if join_date else "Unknown")}

*Activity:*
• Confessions Posted: {questions_asked}
• Comments Posted: {comments_posted}
• Likes Received: {likes_received}
• Total Activity: {questions_asked + comments_posted}
"""
        
        keyboard = [
            [
                InlineKeyboardButton(f"{'✅ Unblock' if blocked else '⛔ Block'}", 
                                   callback_data=f"admin_{'unblock' if blocked else 'block'}_{uid}")
            ],
            [
                InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            user_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
async def admin_pending_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending posts for approval"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    from submission import get_pending_submissions_with_media
    pending_posts = get_pending_submissions_with_media()
    
    if not pending_posts:
        await query.edit_message_text(
            "📋 *Pending Posts*\n\n✅ No posts pending approval!\n\nAll submissions have been reviewed.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")
            ]]),
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the menu and send header
    await query.delete_message()
    
    header_text = f"📋 *Pending Posts \\({len(pending_posts)}\\)*\n\n⏳ Posts waiting for review"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from utils import escape_markdown_text, truncate_text
    
    # Show each pending post
    for post in pending_posts:
        post_id = post[0]
        content = post[1]
        category = post[2]
        timestamp = post[3]
        user_id = post[4]
        
        # Extract media information from get_pending_submissions_with_media
        # [10]=media_type, [11]=media_file_id, [13]=media_caption
        media_type = post[10] if len(post) > 10 else None
        media_file_id = post[11] if len(post) > 11 else None
        media_caption = post[13] if len(post) > 13 else None
        
        # Check if this is an edited confession (is_edited field)
        is_edited = post[21] if len(post) > 21 else False  # Adjust index based on schema
        edited_badge = "✏️ *EDITED*\n\n" if is_edited else ""
        
        # Format timestamp
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_time = dt.strftime('%Y-%m-%d %H:%M')
            escaped_time = escape_markdown_text(formatted_time)
        except:
            escaped_time = escape_markdown_text("recently")
        
        post_text = f"*{escape_markdown_text(category)}*\n\n{edited_badge}{escape_markdown_text(truncate_text(content, 200))}\n\n"
        post_text += f"*ID:* \\#{post_id} \\| *User:* {user_id} \\| {escaped_time}"
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{post_id}"),
                InlineKeyboardButton("🔞 Approve 18+", callback_data=f"approve18_{post_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{post_id}")
            ],
            [
                InlineKeyboardButton("🚩 Flag", callback_data=f"flag_{post_id}"),
                InlineKeyboardButton("📖 Full Content", callback_data=f"view_full_post_{post_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # If it's a media post, send the media
        if media_type and media_file_id:
            try:
                # Prepare caption for media
                media_caption_text = f"📝 *Pending Review*\n\n{edited_badge}"
                media_caption_text += f"*{escape_markdown_text(category)}*\n\n"
                
                # Add content or media caption
                if content and content.strip():
                    media_caption_text += f"{escape_markdown_text(truncate_text(content, 200))}\n\n"
                elif media_caption and media_caption.strip():
                    media_caption_text += f"{escape_markdown_text(media_caption)}\n\n"
                
                media_caption_text += f"*ID:* \\#{post_id} \\| *User:* {user_id} \\| {escaped_time}"
                
                if media_type == 'photo':
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=media_file_id,
                        caption=media_caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif media_type == 'video':
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=media_file_id,
                        caption=media_caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                elif media_type == 'animation':
                    await context.bot.send_animation(
                        chat_id=update.effective_chat.id,
                        animation=media_file_id,
                        caption=media_caption_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
                else:
                    # Fallback to text for unsupported media types
                    logger.warning(f"Unsupported media type in pending posts: {media_type}")
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=post_text,
                        reply_markup=reply_markup,
                        parse_mode="MarkdownV2"
                    )
            except Exception as e:
                logger.error(f"Error sending pending media post {post_id}: {e}")
                # Fallback to text message
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=post_text,
                    reply_markup=reply_markup,
                    parse_mode="MarkdownV2"
                )
        else:
            # Send as text message for text-only confessions
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=post_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        
        await asyncio.sleep(0.1)
    
    # Send navigation
    nav_keyboard = [
        [InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    pending_posts = get_pending_submissions()
    
    if not pending_posts:
        pending_text = "✅ *No Pending Posts*\n\nAll submissions have been reviewed\\!"
        keyboard = [[InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            pending_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the current message and send individual pending posts
    try:
        await query.delete_message()
    except:
        pass
    
    # Send header
        header_text = f"📋 *Pending Posts \\({len(pending_posts)} total\\)*\n\nReview each submission below:"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from utils import escape_markdown_text
    
    # Send each pending post individually with approval buttons
    for post in pending_posts[:10]:  # Show first 10 pending posts
        post_id = post[0]
        content = post[1]  # content is at index 1
        category = post[2]  # category is at index 2
        timestamp = post[3]  # timestamp is at index 3
        user_id = post[4]  # user_id is at index 4
        
        # Format timestamp safely
        try:
            if isinstance(timestamp, str):
                formatted_time = timestamp[:16] if len(timestamp) >= 16 else str(timestamp)
            else:
                formatted_time = str(timestamp)
        except:
            formatted_time = "recently"
        
        # Format the post for admin review
        admin_text = f"""
📝 *New Confession Submission*

*ID:* {escape_markdown_text(f'#{post_id}')}
*Category:* {escape_markdown_text(category)}
*Submitter:* {user_id}
*Submitted:* {escape_markdown_text(formatted_time)}

*Content:*
{escape_markdown_text(content)}
"""

        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{post_id}"),
                InlineKeyboardButton("🔞 Approve 18+", callback_data=f"approve18_{post_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{post_id}")
            ],
            [
                InlineKeyboardButton("🚩 Flag", callback_data=f"flag_{post_id}"),
                InlineKeyboardButton("⛔ Block User", callback_data=f"block_{user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=admin_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
        # Small delay between posts (reduced for responsiveness)
        await asyncio.sleep(0.1)
    
    # Send navigation at the end
    nav_keyboard = [
        [InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_content_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show content management panel"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Get content stats
    pending_posts = len(get_pending_submissions())
    
    content_text = f"""
📝 *Content Management*

*Current Status:*
• Pending Posts: {pending_posts}
• Total Posts: Calculating\\.\\.\\.

Choose an action:
"""
    
    keyboard = [
        [
            InlineKeyboardButton(f"📋 Pending Posts \\({pending_posts}\\)", callback_data="admin_pending_posts"),
            InlineKeyboardButton("📰 Recent Posts", callback_data="admin_recent_posts")
        ],
        [
            InlineKeyboardButton("📆 Content Analytics", callback_data="admin_content_stats"),
            InlineKeyboardButton("🗑️ Content Cleanup", callback_data="admin_content_cleanup")
        ],
        [
            InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        content_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_moderation_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show moderation panel"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    from moderation import get_reports
    reports = get_reports()
    report_count = len(reports)
    
    moderation_text = f"""
🚩 *Reports \\& Moderation*

*Current Status:*
• Active Reports: {report_count}
• Auto\\-moderation: Active

Choose an action:
"""
    
    keyboard = [
        [
            InlineKeyboardButton(f"🚩 View Reports \\({report_count}\\)", callback_data="admin_view_reports"),
            InlineKeyboardButton("📊 Moderation Stats", callback_data="admin_mod_stats")
        ],
        [
            InlineKeyboardButton("🔧 Moderation Settings", callback_data="admin_mod_settings"),
            InlineKeyboardButton("📜 Audit Log", callback_data="admin_audit_log")
        ],
        [
            InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        moderation_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_messages_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show messages management panel"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    pending_messages = len(get_pending_messages())
    
    messages_text = f"""
💬 *Message Management*

*Current Status:*
• Pending Messages: {pending_messages}
• Auto\\-replies: Disabled

Choose an action:
"""
    
    keyboard = [
        [
            InlineKeyboardButton(f"📨 Pending Messages \\({pending_messages}\\)", callback_data="admin_pending_messages"),
            InlineKeyboardButton("📜 Message History", callback_data="admin_message_history")
        ],
        [
            InlineKeyboardButton("🤖 Auto-Reply Settings", callback_data="admin_auto_reply"),
            InlineKeyboardButton("📊 Message Stats", callback_data="admin_message_stats")
        ],
        [
            InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        messages_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_system_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system information panel"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    import os
    from datetime import datetime
    
    try:
        # Get database size
        db_size = os.path.getsize(DB_PATH) / (1024 * 1024)  # MB
        
        # Get basic system info
        system_text = f"""
⚙️ *System Information*

*Bot Status:*
• Status: ✅ Running
• Database: Connected
• Database Size: {db_size:.1f} MB

*System:*
• Platform: {escape_markdown_text(os.name)}
• Python: Active

*Last Updated:* {escape_markdown_text(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}
"""
    except Exception as e:
        system_text = f"""
⚙️ *System Information*

*Bot Status:*
• Status: ✅ Running
• Database: Connected
• Error getting system stats: {escape_markdown_text(str(e))}

*Last Updated:* {escape_markdown_text(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="admin_system"),
            InlineKeyboardButton("🗄️ Database Stats", callback_data="admin_db_stats")
        ],
        [
            InlineKeyboardButton("📊 Bot Stats", callback_data="admin_analytics"),
            InlineKeyboardButton("💾 Backup Info", callback_data="admin_backup_info")
        ],
        [
            InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_dashboard")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        system_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

# Add handlers for missing admin panel callbacks and reporting system functionality
async def admin_recent_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent approved posts with admin management options"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Get recent approved posts
    db_conn = get_db_connection()
    with db_conn.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.post_id, p.content, p.category, p.timestamp, p.user_id,
                   COUNT(c.comment_id) as comment_count,
                   p.post_id as display_number
            FROM posts p
            LEFT JOIN comments c ON p.post_id = c.post_id
            WHERE p.approved = 1
            GROUP BY p.post_id, p.content, p.category, p.timestamp, p.user_id
            ORDER BY p.timestamp DESC
            LIMIT 15
        """)
        recent_posts = cursor.fetchall()
    
    if not recent_posts:
        await query.edit_message_text(
            "📰 *Recent Posts*\n\n✅ No approved posts found!\n\nAll posts are still pending approval.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")
            ]]),
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the menu and send header
    await query.delete_message()
    
    header_text = f"📰 *Recent Approved Posts \\({len(recent_posts)}\\)*\n\n📋 Posts available for admin management"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from utils import escape_markdown_text, truncate_text
    
    # Show each recent post
    for post in recent_posts:
        post_id = post[0]
        content = post[1]
        category = post[2]
        timestamp = post[3]
        submitter_id = post[4]
        comment_count = post[5]
        display_number = post[6]
        
        # Format timestamp
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_time = dt.strftime('%Y-%m-%d %H:%M')
            escaped_time = escape_markdown_text(formatted_time)
        except:
            escaped_time = escape_markdown_text("recently")
        
        post_text = f"*{escape_markdown_text(category)}*\n\n{escape_markdown_text(truncate_text(content, 200))}\n\n"
        post_text += f"*ID:* \\#{display_number} \\| *Submitter:* {submitter_id} \\| *Comments:* {comment_count} \\| {escaped_time}"
        
        keyboard = [
            [
                InlineKeyboardButton("👀 View Full Post", callback_data=f"view_post_{post_id}"),
                InlineKeyboardButton(f"💬 See Comments \\({comment_count}\\)", callback_data=f"see_comments_{post_id}_1")
            ],
            [
                InlineKeyboardButton("🗑️ Delete Post", callback_data=f"admin_delete_post_{post_id}"),
                InlineKeyboardButton("⛔ Block Author", callback_data=f"admin_block_{submitter_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=post_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
        await asyncio.sleep(0.1)
    
    # Send navigation
    nav_keyboard = [
        [InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_content_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show content statistics"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        # Get comprehensive content statistics from database
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total posts statistics
            cursor.execute("SELECT COUNT(*) FROM posts")
            total_posts = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts WHERE approved = 1")
            approved_posts = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts WHERE approved = 0")
            rejected_posts = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts WHERE approved IS NULL")
            pending_posts = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts WHERE flagged = 1")
            flagged_posts = cursor.fetchone()[0]
            
            # Comments statistics
            cursor.execute("SELECT COUNT(*) FROM comments")
            total_comments = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM comments WHERE flagged = 1")
            flagged_comments = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM comment_reactions")
            total_reactions = cursor.fetchone()[0]
            
            # Category breakdown
            cursor.execute("""
                SELECT category, COUNT(*) as count 
                FROM posts 
                WHERE approved = 1
                GROUP BY category 
                ORDER BY count DESC
                LIMIT 10
            """)
            top_categories = cursor.fetchall()
            
            # Daily content trends (last 7 days)
            cursor.execute("""
                SELECT DATE(timestamp) as day, 
                       COUNT(*) as posts_count,
                       SUM(CASE WHEN approved = 1 THEN 1 ELSE 0 END) as approved_count
                FROM posts 
                WHERE timestamp >= DATE('now', '-7 days') 
                GROUP BY DATE(timestamp) 
                ORDER BY day DESC
            """)
            daily_trends = cursor.fetchall()
            
            # Most active posts by comment count
            cursor.execute("""
                SELECT p.id, p.content, p.category, COUNT(c.id) as comment_count,
                       COALESCE(p.post_number, p.id) as display_number
                FROM posts p
                LEFT JOIN comments c ON p.id = c.post_id
                WHERE p.approved = 1
                GROUP BY p.id, p.content, p.category, p.post_number
                ORDER BY comment_count DESC
                LIMIT 5
            """)
            most_commented = cursor.fetchall()
            
            # Content engagement metrics
            cursor.execute("""
                SELECT 
                    AVG(comment_count) as avg_comments_per_post,
                    MAX(comment_count) as max_comments,
                    AVG(reaction_count) as avg_reactions_per_comment
                FROM (
                    SELECT p.id, COUNT(c.id) as comment_count,
                           COALESCE(AVG(COALESCE(cr.total_reactions, 0)), 0) as reaction_count
                    FROM posts p
                    LEFT JOIN comments c ON p.id = c.post_id
                    LEFT JOIN (
                        SELECT comment_id, COUNT(*) as total_reactions
                        FROM comment_reactions
                        GROUP BY comment_id
                    ) cr ON c.id = cr.comment_id
                    WHERE p.approved = 1
                    GROUP BY p.id
                )
            """)
            engagement = cursor.fetchone()
            avg_comments = engagement[0] if engagement[0] else 0
            max_comments = engagement[1] if engagement[1] else 0
            avg_reactions = engagement[2] if engagement[2] else 0
            
            # Content quality metrics
            approval_rate = (approved_posts / total_posts * 100) if total_posts > 0 else 0
            engagement_rate = (total_comments / approved_posts) if approved_posts > 0 else 0
    
        # Build the content statistics text
        content_stats_text = f"""
📊 *Content Analytics*

*Overall Statistics:*
• Total Posts Submitted: {total_posts}
• Approved Posts: {approved_posts}
• Rejected Posts: {rejected_posts}
• Pending Posts: {pending_posts}
• Approval Rate: {approval_rate:.1f}%

*Content Health:*
• Flagged Posts: {flagged_posts}
• Flagged Comments: {flagged_comments}
• Total Comments: {total_comments}
• Total Reactions: {total_reactions}

*Engagement Metrics:*
• Avg Comments per Post: {avg_comments:.1f}
• Most Comments on a Post: {max_comments}
• Avg Reactions per Comment: {avg_reactions:.1f}
• Engagement Rate: {engagement_rate:.1f} comments\\/post

*Top Categories:*
"""
        
        if top_categories:
            for category, count in top_categories[:5]:
                percentage = (count / approved_posts * 100) if approved_posts > 0 else 0
                content_stats_text += f"• {escape_markdown_text(str(category))}: {count} posts \\({percentage:.1f}%\\)\n"
        else:
            content_stats_text += "• No approved posts yet\n"
        
        content_stats_text += "\n*Daily Trends \\(7 days\\):*\n"
        if daily_trends:
            for day, total, approved in daily_trends[:5]:
                approval_rate_daily = (approved / total * 100) if total > 0 else 0
                content_stats_text += f"• {escape_markdown_text(str(day))}: {total} submitted, {approved} approved \\({approval_rate_daily:.0f}%\\)\n"
        else:
            content_stats_text += "• No posts in the last 7 days\n"
        
        content_stats_text += "\n*Most Active Posts:*\n"
        if most_commented:
            for post_id, content, category, comment_count, display_number in most_commented:
                preview = truncate_text(content, 40)
                content_stats_text += f"• \\#{display_number} \\({escape_markdown_text(category)}\\): {comment_count} comments\n"
        else:
            content_stats_text += "• No posts with comments yet\n"
        
        keyboard = [
            [
                InlineKeyboardButton("📰 Recent Posts", callback_data="admin_recent_posts"),
                InlineKeyboardButton("🔄 Refresh", callback_data="admin_content_stats")
            ],
            [
                InlineKeyboardButton("📋 Pending Posts", callback_data="admin_pending_posts"),
                InlineKeyboardButton("🗑️ Content Cleanup", callback_data="admin_content_cleanup")
            ],
            [
                InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            content_stats_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_content_stats: {e}")
        await query.edit_message_text(
            "📊 *Content Analytics*\n\n❌ Error loading content statistics\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_content_cleanup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show content cleanup options"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Placeholder response until feature is implemented
    await query.edit_message_text(
        "🗑️ *Content Cleanup*\n\nThis feature is currently under development\\. \n\nPlease check back later\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Content Management", callback_data="admin_content")
        ]]),
        parse_mode="MarkdownV2"
    )

async def admin_view_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed reports for moderation"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    from moderation import get_reports, get_content_details
    reports = get_reports()
    
    if not reports:
        await query.edit_message_text(
            "🚩 *Reports & Moderation*\n\n✅ No active reports!\n\nAll content is clean at the moment.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Moderation Panel", callback_data="admin_moderation")
            ]]),
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the menu and send header
    await query.delete_message()
    
    # Group reports by target for better organization
    from collections import defaultdict
    reports_by_target = defaultdict(list)
    
    for report in reports:
        report_id, user_id, target_type, target_id, reason, timestamp = report
        reports_by_target[(target_type, target_id)].append(report)
    
    header_text = f"🚩 *Active Reports \\({len(reports)} total\\)*\n\n⚠️ Reported content requiring review"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from utils import escape_markdown_text, truncate_text
    
    # Show each reported target
    for (target_type, target_id), target_reports in list(reports_by_target.items())[:10]:  # Show first 10
        report_count = len(target_reports)
        first_report = target_reports[0]
        
        # Get content details
        content_details = get_content_details(target_type, target_id)
        
        if content_details:
            if target_type == 'comment':
                comment_id, post_id, content, timestamp = content_details
                
                report_text = f"📝 *Reported Comment*\n\n"
                report_text += f"*Comment ID:* \\#{comment_id} \\(Post \\#{post_id}\\)\n"
                report_text += f"*Reports:* {report_count}\n"
                report_text += f"*Time:* {escape_markdown_text(timestamp[:16])}\n\n"
                report_text += f"*Content:*\n{escape_markdown_text(truncate_text(content, 200))}\n"
                
                keyboard = [
                    [
                        InlineKeyboardButton("🗑️ Delete Comment", callback_data=f"admin_delete_comment_{comment_id}"),
                        InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_comment_{comment_id}")
                    ],
                    [
                        InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}"),
                        InlineKeyboardButton("👀 See Comments", callback_data=f"see_comments_{post_id}_1")
                    ],
                    [
                        InlineKeyboardButton("🔇 Clear Reports", callback_data=f"admin_clear_reports_comment_{comment_id}")
                    ]
                ]
                
            else:  # post
                post_id, content, category, timestamp = content_details
                
                report_text = f"📝 *Reported Post*\n\n"
                report_text += f"*Post ID:* \\#{post_id}\n"
                report_text += f"*Category:* {escape_markdown_text(category)}\n"
                report_text += f"*Reports:* {report_count}\n"
                report_text += f"*Time:* {escape_markdown_text(timestamp[:16])}\n\n"
                report_text += f"*Content:*\n{escape_markdown_text(truncate_text(content, 200))}\n"
                
                keyboard = [
                    [
                        InlineKeyboardButton("🗑️ Delete Post", callback_data=f"admin_delete_post_{post_id}"),
                        InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_post_{post_id}")
                    ],
                    [
                        InlineKeyboardButton("📖 View Full Post", callback_data=f"view_post_{post_id}"),
                        InlineKeyboardButton("👀 See Comments", callback_data=f"see_comments_{post_id}_1")
                    ],
                    [
                        InlineKeyboardButton("🔇 Clear Reports", callback_data=f"admin_clear_reports_post_{post_id}")
                    ]
                ]
        else:
            # Content not found
            report_text = f"❓ *Missing {target_type.title()}*\n\n"
            report_text += f"*{target_type.title()} ID:* \\#{target_id}\n"
            report_text += f"*Reports:* {report_count}\n\n"
            report_text += f"Content has been deleted or is no longer available\\."
            
            keyboard = [
                [
                    InlineKeyboardButton("🔇 Clear Reports", callback_data=f"admin_clear_reports_{target_type}_{target_id}")
                ]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=report_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
        await asyncio.sleep(0.1)
    
    # Send navigation
    nav_keyboard = [
        [InlineKeyboardButton("🔙 Back to Moderation Panel", callback_data="admin_moderation")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_mod_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show moderation statistics"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        from moderation import get_reports
        reports = get_reports()
        
        # Get detailed moderation statistics from database
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Total reports
            cursor.execute("SELECT COUNT(*) FROM reports")
            total_reports = cursor.fetchone()[0]
            
            # Report types breakdown
            cursor.execute("""
                SELECT target_type, COUNT(*) as count 
                FROM reports 
                GROUP BY target_type
            """)
            report_types = cursor.fetchall()
            
            # Recent moderation activity (last 7 days)
            cursor.execute("""
                SELECT DATE(timestamp) as day, COUNT(*) as reports 
                FROM reports 
                WHERE timestamp >= DATE('now', '-7 days') 
                GROUP BY DATE(timestamp) 
                ORDER BY day DESC
            """)
            recent_reports = cursor.fetchall()
            
            # Most reported content
            cursor.execute("""
                SELECT target_type, target_id, COUNT(*) as report_count
                FROM reports 
                GROUP BY target_type, target_id 
                ORDER BY report_count DESC 
                LIMIT 5
            """)
            most_reported = cursor.fetchall()
            
            # Blocked users count
            cursor.execute("SELECT COUNT(*) FROM users WHERE blocked = 1")
            blocked_users_count = cursor.fetchone()[0]
            
            # Flagged posts/comments
            cursor.execute("SELECT COUNT(*) FROM posts WHERE flagged = 1")
            flagged_posts = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM comments WHERE flagged = 1")
            flagged_comments = cursor.fetchone()[0]
            
            # Total moderation actions (approvals + rejections)
            cursor.execute("SELECT COUNT(*) FROM posts WHERE approved IS NOT NULL")
            total_decisions = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts WHERE approved = 1")
            approved_posts = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts WHERE approved = 0")
            rejected_posts = cursor.fetchone()[0]
    
        # Build the statistics text
        mod_stats_text = f"""
📊 *Moderation Statistics*

*Overall Activity:*
• Total Reports: {total_reports}
• Active Reports: {len(reports)}
• Blocked Users: {blocked_users_count}
• Flagged Posts: {flagged_posts}
• Flagged Comments: {flagged_comments}

*Post Decisions:*
• Total Decisions: {total_decisions}
• Approved: {approved_posts}
• Rejected: {rejected_posts}
• Approval Rate: {(approved_posts/total_decisions*100):.1f if total_decisions > 0 else 0:.1f}%

*Report Types:*
"""
        
        if report_types:
            for report_type, count in report_types:
                mod_stats_text += f"• {report_type.title()}: {count}\n"
        else:
            mod_stats_text += "• No reports yet\n"
        
        mod_stats_text += "\n*Recent Activity \\(7 days\\):*\n"
        if recent_reports:
            for day, count in recent_reports[:5]:
                mod_stats_text += f"• {escape_markdown_text(str(day))}: {count} reports\n"
        else:
            mod_stats_text += "• No recent reports\n"
        
        mod_stats_text += "\n*Most Reported Content:*\n"
        if most_reported:
            for target_type, target_id, count in most_reported:
                mod_stats_text += f"• {target_type.title()} \\#{target_id}: {count} reports\n"
        else:
            mod_stats_text += "• No heavily reported content\n"
        
        keyboard = [
            [
                InlineKeyboardButton("📊 View Reports", callback_data="admin_view_reports"),
                InlineKeyboardButton("🔄 Refresh", callback_data="admin_mod_stats")
            ],
            [
                InlineKeyboardButton("🔙 Back to Moderation Panel", callback_data="admin_moderation")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            mod_stats_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_mod_stats: {e}")
        await query.edit_message_text(
            "📊 *Moderation Statistics*\n\n❌ Error loading statistics\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Moderation Panel", callback_data="admin_moderation")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_mod_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show moderation settings"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Placeholder response until feature is implemented
    await query.edit_message_text(
        "🔧 *Moderation Settings*\n\nThis feature is currently under development\\. \n\nPlease check back later\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Moderation Panel", callback_data="admin_moderation")
        ]]),
        parse_mode="MarkdownV2"
    )

async def admin_audit_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show audit log"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Placeholder response until feature is implemented
    await query.edit_message_text(
        "📜 *Audit Log*\n\nThis feature is currently under development\\. \n\nPlease check back later\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Moderation Panel", callback_data="admin_moderation")
        ]]),
        parse_mode="MarkdownV2"
    )

async def admin_pending_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending user messages"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    pending_messages = get_pending_messages()
    
    if not pending_messages:
        await query.edit_message_text(
            "📨 *Pending Messages*\n\n✅ No pending user messages!\n\nAll messages have been handled.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Message Management", callback_data="admin_messages")
            ]]),
            parse_mode="MarkdownV2"
        )
        return
    
    # Delete the menu and send header
    await query.delete_message()
    
    header_text = f"📋 *Pending Messages \\({len(pending_messages)}\\)*\n\n💌 User messages awaiting response"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=header_text,
        parse_mode="MarkdownV2"
    )
    
    import asyncio
    from utils import escape_markdown_text, truncate_text
    
    # Show each pending message
    for message in pending_messages:
        message_id, sender_user_id, message_content, timestamp = message
        
        # Format timestamp
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_time = dt.strftime('%Y-%m-%d %H:%M')
            escaped_time = escape_markdown_text(formatted_time)
        except:
            escaped_time = escape_markdown_text("recently")
        
        message_text = f"*Message ID:* \\#{message_id}\n"
        message_text += f"*From User:* {sender_user_id}\n"
        message_text += f"*Time:* {escaped_time}\n\n"
        message_text += f"*Content:*\n{escape_markdown_text(truncate_text(message_content, 300))}\n"
        
        keyboard = [
            [
                InlineKeyboardButton("💬 Quick Reply", callback_data=f"admin_reply_{message_id}"),
                InlineKeyboardButton("📋 View History", callback_data=f"admin_history_{sender_user_id}")
            ],
            [
                InlineKeyboardButton("✅ Mark Read", callback_data=f"admin_read_{message_id}"),
                InlineKeyboardButton("🔇 Ignore User", callback_data=f"admin_ignore_{sender_user_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
        await asyncio.sleep(0.1)
    
    # Send navigation
    nav_keyboard = [
        [InlineKeyboardButton("🔙 Back to Message Management", callback_data="admin_messages")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    nav_reply_markup = InlineKeyboardMarkup(nav_keyboard)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📋 *Navigation*",
        reply_markup=nav_reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_message_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show message history"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Placeholder response until feature is implemented
    await query.edit_message_text(
        "📜 *Message History*\n\nThis feature is currently under development\\. \n\nPlease check back later\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Message Management", callback_data="admin_messages")
        ]]),
        parse_mode="MarkdownV2"
    )

async def admin_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show auto-reply settings"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Placeholder response until feature is implemented
    await query.edit_message_text(
        "🤖 *Auto\\-Reply Settings*\n\nThis feature is currently under development\\. \n\nPlease check back later\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Message Management", callback_data="admin_messages")
        ]]),
        parse_mode="MarkdownV2"
    )

async def admin_message_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show message statistics"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Placeholder response until feature is implemented
    await query.edit_message_text(
        "📊 *Message Statistics*\n\nThis feature is currently under development\\. \n\nPlease check back later\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to Message Management", callback_data="admin_messages")
        ]]),
        parse_mode="MarkdownV2"
    )

async def admin_db_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show database statistics"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get basic table counts
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts")
            total_posts = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM comments")
            total_comments = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM reactions")
            total_reactions = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM reports")
            total_reports = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM admin_messages")
            total_admin_messages = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM user_rankings")
            total_rankings = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM point_transactions")
            total_transactions = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM user_achievements")
            total_achievements = cursor.fetchone()[0]
        
        # Get database size
        import os
        try:
            db_size = os.path.getsize(DB_PATH) / (1024 * 1024)  # Convert to MB
            db_size_str = f"{db_size:.2f} MB"
        except:
            db_size_str = "Unknown"
        
        # Get active users (users with activity in last 30 days)
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) 
            FROM (
                SELECT user_id FROM posts WHERE datetime(timestamp) > datetime('now', '-30 days')
                UNION
                SELECT user_id FROM comments WHERE datetime(timestamp) > datetime('now', '-30 days')
                UNION
                SELECT user_id FROM reactions WHERE datetime(timestamp) > datetime('now', '-30 days')
            )
        """)
        active_users = cursor.fetchone()[0]
        
        # Get blocked users count
        cursor.execute("SELECT COUNT(*) FROM users WHERE blocked = 1")
        blocked_users = cursor.fetchone()[0]
        
        # Get storage breakdown
        cursor.execute("SELECT COUNT(*) FROM posts WHERE approved = 1")
        approved_posts = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM posts WHERE approved = 0")
        rejected_posts = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM posts WHERE approved IS NULL")
        pending_posts = cursor.fetchone()[0]
        
        # Get recent activity (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) FROM posts 
            WHERE datetime(timestamp) > datetime('now', '-1 day')
        """)
        posts_24h = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM comments 
            WHERE datetime(timestamp) > datetime('now', '-1 day')
        """)
        comments_24h = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM reactions 
            WHERE datetime(timestamp) > datetime('now', '-1 day')
        """)
        reactions_24h = cursor.fetchone()[0]
        
        # Get top categories by post count
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM posts 
            GROUP BY category 
            ORDER BY count DESC 
            LIMIT 3
        """)
        top_categories = cursor.fetchall()
        
        # Get average engagement
        cursor.execute("""
            SELECT 
                ROUND(AVG(comment_count), 1) as avg_comments,
                ROUND(AVG(reaction_count), 1) as avg_reactions
            FROM (
                SELECT 
                    p.post_id,
                    COUNT(DISTINCT c.comment_id) as comment_count,
                    COUNT(DISTINCT r.reaction_id) as reaction_count
                FROM posts p
                LEFT JOIN comments c ON p.post_id = c.post_id
                LEFT JOIN reactions r ON r.target_type = 'post' AND r.target_id = p.post_id
                WHERE p.approved = 1
                GROUP BY p.post_id
            )
        """)
        engagement_stats = cursor.fetchone()
        avg_comments = engagement_stats[0] if engagement_stats[0] else 0
        avg_reactions = engagement_stats[1] if engagement_stats[1] else 0
        
        
        # Format statistics message
        message_text = "🗄️ *Database Statistics*\n\n"
        
        # Table counts section
        message_text += "📊 *Table Records*\n"
        message_text += f"👥 Users: `{total_users:,}`\n"
        message_text += f"📝 Posts: `{total_posts:,}`\n"
        message_text += f"💬 Comments: `{total_comments:,}`\n"
        message_text += f"❤️ Reactions: `{total_reactions:,}`\n"
        message_text += f"⚠️ Reports: `{total_reports:,}`\n"
        message_text += f"📨 Admin Messages: `{total_admin_messages:,}`\n"
        message_text += f"🏆 User Rankings: `{total_rankings:,}`\n"
        message_text += f"💰 Point Transactions: `{total_transactions:,}`\n"
        message_text += f"🎖️ Achievements: `{total_achievements:,}`\n\n"
        
        # Database info section
        message_text += "💽 *Database Info*\n"
        message_text += f"📂 File Size: `{db_size_str}`\n"
        message_text += f"👤 Active Users \\(30d\\): `{active_users:,}`\n"
        message_text += f"🚫 Blocked Users: `{blocked_users:,}`\n\n"
        
        # Content breakdown
        message_text += "📈 *Content Breakdown*\n"
        message_text += f"✅ Approved Posts: `{approved_posts:,}`\n"
        message_text += f"❌ Rejected Posts: `{rejected_posts:,}`\n"
        message_text += f"⏳ Pending Posts: `{pending_posts:,}`\n\n"
        
        # Recent activity
        message_text += "🕐 *Last 24 Hours*\n"
        message_text += f"📝 New Posts: `{posts_24h:,}`\n"
        message_text += f"💬 New Comments: `{comments_24h:,}`\n"
        message_text += f"❤️ New Reactions: `{reactions_24h:,}`\n\n"
        
        # Top categories
        if top_categories:
            message_text += "🏷️ *Top Categories*\n"
            for i, (category, count) in enumerate(top_categories[:3], 1):
                escaped_category = escape_markdown_text(category)
                message_text += f"{i}\\. {escaped_category}: `{count:,}`\n"
            message_text += "\n"
        
        # Engagement metrics
        message_text += "📊 *Engagement Metrics*\n"
        message_text += f"💬 Avg Comments\\/Post: `{avg_comments}`\n"
        message_text += f"❤️ Avg Reactions\\/Post: `{avg_reactions}`\n\n"
        
        # Performance indicators
        if total_posts > 0:
            approval_rate = (approved_posts / total_posts) * 100
            message_text += "⚡ *Performance*\n"
            message_text += f"✅ Approval Rate: `{approval_rate:.1f}%`\n"
            
            if total_users > 0:
                posts_per_user = total_posts / total_users
                message_text += f"📈 Posts per User: `{posts_per_user:.1f}`\n"
        
        # Create navigation keyboard
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="admin_db_stats"),
                InlineKeyboardButton("📋 Table Info", callback_data="admin_table_info")
            ],
            [
                InlineKeyboardButton("🛠️ Maintenance", callback_data="admin_db_maintenance"),
                InlineKeyboardButton("💾 Backup Info", callback_data="admin_backup_info")
            ],
            [InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_db_stats: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to retrieve database statistics\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_backup_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show backup information"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        from backup_system import get_backup_status, backup_manager
        
        # Get backup system status and statistics
        status = get_backup_status()
        recent_backups = backup_manager.list_backups(limit=5)
        
        # Format backup information message
        message_text = "💾 *Backup Information*\n\n"
        
        # Backup system status
        auto_status = "✅ Enabled" if status.get('auto_backup_enabled', False) else "❌ Disabled"
        running_status = "🏃 Running" if status.get('is_running', False) else "⏸️ Stopped"
        
        message_text += "⚙️ *System Status*\n"
        message_text += f"🤖 Auto Backup: {auto_status}\n"
        message_text += f"🔄 Scheduler: {running_status}\n"
        message_text += f"⏰ Interval: `{status.get('backup_interval_hours', 'N/A')} hours`\n"
        message_text += f"📂 Directory: `{escape_markdown_text(status.get('backup_directory', 'N/A'))}`\n\n"
        
        # Backup statistics
        total_backups = status.get('total_backups', 0)
        total_size_mb = status.get('total_size_mb', 0)
        
        message_text += "📊 *Backup Statistics*\n"
        message_text += f"📁 Total Backups: `{total_backups:,}`\n"
        message_text += f"💾 Total Size: `{total_size_mb:.2f} MB`\n"
        
        if status.get('latest_backup'):
            try:
                from datetime import datetime
                if isinstance(status['latest_backup'], str):
                    latest_dt = datetime.fromisoformat(status['latest_backup'])
                else:
                    latest_dt = status['latest_backup']
                latest_formatted = latest_dt.strftime('%Y-%m-%d %H:%M:%S')
                escaped_latest = escape_markdown_text(latest_formatted)
                message_text += f"🕒 Latest Backup: {escaped_latest}\n"
            except:
                message_text += f"🕒 Latest Backup: {escape_markdown_text(str(status['latest_backup']))}\n"
        else:
            message_text += "🕒 Latest Backup: None\n"
        
        if status.get('oldest_backup'):
            try:
                from datetime import datetime
                if isinstance(status['oldest_backup'], str):
                    oldest_dt = datetime.fromisoformat(status['oldest_backup'])
                else:
                    oldest_dt = status['oldest_backup']
                oldest_formatted = oldest_dt.strftime('%Y-%m-%d')
                escaped_oldest = escape_markdown_text(oldest_formatted)
                message_text += f"📅 Oldest Backup: {escaped_oldest}\n\n"
            except:
                message_text += f"📅 Oldest Backup: {escape_markdown_text(str(status['oldest_backup']))}\n\n"
        else:
            message_text += "📅 Oldest Backup: None\n\n"
        
        # Recent backups list
        if recent_backups:
            message_text += "🗃 *Recent Backups*\n"
            for i, backup in enumerate(recent_backups, 1):
                filename = backup['filename']
                size_mb = backup['size'] / (1024 * 1024)
                
                try:
                    if isinstance(backup['created'], str):
                        created_dt = datetime.fromisoformat(backup['created'])
                    else:
                        created_dt = backup['created']
                    created_str = created_dt.strftime('%m-%d %H:%M')
                    escaped_created = escape_markdown_text(created_str)
                except:
                    escaped_created = "Unknown"
                
                backup_type = backup.get('backup_type', 'unknown')
                type_emoji = "🔄" if backup_type == "auto" else "👤" if backup_type == "manual" else "❓"
                
                message_text += f"{i}\\. {type_emoji} `{size_mb:.1f}MB` \\| {escaped_created}\n"
                
                # Show record count if available
                if 'record_count' in backup:
                    message_text += f"   Records: `{backup['record_count']:,}`\n"
            
            message_text += "\n"
        else:
            message_text += "🗃 *No backups found*\n\n"
        
        # Backup health indicators
        message_text += "❤️ *Health Status*\n"
        if total_backups == 0:
            message_text += "⚠️ No backups available\n"
            message_text += "🚨 **Recommendation:** Create a backup now\n\n"
        elif total_backups < 3:
            message_text += "⚠️ Low backup count\n"
            message_text += "🚨 **Recommendation:** Consider more frequent backups\n\n"
        else:
            message_text += "✅ Healthy backup coverage\n"
            message_text += "✨ Regular backups are being maintained\n\n"
        
        # Current database info
        try:
            import os
            current_size = os.path.getsize(DB_PATH) / (1024 * 1024)  # Convert to MB
            message_text += "📋 *Current Database*\n"
            message_text += f"📂 Size: `{current_size:.2f} MB`\n"
            
            # Check if database is accessible
            try:
                db_conn = get_db_connection()
                with db_conn.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                    table_count = cursor.fetchone()[0]
                    message_text += f"🗄️ Tables: `{table_count}`\n"
                    message_text += "🟢 Status: Accessible\n"
            except:
                message_text += "🔴 Status: Connection error\n"
        
        except Exception as e:
            message_text += f"📋 *Current Database*\n🔴 Error: {escape_markdown_text(str(e))}\n"
        
        # Create navigation keyboard
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="admin_backup_info"),
                InlineKeyboardButton("💾 Create Backup", callback_data="admin_create_backup")
            ],
            [
                InlineKeyboardButton("🗃 View All Backups", callback_data="admin_list_backups"),
                InlineKeyboardButton("🧠 Cleanup Old", callback_data="admin_cleanup_backups")
            ],
            [
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_backup_info: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to retrieve backup information\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user search interface with options"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    search_text = f"""
🔍 *User Search*

Search for users using different criteria:

*Available Search Options:*
• 🆔 Search by User ID \\(exact match\\)
• 👤 Search by Username \\(partial match\\)
• 🔤 Search by Name Starting Letter
• 📝 General Name Search \\(all fields\\)
• 📊 View Recent Users
• ⚡ View Most Active Users

Choose a search method below:
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🆔 Search by ID", callback_data="search_user_by_id"),
            InlineKeyboardButton("👤 Search by Username", callback_data="search_user_by_username")
        ],
        [
            InlineKeyboardButton("🔤 By Name Letter", callback_data="search_user_by_letter"),
            InlineKeyboardButton("📝 General Search", callback_data="search_user_general")
        ],
        [
            InlineKeyboardButton("📊 Recent Users", callback_data="search_user_recent"),
            InlineKeyboardButton("⚡ Most Active", callback_data="search_user_active")
        ],
        [
            InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        search_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def admin_user_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user analytics"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Placeholder response until feature is implemented
    await query.edit_message_text(
        "📊 *User Analytics*\n\nThis feature is currently under development\\. \n\nPlease check back later\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
        ]]),
        parse_mode="MarkdownV2"
    )

# User Search Callback Handlers
async def search_user_by_id_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search by ID - prompt admin to enter user ID"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    context.user_data['admin_search_mode'] = 'by_id'
    context.user_data['state'] = 'admin_searching_user'
    
    await query.edit_message_text(
        "🆔 *Search User by ID*\n\n"
        "Please enter the user ID you want to search for:\n\n"
        "Example: `123456789`\n\n"
        "Type the user ID or use the cancel button to return\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚫 Cancel", callback_data="admin_search_user")
        ]]),
        parse_mode="MarkdownV2"
    )

async def search_user_by_username_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search by username - prompt admin to enter username"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    context.user_data['admin_search_mode'] = 'by_username'
    context.user_data['state'] = 'admin_searching_user'
    
    await query.edit_message_text(
        "👤 *Search User by Username*\n\n"
        "Please enter the username \\(partial or full\\) you want to search for:\n\n"
        "Example: `john` or `john_doe`\n\n"
        "Type the username or use the cancel button to return\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚫 Cancel", callback_data="admin_search_user")
        ]]),
        parse_mode="MarkdownV2"
    )

async def search_user_by_letter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle search by name starting letter - prompt admin to enter letter"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    context.user_data['admin_search_mode'] = 'by_letter'
    context.user_data['state'] = 'admin_searching_user'
    
    await query.edit_message_text(
        "🔤 *Search Users by Name Starting Letter*\n\n"
        "Please enter the letter that names should start with:\n\n"
        "Example: `A` or `J` or `م`\n\n"
        "Type the letter or use the cancel button to return\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚫 Cancel", callback_data="admin_search_user")
        ]]),
        parse_mode="MarkdownV2"
    )

async def search_user_general_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle general name search - prompt admin to enter search term"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    context.user_data['admin_search_mode'] = 'general'
    context.user_data['state'] = 'admin_searching_user'
    
    await query.edit_message_text(
        "📝 *General User Search*\n\n"
        "Please enter any part of the name, username, or identifier:\n\n"
        "This will search across all name fields\n\n"
        "Example: `alice`, `smith`, `أحمد`\n\n"
        "Type the search term or use the cancel button to return\\.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚫 Cancel", callback_data="admin_search_user")
        ]]),
        parse_mode="MarkdownV2"
    )

async def search_user_recent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent users"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        from admin_tools import search_manager
        from db import get_recent_users
        
        # Get recent users using existing function
        recent_users = get_recent_users(15)
        
        if not recent_users:
            await query.edit_message_text(
                "📊 *Recent Users*\n\n"
                "No recent users found\\.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Search", callback_data="admin_search_user")
                ]]),
                parse_mode="MarkdownV2"
            )
            return
        
        # Format results
        result_text = f"📊 *Recent Users \\({len(recent_users)} found\\)*\n\n"
        
        for i, user in enumerate(recent_users, 1):
            user_id_val, username, first_name, last_name, join_date, questions_asked, comments_posted, blocked = user
            
            name = f"{first_name or ''} {last_name or ''}".strip()
            display_name = name or username or "No name"
            
            status = "🚫" if blocked else "✅"
            total_activity = questions_asked + comments_posted
            
            # Format join date
            try:
                if hasattr(join_date, 'strftime'):
                    formatted_date = join_date.strftime('%Y-%m-%d')
                else:
                    formatted_date = str(join_date)[:10] if join_date else "Unknown"
            except:
                formatted_date = "Unknown"
            
            result_text += f"{i}\\. {status} {escape_markdown_text(display_name)}\n"
            result_text += f"   ID: `{user_id_val}` \\| Activity: {total_activity}\n"
            result_text += f"   Joined: {escape_markdown_text(formatted_date)}\n\n"
        
        # Create action buttons for first few users
        keyboard = []
        for i, user in enumerate(recent_users[:5], 1):
            user_id_val = user[0]
            name = f"{user[2] or ''} {user[3] or ''}".strip() or user[1] or "Anonymous"
            keyboard.append([
                InlineKeyboardButton(f"👤 {name[:15]}...", callback_data=f"admin_user_info_{user_id_val}")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Search", callback_data="admin_search_user")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            result_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in search_user_recent_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to fetch recent users\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Search", callback_data="admin_search_user")
            ]]),
            parse_mode="MarkdownV2"
        )

async def search_user_active_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show most active users"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        from db import get_active_users
        
        # Get active users using existing function
        active_users = get_active_users(15)
        
        if not active_users:
            await query.edit_message_text(
                "⚡ *Most Active Users*\n\n"
                "No active users found\\.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Search", callback_data="admin_search_user")
                ]]),
                parse_mode="MarkdownV2"
            )
            return
        
        # Format results
        result_text = f"⚡ *Most Active Users \\({len(active_users)} found\\)*\n\n"
        
        for i, user in enumerate(active_users, 1):
            user_id_val, username, first_name, last_name, join_date, questions_asked, comments_posted, blocked = user
            
            name = f"{first_name or ''} {last_name or ''}".strip()
            display_name = name or username or "No name"
            
            status = "🚫" if blocked else "✅"
            total_activity = questions_asked + comments_posted
            
            result_text += f"{i}\\. {status} {escape_markdown_text(display_name)}\n"
            result_text += f"   ID: `{user_id_val}` \\| Activity: {total_activity}\n"
            result_text += f"   Posts: {questions_asked} \\| Comments: {comments_posted}\n\n"
        
        # Create action buttons for first few users
        keyboard = []
        for i, user in enumerate(active_users[:5], 1):
            user_id_val = user[0]
            name = f"{user[2] or ''} {user[3] or ''}".strip() or user[1] or "Anonymous"
            keyboard.append([
                InlineKeyboardButton(f"👤 {name[:15]}...", callback_data=f"admin_user_info_{user_id_val}")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Search", callback_data="admin_search_user")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            result_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in search_user_active_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to fetch active users\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Search", callback_data="admin_search_user")
            ]]),
            parse_mode="MarkdownV2"
        )

async def handle_admin_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin user search input based on search mode"""
    if not update.message or not update.message.text:
        return
    
    # Do not treat button presses as search queries
    if is_button_text(update.message.text):
        await update.message.reply_text("Search cancelled. Use the search buttons to choose a different option.")
        context.user_data.pop('state', None)
        context.user_data.pop('admin_search_mode', None)
        return
    
    user_id = update.message.from_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❗ You are not authorized to use admin features.")
        context.user_data.pop('state', None)
        context.user_data.pop('admin_search_mode', None)
        return
    
    search_mode = context.user_data.get('admin_search_mode')
    search_term = update.message.text.strip()
    
    if not search_mode or not search_term:
        await update.message.reply_text("❗ Invalid search. Please try again.")
        return
    
    try:
        from admin_tools import search_manager
        
        # Perform search based on mode
        results = []
        
        if search_mode == 'by_id':
            try:
                user_id_search = int(search_term)
                results = search_manager.search_users(user_id=user_id_search)
            except ValueError:
                await update.message.reply_text("❗ Invalid user ID. Please enter a number.")
                return
        elif search_mode == 'by_username':
            results = search_manager.search_users(username=search_term)
        elif search_mode == 'by_letter':
            results = search_manager.search_users(name_starts_with=search_term)
        elif search_mode == 'general':
            results = search_manager.search_users(query=search_term)
        
        # Clear search state
        context.user_data.pop('state', None)
        context.user_data.pop('admin_search_mode', None)
        
        if not results:
            await update.message.reply_text(
                f"🔍 *Search Results*\n\n"
                f"No users found for: `{escape_markdown_text(search_term)}`\n\n"
                f"Try a different search term or method\\.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Search", callback_data="admin_search_user")
                ]]),
                parse_mode="MarkdownV2"
            )
            return
        
        # Format results
        result_text = f"🔍 *Search Results \\({len(results)} found\\)*\n\n"
        result_text += f"Search term: `{escape_markdown_text(search_term)}`\n\n"
        
        for i, user in enumerate(results, 1):
            user_id_val = user['user_id']
            display_name = user['display_name']
            status = "🚫" if user['blocked'] else "✅"
            total_activity = user['questions_asked'] + user['comments_posted']
            total_posts = user['total_posts']
            total_comments = user['total_comments']
            
            # Format join date
            try:
                if hasattr(user['join_date'], 'strftime'):
                    formatted_date = user['join_date'].strftime('%Y-%m-%d')
                else:
                    formatted_date = str(user['join_date'])[:10] if user['join_date'] else "Unknown"
            except:
                formatted_date = "Unknown"
            
            result_text += f"{i}\\. {status} {escape_markdown_text(display_name)}\n"
            result_text += f"   ID: `{user_id_val}` \\| Activity: {total_activity}\n"
            result_text += f"   Posts: {total_posts} \\| Comments: {total_comments}\n"
            result_text += f"   Joined: {escape_markdown_text(formatted_date)}\n\n"
        
        # Create action buttons for results
        keyboard = []
        for user in results[:10]:  # Show buttons for first 10 results
            user_id_val = user['user_id']
            display_name = user['display_name'][:15]
            keyboard.append([
                InlineKeyboardButton(f"👤 {display_name}...", callback_data=f"admin_user_info_{user_id_val}"),
                InlineKeyboardButton(f"📊 Details", callback_data=f"admin_user_detail_{user_id_val}")
            ])
        
        keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="admin_search_user")])
        keyboard.append([InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            result_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in handle_admin_user_search: {e}")
        
        # Handle specific connection errors
        error_message = "❌ *Error*\n\nFailed to perform search\\. Please try again\\."
        if "httpx.ConnectError" in str(e) or "ConnectError" in str(e):
            error_message = "🌐 *Network Error*\n\nConnection issue detected\\. Please check your internet connection and try again\\."
        elif "timeout" in str(e).lower():
            error_message = "⏱️ *Timeout Error*\n\nRequest timed out\\. Please try again\\."
        
        try:
            await update.message.reply_text(
                error_message,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Search", callback_data="admin_search_user")
                ]]),
                parse_mode="MarkdownV2"
            )
        except Exception as reply_error:
            logger.error(f"Failed to send error reply: {reply_error}")
            # Try to send a simple text message without markdown if the formatted one fails
            try:
                await update.message.reply_text("Error occurred during search. Please try again.")
            except:
                pass
        
        # Clear search state on error
        context.user_data.pop('state', None)
        context.user_data.pop('admin_search_mode', None)

# Missing backup management callback handlers
async def admin_create_backup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle create backup button callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        from backup_system import backup_manager
        
        # Show progress message
        await query.edit_message_text(
            "💾 *Creating Backup*\n\n⏳ Please wait while creating a manual backup...",
            parse_mode="MarkdownV2"
        )
        
        # Create the backup
        success, result = backup_manager.create_backup(backup_type="manual")
        
        if success:
            backup_info = result
            size_mb = backup_info['size'] / (1024 * 1024)
            
            success_text = f"""✅ *Backup Created Successfully\\!*

📁 *Backup Details:*
• File: `{escape_markdown_text(backup_info['filename'])}`
• Size: `{size_mb:.2f} MB`
• Records: `{backup_info.get('record_count', 'Unknown'):,}`
• Type: Manual
• Created: {escape_markdown_text(backup_info['created'].strftime('%Y-%m-%d %H:%M:%S'))}

Backup has been saved to the backup directory\\."""
            
            keyboard = [
                [
                    InlineKeyboardButton("🗃 View All Backups", callback_data="admin_list_backups"),
                    InlineKeyboardButton("💾 Backup Info", callback_data="admin_backup_info")
                ],
                [
                    InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                success_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        else:
            error_text = f"""❌ *Backup Failed*

🚨 Error creating backup:
`{escape_markdown_text(str(result))}`

Please check the system logs and try again\\."""
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Try Again", callback_data="admin_create_backup"),
                    InlineKeyboardButton("💾 Backup Info", callback_data="admin_backup_info")
                ],
                [
                    InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                error_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
    
    except Exception as e:
        logger.error(f"Error in admin_create_backup_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to create backup\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_list_backups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle list backups button callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        from backup_system import backup_manager
        from datetime import datetime
        
        # Get all backups
        backups = backup_manager.list_backups(limit=20)
        
        if not backups:
            await query.edit_message_text(
                "🗃 *Backup List*\n\n📭 No backups found\\!\n\nConsider creating your first backup\\.",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("💾 Create Backup", callback_data="admin_create_backup"),
                        InlineKeyboardButton("💾 Backup Info", callback_data="admin_backup_info")
                    ],
                    [
                        InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
                    ]
                ]),
                parse_mode="MarkdownV2"
            )
            return
        
        # Build backup list message
        list_text = f"🗃 *All Backups \\({len(backups)}\\)*\n\n"
        
        total_size = 0
        for i, backup in enumerate(backups, 1):
            filename = backup['filename']
            size_mb = backup['size'] / (1024 * 1024)
            total_size += size_mb
            
            try:
                if isinstance(backup['created'], str):
                    created_dt = datetime.fromisoformat(backup['created'])
                else:
                    created_dt = backup['created']
                created_str = created_dt.strftime('%Y-%m-%d %H:%M')
                escaped_created = escape_markdown_text(created_str)
            except:
                escaped_created = "Unknown date"
            
            backup_type = backup.get('backup_type', 'unknown')
            type_emoji = "🔄" if backup_type == "auto" else "👤" if backup_type == "manual" else "❓"
            
            list_text += f"{i}\\. {type_emoji} **{size_mb:.1f}MB** \\| {escaped_created}\n"
            
            # Show record count if available
            if 'record_count' in backup:
                list_text += f"   📊 Records: `{backup['record_count']:,}`\n"
            
            # Show filename (truncated)
            short_filename = filename[:30] + "..." if len(filename) > 33 else filename
            list_text += f"   📄 `{escape_markdown_text(short_filename)}`\n\n"
            
            # Limit display to prevent message being too long
            if i >= 10:
                remaining = len(backups) - 10
                if remaining > 0:
                    list_text += f"... and {remaining} more backups\n\n"
                break
        
        list_text += f"💾 **Total Storage:** `{total_size:.2f} MB`\n"
        
        # Add navigation buttons
        keyboard = [
            [
                InlineKeyboardButton("💾 Create New", callback_data="admin_create_backup"),
                InlineKeyboardButton("🧹 Cleanup Old", callback_data="admin_cleanup_backups")
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="admin_list_backups"),
                InlineKeyboardButton("💾 Backup Info", callback_data="admin_backup_info")
            ],
            [
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            list_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    
    except Exception as e:
        logger.error(f"Error in admin_list_backups_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to list backups\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_cleanup_backups_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cleanup backups button callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        from backup_system import backup_manager
        
        # Show progress message
        await query.edit_message_text(
            "🧹 *Cleaning Up Old Backups*\n\n⏳ Analyzing and removing old backups...",
            parse_mode="MarkdownV2"
        )
        
        # Get current backup count before cleanup
        backups_before = backup_manager.list_backups()
        count_before = len(backups_before)
        
        # Clean old backups (keep last 10)
        cleaned_count, total_size_freed = backup_manager.cleanup_old_backups(keep_count=10)
        
        # Get backup count after cleanup
        backups_after = backup_manager.list_backups()
        count_after = len(backups_after)
        
        if cleaned_count > 0:
            success_text = f"""✅ *Cleanup Completed*

🗑️ **Cleaned Up:**
• Removed: `{cleaned_count}` old backups
• Space Freed: `{total_size_freed:.2f} MB`
• Before: `{count_before}` backups
• After: `{count_after}` backups

✨ Old backups have been successfully removed\\."""
        else:
            success_text = f"""✅ *Cleanup Completed*

🧹 **No Cleanup Needed:**
• Current backups: `{count_before}`
• All backups are within retention policy
• No old backups to remove

✨ Your backup collection is already optimized\\."""
        
        keyboard = [
            [
                InlineKeyboardButton("🗃 View Backups", callback_data="admin_list_backups"),
                InlineKeyboardButton("💾 Backup Info", callback_data="admin_backup_info")
            ],
            [
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            success_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    
    except Exception as e:
        logger.error(f"Error in admin_cleanup_backups_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to cleanup backups\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_table_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle table info button callback"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return

    try:
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()

            # Get table names (PostgreSQL style)
            cursor.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = cursor.fetchall()

        table_text = "📋 *Database Table Information*\n\n"

        if not tables:
            table_text += "❓ No tables found in database\n"
        else:
            table_text += f"📊 **Total Tables:** `{len(tables)}`\n\n"

            for (table_name,) in tables:
                # Get row count for each table
                try:
                    cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                    row_count = cursor.fetchone()[0]
                except Exception:
                    row_count = "Error"
                
                # Get column count
                try:
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns = cursor.fetchall()
                    column_count = len(columns)
                    
                    # Show some key columns
                    key_columns = []
                    for col in columns[:3]:  # Show first 3 columns
                        col_name = col[1]  # Column name is at index 1
                        col_type = col[2]  # Column type is at index 2
                        key_columns.append(f"{col_name} ({col_type})")
                    
                    if len(columns) > 3:
                        key_columns.append(f"... +{len(columns) - 3} more")
                    
                    columns_info = ", ".join(key_columns)
                    
                except:
                    column_count = "Error"
                    columns_info = "Unable to fetch"
                
                table_text += f"🗄️ **{escape_markdown_text(table_name)}**\n"
                table_text += f"• Rows: `{row_count:,}`\n" if isinstance(row_count, int) else f"• Rows: {row_count}\n"
                table_text += f"• Columns: `{column_count}`\n"
                if isinstance(column_count, int) and column_count <= 10:
                    table_text += f"• Schema: {escape_markdown_text(columns_info[:100])}...\n" if len(columns_info) > 100 else f"• Schema: {escape_markdown_text(columns_info)}\n"
                table_text += "\n"

        # Get database file info
        try:
            import os
            db_size = os.path.getsize(DB_PATH) / (1024 * 1024)  # Convert to MB
            table_text += f"💾 **Database File**\n"
            table_text += f"• Size: `{db_size:.2f} MB`\n"
            table_text += f"• Path: `{escape_markdown_text(DB_PATH)}`\n"
        except Exception as e:
            table_text += f"💾 **Database File**\n• Error: {escape_markdown_text(str(e))}\n"

        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="admin_table_info"),
                InlineKeyboardButton("🗄️ Database Stats", callback_data="admin_db_stats")
            ],
            [
                InlineKeyboardButton("🛠️ Maintenance", callback_data="admin_db_maintenance"),
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            table_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )

    except Exception as e:
        logger.error(f"Error in admin_table_info_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to retrieve table information\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_db_maintenance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle database maintenance button callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        # Show progress message
        await query.edit_message_text(
            "🛠️ *Database Maintenance*\n\n⏳ Running maintenance operations...",
            parse_mode="MarkdownV2"
        )
        
        db_conn = get_db_connection()
        with db_conn.get_connection() as conn:
            cursor = conn.cursor()
            
            maintenance_results = []
        
        # 1. Vacuum the database to reclaim space
        try:
            cursor.execute("VACUUM")
            maintenance_results.append("✅ Database vacuum completed")
        except Exception as e:
            maintenance_results.append(f"❌ Vacuum failed: {str(e)}")
        
        # 2. Analyze the database for query optimization
        try:
            cursor.execute("ANALYZE")
            maintenance_results.append("✅ Database analysis completed")
        except Exception as e:
            maintenance_results.append(f"❌ Analysis failed: {str(e)}")
        
        # 3. Check database integrity
        try:
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]
            if integrity_result == "ok":
                maintenance_results.append("✅ Database integrity check passed")
            else:
                maintenance_results.append(f"⚠️ Integrity issues: {integrity_result}")
        except Exception as e:
            maintenance_results.append(f"❌ Integrity check failed: {str(e)}")
        
        # 4. Update database statistics
        try:
            # Get updated stats
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM posts")
            post_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM comments")
            comment_count = cursor.fetchone()[0]
            
            maintenance_results.append(f"📊 Updated stats: {user_count:,} users, {post_count:,} posts, {comment_count:,} comments")
        except Exception as e:
            maintenance_results.append(f"❌ Stats update failed: {str(e)}")
        
        # 5. Get database size after maintenance
        try:
            import os
            db_size = os.path.getsize(DB_PATH) / (1024 * 1024)  # Convert to MB
            maintenance_results.append(f"💾 Database size: {db_size:.2f} MB")
        except Exception as e:
            maintenance_results.append(f"❌ Size check failed: {str(e)}")
        
        
        # Build results message
        maintenance_text = "🛠️ *Database Maintenance Completed*\n\n"
        maintenance_text += "📋 **Operations Performed:**\n"
        
        for i, result in enumerate(maintenance_results, 1):
            maintenance_text += f"{i}\\. {result}\n"
        
        maintenance_text += "\n✨ Regular maintenance helps keep your database optimized and running smoothly\\."
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Run Again", callback_data="admin_db_maintenance"),
                InlineKeyboardButton("🗄️ Database Stats", callback_data="admin_db_stats")
            ],
            [
                InlineKeyboardButton("📋 Table Info", callback_data="admin_table_info"),
                InlineKeyboardButton("💾 Create Backup", callback_data="admin_create_backup")
            ],
            [
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            maintenance_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    
    except Exception as e:
        logger.error(f"Error in admin_db_maintenance_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to perform database maintenance\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to System Info", callback_data="admin_system")
            ]]),
            parse_mode="MarkdownV2"
        )

# Admin deletion callback handlers
async def handle_admin_delete_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin delete post button"""
    query = update.callback_query
    await query.answer()

    try:
        user_id = update.effective_user.id
        logger.info(f"Admin delete post callback triggered by user {user_id}")

        if user_id not in ADMIN_IDS:
            logger.warning(f"Unauthorized delete attempt by user {user_id}")
            await query.answer("❗ Not authorized")
            return

        post_id = int(query.data.replace("admin_delete_post_", ""))
        logger.info(f"Admin {user_id} attempting to delete post {post_id}")

        # Get post details first
        post_details = get_post_details_for_deletion(post_id)
        logger.info(f"Post details for {post_id}: {post_details}")

        if not post_details:
            logger.warning(f"Post {post_id} not found for deletion")
            await query.answer("❗ Post not found!")
            return

        # Show confirmation dialog
        content_preview = post_details['content'][:100] + "..." if len(post_details['content']) > 100 else post_details['content']

        confirm_text = f"""⚠️ *Confirm Deletion*

🗑️ **Post to Delete:**
• ID: \\#{post_id}
• Category: {escape_markdown_text(post_details['category'])}
• Comments: {post_details['comment_count']}
• Content: {escape_markdown_text(content_preview)}

**Warning:** This action will:
• Delete the post permanently
• Delete all {post_details['comment_count']} comments
• Delete all reactions and reports
• Cannot be undone

Are you sure you want to proceed?"""

        keyboard = [
            [
                InlineKeyboardButton("🗑️ Yes, Delete Permanently", callback_data=f"confirm_delete_post_{post_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="admin_view_reports")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            confirm_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        logger.error(f"Error in admin delete post callback: {e}")
        await query.answer("An error occurred. Please try again later.")
        await query.edit_message_text("An unexpected error occurred while processing your request.")
async def handle_admin_delete_comment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin delete comment button"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    comment_id = int(query.data.replace("admin_delete_comment_", ""))
    
    # Get comment details first
    comment_details = get_comment_details_for_deletion(comment_id)
    
    if not comment_details:
        await query.answer("❗ Comment not found!")
        return
    
    # Show confirmation dialog
    content_preview = comment_details['content'][:100] + "..." if len(comment_details['content']) > 100 else comment_details['content']
    
    confirm_text = f"""⚠️ *Confirm Comment Deletion*

🗑️ **Comment to Delete:**
• ID: \\#{comment_id} \\(Post \\#{comment_details['post_id']}\\)
• Replies: {comment_details['reply_count']}
• Content: {escape_markdown_text(content_preview)}

**Warning:** This action will:
• Delete the comment permanently
• Delete all {comment_details['reply_count']} replies
• Delete all reactions and reports
• Cannot be undone

Are you sure you want to proceed?"""
    
    keyboard = [
        [
            InlineKeyboardButton("🗑️ Yes, Delete Permanently", callback_data=f"confirm_delete_comment_{comment_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data="admin_view_reports")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        confirm_text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )

async def handle_admin_clear_reports_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin clear reports button"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Parse callback data to get target type and ID
    parts = query.data.replace("admin_clear_reports_", "").split("_")
    if len(parts) < 2:
        await query.answer("❗ Invalid callback data")
        return
    
    target_type = parts[0]  # 'post' or 'comment'
    target_id = int(parts[1])
    
    try:
        # Clear reports for the content
        success, cleared_count = clear_reports_for_content(target_type, target_id)
        
        if success:
            await query.answer(f"✅ Cleared {cleared_count} reports!")
            
            # Show success message and return to reports view
            success_text = f"""✅ *Reports Cleared*

🔇 Successfully cleared {cleared_count} reports for {target_type} #{target_id}.

The content is no longer flagged for moderation."""
            
            keyboard = [[
                InlineKeyboardButton("🚩 View Reports", callback_data="admin_view_reports"),
                InlineKeyboardButton("🔙 Back to Moderation", callback_data="admin_moderation")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                success_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        else:
            await query.answer("❗ Failed to clear reports")
    
    except Exception as e:
        logger.error(f"Error clearing reports: {e}")
        await query.answer(f"❗ Error: {str(e)}")

async def handle_admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approve content button"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    # Parse callback data to get target type and ID
    if query.data.startswith("admin_approve_post_"):
        target_type = "post"
        target_id = int(query.data.replace("admin_approve_post_", ""))
    elif query.data.startswith("admin_approve_comment_"):
        target_type = "comment"
        target_id = int(query.data.replace("admin_approve_comment_", ""))
    else:
        await query.answer("❗ Invalid callback data")
        return
    
    try:
        # Clear reports for the content (approving it)
        success, cleared_count = clear_reports_for_content(target_type, target_id)
        
        if success:
            await query.answer(f"✅ {target_type.title()} approved!")
            
            # Show success message and return to reports view
            success_text = f"""✅ *Content Approved*

👍 {target_type.title()} #{target_id} has been approved and {cleared_count} reports have been cleared.

The content is now considered clean and appropriate."""
            
            keyboard = [[
                InlineKeyboardButton("🚩 View Reports", callback_data="admin_view_reports"),
                InlineKeyboardButton("🔙 Back to Moderation", callback_data="admin_moderation")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                success_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
        else:
            await query.answer("❗ Failed to approve content")
    
    except Exception as e:
        logger.error(f"Error approving content: {e}")
        await query.answer(f"❗ Error: {str(e)}")

async def handle_confirm_delete_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmed post deletion"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    post_id = int(query.data.replace("confirm_delete_post_", ""))
    
    # Show processing message
    await query.edit_message_text(
        "<b>🗑️ Deleting Post...</b>\n\n⏳ Please wait while the post and all related data is being deleted permanently...",
        parse_mode="HTML"
    )
    
    try:
        # Get post details for logging before deletion
        post_details = get_post_details_for_deletion(post_id)
        
        if not post_details:
            await query.edit_message_text(
                "❌ *Deletion Failed*\n\nPost not found or already deleted.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Reports", callback_data="admin_view_reports")
                ]]),
                parse_mode="MarkdownV2"
            )
            return
        
        # Delete the channel message if it exists
        if post_details.get('channel_message_id'):
            try:
                await delete_channel_message(context, post_details['channel_message_id'])
                logger.info(f"Deleted channel message {post_details['channel_message_id']} for post {post_id}")
            except Exception as e:
                logger.warning(f"Failed to delete channel message for post {post_id}: {e}")
        
        # Perform the complete deletion
        success, deletion_stats = delete_post_completely(post_id, user_id)
        
        if success:
            # Create success message with deletion statistics (use HTML to avoid MarkdownV2 escaping issues)
            success_text = (
                f"<b>✅ Post Deleted Successfully</b>\n\n"
                f"🗑️ <b>Deletion Summary:</b>\n"
                f"• Post ID: #{post_id}\n"
                f"• Comments Deleted: {deletion_stats['comments_deleted']:,}\n"
                f"• Reactions Deleted: {deletion_stats['reactions_deleted']:,}\n"
                f"• Reports Cleared: {deletion_stats['reports_deleted']:,}\n"
                f"• Channel Message: {'✅ Removed' if post_details.get('channel_message_id') else 'N/A'}\n\n"
                f"<b>Admin:</b> {user_id}\n"
                f"<b>Action:</b> Permanent deletion completed\n\n"
                f"⚠️ This action has been logged for audit purposes."
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("🚩 View Remaining Reports", callback_data="admin_view_reports"),
                    InlineKeyboardButton("🔙 Back to Moderation", callback_data="admin_moderation")
                ],
                [
                    InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                success_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            
            # Log the deletion action
            logger.info(f"Admin {user_id} successfully deleted post {post_id} with {deletion_stats['comments_deleted']} comments")
        
        else:
            # Deletion failed (use HTML formatting to avoid escaping issues)
            error_text = (
                f"<b>❌ Deletion Failed</b>\n\n"
                f"🚨 An error occurred while deleting post #{post_id}.\n\n"
                f"Error: {str(deletion_stats)}\n\n"
                f"Please try again or contact system administrator."
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Try Again", callback_data=f"admin_delete_post_{post_id}"),
                    InlineKeyboardButton("🔙 Back to Reports", callback_data="admin_view_reports")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                error_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            
            # Log the failure
            logger.error(f"Admin {user_id} failed to delete post {post_id}: {deletion_stats}")
    
    except Exception as e:
        logger.error(f"Critical error in handle_confirm_delete_post_callback for post {post_id}: {e}")
        logger.error(f"Admin user {user_id}, Post ID: {post_id}, Exception type: {type(e).__name__}")
        
        # Log additional context for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Provide more detailed error information based on exception type
        error_str = str(e).lower()
        if "connection" in error_str or "network" in error_str:
            error_details = "🌐 Network or database connection issue. This may be temporary."
            suggestion = "Please wait a few moments and try again."
        elif "permission" in error_str or "access" in error_str:
            error_details = "🔒 Database permission or access issue."
            suggestion = "Please contact the system administrator."
        elif "timeout" in error_str:
            error_details = "⏰ Operation timed out due to system load."
            suggestion = "Please try again in a few minutes."
        elif "foreign key" in error_str or "constraint" in error_str:
            error_details = "🔗 Database constraint issue - there may be related data preventing deletion."
            suggestion = "Please contact the system administrator."
        else:
            error_details = "💥 An unexpected system error occurred."
            suggestion = "Please try again or contact the system administrator."
        
        # Unexpected error (use HTML formatting to avoid escaping issues)
        error_text = (
            f"<b>❌ Critical Deletion Error</b>\n\n"
            f"{error_details}\n\n"
            f"<b>Technical Details:</b>\n"
            f"• Post ID: #{post_id}\n"
            f"• Admin ID: {user_id}\n"
            f"• Error: {str(e)[:200]}{'...' if len(str(e)) > 200 else ''}\n\n"
            f"<b>What to do:</b>\n{suggestion}\n\n"
            f"⚠️ This error has been logged for investigation."
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Try Again", callback_data=f"admin_delete_post_{post_id}"),
                InlineKeyboardButton("🔙 Back to Reports", callback_data="admin_view_reports")
            ],
            [
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(
                error_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as edit_error:
            logger.error(f"Failed to edit error message for post deletion: {edit_error}")
            # Try to send a new message if editing fails
            try:
                await query.message.reply_text(
                    f"❌ Critical error during post deletion: {str(e)[:100]}...",
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            except Exception as reply_error:
                logger.error(f"Failed to send error reply for post deletion: {reply_error}")

async def handle_confirm_delete_comment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmed comment deletion"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    comment_id = int(query.data.replace("confirm_delete_comment_", ""))
    
    # Show processing message
    await query.edit_message_text(
        "🗑️ *Deleting Comment...*\n\n⏳ Please wait while the comment and all related data is being deleted permanently...",
        parse_mode="MarkdownV2"
    )
    
    try:
        # Get comment details for logging before deletion
        comment_details = get_comment_details_for_deletion(comment_id)
        
        if not comment_details:
            await query.edit_message_text(
                "❌ *Deletion Failed*\n\nComment not found or already deleted.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to Reports", callback_data="admin_view_reports")
                ]]),
                parse_mode="MarkdownV2"
            )
            return
        
        post_id = comment_details.get('post_id')
        
        # Perform the complete deletion
        success, deletion_stats = delete_comment_completely(comment_id, user_id)
        
        if success:
            # Update the channel message comment count if post exists
            if post_id:
                try:
                    from comments import update_channel_message_comment_count
                    update_success, update_result = await update_channel_message_comment_count(context, post_id)
                    if update_success:
                        logger.info(f"Updated channel message comment count for post {post_id} after comment deletion")
                    else:
                        logger.warning(f"Failed to update channel message for post {post_id}: {update_result}")
                except Exception as e:
                    logger.error(f"Error updating channel message after comment deletion: {e}", exc_info=True)
            
            # Create success message with deletion statistics (use HTML to avoid MarkdownV2 escaping issues)
            success_text = (
                f"<b>✅ Comment Deleted Successfully</b>\n\n"
                f"🗑️ <b>Deletion Summary:</b>\n"
                f"• Comment ID: #{comment_id}\n"
                f"• Post ID: #{post_id if post_id else 'N/A'}\n"
                f"• Replies Deleted: {deletion_stats['replies_deleted']:,}\n"
                f"• Reactions Deleted: {deletion_stats['reactions_deleted']:,}\n"
                f"• Reports Cleared: {deletion_stats['reports_deleted']:,}\n\n"
                f"<b>Admin:</b> {user_id}\n"
                f"<b>Action:</b> Permanent deletion completed\n\n"
                f"⚠️ This action has been logged for audit purposes."
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("🚩 View Remaining Reports", callback_data="admin_view_reports"),
                    InlineKeyboardButton("🔙 Back to Moderation", callback_data="admin_moderation")
                ],
                [
                    InlineKeyboardButton(f"👀 View Post #{post_id}", callback_data=f"view_post_{post_id}") if post_id else InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                success_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            
            # Log the deletion action
            logger.info(f"Admin {user_id} successfully deleted comment {comment_id} with {deletion_stats['replies_deleted']} replies")
        
        else:
            # Deletion failed (use HTML formatting)
            error_text = (
                f"<b>❌ Deletion Failed</b>\n\n"
                f"🚨 An error occurred while deleting comment #{comment_id}.\n\n"
                f"Error: {str(deletion_stats)}\n\n"
                f"Please try again or contact system administrator."
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Try Again", callback_data=f"admin_delete_comment_{comment_id}"),
                    InlineKeyboardButton("🔙 Back to Reports", callback_data="admin_view_reports")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                error_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
            
            # Log the failure
            logger.error(f"Admin {user_id} failed to delete comment {comment_id}: {deletion_stats}")
    
    except Exception as e:
        logger.error(f"Critical error in handle_confirm_delete_comment_callback for comment {comment_id}: {e}")
        logger.error(f"Admin user {user_id}, Comment ID: {comment_id}, Exception type: {type(e).__name__}")
        
        # Log additional context for debugging
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Provide more detailed error information based on exception type
        error_str = str(e).lower()
        if "connection" in error_str or "network" in error_str:
            error_details = "🌐 Network or database connection issue. This may be temporary."
            suggestion = "Please wait a few moments and try again."
        elif "permission" in error_str or "access" in error_str:
            error_details = "🔒 Database permission or access issue."
            suggestion = "Please contact the system administrator."
        elif "timeout" in error_str:
            error_details = "⏰ Operation timed out due to system load."
            suggestion = "Please try again in a few minutes."
        elif "foreign key" in error_str or "constraint" in error_str:
            error_details = "🔗 Database constraint issue - there may be related data preventing deletion."
            suggestion = "Please contact the system administrator."
        else:
            error_details = "💥 An unexpected system error occurred."
            suggestion = "Please try again or contact the system administrator."
        
        # Unexpected error (use HTML formatting to avoid escaping issues)
        error_text = (
            f"<b>❌ Critical Deletion Error</b>\n\n"
            f"{error_details}\n\n"
            f"<b>Technical Details:</b>\n"
            f"• Comment ID: #{comment_id}\n"
            f"• Admin ID: {user_id}\n"
            f"• Error: {str(e)[:200]}{'...' if len(str(e)) > 200 else ''}\n\n"
            f"<b>What to do:</b>\n{suggestion}\n\n"
            f"⚠️ This error has been logged for investigation."
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Try Again", callback_data=f"admin_delete_comment_{comment_id}"),
                InlineKeyboardButton("🔙 Back to Reports", callback_data="admin_view_reports")
            ],
            [
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(
                error_text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        except Exception as edit_error:
            logger.error(f"Failed to edit error message for comment deletion: {edit_error}")
            # Try to send a new message if editing fails
            try:
                await query.message.reply_text(
                    f"❌ Critical error during comment deletion: {str(e)[:100]}...",
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            except Exception as reply_error:
                logger.error(f"Failed to send error reply for comment deletion: {reply_error}")

async def admin_user_detailed_info(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id_to_view: int):
    """Show detailed user information using SearchManager with navigation buttons"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        from admin_tools import search_manager
        from text_utils import escape_markdown_text
        
        # Get detailed user info from SearchManager
        user_details = search_manager.get_user_detailed_info(user_id_to_view)
        
        if not user_details:
            await query.edit_message_text(
                "❗ *User Not Found*\n\nThe requested user could not be found in the database\\.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
                ]]),
                parse_mode="MarkdownV2"
            )
            return
        
        # Format user information
        display_name = user_details['display_name']
        status = "🚫 Blocked" if user_details['blocked'] else "✅ Active"
        
        # Format join date
        try:
            if hasattr(user_details['join_date'], 'strftime'):
                formatted_date = user_details['join_date'].strftime('%Y-%m-%d %H:%M')
            else:
                formatted_date = str(user_details['join_date'])[:16] if user_details['join_date'] else "Unknown"
            # Escape the formatted date
            formatted_date = escape_markdown_text(formatted_date)
        except:
            formatted_date = "Unknown"
        
        details_text = f"""👤 *User Details*

**Basic Information:**
• Name: {escape_markdown_text(display_name)}
• ID: `{user_details['user_id']}`
• Username: {f"@{escape_markdown_text(user_details['username'])}" if user_details['username'] else "None"}
• Status: {status}
• Joined: {formatted_date}

**Activity Statistics:**
• Total Posts: {user_details['statistics']['total_posts']}
• Approved Posts: {user_details['statistics']['approved_posts']}
• Rejected Posts: {user_details['statistics']['rejected_posts']}
• Pending Posts: {user_details['statistics']['pending_posts']}
• Total Comments: {user_details['statistics']['total_comments']}
• Post Likes: {user_details['statistics']['total_post_likes']}
• Comment Likes: {user_details['statistics']['total_comment_likes']}

**Recent Activity:**
• Questions Asked: {user_details['questions_asked']}
• Comments Posted: {user_details['comments_posted']}"""
        
        # Create main action buttons
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{'✅ Unblock User' if user_details['blocked'] else '⛔ Block User'}",
                    callback_data=f"admin_{'unblock' if user_details['blocked'] else 'block'}_{user_id_to_view}"
                )
            ]
        ]
        
        # Add posts navigation if user has posts
        if user_details['statistics']['total_posts'] > 0:
            total_posts = user_details['statistics']['total_posts']
            keyboard.append([
                InlineKeyboardButton(
                    f"📝 View Posts ({total_posts})",
                    callback_data=f"admin_user_posts_{user_id_to_view}_1"
                ),
                InlineKeyboardButton(
                    f"📈 Post Analytics",
                    callback_data=f"admin_user_post_analytics_{user_id_to_view}"
                )
            ])
        
        # Add comments navigation if user has comments
        if user_details['statistics']['total_comments'] > 0:
            total_comments = user_details['statistics']['total_comments']
            keyboard.append([
                InlineKeyboardButton(
                    f"💬 View Comments ({total_comments})",
                    callback_data=f"admin_user_comments_{user_id_to_view}_1"
                ),
                InlineKeyboardButton(
                    f"📊 Comment Analytics",
                    callback_data=f"admin_user_comment_analytics_{user_id_to_view}"
                )
            ])
        
        # Add activity analytics button
        keyboard.append([
            InlineKeyboardButton(
                "🎯 Activity Analytics",
                callback_data=f"admin_user_activity_analytics_{user_id_to_view}"
            )
        ])
        
        # Add navigation buttons
        keyboard.extend([
            [
                InlineKeyboardButton("📊 User Info", callback_data=f"admin_user_info_{user_id_to_view}"),
                InlineKeyboardButton("🔍 New Search", callback_data="admin_search_user")
            ],
            [
                InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
            ]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            details_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_user_detailed_info: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to load user details\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[\
                InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")\
            ]]),
            parse_mode="MarkdownV2"
        )

# Implement the missing callback handlers for user activity analytics
async def admin_user_posts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin user posts navigation callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        # Parse callback data: admin_user_posts_USER_ID_PAGE
        parts = query.data.split("_")
        user_id_to_view = int(parts[3])
        page = int(parts[4])
        
        from admin_tools import search_manager
        
        # Get paginated posts for the user
        posts_data = search_manager.get_user_posts_paginated(user_id_to_view, page)
        
        if not posts_data['posts']:
            no_posts_text = f"📝 *No Posts Found*\n\n"
            no_posts_text += f"User {user_id_to_view} has no posts to display\\."
            
            keyboard = [[
                InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                no_posts_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
            return
        
        # Build the posts display
        posts_text = f"📝 *User Posts \\- Page {posts_data['current_page']} of {posts_data['total_pages']}*\n\n"
        
        for i, post in enumerate(posts_data['posts'], 1):
            status_emoji = "✅" if post['approved'] == 1 else "⏳" if post['approved'] is None else "❌"
            status_text = "Approved" if post['approved'] == 1 else "Pending" if post['approved'] is None else "Rejected"
            
            posts_text += f"{i}\\. *Post \\#{post['post_id']}* {status_emoji}\n"
            posts_text += f"   Category: {escape_markdown_text(post['category'])}\n"
            ellipsis = "\\.\\.\\." if len(post['content']) > 100 else ""
            posts_text += f"   Content: {escape_markdown_text(post['content'][:100])}{ellipsis}\n"
            posts_text += f"   Comments: {post['comments_count']} \\| Status: {status_text}\n\n"
        
        # Create navigation buttons
        keyboard = []
        
        # Pagination buttons
        nav_buttons = []
        if posts_data['current_page'] > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin_user_posts_{user_id_to_view}_{posts_data['current_page'] - 1}"))
        if posts_data['current_page'] < posts_data['total_pages']:
            nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"admin_user_posts_{user_id_to_view}_{posts_data['current_page'] + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Back button
        keyboard.append([
            InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            posts_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_user_posts_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to load user posts\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_user_comments_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin user comments navigation callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        # Parse callback data: admin_user_comments_USER_ID_PAGE
        parts = query.data.split("_")
        user_id_to_view = int(parts[3])
        page = int(parts[4])
        
        from admin_tools import search_manager
        
        # Get paginated comments for the user
        comments_data = search_manager.get_user_comments_paginated(user_id_to_view, page)
        
        if not comments_data['comments']:
            no_comments_text = f"💬 *No Comments Found*\n\n"
            no_comments_text += f"User {user_id_to_view} has no comments to display\\."
            
            keyboard = [[
                InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                no_comments_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
            return
        
        # Build the comments display
        comments_text = f"💬 *User Comments \\- Page {comments_data['current_page']} of {comments_data['total_pages']}*\n\n"
        
        for i, comment in enumerate(comments_data['comments'], 1):
            comments_text += f"{i}\\. *Comment \\#{comment['comment_id']}*\n"
            comments_text += f"   Post: \\#{comment['post_id']}\n"
            ellipsis = "\\.\\.\\." if len(comment['content']) > 80 else ""
            comments_text += f"   Content: {escape_markdown_text(comment['content'][:80])}{ellipsis}\n"
            comments_text += f"   Likes: {comment['likes']} \\| Dislikes: {comment['dislikes']}\n\n"
        
        # Create navigation buttons
        keyboard = []
        
        # Pagination buttons
        nav_buttons = []
        if comments_data['current_page'] > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"admin_user_comments_{user_id_to_view}_{comments_data['current_page'] - 1}"))
        if comments_data['current_page'] < comments_data['total_pages']:
            nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"admin_user_comments_{user_id_to_view}_{comments_data['current_page'] + 1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Back button
        keyboard.append([
            InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            comments_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_user_comments_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to load user comments\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_user_activity_analytics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin user activity analytics callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        # Parse callback data: admin_user_activity_analytics_USER_ID
        parts = query.data.split("_")
        user_id_to_view = int(parts[4])
        
        from admin_tools import search_manager
        
        # Get user activity analytics
        analytics = search_manager.get_user_activity_analytics(user_id_to_view)
        
        if not analytics:
            no_analytics_text = f"🎯 *No Activity Analytics*\n\n"
            no_analytics_text += f"User {user_id_to_view} has no activity to analyze\\."
            
            keyboard = [[
                InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                no_analytics_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
            return
        
        # Build analytics display
        analytics_text = f"🎯 *User Activity Analytics*\n\n"
        
        # General activity
        analytics_text += f"**📊 General Activity:**\n"
        analytics_text += f"• Total Posts: {analytics['total_posts']}\n"
        analytics_text += f"• Total Comments: {analytics['total_comments']}\n"
        analytics_text += f"• Activity Score: {analytics['activity_score']}\n\n"
        
        # Most liked posts
        if analytics['most_liked_posts']:
            analytics_text += f"**🏆 Top Liked Posts:**\n"
            for i, post in enumerate(analytics['most_liked_posts'][:3], 1):
                analytics_text += f"{i}\\. Post #{post['post_id']} - {post['total_likes']} likes\n"
            analytics_text += "\n"
        
        # Most liked comments
        if analytics['most_liked_comments']:
            analytics_text += f"**💬 Top Liked Comments:**\n"
            for i, comment in enumerate(analytics['most_liked_comments'][:3], 1):
                analytics_text += f"{i}\\. Comment #{comment['id']} - {comment['likes']} likes\n"
            analytics_text += "\n"
        
        # Category statistics
        if analytics['category_stats']:
            analytics_text += f"**📂 Category Breakdown:**\n"
            for category, count in analytics['category_stats'].items():
                analytics_text += f"• {escape_markdown_text(category)}: {count} posts\n"
            analytics_text += "\n"
        
        # Recent activity
        if analytics.get('recent_activity'):
            analytics_text += f"**🕒 Recent Activity \\(7 days\\):**\n"
            analytics_text += f"• Posts: {analytics['recent_activity']['posts']}\n"
            analytics_text += f"• Comments: {analytics['recent_activity']['comments']}\n"
        
        keyboard = [[
            InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            analytics_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_user_activity_analytics_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to load activity analytics\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_user_post_analytics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin user post analytics callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        # Parse callback data: admin_user_post_analytics_USER_ID
        parts = query.data.split("_")
        user_id_to_view = int(parts[4])
        
        from admin_tools import search_manager
        
        # Get user activity analytics (contains post analytics)
        analytics = search_manager.get_user_activity_analytics(user_id_to_view)
        
        if not analytics or analytics['total_posts'] == 0:
            no_posts_text = f"📈 *No Post Analytics*\n\n"
            no_posts_text += f"User {user_id_to_view} has no posts to analyze\\."
            
            keyboard = [[
                InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                no_posts_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
            return
        
        # Build post analytics display
        analytics_text = f"📈 *Post Analytics*\n\n"
        
        analytics_text += f"**📊 Post Statistics:**\n"
        analytics_text += f"• Total Posts: {analytics['total_posts']}\n"
        
        # Most liked posts
        if analytics['most_liked_posts']:
            analytics_text += f"\n**🏆 Most Liked Posts:**\n"
            for i, post in enumerate(analytics['most_liked_posts'][:5], 1):
                analytics_text += f"{i}\\. Post #{post['id']} \\- {post['total_likes']} likes\n"
                analytics_text += f"   Category: {escape_markdown_text(post['category'])}\n"
                analytics_text += f"   Comments: {post.get('comment_count', 0)}\n"
            analytics_text += "\n"
        
        # Category breakdown
        if analytics['category_stats']:
            analytics_text += f"**📂 Posts by Category:**\n"
            for category, count in analytics['category_stats'].items():
                percentage = (count / analytics['total_posts'] * 100) if analytics['total_posts'] > 0 else 0
                analytics_text += f"• {escape_markdown_text(category)}: {count} \\({percentage:.1f}%\\)\n"
        
        keyboard = [[
            InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            analytics_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_user_post_analytics_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to load post analytics\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
            ]]),
            parse_mode="MarkdownV2"
        )

async def admin_user_comment_analytics_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin user comment analytics callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("❗ Not authorized")
        return
    
    try:
        # Parse callback data: admin_user_comment_analytics_USER_ID
        parts = query.data.split("_")
        user_id_to_view = int(parts[4])
        
        from admin_tools import search_manager
        
        # Get user activity analytics (contains comment analytics)
        analytics = search_manager.get_user_activity_analytics(user_id_to_view)
        
        if not analytics or analytics['total_comments'] == 0:
            no_comments_text = f"📊 *No Comment Analytics*\n\n"
            no_comments_text += f"User {user_id_to_view} has no comments to analyze\\."
            
            keyboard = [[
                InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                no_comments_text,
                reply_markup=reply_markup,
                parse_mode="MarkdownV2"
            )
            return
        
        # Build comment analytics display
        analytics_text = f"📊 *Comment Analytics*\n\n"
        
        analytics_text += f"**💬 Comment Statistics:**\n"
        analytics_text += f"• Total Comments: {analytics['total_comments']}\n"
        
        # Calculate engagement metrics
        total_likes = sum(comment['likes'] for comment in analytics.get('most_liked_comments', []))
        avg_likes = total_likes / analytics['total_comments'] if analytics['total_comments'] > 0 else 0
        analytics_text += f"• Average Likes per Comment: {avg_likes:.1f}\n\n"
        
        # Most liked comments
        if analytics['most_liked_comments']:
            analytics_text += f"**🏆 Most Liked Comments:**\n"
            for i, comment in enumerate(analytics['most_liked_comments'][:5], 1):
                analytics_text += f"{i}\\. Comment #{comment['id']} \\- {comment['likes']} likes\n"
                analytics_text += f"   Post: #{comment['post_id']}\n"
                comment_preview = comment['content'][:50] + "..." if len(comment['content']) > 50 else comment['content']
                analytics_text += f"   Preview: {escape_markdown_text(comment_preview)}\n\n"
        
        # Recent comment activity (if available)
        if analytics.get('recent_activity', {}).get('comments', 0) > 0:
            analytics_text += f"**🕒 Recent Activity \\(7 days\\):**\n"
            analytics_text += f"• Comments Posted: {analytics['recent_activity']['comments']}\n"
        
        keyboard = [[
            InlineKeyboardButton("🔙 Back to User Details", callback_data=f"admin_user_detail_{user_id_to_view}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            analytics_text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2"
        )
        
    except Exception as e:
        logger.error(f"Error in admin_user_comment_analytics_callback: {e}")
        await query.edit_message_text(
            "❌ *Error*\n\nFailed to load comment analytics\\. Please try again\\.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to User Management", callback_data="admin_users")
            ]]),
            parse_mode="MarkdownV2"
        )

async def warmup_cache():
    """Warm up cache with frequently accessed data for better performance"""
    try:
        from db import cache_manager
        
        # Pre-warm common cache entries
        logger.info("Cache warm-up started")
        
        # Cache will be populated on-demand as queries are made
        # This is just to initialize the cache manager
        cache_stats = cache_manager.get_stats()
        logger.info(f"Cache manager ready - {cache_stats['cached_items']} items cached")
        
    except Exception as e:
        logger.error(f"Error during cache warmup: {e}")

def main():
    """Main function to run the bot - optimized with async startup"""
    import asyncio
    
    # Import instance manager
    from instance_manager import ensure_single_instance
    
    # Ensure only one instance is running
    if not ensure_single_instance():
        logger.error("Another bot instance is already running. Exiting.")
        return
    
    logger.info("✅ Bot instance lock acquired successfully")
    
    # Initialize async database wrapper
    from db import AsyncDBWrapper
    AsyncDBWrapper.initialize()
    logger.info("✅ Async database wrapper initialized")
    
    # Initialize database
    init_db()
    
    # Run database migrations
    logger.info("Running database migrations...")
    if not run_migrations():
        logger.error("Failed to run migrations, exiting")
        return
    
    # Run automatic notification table schema fixes
    logger.info("Running notification table schema migrations...")
    try:
        from auto_migrate_notifications import run_startup_migrations
        if not run_startup_migrations():
            logger.warning("Notification table migration failed - continuing anyway")
    except ModuleNotFoundError:
        logger.info("Notification auto-migration module not found - skipping (this is okay)")
        # Don't exit, notification issues shouldn't prevent bot startup
    
    # Initialize backup system
    logger.info("Starting backup system...")
    start_backup_system()
    
    # Warm up cache with frequently accessed data
    logger.info("Warming up cache...")
    asyncio.run(warmup_cache())
    logger.info("✅ Cache warmed up")
    
    # Create application with connection settings
    from telegram.request import HTTPXRequest
    
    # Create custom request with timeouts
    request = HTTPXRequest(
        connection_pool_size=16,
        pool_timeout=20.0,
        read_timeout=30.0,
        write_timeout=30.0,
        connect_timeout=10.0
    )
    
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .concurrent_updates(256)
        .build()
    )
    
    # Add error handler
    application.add_error_handler(global_error_handler)
    
    # Add handlers with decorators
    application.add_handler(CommandHandler("start", handle_telegram_errors(start_handler)))
    application.add_handler(CommandHandler("menu", handle_telegram_errors(menu_command)))
    application.add_handler(CommandHandler("admin", handle_telegram_errors(admin_command)))
    application.add_handler(CommandHandler("stats", handle_telegram_errors(stats_command)))
    application.add_handler(CommandHandler("pending", handle_telegram_errors(pending_command)))
    application.add_handler(CommandHandler("messages", handle_telegram_errors(messages_command)))
    application.add_handler(CommandHandler("reply", handle_telegram_errors(reply_command)))
    application.add_handler(CommandHandler("reports", handle_telegram_errors(reports_command)))
    application.add_handler(CommandHandler("users", handle_telegram_errors(users_command)))
    application.add_handler(CommandHandler("block", handle_telegram_errors(block_command)))
    application.add_handler(CommandHandler("unblock", handle_telegram_errors(unblock_command)))
    application.add_handler(CommandHandler("blocked", handle_telegram_errors(blocked_command)))
    application.add_handler(CommandHandler("broadcast", handle_telegram_errors(broadcast_command)))
    # Add media handlers before text handler (more specific handlers first)
    application.add_handler(MessageHandler(filters.PHOTO, handle_telegram_errors(handle_menu_choice)))
    application.add_handler(MessageHandler(filters.VIDEO, handle_telegram_errors(handle_menu_choice)))
    application.add_handler(MessageHandler(filters.ANIMATION, handle_telegram_errors(handle_menu_choice)))
    
    # Add text handler (must come after media handlers)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_telegram_errors(handle_menu_choice)))
    
    # Add reporting callback handlers BEFORE the general callback handler
    application.add_handler(CallbackQueryHandler(handle_telegram_errors(handle_report_reason_callback), pattern=r"^report_reason_"))
    application.add_handler(CallbackQueryHandler(handle_telegram_errors(handle_submit_report), pattern=r"^submit_report_"))
    application.add_handler(CallbackQueryHandler(handle_telegram_errors(handle_cancel_report), pattern=r"^cancel_report"))
    
    # Add ranking callback handler BEFORE the general callback handler
    application.add_handler(CallbackQueryHandler(enhanced_ranking_callback_handler, pattern=r"^(enhanced_|leaderboard_|ranking_|achievement_|missing_achievements|rank_)"))
    application.add_handler(CallbackQueryHandler(handle_telegram_errors(callback_handler)))
    
    # Log bot startup
    bot_logger.log_user_action(0, "bot_started", "University Confession Bot initialized")
    
    # Run the bot
    logger.info("Starting University Confession Bot...")
    
    try:
        # Use the standard run_polling method with proper initialization for v20+
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
        # Try alternative approach if the first fails
        try:
            logger.info("Retrying with alternative approach...")
            import asyncio
            
            async def run_bot_alternative():
                async with application:
                    await application.start()
                    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
                    await application.updater.idle()
                    
            asyncio.run(run_bot_alternative())
        except Exception as e2:
            logger.error(f"Alternative approach also failed: {e2}")
            raise

if __name__ == '__main__':
    main()







