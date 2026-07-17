import os
import asyncio
import logging
import sys
import traceback
import emergency_plan

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
        print("✅ Database connected successfully!")
    except Exception as e:
        print(f"\n❌ Failed to connect to database: {e}")
        return

    # Initialize admin list
    admin_ids = config.get_admin_ids()
    set_admin_ids(admin_ids)

    emergency_plan.set_db(db)
    emergency_plan.set_admin_ids(admin_ids)
    emergency_plan.set_get_main_menu(handlers.get_main_menu)

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

    # ---------- ویرایش متن پروکسی/کانفیگ ----------
    emergency_proxy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(emergency_plan.emergency_edit_proxy_start, pattern="^emg_edit_proxy$")],
        states={
            emergency_plan.EMERGENCY_PROXY_EDIT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, emergency_plan.emergency_edit_proxy_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(emergency_proxy_conv)

    emergency_config_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(emergency_plan.emergency_edit_config_start, pattern="^emg_edit_config$")],
        states={
            emergency_plan.EMERGENCY_CONFIG_EDIT_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, emergency_plan.emergency_edit_config_input)
            ],
        },
        fallbacks=[CommandHandler("cancel", admin_cancel)]
    )
    application.add_handler(emergency_config_conv)

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, emergency_plan.emergency_admin_custom_days_input),
        group=-1
    )

    # ---------- مدیریت اعضا (لیست/حذف) ----------
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_admin_menu, pattern="^emg_admin_menu$"))
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_list_members, pattern="^emg_list_members$"))
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_remove_member, pattern="^emg_remove_"))

    # ---------- سمت کاربر ----------
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_request, pattern="^emergency_request$"))
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_get_proxy, pattern="^emergency_get_proxy$"))
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_get_config, pattern="^emergency_get_config$"))

    # ---------- تایید/رد/تعیین مدت توسط ادمین ----------
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_admin_approve, pattern="^emg_approve_"))
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_admin_reject, pattern="^emg_reject_"))
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_admin_set_days, pattern="^emg_days_"))
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_admin_custom_days_start, pattern="^emg_customdays_"))
    application.add_handler(CallbackQueryHandler(emergency_plan.emergency_admin_cancel_approve, pattern="^emg_cancelapprove_"))


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
