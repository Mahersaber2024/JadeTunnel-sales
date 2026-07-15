import os
import json
import getpass
from typing import Optional, List, Any  # اضافه کردن این خط

CONFIG_FILE = 'config.json'

class Config:
    def __init__(self):
        self.config = {}
        self.load()
    
    def load(self):
        """Load configuration from file"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                return True
            except Exception as e:
                print(f"⚠️ Error loading config: {e}")
                return False
        return False
    
    def save(self):
        """Save configuration to file"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            print("✅ Config saved successfully!")
            return True
        except Exception as e:
            print(f"❌ Error saving config: {e}")
            return False
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
        self.save()
    
    def is_configured(self):
        """Check if all required configs are set"""
        return (self.get('bot_token') and 
                self.get('db_password') and
                self.get('db_host') and
                self.get('db_name') and
                self.get('db_user'))
    
    def setup_interactive(self):
        """Interactive configuration setup"""
        print("\n🔧 First Time Setup - VPN Bot")
        print("=" * 50)
        print("Please enter the following information:\n")
        
        # Bot Token
        print("🤖 Bot Token:")
        print("  Get it from @BotFather on Telegram")
        token = input("  Enter Bot Token: ").strip()
        while not token:
            print("  ❌ Bot Token is required!")
            token = input("  Enter Bot Token: ").strip()
        self.set('bot_token', token)
        
        # Database Configuration
        print("\n📊 Database Configuration:")
        
        host = input(f"  Database Host [localhost]: ").strip()
        self.set('db_host', host if host else 'localhost')
        
        port = input(f"  Database Port [5432]: ").strip()
        self.set('db_port', int(port) if port else 5432)
        
        db_name = input(f"  Database Name [jadetunnel_base]: ").strip()
        self.set('db_name', db_name if db_name else 'jadetunnel_base')
        
        db_user = input(f"  Database User [cbu_user]: ").strip()
        self.set('db_user', db_user if db_user else 'cbu_user')
        
        # Password input with hidden characters
        db_password = getpass.getpass(f"  Database Password: ")
        while not db_password:
            print("  ❌ Password is required!")
            db_password = getpass.getpass(f"  Database Password: ")
        self.set('db_password', db_password)
        
        # Admin IDs
        print("\n👑 Admin Configuration:")
        admin_input = input("  Admin User IDs (comma separated, e.g. 12345,67890) [optional]: ").strip()
        admin_ids = []
        if admin_input:
            for part in admin_input.split(","):
                part = part.strip()
                if part.isdigit():
                    admin_ids.append(int(part))
        self.set('admin_ids', admin_ids)
        
        # Log Group ID
        print("\n📢 Log Group Configuration:")
        log_group_input = input("  Log Group ID (e.g. -1001234567890) [optional]: ").strip()
        if log_group_input:
            try:
                self.set('LOG_GROUP_ID', int(log_group_input))
            except ValueError:
                print("  ⚠️ Invalid group ID format. Skipping...")
        
        print("\n" + "=" * 50)
        print("✅ Setup completed successfully!")
        self.show_config()
    
    def show_config(self):
        """Display current configuration"""
        print("\n📋 Current Configuration:")
        print("=" * 40)
        token = self.get('bot_token')
        print(f"🤖 Bot Token: {'*' * 10}{token[-5:] if token else 'Not set'}")
        print(f"📊 Database: {self.get('db_host')}:{self.get('db_port')}/{self.get('db_name')}")
        print(f"👤 User: {self.get('db_user')}")
        print(f"🔑 Password: {'*' * 10 if self.get('db_password') else 'Not set'}")
        admin_ids = self.get_admin_ids()
        print(f"👑 Admins: {admin_ids if admin_ids else 'Not set'}")
        log_group_id = self.get_log_group_id()
        print(f"📢 Log Group: {log_group_id if log_group_id else 'Not set'}")
        print("=" * 40)
    
    def get_db_config(self):
        """Get database configuration dictionary"""
        return {
            'host': self.get('db_host', 'localhost'),
            'port': self.get('db_port', 5432),
            'database': self.get('db_name', 'jadetunnel_base'),
            'user': self.get('db_user', 'cbu_user'),
            'password': self.get('db_password', '')
        }
    
    def get_admin_ids(self) -> List[int]:
        """Get list of admin user IDs"""
        ids = self.get('admin_ids', [])
        return ids if isinstance(ids, list) else []

    def get_log_group_id(self) -> Optional[int]:
        """Get log group ID from config"""
        group_id = self.get('LOG_GROUP_ID')
        if group_id:
            try:
                return int(group_id)
            except ValueError:
                return None
        return None

# Global config instance
config = Config()