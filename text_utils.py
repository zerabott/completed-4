"""
Text utility functions for the Telegram bot
"""
import re


def escape_markdown_text(text):
    """Escape special characters for Telegram MarkdownV2 parsing.

    This helper is used throughout the bot whenever we send MarkdownV2.
    It now also escapes backslashes themselves to avoid broken escape
    sequences when user text already contains ``\\`` characters.
    """
    if not text:
        return ""

    escaped_text = str(text)

    # First, escape existing backslashes so they don't interfere with
    # the escapes we add for other special characters.
    escaped_text = escaped_text.replace("\\", "\\\\")

    # MarkdownV2 special characters that need escaping
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

    for char in special_chars:
        escaped_text = escaped_text.replace(char, f'\\{char}')

    return escaped_text


def truncate_text(text, max_length=100):
    """
    Truncate text to specified length with ellipsis
    
    Args:
        text: Text to truncate
        max_length: Maximum length before truncation
        
    Returns:
        Truncated text with ellipsis if needed
    """
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    return text[:max_length-3] + "..."


def sanitize_content(content):
    """
    Sanitize user input content while preserving newlines and formatting
    
    Args:
        content: Raw content from user
        
    Returns:
        Sanitized content with preserved formatting
    """
    if not content:
        return ""
    
    # Strip leading/trailing whitespace but preserve internal formatting
    content = content.strip()
    
    # Replace multiple consecutive spaces/tabs with single space, BUT preserve newlines
    # First, temporarily replace newlines with a placeholder
    content_with_placeholders = content.replace('\n', '\x00NEWLINE\x00')
    
    # Now collapse multiple spaces/tabs into single space (but not newlines)
    content_collapsed = re.sub(r'[^\S\n]+', ' ', content_with_placeholders)
    
    # Restore newlines
    content = content_collapsed.replace('\x00NEWLINE\x00', '\n')
    
    # Remove any leading/trailing spaces on each line while preserving the newlines
    lines = content.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    content = '\n'.join(cleaned_lines)
    
    # Remove excessive consecutive blank lines (more than 2 blank lines in a row)
    content = re.sub(r'\n{4,}', '\n\n\n', content)
    
    # Basic length check (count meaningful characters, excluding whitespace)
    meaningful_chars = len(re.sub(r'\s', '', content))
    if meaningful_chars < 5:
        return ""
    
    return content


def format_time_ago(dt):
    """
    Format datetime to human-readable "time ago" format
    
    Args:
        dt: datetime object
        
    Returns:
        Human-readable time string
    """
    from datetime import datetime, timezone
    import math
    
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
        
    diff = now - dt
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours}h ago"
    elif seconds < 604800:
        days = int(seconds // 86400)
        return f"{days}d ago"
    else:
        weeks = int(seconds // 604800)
        return f"{weeks}w ago"


def clean_unicode_corruption(text):
    """Clean up Unicode corruption in text"""
    if not text:
        return text
    
    # Dictionary of corrupted characters to fix
    corruption_fixes = {
        '遅': ' • ',          # Main issue: Japanese char to bullet
        '≡ƒÑë': '🥉',        # Bronze medal corruption
        '≡ƒÄ»': '🏆',        # Trophy corruption
        'Γ£¿': '✨',         # Sparkle corruption
        '≡ƒô¥': '📋',        # Clipboard corruption
        'ΓÇó': '•',          # Bullet corruption
        '≡ƒÜ¿': '❌',        # X emoji corruption
    }
    
    cleaned_text = text
    for corrupted, fixed in corruption_fixes.items():
        if corrupted in cleaned_text:
            cleaned_text = cleaned_text.replace(corrupted, fixed)
    
    return cleaned_text
