#!/usr/bin/env python3
# panel_manager.py - مدیریت چندین پنل 3xUI با پشتیب از طرح‌ها

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import requests

logger = logging.getLogger(__name__)

# ========== Settings ==========
def find_env_file():
    """Find .env file in current directory or parent directories"""
    current_dir = Path(__file__).parent.absolute()
    
    env_path = current_dir / '.env'
    if env_path.exists():
        return str(env_path)
    
    parent_dir = current_dir.parent
    env_path = parent_dir / '.env'
    if env_path.exists():
        return str(env_path)
    
    opt_path = Path('/opt/x3-traffic-reset/.env')
    if opt_path.exists():
        return str(opt_path)
    
    return None

ENV_FILE = find_env_file()
CONFIG_DIR = Path(__file__).parent / 'config'
PANELS_FILE = str(CONFIG_DIR / 'panels.json')

# ========== Panel Manager Class ==========
class PanelManager:
    """Manager for multiple 3xUI panels"""
    
    def __init__(self):
        self.panels: Dict[str, dict] = {}
        self.default_panel: Optional[str] = None
        self.panel_usage: Dict[str, int] = {}
        self._load_panels()
    
    def _load_panels(self):
        """Load panels from JSON file"""
        if os.path.exists(PANELS_FILE):
            try:
                with open(PANELS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.panels = data.get('panels', {})
                    self.default_panel = data.get('default_panel')
                    self.panel_usage = data.get('usage', {})
                    logger.info(f"Loaded {len(self.panels)} panels from config")
            except Exception as e:
                logger.error(f"Error loading panels: {e}")
                self.panels = {}
                self.default_panel = None
                self.panel_usage = {}
        else:
            # Try to load from .env for backward compatibility
            self._migrate_from_env()
    
    def _save_panels(self):
        """Save panels to JSON file"""
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            data = {
                'panels': self.panels,
                'default_panel': self.default_panel,
                'usage': self.panel_usage,
                'updated_at': datetime.now().isoformat()
            }
            with open(PANELS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Panels saved successfully")
        except Exception as e:
            logger.error(f"Error saving panels: {e}")
    
    def _migrate_from_env(self):
        """Migrate from single panel in .env to multiple panels"""
        if not ENV_FILE or not os.path.exists(ENV_FILE):
            return
        
        env = {}
        try:
            with open(ENV_FILE, 'r') as f:
                for line in f:
                    line = line.rstrip('\n')
                    if not line or line.strip().startswith('#'):
                        continue
                    if '=' in line:
                        key, _, value = line.partition('=')
                        env[key.strip()] = value.strip()
        except Exception as e:
            logger.error(f"Error reading .env: {e}")
            return
        
        panel_base = env.get("PANEL_BASE", "")
        username = env.get("USERNAME", "")
        password = env.get("PASSWORD", "")
        
        if panel_base and username and password:
            # Add as default panel with all plan types
            panel_id = "default"
            self.panels[panel_id] = {
                'id': panel_id,
                'name': 'پنل اصلی',
                'panel_base': panel_base,
                'username': username,
                'password': password,
                'inbound_ids': [82, 80, 81],
                'max_subscriptions': 100,
                'is_default': True,
                'enabled': True,
                'plan_types': ['new', 'old', 'custom_charge'],
                'created_at': datetime.now().isoformat()
            }
            self.default_panel = panel_id
            self.panel_usage[panel_id] = 0
            self._save_panels()
            logger.info("Migrated from .env to panels config")
    
    def get_panel(self, panel_id: str = None) -> Optional[dict]:
        """Get a panel by ID, or default panel if None"""
        if not panel_id:
            panel_id = self.default_panel
        return self.panels.get(panel_id)
    
    def get_default_panel(self) -> Optional[dict]:
        """Get default panel"""
        if self.default_panel:
            return self.panels.get(self.default_panel)
        return None
    
    def get_all_panels(self) -> Dict[str, dict]:
        """Get all panels"""
        return self.panels
    
    def get_panel_for_subscription(self, plan_type: str = 'old') -> Tuple[Optional[dict], Optional[str]]:
        """
        Get the best panel to use for a new subscription based on plan type.
        Returns (panel_data, panel_id)
    
        Args:
            plan_type: نوع طرح ('new', 'old', 'custom_charge')
        """
        if not self.panels:
            return None, None
    
        # Get all active panels (not disabled)
        active_panels = {
            pid: p for pid, p in self.panels.items()
            if p.get('enabled', True)
        }
    
        if not active_panels:
            return None, None
    
        # اول پنلی که دقیقاً این plan_type را پشتیبانی می‌کند
        for panel_id, panel in active_panels.items():
            plan_types = panel.get('plan_types', ['new', 'old', 'custom_charge'])
            usage = self.panel_usage.get(panel_id, 0)
            max_subs = panel.get('max_subscriptions', 100)
        
            if plan_type in plan_types and usage < max_subs:
                return panel, panel_id
    
        # اگر پنل دقیقاً پشتیبانی نکرد، پنلی که همه طرح‌ها را پشتیبانی می‌کند
        for panel_id, panel in active_panels.items():
            plan_types = panel.get('plan_types', ['new', 'old', 'custom_charge'])
            usage = self.panel_usage.get(panel_id, 0)
            max_subs = panel.get('max_subscriptions', 100)
        
            if len(plan_types) == 3 and usage < max_subs:
                return panel, panel_id
    
        # آخرین راه: هر پنل فعال با ظرفیت خالی
        for panel_id, panel in active_panels.items():
            usage = self.panel_usage.get(panel_id, 0)
            max_subs = panel.get('max_subscriptions', 100)
            if usage < max_subs:
                return panel, panel_id
    
        # If all panels are full, return None
        return None, None
    
    def increment_usage(self, panel_id: str):
        """Increment usage counter for a panel"""
        if panel_id in self.panel_usage:
            self.panel_usage[panel_id] += 1
        else:
            self.panel_usage[panel_id] = 1
        self._save_panels()
    
    def decrement_usage(self, panel_id: str):
        """Decrement usage counter for a panel"""
        if panel_id in self.panel_usage and self.panel_usage[panel_id] > 0:
            self.panel_usage[panel_id] -= 1
            self._save_panels()
    
    def add_panel(self, panel_id: str, name: str, panel_base: str, 
                  username: str, password: str, inbound_ids: List[int],
                  max_subscriptions: int = 100, is_default: bool = False,
                  plan_types: List[str] = None) -> bool:
        """Add a new panel"""
        if panel_id in self.panels:
            logger.error(f"Panel {panel_id} already exists")
            return False
        
        if plan_types is None:
            plan_types = ['new', 'old', 'custom_charge']
        
        self.panels[panel_id] = {
            'id': panel_id,
            'name': name,
            'panel_base': panel_base.rstrip('/'),
            'username': username,
            'password': password,
            'inbound_ids': inbound_ids,
            'max_subscriptions': max_subscriptions,
            'enabled': True,
            'is_default': is_default,
            'plan_types': plan_types,
            'created_at': datetime.now().isoformat()
        }
        
        if is_default:
            self.default_panel = panel_id
        
        self.panel_usage[panel_id] = 0
        self._save_panels()
        return True
    
    def remove_panel(self, panel_id: str) -> bool:
        """Remove a panel"""
        if panel_id not in self.panels:
            return False
        
        # Don't remove if it's the only panel
        if len(self.panels) <= 1:
            logger.error("Cannot remove the last panel")
            return False
        
        del self.panels[panel_id]
        if panel_id in self.panel_usage:
            del self.panel_usage[panel_id]
        
        if self.default_panel == panel_id:
            # Set another panel as default
            self.default_panel = next(iter(self.panels))
            self.panels[self.default_panel]['is_default'] = True
        
        self._save_panels()
        return True
    
    def set_default_panel(self, panel_id: str) -> bool:
        """Set a panel as default"""
        if panel_id not in self.panels:
            return False
        
        # Remove default from all panels
        for pid in self.panels:
            self.panels[pid]['is_default'] = False
        
        self.panels[panel_id]['is_default'] = True
        self.default_panel = panel_id
        self._save_panels()
        return True
    
    def update_panel(self, panel_id: str, **kwargs) -> bool:
        """Update panel settings"""
        if panel_id not in self.panels:
            return False
        
        for key, value in kwargs.items():
            if key in ['name', 'panel_base', 'username', 'password', 
                       'inbound_ids', 'max_subscriptions', 'enabled', 'plan_types']:
                self.panels[panel_id][key] = value
        
        self._save_panels()
        return True
    
    def test_panel_connection(self, panel_base: str, username: str, password: str) -> Tuple[bool, str]:
        """Test connection to a panel"""
        try:
            # Test CSRF token
            csrf_url = f"{panel_base}/csrf-token"
            session = requests.Session()
            
            response = session.get(csrf_url, verify=False, timeout=10)
            response.raise_for_status()
            csrf_token = response.json().get('obj')
            
            if not csrf_token:
                return False, "Failed to get CSRF token"
            
            # Test login
            login_url = f"{panel_base}/login"
            response = session.post(
                login_url,
                json={"username": username, "password": password},
                headers={"x-csrf-token": csrf_token},
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            
            return True, "Connection successful"
            
        except requests.exceptions.Timeout:
            return False, "Connection timeout"
        except requests.exceptions.ConnectionError:
            return False, "Connection failed - check URL"
        except Exception as e:
            return False, f"Error: {str(e)}"


# ========== Singleton instance ==========
_panel_manager = None

def get_panel_manager() -> PanelManager:
    """Get or create panel manager instance"""
    global _panel_manager
    if _panel_manager is None:
        _panel_manager = PanelManager()
    return _panel_manager
