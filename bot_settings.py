import json
import os
import logging

# ============ Emergency Proxy Links (self-contained storage) ============
import json as _json
import os as _os

_EMERGENCY_PROXY_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "emergency_proxies.json")


logger = logging.getLogger(__name__)

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_settings.json")

DEFAULT_SETTINGS = {
    "sponsor_channel": "@jadetunnell",
    "sponsor_channel_title": "Jade Tunnel",
    "membership_required": True,
    "support_username": "@jadetunnel",
    "signup_bonus": 30000,
    "referral_bonus_inviter": 20000,
    "referral_bonus_invitee": 30000,
    "special_panel_id": None,                 # پنل اختصاصی کمیسیونی
    "special_panel_commission_percent": 50,
    "hybrid_payment_enabled": False,
    "card_number": "6219861065685272",
    "card_holder": "وحید صابر",
    "card_bank": "سامان",
    "combined_sub_base_url": "https://heysolo.ir",
    "lifeline_enabled": False,
    "emergency_plan_volume_gb": 10,      # <-- جدید
    "emergency_plan_duration_days": 10,
}

_settings_cache = None


def _load():
    global _settings_cache
    if _settings_cache is not None:
        return _settings_cache

    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading bot_settings.json: {e}")
            data = {}

    merged = {**DEFAULT_SETTINGS, **data}
    _settings_cache = merged
    return merged


def _save(data):
    global _settings_cache
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _settings_cache = data


def get_sponsor_channel() -> str:
    channel = _load().get("sponsor_channel", DEFAULT_SETTINGS["sponsor_channel"])
    channel = channel.strip()
    if not channel.startswith("@"):
        channel = "@" + channel.lstrip("@")
    return channel


def set_sponsor_channel(channel: str):
    channel = channel.strip()
    if "t.me/" in channel:
        channel = channel.split("t.me/")[-1].split("?")[0].strip("/")
    if not channel.startswith("@"):
        channel = "@" + channel.lstrip("@")
    data = _load()
    data["sponsor_channel"] = channel
    _save(data)


def get_sponsor_channel_title() -> str:
    title = _load().get("sponsor_channel_title", DEFAULT_SETTINGS["sponsor_channel_title"])
    return title.strip() or DEFAULT_SETTINGS["sponsor_channel_title"]


def set_sponsor_channel_title(title: str):
    title = title.strip()
    if not title:
        return
    data = _load()
    data["sponsor_channel_title"] = title
    _save(data)


def is_membership_required() -> bool:
    return bool(_load().get("membership_required", True))


def set_membership_required(value: bool):
    data = _load()
    data["membership_required"] = bool(value)
    _save(data)
    
def is_lifeline_enabled() -> bool:
    return bool(_load().get("lifeline_enabled", False))


def set_lifeline_enabled(value: bool):
    data = _load()
    data["lifeline_enabled"] = bool(value)
    _save(data)

def get_support_username() -> str:
    """همیشه با @ برمی‌گرداند"""
    username = _load().get("support_username", DEFAULT_SETTINGS["support_username"])
    username = username.strip()
    if not username.startswith("@"):
        username = "@" + username.lstrip("@")
    return username

def set_support_username(username: str):
    username = username.strip()
    if "t.me/" in username:
        username = username.split("t.me/")[-1].split("?")[0].strip("/")
    if not username.startswith("@"):
        username = "@" + username.lstrip("@")
    data = _load()
    data["support_username"] = username
    _save(data)

# ====================== Gift & Bonus Settings ======================

def get_signup_bonus() -> int:
    try:
        return int(_load().get("signup_bonus", DEFAULT_SETTINGS["signup_bonus"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["signup_bonus"]


def set_signup_bonus(amount: int):
    data = _load()
    data["signup_bonus"] = int(amount)
    _save(data)


def get_referral_bonus_inviter() -> int:
    try:
        return int(_load().get("referral_bonus_inviter", DEFAULT_SETTINGS["referral_bonus_inviter"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["referral_bonus_inviter"]


def set_referral_bonus_inviter(amount: int):
    data = _load()
    data["referral_bonus_inviter"] = int(amount)
    _save(data)


def get_referral_bonus_invitee() -> int:
    try:
        return int(_load().get("referral_bonus_invitee", DEFAULT_SETTINGS["referral_bonus_invitee"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["referral_bonus_invitee"]


def set_referral_bonus_invitee(amount: int):
    data = _load()
    data["referral_bonus_invitee"] = int(amount)
    _save(data)
    
# ====================== Commission-based Panel Access ======================

def get_special_panel_id():
    """پنل اختصاصی برای کاربرانی که کمیسیون کافی دارند"""
    return _load().get("special_panel_id", DEFAULT_SETTINGS["special_panel_id"])


def set_special_panel_id(panel_id):
    data = _load()
    data["special_panel_id"] = panel_id
    _save(data)


def get_special_panel_commission_percent() -> int:
    try:
        return int(_load().get(
            "special_panel_commission_percent",
            DEFAULT_SETTINGS["special_panel_commission_percent"]
        ))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["special_panel_commission_percent"]


def set_special_panel_commission_percent(percent: int):
    data = _load()
    data["special_panel_commission_percent"] = int(percent)
    _save(data)

# ====================== Hybrid Payment (Wallet + Card) ======================

def is_hybrid_payment_enabled() -> bool:
    return bool(_load().get("hybrid_payment_enabled", False))


def set_hybrid_payment_enabled(value: bool):
    data = _load()
    data["hybrid_payment_enabled"] = bool(value)
    _save(data)

# ====================== Card Payment Info ======================

def get_card_number() -> str:
    return str(_load().get("card_number", DEFAULT_SETTINGS["card_number"])).strip()


def set_card_number(value: str):
    data = _load()
    data["card_number"] = value.strip()
    _save(data)


def get_card_holder() -> str:
    return str(_load().get("card_holder", DEFAULT_SETTINGS["card_holder"])).strip()


def set_card_holder(value: str):
    data = _load()
    data["card_holder"] = value.strip()
    _save(data)


def get_card_bank() -> str:
    return str(_load().get("card_bank", DEFAULT_SETTINGS["card_bank"])).strip()


def set_card_bank(value: str):
    data = _load()
    data["card_bank"] = value.strip()
    _save(data)

# ====================== Combined Sub URL ======================

_COMBINED_SUB_BASE_URL = None

def set_combined_sub_base_url(url: str):
    """تنظیم آدرس پایه برای لینک اشتراک یکپارچه"""
    global _COMBINED_SUB_BASE_URL
    _COMBINED_SUB_BASE_URL = url.rstrip('/')
    # ذخیره در settings
    data = _load()
    data["combined_sub_base_url"] = _COMBINED_SUB_BASE_URL
    _save(data)


def get_combined_sub_base_url() -> str:
    """دریافت آدرس پایه برای لینک اشتراک یکپارچه"""
    global _COMBINED_SUB_BASE_URL
    if _COMBINED_SUB_BASE_URL:
        return _COMBINED_SUB_BASE_URL
    
    # بارگذاری از settings
    data = _load()
    url = data.get("combined_sub_base_url")
    if url:
        _COMBINED_SUB_BASE_URL = url.rstrip('/')
        return _COMBINED_SUB_BASE_URL
    
    # مقدار پیش‌فرض (هاست ایران)
    default_url = "https://heysolo.ir"
    _COMBINED_SUB_BASE_URL = default_url
    return default_url

def get_emergency_proxy_links() -> list:
    """
    لیست پروکسی‌های اضطراری را برمی‌گرداند.
    هر آیتم: {'name': 'Proxy🇧🇬', 'link': 'tg://proxy?server=...'}
    """
    if not _os.path.exists(_EMERGENCY_PROXY_FILE):
        return []
    try:
        with open(_EMERGENCY_PROXY_FILE, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return []


def set_emergency_proxy_links(links: list):
    """لیست پروکسی‌های اضطراری را ذخیره می‌کند"""
    try:
        with open(_EMERGENCY_PROXY_FILE, "w", encoding="utf-8") as f:
            _json.dump(links, f, ensure_ascii=False, indent=2)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error saving emergency proxies: {e}")

# ====================== Emergency Plan Defaults ======================

def get_emergency_plan_volume_gb() -> int:
    try:
        return int(_load().get("emergency_plan_volume_gb", DEFAULT_SETTINGS["emergency_plan_volume_gb"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["emergency_plan_volume_gb"]


def set_emergency_plan_volume_gb(value: int):
    data = _load()
    data["emergency_plan_volume_gb"] = int(value)
    _save(data)


def get_emergency_plan_duration_days() -> int:
    try:
        return int(_load().get("emergency_plan_duration_days", DEFAULT_SETTINGS["emergency_plan_duration_days"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["emergency_plan_duration_days"]


def set_emergency_plan_duration_days(value: int):
    data = _load()
    data["emergency_plan_duration_days"] = int(value)
    _save(data)
