#!/usr/bin/env python3
"""
Rank Ladder Display Module
Shows the complete hierarchy of ranks and their point requirements
"""

import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from typing import List, Dict, Tuple

from config import DB_PATH
from utils import escape_markdown_text
from logger import get_logger
from ranking_integration import ranking_manager

logger = get_logger('rank_ladder')

class RankLadderDisplay:
    """Display complete rank hierarchy and user's position in it"""
    
    @staticmethod
    def get_all_ranks() -> List[Dict]:
        """Get all rank definitions from the database"""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT rank_id, rank_name, rank_emoji, min_points, max_points, 
                           special_perks, is_special
                    FROM rank_definitions
                    ORDER BY min_points ASC
                """)
                
                ranks = []
                for row in cursor.fetchall():
                    rank_id, rank_name, rank_emoji, min_points, max_points, special_perks, is_special = row
                    ranks.append({
                        'rank_id': rank_id,
                        'rank_name': rank_name,
                        'rank_emoji': rank_emoji,
                        'min_points': min_points,
                        'max_points': max_points if max_points is not None else float('inf'),
                        'special_perks': special_perks,
                        'is_special': bool(is_special)
                    })
                
                return ranks
        except Exception as e:
            logger.error(f"Error getting rank definitions: {e}")
            return []
    
    @staticmethod
    def format_rank_ladder(user_id: int) -> str:
        """Format the complete rank ladder/hierarchy with user's current position"""
        ranks = RankLadderDisplay.get_all_ranks()
        if not ranks:
            return "⚠️ " + escape_markdown_text("Error loading rank information. Please try again later.")
        
        # Get user's current rank (create if doesn't exist)
        try:
            user_rank = ranking_manager.get_user_rank(user_id)
            if not user_rank:
                # Initialize user ranking if it doesn't exist
                ranking_manager.initialize_user_ranking(user_id)
                user_rank = ranking_manager.get_user_rank(user_id)
            
            user_total_points = user_rank.total_points if user_rank else 0
            user_rank_id = user_rank.rank_level if user_rank else 1
        except Exception as e:
            logger.warning(f"Could not get user rank for ladder display: {e}")
            user_rank = None
            user_total_points = 0
            user_rank_id = 1  # Default to first rank
        
        # Format the rank ladder
        ladder_text = "🪜 *RANK LADDER*\n\n"
        ladder_text += escape_markdown_text("Complete hierarchy of all available ranks and their requirements.")
        ladder_text += "\n" + escape_markdown_text("Your current position is highlighted.") + "\n\n"
        
        # Create a visual ladder of all ranks
        for rank in ranks:
            rank_emoji = rank['rank_emoji']
            rank_name = rank['rank_name']
            min_points = rank['min_points']
            max_points = rank['max_points']
            is_special = rank['is_special']
            is_user_rank = (user_rank_id == rank['rank_id'])
            
            # Format point range (escaping will be handled by escape_markdown_text)
            if max_points == float('inf'):
                points_range = f"{min_points:,}+ points"
            else:
                points_range = f"{min_points:,} - {max_points:,} points"
            
            # Rank indicator
            rank_type = "⭐ SPECIAL RANK" if is_special else "📊 Standard Rank"
            
            # Highlight current user rank
            prefix = "➡️ " if is_user_rank else "   "
            name_format = f"*{escape_markdown_text(rank_name)}*" if is_user_rank else escape_markdown_text(rank_name)
            
            # Format each rank entry with proper escaping
            ladder_text += f"{prefix}{escape_markdown_text(rank_emoji)} {name_format}\n"
            ladder_text += f"   {escape_markdown_text(points_range)} {escape_markdown_text('(' + rank_type + ')')}\n"
            
            # Add perks information if available
            if rank['special_perks'] and rank['special_perks'] != '{}':
                try:
                    import json
                    perks = json.loads(rank['special_perks'])
                    if perks:
                        perks_text = "   _Perks:_ "
                        perk_list = []
                        if 'daily_confessions' in perks:
                            perk_list.append(f"{perks['daily_confessions']} daily confessions")
                        if 'priority_review' in perks:
                            perk_list.append("Priority review")
                        if 'comment_highlight' in perks:
                            perk_list.append("Comment highlighting")
                        if 'all_perks' in perks and perks['all_perks']:
                            perk_list.append("All system perks")
                        if 'unlimited_daily' in perks and perks['unlimited_daily']:
                            perk_list.append("Unlimited confessions")
                        
                        if perk_list:
                            perks_text += escape_markdown_text(" • ".join(perk_list))
                            ladder_text += perks_text + "\n"
                except:
                    pass
            
            # Add separator between ranks
            ladder_text += "\n"
        
        # Add user's current progress information
        if user_rank:
            points_to_next = user_rank.points_to_next
            if points_to_next > 0:
                next_rank_name = next((r['rank_name'] for r in ranks if r['rank_id'] == user_rank_id + 1), "")
                ladder_text += f"📊 *Your Progress:* {escape_markdown_text(f'{user_total_points:,}')} points\n"
                ladder_text += f"🔼 *Next Rank:* {escape_markdown_text(f'{points_to_next:,}')} more points to reach {escape_markdown_text(next_rank_name)}\n"
            else:
                ladder_text += "🎉 " + escape_markdown_text("Congratulations! You've reached the maximum rank!") + "\n"
        
        ladder_text += "\n🚀 *" + escape_markdown_text("Keep contributing to climb the ladder!") + "*"
        
        return ladder_text

async def show_rank_ladder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the complete rank ladder with user's position"""
    user_id = update.effective_user.id
    
    # Format the rank ladder text
    ladder_text = RankLadderDisplay.format_rank_ladder(user_id)
    
    # Create keyboard with back button
    keyboard = [
        [
            InlineKeyboardButton("🔙 Back to Rank Menu", callback_data="enhanced_rank_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            ladder_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            ladder_text,
            parse_mode="MarkdownV2",
            reply_markup=reply_markup
        )
