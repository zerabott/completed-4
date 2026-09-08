#!/usr/bin/env python3
"""
Enhanced Ranking UI with Better Progress Visualization and User Experience
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from typing import List, Dict, Optional
import math
from datetime import datetime, timedelta

from enhanced_ranking_system import EnhancedPointSystem, EnhancedAchievementSystem
from enhanced_leaderboard import EnhancedLeaderboardManager, LeaderboardType
from enhanced_ranking_system import UserRank
from ranking_integration import ranking_manager
from utils import escape_markdown_text
from logger import get_logger

logger = get_logger('enhanced_ranking_ui')

def format_number_for_markdown(value: float, decimal_places: int = 1) -> str:
    """Format a number for MarkdownV2 display, escaping decimal points"""
    if decimal_places == 0:
        formatted = f"{value:.0f}"
    else:
        formatted = f"{value:.{decimal_places}f}"
    
    # Escape decimal points for MarkdownV2
    return formatted.replace('.', '\\.')

def escape_all_markdown_v2(text: str) -> str:
    """Escape all special characters for MarkdownV2"""
    # Characters that need escaping in MarkdownV2: _*[]()~`>#+-=|{}.!
    chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in chars_to_escape:
        text = text.replace(char, '\\' + char)
    
    return text

class EnhancedRankingUI:
    """Enhanced UI components with better visualizations"""
    
    @staticmethod
    def create_advanced_progress_bar(current: int, maximum: int, length: int = 15) -> str:
        """Create an advanced progress bar with realistic loading appearance"""
        if maximum == 0:
            return "█" * length + " 100% MAXED!"
        
        # Ensure we don't have negative values
        current = max(0, current)
        progress = min(current / maximum, 1.0) if maximum > 0 else 0
        filled = int(progress * length)
        empty = length - filled
        
        # Use realistic loading bar characters
        fill_char = "█"  # Solid block
        empty_char = "░"  # Light shade
        
        bar = fill_char * filled + empty_char * empty
        percentage = f"{int(progress * 100)}%"
        
        return f"{bar} {percentage}"
    
    @staticmethod
    def create_streak_visualization(streak_days: int) -> str:
        """Create visual representation of streak"""
        if streak_days == 0:
            return "📅 No streak yet - start your journey!"
        elif streak_days < 7:
            return f"🔥 {streak_days} day streak - keep it up!"
        elif streak_days < 30:
            return f"⚡ {streak_days} day streak - you're on fire!"
        elif streak_days < 90:
            return f"🚀 {streak_days} day streak - amazing dedication!"
        elif streak_days < 365:
            return f"👑 {streak_days} day streak - you're a legend!"
        else:
            return f"🌟 {streak_days} day streak - ULTIMATE DEVOTEE!"
    
    @staticmethod
    def format_enhanced_rank_display(user_rank: UserRank, user_id: int) -> str:
        """Enhanced rank display with more visual elements"""
        # Calculate progress to next rank with debugging info
        if user_rank.points_to_next > 0:
            # Direct approach: calculate what percentage of the way we are to next rank
            # If next_rank_points = 1000 and points_to_next = 200, then we're at 800/1000 = 80%
            current_points_in_rank = user_rank.next_rank_points - user_rank.points_to_next
            progress_percentage = int((current_points_in_rank / user_rank.next_rank_points) * 100)
            
            # Ensure percentage is within valid range
            progress_percentage = max(0, min(100, progress_percentage))
            
            # Create the visual progress bar
            filled_blocks = int((progress_percentage / 100) * 12)
            empty_blocks = 12 - filled_blocks
            progress_bar = f"{'█' * filled_blocks}{'░' * empty_blocks} {progress_percentage}%"
            
            next_rank_text = f"Next: {user_rank.points_to_next:,} points to go"
            
            
        else:
            progress_bar = "████████████ 100% MAXED!"
            next_rank_text = "🎉 Maximum rank achieved!"
        
        # Get streak visualization
        from db_connection import get_db_connection
        try:
            db_conn = get_db_connection()
            with db_conn.get_connection() as conn:
                cursor = conn.cursor()
                placeholder = db_conn.get_placeholder()
                cursor.execute(f"SELECT consecutive_days FROM user_rankings WHERE user_id = {placeholder}", (user_id,))
                result = cursor.fetchone()
                streak_days = result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting streak days for user {user_id}: {e}")
            streak_days = 0
        
        streak_viz = EnhancedRankingUI.create_streak_visualization(streak_days)
        
        # Special rank indicator
        rank_indicator = "⭐ SPECIAL RANK" if user_rank.is_special_rank else "📊 Standard Rank"
        
        rank_text = f"""
🏆 *YOUR RANKING STATUS*

{escape_markdown_text(user_rank.rank_emoji)} **{escape_markdown_text(user_rank.rank_name)}** {escape_markdown_text('(' + rank_indicator + ')')}
💎 **{escape_markdown_text(f'{user_rank.total_points:,}')} Total Points**

📈 *Progress to Next Rank*
{escape_markdown_text(progress_bar)}
{escape_markdown_text(next_rank_text)}

{escape_markdown_text(streak_viz)}

🎯 **{escape_markdown_text(f'{user_rank.total_points:,}')}** total points earned
🏅 **{escape_markdown_text(str(len(ranking_manager.get_user_achievements(user_id))))}** achievements unlocked
"""
        
        return rank_text
    
    @staticmethod
    def create_enhanced_ranking_keyboard(user_id: int) -> InlineKeyboardMarkup:
        """Create enhanced keyboard with more options"""
        keyboard = [
            [
                InlineKeyboardButton("🪜 Rank Ladder", callback_data="rank_ladder"),
                InlineKeyboardButton("🎯 My Achievements", callback_data="enhanced_achievements")
            ],
            [
                InlineKeyboardButton("🎁 Point Guide", callback_data="enhanced_point_guide"),
                InlineKeyboardButton("📈 Analytics", callback_data="ranking_analytics")
            ],
            [
                InlineKeyboardButton("🏠 Main Menu", callback_data="menu")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_leaderboard_selection_keyboard() -> InlineKeyboardMarkup:
        """Enhanced leaderboard selection with more options"""
        keyboard = [
            [
                InlineKeyboardButton("🔙 Back", callback_data="enhanced_rank_menu")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def format_enhanced_leaderboard(leaderboard_data: List, leaderboard_type: str, stats: Dict = None) -> str:
        """Format enhanced leaderboard with better visualization"""
        if not leaderboard_data:
            return f"""
🏆 *{leaderboard_type.title()} Leaderboard*

🎯 No participants yet\\. Be the first to earn your place\\!

💡 *Tips to get on the leaderboard:*
• Submit quality confessions
• Engage with comments
• Maintain daily streaks
• Earn achievements
"""
        
        # Title with stats
        header = f"🏆 *{leaderboard_type.title()} Leaderboard*\n\n"
        if stats:
            header += f"👥 **{escape_markdown_text(str(stats.get('total_participants', 0)))}** active participants\n"
            average_points = escape_markdown_text(f"{stats.get('average_points', 0):,}")
            highest_points = escape_markdown_text(f"{stats.get('highest_points', 0):,}")
            header += f"📊 Average: **{average_points}** points\n"
            header += f"🎯 Highest: **{highest_points}** points\n\n"
        
        leaderboard_text = header
        
        # Position emojis with more variety
        position_emojis = {
            1: "🥇", 2: "🥈", 3: "🥉", 4: "🏅", 5: "🏅",
            6: "⭐", 7: "⭐", 8: "⭐", 9: "💫", 10: "💫"
        }
        
        for entry in leaderboard_data:
            position = entry.position if hasattr(entry, 'position') else entry.get('position', 0)
            name = entry.anonymous_name if hasattr(entry, 'anonymous_name') else entry.get('anonymous_name', 'Unknown')
            points = entry.points if hasattr(entry, 'points') else entry.get('points', 0)
            rank_emoji = entry.rank_emoji if hasattr(entry, 'rank_emoji') else entry.get('rank_emoji', '🎯')
            rank_name = entry.rank_name if hasattr(entry, 'rank_name') else entry.get('rank_name', 'Student')
            
            pos_emoji = position_emojis.get(position, f"{position}\\.")
            
            # Add badges if available
            badges_str = ""
            if hasattr(entry, 'special_badges') and entry.special_badges:
                badges_str = " " + " ".join(entry.special_badges[:2])  # Show max 2 badges
            
            # Add streak indicator
            streak_str = ""
            if hasattr(entry, 'streak_days') and entry.streak_days > 0:
                if entry.streak_days >= 30:
                    streak_str = " 🔥"
                elif entry.streak_days >= 7:
                    streak_str = " ⚡"
            
            leaderboard_text += (
                f"{pos_emoji} {escape_markdown_text(rank_emoji)} "
                f"**{escape_markdown_text(name)}**{badges_str}{streak_str}\\n"
                f"     {escape_markdown_text(rank_name)} • **{escape_markdown_text(f'{points:,}')}** points\\n\\n"
            )
        
        leaderboard_text += "🚀 *Keep climbing the ranks\\!*"
        return leaderboard_text
    
    @staticmethod
    def format_enhanced_achievements(achievements: List[Dict], user_achievements_count: int) -> str:
        """Enhanced achievements display with categories and progress - Plain text format"""
        if not achievements:
            return """🎯 YOUR ACHIEVEMENTS

🌟 No achievements unlocked yet!

💡 Start earning achievements by:
• Posting your first confession
• Making your first comment  
• Building daily streaks
• Getting likes on your content
• Participating in community events

🎁 Each achievement rewards you with bonus points!"""
        
        # Group achievements by category
        categories = {}
        for achievement in achievements:
            category = achievement.get('category', 'General')
            if category not in categories:
                categories[category] = []
            categories[category].append(achievement)
        
        # Sort categories by importance
        category_order = ['milestone', 'content', 'engagement', 'popularity', 'streak', 'quality', 'community', 'seasonal', 'secret', 'time', 'points', 'meta']
        sorted_categories = []
        for cat in category_order:
            if cat in [c.lower() for c in categories.keys()]:
                # Find the actual category name (with proper case)
                actual_cat = next(c for c in categories.keys() if c.lower() == cat)
                sorted_categories.append(actual_cat)
        # Add any remaining categories not in the order list
        for cat in categories.keys():
            if cat not in sorted_categories:
                sorted_categories.append(cat)
        
        achievements_text = f"🎯 YOUR ACHIEVEMENTS ({len(achievements)} earned)\n\n"
        
        # Category emojis
        category_emojis = {
            'milestone': '🎯', 'content': '📝', 'engagement': '💬',
            'popularity': '🔥', 'streak': '⚡', 'quality': '💎',
            'community': '🤝', 'seasonal': '🎪', 'secret': '🔮',
            'time': '⏰', 'points': '💰', 'meta': '🏅', 'general': '🏆'
        }
        
        for category in sorted_categories:
            if category not in categories:
                continue
                
            cat_achievements = categories[category]
            emoji = category_emojis.get(category.lower(), '🏆')
            
            # Clean category display
            achievements_text += "━━━━━━━━━━━━━━━━━━━━━━━\n"
            achievements_text += f"{emoji} {category.upper()} ({len(cat_achievements)} unlocked)\n\n"
            
            # Show achievements in this category (max 4 for better readability)
            for i, achievement in enumerate(cat_achievements[:4]):
                special_mark = "⭐" if achievement.get('is_special') else "🏅"
                
                # Format date more nicely
                date_value = achievement.get('date')
                if date_value:
                    if isinstance(date_value, str):
                        # If it's already a string, try to format it nicely
                        try:
                            from datetime import datetime
                            parsed_date = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                            date_str = parsed_date.strftime('%b %d, %Y')
                        except:
                            date_str = date_value[:10] if len(date_value) >= 10 else date_value
                    else:
                        # datetime object
                        date_str = date_value.strftime('%b %d, %Y')
                else:
                    date_str = "Recent"
                
                # Clean achievement name and description
                name = achievement.get('name', 'Unknown Achievement')
                description = achievement.get('description', 'No description available')
                points = achievement.get('points', 0)
                
                # Truncate long descriptions
                if len(description) > 60:
                    description = description[:60] + "..."
                
                achievements_text += (
                    f"{special_mark} {name}\n"
                    f"   📝 {description}\n"
                    f"   💰 +{points} points • 📅 {date_str}\n\n"
                )
            
            # Show count if there are more achievements in this category
            if len(cat_achievements) > 4:
                remaining = len(cat_achievements) - 4
                achievements_text += f"   📋 ...and {remaining} more in this category\n\n"
        
        # Achievement progress summary
        try:
            total_possible = len(EnhancedAchievementSystem().get_all_achievements())
        except:
            total_possible = 50  # fallback estimate
            
        progress = (len(achievements) / total_possible) * 100 if total_possible > 0 else 0
        
        achievements_text += "━━━━━━━━━━━━━━━━━━━━━━━\n"
        achievements_text += f"📊 PROGRESS SUMMARY\n\n"
        achievements_text += f"🏆 Achievements Unlocked: {len(achievements)}/{total_possible}\n"
        achievements_text += f"📈 Completion Rate: {progress:.1f}%\n"
        
        # Progress bar visualization
        progress_blocks = int(progress / 10)  # 10 blocks total
        progress_bar = "█" * progress_blocks + "░" * (10 - progress_blocks)
        achievements_text += f"📊 [{progress_bar}] {progress:.1f}%\n\n"
        
        # Total points from achievements
        total_points = sum(achievement.get('points', 0) for achievement in achievements)
        achievements_text += f"💎 Total Achievement Points: {total_points:,}\n"
        achievements_text += "🚀 Keep unlocking more achievements!"
        
        return achievements_text
    
    @staticmethod
    def format_enhanced_point_guide() -> str:
        """Enhanced point earning guide with better organization"""
        return """
🎁 *COMPLETE POINT EARNING GUIDE*

*🏆 CONFESSION ACTIVITIES*
📝 Submit confession: **\\+0** points \\(awaiting approval\\)
✅ Confession approved: **\\+50** points
🔥 Confession featured: **\\+75** points
👍 Each like received: **\\+3** points \\(with multipliers\\)
🌟 Trending post: **\\+125** points
💯 100\\+ likes: **\\+150** points bonus
🚀 Viral confession \\(200\\+ likes\\): **\\+200** points
⭐ Popular confession: **\\+100** points

*💬 ENGAGEMENT ACTIVITIES*  
💭 Post comment: **\\+8** points
👍 Comment liked: **\\+2** points \\(with multipliers\\)
💎 Quality comment: **\\+30** points
🎯 Helpful comment: **\\+25** points
🔥 Viral comment \\(50\\+ likes\\): **\\+50** points
💬 Thread starter: **\\+15** points
🗣️ Discussion spark \\(10\\+ replies\\): **\\+40** points

*⚡ STREAK & DAILY BONUSES*
📅 Daily login: **\\+5** points
🔥 Consecutive days \\(3\\+\\): **\\+10\\+** points/day with multipliers
📅 Week streak: **\\+50** points
📆 Month streak: **\\+200** points  
🏆 Quarter streak \\(90 days\\): **\\+500** points
👑 Year streak \\(365 days\\): **\\+1000** points

*🤝 SOCIAL & COMMUNITY ACTIVITIES*
👍 Give reaction: **\\+2** points
🤝 Help others: **\\+20** points
😊 Positive interaction: **\\+10** points
🆘 Community support: **\\+25** points
🎓 Mentor activity: **\\+30** points
🏛️ Community contribution: **\\+50** points

*🎁 SPECIAL & MILESTONE BONUSES*
🎯 First confession: **\\+75** points
💬 First comment: **\\+30** points
🏅 Achievement earned: **\\+25** points
🏁 Milestone reached: **\\+150** points
🎪 Seasonal participation: **\\+75** points
📚 Educational content: **\\+35** points
🎨 Creative content: **\\+30** points
💡 Discussion catalyst: **\\+45** points
💎 High quality content: **\\+40** points

*🎉 TIME & EVENT BONUSES*
🌙 Night owl \\(10PM\\-6AM\\): **\\+5%** bonus
🎉 Weekend posting: **\\+10%** bonus
🌅 Weekend bonus: **\\+5** points
🎄 Holiday bonus: **\\+10** points
🎂 Anniversary bonus: **\\+15** points
🎊 Milestone celebration: **\\+20** points
📝 Feedback participation: **\\+25** points

*🚫 POINT PENALTIES*
❌ Content rejected: **\\-3** points
⚠️ Spam detected: **\\-10** points
🚨 Inappropriate content: **\\-20** points
😤 Excessive negativity: **\\-15** points

*⚡ MULTIPLIERS & BONUSES*
• **Length Bonus:** Long content \\(200\\+ chars\\) gets \\+8 points
• **Quality Bonus:** Admin\\-rated content gets up to 50% more points
• **Engagement Multiplier:** Popular content gets 2\\-5x points per like
• **Streak Multiplier:** Up to 3x daily bonus for long streaks
• **Time Bonus:** Night and weekend posting gets extra percentage

*💡 PRO TIPS*
• Write longer, thoughtful content for bonuses
• Maintain daily activity to build powerful streaks  
• Quality over quantity always wins
• Engage positively with community members
• Participate in seasonal events and milestones
• Help new users and contribute to discussions
• Be creative and educational in your posts

🚀 *The more you contribute meaningfully, the faster you climb\\!*
"""

async def show_enhanced_ranking_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show enhanced ranking menu with better UI"""
    user_id = update.effective_user.id
    user_rank = ranking_manager.get_user_rank(user_id)
    
    if not user_rank:
        ranking_manager.initialize_user_ranking(user_id)
        user_rank = ranking_manager.get_user_rank(user_id)
    
    if not user_rank:
        await update.message.reply_text("❗ Error loading ranking information. Please try again.")
        return
    
    rank_display = EnhancedRankingUI.format_enhanced_rank_display(user_rank, user_id)
    keyboard = EnhancedRankingUI.create_enhanced_ranking_keyboard(user_id)
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                rank_display,
                parse_mode="MarkdownV2",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Error editing enhanced ranking message: {e}")
            await update.callback_query.answer("Error updating display. Please try again.")
    else:
        await update.message.reply_text(
            rank_display,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )

async def show_enhanced_leaderboard_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show enhanced leaderboard selection"""
    keyboard = EnhancedRankingUI.create_leaderboard_selection_keyboard()
    
    text = """
🏆 *COMMUNITY LEADERBOARDS*

Choose your preferred timeframe to see the top contributors:

📅 **This Week:** Current weekly champions
📆 **This Month:** Monthly top performers  
🗓️ **This Quarter:** 90\\-day elite members
📅 **This Year:** Annual ranking leaders
⭐ **All Time:** Legendary hall of fame

🔒 *Privacy Protected:* All names are anonymized
🏅 *Fair Competition:* Multiple categories available
"""
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="MarkdownV2",
            reply_markup=keyboard
        )

async def show_enhanced_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE, leaderboard_type: str):
    """Show enhanced leaderboard for specific timeframe"""
    leaderboard_manager = EnhancedLeaderboardManager()
    
    # Map string to enum
    type_mapping = {
        'weekly': LeaderboardType.WEEKLY,
        'monthly': LeaderboardType.MONTHLY,  
        'quarterly': LeaderboardType.QUARTERLY,
        'yearly': LeaderboardType.YEARLY,
        'alltime': LeaderboardType.ALL_TIME
    }
    
    lb_type = type_mapping.get(leaderboard_type, LeaderboardType.ALL_TIME)
    leaderboard = leaderboard_manager.get_enhanced_leaderboard(lb_type, limit=10, user_id=update.effective_user.id)
    stats = leaderboard_manager.get_leaderboard_stats(lb_type)
    
    leaderboard_text = EnhancedRankingUI.format_enhanced_leaderboard(leaderboard, leaderboard_type, stats)
    
    keyboard = [
        [
            InlineKeyboardButton("📅 Weekly", callback_data="enhanced_leaderboard_weekly"),
            InlineKeyboardButton("📆 Monthly", callback_data="enhanced_leaderboard_monthly"),
        ],
        [
            InlineKeyboardButton("🗓️ Quarterly", callback_data="enhanced_leaderboard_quarterly"),
            InlineKeyboardButton("📅 Yearly", callback_data="enhanced_leaderboard_yearly")
        ],
        [
            InlineKeyboardButton("⭐ All Time", callback_data="enhanced_leaderboard_alltime"),
            InlineKeyboardButton("🔙 Back", callback_data="enhanced_leaderboard")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            leaderboard_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )

async def show_enhanced_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show enhanced achievements display"""
    user_id = update.effective_user.id
    achievements = ranking_manager.get_user_achievements(user_id, limit=50)  # Get more for categorization
    
    # Get total achievement count
    user_rank = ranking_manager.get_user_rank(user_id)
    achievement_count = user_rank.total_points if user_rank else 0
    
    achievements_text = EnhancedRankingUI.format_enhanced_achievements(achievements, achievement_count)
    
    keyboard = [
        [
            InlineKeyboardButton("🔙 Back", callback_data="enhanced_rank_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            achievements_text,
            reply_markup=reply_markup
        )

async def show_enhanced_point_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show enhanced point earning guide"""
    guide_text = EnhancedRankingUI.format_enhanced_point_guide()
    
    keyboard = [
        [
            InlineKeyboardButton("🔙 Back", callback_data="enhanced_rank_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            guide_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )

async def show_enhanced_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed stats with back button only"""
    stats_text = """
📊 *DETAILED STATS*

😧 Detailed statistics coming soon\\!

📊 This section will include:
• Detailed point breakdown
• Activity patterns
• Performance analytics
• Engagement metrics
• Progress tracking

Check back later for updates\\!
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🔙 Back", callback_data="enhanced_rank_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            stats_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )

async def show_enhanced_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show progress tracking with back button only"""
    progress_text = """
🔥 *MY PROGRESS*

😧 Progress tracking coming soon\\!

📈 This section will include:
• Visual progress charts
• Goal tracking
• Milestone countdown
• Achievement roadmap
• Performance trends

Check back later for updates\\!
"""
    
    keyboard = [
        [
            InlineKeyboardButton("🔙 Back", callback_data="enhanced_rank_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            progress_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )

async def show_ranking_analytics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show comprehensive ranking analytics with real data"""
    from analytics import analytics_manager
    from datetime import date, timedelta
    
    try:
        # Get user ID for personalized analytics
        user_id = update.effective_user.id
        
        # Get analytics data - will gracefully handle missing data
        logger.info("Fetching analytics data for ranking analytics display")
        
        # Update daily stats first
        try:
            analytics_manager.update_daily_stats()
        except Exception as e:
            logger.warning(f"Could not update daily stats: {e}")
        
        # Get analytics data with error handling
        weekly_stats = {}
        category_data = {}
        engagement_data = {}
        
        try:
            # Get weekly trends (fall back to fewer weeks if data is sparse)
            weekly_stats = analytics_manager.get_weekly_stats(weeks_back=2)
        except Exception as e:
            logger.warning(f"Could not get weekly stats: {e}")
            weekly_stats = {'error': str(e)}
        
        try:
            # Get category analytics
            category_data = analytics_manager.get_category_analytics(days_back=14)
        except Exception as e:
            logger.warning(f"Could not get category analytics: {e}")
            category_data = {'error': str(e)}
        
        try:
            # Get user engagement metrics
            engagement_data = analytics_manager.get_user_engagement_metrics(days_back=14)
        except Exception as e:
            logger.warning(f"Could not get engagement data: {e}")
            engagement_data = {'error': str(e)}
        
        # Format analytics text with error handling
        analytics_text = "📈 *RANKING ANALYTICS*\n\n"
        
        # Weekly trends section
        if weekly_stats and 'error' not in weekly_stats:
            summary = weekly_stats.get('summary', {})
            trends = weekly_stats.get('trends', {})
            
            analytics_text += "📊 *Weekly Performance*\n"
            if summary.get('avg_weekly_confessions', 0) > 0:
                analytics_text += f"• Avg Confessions: {format_number_for_markdown(summary['avg_weekly_confessions'])}/week\n"
            if summary.get('avg_weekly_comments', 0) > 0:
                analytics_text += f"• Avg Comments: {format_number_for_markdown(summary['avg_weekly_comments'])}/week\n"
            if summary.get('avg_weekly_new_users', 0) > 0:
                analytics_text += f"• New Users: {format_number_for_markdown(summary['avg_weekly_new_users'])}/week\n"
            
            # Show trends if available
            if trends:
                analytics_text += "\n📈 *Recent Trends:*\n"
                for key, trend in trends.items():
                    if abs(trend) > 5:  # Only show significant trends
                        trend_emoji = "📈" if trend > 0 else "📉"
                        key_display = key.replace('_', ' ').title()
                        trend_formatted = f"{trend:+.1f}".replace('.', '\\.')
                        analytics_text += f"{trend_emoji} {key_display}: {trend_formatted}%\n"
        else:
            analytics_text += "📊 *Weekly Performance*\n• Building analytics data\\.\\.\\.\\."
        
        analytics_text += "\n\n"
        
        # Category insights section
        if category_data and 'error' not in category_data:
            category_stats = category_data.get('category_stats', {})
            trending_cats = category_data.get('trending_categories', [])
            
            analytics_text += "🏷️ *Category Insights*\n"
            
            # Top categories
            if category_stats:
                sorted_categories = sorted(
                    category_stats.items(), 
                    key=lambda x: x[1]['post_count'], 
                    reverse=True
                )[:3]
                
                for i, (cat_name, cat_data) in enumerate(sorted_categories, 1):
                    emoji = ["🥇", "🥈", "🥉"][i-1]
                    analytics_text += f"{emoji} {escape_markdown_text(cat_name)}: {cat_data['post_count']} posts \\({format_number_for_markdown(cat_data['percentage'])}%\\)\n"
            
            # Trending categories
            if trending_cats:
                analytics_text += "\n🔥 *Trending Categories:*\n"
                for cat in trending_cats[:2]:  # Show top 2 trending
                    analytics_text += f"• {escape_markdown_text(cat['category'])}: \\+{format_number_for_markdown(cat['growth_rate'], 0)}% growth\n"
        else:
            analytics_text += "🏷️ *Category Insights*\n• Analyzing category trends\\.\\.\\.\\."
        
        analytics_text += "\n\n"
        
        # User engagement section
        if engagement_data and 'error' not in engagement_data:
            analytics_text += "👥 *Community Engagement*\n"
            
            # Engagement levels
            engagement_levels = engagement_data.get('engagement_levels', {})
            total_users = sum(engagement_levels.values()) if engagement_levels else 0
            
            if total_users > 0:
                highly_active = engagement_levels.get('highly_active', 0)
                moderately_active = engagement_levels.get('moderately_active', 0)
                
                analytics_text += f"• Total Active Users: {total_users}\n"
                if highly_active > 0:
                    analytics_text += f"• Highly Active: {highly_active} \\({format_number_for_markdown(highly_active/total_users*100, 0)}%\\)\n"
                if moderately_active > 0:
                    analytics_text += f"• Moderately Active: {moderately_active} \\({format_number_for_markdown(moderately_active/total_users*100, 0)}%\\)\n"
            
            # Retention rate
            retention_rate = engagement_data.get('retention_rate', 0)
            if retention_rate > 0:
                analytics_text += f"• Retention Rate: {format_number_for_markdown(retention_rate)}%\n"
        else:
            analytics_text += "👥 *Community Engagement*\n• Calculating engagement metrics\\.\\.\\.\\."
        
        analytics_text += "\n\n"
        
        # Personal ranking context for the user
        try:
            user_rank = ranking_manager.get_user_rank(user_id)
            if user_rank:
                analytics_text += "🎯 *Your Position*\n"
                analytics_text += f"• Current Rank: {escape_markdown_text(user_rank.rank_emoji)} {escape_markdown_text(user_rank.rank_name)}\n"
                analytics_text += f"• Total Points: {escape_markdown_text(f'{user_rank.total_points:,}')}\n"
                
                if user_rank.points_to_next > 0:
                    analytics_text += f"• Next Rank: {escape_markdown_text(f'{user_rank.points_to_next:,}')} points away\n"
                else:
                    analytics_text += f"• Status: Maximum rank achieved\\! 🎉\n"
        except Exception as e:
            logger.warning(f"Could not get user rank for analytics: {e}")
        
        # Footer
        analytics_text += "\n💡 *Analytics updated in real\\-time*"
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="ranking_analytics"),
                InlineKeyboardButton("🔙 Back", callback_data="enhanced_rank_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
    except Exception as e:
        logger.error(f"Error generating ranking analytics: {e}")
        # Fallback error message
        analytics_text = """
📈 *RANKING ANALYTICS*

⚠️ *Analytics temporarily unavailable*

We're experiencing technical difficulties loading the analytics data\\. This usually happens when:
• The bot is newly deployed
• Database is being updated
• Not enough data has been collected yet

Please try again in a few minutes\\!

💡 *Tip:* Analytics become more accurate as more users participate in the community\\.
"""
        
        keyboard = [
            [
                InlineKeyboardButton("🔄 Try Again", callback_data="ranking_analytics"),
                InlineKeyboardButton("🔙 Back", callback_data="enhanced_rank_menu")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            analytics_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )

# Enhanced callback handlers
async def enhanced_ranking_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle enhanced ranking system callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "enhanced_rank_menu":
        await show_enhanced_ranking_menu(update, context)
    elif data == "rank_ladder":
        # Import and show rank ladder
        from rank_ladder import show_rank_ladder
        await show_rank_ladder(update, context)
    elif data == "enhanced_achievements":
        await show_enhanced_achievements(update, context)
    elif data == "enhanced_point_guide":
        await show_enhanced_point_guide(update, context)
    elif data == "enhanced_progress":
        # Show progress tracking with back button
        await show_enhanced_progress(update, context)
    elif data == "seasonal_competitions":
        # Could implement seasonal competitions view
        await query.answer("😧 Seasonal events coming soon!")
    elif data == "ranking_analytics":
        # Show analytics with back button
        await show_ranking_analytics(update, context)
    else:
        await query.answer("Unknown enhanced ranking option.")
