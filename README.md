# Advanced Telegram Referral Bot

A feature-rich Telegram bot with referral system, points management, and special links.

## Features

### ✅ Force Join System
- Users must join 4 channels before using bot
- Automatic channel membership verification

### ✅ Referral System
- Unique referral codes for each user
- Referral leaderboard
- Points for successful referrals

### ✅ Points/Coins System
- Daily bonus points
- Points for referrals
- Points for special link clicks
- Withdrawal system

### ✅ Special Links Manager
- Create special links with custom messages
- Earn points when others click your links
- Manage (create/modify/delete) special links

### ✅ Admin Features
- Broadcast messages to all users
- View bot statistics
- Process withdrawal requests

### ✅ MongoDB Integration
- Permanent data storage
- User profiles and referral tracking
- Transaction history

## Deployment on Railway

### Step 1: Create Telegram Bot
1. Message @BotFather on Telegram
2. Create new bot with `/newbot`
3. Copy the bot token

### Step 2: Setup MongoDB
1. Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Create free cluster
3. Get connection string

### Step 3: Deploy on Railway
1. Fork this repository to your GitHub
2. Go to [Railway](https://railway.app)
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your forked repository
5. Add environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `MONGODB_URI`
   - `ADMIN_IDS`
   - Channel IDs

### Step 4: Get Channel IDs
1. Add bot as admin to your channels
2. Use @userinfobot to get channel IDs (add -100 prefix)

## Environment Variables

Create `.env` file or set in Railway:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
MONGODB_URI=mongodb+srv://...
ADMIN_IDS=123456789,987654321
CHANNEL_1_ID=-1001234567890
CHANNEL_2_ID=-1002345678901
CHANNEL_3_ID=-1003456789012
CHANNEL_4_ID=-1004567890123
