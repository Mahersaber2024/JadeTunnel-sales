#!/usr/bin/env python3
# logger_bot.py - ارسال لاگ‌های کاربران به گروه تلگرام
import json
import logging
import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ============ Constants ============
LOG_GROUP_ID = None  # مثلاً -1001234567890

# فایلی که شناسه‌ی تاپیک‌های ساخته‌شده در آن ذخیره می‌شود
TOPICS_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "topics_state.json")


def init_logger(group_id: int):
    """Initialize logger with group ID"""
    global LOG_GROUP_ID
    LOG_GROUP_ID = group_id
    logger.info(f"Logger initialized with group ID: {group_id}")


# ============ Topic IDs ============
class Topics:
    """
    Topic IDs for different log categories.
    توجه: از 2 شروع می‌شود چون thread_id = 1 همیشه متعلق به تاپیک پیش‌فرض
    "General" هر گروه فروم است و تلگرام هرگز آن را به تاپیک جدید اختصاص نمی‌دهد.
    """
    USER_JOIN = 2  # عضویت کاربر جدید
    USER_REFERRAL = 3  # عضویت با لینک دعوت
    INVOICE = 4  # فاکتور صادر شده
    PURCHASE = 5  # مشخصات خرید کاربر
    SUBSCRIPTION = 6  # اشتراک جدید
    PANEL_ERROR = 7  # خطاهای پنل
    ADMIN_ACTION = 8  # اقدامات ادمین
    SYSTEM_ERROR = 9  # خطاهای سیستمی
    USER_ACTIVITY = 10  # فعالیت‌های کاربر
    BALANCE_CHANGE = 11  # تغییرات موجودی
    REFERRAL_BONUS = 12  # پاداش دعوت
    VOLUME_ADDED = 13  # افزایش حجم اضافی
    CARD_PAYMENT = 14  # پرداخت کارت به کارت
    WALLET_PAYMENT = 15  # پرداخت با کیف پول
    PANEL_STATUS = 16  # وضعیت پنل‌ها
    SUBSCRIPTION_EXPIRE = 17  # انقضای اشتراک
    GIFT_SENT = 18  # ارسال هدیه بین کاربران
    EMERGENCY_PLAN = 19


# ============ Topic Names ============
TOPIC_NAMES = {
    Topics.USER_JOIN: "📢 عضویت کاربران جدید",
    Topics.USER_REFERRAL: "🎁 عضویت با لینک دعوت",
    Topics.INVOICE: "🧾 فاکتورهای صادر شده",
    Topics.PURCHASE: "🛒 مشخصات خرید کاربران",
    Topics.SUBSCRIPTION: "🔑 اشتراک‌های جدید",
    Topics.PANEL_ERROR: "⚠️ خطاهای پنل",
    Topics.ADMIN_ACTION: "🔧 اقدامات ادمین",
    Topics.SYSTEM_ERROR: "💥 خطاهای سیستمی",
    Topics.USER_ACTIVITY: "🔄 فعالیت‌های کاربران",
    Topics.BALANCE_CHANGE: "💰 تغییرات موجودی",
    Topics.REFERRAL_BONUS: "🎁 پاداش‌های دعوت",
    Topics.VOLUME_ADDED: "➕ افزایش حجم اضافی",
    Topics.CARD_PAYMENT: "🏦 پرداخت کارت به کارت",
    Topics.WALLET_PAYMENT: "💰 پرداخت با کیف پول",
    Topics.PANEL_STATUS: "🖥 وضعیت پنل‌ها",
    Topics.SUBSCRIPTION_EXPIRE: "⏰ انقضای اشتراک",
    Topics.GIFT_SENT: "🎁 هدیه‌های ارسالی کاربران",
    Topics.EMERGENCY_PLAN: "🆘 طرح اضطراری",   # <-- جدید
    
}


# ============ Persisted Topic State ============
def _load_topics_state() -> Dict[str, int]:
    """
    خواندن نگاشت topic_id (منطقی، همان Topics.*) -> message_thread_id واقعی تلگرام
    از فایل. کلیدها به‌صورت رشته ذخیره می‌شوند چون JSON کلید int ندارد.
    """
    if not os.path.exists(TOPICS_STATE_FILE):
        return {}
    try:
        with open(TOPICS_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading topics state file: {e}")
        return {}


def _save_topics_state(state: Dict[str, int]) -> None:
    try:
        with open(TOPICS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving topics state file: {e}")


# نگاشت درون‌حافظه‌ای: topic_id منطقی -> message_thread_id واقعی
_TOPIC_THREAD_MAP: Dict[int, int] = {}


def get_thread_id(topic_id: int) -> Optional[int]:
    """گرفتن message_thread_id واقعی تلگرام برای یک topic_id منطقی"""
    return _TOPIC_THREAD_MAP.get(topic_id)


# ============ Create Topics ============
async def create_all_topics(bot) -> bool:
    """
    ساخت تمام تاپیک‌ها در گروه لاگ.
    به‌جای پرسیدن از تلگرام (که چنین APIای ندارد)، وضعیت از فایل محلی خوانده می‌شود
    و فقط تاپیک‌هایی که واقعاً ساخته نشده‌اند، ساخته می‌شوند.
    """
    global _TOPIC_THREAD_MAP

    if not LOG_GROUP_ID:
        logger.error("LOG_GROUP_ID is not set")
        return False

    try:
        state = _load_topics_state()
        # کلیدها رشته هستند؛ به int تبدیل می‌کنیم
        _TOPIC_THREAD_MAP = {int(k): v for k, v in state.items()}

        created_count = 0

        for topic_id, topic_name in TOPIC_NAMES.items():
            # اگر قبلاً ساخته و ذخیره شده، رد شو
            if topic_id in _TOPIC_THREAD_MAP:
                logger.info(
                    f"Topic {topic_id} already exists (thread_id={_TOPIC_THREAD_MAP[topic_id]}): {topic_name}"
                )
                continue

            # ساخت تاپیک جدید
            try:
                result = await bot.create_forum_topic(
                    chat_id=LOG_GROUP_ID,
                    name=topic_name,
                    icon_color=0x6FB9F0
                )
                thread_id = result.message_thread_id
                _TOPIC_THREAD_MAP[topic_id] = thread_id
                created_count += 1
                logger.info(f"✅ Created topic {topic_id}: {topic_name} (thread_id={thread_id})")

                # بلافاصله ذخیره کن تا اگر بعداً خطا رخ داد، این یکی از دست نرود
                _save_topics_state({str(k): v for k, v in _TOPIC_THREAD_MAP.items()})

                await asyncio.sleep(0.5)  # Rate limit
            except Exception as e:
                logger.error(f"Failed to create topic {topic_id}: {e}")

        logger.info(f"✅ Created {created_count} new topics")
        return True

    except Exception as e:
        logger.error(f"Error creating topics: {e}")
        return False


# ============ Send Message Function ============
async def send_log_message(topic_id: int, message: str, parse_mode: str = 'HTML',
                            reply_to_message_id: int = None,
                            buttons: list = None, bot=None):
    """Send a message to the log group with topic"""
    if not LOG_GROUP_ID:
        logger.warning("Logger not initialized. LOG_GROUP_ID is missing.")
        return None

    if bot is None:
        logger.warning("Bot instance not provided")
        return None

    # topic_id منطقی را به message_thread_id واقعی تلگرام تبدیل کن
    thread_id = get_thread_id(topic_id)
    if thread_id is None:
        logger.warning(f"No thread_id found for logical topic {topic_id}; sending without topic")

    try:
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton

        reply_markup = None
        if buttons:
            keyboard = []
            for row in buttons:
                keyboard.append([InlineKeyboardButton(text, url=url) for text, url in row])
            reply_markup = InlineKeyboardMarkup(keyboard)

        result = await bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=message,
            parse_mode=parse_mode,
            message_thread_id=thread_id,
            reply_markup=reply_markup
        )
        logger.info(f"Log message sent to topic {topic_id}")
        return result
    except Exception as e:
        logger.error(f"Error sending log message: {e}")
        return None


# ============ Format Helpers ============
def format_user_info(user) -> str:
    """Format user information for display (از آبجکت user تلگرام)"""
    first_name = user.first_name or 'نامشخص'
    last_name = user.last_name or ''
    username = f"@{user.username}" if user.username else 'ندارد'

    return f"""
👤 **اطلاعات کاربر:**
🆔 شناسه: `{user.id}`
📛 نام: {first_name} {last_name}
🔰 یوزرنیم: {username}
    """.strip()


def format_plan_info(plan: Dict) -> str:
    """Format plan information"""
    name = plan.get('name', 'نامشخص')
    price = plan.get('price', 0)
    days = plan.get('days', 0)
    volume = plan.get('daily_volume', '')

    result = f"""
📦 **پلن انتخابی:**
📛 نام: {name}
💰 قیمت: {price:,} تومان
⏰ مدت: {days} روز
"""
    if volume:
        result += f"📊 حجم روزانه: {volume} گیگ\n"

    return result.strip()


def format_user_short(user_id: int, username: str = None) -> str:
    """
    (Deprecated) Format short user info - فقط برای سازگاری با کدهای قدیمی نگه داشته شده.
    برای نمایش کامل کاربر از format_user_full استفاده کنید.
    """
    if username:
        return f"@{username} (`{user_id}`)"
    return f"`{user_id}`"


def _full_name(first_name: str = None, last_name: str = None) -> str:
    """ترکیب نام و نام خانوادگی؛ اگر هیچ‌کدام نبود 'نامشخص' برمی‌گرداند"""
    first_name = (first_name or '').strip()
    last_name = (last_name or '').strip()
    full = f"{first_name} {last_name}".strip()
    return full if full else 'نامشخص'


def format_user_full(user_id: int, username: str = None,
                      first_name: str = None, last_name: str = None) -> str:
    """
    فرمت کامل اطلاعات کاربر شامل نام، نام خانوادگی، یوزرنیم و آیدی عددی.
    در تمام لاگ‌ها به‌جای format_user_short از این تابع استفاده می‌شود.
    """
    name = _full_name(first_name, last_name)
    username_text = f"@{username}" if username else 'ندارد'

    return (
        f"📛 نام: {name} | "
        f"🔰 یوزرنیم: {username_text} | "
        f"🆔 آیدی: `{user_id}`"
    )

def format_user_multiline(user_id: int, username: str = None,
                           first_name: str = None, last_name: str = None,
                           show_name: bool = True) -> str:
    """
    فرمت چندخطی اطلاعات کاربر (نام اختیاری، یوزرنیم و آیدی جدا از هم).
    مناسب برای مواردی که می‌خواهیم یوزرنیم و آیدی در خطوط جداگانه نمایش داده شوند.
    """
    name = _full_name(first_name, last_name)
    username_clean = (username or '').lstrip('@').strip()
    username_text = username_clean if username_clean else 'ندارد'

    lines = []
    if show_name:
        lines.append(f"📛 نام: {name}")
    lines.append(f"🔰 یوزرنیم: {username_text}")
    lines.append(f"🆔 آیدی: `{user_id}`")
    return "\n".join(lines)

def _resolve_user_details(user_id: int, username: str = None,
                           first_name: str = None, last_name: str = None) -> Dict[str, Any]:
    """
    اگر نام/یوزرنیم به تابع پاس داده نشده باشد، تلاش می‌کند اطلاعات را از دیتابیس بخواند
    تا در هیچ لاگی فقط آیدی عددی به تنهایی نمایش داده نشود.
    """
    if username or first_name or last_name:
        return {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
        }

    try:
        from handlers import db
        user = db.get_user(user_id)
        if user:
            return {
                "user_id": user_id,
                "username": user.get('username'),
                "first_name": user.get('first_name'),
                "last_name": user.get('last_name'),
            }
    except Exception:
        pass

    return {
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
    }

# ============ Log Functions ============
async def log_user_join(bot, user_id: int, username: str, first_name: str, referred_by: Optional[int] = None,
                         last_name: str = None):
    """Log when a user joins the bot"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    balance = 0

    try:
        from handlers import db
        user = db.get_user(user_id)
        if user:
            balance = user.get('balance', 0)
    except Exception:
        pass

    user_block = format_user_multiline(user_id, username, first_name, last_name)

    referral_block = ""
    if referred_by:
        inviter_details = _resolve_user_details(referred_by)
        inviter_block = format_user_multiline(
            inviter_details['user_id'],
            inviter_details['username'],
            inviter_details['first_name'],
            inviter_details['last_name'],
            show_name=False
        )

        # ============ آمار دعوت‌کننده ============
        referrals_count = 0
        total_commission = 0
        try:
            from handlers import db
            referrals_count = db.get_referral_count(referred_by)
            total_commission = db.get_total_commission(referred_by)
        except Exception:
            pass

        referral_block = (
            f"🎁 دعوت شده توسط:\n{inviter_block}\n"
            f"📊 آمار:\n"
            f"👥 تعداد کل دعوت‌های موفق: {referrals_count}\n"
            f"💰 مجموع کمیسیون دریافتی: {total_commission:,} تومان\n"
        )
    else:
        referral_block = "✅ بدون دعوت\n"

    message = f"""
📢 **عضویت جدید کاربر**
🕐 زمان: {timestamp}
{user_block}
💰 موجودی اولیه: {balance:,} تومان
{referral_block}📊 **وضعیت:** کاربر جدید به ربات پیوست
    """.strip()

    # انتخاب تاپیک مناسب
    topic = Topics.USER_REFERRAL if referred_by else Topics.USER_JOIN
    await send_log_message(topic, message, bot=bot)

async def log_invoice_issued(bot, user_id: int, plan_name: str, price: int, card_digits: str = None,
                              username: str = None, first_name: str = None, last_name: str = None):
    """Log when an invoice is issued"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
🧾 **فاکتور صادر شد**
🕐 زمان: {timestamp}
{user_info}
📦 پلن: {plan_name}
💰 مبلغ: {price:,} تومان
{'🔢 چهار رقم آخر کارت: `' + card_digits + '`' if card_digits else ''}
📊 **وضعیت:** ⏳ منتظر پرداخت
    """.strip()

    await send_log_message(Topics.INVOICE, message, bot=bot)
    
async def log_purchase_details(bot, user_id: int, plan: Dict, payment_method: str,
                                amount: int, balance_after: int, status: str = 'success',
                                username: str = None, email: str = None,
                                first_name: str = None, last_name: str = None):
    """Log purchase details"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)
    status_text = "✅ موفق" if status == 'success' else "❌ ناموفق"
    status_emoji = "✅" if status == 'success' else "❌"

    message = f"""
🛒 **جزئیات خرید** {status_emoji}
🕐 زمان: {timestamp}
{user_info}
{'📧 ایمیل اشتراک: `' + email + '`' if email else ''}
📦 **پلن:**
📛 نام: {plan.get('name', 'نامشخص')}
💰 قیمت: {amount:,} تومان
⏰ مدت: {plan.get('days', 0)} روز
{'📊 حجم: ' + str(plan.get('daily_volume', '')) + ' گیگ روزانه' if plan.get('daily_volume') else ''}
💳 **روش پرداخت:** {payment_method}
💳 موجودی جدید: {balance_after:,} تومان
📊 **وضعیت:** {status_text}
    """.strip()

    await send_log_message(Topics.PURCHASE, message, bot=bot)


async def log_payment_card(bot, user_id: int, plan_name: str, amount: int,
                            card_digits: str, status: str = 'pending', username: str = None,
                            first_name: str = None, last_name: str = None):
    """Log card payment"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    status_text = {
        'pending': '⏳ در انتظار تایید',
        'success': '✅ تایید شد',
        'failed': '❌ ناموفق'
    }.get(status, status)

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
🏦 **پرداخت کارت به کارت**
🕐 زمان: {timestamp}
{user_info}
📦 پلن: {plan_name}
💰 مبلغ: {amount:,} تومان
🔢 چهار رقم آخر کارت: `{card_digits}`
📊 **وضعیت:** {status_text}
    """.strip()

    await send_log_message(Topics.CARD_PAYMENT, message, bot=bot)


async def log_wallet_payment(bot, user_id: int, plan_name: str, amount: int,
                              balance_before: int, balance_after: int, status: str = 'success',
                              username: str = None, first_name: str = None, last_name: str = None):
    """Log wallet payment"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    status_text = "✅ موفق" if status == 'success' else "❌ ناموفق"
    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
💰 **پرداخت با کیف پول**
🕐 زمان: {timestamp}
{user_info}
📦 پلن: {plan_name}
💰 مبلغ پرداخت: {amount:,} تومان
💳 موجودی قبل: {balance_before:,} تومان
💳 موجودی بعد: {balance_after:,} تومان
📊 **وضعیت:** {status_text}
    """.strip()

    await send_log_message(Topics.WALLET_PAYMENT, message, bot=bot)


async def log_subscription_created(bot, user_id: int, subscription_id: int,
                                    plan_name: str, email: str, panel_id: str,
                                    username: str = None, first_name: str = None, last_name: str = None):
    """Log when a subscription is created"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
🔑 **اشتراک جدید ایجاد شد**
🕐 زمان: {timestamp}
{user_info}
🆔 اشتراک: `{subscription_id}`
📦 پلن: {plan_name}
📧 ایمیل: `{email}`
🖥 پنل: {panel_id}
📊 **وضعیت:** ✅ فعال
    """.strip()

    await send_log_message(Topics.SUBSCRIPTION, message, bot=bot)


async def log_panel_error(bot, user_id: int, action: str, error: str, plan_name: str = None,
                           username: str = None, first_name: str = None, last_name: str = None):
    """Log panel errors"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if user_id:
        details = _resolve_user_details(user_id, username, first_name, last_name)
        user_info = format_user_full(**details)
    else:
        user_info = "👤 کاربر: سیستم"

    message = f"""
⚠️ **خطای پنل**
🕐 زمان: {timestamp}
{user_info}
{'📦 پلن: ' + plan_name if plan_name else ''}
🔧 عملیات: {action}
❌ **خطا:**
<code>{error[:500]}</code>
    """.strip()

    await send_log_message(Topics.PANEL_ERROR, message, parse_mode='HTML', bot=bot)


async def log_admin_action(bot, admin_id: int, action: str, target_user_id: int = None,
                            details: str = None, amount: int = None, username: str = None,
                            first_name: str = None, last_name: str = None,
                            target_username: str = None, target_first_name: str = None,
                            target_last_name: str = None):
    """Log admin actions"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    admin_details = _resolve_user_details(admin_id, username, first_name, last_name)
    admin_info = format_user_full(**admin_details)

    if target_user_id:
        target_details = _resolve_user_details(target_user_id, target_username, target_first_name, target_last_name)
        target_info = format_user_full(**target_details)
    else:
        target_info = "👤 کاربر هدف: نامشخص"

    message = f"""
🔧 **اقدام ادمین**
🕐 زمان: {timestamp}
👤 ادمین -> {admin_info}
{'👤 کاربر هدف -> ' + target_info if target_user_id else ''}
{'💰 مبلغ: ' + f'{amount:,} تومان' if amount else ''}
📝 توضیحات: {details or 'بدون توضیحات'}
📊 **اقدام:** {action}
    """.strip()

    await send_log_message(Topics.ADMIN_ACTION, message, bot=bot)


async def log_system_error(bot, error: str, context: str = None):
    """Log system errors"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    message = f"""
💥 **خطای سیستمی**
🕐 زمان: {timestamp}
{'📝 متن: ' + context if context else ''}
❌ **خطا:**
<code>{error[:500]}</code>
    """.strip()

    await send_log_message(Topics.SYSTEM_ERROR, message, parse_mode='HTML', bot=bot)


async def log_user_activity(bot, user_id: int, action: str, details: str = None,
                             username: str = None, first_name: str = None, last_name: str = None):
    """Log user activities"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**user_details)

    message = f"""
🔄 **فعالیت کاربر**
🕐 زمان: {timestamp}
{user_info}
📝 فعالیت: {action}
{'📋 جزئیات: ' + details if details else ''}
    """.strip()

    await send_log_message(Topics.USER_ACTIVITY, message, bot=bot)


async def log_balance_change(bot, user_id: int, change: int, new_balance: int, reason: str,
                              username: str = None, first_name: str = None, last_name: str = None):
    """Log balance changes"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    change_type = "افزایش" if change > 0 else "کاهش"
    emoji = "📈" if change > 0 else "📉"
    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
{emoji} **تغییر موجودی**
🕐 زمان: {timestamp}
{user_info}
📊 نوع: {change_type}
💰 مبلغ: {abs(change):,} تومان
💳 موجودی جدید: {new_balance:,} تومان
📝 دلیل: {reason}
    """.strip()

    await send_log_message(Topics.BALANCE_CHANGE, message, bot=bot)


async def log_referral_bonus(bot, user_id: int, amount: int, new_user_id: int,
                              username: str = None, first_name: str = None, last_name: str = None,
                              new_username: str = None, new_first_name: str = None, new_last_name: str = None):
    """Log referral bonus"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    inviter_details = _resolve_user_details(user_id, username, first_name, last_name)
    inviter_info = format_user_full(**inviter_details)

    new_user_details = _resolve_user_details(new_user_id, new_username, new_first_name, new_last_name)
    new_user_info = format_user_full(**new_user_details)

    message = f"""
🎁 **پاداش دعوت**
🕐 زمان: {timestamp}
👤 کاربر دعوت‌کننده -> {inviter_info}
👤 کاربر جدید -> {new_user_info}
💰 مبلغ پاداش: {amount:,} تومان
📊 **وضعیت:** ✅ پرداخت شد
    """.strip()

    await send_log_message(Topics.REFERRAL_BONUS, message, bot=bot)


async def log_volume_added(bot, user_id: int, subscription_id: int, volume: int, price: int, method: str,
                            username: str = None, first_name: str = None, last_name: str = None):
    """Log when extra volume is added"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
➕ **افزایش حجم اضافی**
🕐 زمان: {timestamp}
{user_info}
🆔 اشتراک: `{subscription_id}`
📊 حجم اضافه شده: {volume} گیگ
💰 قیمت: {price:,} تومان
💳 روش پرداخت: {method}
📊 **وضعیت:** ✅ موفق
    """.strip()

    await send_log_message(Topics.VOLUME_ADDED, message, bot=bot)


async def log_subscription_expire(bot, user_id: int, subscription_id: int, plan_name: str,
                                   username: str = None, first_name: str = None, last_name: str = None):
    """Log when a subscription expires"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
⏰ **انقضای اشتراک**
🕐 زمان: {timestamp}
{user_info}
🆔 اشتراک: `{subscription_id}`
📦 پلن: {plan_name}
📊 **وضعیت:** ⏰ منقضی شد
    """.strip()

    await send_log_message(Topics.SUBSCRIPTION_EXPIRE, message, bot=bot)


async def log_panel_status(bot, panel_id: str, status: str, details: str = None):
    """Log panel status changes"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    status_emoji = "✅" if status == "online" else "❌" if status == "offline" else "⚠️"
    status_text = {
        "online": "آنلاین",
        "offline": "آفلاین",
        "error": "خطا"
    }.get(status, status)

    message = f"""
🖥 **وضعیت پنل** {status_emoji}
🕐 زمان: {timestamp}
🆔 پنل: `{panel_id}`
📊 وضعیت: {status_text}
{'📝 جزئیات: ' + details if details else ''}
    """.strip()

    await send_log_message(Topics.PANEL_STATUS, message, bot=bot)

async def log_gift_sent(bot, sender_id: int, recipient_id: int, amount: int, gift_message: str = None,
                         username: str = None, first_name: str = None, last_name: str = None):
    """Log when a user sends a gift to another user"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sender_details = _resolve_user_details(sender_id, username, first_name, last_name)
    sender_info = format_user_full(**sender_details)

    recipient_details = _resolve_user_details(recipient_id)
    recipient_info = format_user_full(**recipient_details)

    message = f"""
🎁 **هدیه ارسال شد**
🕐 زمان: {timestamp}
👤 فرستنده -> {sender_info}
👤 گیرنده -> {recipient_info}
💰 مبلغ: {amount:,} تومان
{'💌 پیام: ' + gift_message if gift_message else ''}
📊 **وضعیت:** ✅ موفق
    """.strip()

    await send_log_message(Topics.GIFT_SENT, message, bot=bot)

async def log_emergency_config_result(bot, user_id: int, panel_id: str, panel_name: str, status: str,
                                       detail: str = None,
                                       username: str = None, first_name: str = None, last_name: str = None):
    """Log emergency plan config creation result (success/failure)"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    status_text = "✅ موفق" if status == 'success' else "❌ ناموفق"
    detail_line = ""
    if detail and status != 'success':
        detail_line = f"\n❌ خطا:\n<code>{detail[:500]}</code>"

    message = f"""
🆘 **ساخت کانفیگ طرح اضطراری**
🕐 زمان: {timestamp}
{user_info}
🖥 پنل: {panel_name} (`{panel_id}`)
📊 **وضعیت:** {status_text}{detail_line}
    """.strip()

    await send_log_message(Topics.EMERGENCY_PLAN, message, parse_mode='HTML', bot=bot)
