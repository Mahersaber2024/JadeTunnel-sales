import os
import asyncio
import logging
import sys
import traceback
from datetime import datetime
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
    ChatMemberHandler
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handlers import admin_approve_payment, admin_reject_payment
import admin_dynamic_plans as adp
import admin_send_plan as asp

import lifeline
from bot_settings import get_sponsor_channel

from datetime import time as dt_time
from zoneinfo import ZoneInfo
import daily_reset
from Autoscanner import admin_autoscanner as aas

from config import config
from database import Database
import handlers
from admin import (
    ADMIN_USER_ID_INPUT, ADMIN_AMOUNT_INPUT,
    ADMIN_DELSUB_USER_ID, ADMIN_DELSUB_SELECT,
    ADMIN_PANEL_ADD,
    ADMIN_PANEL_EDIT_LIMIT,
    ADMIN_CHANNEL_INPUT,
    ADMIN_CHANNEL_TITLE_INPUT,
    ADMIN_SUPPORT_INPUT,
    ADMIN_DELETE_USER_ID,            # <-- جدید
    ADMIN_DELETE_USER_CONFIRM,       # <-- جدید
    ADMIN_RESET_BALANCE_ID,          # <-- جدید
    ADMIN_RESET_BALANCE_CONFIRM,     # <-- جدید
    ADMIN_BONUS_INPUT,
    ADMIN_COMMISSION_PERCENT_INPUT,
    ADMIN_CARD_INFO_INPUT,
    ADMIN_EMERGENCY_PROXY_NAME_INPUT,
    ADMIN_EMERGENCY_PROXY_LINK_INPUT,
    ADMIN_EMERGENCY_ADD_USER_ID,
    ADMIN_EMERGENCY_DENY_REASON,
    ADMIN_MANUAL_SUB_USER_ID,
    ADMIN_MANUAL_SUB_PLAN_NAME,
    ADMIN_MANUAL_SUB_EXPIRY,
    ADMIN_MANUAL_SUB_VOLUME,        # <-- جدید
    ADMIN_EMERGENCY_VOLUME_INPUT,      # <-- جدید
    ADMIN_EMERGENCY_DURATION_INPUT,    # <-- جدید
    ADMIN_MANUAL_SUB_PRIORITY,
    ADMIN_MANUAL_SUB_CONFIG,
    ADMIN_USERINFO_ID,
    ADMIN_MANUAL_SUB_TARGET, 
    ADMIN_ADDCONFIG_TARGET, 
    ADMIN_ADDCONFIG_PLAN_SELECT, 
    set_db as set_admin_db,
    set_admin_ids,
    is_admin,
    admin_panel,
    admin_add_balance_start,
    admin_add_balance_user_id,
    admin_add_balance_amount,
    admin_cancel,
    admin_delete_sub_start,
    admin_delete_sub_user_id,
    admin_delete_sub_select,
    admin_manage_panels,
    admin_panel_info,
    admin_panel_add_start,
    admin_panel_add_input,
    admin_panel_delete,
    admin_panel_set_default,
    admin_panel_test,
    admin_panel_edit_limit_start, 
    admin_panel_edit_limit_input,  
    admin_panel_edit_plans_start,  
    admin_panel_toggle_plan,      
    admin_panel_save_plans,   
    admin_channel_settings_menu,      
    admin_channel_toggle,            
    admin_channel_edit_start,  
    admin_channel_edit_input,           
    admin_channel_title_edit_start,      
    admin_channel_title_edit_input,
    admin_support_settings_menu,       
    admin_support_edit_start,          
    admin_support_edit_input,
    admin_delete_user_start,        
    admin_delete_user_get_id,       
    admin_delete_user_confirm,      
    admin_reset_balance_start,      
    admin_reset_balance_get_id,     
    admin_reset_balance_confirm,    
    admin_user_management_menu,      
    admin_back_to_main_menu,
    admin_bonus_settings_menu,      
    admin_bonus_edit_start,       
    admin_bonus_edit_input,          
    admin_commission_settings_menu,         
    admin_commission_select_panel,           
    admin_commission_set_panel,              
    admin_commission_disable,               
    admin_commission_edit_percent_start,    
    admin_commission_edit_percent_input,     
    admin_payment_settings_menu,        
    admin_hybrid_payment_toggle,       
    admin_card_info_edit_start,         
    admin_card_info_edit_input,

    admin_emergency_proxy_menu,
    admin_emergency_proxy_delete,
    admin_emergency_proxy_add_start,
    admin_emergency_proxy_name_input,
    admin_emergency_proxy_link_input,

    admin_emergency_settings_menu,
    admin_emergency_pending_menu,
    admin_emergency_review_user,
    admin_emergency_grant,
    admin_emergency_deny_start,
    admin_emergency_deny_reason_input,
    admin_emergency_users_menu,
    admin_emergency_manage_user,
    admin_emergency_revoke,
    admin_emergency_add_user_start,
    admin_emergency_add_user_id_input,

    ADMIN_MANUAL_SUB_USER_ID,
    ADMIN_MANUAL_SUB_PLAN_NAME,
    ADMIN_MANUAL_SUB_EXPIRY,
    ADMIN_MANUAL_SUB_PRIORITY,
    ADMIN_MANUAL_SUB_CONFIG,
    ADMIN_ADDCONFIG_USER_ID,
    ADMIN_ADDCONFIG_SELECT_SUB,
    ADMIN_ADDCONFIG_PRIORITY,
    ADMIN_ADDCONFIG_LINK,
    admin_manual_sub_start,
    admin_manual_sub_user_id,
    admin_manual_sub_plan_selected,
    admin_manual_sub_plan_name_text,
    admin_manual_sub_expiry_input,
    admin_manual_sub_volume_input,
    admin_manual_sub_priority_selected,
    admin_manual_sub_config_input,
    admin_addconfig_start,
    admin_addconfig_user_id,
    admin_addconfig_select_sub,
    admin_addconfig_priority_selected,
    admin_addconfig_link_input,
    admin_lifeline_settings_menu,
    admin_lifeline_toggle,
    admin_emergency_plan_settings_menu,
    admin_emergency_edit_volume_start,
    admin_emergency_edit_volume_input,
    admin_emergency_edit_duration_start,
    admin_emergency_edit_duration_input,
    ADMIN_EDITSUB_USER_ID,          # <-- اضافه کنید
    ADMIN_EDITSUB_SELECT,           # <-- اضافه کنید
    ADMIN_EDITSUB_DURATION_INPUT,   # <-- اضافه کنید
    ADMIN_EDITSUB_VOLUME_INPUT,     # <-- اضافه کنید
    admin_editsub_start,
    admin_editsub_user_id,
    admin_editsub_select,
    admin_editsub_field_selected,
    admin_editsub_duration_input,
    admin_editsub_volume_input,
    admin_userinfo_start,
    admin_userinfo_show,
    admin_manual_sub_target_selected, 
    admin_addconfig_target_selected, 
    admin_addconfig_plan_selected,
    set_get_main_menu
)

import send_gift
from send_gift import (
    GIFT_RECIPIENT_INPUT,
    GIFT_AMOUNT_INPUT,
    GIFT_MESSAGE_INPUT,
    GIFT_CONFIRM,
    gift_start,
    gift_users_shared,      # <-- جدید
    gift_recipient_input,
    gift_amount_input,
    gift_message_input,
    gift_confirm,
    gift_cancel,
)

# ============ Import Logger ============
from logger_bot import (
    init_logger, create_all_topics, send_log_message, Topics,
    log_system_error, log_user_join, log_invoice_issued,
    log_purchase_details, log_payment_card, log_wallet_payment,
    log_subscription_created, log_panel_error, log_user_activity,
    log_balance_change, log_referral_bonus, log_volume_added,
    log_subscription_expire, log_panel_status
)

# ====================== Logging Configuration ======================
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# ============ Global bot instance for logger ============
_bot_instance = None

def get_bot():
    """Get global bot instance"""
    return _bot_instance

# ============ Initialize Logger ============
async def initialize_logger(application):
    """Initialize logger with bot and create topics"""
    global _bot_instance
    _bot_instance = application.bot
    
    log_group_id = config.get_log_group_id()
    
    if log_group_id:
        init_logger(log_group_id)
        logger.info(f"✅ Logger initialized with group ID: {log_group_id}")
        
        # Create all topics
        await create_all_topics(application.bot)
        
        # Log bot startup
        await log_system_error(
            application.bot,
            "🚀 ربات با موفقیت راه‌اندازی شد!",
            context=f"زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    else:
        logger.warning("⚠️ Logger not configured. LOG_GROUP_ID missing.")

# ============ Set Bot for Handlers ============
# بعد از راه‌اندازی، توابع لاگر را در دسترس handlers قرار می‌دهیم

async def set_bot_commands(application):
    """Set bot commands menu that appears when user types /"""
    commands = [
        BotCommand("start", "جاده تونل"),
        BotCommand("admin", "مدیریت"),
    ]
    await application.bot.set_my_commands(commands)

def main():
    """Main function to run the bot"""
    global _bot_instance
    
    print("\n" + "=" * 60)
    print("🚀 VPN Bot Starting...")
    print("=" * 60)

    if not config.load():
        print("\n⚠️ No configuration file found!")
        config.setup_interactive()
    elif not config.is_configured():
        print("\n⚠️ Configuration is incomplete!")
        config.setup_interactive()

    if not config.is_configured():
        print("\n❌ Configuration is incomplete. Please run setup again.")
        return
    config.show_config()

    # Initialize database
    try:
        db_config = config.get_db_config()
        db = Database(db_config)
        handlers.set_db(db)
        daily_reset.set_db(db)
        set_admin_db(db)
        send_gift.set_db(db)
        asp.set_db(db)
        lifeline.set_db(db)
        lifeline.set_channel(get_sponsor_channel())
        print("✅ Database connected successfully!")
    except Exception as e:
        print(f"\n❌ Failed to connect to database: {e}")
        return

    # Initialize admin list
    admin_ids = config.get_admin_ids()
    set_admin_ids(admin_ids)
    aas.set_is_admin(is_admin)
    aas.set_get_main_menu(handlers.get_main_menu)
    adp.set_is_admin(is_admin)   # <-- اضافه شد (۳.۲)
    asp.set_is_admin(is_admin)
    set_get_main_menu(handlers.get_main_menu)
    send_gift.set_get_main_menu(handlers.get_main_menu)
    asp.set_get_main_menu(handlers.get_main_menu)
    asp.set_purchase_deps(handlers.create_subscription_for_purchase, handlers.get_single_sub_link)

    token = config.get('bot_token')
    if not token:
        print("\n❌ Bot token is missing.")
        return

    try:
        application = Application.builder().token(token).build()
        print("✅ Bot initialized successfully!")
    except Exception as e:
        print(f"\n❌ Failed to initialize bot: {e}")
        return

    application.post_init = set_bot_commands

    # ====================== Handlers ======================
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("admin", admin_panel))

    # ============ AutoScanner Handlers ============
    application.add_handler(CallbackQueryHandler(aas.admin_autoscanner_menu, pattern="^admin_autoscanner_menu$"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_zones_menu, pattern="^autoscanner_zones_menu$"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_records_menu, pattern="^autoscanner_records_menu$"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_toggle, pattern="^autoscanner_toggle$"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_run_menu, pattern="^autoscanner_run_menu$"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_runsel_toggle, pattern="^autoscanner_runsel_toggle_"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_runsel_all, pattern="^autoscanner_runsel_all$"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_runsel_none, pattern="^autoscanner_runsel_none$"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_runsel_start, pattern="^autoscanner_runsel_start$"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_zone_delete, pattern="^autoscanner_zone_del_"))
    application.add_handler(CallbackQueryHandler(aas.autoscanner_record_delete, pattern="^autoscanner_record_del_"))

    # Matches the "❌ Cancel" reply-keyboard button shown (in place of the main menu)
    # while an AutoScanner conversation is waiting for text input.
    autoscanner_cancel_button = MessageHandler(filters.Regex(f"^{aas.CANCEL_BUTTON_TEXT}$"), admin_cancel)

    autoscanner_token_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(aas.autoscanner_token_edit_start, pattern="^autoscanner_token_edit$")],
        states={
            aas.AUTOSCANNER_TOKEN_INPUT: [
                CommandHandler("cancel", admin_cancel),
                autoscanner_cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, aas.autoscanner_token_edit_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel), autoscanner_cancel_button]
    )
    application.add_handler(autoscanner_token_conv)

    autoscanner_zone_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(aas.autoscanner_zone_add_start, pattern="^autoscanner_zone_add$")],
        states={
            aas.AUTOSCANNER_ZONE_INPUT: [
                CommandHandler("cancel", admin_cancel),
                autoscanner_cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, aas.autoscanner_zone_add_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel), autoscanner_cancel_button]
    )
    application.add_handler(autoscanner_zone_conv)

    autoscanner_record_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(aas.autoscanner_record_add_start, pattern="^autoscanner_record_add$")],
        states={
            aas.AUTOSCANNER_RECORD_INPUT: [
                CommandHandler("cancel", admin_cancel),
                autoscanner_cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, aas.autoscanner_record_add_input)
            ],
            aas.AUTOSCANNER_RECORD_ZONE_SELECT: [
                CallbackQueryHandler(aas.autoscanner_record_zone_selected, pattern="^autoscanner_recordzone_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel), autoscanner_cancel_button]
    )
    application.add_handler(autoscanner_record_conv)

    autoscanner_record_bulk_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(aas.autoscanner_record_bulk_add_start, pattern="^autoscanner_record_bulk_add$")],
        states={
            aas.AUTOSCANNER_RECORD_BULK_ADD_INPUT: [
                CommandHandler("cancel", admin_cancel),
                autoscanner_cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, aas.autoscanner_record_bulk_add_input)
            ],
            aas.AUTOSCANNER_RECORD_BULK_ADD_ZONE_SELECT: [
                CallbackQueryHandler(aas.autoscanner_record_bulk_zone_selected, pattern="^autoscanner_bulkzone_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel), autoscanner_cancel_button]
    )
    application.add_handler(autoscanner_record_bulk_add_conv)

    autoscanner_record_bulk_delete_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(aas.autoscanner_record_bulk_delete_start, pattern="^autoscanner_record_bulk_delete$")],
        states={
            aas.AUTOSCANNER_RECORD_BULK_DELETE_INPUT: [
                CommandHandler("cancel", admin_cancel),
                autoscanner_cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, aas.autoscanner_record_bulk_delete_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel), autoscanner_cancel_button]
    )
    application.add_handler(autoscanner_record_bulk_delete_conv)

    autoscanner_interval_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(aas.autoscanner_interval_edit_start, pattern="^autoscanner_interval_edit$")],
        states={
            aas.AUTOSCANNER_INTERVAL_INPUT: [
                CommandHandler("cancel", admin_cancel),
                autoscanner_cancel_button,
                MessageHandler(filters.TEXT & ~filters.COMMAND, aas.autoscanner_interval_edit_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel), autoscanner_cancel_button]
    )
    application.add_handler(autoscanner_interval_conv)

    # Message handlers for main menu
    application.add_handler(MessageHandler(filters.Regex("^🛒 خرید VPN$"), handlers.buy_vpn))
    application.add_handler(MessageHandler(filters.Regex("^📒 اشتراک ها$"), handlers.view_subscriptions))
    application.add_handler(MessageHandler(filters.Regex("^🗂 حساب کاربری$"), handlers.account_info))
    application.add_handler(MessageHandler(filters.Regex("^📝 راهنما$"), handlers.help_command))
    application.add_handler(MessageHandler(filters.Regex("^📨 پشتیبانی$"), handlers.support))
    application.add_handler(MessageHandler(filters.Regex("^👥 دعوت از دوستان$"), handlers.invite_friends))

    # Charge conversation handler
    charge_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 افزایش موجودی$"), handlers.charge_wallet)],
        states={
            handlers.AMOUNT_SELECTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.charge_amount)
            ],
            handlers.PAYMENT_METHOD: [
                CallbackQueryHandler(handlers.charge_pay_card, pattern="^charge_pay_card$"),
                MessageHandler(filters.Regex("^❌ انصراف از شارژ$"), handlers.charge_amount),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_charge_card_digits),
                CallbackQueryHandler(handlers.charge_cancel, pattern="^cancel_charge$")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(handlers.charge_cancel, pattern="^cancel_charge$"),
            MessageHandler(filters.Regex("^❌ انصراف از شارژ$"), handlers.charge_amount)
        ]
    )
    application.add_handler(charge_conv_handler)

    # Card payment conversation handler
    card_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handlers.pay_with_card, pattern="^pay_card$")],
        states={
            handlers.PAYMENT_METHOD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_card_digits),
                CallbackQueryHandler(handlers.cancel_payment, pattern="^cancel_payment$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(handlers.cancel_payment, pattern="^cancel_payment$"),
            MessageHandler(filters.Regex("^❌ انصراف از پرداخت$"), handlers.handle_card_digits)
        ]
    )
    application.add_handler(card_conv_handler)

    # Extra Volume Conversation Handler
    extra_volume_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ افزایش حجم اضافی$"), handlers.add_extra_volume),
            CallbackQueryHandler(handlers.add_extra_volume_from_plan, pattern="^add_extra_volume_from_plan$"),
        ],
        states={
            handlers.VOLUME_SELECTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_volume_input),
                CallbackQueryHandler(handlers.back_to_custom_charge_from_plan, pattern="^back_to_custom_charge_from_plan$"),
            ],
            handlers.PAYMENT_METHOD: [
                CallbackQueryHandler(handlers.extra_volume_pay_wallet, pattern="^extra_volume_pay_wallet$"),
                CallbackQueryHandler(handlers.extra_volume_pay_card, pattern="^extra_volume_pay_card$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_extra_volume_card_digits),
                CallbackQueryHandler(handlers.cancel_payment, pattern="^cancel_extra_volume$")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(handlers.cancel_payment, pattern="^cancel_extra_volume$"),
            MessageHandler(filters.Regex("^❌ انصراف$"), handlers.handle_volume_input),
            CallbackQueryHandler(handlers.back_to_custom_charge_from_plan, pattern="^back_to_custom_charge_from_plan$"),
        ]
    )
    application.add_handler(extra_volume_conv_handler)

    # Send Gift Conversation Handler
    gift_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🎁 ارسال هدیه$"), gift_start)
        ],
        states={
            GIFT_RECIPIENT_INPUT: [
                MessageHandler(filters.StatusUpdate.USERS_SHARED, gift_users_shared),  # <-- جایگزین دکمه شیشه‌ای
                MessageHandler(filters.TEXT | filters.FORWARDED, gift_recipient_input),
            ],
            GIFT_AMOUNT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gift_amount_input)
            ],
            GIFT_MESSAGE_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gift_message_input)
            ],
            GIFT_CONFIRM: [
                CallbackQueryHandler(gift_confirm, pattern="^gift_confirm_")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", gift_cancel),
            MessageHandler(filters.Regex("^❌ انصراف از ارسال هدیه$"), gift_cancel)
        ]
    )
    application.add_handler(gift_conv_handler)
    
    # Admin handlers
    admin_delsub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_delete_sub_start, pattern="^admin_delete_sub$")],
        states={
            ADMIN_DELSUB_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_delete_sub_user_id)],
            ADMIN_DELSUB_SELECT: [CallbackQueryHandler(admin_delete_sub_select, pattern="^admin_delsub_")],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
    )
    application.add_handler(admin_delsub_conv)

    admin_userinfo_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_userinfo_start, pattern="^admin_userinfo_start$")],
        states={
            ADMIN_USERINFO_ID: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_userinfo_show)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)],
    )
    application.add_handler(admin_userinfo_conv)
    
    admin_add_balance_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_add_balance_start, pattern="^admin_add_balance$")
        ],
        states={
            ADMIN_USER_ID_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_balance_user_id)
            ],
            ADMIN_AMOUNT_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_balance_amount)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel)
        ]
    )
    application.add_handler(admin_add_balance_conv_handler)

    admin_panel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_panel_add_start, pattern="^panel_add$")],
        states={
            ADMIN_PANEL_ADD: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_panel_add_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_panel_conv)

    # Admin Panel Edit Limit Conversation
    admin_panel_edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_panel_edit_limit_start, pattern="^panel_edit_limit_")],
        states={
            ADMIN_PANEL_EDIT_LIMIT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_panel_edit_limit_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_panel_edit_conv)

    # Admin Sponsor Channel Conversation
    admin_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_channel_edit_start, pattern="^admin_channel_edit$")],
        states={
            ADMIN_CHANNEL_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_channel_edit_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_channel_conv)

    # Admin Sponsor Channel Display Title Conversation
    admin_channel_title_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_channel_title_edit_start, pattern="^admin_channel_title_edit$")],
        states={
            ADMIN_CHANNEL_TITLE_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_channel_title_edit_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_channel_title_conv)

    # Admin Support Address Conversation
    admin_support_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_support_edit_start, pattern="^admin_support_edit$")],
        states={
            ADMIN_SUPPORT_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_support_edit_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_support_conv)

    # Admin Delete User Conversation
    admin_delete_user_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_delete_user_start, pattern="^admin_delete_user$")],
        states={
            ADMIN_DELETE_USER_ID: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_delete_user_get_id)
            ],
            ADMIN_DELETE_USER_CONFIRM: [
                CallbackQueryHandler(admin_delete_user_confirm, pattern="^admin_delete_user_confirm_")
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_delete_user_conv)

    # Admin Reset Balance Conversation
    admin_reset_balance_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_reset_balance_start, pattern="^admin_reset_balance$")],
        states={
            ADMIN_RESET_BALANCE_ID: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reset_balance_get_id)
            ],
            ADMIN_RESET_BALANCE_CONFIRM: [
                CallbackQueryHandler(admin_reset_balance_confirm, pattern="^admin_reset_balance_confirm_")
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_reset_balance_conv)

    # Admin Gift & Bonus Conversation
    admin_bonus_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_bonus_edit_start,
                pattern="^admin_bonus_edit_(signup|inviter|invitee)$"
            )
        ],
        states={
            ADMIN_BONUS_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_bonus_edit_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_bonus_conv)

   # Admin Commission-based Panel Access Conversation
    admin_commission_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_commission_edit_percent_start, pattern="^admin_commission_edit_percent$")
        ],
        states={
            ADMIN_COMMISSION_PERCENT_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_commission_edit_percent_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_commission_conv)

    # Admin Card Payment Info Conversation
    admin_card_info_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_card_info_edit_start, pattern="^admin_card_info_edit$")],
        states={
            ADMIN_CARD_INFO_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_card_info_edit_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_card_info_conv)

    admin_emergency_proxy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_emergency_proxy_add_start, pattern="^admin_emergency_proxy_add$")],
        states={
            ADMIN_EMERGENCY_PROXY_NAME_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_emergency_proxy_name_input)
            ],
            ADMIN_EMERGENCY_PROXY_LINK_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_emergency_proxy_link_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_emergency_proxy_conv)

    # Admin Manual Subscription Conversation
    admin_manual_sub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_manual_sub_start, pattern="^admin_manual_sub_add$")],
        states={
            ADMIN_MANUAL_SUB_USER_ID: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manual_sub_user_id)
            ],
            ADMIN_MANUAL_SUB_PLAN_NAME: [
                CommandHandler("cancel", admin_cancel),
                CallbackQueryHandler(admin_manual_sub_plan_selected, pattern="^admin_manual_plan_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manual_sub_plan_name_text)
            ],
            ADMIN_MANUAL_SUB_EXPIRY: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manual_sub_expiry_input)
            ],
            ADMIN_MANUAL_SUB_VOLUME: [                                       # <-- جدید
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manual_sub_volume_input)
            ],
            ADMIN_MANUAL_SUB_PRIORITY: [
                CommandHandler("cancel", admin_cancel),
                CallbackQueryHandler(admin_manual_sub_priority_selected, pattern="^admin_manual_priority_")
            ],
            ADMIN_MANUAL_SUB_CONFIG: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_manual_sub_config_input)
            ],
            # NEW: Target selection state for manual subscription (added in section 3)
            ADMIN_MANUAL_SUB_TARGET: [
                CommandHandler("cancel", admin_cancel),
                CallbackQueryHandler(admin_manual_sub_target_selected, pattern="^admin_manual_target_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_manual_sub_conv)

    # Admin Send Plan to User(s) Conversation (gift a real plan, created via the panel
    # exactly like a normal purchase, either to one user or to every user)
    admin_send_plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(asp.admin_send_plan_start, pattern="^admin_send_plan_start$")],
        states={
            asp.ADMSP_TARGET: [
                CallbackQueryHandler(asp.admin_send_plan_target_single, pattern="^admsp_target_single$"),
                CallbackQueryHandler(asp.admin_send_plan_target_all, pattern="^admsp_target_all$"),
            ],
            asp.ADMSP_USER_ID: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, asp.admin_send_plan_user_id)
            ],
            asp.ADMSP_SCHEME: [
                CallbackQueryHandler(asp.admin_send_plan_scheme_selected, pattern="^admsp_scheme_"),
                CallbackQueryHandler(asp.admin_send_plan_cancel, pattern="^admsp_cancel$"),
            ],
            asp.ADMSP_PLAN: [
                CallbackQueryHandler(asp.admin_send_plan_plan_selected, pattern="^admsp_plan_"),
                CallbackQueryHandler(asp.admin_send_plan_cancel, pattern="^admsp_cancel$"),
            ],
            asp.ADMSP_REPLACE: [
                CallbackQueryHandler(asp.admin_send_plan_replace_selected, pattern="^admsp_replace_"),
                CallbackQueryHandler(asp.admin_send_plan_cancel, pattern="^admsp_cancel$"),
            ],
            asp.ADMSP_DELAY: [
                CallbackQueryHandler(asp.admin_send_plan_delay_selected, pattern="^admsp_delay_"),
                CallbackQueryHandler(asp.admin_send_plan_cancel, pattern="^admsp_cancel$"),
            ],
            asp.ADMSP_CONFIRM: [
                CallbackQueryHandler(asp.admin_send_plan_confirm, pattern="^admsp_confirm_yes$"),
                CallbackQueryHandler(asp.admin_send_plan_cancel, pattern="^admsp_cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_send_plan_conv)

    # Admin Add Config to Existing Subscription Conversation
    admin_addconfig_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_addconfig_start, pattern="^admin_addconfig_start$")],
        states={
            ADMIN_ADDCONFIG_TARGET: [
                CommandHandler("cancel", admin_cancel),
                CallbackQueryHandler(admin_addconfig_target_selected, pattern="^admin_addconfig_target_")
            ],
            ADMIN_ADDCONFIG_PLAN_SELECT: [
                CommandHandler("cancel", admin_cancel),
                CallbackQueryHandler(admin_addconfig_plan_selected, pattern="^admin_addconfig_planidx_")
            ],
            ADMIN_ADDCONFIG_USER_ID: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_addconfig_user_id)
            ],
            ADMIN_ADDCONFIG_SELECT_SUB: [
                CommandHandler("cancel", admin_cancel),
                CallbackQueryHandler(admin_addconfig_select_sub, pattern="^admin_addconfig_sub_")
            ],
            ADMIN_ADDCONFIG_PRIORITY: [
                CommandHandler("cancel", admin_cancel),
                CallbackQueryHandler(admin_addconfig_priority_selected, pattern="^admin_addconfig_priority_")
            ],
            ADMIN_ADDCONFIG_LINK: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_addconfig_link_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_addconfig_conv)

    # Admin Dynamic Purchase Plans Management (admin_dynamic_plans.py)
    application.add_handler(CallbackQueryHandler(adp.admin_plans_menu, pattern="^admin_dynamic_plans_menu$"))
    application.add_handler(CallbackQueryHandler(adp.admin_plan_view, pattern="^dynplan_view_"))
    application.add_handler(CallbackQueryHandler(adp.admin_plan_toggle, pattern="^dynplan_toggle_"))
    application.add_handler(CallbackQueryHandler(adp.admin_plan_delete, pattern="^dynplan_delete_"))

    admin_dynplan_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(adp.admin_plan_add_start, pattern="^dynplan_add_start$")],
        states={
            adp.ADMIN_DYNPLAN_CATEGORY: [
                CallbackQueryHandler(adp.admin_plan_add_category, pattern="^dynplan_scheme_"),   # <-- باید scheme_ باشه نه cat_
            ],
            adp.ADMIN_DYNPLAN_NAME: [
                CommandHandler("cancel", adp.admin_plan_add_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adp.admin_plan_add_name)
            ],
            adp.ADMIN_DYNPLAN_DESC: [
                CommandHandler("cancel", adp.admin_plan_add_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adp.admin_plan_add_desc)
            ],
            adp.ADMIN_DYNPLAN_PRICE: [
                CommandHandler("cancel", adp.admin_plan_add_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adp.admin_plan_add_price)
            ],
            adp.ADMIN_DYNPLAN_DAYS: [
                CommandHandler("cancel", adp.admin_plan_add_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adp.admin_plan_add_days)
            ],
            adp.ADMIN_DYNPLAN_VOLUME: [
                CommandHandler("cancel", adp.admin_plan_add_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adp.admin_plan_add_volume)
            ],
            adp.ADMIN_DYNPLAN_DAILY: [
                CommandHandler("cancel", adp.admin_plan_add_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adp.admin_plan_add_daily)
            ],
        },
        fallbacks=[CommandHandler("cancel", adp.admin_plan_add_cancel)]
    )
    application.add_handler(admin_dynplan_add_conv)

    application.add_handler(CallbackQueryHandler(admin_emergency_plan_settings_menu, pattern="^admin_emergency_plan_settings$"))

    admin_emergency_volume_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_emergency_edit_volume_start, pattern="^admin_emergency_edit_volume$")],
        states={
            ADMIN_EMERGENCY_VOLUME_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_emergency_edit_volume_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_emergency_volume_conv)

    # Admin Edit Existing Subscription Conversation
    admin_editsub_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_editsub_start, pattern="^admin_editsub_start$")],
        states={
            ADMIN_EDITSUB_USER_ID: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_editsub_user_id)
            ],
            ADMIN_EDITSUB_SELECT: [
                CallbackQueryHandler(admin_editsub_field_selected, pattern="^admin_editsub_field_"),
                CallbackQueryHandler(admin_editsub_select, pattern="^admin_editsub_pick_"),
                CallbackQueryHandler(admin_editsub_select, pattern="^admin_editsub_cancel$"),
            ],
            ADMIN_EDITSUB_DURATION_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_editsub_duration_input)
            ],
            ADMIN_EDITSUB_VOLUME_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_editsub_volume_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_editsub_conv)
    
    admin_emergency_duration_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_emergency_edit_duration_start, pattern="^admin_emergency_edit_duration$")],
        states={
            ADMIN_EMERGENCY_DURATION_INPUT: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_emergency_edit_duration_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_emergency_duration_conv)

    application.add_handler(CallbackQueryHandler(admin_lifeline_settings_menu, pattern="^admin_lifeline_settings$"))
    application.add_handler(CallbackQueryHandler(admin_lifeline_toggle, pattern="^admin_lifeline_toggle$"))

    application.add_handler(CallbackQueryHandler(handlers.send_config_by_priority, pattern="^get_config_"))
    application.add_handler(CallbackQueryHandler(admin_emergency_proxy_menu, pattern="^admin_emergency_proxy_settings$"))
    application.add_handler(CallbackQueryHandler(admin_emergency_proxy_delete, pattern="^admin_emergency_proxy_del_"))

    application.add_handler(CallbackQueryHandler(admin_commission_settings_menu, pattern="^admin_commission_settings$"))
    application.add_handler(CallbackQueryHandler(admin_commission_select_panel, pattern="^admin_commission_select_panel$"))
    application.add_handler(CallbackQueryHandler(admin_commission_set_panel, pattern="^admin_commission_set_panel_"))
    application.add_handler(CallbackQueryHandler(admin_commission_disable, pattern="^admin_commission_disable$"))
    
    application.add_handler(CallbackQueryHandler(admin_bonus_settings_menu, pattern="^admin_bonus_settings$"))
    application.add_handler(CallbackQueryHandler(admin_support_settings_menu, pattern="^admin_support_settings$"))
    
    application.add_handler(CallbackQueryHandler(admin_channel_settings_menu, pattern="^admin_channel_settings$"))
    application.add_handler(CallbackQueryHandler(admin_channel_toggle, pattern="^admin_channel_toggle$"))
    application.add_handler(CallbackQueryHandler(admin_user_management_menu, pattern="^admin_user_management$"))
    application.add_handler(CallbackQueryHandler(admin_back_to_main_menu, pattern="^admin_back_to_main_menu$"))
    
    application.add_handler(CallbackQueryHandler(admin_manage_panels, pattern="^panel_manage$"))
    application.add_handler(CallbackQueryHandler(admin_panel_info, pattern="^panel_info_"))
    application.add_handler(CallbackQueryHandler(admin_panel_delete, pattern="^panel_delete_"))
    application.add_handler(CallbackQueryHandler(admin_panel_set_default, pattern="^panel_set_default_"))
    application.add_handler(CallbackQueryHandler(admin_panel_test, pattern="^panel_test_"))
    application.add_handler(CallbackQueryHandler(admin_approve_payment, pattern="^admin_approve_"))
    application.add_handler(CallbackQueryHandler(admin_reject_payment, pattern="^admin_reject_"))
    application.add_handler(CallbackQueryHandler(admin_payment_settings_menu, pattern="^admin_payment_settings$"))
    application.add_handler(CallbackQueryHandler(admin_hybrid_payment_toggle, pattern="^admin_hybrid_payment_toggle$"))
    # Admin Panel Edit Plans handlers
    application.add_handler(CallbackQueryHandler(admin_panel_edit_plans_start, pattern="^panel_edit_plans_"))
    application.add_handler(CallbackQueryHandler(admin_panel_toggle_plan, pattern="^panel_toggle_plan_"))
    application.add_handler(CallbackQueryHandler(admin_panel_save_plans, pattern="^panel_save_plans_"))
    
    # Callback query handlers
    application.add_handler(CallbackQueryHandler(handlers.plan_type_selected, pattern="^plan_type_"))
    application.add_handler(CallbackQueryHandler(handlers.custom_charge_buy, pattern="^custom_charge_buy$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_custom_charge, pattern="^back_to_custom_charge$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_plan_type, pattern="^back_to_plan_type$"))
    application.add_handler(CallbackQueryHandler(handlers.select_sub_for_volume, pattern="^select_sub_for_volume_"))
    application.add_handler(CallbackQueryHandler(handlers.plan_dyn_selected, pattern="^plan_dyn_"))   # <-- اضافه شد (۳.۴)
    application.add_handler(CallbackQueryHandler(handlers.back_to_dyn_category, pattern="^back_to_dyn_category$"))
    application.add_handler(CallbackQueryHandler(handlers.protocol_selected, pattern="^protocol_"))
    application.add_handler(CallbackQueryHandler(handlers.pay_with_wallet, pattern="^pay_wallet$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_main, pattern="^back_to_main$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_protocols, pattern="^back_to_protocols$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_plans, pattern="^back_to_plans$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_old_plan, pattern="^back_to_old_plan$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_help, pattern="^back_to_help$"))
    application.add_handler(CallbackQueryHandler(handlers.help_protocol_selected, pattern="^help_"))
    application.add_handler(CallbackQueryHandler(handlers.v2ray_os_selected, pattern="^v2ray_"))
    application.add_handler(CallbackQueryHandler(handlers.view_subscriptions_callback, pattern="^view_subscriptions$"))
    application.add_handler(CallbackQueryHandler(handlers.buy_vpn_callback, pattern="^buy_vpn$"))

    application.add_handler(MessageHandler(filters.Regex("^🆘 طرح اضطراری$"), handlers.emergency_plan))
    application.add_handler(CallbackQueryHandler(handlers.emergency_build_config, pattern="^emergency_build_config$"))
    application.add_handler(CallbackQueryHandler(handlers.emergency_get_proxy, pattern="^emergency_get_proxy$"))
    application.add_handler(CallbackQueryHandler(handlers.emergency_panel_selected, pattern="^emergency_panel_"))

    application.add_handler(CallbackQueryHandler(admin_emergency_settings_menu, pattern="^admin_emergency_settings$"))
    application.add_handler(CallbackQueryHandler(admin_emergency_pending_menu, pattern="^admin_emergency_pending$"))
    application.add_handler(CallbackQueryHandler(admin_emergency_review_user, pattern="^admin_emergency_review_"))
    application.add_handler(CallbackQueryHandler(admin_emergency_grant, pattern="^admin_emergency_grant_"))
    
    application.add_handler(CallbackQueryHandler(admin_emergency_users_menu, pattern="^admin_emergency_users_menu$"))
    application.add_handler(CallbackQueryHandler(admin_emergency_manage_user, pattern="^admin_emergency_manage_"))
    application.add_handler(CallbackQueryHandler(admin_emergency_revoke, pattern="^admin_emergency_revoke_"))

    application.add_handler(CallbackQueryHandler(adp.admin_schemes_menu, pattern="^dynscheme_menu$"))
    application.add_handler(CallbackQueryHandler(adp.admin_scheme_view, pattern="^dynscheme_view_"))
    application.add_handler(CallbackQueryHandler(adp.admin_scheme_toggle, pattern="^dynscheme_toggle_"))
    application.add_handler(CallbackQueryHandler(adp.admin_scheme_delete, pattern="^dynscheme_delete_"))

    dynscheme_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(adp.admin_scheme_add_start, pattern="^dynscheme_add_start$"),
            CallbackQueryHandler(adp.admin_scheme_rename_start, pattern="^dynscheme_rename_"),
            CallbackQueryHandler(adp.admin_scheme_editfooter_start, pattern="^dynscheme_editfooter_"),
        ],
        states={
            adp.ADMIN_DYNSCHEME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, adp.admin_scheme_name_received)],
            adp.ADMIN_DYNSCHEME_FOOTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, adp.admin_scheme_footer_received)],
        },
        fallbacks=[CommandHandler('cancel', adp.admin_scheme_name_cancel)],
    )
    application.add_handler(dynscheme_conv)

    admin_emergency_add_user_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_emergency_add_user_start, pattern="^admin_emergency_add_user$")],
        states={
            ADMIN_EMERGENCY_ADD_USER_ID: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_emergency_add_user_id_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_emergency_add_user_conv)

    admin_emergency_deny_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_emergency_deny_start, pattern="^admin_emergency_deny_")],
        states={
            ADMIN_EMERGENCY_DENY_REASON: [
                CommandHandler("cancel", admin_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_emergency_deny_reason_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_emergency_deny_conv)

    # ====================== Lifeline (چراغ جاده تونل) ======================
    async def handle_channel_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
        result = update.chat_member
        if not result:
            return
        old_status = result.old_chat_member.status
        new_status = result.new_chat_member.status
        was_member = old_status in ("member", "administrator", "creator")
        is_member_now = new_status in ("member", "administrator", "creator")

        if not was_member and is_member_now:
            await lifeline.add_day(context.bot)          # عضویت جدید = +۱ روز
        elif was_member and not is_member_now:
            await lifeline.subtract_day(context.bot)      # خروج = −۱ روز

    application.add_handler(ChatMemberHandler(handle_channel_member_update, ChatMemberHandler.CHAT_MEMBER))

    application.job_queue.run_repeating(lifeline.refresh_pulse, interval=1800, first=10)
    application.job_queue.run_repeating(
        daily_reset.run_emergency_plan_cleanup,
        interval=1800,
        first=30,
        name="emergency_plan_cleanup"
    )
    application.job_queue.run_daily(
        daily_reset.run_daily_traffic_reset,
        time=dt_time(hour=0, minute=5, tzinfo=ZoneInfo("Asia/Tehran")),
        name="daily_traffic_reset"
    )
    application.job_queue.run_repeating(
        aas.autoscanner_scheduled_job,
        interval=1800,
        first=60,
        name="autoscanner_periodic_check"
    )
    async def admin_lifeline_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            return
        row = db.get_lifeline()
        if not context.args:
            await update.message.reply_text(f"روز باقیمانده: {row['days_remaining']} از {row['max_days']}")
            return
        try:
            new_days = int(context.args[0])
        except ValueError:
            await update.message.reply_text("عدد نامعتبر است.")
            return
        db.adjust_lifeline_days(new_days - row['days_remaining'], max_days=row['max_days'])
        await lifeline.post_or_update_lifeline(context.bot)
        await update.message.reply_text(f"✅ روز باقیمانده به {new_days} تنظیم شد.")

    application.add_handler(CommandHandler("lifeline", admin_lifeline_command))

    # Initialize logger after bot is ready (runs after set_bot_commands)
    application.post_init = initialize_logger

    # Start the Bot
    print("\n" + "=" * 60)
    print("✅ Bot is ready and running!")
    print("🤖 Press Ctrl+C to stop.")
    print("=" * 60 + "\n")

    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print(f"\n❌ Bot stopped with error: {e}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Bot stopped by user.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
