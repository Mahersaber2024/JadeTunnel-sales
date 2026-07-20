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
    ConversationHandler
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handlers import admin_approve_payment, admin_reject_payment

import lifeline
from telegram.ext import ChatMemberHandler
from bot_settings import get_sponsor_channel

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
    ADMIN_MANUAL_SUB_PRIORITY,
    ADMIN_MANUAL_SUB_CONFIG,
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
        set_admin_db(db)
        send_gift.set_db(db)
        lifeline.set_db(db)
        lifeline.set_channel(get_sponsor_channel())
        print("✅ Database connected successfully!")
    except Exception as e:
        print(f"\n❌ Failed to connect to database: {e}")
        return

    # Initialize admin list
    admin_ids = config.get_admin_ids()
    set_admin_ids(admin_ids)
    
    set_get_main_menu(handlers.get_main_menu)
    send_gift.set_get_main_menu(handlers.get_main_menu)

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
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(admin_manual_sub_conv)

    # Admin Add Config to Existing Subscription Conversation
    admin_addconfig_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_addconfig_start, pattern="^admin_addconfig_start$")],
        states={
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
    application.add_handler(CallbackQueryHandler(handlers.plan_selected, pattern="^plan_"))
    application.add_handler(CallbackQueryHandler(handlers.protocol_selected, pattern="^protocol_"))
    application.add_handler(CallbackQueryHandler(handlers.pay_with_wallet, pattern="^pay_wallet$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_main, pattern="^back_to_main$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_protocols, pattern="^back_to_protocols$"))
    application.add_handler(CallbackQueryHandler(handlers.back_to_plans, pattern="^back_to_plans$"))
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
        if was_member and new_status in ("left", "kicked"):
            await lifeline.subtract_day(context.bot)

    application.add_handler(ChatMemberHandler(handle_channel_member_update, ChatMemberHandler.CHAT_MEMBER))

    application.job_queue.run_repeating(lifeline.refresh_pulse, interval=1800, first=10)

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
