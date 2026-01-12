"""
Helper functions for Telegram Referral Bot
"""
import os
import re
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Tuple, Any
from urllib.parse import quote, urlencode
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

class ValidationHelper:
    """Input validation helpers"""
    
    @staticmethod
    def validate_telegram_username(username: str) -> bool:
        """
        Validate Telegram username
        
        Args:
            username: Telegram username
            
        Returns:
            bool: True if valid
        """
        if not username:
            return False
        
        # Telegram username rules
        pattern = r'^[a-zA-Z][a-zA-Z0-9_]{4,31}$'
        return bool(re.match(pattern, username))
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """
        Validate email address
        
        Args:
            email: Email address
            
        Returns:
            bool: True if valid
        """
        if not email:
            return False
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_phone(phone: str) -> bool:
        """
        Validate phone number
        
        Args:
            phone: Phone number
            
        Returns:
            bool: True if valid
        """
        if not phone:
            return False
        
        # Remove spaces, dashes, plus sign
        phone_clean = re.sub(r'[\s\-+]', '', phone)
        
        # Check if contains only digits
        if not phone_clean.isdigit():
            return False
        
        # Check length (minimum 10 digits for most countries)
        return len(phone_clean) >= 10
    
    @staticmethod
    def validate_amount(amount: str, min_amount: float = 0.01, 
                       max_amount: float = 1000000) -> Tuple[bool, Optional[float]]:
        """
        Validate amount input
        
        Args:
            amount: Amount string
            min_amount: Minimum allowed amount
            max_amount: Maximum allowed amount
            
        Returns:
            Tuple[bool, Optional[float]]: (is_valid, parsed_amount)
        """
        try:
            # Remove commas and whitespace
            amount_clean = amount.strip().replace(',', '')
            
            # Convert to float
            parsed_amount = float(amount_clean)
            
            # Check range
            if min_amount <= parsed_amount <= max_amount:
                return True, parsed_amount
            else:
                return False, None
                
        except (ValueError, TypeError):
            return False, None
    
    @staticmethod
    def validate_withdrawal_details(payment_method: str, details: Dict) -> List[str]:
        """
        Validate withdrawal details based on payment method
        
        Args:
            payment_method: Payment method
            details: Payment details dictionary
            
        Returns:
            List[str]: List of validation errors
        """
        errors = []
        
        if payment_method == 'upi':
            required_fields = ['upi_id']
            if 'upi_id' not in details or not details['upi_id']:
                errors.append("UPI ID is required")
            elif not re.match(r'^[\w.\-]+@[\w]+$', details.get('upi_id', '')):
                errors.append("Invalid UPI ID format")
        
        elif payment_method == 'bank':
            required_fields = ['account_number', 'account_holder', 'ifsc_code']
            for field in required_fields:
                if field not in details or not details[field]:
                    errors.append(f"{field.replace('_', ' ').title()} is required")
            
            if 'account_number' in details and not details['account_number'].isdigit():
                errors.append("Account number must contain only digits")
        
        elif payment_method == 'crypto':
            required_fields = ['wallet_address', 'crypto_type']
            for field in required_fields:
                if field not in details or not details[field]:
                    errors.append(f"{field.replace('_', ' ').title()} is required")
        
        elif payment_method == 'paypal':
            required_fields = ['paypal_email']
            if 'paypal_email' not in details or not details['paypal_email']:
                errors.append("PayPal email is required")
            elif not ValidationHelper.validate_email(details['paypal_email']):
                errors.append("Invalid PayPal email")
        
        return errors

class TimeHelper:
    """Time and date related helpers"""
    
    @staticmethod
    def get_ist_now() -> datetime:
        """
        Get current time in Indian Standard Time
        
        Returns:
            datetime: Current IST time
        """
        utc_now = datetime.utcnow()
        ist_tz = pytz.timezone('Asia/Kolkata')
        return utc_now.replace(tzinfo=pytz.utc).astimezone(ist_tz)
    
    @staticmethod
    def format_datetime(dt: datetime, format_str: str = '%Y-%m-%d %H:%M:%S', 
                       timezone: str = 'Asia/Kolkata') -> str:
        """
        Format datetime to string
        
        Args:
            dt: Datetime object
            format_str: Format string
            timezone: Timezone string
            
        Returns:
            str: Formatted datetime string
        """
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        
        tz = pytz.timezone(timezone)
        localized_dt = dt.astimezone(tz)
        return localized_dt.strftime(format_str)
    
    @staticmethod
    def format_time_ago(dt: datetime) -> str:
        """
        Format datetime as "time ago" string
        
        Args:
            dt: Datetime object
            
        Returns:
            str: Time ago string
        """
        now = datetime.utcnow()
        if dt.tzinfo:
            now = pytz.utc.localize(now)
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
        
        diff = now - dt
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
    
    @staticmethod
    def get_next_daily_reset() -> datetime:
        """
        Get next daily bonus reset time (12:00 AM IST)
        
        Returns:
            datetime: Next reset time
        """
        ist_now = TimeHelper.get_ist_now()
        tomorrow = ist_now.date() + timedelta(days=1)
        reset_time = datetime.combine(tomorrow, datetime.min.time())
        reset_time = pytz.timezone('Asia/Kolkata').localize(reset_time)
        return reset_time.astimezone(pytz.utc)
    
    @staticmethod
    def get_time_until_reset() -> str:
        """
        Get time until next daily reset
        
        Returns:
            str: Formatted time string
        """
        reset_time = TimeHelper.get_next_daily_reset()
        now = datetime.utcnow().replace(tzinfo=pytz.utc)
        
        diff = reset_time - now
        hours, remainder = divmod(diff.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        return f"{hours}h {minutes}m"

class TextHelper:
    """Text formatting and manipulation helpers"""
    
    @staticmethod
    def escape_markdown(text: str) -> str:
        """
        Escape special Markdown characters
        
        Args:
            text: Text to escape
            
        Returns:
            str: Escaped text
        """
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 100, 
                      ellipsis: str = '...') -> str:
        """
        Truncate text to maximum length
        
        Args:
            text: Text to truncate
            max_length: Maximum length
            ellipsis: Ellipsis string
            
        Returns:
            str: Truncated text
        """
        if len(text) <= max_length:
            return text
        
        return text[:max_length - len(ellipsis)] + ellipsis
    
    @staticmethod
    def format_number(number: Union[int, float]) -> str:
        """
        Format number with commas
        
        Args:
            number: Number to format
            
        Returns:
            str: Formatted number string
        """
        return f"{number:,}"
    
    @staticmethod
    def format_points(points: int) -> str:
        """
        Format points with symbol
        
        Args:
            points: Points to format
            
        Returns:
            str: Formatted points string
        """
        return f"🏆 {TextHelper.format_number(points)} points"
    
    @staticmethod
    def format_currency(amount: float, currency: str = '₹') -> str:
        """
        Format currency amount
        
        Args:
            amount: Amount to format
            currency: Currency symbol
            
        Returns:
            str: Formatted currency string
        """
        if amount.is_integer():
            return f"{currency}{TextHelper.format_number(int(amount))}"
        else:
            return f"{currency}{TextHelper.format_number(amount)}"
    
    @staticmethod
    def generate_progress_bar(percentage: float, length: int = 10) -> str:
        """
        Generate ASCII progress bar
        
        Args:
            percentage: Percentage (0-100)
            length: Length of progress bar
            
        Returns:
            str: Progress bar string
        """
        filled = int(percentage / 100 * length)
        empty = length - filled
        
        bar = '█' * filled + '░' * empty
        return f"{bar} {percentage:.1f}%"

class KeyboardHelper:
    """Keyboard and button generation helpers"""
    
    @staticmethod
    def create_main_menu_keyboard(user_id: int, admin_ids: List[int] = None) -> InlineKeyboardMarkup:
        """
        Create main menu keyboard
        
        Args:
            user_id: User ID
            admin_ids: List of admin IDs
            
        Returns:
            InlineKeyboardMarkup: Main menu keyboard
        """
        keyboard = [
            [InlineKeyboardButton("👥 Referral System", callback_data='referral_menu')],
            [InlineKeyboardButton("💰 Points & Withdraw", callback_data='points_menu')],
            [InlineKeyboardButton("🎁 Daily Bonus", callback_data='daily_bonus')],
            [InlineKeyboardButton("🔗 Special Links", callback_data='special_links')],
            [InlineKeyboardButton("📊 Leaderboard", callback_data='leaderboard')]
        ]
        
        if admin_ids and user_id in admin_ids:
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_referral_menu_keyboard(referral_link: str) -> InlineKeyboardMarkup:
        """
        Create referral menu keyboard
        
        Args:
            referral_link: User's referral link
            
        Returns:
            InlineKeyboardMarkup: Referral menu keyboard
        """
        share_text = quote("Join our awesome community and earn points!")
        share_url = f"https://t.me/share/url?url={quote(referral_link)}&text={share_text}"
        
        keyboard = [
            [InlineKeyboardButton("📤 Share Referral Link", url=share_url)],
            [InlineKeyboardButton("📊 My Referrals", callback_data='my_referrals')],
            [InlineKeyboardButton("🏆 Leaderboard", callback_data='leaderboard')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_points_menu_keyboard() -> InlineKeyboardMarkup:
        """
        Create points menu keyboard
        
        Returns:
            InlineKeyboardMarkup: Points menu keyboard
        """
        keyboard = [
            [InlineKeyboardButton("💰 Withdraw Points", callback_data='withdraw')],
            [InlineKeyboardButton("📊 Points History", callback_data='points_history')],
            [InlineKeyboardButton("💎 Earn More Points", callback_data='earn_points')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_special_links_menu_keyboard() -> InlineKeyboardMarkup:
        """
        Create special links menu keyboard
        
        Returns:
            InlineKeyboardMarkup: Special links keyboard
        """
        keyboard = [
            [InlineKeyboardButton("➕ Create Special Link", callback_data='create_special')],
            [InlineKeyboardButton("📋 My Special Links", callback_data='my_special_links')],
            [InlineKeyboardButton("✏️ Modify Special Link", callback_data='modify_special')],
            [InlineKeyboardButton("🗑️ Delete Special Link", callback_data='delete_special')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_admin_panel_keyboard() -> InlineKeyboardMarkup:
        """
        Create admin panel keyboard
        
        Returns:
            InlineKeyboardMarkup: Admin panel keyboard
        """
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast Message", callback_data='broadcast')],
            [InlineKeyboardButton("📊 Bot Statistics", callback_data='stats')],
            [InlineKeyboardButton("💸 Withdrawal Requests", callback_data='withdrawal_requests')],
            [InlineKeyboardButton("👥 User Management", callback_data='user_management')],
            [InlineKeyboardButton("⚙️ Bot Settings", callback_data='bot_settings')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_pagination_keyboard(current_page: int, total_pages: int, 
                                 prefix: str = 'page_') -> InlineKeyboardMarkup:
        """
        Create pagination keyboard
        
        Args:
            current_page: Current page number
            total_pages: Total number of pages
            prefix: Callback data prefix
            
        Returns:
            InlineKeyboardMarkup: Pagination keyboard
        """
        keyboard = []
        
        # Previous button
        if current_page > 1:
            keyboard.append(
                InlineKeyboardButton("⬅️ Previous", callback_data=f"{prefix}{current_page - 1}")
            )
        
        # Next button
        if current_page < total_pages:
            keyboard.append(
                InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}{current_page + 1}")
            )
        
        # Add page info in middle if space
        if len(keyboard) > 0:
            keyboard.insert(1, InlineKeyboardButton(f"📄 {current_page}/{total_pages}", callback_data='noop'))
        else:
            keyboard.append(InlineKeyboardButton(f"Page {current_page}/{total_pages}", callback_data='noop'))
        
        return InlineKeyboardMarkup([keyboard])
    
    @staticmethod
    def create_confirmation_keyboard(yes_data: str = 'confirm', 
                                   no_data: str = 'cancel') -> InlineKeyboardMarkup:
        """
        Create confirmation keyboard
        
        Args:
            yes_data: Callback data for Yes button
            no_data: Callback data for No button
            
        Returns:
            InlineKeyboardMarkup: Confirmation keyboard
        """
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes", callback_data=yes_data),
                InlineKeyboardButton("❌ No", callback_data=no_data)
            ]
        ]
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def create_withdrawal_methods_keyboard() -> InlineKeyboardMarkup:
        """
        Create withdrawal methods keyboard
        
        Returns:
            InlineKeyboardMarkup: Withdrawal methods keyboard
        """
        keyboard = [
            [InlineKeyboardButton("📱 UPI", callback_data='withdraw_upi')],
            [InlineKeyboardButton("🏦 Bank Transfer", callback_data='withdraw_bank')],
            [InlineKeyboardButton("₿ Crypto", callback_data='withdraw_crypto')],
            [InlineKeyboardButton("💳 PayPal", callback_data='withdraw_paypal')],
            [InlineKeyboardButton("🔙 Back", callback_data='points_menu')]
        ]
        
        return InlineKeyboardMarkup(keyboard)

class ChannelHelper:
    """Channel management helpers"""
    
    @staticmethod
    def get_channel_buttons(channels: List[Dict]) -> InlineKeyboardMarkup:
        """
        Create channel join buttons
        
        Args:
            channels: List of channel dictionaries with 'name' and 'link'
            
        Returns:
            InlineKeyboardMarkup: Channel join buttons
        """
        keyboard = []
        for channel in channels:
            keyboard.append([
                InlineKeyboardButton(
                    f"👉 Join {channel.get('name', 'Channel')}", 
                    url=channel.get('link', '#')
                )
            ])
        
        keyboard.append([InlineKeyboardButton("✅ I've Joined All", callback_data='check_join')])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    async def check_channel_membership(bot, user_id: int, channel_ids: List[int]) -> List[Dict]:
        """
        Check if user is member of channels
        
        Args:
            bot: Bot instance
            user_id: User ID to check
            channel_ids: List of channel IDs
            
        Returns:
            List[Dict]: List of channels user hasn't joined
        """
        not_joined = []
        
        for channel_id in channel_ids:
            try:
                member = await bot.get_chat_member(channel_id, user_id)
                if member.status in ['left', 'kicked']:
                    not_joined.append({'id': channel_id, 'status': 'not_joined'})
            except Exception as e:
                logger.error(f"Error checking channel {channel_id}: {e}")
                not_joined.append({'id': channel_id, 'status': 'error'})
        
        return not_joined

class SecurityHelper:
    """Security related helpers"""
    
    @staticmethod
    def generate_hash(data: str, salt: str = None) -> str:
        """
        Generate SHA256 hash of data
        
        Args:
            data: Data to hash
            salt: Optional salt
            
        Returns:
            str: Hashed string
        """
        if salt:
            data = f"{data}{salt}"
        
        return hashlib.sha256(data.encode()).hexdigest()
    
    @staticmethod
    def validate_referral_code(code: str) -> bool:
        """
        Validate referral code format
        
        Args:
            code: Referral code
            
        Returns:
            bool: True if valid format
        """
        # 8 characters, alphanumeric, uppercase
        pattern = r'^[A-Z0-9]{8}$'
        return bool(re.match(pattern, code))
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """
        Sanitize user input to prevent injection
        
        Args:
            text: Input text
            
        Returns:
            str: Sanitized text
        """
        # Remove potentially dangerous characters
        dangerous_chars = ['<', '>', '&', "'", '"', '`', '\\', '/', ';']
        for char in dangerous_chars:
            text = text.replace(char, '')
        
        return text.strip()

class MessageTemplate:
    """Message templates for the bot"""
    
    @staticmethod
    def welcome_message(user_name: str, points: int = 0) -> str:
        """
        Welcome message template
        
        Args:
            user_name: User's first name
            points: User's starting points
            
        Returns:
            str: Welcome message
        """
        return (
            f"🎉 *Welcome {user_name}!*\n\n"
            f"Start earning points and rewards with our referral system!\n\n"
            f"💎 *Quick Start Guide:*\n"
            f"1️⃣ Share your referral link to earn points\n"
            f"2️⃣ Claim daily bonus every 24 hours\n"
            f"3️⃣ Create special links for extra points\n"
            f"4️⃣ Withdraw your points when you reach minimum\n\n"
            f"*Current Points:* {points}\n"
            f"*Minimum Withdrawal:* 1,000 points\n\n"
            f"Use the buttons below to get started! 👇"
        )
    
    @staticmethod
    def referral_stats_message(stats: Dict) -> str:
        """
        Referral statistics message
        
        Args:
            stats: Referral statistics dictionary
            
        Returns:
            str: Formatted stats message
        """
        return (
            f"📊 *Your Referral Statistics*\n\n"
            f"👥 Total Referrals: *{stats.get('total_referrals', 0)}*\n"
            f"📈 Today's Referrals: *{stats.get('today_referrals', 0)}*\n"
            f"📅 This Week: *{stats.get('week_referrals', 0)}*\n"
            f"🗓️ This Month: *{stats.get('month_referrals', 0)}*\n\n"
            f"💰 Points from Referrals: *{stats.get('referral_points', 0)}*\n"
            f"🏆 Your Rank: *#{stats.get('referral_rank', 0)}*\n\n"
            f"Keep sharing your link to climb the leaderboard! 🚀"
        )
    
    @staticmethod
    def special_link_created_message(link: str, message_preview: str) -> str:
        """
        Special link created message
        
        Args:
            link: Generated special link
            message_preview: Preview of stored message
            
        Returns:
            str: Special link message
        """
        preview = TextHelper.truncate_text(message_preview, 100)
        
        return (
            f"✅ *Special Link Created!*\n\n"
            f"*Your Link:*\n`{link}`\n\n"
            f"*Message Preview:*\n{preview}\n\n"
            f"*How it works:*\n"
            f"• Share this link with anyone\n"
            f"• You earn *10 points* per click\n"
            f"• Track clicks in your special links menu\n\n"
            f"Click 'Share URL' to share your link! 📤"
        )
    
    @staticmethod
    def withdrawal_request_message(withdrawal_id: str, amount: int, 
                                 method: str) -> str:
        """
        Withdrawal request confirmation message
        
        Args:
            withdrawal_id: Withdrawal request ID
            amount: Withdrawal amount
            method: Payment method
            
        Returns:
            str: Withdrawal confirmation message
        """
        return (
            f"✅ *Withdrawal Request Submitted!*\n\n"
            f"*Request ID:* `{withdrawal_id}`\n"
            f"*Amount:* {TextHelper.format_points(amount)}\n"
            f"*Method:* {method.title()}\n"
            f"*Status:* ⏳ Pending\n\n"
            f"Your request has been sent to admins for processing.\n"
            f"Processing usually takes 24-48 hours.\n\n"
            f"You will be notified when your request is approved. ✅"
        )
    
    @staticmethod
    def daily_bonus_message(points: int, next_reset: str) -> str:
        """
        Daily bonus claimed message
        
        Args:
            points: Points awarded
            next_reset: Time until next reset
            
        Returns:
            str: Daily bonus message
        """
        return (
            f"🎁 *Daily Bonus Claimed!*\n\n"
            f"You received *{TextHelper.format_points(points)}*!\n\n"
            f"Come back in *{next_reset}* to claim your next bonus.\n\n"
            f"*Pro Tip:* Invite friends to earn even more points! 👥"
        )

class ErrorHandler:
    """Error handling helpers"""
    
    @staticmethod
    def format_error_message(error: Exception, context: str = '') -> str:
        """
        Format error message for logging
        
        Args:
            error: Exception object
            context: Context where error occurred
            
        Returns:
            str: Formatted error message
        """
        error_type = type(error).__name__
        error_msg = str(error)
        
        message = f"❌ Error"
        if context:
            message += f" in {context}"
        
        message += f": [{error_type}] {error_msg}"
        return message
    
    @staticmethod
    def get_user_friendly_error(error: Exception) -> str:
        """
        Get user-friendly error message
        
        Args:
            error: Exception object
            
        Returns:
            str: User-friendly error message
        """
        error_type = type(error).__name__
        
        # Common error messages
        error_messages = {
            'ConnectionError': "Unable to connect to server. Please try again later.",
            'TimeoutError': "Request timed out. Please check your connection.",
            'ValueError': "Invalid input provided. Please check and try again.",
            'KeyError': "Required information missing. Please try again.",
            'PermissionError': "You don't have permission to perform this action.",
            'DuplicateKeyError': "This already exists. Please try a different value."
        }
        
        return error_messages.get(error_type, "An error occurred. Please try again later.")

# Helper functions for easy access
def format_user_mention(user_id: int, username: str = None, 
                       first_name: str = None) -> str:
    """
    Format user mention for Telegram messages
    
    Args:
        user_id: User ID
        username: Telegram username
        first_name: User's first name
        
    Returns:
        str: Formatted mention
    """
    if username:
        return f"@{username}"
    elif first_name:
        return f"[{first_name}](tg://user?id={user_id})"
    else:
        return f"User {user_id}"

def generate_invite_link(bot_username: str, referral_code: str) -> str:
    """
    Generate Telegram invite link
    
    Args:
        bot_username: Bot username (without @)
        referral_code: Referral code
        
    Returns:
        str: Full invite link
    """
    return f"https://t.me/{bot_username}?start=ref_{referral_code}"

def calculate_referral_bonus(base_points: int, level: int = 1) -> int:
    """
    Calculate referral bonus points (for multi-level referrals)
    
    Args:
        base_points: Base points per referral
        level: Referral level (1 = direct, 2 = indirect, etc.)
        
    Returns:
        int: Bonus points
    """
    # Example: Level 1: 100%, Level 2: 20%, Level 3: 10%
    multipliers = {1: 1.0, 2: 0.2, 3: 0.1}
    multiplier = multipliers.get(level, 0)
    return int(base_points * multiplier)

def format_duration(seconds: int) -> str:
    """
    Format duration in seconds to human readable string
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        str: Formatted duration
    """
    if seconds < 60:
        return f"{seconds} seconds"
    
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    
    hours, mins = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {mins}m"
    
    days, hrs = divmod(hours, 24)
    return f"{days}d {hrs}h"
