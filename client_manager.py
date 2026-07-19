#!/usr/bin/env python3
# client_manager.py - 3xUI Client Manager with multi-panel support

import os
import sys
import json
import requests
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# Import panel manager
from panel_manager import get_panel_manager, PanelManager

class PanelClient:
    """Client for interacting with 3xUI panel API using CSRF"""
    
    def __init__(self, panel_id: str = None):
        self.panel_manager = get_panel_manager()
        self.panel_id = panel_id
        self.panel_data = None
        self.panel_base = None
        self.username = None
        self.password = None
        self.inbound_ids = None
        self.session = None
        self.csrf_token = None
        self._load_panel_config()
    
    def _load_panel_config(self):
        """Load panel configuration from panel manager"""
        if self.panel_id:
            self.panel_data = self.panel_manager.get_panel(self.panel_id)
        else:
            self.panel_data = self.panel_manager.get_default_panel()
        
        if self.panel_data:
            self.panel_base = self.panel_data.get('panel_base')
            self.username = self.panel_data.get('username')
            self.password = self.panel_data.get('password')
            self.inbound_ids = self.panel_data.get('inbound_ids', [1])
            self.panel_id = self.panel_data.get('id')
            logger.info(f"Using panel: {self.panel_data.get('name')} ({self.panel_base})")
        else:
            logger.error(f"No panel configured (panel_id={self.panel_id!r})")
    
    def _get_session(self):
        """Get session with CSRF token"""
        if not self.panel_base or not self.username or not self.password:
            return False
        
        self.session = requests.Session()
        
        # 1. Get CSRF token
        csrf_url = f"{self.panel_base}/csrf-token"
        try:
            response = self.session.get(csrf_url, verify=False, timeout=10)
            response.raise_for_status()
            self.csrf_token = response.json().get('obj')
            if not self.csrf_token:
                logger.error("Failed to get CSRF token")
                return False
            logger.info("CSRF token obtained")
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error (CSRF): {e}")
            return False
        
        # 2. Login with CSRF token
        login_url = f"{self.panel_base}/login"
        try:
            response = self.session.post(
                login_url,
                json={"username": self.username, "password": self.password},
                headers={"x-csrf-token": self.csrf_token},
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            logger.info("Panel login successful")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Login failed: {e}")
            return False
    
    def _ensure_session(self):
        """Ensure we have a valid session"""
        if self.session and self.csrf_token:
            return True
        return self._get_session()
    
    def _get_headers(self):
        """Get headers for API requests"""
        return {
            "x-csrf-token": self.csrf_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    def create_client(self, email, total_gb, expiry_days, inbound_ids=None, enable=True, limit_ip=0):
        """Create a new client in 3xUI panel"""
        if not self._ensure_session():
            return False, "Failed to authenticate with panel", None
        
        if inbound_ids is None:
            inbound_ids = self.inbound_ids or [1]
        
        if expiry_days > 0:
            expiry_time = int((datetime.now() + timedelta(days=expiry_days)).timestamp() * 1000)
        else:
            expiry_time = 0
        
        payload = {
            "client": {
                "email": email,
                "totalGB": total_gb,
                "expiryTime": expiry_time,
                "tgId": 0,
                "limitIp": limit_ip,
                "enable": enable
            },
            "inboundIds": inbound_ids
        }
        
        logger.info(f"Creating client on {self.panel_base} with payload: {json.dumps(payload, indent=2)}")
        
        url = f"{self.panel_base}/panel/api/clients/add"
        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                verify=False,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('success', False):
                client_data = self.get_client_info(email)
                self.panel_manager.increment_usage(self.panel_id)
                return True, result.get('msg', 'Client created'), client_data
            else:
                return False, result.get('msg', 'Unknown error from panel'), None
                
        except Exception as e:
            error_msg = f"Error creating client: {e}"
            logger.error(error_msg)
            return False, error_msg, None
    
    def get_client_info(self, email):
        """Get client info by email"""
        if not self._ensure_session():
            return None
        
        url = f"{self.panel_base}/panel/api/clients/get/{email}"
        try:
            response = self.session.get(
                url,
                headers=self._get_headers(),
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            return result.get('obj')
        except Exception as e:
            logger.error(f"Error getting client info: {e}")
            return None
    
    def get_client_links(self, email):
        """Get client links using /panel/api/clients/links/{email}"""
        if not self._ensure_session():
            return None
        
        url = f"{self.panel_base}/panel/api/clients/links/{email}"
        try:
            response = self.session.get(
                url,
                headers=self._get_headers(),
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('success', False):
                urls = result.get('obj', [])
                if urls and len(urls) > 0:
                    return urls
            return None
        except Exception as e:
            logger.error(f"Error getting client links for {email}: {e}")
            return None
    
    def delete_client(self, email, keep_traffic=False):
        """Delete a client by email"""
        if not self._ensure_session():
            return False, "Failed to authenticate"
        
        keep = "?keepTraffic=1" if keep_traffic else ""
        url = f"{self.panel_base}/panel/api/clients/del/{email}{keep}"
        try:
            response = self.session.post(
                url,
                headers=self._get_headers(),
                verify=False,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()
            if result.get('success', False):
                self.panel_manager.decrement_usage(self.panel_id)
            return result.get('success', False), result.get('msg', 'Unknown')
        except Exception as e:
            return False, str(e)

    # ====================== تابع جدید برای افزایش حجم ======================
    def update_client_volume(self, email: str, new_total_gb):
        """
        ست کردن مستقیم حجم کل کلاینت در پنل با مقدار محاسبه‌شده در دیتابیس.

        توجه: جمع زدن حجم قبلی + جدید باید قبلاً در دیتابیس انجام شده باشد
        (توسط db.add_volume_to_subscription). این تابع دیگر حجم فعلی را
        از پنل نمی‌خواند و صرفاً مقدار کل نهایی را که از بیرون (دیتابیس)
        دریافت می‌کند روی پنل ست می‌کند.

        Args:
            email: ایمیل کاربر (شناسه یکتا)
            new_total_gb: حجم کل جدید (از دیتابیس، نه دلتای اضافه‌شده)

        Returns:
            (success, message, new_total_gb)
        """
        if not self._ensure_session():
            return False, "Failed to authenticate with panel", None

        # فقط برای فیلدهای دیگری که پنل برای آپدیت لازم دارد (expiryTime, tgId, enable)
        client_info = self.get_client_info(email)
        if not client_info:
            return False, f"Client with email '{email}' not found in panel", None

        logger.info(f"Updating client {email}: setting totalGB directly to {new_total_gb}GB (from DB)")

        payload = {
            "email": email,
            "totalGB": new_total_gb,
            "expiryTime": client_info.get('expiryTime', 0),
            "tgId": client_info.get('tgId', 0),
            "enable": client_info.get('enable', True)
        }

        url = f"{self.panel_base}/panel/api/clients/update/{email}"

        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                verify=False,
                timeout=30
            )

            response.raise_for_status()
            result = response.json()

            if result.get('success', False):
                return True, f"حجم کل کاربر روی پنل به {new_total_gb}GB بروزرسانی شد", new_total_gb
            else:
                return False, result.get('msg', 'خطا در آپدیت کاربر'), None

        except Exception as e:
            logger.error(f"Error updating volume for {email}: {e}")
            return False, str(e), None

class PanelClientFactory:
    """Factory for creating panel clients"""
    
    @staticmethod
    def get_client(panel_id: str = None) -> PanelClient:
        """Get a panel client for the specified panel or default"""
        return PanelClient(panel_id)
    
    @staticmethod
    def get_available_panel() -> Tuple[Optional[PanelClient], Optional[str]]:
        """Get a client for an available panel"""
        panel_manager = get_panel_manager()
        panel_data, panel_id = panel_manager.get_panel_for_subscription()
        
        if panel_data:
            return PanelClient(panel_id), panel_id
        return None, None
    
    @staticmethod
    def get_all_panels_info() -> dict:
        """Get info about all panels"""
        panel_manager = get_panel_manager()
        panels = panel_manager.get_all_panels()
        usage = panel_manager.panel_usage
        
        result = {}
        for pid, panel in panels.items():
            result[pid] = {
                'name': panel.get('name'),
                'panel_base': panel.get('panel_base'),
                'max_subscriptions': panel.get('max_subscriptions', 100),
                'current_usage': usage.get(pid, 0),
                'is_default': panel.get('is_default', False),
                'enabled': panel.get('enabled', True)
            }
        return result


# ========== Factory function ==========
# توجه: قبلاً یک نمونه‌ی PanelClient پیش‌فرض (بدون panel_id) در متغیر
# سراسری _default_client کش می‌شد و فقط بار اول ساخته می‌شد. اگر بعداً
# پنل پیش‌فرض عوض/اضافه می‌شد، این کلاینت قدیمی همچنان استفاده می‌شد و
# باعث خطای "No panel configured" در سرویس‌های جدا (مثل sub_api.py)
# می‌شد. ساخت PanelClient سبک است (فقط تنظیمات را می‌خواند؛ سشن HTTP
# فقط هنگام نیاز واقعی/lazy باز می‌شود)، پس دیگر کش نمی‌کنیم.

def get_panel_client(panel_id: str = None) -> PanelClient:
    """Get a fresh panel client instance (no stale caching)"""
    return PanelClient(panel_id)
