"""
Helper functions for the enhanced profile system.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from db import get_user_profile, upsert_user_profile, get_user_active_chats, get_user_pending_requests, get_blocked_users, unblock_profile_user
from utils import escape_markdown_text

logger = logging.getLogger(__name__)


async def handle_emoji_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle emoji selection from the emoji menu."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    if not profile:
        await query.answer("Profile not found!", show_alert=True)
        return
    
    # Extract emoji from callback data
    emoji_data = query.data.replace("emoji_", "")
    emoji = "" if emoji_data == "none" else emoji_data
    
    # Update profile with new emoji
    upsert_user_profile(
        user_id,
        profile['display_name'],
        emoji,
        profile['bio'],
        profile['is_active'],
        profile.get('gender', ''),
        profile.get('age'),
        profile.get('department', ''),
        profile.get('year', ''),
        profile.get('religion', ''),
        profile.get('relationship_status', ''),
        profile.get('other_info', '')
    )
    
    # Show updated profile
    from bot import send_profile_overview
    updated_profile = get_user_profile(user_id)
    await send_profile_overview(update, context, updated_profile)


async def show_edit_details_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show menu for editing optional profile details."""
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    # Display current values
    gender = profile.get('gender') or 'Not set'
    age = str(profile.get('age')) if profile.get('age') else 'Not set'
    department = profile.get('department') or 'Not set'
    year = profile.get('year') or 'Not set'
    religion = profile.get('religion') or 'Not set'
    relationship = profile.get('relationship_status') or 'Not set'
    other = profile.get('other_info') or 'Not set'
    
    text = (
        f"📄 *Edit Details \\(Optional\\)*\\n\\n"
        f"*Current Values:*\\n"
        f"Gender: {escape_markdown_text(gender)}\\n"
        f"Age: {escape_markdown_text(age)}\\n"
        f"Department: {escape_markdown_text(department)}\\n"
        f"Year: {escape_markdown_text(year)}\\n"
        f"Religion: {escape_markdown_text(religion)}\\n"
        f"Relationship: {escape_markdown_text(relationship)}\\n"
        f"Other Info: {escape_markdown_text(other[:30] + '...' if len(other) > 30 else other)}\\n\\n"
        f"Choose a field to edit:"
    )
    
    buttons = [
        [InlineKeyboardButton("👤 Gender", callback_data="edit_gender")],
        [InlineKeyboardButton("🎂 Age", callback_data="edit_age")],
        [InlineKeyboardButton("🎓 Department", callback_data="edit_department")],
        [InlineKeyboardButton("📅 Year", callback_data="edit_year")],
        [InlineKeyboardButton("🕌 Religion", callback_data="edit_religion")],
        [InlineKeyboardButton("💑 Relationship Status", callback_data="edit_relationship")],
        [InlineKeyboardButton("📝 Other Info", callback_data="edit_other_info")],
        [InlineKeyboardButton("🔙 Back", callback_data="profile_edit_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    # Handle both callback query and message updates
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2",
        )
    else:
        # For message updates (after text input)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="MarkdownV2",
        )


async def show_gender_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show gender selection menu."""
    text = (
        "👤 *Select Gender*\n\n"
        "Choose your gender:\\."
    )
    
    buttons = [
        [InlineKeyboardButton("👨 Male", callback_data="gender_Male")],
        [InlineKeyboardButton("👩 Female", callback_data="gender_Female")],
        [InlineKeyboardButton("🚫 Prefer not to say", callback_data="gender_none")],
        [InlineKeyboardButton("🔙 Back", callback_data="edit_details")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def handle_gender_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gender selection."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    if not profile:
        await query.answer("Profile not found!", show_alert=True)
        return
    
    gender_data = query.data.replace("gender_", "")
    gender = "" if gender_data == "none" else gender_data
    
    # Update profile with new gender
    upsert_user_profile(
        user_id,
        profile['display_name'],
        profile['emoji'],
        profile['bio'],
        profile['is_active'],
        gender,
        profile.get('age'),
        profile.get('department', ''),
        profile.get('year', ''),
        profile.get('religion', ''),
        profile.get('relationship_status', ''),
        profile.get('other_info', '')
    )
    
    await show_edit_details_menu(update, context)


async def show_year_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show year/level selection menu."""
    text = (
        "📅 *Select Year*\n\n"
        "Choose your current year/level:\\."
    )
    
    buttons = [
        [InlineKeyboardButton("1️⃣ 1st Year", callback_data="year_1st Year"),
         InlineKeyboardButton("2️⃣ 2nd Year", callback_data="year_2nd Year")],
        [InlineKeyboardButton("3️⃣ 3rd Year", callback_data="year_3rd Year"),
         InlineKeyboardButton("4️⃣ 4th Year", callback_data="year_4th Year")],
        [InlineKeyboardButton("5️⃣ 5th Year", callback_data="year_5th Year"),
         InlineKeyboardButton("🎓 Graduate", callback_data="year_Graduate")],
        [InlineKeyboardButton("🚫 Prefer not to say", callback_data="year_none")],
        [InlineKeyboardButton("🔙 Back", callback_data="edit_details")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def handle_year_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle year selection."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    if not profile:
        await query.answer("Profile not found!", show_alert=True)
        return
    
    year_data = query.data.replace("year_", "")
    year = "" if year_data == "none" else year_data
    
    # Update profile with new year
    upsert_user_profile(
        user_id,
        profile['display_name'],
        profile['emoji'],
        profile['bio'],
        profile['is_active'],
        profile.get('gender', ''),
        profile.get('age'),
        profile.get('department', ''),
        year,
        profile.get('religion', ''),
        profile.get('relationship_status', ''),
        profile.get('other_info', '')
    )
    
    await show_edit_details_menu(update, context)


async def show_relationship_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show relationship status selection menu."""
    text = (
        "💑 *Select Relationship Status*\n\n"
        "Choose your current status:\\."
    )
    
    buttons = [
        [InlineKeyboardButton("💚 Single", callback_data="relationship_Single")],
        [InlineKeyboardButton("❤️ In a relationship", callback_data="relationship_In a relationship")],
        [InlineKeyboardButton("💍 Engaged", callback_data="relationship_Engaged")],
        [InlineKeyboardButton("💑 Married", callback_data="relationship_Married")],
        [InlineKeyboardButton("💔 It's complicated", callback_data="relationship_It's complicated")],
        [InlineKeyboardButton("🚫 Prefer not to say", callback_data="relationship_none")],
        [InlineKeyboardButton("🔙 Back", callback_data="edit_details")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def handle_relationship_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle relationship status selection."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    
    if not profile:
        await query.answer("Profile not found!", show_alert=True)
        return
    
    relationship_data = query.data.replace("relationship_", "")
    relationship = "" if relationship_data == "none" else relationship_data
    
    # Update profile with new relationship status
    upsert_user_profile(
        user_id,
        profile['display_name'],
        profile['emoji'],
        profile['bio'],
        profile['is_active'],
        profile.get('gender', ''),
        profile.get('age'),
        profile.get('department', ''),
        profile.get('year', ''),
        profile.get('religion', ''),
        relationship,
        profile.get('other_info', '')
    )
    
    await show_edit_details_menu(update, context)


async def show_previous_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's previous/active chats."""
    user_id = update.effective_user.id
    chats = get_user_active_chats(user_id)
    
    if not chats:
        text = (
            "💬 *Previous Chats*\\n\\n"
            "You don\\'t have any active chats yet\\.\\n\\n"
            "Start chatting with other users by visiting their profiles\\!"
        )
        buttons = [[InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")]]
    else:
        text = (
            "💬 *Previous Chats*\\n\\n"
            "Select a chat to continue:"
        )
        buttons = []
        for chat in chats[:10]:  # Limit to 10 most recent
            # Determine the other user's ID
            other_user_id = chat['user_b_id'] if chat['user_a_id'] == user_id else chat['user_a_id']
            other_profile = get_user_profile(other_user_id)
            
            if other_profile:
                name = (other_profile.get('emoji', '') + ' ' + other_profile.get('display_name', '')).strip()
                if not name:
                    name = f"User {other_user_id}"
            else:
                name = f"User {other_user_id}"
            
            buttons.append([InlineKeyboardButton(
                f"💬 {name}",
                callback_data=f"resume_chat_{chat['id']}"
            )])
        
        buttons.append([InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def resume_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume a previous chat session."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Extract contact ID from callback data
    contact_id = int(query.data.replace("resume_chat_", ""))
    
    from db import get_profile_contact_by_id, is_profile_blocked_either_way
    
    contact = get_profile_contact_by_id(contact_id)
    if not contact:
        await query.answer("Chat not found!")
        return
    
    # Determine the other user
    other_user_id = contact['user_b_id'] if contact['user_a_id'] == user_id else contact['user_a_id']
    
    # Check if blocked
    if is_profile_blocked_either_way(user_id, other_user_id):
        await query.edit_message_text(
            "🚫 *Chat Not Available*\\n\\n"
            "This chat is no longer available\\.",
            parse_mode="MarkdownV2",
        )
        return
    
    # Set up chat session
    context.user_data['state'] = 'profile_chat'
    context.user_data['profile_chat_partner'] = other_user_id
    context.user_data['profile_contact_id'] = contact_id
    # Set reply mode to True so messages can be sent
    context.user_data['reply_mode_active'] = True
    
    other_profile = get_user_profile(other_user_id)
    if other_profile:
        name = (other_profile.get('emoji', '') + ' ' + other_profile.get('display_name', '')).strip()
        if not name:
            name = f"User {other_user_id}"
    else:
        name = f"User {other_user_id}"
    
    text = (
        "💬 *Chat Resumed*\n\n"
        f"You're now chatting with {escape_markdown_text(name)}\.\n\n"
        "📤 *Send a message*\n"
        "Type your message and press Send\n\n"
        "⚙️ *Chat controls*\n"
        "Use the buttons to end the chat or go to the main menu\."
    )
    
    buttons = [
        [InlineKeyboardButton("🔚 End Chat", callback_data=f"profile_end_{contact_id}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )
    # Send clear instructions about how to use the resumed chat
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=(
            "💬 *How this chat works*\n\n"
            "• Type your message and press Send\n"
            "• I'll deliver it to the other user\n"
            "• Use the buttons below to end or block\n\n"
            "🔄 *Ready to continue chatting?*"
        ),
        parse_mode="MarkdownV2",
    )


async def show_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's inbox with pending contact requests."""
    user_id = update.effective_user.id
    pending_requests = get_user_pending_requests(user_id)
    
    if not pending_requests:
        text = (
            "📥 *Inbox*\n\n"
            "You don't have any pending contact requests\.\n\n"
            "When someone wants to chat with you, their request will appear here\!"
        )
        buttons = [[InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")]]
    else:
        text = (
            "📥 *Inbox*\\n\\n"
            f"You have {len(pending_requests)} pending contact request{'s' if len(pending_requests) > 1 else ''}\\:"
        )
        buttons = []
        for request in pending_requests[:10]:  # Limit to 10 most recent
            # Determine the requester (initiator)
            requester_id = request['initiator_id']
            requester_profile = get_user_profile(requester_id)
            
            if requester_profile:
                name = (requester_profile.get('emoji', '') + ' ' + requester_profile.get('display_name', '')).strip()
                if not name:
                    name = f"User {requester_id}"
            else:
                name = f"User {requester_id}"
            
            buttons.append([
                InlineKeyboardButton(
                    f"💌 {name}",
                    callback_data=f"view_request_{request['id']}"
                )
            ])
        
        buttons.append([InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def show_contact_request_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show details of a specific contact request with accept/decline options."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    # Extract contact ID from callback data
    contact_id = int(query.data.replace("view_request_", ""))
    
    from db import get_profile_contact_by_id
    
    contact = get_profile_contact_by_id(contact_id)
    if not contact or contact['status'] != 'pending':
        await query.edit_message_text(
            "❗ *Request Not Available*\\n\\n"
            "This contact request is no longer available\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Inbox", callback_data="profile_inbox")
            ]])
        )
        return
    
    # Get requester info
    requester_id = contact['initiator_id']
    requester_profile = get_user_profile(requester_id)
    
    if requester_profile:
        name_raw = (requester_profile.get('emoji', '') + ' ' + requester_profile.get('display_name', '')).strip()
        name = escape_markdown_text(name_raw if name_raw else f"User {requester_id}")
        bio = requester_profile.get('bio', '')
        bio_display = escape_markdown_text(bio[:100] + '...' if len(bio) > 100 else bio) if bio else escape_markdown_text("No bio")
    else:
        name = escape_markdown_text(f"User {requester_id}")
        bio_display = escape_markdown_text("No bio")
    
    text = (
        "📬 *Contact request*\n\n"
        f"From: {name}\n"
        f"Bio: {bio_display}\n\n"
        "🤔 *Choose an option below*\."
    )
    
    buttons = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"profile_accept_{contact_id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"profile_decline_{contact_id}")
        ],
        [
            InlineKeyboardButton("🚫 Block User", callback_data=f"profile_block_requester_{contact_id}")
        ],
        [
            InlineKeyboardButton("👤 Show Profile", callback_data=f"profile_show_requester_{requester_id}_from_{contact_id}"),
            InlineKeyboardButton("🔙 Back to Inbox", callback_data="profile_inbox")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def show_friends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's friends list (active contacts)."""
    user_id = update.effective_user.id
    friends = get_user_active_chats(user_id)
    
    if not friends:
        text = (
            "👥 *Friends*\n\n"
            "You don't have any active chats yet\.\n\n"
            "Start by chatting with other users through their profiles\. "
            "Once you accept a chat request, they'll appear here\!"
        )
        buttons = [[InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")]]
    else:
        text = (
            "👥 *Friends*\\n\\n"
            f"You have {len(friends)} friend{'s' if len(friends) != 1 else ''}\\. "
            "Click to view profile or chat\\:"
        )
        buttons = []
        for friend in friends[:20]:  # Limit to 20 most recent
            # Determine the friend's ID
            friend_id = friend['user_b_id'] if friend['user_a_id'] == user_id else friend['user_a_id']
            friend_profile = get_user_profile(friend_id)
            
            if friend_profile:
                name = (friend_profile.get('emoji', '') + ' ' + friend_profile.get('display_name', '')).strip()
                if not name:
                    name = f"User {friend_id}"
            else:
                name = f"User {friend_id}"
            
            buttons.append([InlineKeyboardButton(
                f"👤 {name}",
                callback_data=f"view_friend_{friend['id']}"
            )])
        
        buttons.append([InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def show_friend_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show friend profile with options to chat or remove friend."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    # Extract contact ID from callback data
    contact_id = int(query.data.replace("view_friend_", ""))
    
    from db import get_profile_contact_by_id, is_profile_blocked_either_way
    
    contact = get_profile_contact_by_id(contact_id)
    if not contact or contact['status'] != 'active':
        await query.edit_message_text(
            "❗ *Friend Not Available*\\n\\n"
            "This friendship is no longer active\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Friends", callback_data="profile_friends")
            ]])
        )
        return
    
    # Get friend info
    friend_id = contact['user_b_id'] if contact['user_a_id'] == user_id else contact['user_a_id']
    
    # Check if blocked
    if is_profile_blocked_either_way(user_id, friend_id):
        await query.edit_message_text(
            "🚫 *Cannot View Friend*\\n\\n"
            "This user is blocked\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Friends", callback_data="profile_friends")
            ]])
        )
        return
    
    friend_profile = get_user_profile(friend_id)
    
    if friend_profile:
        name_raw = (friend_profile.get('emoji', '') + ' ' + friend_profile.get('display_name', '')).strip()
        name = escape_markdown_text(name_raw if name_raw else f"User {friend_id}")
        bio = friend_profile.get('bio', '')
        bio_display = escape_markdown_text(bio[:150] + '...' if len(bio) > 150 else bio) if bio else escape_markdown_text("No bio")
    else:
        name = escape_markdown_text(f"User {friend_id}")
        bio_display = escape_markdown_text("No bio")
    
    text = (
        "👤 *Friend Profile*\\n\\n"
        f"Name: {name}\\n"
        f"Bio: {bio_display}\\n\\n"
        "🤔 *What would you like to do\\?*"
    )
    
    buttons = [
        [
            InlineKeyboardButton("💬 Chat", callback_data=f"resume_chat_{contact_id}")
        ],
        [
            InlineKeyboardButton("👁️ View Full Profile", callback_data=f"view_full_profile_{friend_id}")
        ],
        [
            InlineKeyboardButton("🚫 Remove Friend", callback_data=f"remove_friend_{contact_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Friends", callback_data="profile_friends")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def show_blocked_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of blocked users with unblock option."""
    user_id = update.effective_user.id
    blocked_list = get_blocked_users(user_id)
    
    if not blocked_list:
        text = (
            "🚫 *Blocked Users*\\n\\n"
            "You haven\\'t blocked anyone\\.\\n\\n"
            "Blocked users cannot contact you or see your active status\\."
        )
        buttons = [[InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")]]
    else:
        text = (
            "🚫 *Blocked Users*\\n\\n"
            f"You have blocked {len(blocked_list)} user{'s' if len(blocked_list) != 1 else ''}\\. "
            "Click to unblock\\:"
        )
        buttons = []
        for block in blocked_list[:20]:  # Limit to 20
            blocked_id = block['blocked_id']
            blocked_profile = get_user_profile(blocked_id)
            
            if blocked_profile:
                name = (blocked_profile.get('emoji', '') + ' ' + blocked_profile.get('display_name', '')).strip()
                if not name:
                    name = f"User {blocked_id}"
            else:
                name = f"User {blocked_id}"
            
            buttons.append([InlineKeyboardButton(
                f"🚫 {name}",
                callback_data=f"view_blocked_{blocked_id}"
            )])
        
        buttons.append([InlineKeyboardButton("🔙 Back to Profile", callback_data="back_to_profile")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )


async def show_blocked_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show blocked user details with unblock option."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    # Extract blocked user ID from callback data
    blocked_id = int(query.data.replace("view_blocked_", ""))
    
    blocked_profile = get_user_profile(blocked_id)
    
    if blocked_profile:
        name_raw = (blocked_profile.get('emoji', '') + ' ' + blocked_profile.get('display_name', '')).strip()
        name = escape_markdown_text(name_raw if name_raw else f"User {blocked_id}")
        bio = blocked_profile.get('bio', '')
        bio_display = escape_markdown_text(bio[:100] + '...' if len(bio) > 100 else bio) if bio else escape_markdown_text("No bio")
    else:
        name = escape_markdown_text(f"User {blocked_id}")
        bio_display = escape_markdown_text("No bio")
    
    text = (
        "🚫 *Blocked User*\\n\\n"
        f"Name: {name}\\n"
        f"Bio: {bio_display}\\n\\n"
        "This user is currently blocked and cannot contact you or see your profile status\\.\\n\\n"
        "🔓 *Want to unblock them\\?*"
    )
    
    buttons = [
        [
            InlineKeyboardButton("✅ Unblock User", callback_data=f"unblock_user_{blocked_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back to Blocked List", callback_data="profile_blocked_users")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="MarkdownV2",
    )



