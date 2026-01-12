"""
Database management utilities for Telegram Referral Bot
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from bson import ObjectId
import pymongo
from pymongo import MongoClient, IndexModel, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, ConnectionFailure
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    MongoDB database manager for the referral bot
    """
    
    def __init__(self, mongo_uri: str = None):
        """
        Initialize database connection
        
        Args:
            mongo_uri: MongoDB connection URI
        """
        self.mongo_uri = mongo_uri or os.getenv('MONGODB_URI')
        if not self.mongo_uri:
            raise ValueError("MongoDB URI is required")
        
        self.client = None
        self.db = None
        self.connect()
        self.setup_indexes()
    
    def connect(self) -> bool:
        """
        Establish connection to MongoDB
        
        Returns:
            bool: True if connection successful
        """
        try:
            self.client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=3000,
                socketTimeoutMS=3000
            )
            
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client.get_database()
            
            logger.info("✅ Successfully connected to MongoDB")
            return True
            
        except ConnectionFailure as e:
            logger.error(f"❌ Failed to connect to MongoDB: {e}")
            raise
    
    def setup_indexes(self) -> None:
        """
        Create necessary database indexes for performance
        """
        try:
            # Users collection indexes
            users_indexes = [
                IndexModel([('user_id', ASCENDING)], unique=True, name='user_id_unique'),
                IndexModel([('referral_code', ASCENDING)], unique=True, name='referral_code_unique'),
                IndexModel([('points', DESCENDING)], name='points_desc'),
                IndexModel([('total_referred', DESCENDING)], name='total_referred_desc'),
                IndexModel([('referrer_id', ASCENDING)], name='referrer_id_idx'),
                IndexModel([('created_at', DESCENDING)], name='created_at_desc'),
                IndexModel([('daily_bonus_claimed', ASCENDING)], name='daily_bonus_idx')
            ]
            self.db.users.create_indexes(users_indexes)
            
            # Referrals collection indexes
            referrals_indexes = [
                IndexModel([('referrer_id', ASCENDING), ('referred_id', ASCENDING)], 
                          unique=True, name='referral_pair_unique'),
                IndexModel([('referrer_id', ASCENDING)], name='referrer_idx'),
                IndexModel([('referred_id', ASCENDING)], name='referred_idx'),
                IndexModel([('timestamp', DESCENDING)], name='timestamp_desc')
            ]
            self.db.referrals.create_indexes(referrals_indexes)
            
            # Special links collection indexes
            special_links_indexes = [
                IndexModel([('link_id', ASCENDING)], unique=True, name='link_id_unique'),
                IndexModel([('user_id', ASCENDING)], name='user_id_special_idx'),
                IndexModel([('created_at', DESCENDING)], name='special_created_desc'),
                IndexModel([('clicks', DESCENDING)], name='clicks_desc')
            ]
            self.db.special_links.create_indexes(special_links_indexes)
            
            # Transactions collection indexes
            transactions_indexes = [
                IndexModel([('user_id', ASCENDING), ('timestamp', DESCENDING)], 
                          name='user_transactions_idx'),
                IndexModel([('timestamp', DESCENDING)], name='transaction_time_desc'),
                IndexModel([('reason', ASCENDING)], name='reason_idx')
            ]
            self.db.transactions.create_indexes(transactions_indexes)
            
            # Withdrawals collection indexes
            withdrawals_indexes = [
                IndexModel([('withdrawal_id', ASCENDING)], unique=True, name='withdrawal_id_unique'),
                IndexModel([('user_id', ASCENDING)], name='user_withdrawals_idx'),
                IndexModel([('status', ASCENDING)], name='status_idx'),
                IndexModel([('created_at', DESCENDING)], name='withdrawal_created_desc')
            ]
            self.db.withdrawals.create_indexes(withdrawals_indexes)
            
            # Broadcasts collection indexes
            broadcasts_indexes = [
                IndexModel([('broadcast_id', ASCENDING)], unique=True, name='broadcast_id_unique'),
                IndexModel([('created_at', DESCENDING)], name='broadcast_created_desc'),
                IndexModel([('status', ASCENDING)], name='broadcast_status_idx')
            ]
            self.db.broadcasts.create_indexes(broadcasts_indexes)
            
            logger.info("✅ Database indexes created successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to create indexes: {e}")
            raise
    
    def get_or_create_user(self, user_id: int, username: str = None, 
                          first_name: str = None, last_name: str = None) -> Dict:
        """
        Get user or create if doesn't exist
        
        Args:
            user_id: Telegram user ID
            username: Telegram username
            first_name: User first name
            last_name: User last name
            
        Returns:
            Dict: User document
        """
        try:
            user = self.db.users.find_one({'user_id': user_id})
            
            if not user:
                from uuid import uuid4
                user_data = {
                    'user_id': user_id,
                    'username': username,
                    'first_name': first_name,
                    'last_name': last_name,
                    'points': 0,
                    'referral_code': str(uuid4())[:8].upper(),
                    'referrer_id': None,
                    'total_referred': 0,
                    'daily_bonus_claimed': None,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow(),
                    'special_links': [],
                    'total_points_earned': 0,
                    'total_points_withdrawn': 0,
                    'is_banned': False,
                    'language': 'en'
                }
                
                result = self.db.users.insert_one(user_data)
                user_data['_id'] = result.inserted_id
                user = user_data
                
                logger.info(f"✅ Created new user: {user_id}")
            
            return user
            
        except Exception as e:
            logger.error(f"❌ Error in get_or_create_user: {e}")
            raise
    
    def update_user(self, user_id: int, update_data: Dict) -> bool:
        """
        Update user data
        
        Args:
            user_id: Telegram user ID
            update_data: Data to update
            
        Returns:
            bool: True if successful
        """
        try:
            update_data['updated_at'] = datetime.utcnow()
            result = self.db.users.update_one(
                {'user_id': user_id},
                {'$set': update_data}
            )
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error updating user {user_id}: {e}")
            return False
    
    def add_points(self, user_id: int, points: int, reason: str = '', 
                   source: str = 'system') -> Dict:
        """
        Add points to user with transaction tracking
        
        Args:
            user_id: Telegram user ID
            points: Points to add (can be negative)
            reason: Reason for points change
            source: Source of points (system, referral, bonus, etc.)
            
        Returns:
            Dict: Update result
        """
        try:
            # Update user points
            result = self.db.users.update_one(
                {'user_id': user_id},
                {
                    '$inc': {
                        'points': points,
                        'total_points_earned': max(points, 0)
                    },
                    '$set': {'updated_at': datetime.utcnow()}
                }
            )
            
            # Record transaction
            if result.modified_count > 0:
                transaction_data = {
                    'user_id': user_id,
                    'points': points,
                    'reason': reason,
                    'source': source,
                    'timestamp': datetime.utcnow(),
                    'balance_after': self.db.users.find_one(
                        {'user_id': user_id}, {'points': 1}
                    )['points']
                }
                self.db.transactions.insert_one(transaction_data)
            
            return {
                'success': result.modified_count > 0,
                'modified_count': result.modified_count
            }
            
        except Exception as e:
            logger.error(f"❌ Error adding points to user {user_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    def record_referral(self, referrer_id: int, referred_id: int) -> bool:
        """
        Record a successful referral
        
        Args:
            referrer_id: Referrer's user ID
            referred_id: Referred user's ID
            
        Returns:
            bool: True if successful
        """
        try:
            # Check if referral already exists
            existing = self.db.referrals.find_one({
                'referrer_id': referrer_id,
                'referred_id': referred_id
            })
            
            if existing:
                return False
            
            # Create referral record
            referral_data = {
                'referrer_id': referrer_id,
                'referred_id': referred_id,
                'timestamp': datetime.utcnow(),
                'status': 'completed',
                'points_awarded': int(os.getenv('REFERRAL_POINTS', 100))
            }
            
            self.db.referrals.insert_one(referral_data)
            
            # Update referrer's count
            self.db.users.update_one(
                {'user_id': referrer_id},
                {
                    '$inc': {'total_referred': 1},
                    '$set': {'updated_at': datetime.utcnow()}
                }
            )
            
            logger.info(f"✅ Recorded referral: {referrer_id} -> {referred_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error recording referral: {e}")
            return False
    
    def get_user_referrals(self, user_id: int, limit: int = 50) -> List[Dict]:
        """
        Get referrals made by a user
        
        Args:
            user_id: Referrer's user ID
            limit: Maximum number of referrals to return
            
        Returns:
            List[Dict]: List of referral records
        """
        try:
            referrals = list(self.db.referrals.find(
                {'referrer_id': user_id},
                sort=[('timestamp', DESCENDING)],
                limit=limit
            ))
            
            # Get user info for referred users
            for ref in referrals:
                referred_user = self.db.users.find_one(
                    {'user_id': ref['referred_id']},
                    {'first_name': 1, 'username': 1}
                )
                if referred_user:
                    ref['referred_user'] = referred_user
            
            return referrals
            
        except Exception as e:
            logger.error(f"❌ Error getting referrals for user {user_id}: {e}")
            return []
    
    def get_referral_stats(self, user_id: int) -> Dict:
        """
        Get comprehensive referral statistics for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict: Referral statistics
        """
        try:
            # Total referrals count
            total_referrals = self.db.referrals.count_documents({'referrer_id': user_id})
            
            # Today's referrals
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            today_referrals = self.db.referrals.count_documents({
                'referrer_id': user_id,
                'timestamp': {'$gte': today}
            })
            
            # This week's referrals
            week_start = today - timedelta(days=today.weekday())
            week_referrals = self.db.referrals.count_documents({
                'referrer_id': user_id,
                'timestamp': {'$gte': week_start}
            })
            
            # This month's referrals
            month_start = today.replace(day=1)
            month_referrals = self.db.referrals.count_documents({
                'referrer_id': user_id,
                'timestamp': {'$gte': month_start}
            })
            
            # Points from referrals
            referral_points = total_referrals * int(os.getenv('REFERRAL_POINTS', 100))
            
            return {
                'total_referrals': total_referrals,
                'today_referrals': today_referrals,
                'week_referrals': week_referrals,
                'month_referrals': month_referrals,
                'referral_points': referral_points,
                'referral_rank': self.get_user_rank(user_id)
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting referral stats for user {user_id}: {e}")
            return {}
    
    def get_leaderboard(self, limit: int = 20, time_period: str = 'all') -> List[Dict]:
        """
        Get referral leaderboard
        
        Args:
            limit: Number of top users to return
            time_period: Time period filter ('today', 'week', 'month', 'all')
            
        Returns:
            List[Dict]: Leaderboard entries
        """
        try:
            # Define time filter
            time_filters = {
                'today': datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
                'week': datetime.utcnow() - timedelta(days=7),
                'month': datetime.utcnow() - timedelta(days=30),
                'all': datetime.min
            }
            
            start_date = time_filters.get(time_period, datetime.min)
            
            # Aggregate referrals by referrer
            pipeline = [
                {
                    '$match': {
                        'timestamp': {'$gte': start_date},
                        'status': 'completed'
                    }
                },
                {
                    '$group': {
                        '_id': '$referrer_id',
                        'referral_count': {'$sum': 1},
                        'last_referral': {'$max': '$timestamp'}
                    }
                },
                {
                    '$sort': {'referral_count': -1, 'last_referral': -1}
                },
                {
                    '$limit': limit
                },
                {
                    '$lookup': {
                        'from': 'users',
                        'localField': '_id',
                        'foreignField': 'user_id',
                        'as': 'user_info'
                    }
                },
                {
                    '$unwind': '$user_info'
                },
                {
                    '$project': {
                        'user_id': '$_id',
                        'referral_count': 1,
                        'last_referral': 1,
                        'username': '$user_info.username',
                        'first_name': '$user_info.first_name',
                        'points': '$user_info.points',
                        'total_referred': '$user_info.total_referred'
                    }
                }
            ]
            
            leaderboard = list(self.db.referrals.aggregate(pipeline))
            return leaderboard
            
        except Exception as e:
            logger.error(f"❌ Error getting leaderboard: {e}")
            return []
    
    def get_user_rank(self, user_id: int) -> int:
        """
        Get user's rank in referral leaderboard
        
        Args:
            user_id: User ID
            
        Returns:
            int: User rank (0 if not in top list)
        """
        try:
            # Get all users sorted by referrals
            users = list(self.db.users.find(
                {},
                {'user_id': 1, 'total_referred': 1},
                sort=[('total_referred', DESCENDING)]
            ))
            
            # Find user rank (1-based)
            for rank, user in enumerate(users, 1):
                if user['user_id'] == user_id:
                    return rank
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ Error getting user rank: {e}")
            return 0
    
    def create_special_link(self, user_id: int, message: str, 
                           link_type: str = 'message') -> Dict:
        """
        Create a special link for a user
        
        Args:
            user_id: User ID
            message: Link message/content
            link_type: Type of link ('message', 'url', 'file')
            
        Returns:
            Dict: Special link data
        """
        try:
            from uuid import uuid4
            link_id = str(uuid4())[:8].upper()
            
            link_data = {
                'link_id': link_id,
                'user_id': user_id,
                'message': message,
                'link_type': link_type,
                'clicks': 0,
                'unique_clicks': 0,
                'points_earned': 0,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'is_active': True,
                'expires_at': None  # Optional: add expiration
            }
            
            result = self.db.special_links.insert_one(link_data)
            link_data['_id'] = result.inserted_id
            
            # Add link to user's special links array
            self.db.users.update_one(
                {'user_id': user_id},
                {'$push': {'special_links': link_id}}
            )
            
            logger.info(f"✅ Created special link {link_id} for user {user_id}")
            return link_data
            
        except Exception as e:
            logger.error(f"❌ Error creating special link: {e}")
            raise
    
    def get_special_link(self, link_id: str) -> Optional[Dict]:
        """
        Get special link by ID
        
        Args:
            link_id: Special link ID
            
        Returns:
            Optional[Dict]: Special link data or None
        """
        try:
            link = self.db.special_links.find_one({'link_id': link_id})
            return link
        except Exception as e:
            logger.error(f"❌ Error getting special link {link_id}: {e}")
            return None
    
    def record_link_click(self, link_id: str, clicker_id: int) -> bool:
        """
        Record a click on a special link
        
        Args:
            link_id: Special link ID
            clicker_id: User ID who clicked
            
        Returns:
            bool: True if successful
        """
        try:
            # Check if already clicked
            click_key = f'clickers.{clicker_id}'
            existing_click = self.db.special_links.find_one({
                'link_id': link_id,
                click_key: {'$exists': True}
            })
            
            # Update click counts
            update_data = {
                '$inc': {'clicks': 1},
                '$set': {'updated_at': datetime.utcnow()}
            }
            
            # Only count as unique click if first time
            if not existing_click:
                update_data['$inc']['unique_clicks'] = 1
                update_data['$set'][click_key] = datetime.utcnow()
            
            result = self.db.special_links.update_one(
                {'link_id': link_id},
                update_data
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error recording link click: {e}")
            return False
    
    def get_user_special_links(self, user_id: int) -> List[Dict]:
        """
        Get all special links for a user
        
        Args:
            user_id: User ID
            
        Returns:
            List[Dict]: List of special links
        """
        try:
            links = list(self.db.special_links.find(
                {'user_id': user_id},
                sort=[('created_at', DESCENDING)]
            ))
            return links
        except Exception as e:
            logger.error(f"❌ Error getting user special links: {e}")
            return []
    
    def create_withdrawal_request(self, user_id: int, amount: int, 
                                 payment_method: str, details: Dict) -> Optional[str]:
        """
        Create a withdrawal request
        
        Args:
            user_id: User ID
            amount: Amount to withdraw
            payment_method: Payment method (upi, bank, crypto, etc.)
            details: Payment details
            
        Returns:
            Optional[str]: Withdrawal ID or None
        """
        try:
            from uuid import uuid4
            withdrawal_id = str(uuid4())[:8].upper()
            
            withdrawal_data = {
                'withdrawal_id': withdrawal_id,
                'user_id': user_id,
                'amount': amount,
                'payment_method': payment_method,
                'details': details,
                'status': 'pending',
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'admin_notes': '',
                'processed_by': None,
                'processed_at': None
            }
            
            result = self.db.withdrawals.insert_one(withdrawal_data)
            
            if result.inserted_id:
                # Deduct points from user
                self.add_points(user_id, -amount, 'withdrawal_request', 'withdrawal')
                
                # Update user's withdrawn total
                self.db.users.update_one(
                    {'user_id': user_id},
                    {'$inc': {'total_points_withdrawn': amount}}
                )
                
                logger.info(f"✅ Created withdrawal request {withdrawal_id} for user {user_id}")
                return withdrawal_id
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error creating withdrawal request: {e}")
            return None
    
    def get_withdrawal_requests(self, status: str = None, 
                               limit: int = 50) -> List[Dict]:
        """
        Get withdrawal requests
        
        Args:
            status: Filter by status ('pending', 'approved', 'rejected')
            limit: Maximum number to return
            
        Returns:
            List[Dict]: List of withdrawal requests
        """
        try:
            query = {}
            if status:
                query['status'] = status
            
            requests = list(self.db.withdrawals.find(
                query,
                sort=[('created_at', DESCENDING)],
                limit=limit
            ))
            
            # Get user info for each request
            for req in requests:
                user = self.db.users.find_one(
                    {'user_id': req['user_id']},
                    {'first_name': 1, 'username': 1}
                )
                if user:
                    req['user_info'] = user
            
            return requests
            
        except Exception as e:
            logger.error(f"❌ Error getting withdrawal requests: {e}")
            return []
    
    def update_withdrawal_status(self, withdrawal_id: str, status: str, 
                                admin_id: int = None, notes: str = '') -> bool:
        """
        Update withdrawal request status
        
        Args:
            withdrawal_id: Withdrawal request ID
            status: New status ('approved', 'rejected')
            admin_id: Admin user ID who processed
            notes: Admin notes
            
        Returns:
            bool: True if successful
        """
        try:
            update_data = {
                'status': status,
                'updated_at': datetime.utcnow(),
                'admin_notes': notes
            }
            
            if admin_id:
                update_data['processed_by'] = admin_id
                update_data['processed_at'] = datetime.utcnow()
            
            result = self.db.withdrawals.update_one(
                {'withdrawal_id': withdrawal_id},
                {'$set': update_data}
            )
            
            # If rejected, return points to user
            if status == 'rejected':
                withdrawal = self.db.withdrawals.find_one(
                    {'withdrawal_id': withdrawal_id}
                )
                if withdrawal:
                    self.add_points(
                        withdrawal['user_id'], 
                        withdrawal['amount'], 
                        'withdrawal_rejected', 
                        'system'
                    )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error updating withdrawal status: {e}")
            return False
    
    def create_broadcast(self, admin_id: int, message: str, 
                        message_type: str = 'text', 
                        media_url: str = None) -> Optional[str]:
        """
        Create a broadcast message
        
        Args:
            admin_id: Admin user ID
            message: Broadcast message
            message_type: Type of message ('text', 'photo', 'video', 'document')
            media_url: URL for media files
            
        Returns:
            Optional[str]: Broadcast ID or None
        """
        try:
            from uuid import uuid4
            broadcast_id = str(uuid4())[:8].upper()
            
            broadcast_data = {
                'broadcast_id': broadcast_id,
                'admin_id': admin_id,
                'message': message,
                'message_type': message_type,
                'media_url': media_url,
                'status': 'pending',
                'total_users': 0,
                'sent_count': 0,
                'failed_count': 0,
                'created_at': datetime.utcnow(),
                'scheduled_for': None,
                'sent_at': None
            }
            
            result = self.db.broadcasts.insert_one(broadcast_data)
            
            if result.inserted_id:
                logger.info(f"✅ Created broadcast {broadcast_id} by admin {admin_id}")
                return broadcast_id
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Error creating broadcast: {e}")
            return None
    
    def get_broadcast_stats(self, broadcast_id: str) -> Dict:
        """
        Get statistics for a broadcast
        
        Args:
            broadcast_id: Broadcast ID
            
        Returns:
            Dict: Broadcast statistics
        """
        try:
            broadcast = self.db.broadcasts.find_one({'broadcast_id': broadcast_id})
            if not broadcast:
                return {}
            
            return {
                'total_users': broadcast.get('total_users', 0),
                'sent_count': broadcast.get('sent_count', 0),
                'failed_count': broadcast.get('failed_count', 0),
                'success_rate': (
                    (broadcast['sent_count'] / broadcast['total_users'] * 100)
                    if broadcast['total_users'] > 0 else 0
                ),
                'status': broadcast['status'],
                'created_at': broadcast['created_at'],
                'sent_at': broadcast.get('sent_at')
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting broadcast stats: {e}")
            return {}
    
    def get_bot_statistics(self) -> Dict:
        """
        Get comprehensive bot statistics
        
        Returns:
            Dict: Bot statistics
        """
        try:
            # Total users
            total_users = self.db.users.count_documents({})
            
            # Active users (last 7 days)
            week_ago = datetime.utcnow() - timedelta(days=7)
            active_users = self.db.users.count_documents({
                'updated_at': {'$gte': week_ago}
            })
            
            # Total points in system
            total_points_result = self.db.users.aggregate([
                {'$group': {'_id': None, 'total_points': {'$sum': '$points'}}}
            ])
            total_points = list(total_points_result)[0]['total_points'] if total_points_result else 0
            
            # Total referrals
            total_referrals = self.db.referrals.count_documents({})
            
            # Total withdrawals
            total_withdrawals = self.db.withdrawals.count_documents({})
            total_withdrawn_amount = self.db.withdrawals.aggregate([
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ])
            total_withdrawn = list(total_withdrawn_amount)[0]['total'] if total_withdrawn_amount else 0
            
            # Daily signups
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            daily_signups = self.db.users.count_documents({'created_at': {'$gte': today}})
            
            # Today's points earned
            today_transactions = self.db.transactions.aggregate([
                {'$match': {'timestamp': {'$gte': today}, 'points': {'$gt': 0}}},
                {'$group': {'_id': None, 'total': {'$sum': '$points'}}}
            ])
            today_points = list(today_transactions)[0]['total'] if today_transactions else 0
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'total_points': total_points,
                'total_referrals': total_referrals,
                'total_withdrawals': total_withdrawals,
                'total_withdrawn': total_withdrawn,
                'daily_signups': daily_signups,
                'today_points': today_points,
                'special_links': self.db.special_links.count_documents({}),
                'pending_withdrawals': self.db.withdrawals.count_documents({'status': 'pending'})
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting bot statistics: {e}")
            return {}
    
    def cleanup_old_data(self, days: int = 30) -> Dict:
        """
        Cleanup old data to save storage
        
        Args:
            days: Delete data older than this many days
            
        Returns:
            Dict: Cleanup statistics
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Cleanup old transactions (keep only 90 days)
            trans_result = self.db.transactions.delete_many({
                'timestamp': {'$lt': cutoff_date}
            })
            
            # Cleanup old broadcast logs
            broadcast_result = self.db.broadcast_logs.delete_many({
                'created_at': {'$lt': cutoff_date}
            })
            
            logger.info(f"✅ Cleaned up {trans_result.deleted_count} old transactions and {broadcast_result.deleted_count} broadcast logs")
            
            return {
                'transactions_deleted': trans_result.deleted_count,
                'broadcast_logs_deleted': broadcast_result.deleted_count
            }
            
        except Exception as e:
            logger.error(f"❌ Error cleaning up old data: {e}")
            return {}
    
    def backup_database(self) -> bool:
        """
        Create database backup (simplified version)
        For production, use MongoDB Atlas backups or mongodump
        
        Returns:
            bool: True if backup initiated
        """
        try:
            # Create backup collection
            backup_time = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            backup_collection_name = f'backup_{backup_time}'
            
            # Copy important collections
            collections_to_backup = ['users', 'referrals', 'transactions', 'withdrawals']
            
            for collection_name in collections_to_backup:
                documents = list(self.db[collection_name].find({}))
                if documents:
                    self.db[backup_collection_name].insert_many(documents)
            
            logger.info(f"✅ Database backup created: {backup_collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error creating database backup: {e}")
            return False
    
    def close_connection(self) -> None:
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("✅ MongoDB connection closed")


# Singleton instance
db_manager = DatabaseManager()
