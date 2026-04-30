"""
Essential utility functions for the Telegram Confession Bot
"""
from text_utils import escape_markdown_text, truncate_text, sanitize_content, format_time_ago

# Re-export essential functions for backward compatibility
__all__ = ['escape_markdown_text', 'truncate_text', 'sanitize_content', 'format_time_ago', 'format_date_only', 'format_join_date', 'format_date_only_html']

def format_date_only(timestamp_str):
    """
    Format timestamp to show only date part with proper escaping for MarkdownV2
    
    Args:
        timestamp_str: Timestamp string
        
    Returns:
        Escaped date string
    """
    if not timestamp_str:
        return escape_markdown_text("unknown date")
    
    try:
        from datetime import datetime
        if isinstance(timestamp_str, str):
            if 'T' in timestamp_str or ' ' in timestamp_str:
                # Parse ISO format or standard datetime format
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                formatted_date = dt.strftime('%m/%d %H:%M')
            else:
                # Already just a date
                formatted_date = timestamp_str[:10]
        else:
            formatted_date = str(timestamp_str)
        
        return escape_markdown_text(formatted_date)
    except:
        return escape_markdown_text("unknown date")

def format_join_date(join_date):
    """
    Format join date for display
    
    Args:
        join_date: Join date string
        
    Returns:
        Formatted join date
    """
    if not join_date:
        return "Unknown"
    
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(join_date.replace('Z', '+00:00'))
        return dt.strftime('%B %d, %Y at %H:%M')
    except:
        return str(join_date)[:16] if join_date else "Unknown"

def format_date_only_html(timestamp_str):
    """
    Format timestamp to show only date part for HTML parsing
    
    Args:
        timestamp_str: Timestamp string or datetime object
        
    Returns:
        HTML-safe formatted date string
    """
    if not timestamp_str:
        return "unknown date"
    
    try:
        from datetime import datetime
        from html import escape as html_escape
        
        if isinstance(timestamp_str, str):
            if 'T' in timestamp_str or ' ' in timestamp_str:
                # Parse ISO format or standard datetime format
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                formatted_date = dt.strftime('%m/%d %H:%M')
            else:
                # Already just a date
                formatted_date = timestamp_str[:10]
        elif hasattr(timestamp_str, 'strftime'):
            # It's a datetime object
            formatted_date = timestamp_str.strftime('%m/%d %H:%M')
        else:
            formatted_date = str(timestamp_str)
        
        return html_escape(formatted_date)
    except:
        return "unknown date"


def get_safe_separator():
    """Get a safe separator character that works across all platforms"""
    import os
    # Use ASCII-safe separator for hosting environments
    if os.getenv('HOSTING_SAFE_MODE', 'false').lower() == 'true':
        return ' | '  # ASCII pipe separator
    else:
        return ' • '  # Standard bullet point

def safe_format_with_rank(timestamp_text, rank_emoji, rank_name):
    """Format timestamp with rank using safe separator"""
    separator = get_safe_separator()
    return f"{timestamp_text}{separator}{rank_emoji} {rank_name}"
