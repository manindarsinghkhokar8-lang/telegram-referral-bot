import os
import logging
from datetime import datetime, timedelta
from uuid import uuid4
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import pymongo
from pymongo import MongoClient

# Load environment variables
load_dotenv()

# Configuration
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MONGO_URI = os.getenv('MONGODB_URI')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []
DAILY_BONUS = 50
REFERRAL_POINTS = 100
WITHDRAW_MIN = 1000

# Required channels for force join
REQUIRED_CHANNELS = [
    {'name': 'Channel 1', 'link': 'https://t.me/+imnY9aNAt9A1YzNl', 'id': -1001234567890},
    {'name': 'Channel 2', 'link': 'https://t.me/+ZlHW_ZUS6yQ1NDA9', 'id': -1002345678901},
    {'name': 'Channel 3', 'link': 'https://t.me/+Db38DSH0iR1iMDc1', 'id': -1003456789012},
    {'name': 'Channel 4', 'link': 'https://t.me/+1ZMyGGyTb1s0MzM1', 'id': -1004567890123}
]

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB connection
client = MongoClient(MONGO_URI)
db = client['telegram_referral_bot']
users_collection = db['users']
referrals_collection = db['referrals']
special_links_collection = db['special_links']
withdrawals_collection = db['withdrawals']
broadcasts_collection = db['broadcasts']

class UserManager:
    @staticmethod
    async def get_user(user_id):
        user = users_collection.find_one({'user_id': user_id})
        if not user:
            user = {
                'user_id': user_id,
                'points': 0,
                'referral_code': str(uuid4())[:8],
                'referrer_id': None,
                'total_referred': 0,
                'daily_bonus_claimed': None,
                'created_at': datetime.utcnow(),
                'special_links': []
            }
            users_collection.insert_one(user)
        return user

    @staticmethod
    async def update_user(user_id, update_data):
        users_collection.update_one(
            {'user_id': user_id},
            {'$set': update_data}
        )

    @staticmethod
    async def add_points(user_id, points, reason=''):
        user = await UserManager.get_user(user_id)
        new_points = user['points'] + points
        await UserManager.update_user(user_id, {'points': new_points})
        
        # Log transaction
        db['transactions'].insert_one({
            'user_id': user_id,
            'points': points,
            'reason': reason,
            'timestamp': datetime.utcnow()
        })
        return new_points

class ReferralSystem:
    @staticmethod
    async def handle_referral(user_id, referrer_code):
        if referrer_code:
            referrer = users_collection.find_one({'referral_code': referrer_code})
            if referrer and referrer['user_id'] != user_id:
                # Add points to referrer
                await UserManager.add_points(referrer['user_id'], REFERRAL_POINTS, 'referral')
                
                # Update referrer's count
                users_collection.update_one(
                    {'user_id': referrer['user_id']},
                    {'$inc': {'total_referred': 1}}
                )
                
                # Record referral
                referrals_collection.insert_one({
                    'referrer_id': referrer['user_id'],
                    'referred_id': user_id,
                    'timestamp': datetime.utcnow()
                })
                
                # Set referrer for new user
                await UserManager.update_user(user_id, {'referrer_id': referrer['user_id']})
                return True
        return False

    @staticmethod
    async def get_leaderboard(limit=10):
        pipeline = [
            {'$sort': {'total_referred': -1}},
            {'$limit': limit},
            {'$project': {
                'user_id': 1,
                'total_referred': 1,
                'points': 1
            }}
        ]
        return list(users_collection.aggregate(pipeline))

class SpecialLinkManager:
    @staticmethod
    async def create_special_link(user_id, message):
        link_id = str(uuid4())[:8]
        special_links_collection.insert_one({
            'link_id': link_id,
            'user_id': user_id,
            'message': message,
            'clicks': 0,
            'created_at': datetime.utcnow()
        })
        
        # Add to user's special links
        users_collection.update_one(
            {'user_id': user_id},
            {'$push': {'special_links': link_id}}
        )
        
        return f"https://t.me/{TOKEN.split(':')[0]}?start=special_{link_id}"

    @staticmethod
    async def get_special_link(link_id):
        return special_links_collection.find_one({'link_id': link_id})

    @staticmethod
    async def delete_special_link(user_id, link_id):
        special_links_collection.delete_one({'link_id': link_id, 'user_id': user_id})
        users_collection.update_one(
            {'user_id': user_id},
            {'$pull': {'special_links': link_id}}
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user is in required channels
    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel['id'], user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
        except:
            not_joined.append(channel)
    
    if not_joined:
        keyboard = []
        for channel in not_joined:
            keyboard.append([InlineKeyboardButton(
                f"Join {channel['name']}", 
                url=channel['link']
            )])
        keyboard.append([InlineKeyboardButton("✅ I've Joined All", callback_data='check_join')])
        
        await update.message.reply_text(
            "⚠️ Please join our channels first:\n\n"
            "Join all channels then click 'I've Joined All'",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Handle referral parameter
    referrer_code = None
    if context.args:
        if context.args[0].startswith('ref_'):
            referrer_code = context.args[0].split('_')[1]
        elif context.args[0].startswith('special_'):
            link_id = context.args[0].split('_')[1]
            link_data = await SpecialLinkManager.get_special_link(link_id)
            if link_data:
                await update.message.reply_text(f"📨 Special Message:\n\n{link_data['message']}")
                # Add points for clicking special link
                await UserManager.add_points(user_id, 10, 'special_link_click')
                special_links_collection.update_one(
                    {'link_id': link_id},
                    {'$inc': {'clicks': 1}}
                )
    
    # Get or create user
    user = await UserManager.get_user(user_id)
    
    # Handle referral
    if referrer_code and not user.get('referrer_id'):
        await ReferralSystem.handle_referral(user_id, referrer_code)
    
    # Send welcome message with main menu
    referral_link = f"https://t.me/{TOKEN.split(':')[0]}?start=ref_{user['referral_code']}"
    
    keyboard = [
        [InlineKeyboardButton("👥 Referral System", callback_data='referral_menu')],
        [InlineKeyboardButton("💰 Points & Withdraw", callback_data='points_menu')],
        [InlineKeyboardButton("🎁 Daily Bonus", callback_data='daily_bonus')],
        [InlineKeyboardButton("🔗 Special Links", callback_data='special_links')],
        [InlineKeyboardButton("📊 Leaderboard", callback_data='leaderboard')]
    ]
    
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
    
    await update.message.reply_text(
        f"🎉 Welcome {update.effective_user.first_name}!\n\n"
        f"📊 Your Points: {user['points']}\n"
        f"👥 Referrals: {user['total_referred']}\n"
        f"🔗 Your Referral Link:\n{referral_link}\n\n"
        f"Use buttons below to navigate:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == 'check_join':
        await check_channels_joined(update, context)
    
    elif query.data == 'referral_menu':
        user = await UserManager.get_user(user_id)
        referral_link = f"https://t.me/{TOKEN.split(':')[0]}?start=ref_{user['referral_code']}"
        
        keyboard = [
            [InlineKeyboardButton("📤 Share Referral Link", url=f"https://t.me/share/url?url={referral_link}&text=Join%20our%20awesome%20community!")],
            [InlineKeyboardButton("📊 My Referrals", callback_data='my_referrals')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        
        await query.edit_message_text(
            f"👥 **Referral System**\n\n"
            f"Your Referral Code: `{user['referral_code']}`\n"
            f"Total Referrals: {user['total_referred']}\n"
            f"Earned from referrals: {user['total_referred'] * REFERRAL_POINTS} points\n\n"
            f"**Referral Link:**\n{referral_link}\n\n"
            f"Share this link to earn {REFERRAL_POINTS} points per referral!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif query.data == 'points_menu':
        user = await UserManager.get_user(user_id)
        
        keyboard = [
            [InlineKeyboardButton("💰 Withdraw Points", callback_data='withdraw')],
            [InlineKeyboardButton("📊 Points History", callback_data='points_history')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        
        await query.edit_message_text(
            f"💰 **Points System**\n\n"
            f"Current Points: **{user['points']}**\n"
            f"Minimum Withdrawal: {WITHDRAW_MIN} points\n\n"
            f"**Ways to earn points:**\n"
            f"• Daily Bonus: {DAILY_BONUS} points\n"
            f"• Referral: {REFERRAL_POINTS} points each\n"
            f"• Special Links: 10 points per click",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'daily_bonus':
        user = await UserManager.get_user(user_id)
        today = datetime.utcnow().date()
        
        if user.get('daily_bonus_claimed') and user['daily_bonus_claimed'].date() == today:
            await query.answer("You've already claimed your daily bonus today!", show_alert=True)
        else:
            await UserManager.add_points(user_id, DAILY_BONUS, 'daily_bonus')
            await UserManager.update_user(user_id, {'daily_bonus_claimed': datetime.utcnow()})
            
            keyboard = [[InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]]
            await query.edit_message_text(
                f"🎉 Daily Bonus Claimed!\n\n"
                f"You received {DAILY_BONUS} points!\n"
                f"Total Points: {user['points'] + DAILY_BONUS}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    elif query.data == 'special_links':
        keyboard = [
            [InlineKeyboardButton("➕ Create Special Link", callback_data='create_special')],
            [InlineKeyboardButton("✏️ Modify Special Link", callback_data='modify_special')],
            [InlineKeyboardButton("🗑️ Delete Special Link", callback_data='delete_special')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        
        await query.edit_message_text(
            "🔗 **Special Links Manager**\n\n"
            "Create special links that give you 10 points when someone clicks them!\n\n"
            "Choose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'create_special':
        context.user_data['awaiting_special_message'] = True
        await query.edit_message_text(
            "📝 **Create Special Link**\n\n"
            "Send me the message you want to store with your special link.\n"
            "You can add multiple messages by sending them one by one.\n\n"
            "Type /cancel to cancel."
        )
    
    elif query.data == 'leaderboard':
        leaderboard = await ReferralSystem.get_leaderboard()
        
        text = "🏆 **Top Referrers Leaderboard**\n\n"
        for i, user_data in enumerate(leaderboard, 1):
            try:
                user_obj = await context.bot.get_chat(user_data['user_id'])
                name = user_obj.first_name
            except:
                name = f"User{user_data['user_id']}"
            
            text += f"{i}. {name}: {user_data['total_referred']} referrals ({user_data.get('points', 0)} points)\n"
        
        keyboard = [[InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data == 'admin_panel' and user_id in ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("📢 Broadcast Message", callback_data='broadcast')],
            [InlineKeyboardButton("📊 Bot Statistics", callback_data='stats')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        await query.edit_message_text(
            "👑 **Admin Panel**\n\n"
            "Choose an option:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'main_menu':
        user = await UserManager.get_user(user_id)
        referral_link = f"https://t.me/{TOKEN.split(':')[0]}?start=ref_{user['referral_code']}"
        
        keyboard = [
            [InlineKeyboardButton("👥 Referral System", callback_data='referral_menu')],
            [InlineKeyboardButton("💰 Points & Withdraw", callback_data='points_menu')],
            [InlineKeyboardButton("🎁 Daily Bonus", callback_data='daily_bonus')],
            [InlineKeyboardButton("🔗 Special Links", callback_data='special_links')],
            [InlineKeyboardButton("📊 Leaderboard", callback_data='leaderboard')]
        ]
        
        if user_id in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data='admin_panel')])
        
        await query.edit_message_text(
            f"🏠 **Main Menu**\n\n"
            f"📊 Your Points: {user['points']}\n"
            f"👥 Referrals: {user['total_referred']}\n"
            f"🔗 Your Referral Link:\n{referral_link}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if context.user_data.get('awaiting_special_message'):
        message_text = update.message.text
        
        # Store message and generate link
        special_link = await SpecialLinkManager.create_special_link(user_id, message_text)
        
        keyboard = [
            [InlineKeyboardButton("📤 Share URL", url=f"https://t.me/share/url?url={special_link}&text=Check%20this%20special%20message!")],
            [InlineKeyboardButton("➕ Add Another Message", callback_data='create_special')],
            [InlineKeyboardButton("🏠 Back to Main", callback_data='main_menu')]
        ]
        
        await update.message.reply_text(
            f"✅ **Special Link Created!**\n\n"
            f"Your special link:\n`{special_link}`\n\n"
            f"Each click earns you 10 points!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # Clear the state
        context.user_data.pop('awaiting_special_message', None)
    
    else:
        # Auto-reply system
        responses = {
            'hello': 'Hi there! How can I help you?',
            'hi': 'Hello! Use /start to begin.',
            'help': 'Use /start to see all available commands.',
        }
        
        message_lower = update.message.text.lower()
        for key in responses:
            if key in message_lower:
                await update.message.reply_text(responses[key])
                break

async def check_channels_joined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel['id'], user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
        except:
            not_joined.append(channel)
    
    if not_joined:
        keyboard = []
        for channel in not_joined:
            keyboard.append([InlineKeyboardButton(
                f"Join {channel['name']}", 
                url=channel['link']
            )])
        keyboard.append([InlineKeyboardButton("✅ Check Again", callback_data='check_join')])
        
        await query.edit_message_text(
            "⚠️ You still need to join these channels:\n\n"
            "Please join all channels to continue.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # User joined all channels, proceed to start
        await start(update, context)

async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await UserManager.get_user(user_id)
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /withdraw <amount> <payment_method>\n"
            f"Minimum: {WITHDRAW_MIN} points\n"
            f"Your Points: {user['points']}"
        )
        return
    
    try:
        amount = int(context.args[0])
        payment_method = context.args[1]
        
        if amount < WITHDRAW_MIN:
            await update.message.reply_text(f"Minimum withdrawal is {WITHDRAW_MIN} points!")
            return
        
        if amount > user['points']:
            await update.message.reply_text("Insufficient points!")
            return
        
        # Create withdrawal request
        withdrawal_id = str(uuid4())[:8]
        withdrawals_collection.insert_one({
            'withdrawal_id': withdrawal_id,
            'user_id': user_id,
            'amount': amount,
            'payment_method': payment_method,
            'status': 'pending',
            'created_at': datetime.utcnow()
        })
        
        # Deduct points
        await UserManager.add_points(user_id, -amount, 'withdrawal')
        
        # Notify admin
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"🔄 New Withdrawal Request\n\n"
                    f"ID: {withdrawal_id}\n"
                    f"User: {user_id}\n"
                    f"Amount: {amount} points\n"
                    f"Method: {payment_method}"
                )
            except:
                pass
        
        await update.message.reply_text(
            f"✅ Withdrawal request submitted!\n\n"
            f"ID: {withdrawal_id}\n"
            f"Amount: {amount} points\n"
            f"Status: Pending\n\n"
            f"Admin will process your request soon."
        )
    
    except ValueError:
        await update.message.reply_text("Invalid amount!")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized!")
        return
    
    total_users = users_collection.count_documents({})
    total_points = sum(user['points'] for user in users_collection.find({}, {'points': 1}))
    total_referrals = referrals_collection.count_documents({})
    total_withdrawals = withdrawals_collection.count_documents({})
    
    await update.message.reply_text(
        "📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"💰 Total Points in System: {total_points}\n"
        f"📈 Total Referrals: {total_referrals}\n"
        f"💸 Total Withdrawals: {total_withdrawals}\n"
        f"🔗 Special Links Created: {special_links_collection.count_documents({})}"
    )

def main():
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('withdraw', withdraw_command))
    application.add_handler(CommandHandler('stats', stats_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    print("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
