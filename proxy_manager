#!/usr/bin/env python3
# proxy_manager.py - مدیریت لیست پروکسی‌های ویژه اشتراک

import os
import json
import logging
from pathlib import Path
from typing import Dict
from datetime import datetime

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent / 'config'
PROXIES_FILE = str(CONFIG_DIR / 'proxies.json')


class ProxyManager:
    """Manager for the list of special proxies offered to users"""

    def __init__(self):
        self.proxies: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if os.path.exists(PROXIES_FILE):
            try:
                with open(PROXIES_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.proxies = data.get('proxies', {})
            except Exception as e:
                logger.error(f"Error loading proxies: {e}")
                self.proxies = {}
        else:
            self.proxies = {}

    def _save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(PROXIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(
                    {'proxies': self.proxies, 'updated_at': datetime.now().isoformat()},
                    f, indent=2, ensure_ascii=False
                )
        except Exception as e:
            logger.error(f"Error saving proxies: {e}")

    def get_all_proxies(self) -> Dict[str, dict]:
        return self.proxies

    def add_proxy(self, name: str, value: str) -> str:
        proxy_id = f"proxy_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        self.proxies[proxy_id] = {
            'name': name,
            'value': value,
            'created_at': datetime.now().isoformat()
        }
        self._save()
        return proxy_id

    def remove_proxy(self, proxy_id: str) -> bool:
        if proxy_id in self.proxies:
            del self.proxies[proxy_id]
            self._save()
            return True
        return False


_proxy_manager = None

def get_proxy_manager() -> ProxyManager:
    global _proxy_manager
    if _proxy_manager is None:
        _proxy_manager = ProxyManager()
    return _proxy_manager
