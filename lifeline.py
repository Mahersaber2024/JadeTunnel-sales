#!/usr/bin/env python3
import logging
from telegram import Bot
from telegram.error import TelegramError
from bot_settings import is_lifeline_enabled

logger = logging.getLogger(__name__)

db = None
LIFELINE_CHANNEL_ID = None


def set_db(database):
    global db
    db = database


def set_channel(channel_id: str):
    global LIFELINE_CHANNEL_ID
    LIFELINE_CHANNEL_ID = channel_id


def build_progress_bar(ratio: float, length: int = 12, filled_char="█", empty_char="░") -> str:
    filled = int(round(ratio * length))
    filled = max(0, min(length, filled))
    return filled_char * filled + empty_char * (length - filled)


def to_persian_digits(number) -> str:
    if number is None:
        return "—"
    fa = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(fa[int(d)] if d.isdigit() else d for d in str(number))

def build_caption(
    days_remaining: int,
    max_days: int,
    channel_count=None,
    emergency_count=None,
    active_subs_count=None,
) -> str:
    ratio = max(0.0, min(1.0, days_remaining / max(1, max_days)))
    percent = int(round(ratio * 100))
    bar = build_progress_bar(ratio)

    if days_remaining <= 0:
        return "🕯 <b>چراغ جاده تونل خاموش شد</b>\n\nجاده تونل فعالیت خودش رو به پایان رسوند.\nممنون که در این مسیر همراه ما بودید 🙏"

    stats = (
        f"👥 Channel members: {to_persian_digits(channel_count)}\n"
        f"🆘 Emergency plan members: {to_persian_digits(emergency_count)}\n"
        f"📦 Active subscriptions: {to_persian_digits(active_subs_count)}"
    )

    return (
        f"<b>جاده تونل تصمیم داره به فعالیت خودش پایان بده.</b>\n\n"
        
        f"نگهداری سرورها با تعداد عضو کم بسیار سخته و ادامه دادنش بدون حمایت واقعی تقریباً غیرممکن شده. "
        f"افزایش قیمت هم منطقی نیست چون باعث خروج بیشتر اعضا می‌شه.\n\n"
        
        f"❤️ <b>اگه دوست دارید جاده تونل ادامه بده، به حمایت تک‌تک‌تون نیاز داریم.</b>\n"
        f"با <b>اشتراک‌گذاری این پیام</b> چراغ جاده تونل رو روشن نگه دارید.\n\n"
        
        f"ممنون که همراه ما هستید🙏\n\n"
        f"──────────────────\n\n"
        
        f"🕯 <b>چراغ جاده تونل</b> ({to_persian_digits(days_remaining)} روز باقی‌مانده)\n"
        f"<code>{bar}</code>  <b>{to_persian_digits(percent)}٪</b>\n\n"
        
        f"<b>📊 Live Statistics</b>\n"
        f'<span class="tg-spoiler">{stats}</span>\n\n'
        
        f"🌱 عضویت جدید <code>+۱</code> روز\n"
        f"💔 خروج <code>−۱</code> روز\n"
        f"🛒 خرید <code>+۴</code> روز"
    )

# ============ بقیه توابع بدون تغییر ============

async def _get_channel_members_count(bot: Bot):
    if not LIFELINE_CHANNEL_ID:
        return None
    try:
        return await bot.get_chat_member_count(chat_id=LIFELINE_CHANNEL_ID)
    except TelegramError as e:
        logger.warning(f"Lifeline: خطا در دریافت تعداد اعضای کانال: {e}")
        return None


def _call_db_count(*method_names):
    if not db:
        return None
    for name in method_names:
        fn = getattr(db, name, None)
        if fn:
            try:
                return fn()
            except Exception as e:
                logger.warning(f"Lifeline: خطا در {name}: {e}")
    return None


def _get_emergency_members_count():
    return _call_db_count(
        "get_emergency_members_count",
        "get_emergency_approved_count",
        "count_emergency_access",
    )


def _get_active_subscriptions_count():
    return _call_db_count(
        "get_active_subscriptions_count",
        "count_active_subscriptions",
    )


async def post_or_update_lifeline(bot: Bot):
    if not is_lifeline_enabled():
        return
    if not db or not LIFELINE_CHANNEL_ID:
        logger.warning("Lifeline: db یا channel تنظیم نشده")
        return

    row = db.get_lifeline()
    if not row:
        return

    days_remaining = row['days_remaining']
    max_days = row['max_days']
    message_id = row.get('message_id')

    channel_count = await _get_channel_members_count(bot)
    emergency_count = _get_emergency_members_count()
    active_subs_count = _get_active_subscriptions_count()

    caption = build_caption(
        days_remaining, max_days,
        channel_count, emergency_count, active_subs_count,
    )

    if message_id:
        try:
            await bot.edit_message_text(
                chat_id=LIFELINE_CHANNEL_ID,
                message_id=message_id,
                text=caption,
                parse_mode='HTML'
            )
            return
        except TelegramError as e:
            logger.warning(f"Lifeline: ادیت پیام قبلی شکست خورد ({e})؛ پیام جدید ارسال می‌شود...")

    try:
        if message_id:
            try:
                await bot.delete_message(chat_id=LIFELINE_CHANNEL_ID, message_id=message_id)
            except Exception:
                pass

        sent = await bot.send_message(
            chat_id=LIFELINE_CHANNEL_ID,
            text=caption,
            parse_mode='HTML'
        )
        db.set_lifeline_message(LIFELINE_CHANNEL_ID, sent.message_id)
    except Exception as e:
        logger.error(f"Lifeline: خطا در ارسال پست جدید: {e}")


async def add_day(bot: Bot, amount: int = 1):
    if not is_lifeline_enabled():
        return
    row = db.get_lifeline()
    max_days = row['max_days'] if row else 30
    db.adjust_lifeline_days(amount, max_days=max_days)
    await post_or_update_lifeline(bot)


async def subtract_day(bot: Bot, amount: int = 1):
    if not is_lifeline_enabled():
        return
    db.adjust_lifeline_days(-amount)
    await post_or_update_lifeline(bot)


async def refresh_pulse(context):
    await post_or_update_lifeline(context.bot)
