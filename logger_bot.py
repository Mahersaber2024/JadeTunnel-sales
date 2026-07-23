#!/usr/bin/env python3
# logger_bot.py - send user/admin activity logs to a Telegram log group
import json
import logging
import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ============ Constants ============
LOG_GROUP_ID = None  # e.g. -1001234567890

# File where created topic IDs are persisted
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
    Note: starts at 2 because thread_id = 1 always belongs to the default
    "General" topic of any forum group, and Telegram never assigns it to a new topic.
    """
    USER_JOIN = 2  # New user joins
    USER_REFERRAL = 3  # Joined via referral link
    INVOICE = 4  # Invoice issued
    PURCHASE = 5  # User purchase details
    SUBSCRIPTION = 6  # New subscription
    PANEL_ERROR = 7  # Panel errors
    ADMIN_ACTION = 8  # Admin actions
    SYSTEM_ERROR = 9  # System errors
    USER_ACTIVITY = 10  # User activity
    BALANCE_CHANGE = 11  # Balance changes
    REFERRAL_BONUS = 12  # Referral bonus
    VOLUME_ADDED = 13  # Extra volume added
    CARD_PAYMENT = 14  # Card-to-card payment
    WALLET_PAYMENT = 15  # Wallet payment
    PANEL_STATUS = 16  # Panel status
    SUBSCRIPTION_EXPIRE = 17  # Subscription expiry
    GIFT_SENT = 18  # Gift sent between users
    EMERGENCY_PLAN = 19


# ============ Topic Names ============
TOPIC_NAMES = {
    Topics.USER_JOIN: "📢 New User Joins",
    Topics.USER_REFERRAL: "🎁 Joined via Referral Link",
    Topics.INVOICE: "🧾 Issued Invoices",
    Topics.PURCHASE: "🛒 User Purchase Details",
    Topics.SUBSCRIPTION: "🔑 New Subscriptions",
    Topics.PANEL_ERROR: "⚠️ Panel Errors",
    Topics.ADMIN_ACTION: "🔧 Admin Actions",
    Topics.SYSTEM_ERROR: "💥 System Errors",
    Topics.USER_ACTIVITY: "🔄 User Activity",
    Topics.BALANCE_CHANGE: "💰 Balance Changes",
    Topics.REFERRAL_BONUS: "🎁 Referral Bonuses",
    Topics.VOLUME_ADDED: "➕ Extra Volume Added",
    Topics.CARD_PAYMENT: "🏦 Card-to-Card Payments",
    Topics.WALLET_PAYMENT: "💰 Wallet Payments",
    Topics.PANEL_STATUS: "🖥 Panel Status",
    Topics.SUBSCRIPTION_EXPIRE: "⏰ Subscription Expiry",
    Topics.GIFT_SENT: "🎁 Gifts Sent by Users",
    Topics.EMERGENCY_PLAN: "🆘 Emergency Plan",
}


# ============ Persisted Topic State ============
def _load_topics_state() -> Dict[str, int]:
    """
    Read the mapping of logical topic_id (Topics.*) -> real Telegram message_thread_id
    from file. Keys are stored as strings since JSON has no int keys.
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


# In-memory mapping: logical topic_id -> real message_thread_id
_TOPIC_THREAD_MAP: Dict[int, int] = {}


def get_thread_id(topic_id: int) -> Optional[int]:
    """Get the real Telegram message_thread_id for a logical topic_id"""
    return _TOPIC_THREAD_MAP.get(topic_id)


# ============ Create Topics ============
async def create_all_topics(bot) -> bool:
    """
    Create all topics in the log group.
    Instead of asking Telegram (which has no such API), state is read from a local
    file and only topics that don't actually exist yet are created.
    """
    global _TOPIC_THREAD_MAP

    if not LOG_GROUP_ID:
        logger.error("LOG_GROUP_ID is not set")
        return False

    try:
        state = _load_topics_state()
        # Keys are strings; convert to int
        _TOPIC_THREAD_MAP = {int(k): v for k, v in state.items()}

        created_count = 0

        for topic_id, topic_name in TOPIC_NAMES.items():
            # Skip if already created and saved
            if topic_id in _TOPIC_THREAD_MAP:
                logger.info(
                    f"Topic {topic_id} already exists (thread_id={_TOPIC_THREAD_MAP[topic_id]}): {topic_name}"
                )
                continue

            # Create a new topic
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

                # Save immediately so this one isn't lost if a later error occurs
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

    # Convert logical topic_id to real Telegram message_thread_id
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
    """Format user information for display (from a Telegram user object)"""
    first_name = user.first_name or 'Unknown'
    last_name = user.last_name or ''
    username = f"@{user.username}" if user.username else 'None'

    return f"""
👤 **User Info:**
🆔 ID: `{user.id}`
📛 Name: {first_name} {last_name}
🔰 Username: {username}
    """.strip()


def format_plan_info(plan: Dict) -> str:
    """Format plan information"""
    name = plan.get('name', 'Unknown')
    price = plan.get('price', 0)
    days = plan.get('days', 0)
    volume = plan.get('daily_volume', '')

    result = f"""
📦 **Selected Plan:**
📛 Name: {name}
💰 Price: {price:,} Toman
⏰ Duration: {days} days
"""
    if volume:
        result += f"📊 Daily volume: {volume} GB\n"

    return result.strip()


def format_user_short(user_id: int, username: str = None) -> str:
    """
    (Deprecated) Format short user info - kept only for compatibility with old code.
    Use format_user_full for the complete user display.
    """
    if username:
        return f"@{username} (`{user_id}`)"
    return f"`{user_id}`"


def _full_name(first_name: str = None, last_name: str = None) -> str:
    """Combine first and last name; returns 'Unknown' if neither is present"""
    first_name = (first_name or '').strip()
    last_name = (last_name or '').strip()
    full = f"{first_name} {last_name}".strip()
    return full if full else 'Unknown'


def format_user_full(user_id: int, username: str = None,
                      first_name: str = None, last_name: str = None) -> str:
    """
    Multi-line format of full user info: name, last name, username, and numeric ID.
    Used everywhere instead of format_user_short.
    """
    name = _full_name(first_name, last_name)
    username_text = f"@{username}" if username else 'None'

    return (
        f"📛 Name: {name}\n"
        f"🔰 Username: {username_text}\n"
        f"🆔 ID: `{user_id}`"
    )


def format_user_multiline(user_id: int, username: str = None,
                           first_name: str = None, last_name: str = None,
                           show_name: bool = True) -> str:
    """
    Multi-line user info format (name optional, username and ID on separate lines).
    Useful when we want username and ID shown on their own lines.
    """
    name = _full_name(first_name, last_name)
    username_clean = (username or '').lstrip('@').strip()
    username_text = username_clean if username_clean else 'None'

    lines = []
    if show_name:
        lines.append(f"📛 Name: {name}")
    lines.append(f"🔰 Username: {username_text}")
    lines.append(f"🆔 ID: `{user_id}`")
    return "\n".join(lines)


def _resolve_user_details(user_id: int, username: str = None,
                           first_name: str = None, last_name: str = None) -> Dict[str, Any]:
    """
    If name/username weren't passed to the function, try to read them from the
    database, so no log ever shows just a bare numeric ID.
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

        # ============ Inviter stats ============
        referrals_count = 0
        total_commission = 0
        try:
            from handlers import db
            referrals_count = db.get_referral_count(referred_by)
            total_commission = db.get_total_commission(referred_by)
        except Exception:
            pass

        referral_block = (
            f"🎁 Referred by:\n{inviter_block}\n"
            f"📊 Stats:\n"
            f"👥 Total successful referrals: {referrals_count}\n"
            f"💰 Total commission earned: {total_commission:,} Toman\n"
        )
    else:
        referral_block = "✅ No referral\n"

    message = f"""
📢 **New User Joined**
🕐 Time: {timestamp}
{user_block}
💰 Initial balance: {balance:,} Toman
{referral_block}📊 **Status:** New user joined the bot
    """.strip()

    # Pick the appropriate topic
    topic = Topics.USER_REFERRAL if referred_by else Topics.USER_JOIN
    await send_log_message(topic, message, bot=bot)

async def log_invoice_issued(bot, user_id: int, plan_name: str, price: int, card_digits: str = None,
                              username: str = None, first_name: str = None, last_name: str = None):
    """Log when an invoice is issued"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
🧾 **Invoice Issued**
🕐 Time: {timestamp}
{user_info}
📦 Plan: {plan_name}
💰 Amount: {price:,} Toman
{'🔢 Last 4 card digits: `' + card_digits + '`' if card_digits else ''}
📊 **Status:** ⏳ Awaiting payment
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
    status_text = "✅ Success" if status == 'success' else "❌ Failed"
    status_emoji = "✅" if status == 'success' else "❌"

    message = f"""
🛒 **Purchase Details** {status_emoji}
🕐 Time: {timestamp}
{user_info}
{'📧 Subscription email: `' + email + '`' if email else ''}
📦 **Plan:**
📛 Name: {plan.get('name', 'Unknown')}
💰 Price: {amount:,} Toman
⏰ Duration: {plan.get('days', 0)} days
{'📊 Volume: ' + str(plan.get('daily_volume', '')) + ' GB/day' if plan.get('daily_volume') else ''}
💳 **Payment method:** {payment_method}
💳 New balance: {balance_after:,} Toman
📊 **Status:** {status_text}
    """.strip()

    await send_log_message(Topics.PURCHASE, message, bot=bot)


async def log_payment_card(bot, user_id: int, plan_name: str, amount: int,
                            card_digits: str, status: str = 'pending', username: str = None,
                            first_name: str = None, last_name: str = None):
    """Log card payment"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    status_text = {
        'pending': '⏳ Awaiting approval',
        'success': '✅ Approved',
        'failed': '❌ Failed'
    }.get(status, status)

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
🏦 **Card-to-Card Payment**
🕐 Time: {timestamp}
{user_info}
📦 Plan: {plan_name}
💰 Amount: {amount:,} Toman
🔢 Last 4 card digits: `{card_digits}`
📊 **Status:** {status_text}
    """.strip()

    await send_log_message(Topics.CARD_PAYMENT, message, bot=bot)


async def log_wallet_payment(bot, user_id: int, plan_name: str, amount: int,
                              balance_before: int, balance_after: int, status: str = 'success',
                              username: str = None, first_name: str = None, last_name: str = None):
    """Log wallet payment"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    status_text = "✅ Success" if status == 'success' else "❌ Failed"
    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
💰 **Wallet Payment**
🕐 Time: {timestamp}
{user_info}
📦 Plan: {plan_name}
💰 Amount paid: {amount:,} Toman
💳 Balance before: {balance_before:,} Toman
💳 Balance after: {balance_after:,} Toman
📊 **Status:** {status_text}
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
🔑 **New Subscription Created**
🕐 Time: {timestamp}
{user_info}
🆔 Subscription: `{subscription_id}`
📦 Plan: {plan_name}
📧 Email: `{email}`
🖥 Panel: {panel_id}
📊 **Status:** ✅ Active
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
        user_info = "👤 User: System"

    message = f"""
⚠️ **Panel Error**
🕐 Time: {timestamp}
{user_info}
{'📦 Plan: ' + plan_name if plan_name else ''}
🔧 Action: {action}
❌ **Error:**
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

    lines = [
        "🔧 **Admin Action**",
        f"🕐 Time: {timestamp}",
        "👤 Admin ->",
        admin_info,
    ]

    if target_user_id:
        target_details = _resolve_user_details(target_user_id, target_username, target_first_name, target_last_name)
        target_info = format_user_full(**target_details)
        lines.append("👤 Target user ->")
        lines.append(target_info)

    if amount:
        lines.append(f"💰 Amount: {amount:,} Toman")

    lines.append("📝 Details:")
    lines.append(details or 'No details')
    lines.append(f"📊 **Action:** {action}")

    message = "\n".join(lines)

    await send_log_message(Topics.ADMIN_ACTION, message, bot=bot)


async def log_system_error(bot, error: str, context: str = None):
    """Log system errors"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    message = f"""
💥 **System Error**
🕐 Time: {timestamp}
{'📝 Context: ' + context if context else ''}
❌ **Error:**
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
🔄 **User Activity**
🕐 Time: {timestamp}
{user_info}
📝 Activity: {action}
{'📋 Details: ' + details if details else ''}
    """.strip()

    await send_log_message(Topics.USER_ACTIVITY, message, bot=bot)


async def log_balance_change(bot, user_id: int, change: int, new_balance: int, reason: str,
                              username: str = None, first_name: str = None, last_name: str = None):
    """Log balance changes"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    change_type = "Increase" if change > 0 else "Decrease"
    emoji = "📈" if change > 0 else "📉"
    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
{emoji} **Balance Change**
🕐 Time: {timestamp}
{user_info}
📊 Type: {change_type}
💰 Amount: {abs(change):,} Toman
💳 New balance: {new_balance:,} Toman
📝 Reason: {reason}
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
🎁 **Referral Bonus**
🕐 Time: {timestamp}
👤 Inviter -> {inviter_info}
👤 New user -> {new_user_info}
💰 Bonus amount: {amount:,} Toman
📊 **Status:** ✅ Paid
    """.strip()

    await send_log_message(Topics.REFERRAL_BONUS, message, bot=bot)


async def log_volume_added(bot, user_id: int, subscription_id: int, volume: int, price: int, method: str,
                            username: str = None, first_name: str = None, last_name: str = None):
    """Log when extra volume is added"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
➕ **Extra Volume Added**
🕐 Time: {timestamp}
{user_info}
🆔 Subscription: `{subscription_id}`
📊 Volume added: {volume} GB
💰 Price: {price:,} Toman
💳 Payment method: {method}
📊 **Status:** ✅ Success
    """.strip()

    await send_log_message(Topics.VOLUME_ADDED, message, bot=bot)


async def log_subscription_expire(bot, user_id: int, subscription_id: int, plan_name: str,
                                   username: str = None, first_name: str = None, last_name: str = None):
    """Log when a subscription expires"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    message = f"""
⏰ **Subscription Expired**
🕐 Time: {timestamp}
{user_info}
🆔 Subscription: `{subscription_id}`
📦 Plan: {plan_name}
📊 **Status:** ⏰ Expired
    """.strip()

    await send_log_message(Topics.SUBSCRIPTION_EXPIRE, message, bot=bot)


async def log_panel_status(bot, panel_id: str, status: str, details: str = None):
    """Log panel status changes"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    status_emoji = "✅" if status == "online" else "❌" if status == "offline" else "⚠️"
    status_text = {
        "online": "Online",
        "offline": "Offline",
        "error": "Error"
    }.get(status, status)

    message = f"""
🖥 **Panel Status** {status_emoji}
🕐 Time: {timestamp}
🆔 Panel: `{panel_id}`
📊 Status: {status_text}
{'📝 Details: ' + details if details else ''}
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
🎁 **Gift Sent**
🕐 Time: {timestamp}
👤 Sender -> {sender_info}
👤 Recipient -> {recipient_info}
💰 Amount: {amount:,} Toman
{'💌 Message: ' + gift_message if gift_message else ''}
📊 **Status:** ✅ Success
    """.strip()

    await send_log_message(Topics.GIFT_SENT, message, bot=bot)

async def log_emergency_config_result(bot, user_id: int, panel_id: str, panel_name: str, status: str,
                                       detail: str = None,
                                       username: str = None, first_name: str = None, last_name: str = None):
    """Log emergency plan config creation result (success/failure)"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    details = _resolve_user_details(user_id, username, first_name, last_name)
    user_info = format_user_full(**details)

    status_text = "✅ Success" if status == 'success' else "❌ Failed"
    detail_line = ""
    if detail and status != 'success':
        detail_line = f"\n❌ Error:\n<code>{detail[:500]}</code>"

    message = f"""
🆘 **Emergency Plan Config Creation**
🕐 Time: {timestamp}
{user_info}
🖥 Panel: {panel_name} (`{panel_id}`)
📊 **Status:** {status_text}{detail_line}
    """.strip()

    await send_log_message(Topics.EMERGENCY_PLAN, message, parse_mode='HTML', bot=bot)
