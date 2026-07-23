# ====================== Admin Panel ======================
import logging
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
import html as html_lib
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from panel_manager import get_panel_manager
from client_manager import PanelClientFactory
import admin_dynamic_plans as adp
import asyncio
logger = logging.getLogger(__name__)

# ====================== Constants ======================
ADMIN_USER_ID_INPUT, ADMIN_AMOUNT_INPUT = range(2)
ADMIN_DELSUB_USER_ID, ADMIN_DELSUB_SELECT = range(2, 4)
ADMIN_PANEL_ADD = 4
ADMIN_PANEL_EDIT = 5
ADMIN_PANEL_EDIT_LIMIT = 6
ADMIN_PANEL_EDIT_PLANS = 7  
ADMIN_CHANNEL_INPUT = 8
ADMIN_CHANNEL_TITLE_INPUT = 9
ADMIN_SUPPORT_INPUT = 10
ADMIN_DELETE_USER_ID = 11
ADMIN_DELETE_USER_CONFIRM = 12
ADMIN_RESET_BALANCE_ID = 13
ADMIN_RESET_BALANCE_CONFIRM = 14
ADMIN_BONUS_INPUT = 15
ADMIN_COMMISSION_PERCENT_INPUT = 16  
ADMIN_CARD_INFO_INPUT = 17
ADMIN_EMERGENCY_PROXY_NAME_INPUT = 18
ADMIN_EMERGENCY_PROXY_LINK_INPUT = 19
ADMIN_EMERGENCY_ADD_USER_ID = 20
ADMIN_EMERGENCY_DENY_REASON = 21
ADMIN_MANUAL_SUB_USER_ID = 22
ADMIN_MANUAL_SUB_PLAN_NAME = 23
ADMIN_MANUAL_SUB_EXPIRY = 24
ADMIN_MANUAL_SUB_PRIORITY = 25
ADMIN_MANUAL_SUB_CONFIG = 26
ADMIN_ADDCONFIG_USER_ID = 27
ADMIN_ADDCONFIG_SELECT_SUB = 28
ADMIN_ADDCONFIG_PRIORITY = 29
ADMIN_ADDCONFIG_LINK = 30
ADMIN_MANUAL_SUB_VOLUME = 31
ADMIN_EMERGENCY_VOLUME_INPUT = 32    
ADMIN_EMERGENCY_DURATION_INPUT = 33  
ADMIN_EDITSUB_USER_ID = 34
ADMIN_EDITSUB_SELECT = 35
ADMIN_EDITSUB_DURATION_INPUT = 36
ADMIN_EDITSUB_VOLUME_INPUT = 37
ADMIN_USERINFO_ID = 38
ADMIN_MANUAL_SUB_TARGET = 39
ADMIN_ADDCONFIG_TARGET = 40
ADMIN_ADDCONFIG_PLAN_SELECT = 41

MANUAL_PLAN_PRESETS = {
    'balanced': '🟢 متعادل',
    'fair': '🔥 منصفانه',
    'pro': '💎 حرفه‌ای',
    'old': '📦 نامحدود تک کاربر',
    'customcharge': '🔥 طرح شارژ دلخواه',
}

import re
import hashlib

def _slugify_plan_name(plan_name: str) -> str:
    """
    نام طرح را به یک شناسه‌ی کوتاه و ASCII-safe تبدیل می‌کند تا در email/config id استفاده شود.
    اگر نام طرح شامل حروف انگلیسی/عدد باشد همان را (بدون فاصله و ایموجی) برمی‌گرداند.
    اگر نام طرح فارسی یا غیر ASCII باشد، یک هش کوتاه و ثابت (deterministic) تولید می‌کند
    تا برای یک نام طرح مشخص همیشه یک مقدار یکسان ساخته شود.
    """
    ascii_only = re.sub(r'[^A-Za-z0-9]+', '', plan_name or '')
    if ascii_only:
        return ascii_only.lower()[:20]
    digest = hashlib.md5((plan_name or '').encode('utf-8')).hexdigest()[:8]
    return f"plan{digest}"

from bot_settings import (
    get_sponsor_channel,
    set_sponsor_channel,
    get_sponsor_channel_title,
    set_sponsor_channel_title,
    is_membership_required,
    set_membership_required,
    get_support_username,
    set_support_username,
    get_signup_bonus,
    set_signup_bonus,
    get_referral_bonus_inviter,
    set_referral_bonus_inviter,
    get_referral_bonus_invitee,
    set_referral_bonus_invitee,
    get_special_panel_id,              
    set_special_panel_id,              
    get_special_panel_commission_percent,  
    set_special_panel_commission_percent,
    is_hybrid_payment_enabled,    
    set_hybrid_payment_enabled,
    get_card_number,          # <-- جدید
    set_card_number,          # <-- جدید
    get_card_holder,          # <-- جدید
    set_card_holder,          # <-- جدید
    get_card_bank,            # <-- جدید
    set_card_bank,            # <-- جدید
    is_lifeline_enabled,
    set_lifeline_enabled,
)

# Global references
db = None
get_main_menu_func = None

def set_db(database):
    """Set database instance"""
    global db
    db = database

def set_get_main_menu(func):
    """Set get_main_menu function reference"""
    global get_main_menu_func
    get_main_menu_func = func

def get_main_menu():
    """Get main menu keyboard"""
    if get_main_menu_func:
        return get_main_menu_func()
    # Fallback
    from telegram import KeyboardButton, ReplyKeyboardMarkup
    keyboard = [
        [KeyboardButton("🛒 Buy VPN")],
        [KeyboardButton("🗂 My Account"), KeyboardButton("📒 Subscriptions")],
        [KeyboardButton("📝 Help"), KeyboardButton("💰 Add Balance")],
        [KeyboardButton("➕ Add Extra Volume"), KeyboardButton("📨 Support")],
        [KeyboardButton("👥 Invite Friends")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

ADMIN_IDS = []

def set_admin_ids(admin_ids):
    """Set the list of admin user IDs"""
    global ADMIN_IDS
    ADMIN_IDS = admin_ids or []

def is_admin(user_id: int) -> bool:
    """Check if a user is an admin"""
    return user_id in ADMIN_IDS

# ============ Helper function for safe message sending ============

def safe_format_text(text):
    """Safely format text without markdown/HTML parsing issues"""
    # Just return the text as-is, no parsing
    return text

# ============ Admin Panel Handlers ============
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel entry point"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔️ You do not have admin access.")
        return

    keyboard = [
        [
            InlineKeyboardButton("👤 User Management", callback_data="admin_user_management"),
            InlineKeyboardButton("🖥 Manage Panels", callback_data="panel_manage"),
        ],
        [
            InlineKeyboardButton("📢 Sponsor Channel Settings", callback_data="admin_channel_settings"),
            InlineKeyboardButton("☎️ Support Address Settings", callback_data="admin_support_settings"),
        ],
        [
            InlineKeyboardButton("🎁 Gift & Bonus Settings", callback_data="admin_bonus_settings"),
            InlineKeyboardButton("💳 Payment Settings", callback_data="admin_payment_settings"),
        ],
        [
            InlineKeyboardButton("🆘 Emergency Management", callback_data="admin_emergency_settings"),
            InlineKeyboardButton("🕯 Lifeline Settings", callback_data="admin_lifeline_settings"),
        ],
        [
            InlineKeyboardButton("📋 Purchase Plans Management", callback_data="admin_dynamic_plans_menu"),
        ],
        [
            InlineKeyboardButton("🛰 AutoScanner (IP کلودفلر)", callback_data="admin_autoscanner_menu"),
        ],     
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🛠 Admin Panel\n\nPlease select an option:",
        reply_markup=reply_markup
    )


def _admin_main_menu_keyboard():
    """Build the top-level admin panel keyboard (used for the back button)"""
    keyboard = [
        [
            InlineKeyboardButton("👤 User Management", callback_data="admin_user_management"),
            InlineKeyboardButton("🖥 Manage Panels", callback_data="panel_manage"),
        ],
        [
            InlineKeyboardButton("📢 Sponsor Channel Settings", callback_data="admin_channel_settings"),
            InlineKeyboardButton("☎️ Support Address Settings", callback_data="admin_support_settings"),
        ],
        [
            InlineKeyboardButton("🎁 Gift & Bonus Settings", callback_data="admin_bonus_settings"),
            InlineKeyboardButton("💳 Payment Settings", callback_data="admin_payment_settings"),
        ],
        [
            InlineKeyboardButton("🆘 Emergency Management", callback_data="admin_emergency_settings"),
            InlineKeyboardButton("🕯 Lifeline Settings", callback_data="admin_lifeline_settings"),
        ],
        [
            InlineKeyboardButton("📋 Purchase Plans Management", callback_data="admin_dynamic_plans_menu"),
        ],
        [
            InlineKeyboardButton("🛰 AutoScanner (IP کلودفلر)", callback_data="admin_autoscanner_menu"),
        ],     
    ]
    return InlineKeyboardMarkup(keyboard)


async def admin_back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to the top-level admin panel (from a submenu, via callback)"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    await query.edit_message_text(
        "🛠 Admin Panel\n\nPlease select an option:",
        reply_markup=_admin_main_menu_keyboard()
    )


async def admin_user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the User Management submenu"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    keyboard = [
        [InlineKeyboardButton("🔍 View User Info", callback_data="admin_userinfo_start")],   # <-- جدید
        [InlineKeyboardButton("💰 Add User Balance", callback_data="admin_add_balance")],
        [InlineKeyboardButton("➕ Add Manual Subscription", callback_data="admin_manual_sub_add")],
        [InlineKeyboardButton("🎁 Send Plan to User(s)", callback_data="admin_send_plan_start")],
        [InlineKeyboardButton("✏️ Edit User Subscription", callback_data="admin_editsub_start")],
        [InlineKeyboardButton("➕ Add Config to Subscription", callback_data="admin_addconfig_start")],
        [InlineKeyboardButton("🗑 Delete / Reset User Subscription", callback_data="admin_delete_sub")],
        [InlineKeyboardButton("🧨 Delete User", callback_data="admin_delete_user")],
        [InlineKeyboardButton("♻️ Reset User Wallet", callback_data="admin_reset_balance")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back_to_main_menu")],
    ]

    await query.edit_message_text(
        "👤 User Management\n\nPlease select an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
# ============ Admin Add Balance ============
async def admin_add_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for target user id"""
    query = update.callback_query
    await query.answer()

    admin_user_id = query.from_user.id
    if not is_admin(admin_user_id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "👤 Please send the target user's numeric ID:\n\n"
        "⚠️ Send /cancel to abort."
    )
    return ADMIN_USER_ID_INPUT

async def admin_add_balance_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive target user id"""
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(
            "❌ The ID must be numeric only. Please send it again:\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_USER_ID_INPUT

    target_user_id = int(text)
    target_user = db.get_user(target_user_id)

    if not target_user:
        await update.message.reply_text(
            "❌ No user found with this ID.\n\n"
            "Please send a different ID or /cancel to abort."
        )
        return ADMIN_USER_ID_INPUT

    context.user_data['admin_target_user_id'] = target_user_id
    balance_str = f"{target_user['balance']:,}"
    name = target_user['first_name'] or target_user['username'] or 'User'

    await update.message.reply_text(
        f"👤 User found:\n\n"
        f"🔰 ID: <code>{target_user_id}</code>\n"
        f"👤 Name: {html_lib.escape(name)}\n"
        f"💰 Current balance: {balance_str} Toman\n\n"
        f"💵 Please enter the amount to add to this user's balance (Toman):\n"
        f"Example: 50000\n\n"
        f"⚠️ Send /cancel to abort.",
        parse_mode='HTML'  # HTML is safe with proper escaping
    )
    return ADMIN_AMOUNT_INPUT

async def admin_add_balance_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive amount and apply balance increase"""
    text = update.message.text.strip()

    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid number:\n"
            "Example: 50000\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_AMOUNT_INPUT

    if amount <= 0:
        await update.message.reply_text(
            "❌ The amount must be greater than zero. Please enter it again:"
        )
        return ADMIN_AMOUNT_INPUT

    target_user_id = context.user_data.get('admin_target_user_id')
    if not target_user_id:
        await update.message.reply_text("❌ Error! Please try again.", reply_markup=get_main_menu())
        return ConversationHandler.END

    admin_id = update.effective_user.id

    db.update_balance(target_user_id, amount)
    db.add_transaction(
        target_user_id, amount, "admin_charge",
        f"Balance increased by admin ({admin_id})"
    )

    updated_user = db.get_user(target_user_id)
    balance_str = f"{updated_user['balance']:,}"
    amount_str = f"{amount:,}"

    await update.message.reply_text(
        f"✅ User balance increased successfully.\n\n"
        f"🔰 User ID: <code>{target_user_id}</code>\n"
        f"💵 Amount added: {amount_str} Toman\n"
        f"💰 New balance: {balance_str} Toman",
        parse_mode='HTML',
        reply_markup=get_main_menu()
    )

    # Notify the user themselves
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"🎉 موجودی حساب شما توسط پشتیبانی افزایش یافت!\n\n"
                f"💵 مبلغ افزوده شده: {amount_str} تومان\n"
                f"💰 موجودی جدید: {balance_str} تومان"
            )
        )
    except Exception as e:
        logger.error(f"Could not notify user {target_user_id}: {e}")

    context.user_data.pop('admin_target_user_id', None)
    return ConversationHandler.END

# ============ Admin Cancel ============

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel admin conversation"""
    context.user_data.pop('admin_target_user_id', None)
    await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
    return ConversationHandler.END

# ============ Admin Delete Subscription ============

async def admin_delete_sub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the delete/reset subscription flow - get user ID"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "👤 Please send the numeric ID of the user whose subscription you want to delete/reset:\n\n"
        "⚠️ Send /cancel to abort."
    )
    return ADMIN_DELSUB_USER_ID

async def admin_delete_sub_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive user ID and show their list of subscriptions"""
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(
            "❌ The ID must be numeric only. Please send it again:\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_DELSUB_USER_ID

    target_user_id = int(text)
    target_user = db.get_user(target_user_id)

    if not target_user:
        await update.message.reply_text(
            "❌ No user found with this ID.\n\n"
            "Please send a different ID or /cancel to abort."
        )
        return ADMIN_DELSUB_USER_ID

    subscriptions = db.get_active_subscriptions(target_user_id)

    if not subscriptions:
        await update.message.reply_text(
            "ℹ️ This user has no active subscriptions.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END

    context.user_data['admin_delsub_target'] = target_user_id
    context.user_data['admin_delsub_list'] = subscriptions

    protocol_names = {
        "wireguard": "WireGuard 🌐",
        "openvpn": "OpenVPN",
        "v2ray": "V2Ray"
    }

    keyboard = []
    text_lines = [f"📒 Active subscriptions for user <code>{target_user_id}</code>:\n"]
    for i, sub in enumerate(subscriptions):
        proto = protocol_names.get(sub['protocol'], sub['protocol'])
        text_lines.append(
            f"{i+1}. {proto} - {sub['duration_days']} days - until {sub['end_date']}"
        )
        keyboard.append([
            InlineKeyboardButton(f"🗑 Delete item {i+1}", callback_data=f"admin_delsub_one_{i}")
        ])

    keyboard.append([InlineKeyboardButton("🗑 Delete / Reset All Subscriptions", callback_data="admin_delsub_all")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_delsub_cancel")])

    await update.message.reply_text(
        "\n".join(text_lines),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_DELSUB_SELECT

async def admin_delete_sub_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perform deletion based on admin's selection"""
    query = update.callback_query
    await query.answer()

    target_user_id = context.user_data.get('admin_delsub_target')
    subscriptions = context.user_data.get('admin_delsub_list', [])

    if not target_user_id:
        await query.edit_message_text("❌ Error! Please try again.")
        return ConversationHandler.END

    data = query.data

    if data == "admin_delsub_cancel":
        await query.edit_message_text("❌ Operation cancelled.")
        context.user_data.pop('admin_delsub_target', None)
        context.user_data.pop('admin_delsub_list', None)
        return ConversationHandler.END

    if data == "admin_delsub_all":
        count = 0
        for sub in subscriptions:
            # Remove from database
            db.delete_subscription(sub['id'])
            # Remove from 3xUI panel
            if sub.get('email'):
                try:
                    from client_manager import get_panel_client
                    panel_client = get_panel_client()
                    panel_client.delete_client(sub['email'])
                except Exception as e:
                    logger.error(f"Error deleting client from panel: {e}")
            count += 1
        await query.edit_message_text(
            f"✅ {count} subscription(s) for user <code>{target_user_id}</code> deleted/reset successfully.",
            parse_mode='HTML'
        )
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="⚠️ تمامی اشتراک‌های شما توسط پشتیبانی حذف/ریست شد."
            )
        except Exception as e:
            logger.error(f"Could not notify user {target_user_id}: {e}")

    elif data.startswith("admin_delsub_one_"):
        idx = int(data.replace("admin_delsub_one_", ""))
        if idx >= len(subscriptions):
            await query.edit_message_text("❌ This item is no longer valid.")
            context.user_data.pop('admin_delsub_target', None)
            context.user_data.pop('admin_delsub_list', None)
            return ConversationHandler.END

        sub = subscriptions[idx]
        db.delete_subscription(sub['id'])

        # Remove from 3xUI panel
        if sub.get('email'):
            try:
                from client_manager import get_panel_client
                panel_client = get_panel_client()
                panel_client.delete_client(sub['email'])
            except Exception as e:
                logger.error(f"Error deleting client from panel: {e}")

        await query.edit_message_text(
            f"✅ Selected subscription for user <code>{target_user_id}</code> deleted successfully.",
            parse_mode='HTML'
        )
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="⚠️ یکی از اشتراک‌های شما توسط پشتیبانی حذف شد."
            )
        except Exception as e:
            logger.error(f"Could not notify user {target_user_id}: {e}")

    context.user_data.pop('admin_delsub_target', None)
    context.user_data.pop('admin_delsub_list', None)
    return ConversationHandler.END

# ============ Admin: View Full User Info ============
async def admin_userinfo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "🔍 View User Info\n\n"
        "👤 Please send the target user's numeric ID:\n\n"
        "⚠️ Send /cancel to abort."
    )
    return ADMIN_USERINFO_ID

async def admin_userinfo_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text(
            "❌ The ID must be numeric only. Please send it again:\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_USERINFO_ID

    target_user_id = int(text)
    user = db.get_user(target_user_id)

    if not user:
        await update.message.reply_text(
            "❌ No user found with this ID.\n\nPlease send a different ID or /cancel to abort."
        )
        return ADMIN_USERINFO_ID

    username_display = f"@{user.get('username')}" if user.get('username') else "-"
    name = user.get('first_name') or "-"
    balance_str = f"{user.get('balance', 0):,}"

    active_subs = db.get_active_subscriptions(target_user_id)

    header = (
        f"👤 User Info\n\n"
        f"🔰 ID: <code>{target_user_id}</code>\n"
        f"👤 Name: {html_lib.escape(str(name))}\n"
        f"🆔 Username: {html_lib.escape(username_display)}\n"
        f"💰 Balance: {balance_str} Toman\n"
        f"📊 Active subscriptions: {len(active_subs)}\n"
    )
    await update.message.reply_text(header, parse_mode='HTML')

    if not active_subs:
        await update.message.reply_text("ℹ️ No active subscriptions for this user.", reply_markup=get_main_menu())
        return ConversationHandler.END

    from handlers import get_single_sub_link

    for i, sub in enumerate(active_subs, 1):
        vol = sub.get('remaining_volume', 0)
        vol_text = 'Unlimited' if not vol else f"{vol} GB"
        end_date = str(sub.get('end_date', ''))[:10]

        panel_name = "-"
        panel_id = sub.get('panel_id')
        if panel_id:
            panel_manager = get_panel_manager()
            panel_data = panel_manager.get_panel(panel_id)
            if panel_data:
                panel_name = panel_data.get('name', panel_id)

        manual_configs = db.get_manual_configs(sub['id']) or []
        manual_configs_count = len(manual_configs)

        sub_text = (
            f"📦 Subscription {i}\n\n"
            f"🆔 Sub ID: {sub['id']}\n"
            f"📛 Plan: {sub.get('plan_name') or sub.get('plan_type', '-')}\n"
            f"📧 Email: {sub.get('email', '-')}\n"
            f"🖥 Panel: {panel_name}\n"
            f"⏰ Duration: {sub.get('duration_days')} days\n"
            f"📅 Expires: {end_date}\n"
            f"📊 Volume: {vol_text}\n"
            f"🔗 Manual configs: {manual_configs_count}\n"
        )

        single_link = get_single_sub_link(sub['id'])
        if single_link:
            sub_text += f"\n🔗 Subscription link:\n<code>{single_link}</code>"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔧 Get Config", callback_data=f"get_config_{sub['id']}")]
        ])

        await update.message.reply_text(
            sub_text,
            parse_mode='HTML',
            disable_web_page_preview=True,
            reply_markup=keyboard
        )

    await update.message.reply_text("✅ Done.", reply_markup=get_main_menu())
    return ConversationHandler.END

# ============ Admin Panel Management ============
async def admin_manage_panels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel management"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    panel_manager = get_panel_manager()
    panels = panel_manager.get_all_panels()
    usage = panel_manager.panel_usage

    keyboard = []

    for pid, panel in panels.items():
        status = "✅" if panel.get('enabled', True) else "❌"
        default = "⭐️ " if panel.get('is_default', False) else ""
        usage_count = usage.get(pid, 0)
        max_subs = panel.get('max_subscriptions', 100)

        # Show supported plan types briefly
        plan_types = panel.get('plan_types', ['new', 'old', 'custom_charge'])
        plan_icons = []
        if 'new' in plan_types:
            plan_icons.append('🆕')
        if 'old' in plan_types:
            plan_icons.append('📦')
        if 'custom_charge' in plan_types:
            plan_icons.append('🔥')
        if 'emergency' in plan_types:      # <-- جدید
            plan_icons.append('🆘')
        plan_display = ''.join(plan_icons) if plan_icons else '📌'

        keyboard.append([
            InlineKeyboardButton(
                f"{default}{status} {panel.get('name')} {plan_display} ({usage_count}/{max_subs})",
                callback_data=f"panel_info_{pid}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("🎯 Panel Access by Commission", callback_data="admin_commission_settings")
    ])
    keyboard.append([
        InlineKeyboardButton("➕ Add New Panel", callback_data="panel_add"),
        InlineKeyboardButton("🔙 Back", callback_data="back_to_main")
    ])

    await query.edit_message_text(
        "🖥 Panel Management\n\n"
        "List of existing panels:\n"
        "⭐️ = Default panel\n"
        "✅ = Enabled | ❌ = Disabled\n"
        "(usage/limit)\n"
        "🆕 = New plan | 📦 = Old plan | 🔥 = Custom charge plan | 🆘 = Emergency plan",  # <-- اصلاح شد
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None
    )

async def admin_panel_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show panel info and actions"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    panel_id = query.data.replace("panel_info_", "")
    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await query.edit_message_text("❌ Panel not found.")
        return

    usage = panel_manager.panel_usage.get(panel_id, 0)

    # Show supported plan types in readable form
    plan_types = panel.get('plan_types', ['new', 'old', 'custom_charge'])
    plan_names = {
        'new': '🆕 New Plan (Unlimited)',
        'old': '📦 Old Plan (Single User)',
        'custom_charge': '🔥 Custom Charge Plan',
        'emergency': '🆘 Emergency Plan',
    }
    plan_display = '\n'.join([plan_names.get(p, p) for p in plan_types]) if plan_types else 'All plans'

    keyboard = [
        [
            InlineKeyboardButton("✏️ Edit Plans", callback_data=f"panel_edit_plans_{panel_id}")
        ],
        [
            InlineKeyboardButton("✏️ Edit Subscription Limit", callback_data=f"panel_edit_limit_{panel_id}")
        ],
        [
            InlineKeyboardButton("🗑 Delete", callback_data=f"panel_delete_{panel_id}")
        ],
        [
            InlineKeyboardButton("⭐️ Set as Default", callback_data=f"panel_set_default_{panel_id}")
        ],
        [
            InlineKeyboardButton("🔄 Test Connection", callback_data=f"panel_test_{panel_id}")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="panel_manage")]
    ]

    text = f"""
Panel Info

🆔 ID: {panel_id}
📛 Name: {panel.get('name')}
🌐 Address: {panel.get('panel_base')}
👤 Username: {panel.get('username')}
📊 Subscription limit: {panel.get('max_subscriptions', 100)}
📈 Current usage: {usage}
🔰 Status: {'✅ Enabled' if panel.get('enabled', True) else '❌ Disabled'}
⭐️ Default: {'✅' if panel.get('is_default', False) else '❌'}

📋 Supported plans:
{plan_display}

📅 Created: {panel.get('created_at', 'Unknown')}
    """

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None  # Changed from Markdown to None
    )

# ============ Admin Panel Edit Plans ============
async def admin_panel_edit_plans_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start editing panel plan types"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    panel_id = query.data.replace("panel_edit_plans_", "")
    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await query.edit_message_text("❌ Panel not found.")
        return ConversationHandler.END

    context.user_data['admin_edit_plans_panel_id'] = panel_id
    current_plans = panel.get('plan_types', ['new', 'old', 'custom_charge'])

    if 'custom' in current_plans and 'custom_charge' not in current_plans:
        current_plans.remove('custom')
        current_plans.append('custom_charge')
        panel_manager.update_panel(panel_id, plan_types=current_plans)

    plan_names = {
        'new': '🆕 New Plan (Unlimited)',
        'old': '📦 Old Plan (Single User)',
        'custom_charge': '🔥 Custom Charge Plan',
        'emergency': '🆘 Emergency Plan',
        'custom_plan': '🧩 Dynamic Purchase Plans',
    }

    current_display = '\n'.join([f"✅ {plan_names.get(p, p)}" for p in current_plans])
    if not current_plans:
        current_display = '❌ No plan selected'

    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✅' if 'new' in current_plans else '⬜'} New Plan",
                callback_data=f"panel_toggle_plan_new_{panel_id}"
            ),
            InlineKeyboardButton(
                f"{'✅' if 'old' in current_plans else '⬜'} Old Plan",
                callback_data=f"panel_toggle_plan_old_{panel_id}"
            ),
            InlineKeyboardButton(
                f"{'✅' if 'custom_charge' in current_plans else '⬜'} Custom Charge",
                callback_data=f"panel_toggle_plan_custom_{panel_id}"
            )
        ],
        [
            InlineKeyboardButton(  # <-- جدید
                f"{'✅' if 'emergency' in current_plans else '⬜'} 🆘 Emergency Plan",
                callback_data=f"panel_toggle_plan_emergency_{panel_id}"
            ),
            InlineKeyboardButton(  # <-- جدید
                f"{'✅' if 'custom_plan' in current_plans else '⬜'} 🧩 Dynamic Plans",
                callback_data=f"panel_toggle_plan_customplan_{panel_id}"
            )
        ],
        [InlineKeyboardButton("💾 Save Changes", callback_data=f"panel_save_plans_{panel_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"panel_info_{panel_id}")]
    ]

    await query.edit_message_text(
        f"✏️ Edit Panel Supported Plans\n\n"
        f"📛 Panel: {panel.get('name')}\n\n"
        f"📋 Current status:\n{current_display}\n\n"
        f"Click each button to enable/disable a plan.\n"
        f"Then click «💾 Save Changes».",
        parse_mode=None,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_PANEL_EDIT_PLANS

async def admin_panel_toggle_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle a plan type for a panel (temporary, not saved yet)"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data

    if data.startswith("panel_toggle_plan_new_"):
        panel_id = data.replace("panel_toggle_plan_new_", "")
        plan_type = 'new'
    elif data.startswith("panel_toggle_plan_old_"):
        panel_id = data.replace("panel_toggle_plan_old_", "")
        plan_type = 'old'
    elif data.startswith("panel_toggle_plan_custom_"):
        panel_id = data.replace("panel_toggle_plan_custom_", "")
        plan_type = 'custom_charge'
    elif data.startswith("panel_toggle_plan_emergency_"):
        panel_id = data.replace("panel_toggle_plan_emergency_", "")
        plan_type = 'emergency'
    elif data.startswith("panel_toggle_plan_customplan_"):  # <-- اضافه شد
        panel_id = data.replace("panel_toggle_plan_customplan_", "")
        plan_type = 'custom_plan'
    else:
        await query.answer("❌ Invalid data format!", show_alert=True)
        return

    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await query.edit_message_text("❌ Panel not found.")
        return

    temp_plans = context.user_data.get(f'temp_plans_{panel_id}')
    if temp_plans is None:
        temp_plans = panel.get('plan_types', ['new', 'old', 'custom_charge']).copy()
        if 'custom' in temp_plans and 'custom_charge' not in temp_plans:
            temp_plans.remove('custom')
            temp_plans.append('custom_charge')

    # Toggle status — دیگر هیچ محدودیتی برای حداقل یک پلن اصلی وجود ندارد
    if plan_type in temp_plans:
        temp_plans.remove(plan_type)
    else:
        temp_plans.append(plan_type)

    context.user_data[f'temp_plans_{panel_id}'] = temp_plans

    plan_names = {
        'new': '🆕 New Plan (Unlimited)',
        'old': '📦 Old Plan (Single User)',
        'custom_charge': '🔥 Custom Charge Plan',
        'emergency': '🆘 Emergency Plan',
        'custom_plan': '🧩 Dynamic Purchase Plans',
    }

    current_display = '\n'.join([f"✅ {plan_names.get(p, p)}" for p in temp_plans])
    if not temp_plans:
        current_display = '❌ No plan selected'

    keyboard = [
        [
            InlineKeyboardButton(
                f"{'✅' if 'new' in temp_plans else '⬜'} New Plan",
                callback_data=f"panel_toggle_plan_new_{panel_id}"
            ),
            InlineKeyboardButton(
                f"{'✅' if 'old' in temp_plans else '⬜'} Old Plan",
                callback_data=f"panel_toggle_plan_old_{panel_id}"
            ),
            InlineKeyboardButton(
                f"{'✅' if 'custom_charge' in temp_plans else '⬜'} Custom Charge",
                callback_data=f"panel_toggle_plan_custom_{panel_id}"
            )
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if 'emergency' in temp_plans else '⬜'} 🆘 Emergency Plan",
                callback_data=f"panel_toggle_plan_emergency_{panel_id}"
            ),
            InlineKeyboardButton(
                f"{'✅' if 'custom_plan' in temp_plans else '⬜'} 🧩 Dynamic Plans",
                callback_data=f"panel_toggle_plan_customplan_{panel_id}"
            )
        ],
        [InlineKeyboardButton("💾 Save Changes", callback_data=f"panel_save_plans_{panel_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data=f"panel_info_{panel_id}")]
    ]

    await query.edit_message_text(
        f"✏️ Edit Panel Supported Plans\n\n"
        f"📛 Panel: {panel.get('name')}\n\n"
        f"📋 Current status:\n{current_display}\n\n"
        f"Click each button to enable/disable a plan.\n"
        f"Then click «💾 Save Changes».",
        parse_mode=None,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_PANEL_EDIT_PLANS

async def admin_panel_save_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    panel_id = query.data.replace("panel_save_plans_", "")
    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await query.edit_message_text("❌ Panel not found.")
        return

    temp_plans = context.user_data.get(f'temp_plans_{panel_id}')
    if temp_plans is None:
        temp_plans = panel.get('plan_types', ['new', 'old', 'custom_charge'])
        if 'custom' in temp_plans and 'custom_charge' not in temp_plans:
            temp_plans.remove('custom')
            temp_plans.append('custom_charge')

    old_plans = panel.get('plan_types', [])
    success = panel_manager.update_panel(panel_id, plan_types=temp_plans)

    if success:
        context.user_data.pop(f'temp_plans_{panel_id}', None)

        plan_names = {
            'new': '🆕 New Plan (Unlimited)',
            'old': '📦 Old Plan (Single User)',
            'custom_charge': '🔥 Custom Charge Plan',
            'emergency': '🆘 Emergency Plan',
            'custom_plan': '🧩 Dynamic Purchase Plans',
        }
        saved_display = '\n'.join([f"✅ {plan_names.get(p, p)}" for p in temp_plans])

        try:
            from logger_bot import log_admin_action
            admin = query.from_user

            changes = []
            for plan in ['new', 'old', 'custom_charge', 'emergency']:
                was_in_old = plan in old_plans
                is_in_new = plan in temp_plans
                if was_in_old and not is_in_new:
                    changes.append(f"❌ Removed {plan_names.get(plan, plan)}")
                elif not was_in_old and is_in_new:
                    changes.append(f"✅ Added {plan_names.get(plan, plan)}")

            change_text = "\n".join(changes) if changes else "No changes"

            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="Edit panel plans",
                target_user_id=None,
                details=f"""
🖥 Panel: {panel.get('name')} (`{panel_id}`)
📋 Changes:
{change_text}
📊 New status:
{saved_display}
                """.strip(),
                username=admin.username,
                first_name=admin.first_name,
                last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        await query.edit_message_text(
            f"✅ Changes saved successfully!\n\n"
            f"📛 Panel: {panel.get('name')}\n\n"
            f"📋 Supported plans:\n{saved_display}",
            parse_mode=None,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Panel Info", callback_data=f"panel_info_{panel_id}")]
            ])
        )
        return ConversationHandler.END
    else:
        await query.edit_message_text(
            "❌ Error saving changes. Please try again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data=f"panel_info_{panel_id}")]
            ])
        )
        return ADMIN_PANEL_EDIT_PLANS

# ============ Admin Panel Edit Limit ============
async def admin_panel_edit_limit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start editing panel subscription limit"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    panel_id = query.data.replace("panel_edit_limit_", "")
    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await query.edit_message_text("❌ Panel not found.")
        return ConversationHandler.END

    context.user_data['admin_edit_panel_id'] = panel_id
    current_limit = panel.get('max_subscriptions', 100)
    usage = panel_manager.panel_usage.get(panel_id, 0)

    await query.edit_message_text(
        f"✏️ Edit Panel Subscription Limit\n\n"
        f"📛 Panel: {panel.get('name')}\n"
        f"📊 Current limit: {current_limit}\n"
        f"📈 Current usage: {usage}\n\n"
        f"Please enter the new limit (integer):\n"
        f"⚠️ The new limit must be greater than or equal to the current usage ({usage}).\n\n"
        f"Send /cancel to abort.",
        parse_mode=None  # Changed from Markdown to None
    )
    return ADMIN_PANEL_EDIT_LIMIT

async def admin_panel_edit_limit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process panel limit edit input"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    try:
        new_limit = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid integer.\n\n"
            "Send /cancel to abort."
        )
        return ADMIN_PANEL_EDIT_LIMIT

    if new_limit < 1:
        await update.message.reply_text(
            "❌ The subscription limit must be at least 1.\n\n"
            "Send /cancel to abort."
        )
        return ADMIN_PANEL_EDIT_LIMIT

    panel_id = context.user_data.get('admin_edit_panel_id')
    if not panel_id:
        await update.message.reply_text("❌ Error! Please try again.", reply_markup=get_main_menu())
        return ConversationHandler.END

    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await update.message.reply_text("❌ Panel not found.", reply_markup=get_main_menu())
        return ConversationHandler.END

    usage = panel_manager.panel_usage.get(panel_id, 0)

    if new_limit < usage:
        await update.message.reply_text(
            f"❌ The new limit ({new_limit}) cannot be less than the current usage ({usage}).\n\n"
            f"Please enter a larger number or /cancel to abort."
        )
        return ADMIN_PANEL_EDIT_LIMIT

    # Update limit
    success = panel_manager.update_panel(panel_id, max_subscriptions=new_limit)

    if success:
        # ============ لاگ تغییر محدودیت پنل ============
        try:
            from logger_bot import log_admin_action
            admin = update.effective_user

            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="Change panel subscription limit",
                target_user_id=None,
                details=f"""
🖥 Panel: {panel.get('name')} (`{panel_id}`)
📊 Previous limit: {panel.get('max_subscriptions', 100)}
📊 New limit: {new_limit}
📈 Current usage: {usage}
                """.strip(),
                username=admin.username,
                first_name=admin.first_name,
                last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")
            
        await update.message.reply_text(
            f"✅ Panel subscription limit updated successfully!\n\n"
            f"📛 Panel: {panel.get('name')}\n"
            f"📊 New limit: {new_limit}\n"
            f"📈 Current usage: {usage}",
            reply_markup=get_main_menu()
        )

        # Return to panel management screen
        context.user_data.pop('admin_edit_panel_id', None)
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Error updating panel limit.")
        return ADMIN_PANEL_EDIT_LIMIT

# ============ Admin Panel Add ============

async def admin_panel_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start adding a new panel"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    await query.edit_message_text(
        "➕ Add New Panel\n\n"
        "Please enter the following information in order (one value per line):\n\n"
        "1️⃣ Panel name (e.g. Main Panel)\n"
        "2️⃣ Panel address (e.g. https://panel.example.com)\n"
        "3️⃣ Username\n"
        "4️⃣ Password\n"
        "5️⃣ Inbound IDs (e.g. 82,80,81)\n"
        "6️⃣ Subscription limit (e.g. 100)\n\n"
        "⚠️ After adding, you can configure the supported plans.\n"
        "⚠️ Send /cancel to abort.",
        parse_mode=None  # Changed from Markdown to None
    )
    return ADMIN_PANEL_ADD

async def admin_panel_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process panel add input"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    lines = text.split('\n')
    if len(lines) < 6:
        await update.message.reply_text(
            "❌ Please enter all 6 values (one value per line):\n\n"
            "1️⃣ Panel name\n"
            "2️⃣ Panel address\n"
            "3️⃣ Username\n"
            "4️⃣ Password\n"
            "5️⃣ Inbound IDs (e.g. 82,80,81)\n"
            "6️⃣ Subscription limit (e.g. 100)"
        )
        return ADMIN_PANEL_ADD

    name = lines[0].strip()
    panel_base = lines[1].strip()
    username = lines[2].strip()
    password = lines[3].strip()

    try:
        inbound_ids = [int(x.strip()) for x in lines[4].split(',') if x.strip()]
        if not inbound_ids:
            inbound_ids = [82, 80, 81]
    except:
        inbound_ids = [82, 80, 81]

    try:
        max_subscriptions = int(lines[5].strip())
    except:
        max_subscriptions = 100

    # Test connection
    panel_manager = get_panel_manager()
    success, msg = panel_manager.test_panel_connection(panel_base, username, password)

    if not success:
        await update.message.reply_text(
            f"❌ Error connecting to panel:\n{msg}\n\n"
            "Please re-enter the information or send /cancel to abort."
        )
        return ADMIN_PANEL_ADD

    # Generate panel ID
    panel_id = f"panel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # All plans are enabled by default
    plan_types = ['new', 'old', 'custom_charge']

    success = panel_manager.add_panel(
        panel_id=panel_id,
        name=name,
        panel_base=panel_base,
        username=username,
        password=password,
        inbound_ids=inbound_ids,
        max_subscriptions=max_subscriptions,
        is_default=(len(panel_manager.get_all_panels()) == 0),
        plan_types=plan_types
    )

    if success:
        # ============ لاگ اضافه کردن پنل جدید ============
        try:
            from logger_bot import log_admin_action
            admin = update.effective_user

            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="Add new panel",
                target_user_id=None,
                details=f"""
🖥 Panel name: {name}
🌐 Address: {panel_base}
👤 Username: {username}
📊 Inbounds: {inbound_ids}
📈 Subscription limit: {max_subscriptions}
📋 Supported plans: new, old, custom_charge
                """.strip(),
                username=admin.username,
                first_name=admin.first_name,
                last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")
            
        await update.message.reply_text(
            f"✅ Panel added successfully!\n\n"
            f"🆔 ID: {panel_id}\n"
            f"📛 Name: {name}\n"
            f"🌐 Address: {panel_base}\n"
            f"📊 Subscription limit: {max_subscriptions}\n"
            f"📋 Supported plans: all plans (new, old, custom charge)\n\n"
            f"💡 You can edit the supported plans from the panel info section.",
            parse_mode=None,  # Changed from Markdown to None
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ Error adding panel. Please try again.")
        return ADMIN_PANEL_ADD

# ============ Admin Panel Delete/Default/Test ============
async def admin_panel_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a panel"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    panel_id = query.data.replace("panel_delete_", "")
    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)
    panel_name = panel.get('name') if panel else panel_id

    if panel_manager.remove_panel(panel_id):
        try:
            from logger_bot import log_admin_action
            admin = query.from_user

            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="Delete panel",
                target_user_id=None,
                details=f"""
🖥 Deleted panel: {panel_name} (`{panel_id}`)
                """.strip(),
                username=admin.username,
                first_name=admin.first_name,
                last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        await query.edit_message_text("✅ Panel deleted successfully.")
    else:
        await query.edit_message_text("❌ Error deleting panel.")

# ============ Admin Sponsor Channel Settings ============

def _channel_settings_text_and_keyboard():
    channel = get_sponsor_channel()
    channel_title = get_sponsor_channel_title()
    required = is_membership_required()
    status_text = "✅ Enabled (mandatory)" if required else "❌ Disabled (not required)"

    text = (
        f"📢 Sponsor Channel Settings\n\n"
        f"🔗 Current channel: {channel}\n"
        f"🏷 Display text (link title): {channel_title}\n"
        f"🔰 Membership check status: {status_text}\n\n"
        f"Use the buttons below to change the channel, its display text, or toggle the requirement."
    )

    keyboard = [
        [InlineKeyboardButton("✏️ Change Channel", callback_data="admin_channel_edit")],
        [InlineKeyboardButton("🏷 Change Display Text", callback_data="admin_channel_title_edit")],
        [InlineKeyboardButton(
            "🔴 Disable Membership Check" if required else "🟢 Enable Membership Check",
            callback_data="admin_channel_toggle"
        )],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def admin_channel_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show sponsor channel settings menu"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    text, reply_markup = _channel_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)

def _lifeline_settings_text_and_keyboard():
    enabled = is_lifeline_enabled()
    status_text = "✅ On" if enabled else "❌ Off"

    text = (
        f"🕯 Tunnel Road Lifeline Settings\n\n"
        f"Current status: {status_text}\n\n"
        f"When enabled, a «Tunnel Road Lifeline» message is created/updated in the channel, "
        f"and remaining days change based on user joins/leaves/purchases."
    )

    keyboard = [
        [InlineKeyboardButton(
            "🔴 Turn Off" if enabled else "🟢 Turn On",
            callback_data="admin_lifeline_toggle"
        )],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back_to_main_menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def admin_lifeline_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    text, reply_markup = _lifeline_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)

async def admin_lifeline_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer("⛔️ No access.", show_alert=True)
        return

    new_value = not is_lifeline_enabled()
    set_lifeline_enabled(new_value)
    await query.answer("✅ Status updated.")

    try:
        from logger_bot import log_admin_action
        admin = query.from_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Toggle Tunnel Road Lifeline status",
            target_user_id=None,
            details=f"New status: {'On' if new_value else 'Off'}",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    if new_value:
        import lifeline
        await lifeline.post_or_update_lifeline(context.bot)

    text, reply_markup = _lifeline_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
    
async def admin_channel_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle membership requirement on/off"""
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer("⛔️ No access.", show_alert=True)
        return

    new_value = not is_membership_required()
    set_membership_required(new_value)
    await query.answer("✅ Status updated.")

    # ============ لاگ تغییر وضعیت ============
    try:
        from logger_bot import log_admin_action
        admin = query.from_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Toggle mandatory channel membership",
            target_user_id=None,
            details=f"New status: {'Enabled' if new_value else 'Disabled'}",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    text, reply_markup = _channel_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)

async def admin_channel_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for the new channel username"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    current = get_sponsor_channel()
    await query.edit_message_text(
        f"📢 Change Sponsor Channel\n\n"
        f"🔗 Current channel: {current}\n\n"
        f"Please send the new channel username (with or without @, e.g. @mychannel)\n"
        f"or a full t.me link (e.g. https://t.me/mychannel).\n\n"
        f"⚠️ Note: the bot must be an admin in the target channel to check membership.\n"
        f"⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_CHANNEL_INPUT


async def admin_channel_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save the new channel"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text:
        await update.message.reply_text(
            "❌ Invalid value. Please send the channel username again, or /cancel to abort."
        )
        return ADMIN_CHANNEL_INPUT

    old_channel = get_sponsor_channel()
    set_sponsor_channel(text)
    new_channel = get_sponsor_channel()

    # ============ لاگ تغییر کانال ============
    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Change sponsor channel",
            target_user_id=None,
            details=f"Previous channel: {old_channel}\nNew channel: {new_channel}",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    await update.message.reply_text(
        f"✅ Sponsor channel updated successfully!\n\n"
        f"🔗 New channel: {new_channel}\n\n"
        f"⚠️ Make sure the bot is an admin in this channel, otherwise membership checks will fail.",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END
async def admin_channel_title_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for the new display text (link title)"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    current = get_sponsor_channel_title()
    await query.edit_message_text(
        f"🏷 Change Display Text\n\n"
        f"Current display text: {current}\n\n"
        f"Please send the new text that should be shown instead of the raw link\n"
        f"(e.g. Jade Tunnel).\n\n"
        f"⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_CHANNEL_TITLE_INPUT


async def admin_channel_title_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save the new display text"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text:
        await update.message.reply_text(
            "❌ Invalid value. Please send the display text again, or /cancel to abort."
        )
        return ADMIN_CHANNEL_TITLE_INPUT

    old_title = get_sponsor_channel_title()
    set_sponsor_channel_title(text)
    new_title = get_sponsor_channel_title()

    # ============ لاگ تغییر نام نمایشی کانال ============
    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Change channel link display text",
            target_user_id=None,
            details=f"Previous text: {old_title}\nNew text: {new_title}",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    await update.message.reply_text(
        f"✅ Display text updated successfully!\n\n"
        f"🏷 New display text: {new_title}",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

async def admin_panel_set_default(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a panel as default"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    panel_id = query.data.replace("panel_set_default_", "")
    panel_manager = get_panel_manager()

    if panel_manager.set_default_panel(panel_id):
        await query.edit_message_text("✅ Panel set as default.")
    else:
        await query.edit_message_text("❌ Error setting default panel.")

async def admin_panel_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test panel connection"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    panel_id = query.data.replace("panel_test_", "")
    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await query.edit_message_text("❌ Panel not found.")
        return

    success, msg = panel_manager.test_panel_connection(
        panel.get('panel_base'),
        panel.get('username'),
        panel.get('password')
    )

    status = "✅" if success else "❌"
    await query.edit_message_text(
        f"{status} Connection Test Result\n\n"
        f"📛 Panel: {panel.get('name')}\n"
        f"🌐 Address: {panel.get('panel_base')}\n"
        f"📊 Result: {msg}",
        parse_mode=None  # Changed from Markdown to None
    )

# ============ Admin Support Address Settings ============

def _support_settings_text_and_keyboard():
    support_username = get_support_username()

    text = (
        f"☎️ Support Address Settings\n\n"
        f"👤 Current support username: {support_username}\n"
        f"🏷 Display text shown to users: «تماس با پشتیبانی» (fixed, not editable)\n\n"
        f"Use the button below to change the support username/address."
    )

    keyboard = [
        [InlineKeyboardButton("✏️ Change Support Address", callback_data="admin_support_edit")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def admin_support_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show support address settings menu"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    text, reply_markup = _support_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_support_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for the new support username"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    current = get_support_username()
    await query.edit_message_text(
        f"☎️ Change Support Address\n\n"
        f"👤 Current: {current}\n\n"
        f"Please send the new support username (with or without @, e.g. @mysupport)\n"
        f"or a full t.me link (e.g. https://t.me/mysupport).\n\n"
        f"ℹ️ Note: the display text shown to users («تماس با پشتیبانی») will NOT change,\n"
        f"only the actual link/address it points to.\n\n"
        f"⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_SUPPORT_INPUT


async def admin_support_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save the new support username"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text:
        await update.message.reply_text(
            "❌ Invalid value. Please send the support username again, or /cancel to abort."
        )
        return ADMIN_SUPPORT_INPUT

    old_username = get_support_username()
    set_support_username(text)
    new_username = get_support_username()

    # ============ لاگ تغییر آدرس پشتیبانی ============
    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Change support address",
            target_user_id=None,
            details=f"Previous address: {old_username}\nNew address: {new_username}",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    await update.message.reply_text(
        f"✅ Support address updated successfully!\n\n"
        f"👤 New support username: {new_username}\n\n"
        f"ℹ️ Display text for users remains: «تماس با پشتیبانی»",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

# ============ Admin Delete User (completely) ============

async def admin_delete_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for the user ID to delete"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "🧨 Delete User\n\n"
        "⚠️ WARNING: This will PERMANENTLY delete the user, their balance, "
        "all subscriptions and transaction history from the database.\n"
        "This action CANNOT be undone.\n\n"
        "👤 Please send the numeric ID of the user to delete:\n\n"
        "⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_DELETE_USER_ID


async def admin_delete_user_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive user id, show confirmation"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text(
            "❌ The ID must be numeric only. Please send it again:\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_DELETE_USER_ID

    target_user_id = int(text)
    target_user = db.get_user(target_user_id)

    if not target_user:
        await update.message.reply_text(
            "❌ No user found with this ID.\n\n"
            "Please send a different ID or /cancel to abort."
        )
        return ADMIN_DELETE_USER_ID

    context.user_data['admin_delete_user_target'] = target_user_id

    name = target_user['first_name'] or target_user['username'] or 'User'
    balance_str = f"{target_user['balance']:,}"
    active_subs = db.get_active_subscriptions(target_user_id)

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, delete permanently", callback_data="admin_delete_user_confirm_yes"),
            InlineKeyboardButton("❌ No, cancel", callback_data="admin_delete_user_confirm_no")
        ]
    ]

    await update.message.reply_text(
        f"⚠️ Are you sure you want to PERMANENTLY delete this user?\n\n"
        f"🔰 ID: <code>{target_user_id}</code>\n"
        f"👤 Name: {html_lib.escape(name)}\n"
        f"💰 Balance: {balance_str} Toman\n"
        f"📊 Active subscriptions: {len(active_subs)}\n\n"
        f"❗️ This will also delete their panel client(s) and cannot be undone.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_DELETE_USER_CONFIRM


async def admin_delete_user_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perform the deletion after confirmation"""
    query = update.callback_query
    await query.answer()

    target_user_id = context.user_data.get('admin_delete_user_target')

    if query.data == "admin_delete_user_confirm_no" or not target_user_id:
        await query.edit_message_text("❌ Operation cancelled.")
        context.user_data.pop('admin_delete_user_target', None)
        return ConversationHandler.END

    # ============ حذف کلاینت‌های پنل قبل از حذف کاربر ============
    subscriptions = db.get_user_subscriptions(target_user_id)
    panel_delete_errors = 0
    for sub in subscriptions:
        if sub.get('email'):
            try:
                from client_manager import get_panel_client
                panel_client = get_panel_client(sub.get('panel_id')) if sub.get('panel_id') else get_panel_client()
                panel_client.delete_client(sub['email'])
            except Exception as e:
                panel_delete_errors += 1
                logger.error(f"Error deleting panel client for {sub.get('email')}: {e}")

    success = db.delete_user(target_user_id)

    if success:
        # ============ لاگ حذف کاربر ============
        try:
            from logger_bot import log_admin_action
            admin = query.from_user
            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="Completely delete user",
                target_user_id=target_user_id,
                details=f"User <code>{target_user_id}</code> was completely deleted.\n"
                        f"Panel client deletion errors: {panel_delete_errors}",
                username=admin.username,
                first_name=admin.first_name,
                last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        extra_note = f"\n\n⚠️ {panel_delete_errors} panel client(s) could not be deleted, please check manually." if panel_delete_errors else ""
        await query.edit_message_text(
            f"✅ User <code>{target_user_id}</code> has been permanently deleted.{extra_note}",
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text("❌ Error deleting user. Please check logs.")

    context.user_data.pop('admin_delete_user_target', None)
    return ConversationHandler.END

# ============ Admin Reset User Wallet ============

async def admin_reset_balance_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for the user ID whose balance should be reset"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "♻️ Reset User Wallet\n\n"
        "⚠️ This will set the user's wallet balance to 0.\n"
        "Subscriptions and history will NOT be affected.\n\n"
        "👤 Please send the numeric ID of the target user:\n\n"
        "⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_RESET_BALANCE_ID


async def admin_reset_balance_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive user id, show confirmation"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text(
            "❌ The ID must be numeric only. Please send it again:\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_RESET_BALANCE_ID

    target_user_id = int(text)
    target_user = db.get_user(target_user_id)

    if not target_user:
        await update.message.reply_text(
            "❌ No user found with this ID.\n\n"
            "Please send a different ID or /cancel to abort."
        )
        return ADMIN_RESET_BALANCE_ID

    context.user_data['admin_reset_balance_target'] = target_user_id

    name = target_user['first_name'] or target_user['username'] or 'User'
    balance_str = f"{target_user['balance']:,}"

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, reset to 0", callback_data="admin_reset_balance_confirm_yes"),
            InlineKeyboardButton("❌ No, cancel", callback_data="admin_reset_balance_confirm_no")
        ]
    ]

    await update.message.reply_text(
        f"⚠️ Are you sure you want to reset this user's wallet to 0?\n\n"
        f"🔰 ID: <code>{target_user_id}</code>\n"
        f"👤 Name: {html_lib.escape(name)}\n"
        f"💰 Current balance: {balance_str} Toman",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_RESET_BALANCE_CONFIRM


async def admin_reset_balance_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perform the reset after confirmation"""
    query = update.callback_query
    await query.answer()

    target_user_id = context.user_data.get('admin_reset_balance_target')

    if query.data == "admin_reset_balance_confirm_no" or not target_user_id:
        await query.edit_message_text("❌ Operation cancelled.")
        context.user_data.pop('admin_reset_balance_target', None)
        return ConversationHandler.END

    old_user = db.get_user(target_user_id)
    old_balance = old_user['balance'] if old_user else 0

    success = db.reset_balance(target_user_id)

    if success:
        db.add_transaction(
            target_user_id, -old_balance, "admin_reset",
            f"Wallet reset to 0 by admin ({query.from_user.id})"
        )

        # ============ لاگ ریست کیف پول ============
        try:
            from logger_bot import log_admin_action
            admin = query.from_user
            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="Reset user wallet",
                target_user_id=target_user_id,
                details=f"Previous balance: {old_balance:,} Toman\nNew balance: 0 Toman",
                username=admin.username,
                first_name=admin.first_name,
                last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        await query.edit_message_text(
            f"✅ Wallet balance for user <code>{target_user_id}</code> has been reset to 0.\n\n"
            f"💰 Previous balance: {old_balance:,} Toman",
            parse_mode='HTML'
        )

        # اطلاع به خود کاربر
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="⚠️ موجودی کیف پول شما توسط پشتیبانی صفر شد."
            )
        except Exception as e:
            logger.error(f"Could not notify user {target_user_id}: {e}")
    else:
        await query.edit_message_text("❌ Error resetting balance. Please check logs.")

    context.user_data.pop('admin_reset_balance_target', None)
    return ConversationHandler.END

# ============ Admin Gift & Bonus Settings ============

def _bonus_settings_text_and_keyboard():
    signup = get_signup_bonus()
    inviter = get_referral_bonus_inviter()
    invitee = get_referral_bonus_invitee()

    text = (
        f"🎁 Gift & Bonus Settings\n\n"
        f"🎉 Signup bonus (new user): {signup:,} Toman\n"
        f"👥 Referral bonus - Inviter: {inviter:,} Toman\n"
        f"👥 Referral bonus - Invitee: {invitee:,} Toman\n\n"
        f"Use the buttons below to change each amount."
    )
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Signup Bonus", callback_data="admin_bonus_edit_signup")],
        [InlineKeyboardButton("✏️ Edit Inviter Bonus", callback_data="admin_bonus_edit_inviter")],
        [InlineKeyboardButton("✏️ Edit Invitee Bonus", callback_data="admin_bonus_edit_invitee")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back_to_main_menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def admin_bonus_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show gift & bonus settings menu"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    text, reply_markup = _bonus_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


_BONUS_FIELD_LABELS = {
    'signup': "Signup Bonus",
    'inviter': "Referral Bonus (Inviter)",
    'invitee': "Referral Bonus (Invitee)",
}


async def admin_bonus_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for the new value of a specific bonus field"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    data = query.data
    if data == "admin_bonus_edit_signup":
        field = 'signup'
        current = get_signup_bonus()
    elif data == "admin_bonus_edit_inviter":
        field = 'inviter'
        current = get_referral_bonus_inviter()
    elif data == "admin_bonus_edit_invitee":
        field = 'invitee'
        current = get_referral_bonus_invitee()
    else:
        await query.answer("❌ Invalid data!", show_alert=True)
        return ConversationHandler.END

    context.user_data['admin_bonus_field'] = field
    label = _BONUS_FIELD_LABELS[field]

    await query.edit_message_text(
        f"✏️ Edit {label}\n\n"
        f"💰 Current value: {current:,} Toman\n\n"
        f"Please send the new amount (integer, Toman):\n"
        f"Example: 30000\n\n"
        f"⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_BONUS_INPUT


async def admin_bonus_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save the new bonus amount"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        context.user_data.pop('admin_bonus_field', None)
        return ConversationHandler.END

    field = context.user_data.get('admin_bonus_field')
    if not field:
        await update.message.reply_text("❌ Error! Please try again.", reply_markup=get_main_menu())
        return ConversationHandler.END

    try:
        amount = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid integer.\nExample: 30000\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_BONUS_INPUT

    if amount < 0:
        await update.message.reply_text(
            "❌ The amount cannot be negative. Please enter it again:"
        )
        return ADMIN_BONUS_INPUT

    if field == 'signup':
        old_value = get_signup_bonus()
        set_signup_bonus(amount)
    elif field == 'inviter':
        old_value = get_referral_bonus_inviter()
        set_referral_bonus_inviter(amount)
    else:  # invitee
        old_value = get_referral_bonus_invitee()
        set_referral_bonus_invitee(amount)

    label = _BONUS_FIELD_LABELS[field]

    # ============ لاگ تغییر مقدار جایزه ============
    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action=f"Change {label}",
            target_user_id=None,
            details=f"Previous value: {old_value:,} Toman\nNew value: {amount:,} Toman",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    await update.message.reply_text(
        f"✅ {label} updated successfully!\n\n"
        f"💰 New value: {amount:,} Toman",
        reply_markup=get_main_menu()
    )
    context.user_data.pop('admin_bonus_field', None)
    return ConversationHandler.END

# ============ Admin Commission-based Panel Access ============

def _commission_settings_text_and_keyboard():
    panel_manager = get_panel_manager()
    panel_id = get_special_panel_id()
    percent = get_special_panel_commission_percent()

    panel_name = "❌ Not Set"
    if panel_id:
        panel = panel_manager.get_panel(panel_id)
        if panel:
            status = "✅" if panel.get('enabled', True) else "❌ (Disabled)"
            panel_name = f"{panel.get('name')} {status}"
        else:
            panel_name = "⚠️ Panel Deleted - Please Select Again"

    text = (
        f"🎯 Commission-Based Panel Access\n\n"
        f"If a user's total commission (referral reward) reaches at least "
        f"{percent}% of the purchased plan price, their client will be created "
        f"on the dedicated panel below instead of the default panel:\n\n"
        f"🖥 Dedicated Panel: {panel_name}\n"
        f"📊 Threshold Percent: {percent}%"
    )

    keyboard = [
        [InlineKeyboardButton("🖥 Select/Change Panel", callback_data="admin_commission_select_panel")],
        [InlineKeyboardButton("✏️ Edit Threshold Percent", callback_data="admin_commission_edit_percent")],
    ]
    if panel_id:
        keyboard.append([InlineKeyboardButton("❌ Disable", callback_data="admin_commission_disable")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="panel_manage")])

    return text, InlineKeyboardMarkup(keyboard)


async def admin_commission_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return
    text, reply_markup = _commission_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_commission_select_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    panel_manager = get_panel_manager()
    panels = panel_manager.get_all_panels()
    current = get_special_panel_id()

    keyboard = []
    for pid, panel in panels.items():
        mark = "✅ " if pid == current else ""
        status = "✅" if panel.get('enabled', True) else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{mark}{status} {panel.get('name')}",
                callback_data=f"admin_commission_set_panel_{pid}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_commission_settings")])

    await query.edit_message_text(
        "🖥 Please select the panel for commission-based access:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None
    )


async def admin_commission_set_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    panel_id = query.data.replace("admin_commission_set_panel_", "")
    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await query.answer("❌ Panel not found.", show_alert=True)
        return

    old_panel_id = get_special_panel_id()
    set_special_panel_id(panel_id)

    try:
        from logger_bot import log_admin_action
        admin = query.from_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Set Commission Dedicated Panel",
            target_user_id=None,
            details=f"Previous Panel: {old_panel_id}\nNew Panel: {panel.get('name')} (`{panel_id}`)",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    text, reply_markup = _commission_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_commission_disable(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    set_special_panel_id(None)

    try:
        from logger_bot import log_admin_action
        admin = query.from_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Disable Commission Dedicated Panel",
            target_user_id=None,
            details="Commission-based panel access has been disabled.",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    text, reply_markup = _commission_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_commission_edit_percent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    current = get_special_panel_commission_percent()
    await query.edit_message_text(
        f"✏️ Edit Commission Threshold Percent\n\n"
        f"📊 Current Percent: {current}%\n\n"
        f"Please send the new percentage as an integer between 1 and 100:\n"
        f"Example: 50\n\n"
        f"⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_COMMISSION_PERCENT_INPUT


async def admin_commission_edit_percent_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    try:
        percent = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid integer between 1 and 100.\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_COMMISSION_PERCENT_INPUT

    if percent < 1 or percent > 100:
        await update.message.reply_text(
            "❌ Percent must be between 1 and 100. Please try again:\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_COMMISSION_PERCENT_INPUT

    old_value = get_special_panel_commission_percent()
    set_special_panel_commission_percent(percent)

    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Change Commission Panel Threshold Percent",
            target_user_id=None,
            details=f"Previous: {old_value}%\nNew: {percent}%",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    await update.message.reply_text(
        f"✅ Threshold percent successfully changed to {percent}%.",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

# ============ Admin Payment Settings (Hybrid Wallet+Card) ============
def _payment_settings_text_and_keyboard():
    enabled = is_hybrid_payment_enabled()
    status_text = "✅ Enabled" if enabled else "❌ Disabled"

    card_number = get_card_number()
    card_holder = get_card_holder()
    card_bank = get_card_bank()

    text = (
        f"💳 Payment Settings\n\n"
        f"🔀 Hybrid Payment (auto wallet deduction before card-to-card): {status_text}\n\n"
        f"When enabled: if a user selects card-to-card payment (for a plan purchase or "
        f"extra volume) and has a wallet balance, that balance is automatically deducted "
        f"first, and the user only needs to pay the remaining amount via card-to-card.\n"
        f"If the wallet balance fully covers the price, no card payment is required at all.\n\n"
        f"🏦 Card-to-card info shown to users:\n"
        f"🔢 Card number: {card_number}\n"
        f"👤 Card holder: {card_holder}\n"
        f"🏦 Bank: {card_bank}"
    )

    keyboard = [
        [InlineKeyboardButton(
            "🔴 Disable Hybrid Payment" if enabled else "🟢 Enable Hybrid Payment",
            callback_data="admin_hybrid_payment_toggle"
        )],
        [InlineKeyboardButton("✏️ Edit Card Info", callback_data="admin_card_info_edit")],   # <-- جدید
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back_to_main_menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def admin_payment_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show payment settings menu"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    text, reply_markup = _payment_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_hybrid_payment_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle hybrid payment on/off"""
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer("⛔️ No access.", show_alert=True)
        return

    new_value = not is_hybrid_payment_enabled()
    set_hybrid_payment_enabled(new_value)
    await query.answer("✅ Status updated.")

    try:
        from logger_bot import log_admin_action
        admin = query.from_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Toggle Hybrid Payment",
            target_user_id=None,
            details=f"New status: {'Enabled' if new_value else 'Disabled'}",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    text, reply_markup = _payment_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)

# ============ Admin Edit Card Payment Info ============
async def admin_card_info_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask admin for new card payment info (3 lines: number, holder, bank)"""
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    current_number = get_card_number()
    current_holder = get_card_holder()
    current_bank = get_card_bank()

    await query.edit_message_text(
        "✏️ Edit Card Payment Info\n\n"
        f"🔢 Current card number: {current_number}\n"
        f"👤 Current card holder: {current_holder}\n"
        f"🏦 Current bank: {current_bank}\n\n"
        "Please send the new info in 3 lines, in this exact order:\n\n"
        "1️⃣ Card number (digits only, e.g. 6219861065685272)\n"
        "2️⃣ Card holder name (e.g. وحید صابر)\n"
        "3️⃣ Bank name (e.g. سامان)\n\n"
        "⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_CARD_INFO_INPUT


async def admin_card_info_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save new card info"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) < 3:
        await update.message.reply_text(
            "❌ Please send all 3 values, one per line:\n\n"
            "1️⃣ Card number\n"
            "2️⃣ Card holder name\n"
            "3️⃣ Bank name\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_CARD_INFO_INPUT

    new_number, new_holder, new_bank = lines[0], lines[1], lines[2]

    if not new_number.isdigit():
        await update.message.reply_text(
            "❌ Card number must be numeric only. Please send the info again:\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_CARD_INFO_INPUT

    old_number = get_card_number()
    old_holder = get_card_holder()
    old_bank = get_card_bank()

    set_card_number(new_number)
    set_card_holder(new_holder)
    set_card_bank(new_bank)

    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Change card payment info",
            target_user_id=None,
            details=(
                f"Previous card number: {old_number}\nNew card number: {new_number}\n"
                f"Previous holder: {old_holder}\nNew holder: {new_holder}\n"
                f"Previous bank: {old_bank}\nNew bank: {new_bank}"
            ),
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    await update.message.reply_text(
        f"✅ Card payment info updated successfully!\n\n"
        f"🔢 New card number: {new_number}\n"
        f"👤 New card holder: {new_holder}\n"
        f"🏦 New bank: {new_bank}",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

def _emergency_proxy_text_and_keyboard():
    from bot_settings import get_emergency_proxy_links
    proxies = get_emergency_proxy_links()

    if proxies:
        lines = [f"{i+1}. {p.get('name', 'Unnamed')}" for i, p in enumerate(proxies)]
        current = "\n".join(lines)
    else:
        current = "❌ No proxy registered."

    text = (
        f"🌐 Proxy Management\n\n"   # قبلاً: "🌐 Emergency Proxy Management"
        f"Current proxies:\n{current}\n\n"
        f"Click the button below to delete each one."
    )

    keyboard = []
    for i, p in enumerate(proxies):
        keyboard.append([
            InlineKeyboardButton(
                f"🗑 Delete #{i+1} - {p.get('name', f'Proxy {i+1}')}", 
                callback_data=f"admin_emergency_proxy_del_{i}"
            )
        ])
    keyboard.append([InlineKeyboardButton("➕ Add New Proxy", callback_data="admin_emergency_proxy_add")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_emergency_settings")])

    return text, InlineKeyboardMarkup(keyboard)

# ============ Admin: Emergency Plan Default Volume/Duration ============
def _emergency_plan_defaults_text_and_keyboard():
    from bot_settings import get_emergency_plan_volume_gb, get_emergency_plan_duration_days
    volume = get_emergency_plan_volume_gb()
    duration = get_emergency_plan_duration_days()
    text = (
        f"⚙️ Emergency Plan Default Settings\n\n"
        f"📊 Default volume for new configs: {'Unlimited' if volume == 0 else f'{volume} GB'}\n"
        f"⏰ Default validity duration: {duration} days\n\n"
        f"⚠️ Emergency subscriptions are automatically removed from both the database "
        f"and the panel once this duration ends."
    )
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Volume", callback_data="admin_emergency_edit_volume")],
        [InlineKeyboardButton("✏️ Edit Duration", callback_data="admin_emergency_edit_duration")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_emergency_settings")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

async def admin_emergency_plan_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return
    text, reply_markup = _emergency_plan_defaults_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)

async def admin_emergency_edit_volume_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    from bot_settings import get_emergency_plan_volume_gb
    current = get_emergency_plan_volume_gb()
    await query.edit_message_text(
        f"✏️ Edit Emergency Plan Default Volume\n\n"
        f"📊 Current value: {'Unlimited' if current == 0 else f'{current} GB'}\n\n"
        f"Please enter the new value in GB (enter 0 for unlimited):\n\n"
        f"⚠️ Send /cancel to abort."
    )
    return ADMIN_EMERGENCY_VOLUME_INPUT

async def admin_emergency_edit_volume_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    try:
        volume = int(text)
        if volume < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid integer (enter 0 for unlimited):"
        )
        return ADMIN_EMERGENCY_VOLUME_INPUT

    from bot_settings import get_emergency_plan_volume_gb, set_emergency_plan_volume_gb
    old_value = get_emergency_plan_volume_gb()
    set_emergency_plan_volume_gb(volume)

    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot, admin_id=admin.id, action="Change emergency plan default volume",
            target_user_id=None,
            details=f"Previous value: {old_value} GB\nNew value: {volume} GB",
            username=admin.username, first_name=admin.first_name, last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    await update.message.reply_text(
        f"✅ Emergency plan default volume changed to {'Unlimited' if volume == 0 else f'{volume} GB'}.",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

async def admin_emergency_edit_duration_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    from bot_settings import get_emergency_plan_duration_days
    current = get_emergency_plan_duration_days()
    await query.edit_message_text(
        f"✏️ Edit Emergency Plan Default Duration\n\n"
        f"⏰ Current value: {current} days\n\n"
        f"Please enter the new value in days:\n\n"
        f"⚠️ Send /cancel to abort."
    )
    return ADMIN_EMERGENCY_DURATION_INPUT


async def admin_emergency_edit_duration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    try:
        duration = int(text)
        if duration < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid integer of at least 1:")
        return ADMIN_EMERGENCY_DURATION_INPUT

    from bot_settings import get_emergency_plan_duration_days, set_emergency_plan_duration_days
    old_value = get_emergency_plan_duration_days()
    set_emergency_plan_duration_days(duration)

    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot, admin_id=admin.id, action="Change emergency plan default duration",
            target_user_id=None,
            details=f"Previous value: {old_value} days\nNew value: {duration} days",
            username=admin.username, first_name=admin.first_name, last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    await update.message.reply_text(
        f"✅ Emergency plan default duration changed to {duration} days.",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

async def admin_emergency_proxy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return
    text, reply_markup = _emergency_proxy_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_emergency_proxy_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a proxy from the list"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    from bot_settings import get_emergency_proxy_links, set_emergency_proxy_links
    idx = int(query.data.replace("admin_emergency_proxy_del_", ""))
    proxies = get_emergency_proxy_links()

    if idx >= len(proxies):
        await query.answer("❌ This proxy no longer exists.", show_alert=True)
    else:
        removed = proxies.pop(idx)
        set_emergency_proxy_links(proxies)

        try:
            from logger_bot import log_admin_action
            admin = query.from_user
            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="Delete Emergency Proxy",
                target_user_id=None,
                details=f"Removed proxy: {removed.get('name', '')}",
                username=admin.username,
                first_name=admin.first_name,
                last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        await query.answer("✅ Deleted successfully.")

    text, reply_markup = _emergency_proxy_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_emergency_proxy_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the process of adding a proxy - Step 1: Get display name"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "➕ Add New Proxy\n\n"
        "Please enter the display name for the proxy:\n"
        "Example: Proxy🇧🇬\n\n"
        "⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_EMERGENCY_PROXY_NAME_INPUT


async def admin_emergency_proxy_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive display name, then ask for link"""
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text:
        await update.message.reply_text(
            "❌ Name cannot be empty. Please enter it again:\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_EMERGENCY_PROXY_NAME_INPUT

    context.user_data['admin_new_proxy_name'] = text

    await update.message.reply_text(
        f"✅ Name saved: {text}\n\n"
        f"Now please enter the proxy link:\n"
        f"Example:\n"
        f"tg://proxy?server=45.137.201.233&port=808&secret=...\n\n"
        f"⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_EMERGENCY_PROXY_LINK_INPUT


async def admin_emergency_proxy_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive link and save the proxy"""
    text = update.message.text.strip()
    if text == "/cancel":
        context.user_data.pop('admin_new_proxy_name', None)
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text:
        await update.message.reply_text(
            "❌ Link cannot be empty. Please enter it again:\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_EMERGENCY_PROXY_LINK_INPUT

    name = context.user_data.get('admin_new_proxy_name', 'Proxy')

    from bot_settings import get_emergency_proxy_links, set_emergency_proxy_links
    proxies = get_emergency_proxy_links()
    proxies.append({'name': name, 'link': text})
    set_emergency_proxy_links(proxies)

    try:
        from logger_bot import log_admin_action
        admin = update.effective_user
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Add Emergency Proxy",
            target_user_id=None,
            details=f"Name: {name}\nLink: {text}",
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    context.user_data.pop('admin_new_proxy_name', None)

    await update.message.reply_text(
        f"✅ Proxy «{name}» added successfully!",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

def _emergency_settings_text_and_keyboard():
    pending_count = len(db.list_emergency_access('pending'))
    approved_count = len(db.list_emergency_access('approved'))
    text = (
        f"🆘 Emergency Plan Management\n\n"
        f"⏳ Pending requests: {pending_count}\n"
        f"✅ Users with access: {approved_count}"
    )
    keyboard = [
        [InlineKeyboardButton("⚙️ Default Settings (Volume/Duration)", callback_data="admin_emergency_plan_settings")],
        [InlineKeyboardButton("🌐 Proxy Management", callback_data="admin_emergency_proxy_settings")],
        [InlineKeyboardButton(f"⏳ Pending Requests ({pending_count})", callback_data="admin_emergency_pending")],
        [InlineKeyboardButton("👥 User Access Management", callback_data="admin_emergency_users_menu")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back_to_main_menu")]
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def admin_emergency_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return
    text, reply_markup = _emergency_settings_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_emergency_pending_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    pending = db.list_emergency_access('pending')
    if not pending:
        await query.edit_message_text(
            "✅ No pending requests.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_emergency_settings")]])
        )
        return

    keyboard = []
    for row in pending:
        name = row.get('first_name') or row.get('username') or str(row['user_id'])
        keyboard.append([InlineKeyboardButton(f"👤 {name} ({row['user_id']})", callback_data=f"admin_emergency_review_{row['user_id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_emergency_settings")])

    await query.edit_message_text(
        f"⏳ {len(pending)} pending request(s):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None
    )

async def admin_emergency_review_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    target_user_id = int(query.data.replace("admin_emergency_review_", ""))
    user = db.get_user(target_user_id)
    name = (user.get('first_name') or user.get('username') or str(target_user_id)) if user else str(target_user_id)

    keyboard = [
        [InlineKeyboardButton("🔧 Config Only", callback_data=f"admin_emergency_grant_config_{target_user_id}")],
        [InlineKeyboardButton("🌐 Proxy Only", callback_data=f"admin_emergency_grant_proxy_{target_user_id}")],
        [InlineKeyboardButton("✅ Both", callback_data=f"admin_emergency_grant_both_{target_user_id}")],
        [InlineKeyboardButton("❌ Deny", callback_data=f"admin_emergency_deny_{target_user_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_emergency_pending")]
    ]
    await query.edit_message_text(
        f"👤 User: {html_lib.escape(str(name))} (`{target_user_id}`)\n\nPlease select the access type:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None
    )

async def admin_emergency_grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shared logic for granting access from both the pending-alert flow and User Access Management"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    data = query.data
    if data.startswith("admin_emergency_grant_config_"):
        target_user_id = int(data.replace("admin_emergency_grant_config_", ""))
        access_type = "config"
    elif data.startswith("admin_emergency_grant_proxy_"):
        target_user_id = int(data.replace("admin_emergency_grant_proxy_", ""))
        access_type = "proxy"
    else:
        target_user_id = int(data.replace("admin_emergency_grant_both_", ""))
        access_type = "both"

    admin = query.from_user
    db.set_emergency_access(target_user_id, access_type, admin_id=admin.id)

    # English labels for admin-facing log/reply
    type_labels_en = {"config": "🔧 Config Only", "proxy": "🌐 Proxy Only", "both": "✅ Config & Proxy"}
    # Persian labels for the message sent to the end user
    type_labels_fa = {"config": "🔧 فقط کانفیگ", "proxy": "🌐 فقط پروکسی", "both": "✅ کانفیگ و پروکسی"}

    try:
        from logger_bot import log_admin_action
        await log_admin_action(
            context.bot, admin_id=admin.id, action="Approve emergency plan access",
            target_user_id=target_user_id,
            details=f"Access type: {type_labels_en[access_type]}",
            username=admin.username, first_name=admin.first_name, last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=(
                f"✅ درخواست شما برای طرح اضطراری تایید شد!\n\n"
                f"📋 نوع دسترسی: {type_labels_fa[access_type]}\n\n"
                f"اکنون می‌توانید از دکمه 🆘 طرح اضطراری استفاده کنید."
            )
        )
    except Exception as e:
        logger.error(f"Could not notify user {target_user_id}: {e}")

    try:
        import lifeline
        await lifeline.post_or_update_lifeline(context.bot)
    except Exception as e:
        logger.error(f"Error refreshing lifeline after emergency grant: {e}")

    await query.edit_message_text(f"✅ Access granted: {type_labels_en[access_type]} — user {target_user_id}")

async def admin_emergency_deny_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start denying a request - ask the admin for a reason"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    target_user_id = int(query.data.replace("admin_emergency_deny_", ""))
    context.user_data['admin_emergency_deny_target'] = target_user_id

    await query.message.reply_text(
        "❌ Deny Emergency Plan Request\n\n"
        "Please write the reason for denial (this will be sent to the user):\n\n"
        "To deny without a reason, just send a - character.\n"
        "⚠️ Send /cancel to abort."
    )
    return ADMIN_EMERGENCY_DENY_REASON

async def admin_emergency_deny_reason_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive the reason and perform the denial"""
    text = update.message.text.strip()

    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        context.user_data.pop('admin_emergency_deny_target', None)
        return ConversationHandler.END

    target_user_id = context.user_data.get('admin_emergency_deny_target')
    if not target_user_id:
        await update.message.reply_text("❌ Error! Please try again.", reply_markup=get_main_menu())
        return ConversationHandler.END

    reason = None if text == "-" else text
    admin = update.effective_user

    db.reject_emergency_access(target_user_id, admin_id=admin.id)

    try:
        from logger_bot import log_admin_action
        await log_admin_action(
            context.bot, admin_id=admin.id, action="Deny emergency plan request",
            target_user_id=target_user_id,
            details=f"Reason: {reason}" if reason else "No reason given",
            username=admin.username, first_name=admin.first_name, last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    user_message = "❌ درخواست شما برای طرح اضطراری رد شد."
    if reason:
        user_message += f"\n\n📝 دلیل: {reason}"
    user_message += "\nبرای اطلاعات بیشتر با پشتیبانی تماس بگیرید."

    try:
        await context.bot.send_message(chat_id=target_user_id, text=user_message)
    except Exception as e:
        logger.error(f"Could not notify user {target_user_id}: {e}")

    await update.message.reply_text(
        f"❌ Request denied for user {target_user_id}" + (f"\n📝 Reason: {reason}" if reason else "")
    )

    context.user_data.pop('admin_emergency_deny_target', None)
    return ConversationHandler.END

async def admin_emergency_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    users = db.list_emergency_access('approved')
    type_icons = {"config": "🔧", "proxy": "🌐", "both": "✅"}
    keyboard = []
    for row in users[:50]:
        name = row.get('first_name') or row.get('username') or str(row['user_id'])
        icon = type_icons.get(row.get('access_type'), "❔")
        keyboard.append([InlineKeyboardButton(
            f"{icon} {name} ({row['user_id']})",
            callback_data=f"admin_emergency_manage_{row['user_id']}"
        )])
    keyboard.append([InlineKeyboardButton("➕ Add User Manually", callback_data="admin_emergency_add_user")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_emergency_settings")])

    text = f"👥 {len(users)} user(s) with emergency access." if users else "👥 No users currently have emergency access."
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=None)

async def admin_emergency_manage_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    target_user_id = int(query.data.replace("admin_emergency_manage_", ""))
    keyboard = [
        [InlineKeyboardButton("🔧 Config Only", callback_data=f"admin_emergency_grant_config_{target_user_id}")],
        [InlineKeyboardButton("🌐 Proxy Only", callback_data=f"admin_emergency_grant_proxy_{target_user_id}")],
        [InlineKeyboardButton("✅ Both", callback_data=f"admin_emergency_grant_both_{target_user_id}")],
        [InlineKeyboardButton("🗑 Remove Access", callback_data=f"admin_emergency_revoke_{target_user_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_emergency_users_menu")]
    ]
    await query.edit_message_text(
        f"👤 User: `{target_user_id}`\n\nPlease select an option:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None
    )

async def admin_emergency_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    target_user_id = int(query.data.replace("admin_emergency_revoke_", ""))
    db.remove_emergency_access(target_user_id)

    try:
        from logger_bot import log_admin_action
        admin = query.from_user
        await log_admin_action(
            context.bot, admin_id=admin.id, action="Remove emergency plan access",
            target_user_id=target_user_id, details="",
            username=admin.username, first_name=admin.first_name, last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text="⚠️ دسترسی شما به طرح اضطراری توسط پشتیبانی حذف شد."
        )
    except Exception as e:
        logger.error(f"Could not notify user {target_user_id}: {e}")

    await admin_emergency_users_menu(update, context)


async def admin_emergency_add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "➕ Add User to Emergency Plan\n\nPlease send the user's numeric ID:\n\n⚠️ Send /cancel to abort.",
        parse_mode=None
    )
    return ADMIN_EMERGENCY_ADD_USER_ID


async def admin_emergency_add_user_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text("❌ The ID must be numeric only. Please send it again:\n\n⚠️ Send /cancel to abort.")
        return ADMIN_EMERGENCY_ADD_USER_ID

    target_user_id = int(text)
    keyboard = [
        [InlineKeyboardButton("🔧 Config Only", callback_data=f"admin_emergency_grant_config_{target_user_id}")],
        [InlineKeyboardButton("🌐 Proxy Only", callback_data=f"admin_emergency_grant_proxy_{target_user_id}")],
        [InlineKeyboardButton("✅ Both", callback_data=f"admin_emergency_grant_both_{target_user_id}")],
    ]
    await update.message.reply_text(
        f"👤 User ID: {target_user_id}\n\nPlease select the access type:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

# ============ Admin: Manual Subscription (plan + expiry + priority + raw config) ============

def _plan_preset_keyboard():
    keyboard = [
        [InlineKeyboardButton(v, callback_data=f"admin_manual_plan_{k}")]
        for k, v in MANUAL_PLAN_PRESETS.items()
    ]
    keyboard.append([InlineKeyboardButton("✏️ Custom Name", callback_data="admin_manual_plan_other")])
    return InlineKeyboardMarkup(keyboard)


def _priority_keyboard(prefix: str):
    keyboard = [
        [InlineKeyboardButton("🥇 First Priority (Main)", callback_data=f"{prefix}_1")],
        [InlineKeyboardButton("🥈 Second Priority", callback_data=f"{prefix}_2")],
        [InlineKeyboardButton("🥉 Third Priority", callback_data=f"{prefix}_3")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def admin_manual_sub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("👤 یک کاربر خاص", callback_data="admin_manual_target_single")],
        [InlineKeyboardButton("👥 همه کاربران", callback_data="admin_manual_target_all")],
    ]
    await query.edit_message_text(
        "➕ افزودن اشتراک دستی\n\nاین اشتراک برای چه کسانی ثبت شود؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_MANUAL_SUB_TARGET


async def admin_manual_sub_target_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    if query.data == "admin_manual_target_all":
        context.user_data['manual_sub_target'] = 'all'
        user_count = len(db.get_all_user_ids())
        await query.edit_message_text(
            f"👥 این اشتراک برای همه‌ی {user_count} کاربر ثبت خواهد شد.\n\n"
            f"📦 لطفاً طرح مورد نظر را انتخاب کنید:",
            reply_markup=_plan_preset_keyboard()
        )
        return ADMIN_MANUAL_SUB_PLAN_NAME

    await query.edit_message_text(
        "👤 لطفاً آیدی عددی کاربر مورد نظر را ارسال کنید:\n\n⚠️ برای انصراف /cancel را ارسال کنید."
    )
    return ADMIN_MANUAL_SUB_USER_ID


async def admin_manual_sub_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text(
            "❌ The ID must be numeric only. Please send it again:\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_MANUAL_SUB_USER_ID

    target_user_id = int(text)
    target_user = db.get_user(target_user_id)
    if not target_user:
        await update.message.reply_text(
            "❌ No user found with this ID.\n\n"
            "Please send a different ID or /cancel to abort."
        )
        return ADMIN_MANUAL_SUB_USER_ID

    context.user_data['manual_sub_target'] = target_user_id
    await update.message.reply_text(
        "📦 Please select the desired plan:",
        reply_markup=_plan_preset_keyboard()
    )
    return ADMIN_MANUAL_SUB_PLAN_NAME


async def admin_manual_sub_plan_name_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text:
        await update.message.reply_text("❌ Plan name cannot be empty. Please enter it again:")
        return ADMIN_MANUAL_SUB_PLAN_NAME

    context.user_data['manual_sub_plan_name'] = text
    # Custom names may be Persian/non-ASCII, so convert to a short, stable slug for the email
    context.user_data['manual_sub_plan_key'] = _slugify_plan_name(text)

    await update.message.reply_text(
        f"✅ Plan: {text}\n\n"
        f"📅 Please enter the subscription validity:\n"
        f"- either a number of days (e.g. 30)\n"
        f"- or an exact expiry date in YYYY-MM-DD format\n\n"
        f"⚠️ Send /cancel to abort."
    )
    return ADMIN_MANUAL_SUB_EXPIRY


async def admin_manual_sub_expiry_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    duration_days = None
    if text.isdigit():
        duration_days = int(text)
        if duration_days < 1:
            await update.message.reply_text("❌ The number of days must be at least 1. Please enter it again:")
            return ADMIN_MANUAL_SUB_EXPIRY
    else:
        try:
            expiry_date = datetime.strptime(text, "%Y-%m-%d")
            duration_days = (expiry_date - datetime.now()).days
            if duration_days < 1:
                await update.message.reply_text(
                    "❌ The expiry date must be in the future. Please enter it again:"
                )
                return ADMIN_MANUAL_SUB_EXPIRY
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid format.\n"
                "Enter either a number of days (e.g. 30) or a date in YYYY-MM-DD format:"
            )
            return ADMIN_MANUAL_SUB_EXPIRY

    context.user_data['manual_sub_duration'] = duration_days

    await update.message.reply_text(
        "📊 Please enter the volume for this subscription in GB:\n"
        "Example: 50\n\n"
        "⚠️ Enter 0 for unlimited.\n"
        "⚠️ Send /cancel to abort."
    )
    return ADMIN_MANUAL_SUB_VOLUME


async def admin_manual_sub_plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    data = query.data
    if data == "admin_manual_plan_other":
        await query.edit_message_text("✏️ Please type the custom plan name:")
        return ADMIN_MANUAL_SUB_PLAN_NAME

    key = data.replace("admin_manual_plan_", "")
    plan_name = MANUAL_PLAN_PRESETS.get(key, key)
    context.user_data['manual_sub_plan_name'] = plan_name
    # Preset keys (balanced, fair, pro, ...) are already ASCII-safe;
    # use the key itself as the plan identifier in the email
    context.user_data['manual_sub_plan_key'] = key

    await query.edit_message_text(
        f"✅ Plan selected: {plan_name}\n\n"
        f"📅 Please enter the subscription validity:\n"
        f"- either a number of days (e.g. 30)\n"
        f"- or an exact expiry date in YYYY-MM-DD format (e.g. 2026-08-20)\n\n"
        f"⚠️ Send /cancel to abort."
    )
    return ADMIN_MANUAL_SUB_EXPIRY


async def admin_manual_sub_volume_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive the volume (GB) for a manual subscription"""
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        for key in ('manual_sub_target', 'manual_sub_plan_name', 'manual_sub_plan_key', 'manual_sub_duration'):
            context.user_data.pop(key, None)
        return ConversationHandler.END

    try:
        volume = int(text)
        if volume < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid integer in GB (enter 0 for unlimited):"
        )
        return ADMIN_MANUAL_SUB_VOLUME

    context.user_data['manual_sub_volume'] = volume

    await update.message.reply_text(
        "🔢 Please select the priority for the config(s) you're about to enter:",
        reply_markup=_priority_keyboard("admin_manual_priority")
    )
    return ADMIN_MANUAL_SUB_PRIORITY


async def admin_manual_sub_priority_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    priority = int(query.data.replace("admin_manual_priority_", ""))
    context.user_data['manual_sub_priority'] = priority

    await query.edit_message_text(
        "🔧 Please send the config(s) for this subscription.\n"
        "You can send several configs; put each one on its own line.\n\n"
        "Example:\nvless://...\nvless://...\n\n"
        "⚠️ Send /cancel to abort."
    )
    return ADMIN_MANUAL_SUB_CONFIG


async def admin_manual_sub_config_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        for key in ('manual_sub_target', 'manual_sub_plan_name', 'manual_sub_plan_key',
                    'manual_sub_duration', 'manual_sub_priority', 'manual_sub_volume'):
            context.user_data.pop(key, None)
        return ConversationHandler.END

    links = [l.strip() for l in text.split('\n') if l.strip()]
    if not links:
        await update.message.reply_text("❌ Please enter at least one config:")
        return ADMIN_MANUAL_SUB_CONFIG

    target = context.user_data.get('manual_sub_target')
    plan_name = context.user_data.get('manual_sub_plan_name')
    plan_key = context.user_data.get('manual_sub_plan_key', 'plan')
    duration_days = context.user_data.get('manual_sub_duration', 30)
    volume = context.user_data.get('manual_sub_volume', 0)
    priority = context.user_data.get('manual_sub_priority', 1)

    if not target or not plan_name:
        await update.message.reply_text("❌ Error! Please try again.", reply_markup=get_main_menu())
        return ConversationHandler.END

    admin = update.effective_user

    if target == 'all':
        user_ids = db.get_all_user_ids()
        success_count = 0
        fail_count = 0
        for uid in user_ids:
            email = f"manual_{uid}_{plan_key}"
            subscription_id = db.add_subscription(
                user_id=uid, protocol='v2ray', duration_days=duration_days,
                plan_type='manual', initial_volume=volume, plan_name=plan_name,
                email=email, panel_id=None
            )
            if not subscription_id:
                fail_count += 1
                continue
            for link in links:
                db.add_manual_config(subscription_id, link, priority)
            success_count += 1
            try:
                await context.bot.send_message(
                    chat_id=uid,
                    text=(
                        f"🎉 یک اشتراک جدید برای شما توسط پشتیبانی ثبت شد!\n\n"
                        f"📦 طرح: {plan_name}\n"
                        f"⏰ مدت: {duration_days} روز\n"
                        f"📊 حجم: {'نامحدود' if volume == 0 else f'{volume} گیگ'}\n\n"
                        f"برای دریافت کانفیگ به بخش «📒 اشتراک ها» مراجعه کنید."
                    )
                )
            except Exception as e:
                logger.error(f"Could not notify user {uid}: {e}")
            await asyncio.sleep(0.05)

        try:
            from logger_bot import log_admin_action
            await log_admin_action(
                context.bot, admin_id=admin.id, action="Add manual subscription to ALL users",
                target_user_id=None,
                details=(
                    f"📦 Plan: {plan_name}\n⏰ Duration: {duration_days} days\n"
                    f"🔢 Priority: {priority}\n🔗 Config count: {len(links)}\n"
                    f"👥 Users affected: {success_count} (failed: {fail_count})"
                ),
                username=admin.username, first_name=admin.first_name, last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        await update.message.reply_text(
            f"✅ اشتراک برای {success_count} کاربر با موفقیت ثبت شد."
            + (f"\n⚠️ {fail_count} مورد با خطا مواجه شد." if fail_count else ""),
            reply_markup=get_main_menu()
        )

    else:
        target_user_id = target
        email = f"manual_{target_user_id}_{plan_key}"
        subscription_id = db.add_subscription(
            user_id=target_user_id, protocol='v2ray', duration_days=duration_days,
            plan_type='manual', initial_volume=volume, plan_name=plan_name,
            email=email, panel_id=None
        )
        if not subscription_id:
            await update.message.reply_text("❌ Error registering subscription. Please try again.", reply_markup=get_main_menu())
            return ConversationHandler.END

        for link in links:
            db.add_manual_config(subscription_id, link, priority)

        try:
            from logger_bot import log_admin_action
            await log_admin_action(
                context.bot, admin_id=admin.id, action="Add manual subscription",
                target_user_id=target_user_id,
                details=(
                    f"📦 Plan: {plan_name}\n⏰ Duration: {duration_days} days\n"
                    f"🔢 Priority: {priority}\n🔗 Config count: {len(links)}"
                ),
                username=admin.username, first_name=admin.first_name, last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        await update.message.reply_text(
            f"✅ Manual subscription registered successfully!\n\n"
            f"👤 User: <code>{target_user_id}</code>\n"
            f"📦 Plan: {plan_name}\n"
            f"⏰ Duration: {duration_days} days\n"
            f"📊 Volume: {'Unlimited' if volume == 0 else f'{volume} GB'}\n"
            f"🔢 Priority: {priority}\n"
            f"🔢 Config count: {len(links)}",
            parse_mode='HTML',
            reply_markup=get_main_menu()
        )

        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎉 یک اشتراک جدید برای شما توسط پشتیبانی ثبت شد!\n\n"
                    f"📦 طرح: {plan_name}\n"
                    f"⏰ مدت: {duration_days} روز\n"
                    f"📊 حجم: {'نامحدود' if volume == 0 else f'{volume} گیگ'}\n\n"
                    f"برای دریافت کانفیگ به بخش «📒 اشتراک ها» مراجعه کنید."
                )
            )
        except Exception as e:
            logger.error(f"Could not notify user {target_user_id}: {e}")

    for key in ('manual_sub_target', 'manual_sub_plan_name', 'manual_sub_plan_key',
                'manual_sub_duration', 'manual_sub_priority', 'manual_sub_volume'):
        context.user_data.pop(key, None)

    return ConversationHandler.END

# ============ Admin: Add Config to Existing Subscription ============
async def admin_addconfig_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("👤 یک کاربر خاص", callback_data="admin_addconfig_target_single")],
        [InlineKeyboardButton("🧩 همه کاربران یک طرح خاص", callback_data="admin_addconfig_target_byplan")],
    ]
    await query.edit_message_text(
        "➕ افزودن کانفیگ به اشتراک\n\nاین کانفیگ برای چه کسانی اضافه شود؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_ADDCONFIG_TARGET


async def admin_addconfig_target_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    if query.data == "admin_addconfig_target_single":
        await query.edit_message_text(
            "👤 Please send the target user's numeric ID:\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_ADDCONFIG_USER_ID

    plan_names = db.get_all_active_plan_names()
    if not plan_names:
        await query.edit_message_text("❌ هیچ اشتراک فعالی با نام طرح مشخص یافت نشد.")
        return ConversationHandler.END

    context.user_data['addconfig_plan_names'] = plan_names
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"admin_addconfig_planidx_{i}")]
        for i, name in enumerate(plan_names)
    ]
    await query.edit_message_text(
        "📦 لطفاً طرحی را انتخاب کنید که کانفیگ باید به همه‌ی اشتراک‌های فعال آن اضافه شود:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_ADDCONFIG_PLAN_SELECT


async def admin_addconfig_plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    idx = int(query.data.replace("admin_addconfig_planidx_", ""))
    plan_names = context.user_data.get('addconfig_plan_names', [])
    if idx >= len(plan_names):
        await query.edit_message_text("❌ این گزینه دیگر معتبر نیست.")
        return ConversationHandler.END

    plan_name = plan_names[idx]
    context.user_data['addconfig_mode'] = 'byplan'
    context.user_data['addconfig_target_plan_name'] = plan_name

    affected_count = len(db.get_active_subscriptions_by_plan_name(plan_name))
    await query.edit_message_text(
        f"📦 طرح انتخابی: {plan_name}\n"
        f"👥 تعداد اشتراک‌های فعال این طرح: {affected_count}\n\n"
        f"🔢 لطفاً اولویت کانفیگ(های) مورد نظر را انتخاب کنید:",
        reply_markup=_priority_keyboard("admin_addconfig_priority")
    )
    return ADMIN_ADDCONFIG_PRIORITY


async def admin_addconfig_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text(
            "❌ The ID must be numeric only. Please send it again:\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_ADDCONFIG_USER_ID

    target_user_id = int(text)
    target_user = db.get_user(target_user_id)
    if not target_user:
        await update.message.reply_text(
            "❌ No user found with this ID.\n\nPlease send a different ID or /cancel to abort."
        )
        return ADMIN_ADDCONFIG_USER_ID

    subs = db.get_active_subscriptions(target_user_id)
    if not subs:
        await update.message.reply_text(
            "ℹ️ This user has no active subscriptions.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END

    context.user_data['addconfig_target'] = target_user_id
    context.user_data['addconfig_subs'] = subs

    keyboard = []
    lines = [f"👤 Active subscriptions for user <code>{target_user_id}</code>:\n"]
    for i, sub in enumerate(subs):
        label = sub.get('plan_name') or sub.get('email') or f"#{sub['id']}"
        lines.append(f"{i+1}. {label} - until {str(sub.get('end_date'))[:10]}")
        keyboard.append([InlineKeyboardButton(f"{i+1}. {label}", callback_data=f"admin_addconfig_sub_{i}")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_ADDCONFIG_SELECT_SUB


async def admin_addconfig_select_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    idx = int(query.data.replace("admin_addconfig_sub_", ""))
    subs = context.user_data.get('addconfig_subs', [])
    if idx >= len(subs):
        await query.edit_message_text("❌ This item is no longer valid.")
        return ConversationHandler.END

    sub = subs[idx]
    context.user_data['addconfig_sub_id'] = sub['id']

    await query.edit_message_text(
        "🔢 Please select the priority for the config(s) you're about to add:",
        reply_markup=_priority_keyboard("admin_addconfig_priority")
    )
    return ADMIN_ADDCONFIG_PRIORITY


async def admin_addconfig_priority_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    priority = int(query.data.replace("admin_addconfig_priority_", ""))
    context.user_data['addconfig_priority'] = priority

    await query.edit_message_text(
        "🔧 Please send the new config(s).\n"
        "You can send several configs; put each one on its own line.\n\n"
        "⚠️ Send /cancel to abort."
    )
    return ADMIN_ADDCONFIG_LINK

async def admin_addconfig_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        for key in ('addconfig_target', 'addconfig_subs', 'addconfig_sub_id', 'addconfig_priority',
                    'addconfig_mode', 'addconfig_plan_names', 'addconfig_target_plan_name'):
            context.user_data.pop(key, None)
        return ConversationHandler.END

    links = [l.strip() for l in text.split('\n') if l.strip()]
    if not links:
        await update.message.reply_text("❌ Please enter at least one config:")
        return ADMIN_ADDCONFIG_LINK

    priority = context.user_data.get('addconfig_priority', 1)
    admin = update.effective_user

    if context.user_data.get('addconfig_mode') == 'byplan':
        plan_name = context.user_data.get('addconfig_target_plan_name')
        subs = db.get_active_subscriptions_by_plan_name(plan_name) if plan_name else []

        if not subs:
            await update.message.reply_text("❌ هیچ اشتراک فعالی برای این طرح یافت نشد.", reply_markup=get_main_menu())
        else:
            for sub in subs:
                for link in links:
                    db.add_manual_config(sub['id'], link, priority)

            try:
                from logger_bot import log_admin_action
                await log_admin_action(
                    context.bot, admin_id=admin.id, action="Add config to ALL subscriptions of a plan",
                    target_user_id=None,
                    details=(
                        f"📦 Plan: {plan_name}\n👥 Subscriptions affected: {len(subs)}\n"
                        f"🔢 Priority: {priority}\n🔗 Config count: {len(links)}"
                    ),
                    username=admin.username, first_name=admin.first_name, last_name=admin.last_name
                )
            except Exception as e:
                logger.error(f"Error logging admin action: {e}")

            await update.message.reply_text(
                f"✅ {len(links)} کانفیگ به {len(subs)} اشتراک فعال طرح «{plan_name}» اضافه شد.",
                reply_markup=get_main_menu()
            )

            for sub in subs:
                try:
                    await context.bot.send_message(
                        chat_id=sub['user_id'],
                        text=(
                            f"🎉 کانفیگ جدیدی به اشتراک شما اضافه شد!\n\n"
                            f"📦 طرح: {plan_name}\n"
                            f"🔢 تعداد کانفیگ اضافه‌شده: {len(links)}\n\n"
                            f"از بخش «📒 اشتراک ها» دریافت کنید."
                        )
                    )
                except Exception as e:
                    logger.error(f"Could not notify user {sub['user_id']}: {e}")
                await asyncio.sleep(0.05)

        for key in ('addconfig_mode', 'addconfig_plan_names', 'addconfig_target_plan_name', 'addconfig_priority'):
            context.user_data.pop(key, None)
        return ConversationHandler.END

    # ---- مسیر قبلی: تک کاربر (بدون تغییر نسبت به قبل) ----
    sub_id = context.user_data.get('addconfig_sub_id')
    priority = context.user_data.get('addconfig_priority', 1)
    target_user_id = context.user_data.get('addconfig_target')

    if not sub_id:
        await update.message.reply_text("❌ Error! Please try again.", reply_markup=get_main_menu())
        return ConversationHandler.END

    for link in links:
        db.add_manual_config(sub_id, link, priority)

    subscription = db.get_subscription(sub_id)
    target_user = db.get_user(target_user_id) if target_user_id else None

    plan_name = subscription.get('plan_name') if subscription else None
    email = subscription.get('email') if subscription else None
    end_date = str(subscription.get('end_date'))[:10] if subscription else None
    remaining_volume = subscription.get('remaining_volume', 0) if subscription else 0
    vol_text = 'Unlimited' if not remaining_volume else f"{remaining_volume} GB"

    user_name = (target_user.get('first_name') or str(target_user_id)) if target_user else str(target_user_id)
    user_username = target_user.get('username') if target_user else None
    username_display = f"@{user_username}" if user_username else "-"

    priority_labels = {1: "🥇 First (Main)", 2: "🥈 Second", 3: "🥉 Third"}
    priority_label = priority_labels.get(priority, f"#{priority}")

    try:
        from logger_bot import log_admin_action
        await log_admin_action(
            context.bot,
            admin_id=admin.id,
            action="Add config to subscription",
            target_user_id=target_user_id,
            details=(
                f"🆔 Subscription: {sub_id}\n"
                f"👤 Username: {username_display}\n"
                f"📦 Plan: {plan_name or '-'}\n"
                f"📧 Email: {email or '-'}\n"
                f"🔢 Priority: {priority}\n"
                f"🔗 Config count: {len(links)}"
            ),
            username=admin.username,
            first_name=admin.first_name,
            last_name=admin.last_name
        )
    except Exception as e:
        logger.error(f"Error logging admin action: {e}")

    confirm_text = (
        f"✅ {len(links)} config(s) successfully added to the subscription.\n\n"
        f"👤 User: {html_lib.escape(str(user_name))} ({username_display}) — `{target_user_id}`\n"
        f"📦 Plan: {plan_name or '-'}\n"
        f"📧 Email: {email or '-'}\n"
        f"📊 Volume: {vol_text}\n"
        f"📅 Expires: {end_date or '-'}\n"
        f"🔢 Priority: {priority_label}"
    )

    await update.message.reply_text(confirm_text, parse_mode=None, reply_markup=get_main_menu())

    if target_user_id:
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎉 کانفیگ جدیدی به اشتراک شما اضافه شد!\n\n"
                    f"📦 طرح: {plan_name or 'اشتراک شما'}\n"
                    f"🔢 تعداد کانفیگ اضافه‌شده: {len(links)}\n\n"
                    f"از بخش «📒 اشتراک ها» دریافت کنید."
                )
            )
        except Exception as e:
            logger.error(f"Could not notify user {target_user_id}: {e}")

    for key in ('addconfig_target', 'addconfig_subs', 'addconfig_sub_id', 'addconfig_priority'):
        context.user_data.pop(key, None)

    return ConversationHandler.END

# ============ Admin: Edit Existing Subscription (duration/volume) ============
async def admin_editsub_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "✏️ Edit User Subscription\n\n"
        "👤 Please send the target user's numeric ID:\n\n"
        "⚠️ Send /cancel to abort."
    )
    return ADMIN_EDITSUB_USER_ID


async def admin_editsub_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text(
            "❌ The ID must be numeric only. Please send it again:\n\n"
            "⚠️ Send /cancel to abort."
        )
        return ADMIN_EDITSUB_USER_ID

    target_user_id = int(text)
    target_user = db.get_user(target_user_id)
    if not target_user:
        await update.message.reply_text(
            "❌ No user found with this ID.\n\n"
            "Please send a different ID or /cancel to abort."
        )
        return ADMIN_EDITSUB_USER_ID

    subs = db.get_active_subscriptions(target_user_id)
    if not subs:
        await update.message.reply_text(
            "ℹ️ This user has no active subscriptions.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END

    context.user_data['editsub_target'] = target_user_id
    context.user_data['editsub_list'] = subs

    keyboard = []
    lines = [f"👤 Active subscriptions for user <code>{target_user_id}</code>:\n"]
    for i, sub in enumerate(subs):
        label = sub.get('plan_name') or sub.get('email') or f"#{sub['id']}"
        vol = sub.get('remaining_volume', 0)
        vol_text = 'Unlimited' if not vol else f"{vol} GB"
        lines.append(f"{i+1}. {label} - {sub['duration_days']} days - Volume: {vol_text}")
        keyboard.append([InlineKeyboardButton(f"{i+1}. {label}", callback_data=f"admin_editsub_pick_{i}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="admin_editsub_cancel")])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_EDITSUB_SELECT


async def admin_editsub_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle picking a subscription from the list, or cancel"""
    query = update.callback_query
    await query.answer()

    if query.data == "admin_editsub_cancel":
        await query.edit_message_text("❌ Operation cancelled.")
        context.user_data.pop('editsub_target', None)
        context.user_data.pop('editsub_list', None)
        context.user_data.pop('editsub_id', None)
        return ConversationHandler.END

    idx = int(query.data.replace("admin_editsub_pick_", ""))
    subs = context.user_data.get('editsub_list', [])
    if idx >= len(subs):
        await query.edit_message_text("❌ This item is no longer valid.")
        return ConversationHandler.END

    sub = subs[idx]
    context.user_data['editsub_id'] = sub['id']
    vol = sub.get('remaining_volume', 0)
    vol_text = 'Unlimited' if not vol else f"{vol} GB"

    keyboard = [
        [InlineKeyboardButton("⏰ Edit Duration", callback_data="admin_editsub_field_duration")],
        [InlineKeyboardButton("📊 Edit Volume", callback_data="admin_editsub_field_volume")],
        [InlineKeyboardButton("❌ Cancel", callback_data="admin_editsub_cancel")]
    ]
    await query.edit_message_text(
        f"📦 Selected subscription: {sub.get('plan_name') or sub.get('email')}\n"
        f"⏰ Current duration: {sub['duration_days']} days\n"
        f"📊 Current volume: {vol_text}\n\n"
        f"Which value would you like to edit?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_EDITSUB_SELECT  # stay in this state until a field is picked


async def admin_editsub_field_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "admin_editsub_field_duration":
        await query.edit_message_text(
            "⏰ Please enter the new duration in days (calculated from the subscription's start date):\n"
            "Example: 30\n\n⚠️ Send /cancel to abort."
        )
        return ADMIN_EDITSUB_DURATION_INPUT

    await query.edit_message_text(
        "📊 Please enter the new volume in GB (enter 0 for unlimited):\n"
        "Example: 50\n\n⚠️ Send /cancel to abort."
    )
    return ADMIN_EDITSUB_VOLUME_INPUT


async def admin_editsub_duration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        for k in ('editsub_target', 'editsub_list', 'editsub_id'):
            context.user_data.pop(k, None)
        return ConversationHandler.END

    try:
        duration = int(text)
        if duration < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid integer of at least 1:")
        return ADMIN_EDITSUB_DURATION_INPUT

    sub_id = context.user_data.get('editsub_id')
    target_user_id = context.user_data.get('editsub_target')
    if not sub_id:
        await update.message.reply_text("❌ Error! Please try again.", reply_markup=get_main_menu())
        return ConversationHandler.END

    success = db.update_subscription_duration(sub_id, duration)

    if success:
        admin = update.effective_user
        try:
            from logger_bot import log_admin_action
            await log_admin_action(
                context.bot, admin_id=admin.id, action="Edit user subscription duration",
                target_user_id=target_user_id,
                details=f"🆔 Subscription: {sub_id}\n⏰ New duration: {duration} days",
                username=admin.username, first_name=admin.first_name, last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        await update.message.reply_text(
            f"✅ Subscription duration successfully updated to {duration} days.",
            reply_markup=get_main_menu()
        )
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"⚠️ مدت یکی از اشتراک‌های شما توسط پشتیبانی به {duration} روز تغییر کرد."
            )
        except Exception as e:
            logger.error(f"Could not notify user {target_user_id}: {e}")
    else:
        await update.message.reply_text("❌ Error updating subscription. Please try again.", reply_markup=get_main_menu())

    for k in ('editsub_target', 'editsub_list', 'editsub_id'):
        context.user_data.pop(k, None)
    return ConversationHandler.END


async def admin_editsub_volume_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ Operation cancelled.", reply_markup=get_main_menu())
        for k in ('editsub_target', 'editsub_list', 'editsub_id'):
            context.user_data.pop(k, None)
        return ConversationHandler.END

    try:
        volume = int(text)
        if volume < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid integer (enter 0 for unlimited):"
        )
        return ADMIN_EDITSUB_VOLUME_INPUT

    sub_id = context.user_data.get('editsub_id')
    target_user_id = context.user_data.get('editsub_target')
    if not sub_id:
        await update.message.reply_text("❌ Error! Please try again.", reply_markup=get_main_menu())
        return ConversationHandler.END

    success = db.set_subscription_volume(sub_id, volume)

    # If this subscription also has a real client on a panel, sync the volume there too
    if success:
        subscription = db.get_subscription(sub_id)
        if subscription and subscription.get('email') and subscription.get('panel_id'):
            try:
                from client_manager import get_panel_client
                panel_client = get_panel_client(subscription['panel_id'])
                panel_client.update_client_volume(subscription['email'], volume)
            except Exception as e:
                logger.error(f"Error syncing volume to panel for sub {sub_id}: {e}")

        admin = update.effective_user
        try:
            from logger_bot import log_admin_action
            await log_admin_action(
                context.bot, admin_id=admin.id, action="Edit user subscription volume",
                target_user_id=target_user_id,
                details=f"🆔 Subscription: {sub_id}\n📊 New volume: {'Unlimited' if volume == 0 else f'{volume} GB'}",
                username=admin.username, first_name=admin.first_name, last_name=admin.last_name
            )
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

        await update.message.reply_text(
            f"✅ Subscription volume successfully updated to {'Unlimited' if volume == 0 else f'{volume} GB'}.",
            reply_markup=get_main_menu()
        )
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"⚠️ One of your subscriptions was updated by support: volume is now "
                    f"{'Unlimited' if volume == 0 else f'{volume} GB'}."
                )
            )
        except Exception as e:
            logger.error(f"Could not notify user {target_user_id}: {e}")
    else:
        await update.message.reply_text("❌ Error updating subscription. Please try again.", reply_markup=get_main_menu())

    for k in ('editsub_target', 'editsub_list', 'editsub_id'):
        context.user_data.pop(k, None)
    return ConversationHandler.END
