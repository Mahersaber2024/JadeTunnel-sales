import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_config):
        self.db_config = db_config
        self.conn = None
        self.connect()
        self._create_tables()
        self._add_missing_columns()
    
    def connect(self):
        """Establish connection to PostgreSQL"""
        try:
            if self.conn and not self.conn.closed:
                return
            self.conn = psycopg2.connect(**self.db_config)
            self.conn.autocommit = False
            logger.info("✅ Connected to PostgreSQL successfully")
        except psycopg2.OperationalError as e:
            if "does not exist" in str(e):
                logger.error(f"❌ Database '{self.db_config['database']}' does not exist!")
                logger.info("📌 Please run: python setup_db.py")
            else:
                logger.error(f"❌ Database connection error: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Database connection error: {e}")
            raise
    
    def get_cursor(self):
        """Get a cursor with RealDictCursor"""
        try:
            if self.conn and self.conn.closed:
                self.connect()
            return self.conn.cursor(cursor_factory=RealDictCursor)
        except Exception as e:
            logger.error(f"Error getting cursor: {e}")
            self.connect()
            return self.conn.cursor(cursor_factory=RealDictCursor)
    
    def _add_missing_columns(self):
        """Add missing columns to existing tables"""
        try:
            cursor = self.get_cursor()
            
            # Check if referral_count column exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='referral_count'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0")
                logger.info("✅ Added referral_count column to users table")
            
            # Check if remaining_volume column exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='remaining_volume'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN remaining_volume INTEGER DEFAULT 0")
                logger.info("✅ Added remaining_volume column to users table")
            
            # Check if plan_type column exists in users table
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='plan_type'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE users ADD COLUMN plan_type VARCHAR(50) DEFAULT NULL")
                logger.info("✅ Added plan_type column to users table")

            # Check if plan_name column exists in subscriptions table
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='subscriptions' AND column_name='plan_name'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE subscriptions ADD COLUMN plan_name VARCHAR(100) DEFAULT NULL")
                logger.info("✅ Added plan_name column to subscriptions table")
    
            # Check if remaining_volume column exists in subscriptions table
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='subscriptions' AND column_name='remaining_volume'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE subscriptions ADD COLUMN remaining_volume INTEGER DEFAULT 0")
                logger.info("✅ Added remaining_volume column to subscriptions table")

            # Check if email column exists in subscriptions table
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='subscriptions' AND column_name='email'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE subscriptions ADD COLUMN email VARCHAR(255) DEFAULT NULL")
                logger.info("✅ Added email column to subscriptions table")

            # Check if panel_id column exists in subscriptions table
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='subscriptions' AND column_name='panel_id'
            """)
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE subscriptions ADD COLUMN panel_id VARCHAR(50) DEFAULT NULL")
                logger.info("✅ Added panel_id column to subscriptions table")
        
            # Commit all changes at once
            self.conn.commit()
            cursor.close()
            logger.info("✅ Missing columns checked/added successfully")
            
        except Exception as e:
            logger.error(f"Error adding missing columns: {e}")
            if self.conn:
                self.conn.rollback()
    
    def _create_tables(self):
        """Create tables if they don't exist"""
        try:
            cursor = self.get_cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    balance BIGINT DEFAULT 30000,
                    referred_by BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (referred_by) REFERENCES users(user_id) ON DELETE SET NULL
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    protocol VARCHAR(50) NOT NULL,
                    duration_days INTEGER NOT NULL,
                    email VARCHAR(255),
                    plan_type VARCHAR(50) DEFAULT NULL,
                    plan_name VARCHAR(100) DEFAULT NULL,
                    remaining_volume INTEGER DEFAULT 0,
                    panel_id VARCHAR(50) DEFAULT NULL,
                    config_data TEXT,
                    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_date TIMESTAMP NOT NULL,
                    status VARCHAR(20) DEFAULT 'active',
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount BIGINT NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invite_codes (
                    code VARCHAR(50) PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    uses INTEGER DEFAULT 0,
                    max_uses INTEGER DEFAULT 5,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_invite_codes_user_id ON invite_codes(user_id)")
            
            self.conn.commit()
            cursor.close()
            logger.info("✅ Tables verified/created successfully")
        except Exception as e:
            logger.error(f"❌ Error creating tables: {e}")
            self.conn.rollback()
    
    def add_user(self, user_id: int, username: str, first_name: str, referred_by: Optional[int] = None):
        """Add a new user"""
        cursor = None
        try:
            cursor = self.get_cursor()
            
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            if cursor.fetchone():
                return False
            
            cursor.execute(
                "INSERT INTO users (user_id, username, first_name, referred_by) VALUES (%s, %s, %s, %s) RETURNING user_id",
                (user_id, username, first_name, referred_by)
            )
            self.conn.commit()
            
            self.add_transaction(user_id, 30000, "bonus", "هدیه عضویت")
            
            if referred_by:
                cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (referred_by,))
                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE users SET referral_count = COALESCE(referral_count, 0) + 1 WHERE user_id = %s",
                        (referred_by,)
                    )
                    cursor.execute(
                        "UPDATE users SET balance = balance + 20000 WHERE user_id = %s",
                        (referred_by,)
                    )
                    self.add_transaction(referred_by, 20000, "referral_bonus", f"پاداش دعوت کاربر {user_id}")
                    self.conn.commit()
            
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
    
    def get_user(self, user_id: int):
        """Get user by ID"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user = cursor.fetchone()
            return user
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
    
    def update_balance(self, user_id: int, amount: int):
        """Update user balance"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                (amount, user_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating balance: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
    
    def add_transaction(self, user_id: int, amount: int, type_: str, description: str):
        """Add a transaction record"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "INSERT INTO transactions (user_id, amount, type, description) VALUES (%s, %s, %s, %s)",
                (user_id, amount, type_, description)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding transaction: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
    
    def add_subscription(self, user_id: int, protocol: str, duration_days: int, 
                         plan_type: str = None, initial_volume: int = 0, 
                         plan_name: str = None, email: str = None, 
                         panel_id: str = None, config_data: str = None):
        """Add a new subscription with panel_id"""
        cursor = None
        try:
            start_date = datetime.now()
            end_date = start_date + timedelta(days=duration_days)
            config_data = config_data or f"EMAIL:{email}"

            cursor = self.get_cursor()
            cursor.execute(
                """INSERT INTO subscriptions 
                   (user_id, protocol, duration_days, email, plan_type, plan_name, 
                    remaining_volume, panel_id, config_data, start_date, end_date) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
                   RETURNING id""",
                (user_id, protocol, duration_days, email, plan_type, plan_name, 
                 initial_volume, panel_id, config_data, start_date, end_date)
            )
            sub_id = cursor.fetchone()['id']
            self.conn.commit()
            return sub_id
        except Exception as e:
            logger.error(f"Error adding subscription: {e}")
            if self.conn:
                self.conn.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
    
    def get_active_subscriptions(self, user_id: int):
        """Get active subscriptions for a user"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT * FROM subscriptions WHERE user_id = %s AND status = 'active' AND end_date > NOW()",
                (user_id,)
            )
            subs = cursor.fetchall()
            return subs
        except Exception as e:
            logger.error(f"Error getting subscriptions: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
    
    def get_inactive_subscriptions_count(self, user_id: int):
        """Get count of inactive subscriptions"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE user_id = %s AND (status != 'active' OR end_date <= NOW())",
                (user_id,)
            )
            count = cursor.fetchone()['count']
            return count
        except Exception as e:
            logger.error(f"Error getting inactive subscriptions: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()
    
    # ============ Referral System Methods ============
    
    def get_referral_count(self, user_id: int) -> int:
        """Get number of successful referrals for a user"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT COALESCE(referral_count, 0) as referral_count FROM users WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            return result['referral_count'] if result else 0
        except Exception as e:
            logger.error(f"Error getting referral count: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()
    
    def get_total_commission(self, user_id: int) -> int:
        """Get total commission earned from referrals"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions "
                "WHERE user_id = %s AND type = 'referral_bonus'",
                (user_id,)
            )
            result = cursor.fetchone()
            return result['total'] if result else 0
        except Exception as e:
            logger.error(f"Error getting total commission: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()
    
    def increment_referral_count(self, user_id: int) -> bool:
        """Increment referral count for a user"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "UPDATE users SET referral_count = COALESCE(referral_count, 0) + 1 WHERE user_id = %s",
                (user_id,)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error incrementing referral count: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
    
    def get_referral_stats(self, user_id: int) -> dict:
        """Get all referral statistics for a user"""
        cursor = None
        try:
            cursor = self.get_cursor()
            
            cursor.execute(
                "SELECT COALESCE(referral_count, 0) as referral_count FROM users WHERE user_id = %s",
                (user_id,)
            )
            count_result = cursor.fetchone()
            referral_count = count_result['referral_count'] if count_result else 0
            
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0) as total FROM transactions "
                "WHERE user_id = %s AND type = 'referral_bonus'",
                (user_id,)
            )
            commission_result = cursor.fetchone()
            total_commission = commission_result['total'] if commission_result else 0
            
            cursor.execute(
                "SELECT user_id, first_name, username, created_at FROM users "
                "WHERE referred_by = %s ORDER BY created_at DESC",
                (user_id,)
            )
            referred_users = cursor.fetchall()
            
            return {
                'referral_count': referral_count,
                'total_commission': total_commission,
                'referred_users': referred_users
            }
        except Exception as e:
            logger.error(f"Error getting referral stats: {e}")
            return {
                'referral_count': 0,
                'total_commission': 0,
                'referred_users': []
            }
        finally:
            if cursor:
                cursor.close()
    
    def get_referrer(self, user_id: int) -> Optional[int]:
        """Get the user ID of who referred this user"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT referred_by FROM users WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            return result['referred_by'] if result else None
        except Exception as e:
            logger.error(f"Error getting referrer: {e}")
            return None
        finally:
            if cursor:
                cursor.close()
    
    # ============ Volume Management Methods ============
    
    def add_volume(self, user_id: int, volume_gb: int) -> bool:
        """Add volume to user's custom charge plan"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "UPDATE users SET remaining_volume = COALESCE(remaining_volume, 0) + %s WHERE user_id = %s",
                (volume_gb, user_id)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding volume: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
    
    def get_remaining_volume(self, user_id: int) -> int:
        """Get remaining volume for user"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT COALESCE(remaining_volume, 0) as remaining_volume FROM users WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()
            return result['remaining_volume'] if result else 0
        except Exception as e:
            logger.error(f"Error getting remaining volume: {e}")
            return 0
        finally:
            if cursor:
                cursor.close()

    def get_user_subscriptions(self, user_id: int):
        """Get all subscriptions for a user (including inactive)"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT * FROM subscriptions WHERE user_id = %s ORDER BY id DESC",
                (user_id,)
            )
            subs = cursor.fetchall()
            return subs
        except Exception as e:
            logger.error(f"Error getting user subscriptions: {e}")
            return []
        finally:
            if cursor:
                cursor.close()

    def delete_subscription(self, subscription_id: int) -> bool:
        """Delete a subscription by ID"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "DELETE FROM subscriptions WHERE id = %s",
                (subscription_id,)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting subscription: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()

    def add_volume_to_subscription(self, subscription_id, volume_gb):
        """Add volume to a specific subscription"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE subscriptions 
            SET remaining_volume = COALESCE(remaining_volume, 0) + %s 
            WHERE id = %s
        """, (volume_gb, subscription_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_subscription(self, subscription_id):
        """Get a specific subscription by ID"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, user_id, protocol, duration_days, email,
               plan_type, remaining_volume, start_date, end_date
            FROM subscriptions 
            WHERE id = %s
        """, (subscription_id,))
        row = cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'protocol': row[2],
                'duration_days': row[3],
                'email': row[4],
                'plan_type': row[5],
                'remaining_volume': row[6],
                'start_date': row[7],
                'end_date': row[8]
            }
        return None

    def get_custom_charge_subscriptions(self, user_id: int):
        """Get active custom_charge subscriptions for a user"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "SELECT * FROM subscriptions WHERE user_id = %s AND plan_type = 'custom_charge' "
                "AND status = 'active' AND end_date > NOW() ORDER BY id ASC",
                (user_id,)
            )
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting custom charge subscriptions: {e}")
            return []
        finally:
            if cursor:
                cursor.close()

    # ============ Admin: Delete User / Reset Balance ============
    def delete_user(self, user_id: int) -> bool:
        """
        Delete a user completely from the database.
        Subscriptions, transactions, and invite_codes are removed automatically
        via ON DELETE CASCADE foreign keys.
        """
        cursor = None
        try:
            cursor = self.get_cursor()
            # اگر این کاربر معرف کاربران دیگری بوده، referred_by آن‌ها NULL می‌شود (ON DELETE SET NULL)
            cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
            deleted = cursor.rowcount > 0
            self.conn.commit()
            return deleted
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()

    def reset_balance(self, user_id: int) -> bool:
        """Reset a user's wallet balance to zero"""
        cursor = None
        try:
            cursor = self.get_cursor()
            cursor.execute(
                "UPDATE users SET balance = 0 WHERE user_id = %s",
                (user_id,)
            )
            updated = cursor.rowcount > 0
            self.conn.commit()
            return updated
        except Exception as e:
            logger.error(f"Error resetting balance for user {user_id}: {e}")
            if self.conn:
                self.conn.rollback()
            return False
        finally:
            if cursor:
                cursor.close()
