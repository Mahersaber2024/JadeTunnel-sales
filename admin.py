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
        [InlineKeyboardButton("👤 User Management", callback_data="admin_user_management")],
        [InlineKeyboardButton("🖥 Manage Panels", callback_data="panel_manage")],
        [InlineKeyboardButton("📢 Sponsor Channel Settings", callback_data="admin_channel_settings")],
        [InlineKeyboardButton("☎️ Support Address Settings", callback_data="admin_support_settings")],
        [InlineKeyboardButton("🎁 Gift & Bonus Settings", callback_data="admin_bonus_settings")],
        [InlineKeyboardButton("💳 Payment Settings", callback_data="admin_payment_settings")],   # <-- جدید
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🛠 Admin Panel\n\nPlease select an option:",
        reply_markup=reply_markup
    )
def _admin_main_menu_keyboard():
    """Build the top-level admin panel keyboard (used for the back button)"""
    keyboard = [
        [InlineKeyboardButton("👤 User Management", callback_data="admin_user_management")],
        [InlineKeyboardButton("🖥 Manage Panels", callback_data="panel_manage")],
        [InlineKeyboardButton("📢 Sponsor Channel Settings", callback_data="admin_channel_settings")],
        [InlineKeyboardButton("☎️ Support Address Settings", callback_data="admin_support_settings")],
        [InlineKeyboardButton("🎁 Gift & Bonus Settings", callback_data="admin_bonus_settings")],
        [InlineKeyboardButton("💳 Payment Settings", callback_data="admin_payment_settings")],   # <-- جدید
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
        [InlineKeyboardButton("💰 Add User Balance", callback_data="admin_add_balance")],
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
        "🆕 = New plan | 📦 = Old plan | 🔥 = Custom charge plan",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None  # Changed from Markdown to None
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
        'custom_charge': '🔥 Custom Charge Plan'
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

    # ============ تصحیح: تبدیل 'custom' به 'custom_charge' ============
    if 'custom' in current_plans and 'custom_charge' not in current_plans:
        current_plans.remove('custom')
        current_plans.append('custom_charge')
        panel_manager.update_panel(panel_id, plan_types=current_plans)

    # Current status
    plan_names = {
        'new': '🆕 New Plan (Unlimited)',
        'old': '📦 Old Plan (Single User)',
        'custom_charge': '🔥 Custom Charge Plan'
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
    
    # استخراج اطلاعات از callback_data
    if data.startswith("panel_toggle_plan_new_"):
        panel_id = data.replace("panel_toggle_plan_new_", "")
        plan_type = 'new'
    elif data.startswith("panel_toggle_plan_old_"):
        panel_id = data.replace("panel_toggle_plan_old_", "")
        plan_type = 'old'
    elif data.startswith("panel_toggle_plan_custom_"):
        panel_id = data.replace("panel_toggle_plan_custom_", "")
        plan_type = 'custom_charge'
    else:
        await query.answer("❌ فرمت داده نامعتبر!", show_alert=True)
        return

    panel_manager = get_panel_manager()
    panel = panel_manager.get_panel(panel_id)

    if not panel:
        await query.edit_message_text("❌ Panel not found.")
        return

    # Get current plan list from context or panel
    temp_plans = context.user_data.get(f'temp_plans_{panel_id}')
    if temp_plans is None:
        temp_plans = panel.get('plan_types', ['new', 'old', 'custom_charge']).copy()
        if 'custom' in temp_plans and 'custom_charge' not in temp_plans:
            temp_plans.remove('custom')
            temp_plans.append('custom_charge')

    # Toggle status
    if plan_type in temp_plans:
        if len(temp_plans) <= 1:
            await query.answer("❌ At least one plan must be selected!", show_alert=True)
            return
        temp_plans.remove(plan_type)
    else:
        temp_plans.append(plan_type)

    # Save in context
    context.user_data[f'temp_plans_{panel_id}'] = temp_plans

    # Re-render the page with the new status
    plan_names = {
        'new': '🆕 New Plan (Unlimited)',
        'old': '📦 Old Plan (Single User)',
        'custom_charge': '🔥 Custom Charge Plan'
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
    """Save the plan types changes to the panel"""
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

    if not temp_plans:
        await query.answer("❌ At least one plan must be selected!", show_alert=True)
        return

    # Save to panel
    old_plans = panel.get('plan_types', [])
    success = panel_manager.update_panel(panel_id, plan_types=temp_plans)

    if success:
        # Clear temp data
        context.user_data.pop(f'temp_plans_{panel_id}', None)

        plan_names = {
            'new': '🆕 New Plan (Unlimited)',
            'old': '📦 Old Plan (Single User)',
            'custom_charge': '🔥 Custom Charge Plan'
        }
        saved_display = '\n'.join([f"✅ {plan_names.get(p, p)}" for p in temp_plans])

        # ============ لاگ تغییرات طرح‌های پنل ============
        try:
            from logger_bot import log_admin_action
            admin = query.from_user
            
            # تغییرات را مشخص کن
            changes = []
            for plan in ['new', 'old', 'custom_charge']:
                was_in_old = plan in old_plans
                is_in_new = plan in temp_plans
                if was_in_old and not is_in_new:
                    changes.append(f"❌ حذف {plan_names.get(plan, plan)}")
                elif not was_in_old and is_in_new:
                    changes.append(f"✅ اضافه {plan_names.get(plan, plan)}")
            
            change_text = "\n".join(changes) if changes else "بدون تغییر"
            
            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="ویرایش طرح‌های پنل",
                target_user_id=None,
                details=f"""
🖥 پنل: {panel.get('name')} (`{panel_id}`)
📋 تغییرات:
{change_text}
📊 وضعیت جدید:
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
                action="تغییر محدودیت اشتراک پنل",
                target_user_id=None,
                details=f"""
🖥 پنل: {panel.get('name')} (`{panel_id}`)
📊 محدودیت قبلی: {panel.get('max_subscriptions', 100)}
📊 محدودیت جدید: {new_limit}
📈 استفاده فعلی: {usage}
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
                action="افزودن پنل جدید",
                target_user_id=None,
                details=f"""
🖥 نام پنل: {name}
🌐 آدرس: {panel_base}
👤 کاربر: {username}
📊 اینباندها: {inbound_ids}
📈 محدودیت اشتراک: {max_subscriptions}
📋 طرح‌های پشتیبانی: new, old, custom_charge
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
        # ============ لاگ حذف پنل ============
        try:
            from logger_bot import log_admin_action
            admin = query.from_user
            
            await log_admin_action(
                context.bot,
                admin_id=admin.id,
                action="حذف پنل",
                target_user_id=None,
                details=f"""
🖥 پنل حذف شده: {panel_name} (`{panel_id}`)
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
            action="تغییر وضعیت عضویت اجباری کانال",
            target_user_id=None,
            details=f"وضعیت جدید: {'فعال' if new_value else 'غیرفعال'}",
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
            action="تغییر کانال اسپانسر",
            target_user_id=None,
            details=f"کانال قبلی: {old_channel}\nکانال جدید: {new_channel}",
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
            action="تغییر متن نمایشی لینک کانال",
            target_user_id=None,
            details=f"متن قبلی: {old_title}\nمتن جدید: {new_title}",
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

    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data=f"panel_info_{panel_id}")]
    ]

    await query.edit_message_text(
        f"{status} Connection Test Result\n\n"
        f"📛 Panel: {panel.get('name')}\n"
        f"🌐 Address: {panel.get('panel_base')}\n"
        f"📊 Result: {msg}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=None
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
            action="تغییر آدرس پشتیبانی",
            target_user_id=None,
            details=f"آدرس قبلی: {old_username}\nآدرس جدید: {new_username}",
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
                action="حذف کامل کاربر",
                target_user_id=target_user_id,
                details=f"کاربر <code>{target_user_id}</code> به‌طور کامل حذف شد.\n"
                        f"خطاهای حذف کلاینت پنل: {panel_delete_errors}",
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
                action="ریست کیف پول کاربر",
                target_user_id=target_user_id,
                details=f"موجودی قبلی: {old_balance:,} تومان\nموجودی جدید: 0 تومان",
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
            action=f"تغییر {label}",
            target_user_id=None,
            details=f"مقدار قبلی: {old_value:,} تومان\nمقدار جدید: {amount:,} تومان",
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
            action="تغییر اطلاعات کارت پرداخت",
            target_user_id=None,
            details=(
                f"شماره کارت قبلی: {old_number}\nشماره کارت جدید: {new_number}\n"
                f"بنام قبلی: {old_holder}\nبنام جدید: {new_holder}\n"
                f"بانک قبلی: {old_bank}\nبانک جدید: {new_bank}"
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
