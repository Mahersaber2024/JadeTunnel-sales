import logging
import uuid
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
from telegram.ext import ContextTypes, ConversationHandler
from urllib.parse import urlparse, parse_qs
import lifeline

logger = logging.getLogger(__name__)
from telegram import LinkPreviewOptions
from bot_settings import (
    get_sponsor_channel,
    get_sponsor_channel_title,
    is_membership_required,
    get_support_username,
    get_signup_bonus,
    get_referral_bonus_inviter,
    get_referral_bonus_invitee,
    get_special_panel_id,
    get_special_panel_commission_percent,
    is_hybrid_payment_enabled,
    get_card_number, 
    get_card_holder,
    get_card_bank,   
)

from panel_manager import get_panel_manager
from client_manager import PanelClient, PanelClientFactory, get_panel_client
from bot_settings import get_combined_sub_base_url 
# ============ Import Logger Functions ============
from logger_bot import (
    log_user_join,
    log_invoice_issued,
    log_purchase_details,
    log_payment_card,
    log_wallet_payment,
    log_subscription_created,
    log_panel_error,
    log_user_activity,
    log_balance_change,
    log_referral_bonus,
    log_volume_added,
    log_system_error
)

# Constants
AMOUNT_SELECTION, CONFIRM_CHARGE, PAYMENT_METHOD = range(3)
VOLUME_SELECTION = 3
PRIORITY_TYPE_ORDER = ['tcp', 'grpc']


INBOUND_IDS = [82, 80, 81]
# ============ تنظیمات طرح اضطراری ============
EMERGENCY_PLAN_VOLUME_GB = 0
EMERGENCY_PLAN_DURATION_DAYS = 30

# Global database instance
db = None

def set_db(database):
    global db
    db = database

# ============ Pending Card Payments Awaiting Admin Approval ============
# request_id -> dict حاوی تمام اطلاعات لازم برای نهایی‌سازی پرداخت پس از تایید ادمین
PENDING_PAYMENTS: dict = {}

# آیدی عددی ادمین‌هایی که مجاز به تایید/رد فاکتور هستند.
# اگر خالی بماند، هر کسی که در تاپیک مربوطه در گروه لاگ روی دکمه بزند مجاز خواهد بود.
ADMIN_IDS: list = []


async def send_payment_approval_request(bot, request_type: str, request_id: str, request_data: dict):
    """
    ارسال فاکتور به تاپیک مربوطه در گروه لاگ همراه با دکمه‌های شیشه‌ای
    «✅ تایید» و «❌ رد» برای بررسی توسط ادمین.
    """
    from logger_bot import LOG_GROUP_ID, get_thread_id, Topics, format_user_full

    if not LOG_GROUP_ID:
        logger.warning("LOG_GROUP_ID تنظیم نشده؛ درخواست تایید پرداخت ارسال نشد.")
        return

    user_info = format_user_full(
        request_data.get('user_id'),
        request_data.get('username'),
        request_data.get('first_name'),
        request_data.get('last_name'),
    )

    card_digits = request_data.get('card_digits', '****')
    amount = request_data.get('amount', 0)
    amount_str = f"{amount:,}"

    if request_type == 'purchase':
        desc = f"📦 پلن: {request_data.get('plan_name')}"
    elif request_type == 'volume':
        desc = f"📊 حجم درخواستی: {request_data.get('volume')} گیگ"
    elif request_type == 'charge':
        desc = "💰 شارژ کیف پول"
    else:
        desc = ""

    text = (
        f"🧾 <b>فاکتور در انتظار تایید</b>\n\n"
        f"{user_info}\n"
        f"{desc}\n"
        f"💰 مبلغ: {amount_str} تومان\n"
        f"🔢 چهار رقم آخر کارت: <code>{card_digits}</code>\n\n"
        f"🆔 شناسه درخواست: <code>{request_id}</code>"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید و ارسال", callback_data=f"admin_approve_{request_id}"),
            InlineKeyboardButton("❌ رد کردن", callback_data=f"admin_reject_{request_id}")
        ]
    ])

    thread_id = get_thread_id(Topics.CARD_PAYMENT)

    try:
        await bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=text,
            parse_mode='HTML',
            message_thread_id=thread_id,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error sending payment approval request: {e}")

async def admin_approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    ادمین روی دکمه «✅ تایید» فاکتور کلیک کرده است.
    بسته به نوع درخواست، کانفیگ ساخته/حجم اضافه/کیف پول شارژ می‌شود و نتیجه به کاربر ارسال می‌شود.
    """
    query = update.callback_query
    bot = context.bot
    admin = query.from_user

    request_id = query.data.replace("admin_approve_", "")
    request_data = PENDING_PAYMENTS.get(request_id)

    if not request_data:
        await query.answer("❌ این درخواست دیگر معتبر نیست (شاید قبلاً بررسی شده).", show_alert=True)
        return

    if ADMIN_IDS and admin.id not in ADMIN_IDS:
        await query.answer("⛔️ شما اجازه تایید فاکتور را ندارید.", show_alert=True)
        return

    await query.answer("⏳ در حال پردازش...")

    req_type = request_data.get('type')
    user_id = request_data.get('user_id')

    try:
        if req_type == 'purchase':
            selected_plan = request_data['selected_plan']
            protocol = request_data.get('protocol', 'v2ray')

            success, msg, sub_data = await create_subscription_for_purchase(
                user_id=user_id,
                selected_plan=selected_plan,
                protocol=protocol
            )

            if not success:
                wallet_used = request_data.get('wallet_used', 0)
                if wallet_used:
                    db.update_balance(user_id, wallet_used)
                    db.add_transaction(
                        user_id, wallet_used, "refund",
                        "بازگشت وجه کسر شده از کیف پول (خطا در ایجاد کلاینت)"
                    )
                await log_panel_error(
                    bot, user_id, "ایجاد کلاینت (تایید ادمین)", msg,
                    plan_name=selected_plan.get('name'),
                    username=request_data.get('username'),
                    first_name=request_data.get('first_name'),
                    last_name=request_data.get('last_name')
                )
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text="❌ متاسفانه در ایجاد اشتراک شما خطایی رخ داد. لطفاً با پشتیبانی تماس بگیرید."
                    )
                except Exception as e:
                    logger.error(f"Error notifying user of creation failure: {e}")

                try:
                    await query.edit_message_text(
                        query.message.text_html + "\n\n❌ <b>خطا در ایجاد کلاینت — به کاربر اطلاع داده شد</b>",
                        parse_mode='HTML'
                    )
                except Exception:
                    pass

                PENDING_PAYMENTS.pop(request_id, None)
                return

            total_price = request_data.get('total_price', selected_plan['price'])
            wallet_used = request_data.get('wallet_used', 0)
            card_amount = request_data.get('amount', total_price)

            db.add_transaction(
                user_id, card_amount, "card_payment",
                f"پرداخت کارت به کارت - {selected_plan['name']}" +
                (f" (+ {wallet_used:,} از کیف پول)" if wallet_used else "")
            )

            await log_payment_card(
                bot, user_id, selected_plan['name'], total_price,
                request_data.get('card_digits', '****'), 'success',
                username=request_data.get('username'),
                first_name=request_data.get('first_name'),
                last_name=request_data.get('last_name')
            )

            # ============ افزایش عمر چراغ جاده تونل ============
            await lifeline.add_day(bot)

            # ============ دریافت نام پنل ============
            panel_name = "پنل پیش‌فرض"
            panel_id = sub_data.get('panel_id')
            if panel_id:
                from panel_manager import get_panel_manager
                panel_manager = get_panel_manager()
                panel_data = panel_manager.get_panel(panel_id)
                if panel_data:
                    panel_name = panel_data.get('name', panel_id)

            subscription_id = sub_data.get('subscription_id')
            price_str = f"{selected_plan['price']:,}"

            # ============ لینک این طرح خریداری‌شده ============
            single_link = get_single_sub_link(subscription_id)
            link_line = f"\nلینک اشتراک شما (سازگار با نت ملی)\n<code>{single_link}</code>\n" if single_link else ""

            keyboard = []
            if subscription_id:
                keyboard.append([InlineKeyboardButton("🔧 دریافت کانفیگ", callback_data=f"get_config_{subscription_id}")])

            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ پرداخت شما تایید شد!\n\n"
                    f"🖥 پنل: {panel_name}\n"
                    f"📦 پلن: {selected_plan['name']}\n"
                    f"💰 مبلغ: {price_str} تومان\n"
                    f"{link_line}\n"
                    f"دریافت کانفیگ همینجا؛ دکمه زیر را بزنید 👇"
                ),
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
            )

        elif req_type == 'volume':
            subscription_id = request_data['subscription_id']
            volume = request_data['volume']
            price = request_data['amount']

            total_price = request_data.get('total_price', price)
            wallet_used = request_data.get('wallet_used', 0)
            db.add_transaction(
                user_id, -total_price, "purchase",
                f"افزایش {volume} گیگ حجم اضافی (کارت به کارت)" +
                (f" - شامل {wallet_used:,} تومان از کیف پول" if wallet_used else "")
            )
            db.add_volume_to_subscription(subscription_id, volume)

            # حجم کل جدید را از دیتابیس بخوان (نه از پنل)
            subscription = db.get_subscription(subscription_id)
            if subscription and subscription.get('email'):
                from client_manager import get_panel_client
                panel_client = get_panel_client()
                panel_success, panel_msg, new_total = panel_client.update_client_volume(
                    subscription['email'], subscription['remaining_volume']
                )
                if not panel_success:
                    logger.error(f"Failed to update panel volume for {subscription['email']}: {panel_msg}")

            await log_volume_added(
                bot, user_id, subscription_id, volume, price, 'کارت به کارت',
                username=request_data.get('username'),
                first_name=request_data.get('first_name'),
                last_name=request_data.get('last_name')
            )

            remaining_volume = subscription.get('remaining_volume', 0) if subscription else 0
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ پرداخت شما تایید شد و {volume} گیگ حجم اضافی به اشتراک شما اضافه شد!\n\n"
                    f"📊 حجم اشتراک: {remaining_volume} گیگ"
                )
            )

        elif req_type == 'charge':
            amount = request_data['amount']
            db.update_balance(user_id, amount)
            user = db.get_user(user_id)
            new_balance = user['balance'] if user else amount

            await log_balance_change(
                bot, user_id, amount, new_balance, "شارژ کیف پول (کارت به کارت - تایید ادمین)",
                username=request_data.get('username'),
                first_name=request_data.get('first_name'),
                last_name=request_data.get('last_name')
            )

            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"✅ شارژ کیف پول شما تایید شد!\n\n"
                    f"💰 مبلغ: {amount:,} تومان\n"
                    f"💳 موجودی جدید: {new_balance:,} تومان"
                )
            )

        # بروزرسانی پیام ادمین برای نشان دادن نتیجه تایید
        try:
            await query.edit_message_text(
                query.message.text_html + f"\n\n✅ <b>تایید شد توسط:</b> {admin.first_name or admin.id}",
                parse_mode='HTML'
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error approving payment {request_id}: {e}")
        await log_system_error(bot, str(e), context=f"admin_approve_payment - request_id={request_id}")
        await query.answer("❌ خطایی رخ داد؛ لاگ سیستم را بررسی کنید.", show_alert=True)
    finally:
        PENDING_PAYMENTS.pop(request_id, None)

async def admin_reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ادمین روی دکمه «❌ رد» فاکتور کلیک کرده است."""
    query = update.callback_query
    bot = context.bot
    admin = query.from_user

    request_id = query.data.replace("admin_reject_", "")
    request_data = PENDING_PAYMENTS.get(request_id)

    if not request_data:
        await query.answer("❌ این درخواست دیگر معتبر نیست (شاید قبلاً بررسی شده).", show_alert=True)
        return

    if ADMIN_IDS and admin.id not in ADMIN_IDS:
        await query.answer("⛔️ شما اجازه رد کردن فاکتور را ندارید.", show_alert=True)
        return

    await query.answer("رد شد")

    user_id = request_data.get('user_id')

    # ============ بازگشت مبلغ کسر شده از کیف پول (پرداخت ترکیبی) در صورت وجود ============
    wallet_used = request_data.get('wallet_used', 0)
    if wallet_used:
        db.update_balance(user_id, wallet_used)
        db.add_transaction(
            user_id, wallet_used, "refund",
            "بازگشت وجه کسر شده از کیف پول (رد پرداخت توسط ادمین)"
        )

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                "❌ متاسفانه پرداخت شما تایید نشد.\n\n"
                "این موضوع معمولاً به دلیل عدم تطابق مبلغ یا شماره کارت واریزی رخ می‌دهد.\n"
                "لطفاً با پشتیبانی تماس بگیرید."
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📨 پشتیبانی", url="https://t.me/jadetunnel")]
            ])
        )
    except Exception as e:
        logger.error(f"Error notifying user of rejection: {e}")

    try:
        await query.edit_message_text(
            query.message.text_html + f"\n\n❌ <b>رد شد توسط:</b> {admin.first_name or admin.id}",
            parse_mode='HTML'
        )
    except Exception:
        pass

    PENDING_PAYMENTS.pop(request_id, None)
   
def get_main_menu():
    """Create main menu keyboard"""
    keyboard = [
        [KeyboardButton("🛒 خرید VPN")],
        [
            KeyboardButton("🗂 حساب کاربری"),
            KeyboardButton("📒 اشتراک ها")
        ],
        [
            KeyboardButton("📝 راهنما"),
            KeyboardButton("💰 افزایش موجودی")
        ],
        [
            KeyboardButton("➕ افزایش حجم اضافی"),
            KeyboardButton("📨 پشتیبانی")
        ],
        [
            KeyboardButton("👥 دعوت از دوستان"),
            KeyboardButton("🎁 ارسال هدیه")
        ],
        [
            KeyboardButton("🆘 طرح اضطراری")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ====================== Channel Membership Check ======================
async def check_channel_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if user is member of the configured sponsor channel"""
    if not is_membership_required():
        return True

    channel = get_sponsor_channel()
    try:
        chat_member = await context.bot.get_chat_member(
            chat_id=channel,
            user_id=update.effective_user.id
        )
        return chat_member.status in ['member', 'administrator', 'creator']
    except:
        return False

async def ensure_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ensure user is member, if not show message and return False"""
    if not is_membership_required():
        return True

    user_id = update.effective_user.id
    
    # ============ بررسی ادمین بودن ============
    # ادمین‌ها نیازی به عضویت در کانال ندارند
    from admin import is_admin
    if is_admin(user_id):
        return True

    if await check_channel_membership(update, context):
        return True

    channel = get_sponsor_channel()
    channel_title = get_sponsor_channel_title()
    channel_url = f"https://t.me/{channel.lstrip('@')}"
    safe_title = html_lib.escape(channel_title)

    keyboard = [
        [InlineKeyboardButton("📢 عضویت در کانال", url=channel_url)]
    ]

    text = (
        f"📢 <b>برای استفاده از ربات، ابتدا در کانال زیر عضو شوید:</b>\n\n"
        f"🔗 <a href=\"{channel_url}\">{safe_title}</a>\n\n"
        f"⚠️ پس از عضویت، مجدداً روی دکمه مورد نظر کلیک کنید."
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    return False

async def membership_required(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check membership and return True/False"""
    return await ensure_membership(update, context)

# ============ Wrapper ============
def require_membership(func):
    """Decorator to check channel membership before executing handler"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await ensure_membership(update, context):
            return
        return await func(update, context)
    return wrapper


# ============ Start Handler ============
from telegram.constants import ParseMode

# ============ Start Handler ============
@require_membership
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    bot = context.bot 
    if not await ensure_membership(update, context):
        return

    user = update.effective_user
    user_id = user.id

    existing_user = db.get_user(user_id)

    referred_by = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            referred_by = int(context.args[0].split("_")[1])
        except:
            pass

    is_new_user = not existing_user

    if is_new_user:
        success = db.add_user(user_id, user.username, user.first_name, referred_by)
        # ============ لاگ عضویت کاربر جدید ============
        if success:
            await log_user_join(bot, user_id, user.username, user.first_name, referred_by, last_name=user.last_name)

            # ============ پردازش پاداش دعوت (اگر دعوت‌کننده معتبر باشد) ============
            if referred_by and referred_by != user_id:
                inviter = db.get_user(referred_by)
                if inviter:
                    inviter_bonus = get_referral_bonus_inviter()
                    invitee_bonus = get_referral_bonus_invitee()

                    # پاداش دعوت‌کننده
                    db.update_balance(referred_by, inviter_bonus)
                    db.add_transaction(
                        referred_by, inviter_bonus, "referral_bonus",
                        f"پاداش دعوت کاربر {user_id}"
                    )

                    # پاداش اضافه‌ی کاربر جدید (علاوه بر هدیه ثبت‌نام)
                    if invitee_bonus > 0:
                        db.update_balance(user_id, invitee_bonus)
                        db.add_transaction(
                            user_id, invitee_bonus, "referral_bonus",
                            f"پاداش دعوت شدن توسط {referred_by}"
                        )

                    # ============ لاگ پاداش دعوت ============
                    inviter_updated = db.get_user(referred_by)
                    try:
                        await log_referral_bonus(
                            bot, referred_by, inviter_bonus, user_id,
                            username=inviter.get('username'),
                            first_name=inviter.get('first_name'),
                            last_name=inviter.get('last_name'),
                            new_username=user.username,
                            new_first_name=user.first_name,
                            new_last_name=user.last_name
                        )
                    except Exception as e:
                        logger.error(f"Error logging referral bonus: {e}")

                    # ============ تبریک و اطلاع‌رسانی به دعوت‌کننده ============
                    inviter_new_balance = inviter_updated['balance'] if inviter_updated else inviter_bonus
                    inviter_bonus_str = f"{inviter_bonus:,}"
                    inviter_balance_str = f"{inviter_new_balance:,}"
                    new_user_name = user.first_name or (f"@{user.username}" if user.username else str(user_id))

                    try:
                        await bot.send_message(
                            chat_id=referred_by,
                            text=(
                                f"🎉 <b>یه هم‌مسیر جدید به جاده تونل پیوست!</b>\n\n"
                                f"دوستتون «{html_lib.escape(new_user_name)}» با لینک دعوت اختصاصی شما عضو ربات شد 🌿\n\n"
                                f"🎁 به همین مناسبت <b>{inviter_bonus_str} تومان</b> به کیف پولتون اضافه شد!\n"
                                f"💳 موجودی جدید: <b>{inviter_balance_str} تومان</b>"
                            ),
                            parse_mode=ParseMode.HTML
                        )
                    except Exception as e:
                        logger.error(f"Could not notify inviter {referred_by}: {e}")
    else:
        success = False

    signup_bonus_str = f"{get_signup_bonus():,}"

    # بخش‌های مشترک پیام
    header = (
        "🚀 <b>به جاده تونل خوش آمدید!</b>\n"
        "<i>سریع‌ترین و مطمئن‌ترین مسیر برای اینترنت بدون محدودیت</i> 🌍\n\n"
        "اینجا دیگه نگران قطعی، کندی یا دردسرهای اینترنتی نباش!\n"
        "ما با جدیدترین سرورها و بالاترین کیفیت، تجربه‌ای حرفه‌ای رو برات به ارمغان آوردیم.\n\n"
        "✨ <b>چرا جاده تونل؟</b>\n"
        "🔹 <u>سرعت بالا</u> و اتصال پایدار\n"
        "🔹 پشتیبانی همراه شما در تمام مراحل\n"
        "🔹 تنوع در طرح‌های متناسب با هر نیاز\n"
        "🔹 قیمت مناسب، بدون هزینه پنهان\n\n"
    )

    footer = (
        "🔥 ما اینجاییم تا اینترنت رو به آرامش تبدیل کنیم.\n"
        "برای شروع، از دکمه 🛒 <b>خرید VPN</b> استفاده کن.\n\n"
        "<b>جاده تونل</b>\n"
        "<i>همراه همیشگی تو در دنیای دیجیتال</i> 🌿"
    )

    if is_new_user and success and referred_by:
        # کاربر جدید که با لینک دعوت وارد شده - پیام کوتاه
        welcome_text = (
            "🚀 <b>به جاده تونل خوش آمدید!</b>\n"
            "🎉 شما با دعوت دوستتون وارد شدید!\n"
            f"🎁 <b>{signup_bonus_str} تومان</b> هدیه ویژه به حساب شما اضافه شد!\n\n"
            "<b>جاده تونل</b>\n"
            "<i>همراه همیشگی تو در دنیای دیجیتال</i> 🌿"
        )
    elif is_new_user and success:
        bonus_line = f"🎁 <b>{signup_bonus_str} تومان</b> هدیه ویژه به حساب شما اضافه شد!\n"
        welcome_text = header + bonus_line + "\n" + footer
    elif is_new_user and not success:
        welcome_text = header + footer
    else:
        # کاربر قدیمی - بدون بخش راهنما
        welcome_text = (
            header +
            "🔥 ما اینجاییم تا اینترنت رو به آرامش تبدیل کنیم.\n"
            "برای شروع، از دکمه 🛒 <b>خرید VPN</b> استفاده کن.\n\n"
            "<b>جاده تونل</b>\n"
            "<i>همراه همیشگی تو در دنیای دیجیتال</i> 🌿"
        )

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu()
    )
    
# ============ Buy VPN Handlers ============
@require_membership
async def buy_vpn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy VPN - Protocol selection"""
    keyboard = [
        [InlineKeyboardButton("🚀 V2Ray | ویتوری", callback_data="protocol_v2ray")],
        [InlineKeyboardButton("🌐 WireGuard", callback_data="protocol_wireguard")],
        [InlineKeyboardButton("🔓 OpenVPN", callback_data="protocol_openvpn")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
   
    await update.message.reply_text(
        "🔌 انتخاب پروتکل VPN\n\n"
        "✅ تمامی پروتکل‌های زیر برای دور زدن فیلترینگ و استفاده در سوشال مدیا و گیم کاملاً مناسب هستند.\n\n"
        "⭐️ پیشنهاد ویژه ما: V2Ray | ویتوری 🌐\n\n"
        "👇 لطفاً پروتکل مورد نظر خود را انتخاب کنید:",
        reply_markup=reply_markup
    )
    
@require_membership
async def buy_vpn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy VPN callback - called from inline keyboard"""
    query = update.callback_query
    await query.answer()
   
    keyboard = [
        [InlineKeyboardButton("🚀 V2Ray | ویتوری", callback_data="protocol_v2ray")],
        [InlineKeyboardButton("🌐 WireGuard", callback_data="protocol_wireguard")],
        [InlineKeyboardButton("🔓 OpenVPN", callback_data="protocol_openvpn")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
   
    await query.edit_message_text(
        "🔌 انتخاب پروتکل VPN\n\n"
        "✅ تمامی پروتکل‌های زیر برای دور زدن فیلترینگ و استفاده در سوشال مدیا و گیم کاملاً مناسب هستند.\n\n"
        "⭐️ پیشنهاد ویژه ما: V2Ray | ویتوری 🌐\n\n"
        "👇 لطفاً پروتکل مورد نظر خود را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def protocol_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Protocol selection callback"""
    query = update.callback_query
    protocol = query.data.replace("protocol_", "")
    context.user_data['selected_protocol'] = protocol
   
    # === فقط V2Ray مجاز است، اما برای سایر پروتکل‌ها پیام هشدار نمایش می‌دهیم ===
    if protocol != "v2ray":
        alert_message = (
            "⚠️ فعلاً فقط پروتکل V2Ray | ویتوری ارائه می‌شود!\n\n"
            "لطفاً از پروتکل V2Ray | ویتوری استفاده نمایید."
        )
        await query.answer(alert_message, show_alert=True)
        return
    
    await query.answer()
    
    # نمایش گزینه‌های طرح فروش به صورت کنار هم + دکمه شارژ دلخواه
    keyboard = [
        [
            InlineKeyboardButton("🆕 طرح جدید", callback_data="plan_type_new"),
            InlineKeyboardButton("📦 طرح قدیمی", callback_data="plan_type_old")
        ],
        [InlineKeyboardButton("🔥 طرح شارژ دلخواه", callback_data="plan_type_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎯 انتخاب نوع طرح\n\n"
        "لطفاً نوع طرح فروش را انتخاب کنید:",
        reply_markup=reply_markup
    )
    
@require_membership
async def back_to_plan_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to plan type selection"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("🆕 طرح جدید (پیشنهادی)", callback_data="plan_type_new"),
            InlineKeyboardButton("📦 طرح قدیمی", callback_data="plan_type_old")
        ],
        [InlineKeyboardButton("🔥 طرح شارژ دلخواه", callback_data="plan_type_custom")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎯 انتخاب نوع طرح\n\n"
        "لطفاً نوع طرح فروش را انتخاب کنید:",
        reply_markup=reply_markup
    )

@require_membership
async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Plan selection callback"""
    query = update.callback_query
    await query.answer()
    
    plan_type = context.user_data.get('plan_type', 'new')
    protocol = context.user_data.get('selected_protocol', 'v2ray')
    
    # فقط V2Ray مجاز است
    if protocol != "v2ray":
        await query.edit_message_text(
            "❌ این پروتکل در حال حاضر ارائه نمی‌شود.\n\n"
            "لطفاً پروتکل V2Ray | ویتوری را انتخاب کنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت به پروتکل‌ها", callback_data="back_to_protocols")]
            ])
        )
        return
    
    # طرح‌های جدید
    new_plans = [
        {"name": "🟢 متعادل", "price": 259000, "days": 30, "volume": 105, "emoji": "🟢", "daily_volume": 3.5},
        {"name": "🔥 منصفانه", "price": 312000, "days": 30, "volume": 150, "emoji": "🔥", "daily_volume": 5},
        {"name": "💎 حرفه‌ای", "price": 492000, "days": 30, "volume": 300, "emoji": "💎", "daily_volume": 10}
    ]
    
    # طرح قدیمی
    old_plan = {"name": "📦 نامحدود تک کاربر", "price": 199000, "days": 30, "volume": 0, "emoji": "📦"}
    
    # تشخیص نوع طرح از callback_data
    callback_data = query.data
    if callback_data.startswith("plan_new_"):
        plan_index = int(callback_data.replace("plan_new_", ""))
        selected_plan = new_plans[plan_index]
        plan_type_db = 'new'
    elif callback_data.startswith("plan_old_"):
        selected_plan = old_plan
        plan_type_db = 'old'
    else:
        # Fallback برای طرح‌های قدیمی
        plan_index = int(callback_data.replace("plan_", ""))
        selected_plan = new_plans[plan_index] if plan_index < len(new_plans) else new_plans[0]
        plan_type_db = 'new'
    
    # ذخیره plan_type در selected_plan و context
    selected_plan['plan_type'] = plan_type_db
    context.user_data['selected_plan'] = selected_plan
    context.user_data['plan_type'] = plan_type_db
    context.user_data['plan_type_name'] = plan_type_db
    
    user_id = query.from_user.id
    user = db.get_user(user_id)
    balance = user['balance'] if user else 0
   
    protocol_names = {
        "v2ray": "V2Ray | ویتوری"
    }
   
    price_str = f"{selected_plan['price']:,}"
    balance_str = f"{balance:,}"
    
    # نمایش حجم روزانه به جای حجم کل
    if 'daily_volume' in selected_plan:
        volume_text = f"{selected_plan['daily_volume']} گیگ روزانه"
    else:
        volume_text = f"{selected_plan['volume']} گیگابایت"
   
    # دکمه‌های کنار هم (کیف پول و کارت به کارت)
    keyboard = [
        [
            InlineKeyboardButton("💰 کیف پول", callback_data="pay_wallet"),
            InlineKeyboardButton("🏦 کارت به کارت", callback_data="pay_card")
        ],
        [InlineKeyboardButton("🔙 بازگشت به پلن‌ها", callback_data="back_to_plans")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
   
    await query.edit_message_text(
        f"📋 جزئیات سفارش:\n\n"
        f"🔄 پروتکل: {protocol_names.get(protocol, protocol)}\n"
        f"📦 پلن انتخابی: {selected_plan['name']}\n\n"
        f"💰 قیمت: {price_str} تومان\n\n"
        f"⏰ مدت: {selected_plan['days']} روز\n"
        f"📊 حجم: {volume_text}\n\n"
        f"💳 موجودی کیف پول: {balance_str} تومان\n\n"
        f"لطفاً روش پرداخت را انتخاب کنید:",
        reply_markup=reply_markup
    )

@require_membership   
async def plan_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plan type selection"""
    query = update.callback_query
    await query.answer()
    
    plan_type = query.data.replace("plan_type_", "")
    context.user_data['plan_type'] = plan_type
    
    if plan_type == "new":
        # نمایش طرح‌های جدید
        await show_new_plans(update, context)
    elif plan_type == "old":
        # نمایش طرح قدیمی
        await show_old_plan(update, context)
    elif plan_type == "custom":
        # هدایت به طرح شارژ دلخواه
        await custom_charge_from_plan(update, context)
        
@require_membership
async def custom_charge_from_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show custom charge plan from plan selection"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # بررسی اینکه کاربر اشتراک شارژ دلخواه دارد
    subscriptions = db.get_active_subscriptions(user_id)
    has_custom_charge = False
    for sub in subscriptions:
        if sub.get('plan_type') == 'custom_charge':
            has_custom_charge = True
            break
    
    keyboard = [
        [InlineKeyboardButton("💳 خرید اشتراک شارژ دلخواه", callback_data="custom_charge_buy")],
        [InlineKeyboardButton("🔙 بازگشت به انتخاب طرح", callback_data="back_to_plan_type")]
    ]
    
    if has_custom_charge:
        keyboard.insert(1, [InlineKeyboardButton("➕ افزایش حجم اضافی", callback_data="add_extra_volume_from_plan")])
    
    await query.edit_message_text(
        f"طرح شارژ دلخواه\n\n"
        f"اشتراک ماهانه\n"
        f"قیمت: ۱۱۲,۰۰۰ تومان (همراه با ۵ گیگ)\n\n"
        f"قیمت هر گیگ اضافی: ۱,۹۵۰ تومان\n\n"
        f'<a href="https://t.me/jadetunnell/25">جزئیات بیشتر</a>',
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

@require_membership
async def show_old_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show old plan option"""
    query = update.callback_query
    
    old_plan = {"name": "نامحدود تک کاربر", "price": 199000, "days": 30, "volume": 0, "emoji": "📦"}
    
    keyboard = [
        [InlineKeyboardButton(
            f"📦 {old_plan['name']} | ۱۹۹,۰۰۰ تومان",
            callback_data="plan_old_0"
        )],
        [InlineKeyboardButton("🔙 بازگشت به انتخاب طرح", callback_data="back_to_plan_type")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📦 طرح قدیمی\n\n"
        f"نامحدود تک کاربر → ۱۹۹,۰۰۰ تومان\n"
        f"(بعضی اپراتورها اختلال دارد)\n\n"
        f"⚠️ توجه: این طرح محدودیت تعداد کاربر دارد\n\n"
        f'<a href="https://t.me/jadetunnell/13">جزئیات بیشتر</a>',
        reply_markup=reply_markup,
        parse_mode='HTML',
        disable_web_page_preview=True
    )

@require_membership
async def show_new_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show new plan options"""
    query = update.callback_query
    protocol = context.user_data.get('selected_protocol', 'v2ray')
    
    # طرح‌های جدید
    new_plans = [
        {"name": "🟢 متعادل", "price": 259000, "days": 30, "volume": 105, "emoji": "🟢", "daily_volume": 3.5},
        {"name": "🔥 منصفانه", "price": 312000, "days": 30, "volume": 150, "emoji": "🔥", "daily_volume": 5},
        {"name": "💎 حرفه‌ای", "price": 492000, "days": 30, "volume": 300, "emoji": "💎", "daily_volume": 10}
    ]
    
    keyboard = []
    for i, plan in enumerate(new_plans):
        price_str = f"{plan['price']:,}"
        keyboard.append([
            InlineKeyboardButton(
                f"{plan['emoji']} {plan['name']} | {price_str} تومان",
                callback_data=f"plan_new_{i}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به انتخاب طرح", callback_data="back_to_plan_type")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"نامحدود\n"
        f"سرعت عالی + پایداری بالا + بدون اختلال در اپراتورها\n"
        f"🔓 بدون محدودیت تعداد کاربر | 📅 ماهانه\n\n"
        f"لطفاً پلن مورد نظر را انتخاب کنید:\n\n"
        f'<a href="https://t.me/jadetunnell/13">جزئیات بیشتر</a>',  # <-- لینک صحیح رو جایگزین کن
        reply_markup=reply_markup,
        parse_mode='HTML',
        disable_web_page_preview=True
    )
    
@require_membership
async def add_extra_volume_from_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add extra volume from plan page - shows subscription selection if multiple"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = db.get_user(user_id)
    
    # بررسی اینکه کاربر اشتراک شارژ دلخواه دارد
    custom_subs = db.get_custom_charge_subscriptions(user_id)
    
    if not custom_subs:
        await query.answer(
            "❌ شما اشتراک شارژ دلخواه ندارید!\n"
            "لطفاً ابتدا اشتراک را خریداری کنید.",
            show_alert=True
        )
        return
    
    if len(custom_subs) == 1:
        # فقط یک اشتراک دارد، مستقیم برو مرحله بعد
        context.user_data['target_subscription_id'] = custom_subs[0]['id']
        balance = user['balance'] if user else 0
        
        await query.edit_message_text(
            f"➕ افزایش حجم اضافی\n\n"
            f"💰 موجودی کیف پول: {balance:,} تومان\n"
            f"🔥 هر گیگ اضافی: ۱,۹۵۰ تومان\n\n"
            f"لطفاً حجم مورد نظر را به صورت عدد (فقط عدد صحیح) وارد کنید:\n"
            f"مثال: 5\n\n"
            f"⚠️ حداقل حجم: 1 گیگ\n"
            f"⚠️ فقط عدد صحیح وارد کنید (اعشاری قبول نیست)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ انصراف", callback_data="cancel_extra_volume")]
            ])
        )
        return VOLUME_SELECTION
    
    # چند اشتراک دارد، از کاربر بخواه انتخاب کند
    keyboard = []
    for idx, sub in enumerate(custom_subs, 1):
        keyboard.append([InlineKeyboardButton(
            f"اشتراک {idx} (حجم اشتراک: {sub.get('remaining_volume', 0)} گیگ)",
            callback_data=f"select_sub_for_volume_{sub['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_custom_charge_from_plan")])
    
    await query.edit_message_text(
        "🔥 شما چند اشتراک شارژ دلخواه فعال دارید.\n\n"
        "لطفاً مشخص کنید حجم را برای کدام اشتراک اضافه کنیم:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return VOLUME_SELECTION

async def back_to_custom_charge_from_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to custom charge plan page"""
    query = update.callback_query
    await query.answer()
    
    # بازگشت به صفحه طرح شارژ دلخواه
    await custom_charge_from_plan(update, context)

async def custom_charge_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy custom charge plan - show payment method selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = db.get_user(user_id)
    balance = user['balance'] if user else 0  # نیاز هست برای نمایش در جزئیات سفارش
    
    # تنظیم selected_plan برای پرداخت
    context.user_data['selected_plan'] = {
        "name": "🔥 طرح شارژ دلخواه",
        "price": 112000,
        "days": 30,
        "volume": 5,
        "is_custom_charge": True,
        "plan_type": "custom_charge"
    }
    context.user_data['plan_type'] = "custom_charge"
    context.user_data['plan_type_name'] = "custom"
    
    price_str = "۱۱۲,۰۰۰"
    balance_str = f"{balance:,}"
    
    keyboard = [
        [
            InlineKeyboardButton("💰 کیف پول", callback_data="pay_wallet"),
            InlineKeyboardButton("🏦 کارت به کارت", callback_data="pay_card")
        ],
        [InlineKeyboardButton("🔙 بازگشت به طرح شارژ دلخواه", callback_data="back_to_custom_charge")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📋 جزئیات سفارش:\n\n"
        f"🔥 طرح: شارژ دلخواه\n\n"
        f"💰 قیمت: {price_str} تومان\n\n"
        f"⏰ مدت: 30 روز\n"
        f"📊 حجم: ۵ گیگ اولیه + امکان افزایش حجم اضافی\n\n"
        f"💳 موجودی کیف پول: {balance_str} تومان\n\n"  # اینجا نمایش داده میشه
        f"لطفاً روش پرداخت را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def add_extra_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for adding extra volume - from main menu"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد. لطفا با /start شروع کنید.")
        return
    
    custom_subs = db.get_custom_charge_subscriptions(user_id)
    
    if not custom_subs:
        await update.message.reply_text(
            "❌ شما اشتراک شارژ دلخواه ندارید!\n"
            "لطفاً ابتدا از طریق بخش خرید VPN، طرح شارژ دلخواه را خریداری کنید.",
            reply_markup=get_main_menu()
        )
        return
    
    if len(custom_subs) == 1:
        # فقط یک اشتراک دارد، مستقیم برو مرحله بعد
        context.user_data['target_subscription_id'] = custom_subs[0]['id']
        
        balance = user['balance']
        
        await update.message.reply_text(
            f"➕ افزایش حجم اضافی\n\n"
            f"💰 موجودی کیف پول: {balance:,} تومان\n"
            f"🔥 هر گیگ اضافی: ۱,۹۵۰ تومان\n\n"
            f"لطفاً حجم مورد نظر را به صورت عدد (فقط عدد صحیح) وارد کنید:\n"
            f"مثال: 5\n\n"
            f"⚠️ حداقل حجم: 1 گیگ\n"
            f"⚠️ فقط عدد صحیح وارد کنید (اعشاری قبول نیست)",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("❌ انصراف")]], 
                resize_keyboard=True
            )
        )
        return VOLUME_SELECTION
    
    # چند اشتراک دارد، از کاربر بخواه انتخاب کند
    keyboard = []
    for idx, sub in enumerate(custom_subs, 1):
        keyboard.append([InlineKeyboardButton(
            f"اشتراک {idx} (حجم اشتراک: {sub.get('remaining_volume', 0)} گیگ)",
            callback_data=f"select_sub_for_volume_{sub['id']}"
        )])
    
    await update.message.reply_text(
        "🔥 شما چند اشتراک شارژ دلخواه فعال دارید.\n\n"
        "لطفاً مشخص کنید حجم را برای کدام اشتراک اضافه کنیم:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return VOLUME_SELECTION

async def select_sub_for_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User picked which subscription to add volume to"""
    query = update.callback_query
    await query.answer()
    
    sub_id = int(query.data.replace("select_sub_for_volume_", ""))
    context.user_data['target_subscription_id'] = sub_id
    
    user_id = query.from_user.id
    user = db.get_user(user_id)
    balance = user['balance'] if user else 0
    
    subscription = db.get_subscription(sub_id)
    remaining_volume = subscription.get('remaining_volume', 0) if subscription else 0
    
    await query.edit_message_text(
        f"➕ افزایش حجم اضافی\n\n"
        f"💰 موجودی کیف پول: {balance:,} تومان\n"
        f"📊 حجم اشتراک: {remaining_volume} گیگ\n"
        f"🔥 هر گیگ اضافی: ۱,۹۵۰ تومان\n\n"
        f"لطفاً حجم مورد نظر را به صورت عدد (فقط عدد صحیح) وارد کنید:\n"
        f"مثال: 5\n\n"
        f"⚠️ حداقل حجم: 1 گیگ",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ انصراف", callback_data="cancel_extra_volume")]
        ])
    )
    await query.message.reply_text(
        "منتظر ورود عدد حجم هستم...",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ انصراف")]],
            resize_keyboard=True
        )
    )
    return VOLUME_SELECTION

async def handle_volume_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle volume input from user"""
    text = update.message.text.strip()
    
    if text == "❌ انصراف":
        await update.message.reply_text(
            "❌ عملیات افزایش حجم لغو شد.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END
    
    # بررسی اینکه عدد صحیح است
    try:
        volume = int(text)
        if volume < 1:
            await update.message.reply_text(
                "❌ حداقل حجم قابل افزایش ۱ گیگ است.\n\n"
                "لطفاً یک عدد صحیح بزرگتر یا مساوی ۱ وارد کنید:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("❌ انصراف")]],
                    resize_keyboard=True
                )
            )
            return VOLUME_SELECTION
    except ValueError:
        await update.message.reply_text(
            "❌ لطفاً فقط عدد صحیح وارد کنید (مثال: 5)\n"
            "اعداد اعشاری و متنی قبول نیست.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("❌ انصراف")]],
                resize_keyboard=True
            )
        )
        return VOLUME_SELECTION
    
    price = volume * 1950
    
    # ذخیره حجم و قیمت برای مراحل بعدی
    context.user_data['extra_volume'] = volume
    context.user_data['extra_volume_price'] = price
    context.user_data['volume_for_card'] = volume
    
    # اگر target_subscription_id از قبل در context نبود، از دیتابیس بگیر
    if 'target_subscription_id' not in context.user_data:
        user_id = update.effective_user.id
        custom_subs = db.get_custom_charge_subscriptions(user_id)
        if custom_subs:
            # اگر فقط یک اشتراک دارد، از همان استفاده کن
            context.user_data['target_subscription_id'] = custom_subs[0]['id']
        else:
            await update.message.reply_text(
                "❌ هیچ اشتراک شارژ دلخواهی یافت نشد!",
                reply_markup=get_main_menu()
            )
            return ConversationHandler.END
    
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    balance = user['balance'] if user else 0
    
    price_str = f"{price:,}".replace(",", ".")
    balance_str = f"{balance:,}".replace(",", ".")
    
    keyboard = [
        [
            InlineKeyboardButton("💰 کیف پول", callback_data="extra_volume_pay_wallet"),
            InlineKeyboardButton("🏦 کارت به کارت", callback_data="extra_volume_pay_card")
        ],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_extra_volume")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📋 جزئیات سفارش:\n\n"
        f"📦 حجم مورد نظر: {volume} گیگ\n"
        f"💰 مبلغ: {price_str} تومان\n\n"
        f"💳 موجودی کیف پول: {balance_str} تومان\n\n"
        f"لطفاً روش پرداخت را انتخاب کنید:",
        reply_markup=reply_markup
    )
    return PAYMENT_METHOD
        
async def extra_volume_pay_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pay for extra volume with wallet"""
    bot = context.bot
    query = update.callback_query
    
    user_id = query.from_user.id
    user = db.get_user(user_id)
    balance = user['balance'] if user else 0
    
    volume = context.user_data.get('extra_volume')
    price = context.user_data.get('extra_volume_price')
    subscription_id = context.user_data.get('target_subscription_id')
    
    if not volume or not price:
        await query.answer("❌ خطا! لطفا دوباره تلاش کنید.", show_alert=True)
        return ConversationHandler.END
    
    if not subscription_id:
        custom_subs = db.get_custom_charge_subscriptions(user_id)
        if custom_subs:
            subscription_id = custom_subs[0]['id']
            context.user_data['target_subscription_id'] = subscription_id
        else:
            await query.answer("❌ هیچ اشتراک شارژ دلخواهی یافت نشد!", show_alert=True)
            return ConversationHandler.END
    
    if balance >= price:
        await query.answer("✅ پرداخت با موفقیت انجام شد!")
        
        db.update_balance(user_id, -price)
        db.add_transaction(user_id, -price, "purchase", f"افزایش {volume} گیگ حجم اضافی")
        
        # اضافه کردن حجم به اشتراک مشخص در دیتابیس داخلی
        db.add_volume_to_subscription(subscription_id, volume)
        
        # === بروزرسانی حجم واقعی روی کلاینت در پنل 3xUI - با مقدار کل از دیتابیس ===
        subscription = db.get_subscription(subscription_id)
        if subscription and subscription.get('email'):
            from client_manager import get_panel_client
            panel_client = get_panel_client()
            panel_success, panel_msg, new_total = panel_client.update_client_volume(
                subscription['email'], subscription['remaining_volume']
            )
            if not panel_success:
                logger.error(
                    f"Failed to update panel volume for {subscription['email']}: {panel_msg}"
                )
                await query.message.reply_text(
                    "⚠️ پرداخت با موفقیت انجام شد و حجم در سیستم داخلی ثبت شد، "
                    "اما بروزرسانی حجم روی پنل با خطا مواجه شد.\n"
                    "لطفاً با پشتیبانی تماس بگیرید تا حجم واقعی کانفیگ شما هم بررسی شود."
                )
        
        new_balance = balance - price
        price_str = f"{price:,}"
        balance_str = f"{new_balance:,}"
        
        # ============ لاگ افزایش حجم اضافی ============
        await log_volume_added(
            bot, user_id, subscription_id, volume, price, 'کیف پول',
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        
        # دریافت اطلاعات به‌روز شده اشتراک برای نمایش
        remaining_volume = subscription.get('remaining_volume', 0) if subscription else 0
        
        await query.edit_message_text(
            f"✅ {volume} گیگ حجم اضافی با موفقیت اضافه شد!\n\n"
            f"🔥 قیمت: {price_str} تومان\n"
            f"💳 موجودی جدید: {balance_str} تومان\n"
            f"📊 حجم اشتراک: {remaining_volume} گیگ"
        )
        await query.message.reply_text(
            "به منوی اصلی خوش آمدید!",
            reply_markup=get_main_menu()
        )
        
        # پاک کردن داده‌های موقت
        context.user_data.pop('extra_volume', None)
        context.user_data.pop('extra_volume_price', None)
        context.user_data.pop('volume_for_card', None)
        context.user_data.pop('target_subscription_id', None)
        return ConversationHandler.END
    else:
        needed = price - balance
        price_str = f"{price:,}".replace(",", ".")
        balance_str = f"{balance:,}".replace(",", ".")
        needed_str = f"{needed:,}".replace(",", ".")
        
        alert_text = (
            f"❌ موجودی کیف پول شما کافی نیست!\n\n"
            f"💰 موجودی فعلی: {balance_str} تومان\n"
            f"💳 مبلغ مورد نیاز: {price_str} تومان\n"
            f"⚠️ کسر موجودی: {needed_str} تومان\n\n"
            f"لطفاً از روش کارت به کارت استفاده کنید."
        )
        
        await query.answer(alert_text, show_alert=True)
        return PAYMENT_METHOD
    
async def extra_volume_pay_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pay for extra volume with card (supports hybrid wallet+card payment)"""
    query = update.callback_query

    volume = context.user_data.get('volume_for_card', 1)
    price = volume * 1950
    user_id = query.from_user.id
    user = db.get_user(user_id)
    balance = user['balance'] if user else 0

    wallet_used = 0
    card_amount = price

    if is_hybrid_payment_enabled() and balance > 0:
        wallet_used = min(balance, price)
        card_amount = price - wallet_used

        if card_amount <= 0:
            await query.answer(
                "💰 موجودی کیف پول شما کل مبلغ را پوشش می‌دهد؛ در حال پرداخت با کیف پول...",
                show_alert=True
            )
            return await extra_volume_pay_wallet(update, context)

        db.update_balance(user_id, -wallet_used)
        db.add_transaction(
            user_id, -wallet_used, "hybrid_wallet_use",
            f"کسر بخشی از کیف پول (پرداخت ترکیبی) - افزایش {volume} گیگ حجم اضافی"
        )

    context.user_data['hybrid_wallet_used'] = wallet_used
    context.user_data['hybrid_card_amount'] = card_amount

    await query.answer(
        "۴ رقم آخر شماره کارتی که با آن قصد واریز دارید را وارد کنید",
        show_alert=True
    )

    price_str = f"{price:,}".replace(",", ".")
    card_amount_str = f"{card_amount:,}".replace(",", ".")
    wallet_note = f"\n💰 کسر شده از کیف پول: {wallet_used:,} تومان" if wallet_used else ""

    message_text = f"""💳 پرداخت کارت به کارت برای افزایش حجم

📦 حجم مورد نظر: {volume} گیگ
💰 مبلغ کل: {price_str} تومان{wallet_note}
🏦 مبلغ قابل پرداخت با کارت: {card_amount_str} تومان

<blockquote>لطفاً ۴ رقم آخر شماره کارتی که می‌خواهید با آن واریز کنید را وارد کنید</blockquote>"""

    keyboard = [[KeyboardButton("❌ انصراف")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await query.edit_message_text(message_text, reply_markup=None, parse_mode='HTML')
    await query.message.reply_text("🍾", reply_markup=reply_markup)

    return PAYMENT_METHOD

async def handle_extra_volume_card_digits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle card digits for extra volume (supports hybrid wallet+card payment)"""
    bot = context.bot
    digits = update.message.text.strip()
    user_id = update.effective_user.id

    if digits == "❌ انصراف":
        wallet_used = context.user_data.get('hybrid_wallet_used', 0)
        if wallet_used:
            db.update_balance(user_id, wallet_used)
            db.add_transaction(
                user_id, wallet_used, "refund",
                "بازگشت وجه کسر شده از کیف پول (انصراف از پرداخت ترکیبی حجم اضافی)"
            )
        context.user_data.pop('hybrid_wallet_used', None)
        context.user_data.pop('hybrid_card_amount', None)
        await update.message.reply_text(
            "❌ پرداخت لغو شد.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END

    if not digits.isdigit() or len(digits) != 4:
        await update.message.reply_text(
            "❌ لطفاً دقیقاً ۴ رقم وارد کنید (فقط عدد):"
        )
        return PAYMENT_METHOD

    volume = context.user_data.get('volume_for_card', 1)
    price = volume * 1950
    wallet_used = context.user_data.get('hybrid_wallet_used', 0)
    card_amount = context.user_data.get('hybrid_card_amount', price)
    card_amount_str = f"{card_amount:,}"

    subscription_id = context.user_data.get('target_subscription_id')
    user = update.effective_user

    request_id = uuid.uuid4().hex[:8]
    PENDING_PAYMENTS[request_id] = {
        'type': 'volume',
        'user_id': user.id,
        'subscription_id': subscription_id,
        'volume': volume,
        'amount': card_amount,
        'total_price': price,
        'wallet_used': wallet_used,
        'card_digits': digits,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
    }
    await send_payment_approval_request(bot, 'volume', request_id, PENDING_PAYMENTS[request_id])

    wallet_note = f"\n💰 مبلغ کسر شده از کیف پول: {wallet_used:,} تومان" if wallet_used else ""

    invoice_text = f"""🧾 فاکتور پرداخت برای افزایش حجم

📦 حجم مورد نظر: {volume} گیگ{wallet_note}
💰 مبلغ قابل پرداخت با کارت: <code>{card_amount_str}</code> تومان
🏦 اطلاعات واریز:
- شماره کارت: <code>{get_card_number()}</code>
- بنام: {get_card_holder()}
- بانک: {get_card_bank()}
💰 مبلغ دقیق: <code>{card_amount_str}</code> تومان

<blockquote>• حتماً از کارتی با ۴ رقم آخر {digits} استفاده کنید
- مبلغ را دقیقاً واریز کنید (رند نکنید)
- فقط کارت به کارت کنید(پل یا شبا نکنید)</blockquote>

<blockquote>• پس از واریز، پرداخت شما توسط ادمین بررسی می‌شود
- حجم اضافی پس از تایید ادمین اضافه می‌شود</blockquote>"""

    await update.message.reply_text(invoice_text, parse_mode='HTML')

    await update.message.reply_text(
        "✅ فاکتور پرداخت صادر شد.\n"
        "📌 نیازی به ارسال عکس رسید نمیباشد\n"
        "⚠️ زمان پرداخت این فاکتور ۲۰ دقیقه میباشد\n\n"
        "پس از واریز و تایید ادمین، حجم اضافی به حساب شما اضافه خواهد شد.",
        reply_markup=get_main_menu()
    )

    context.user_data['card_digits'] = digits
    context.user_data.pop('hybrid_wallet_used', None)
    context.user_data.pop('hybrid_card_amount', None)
    return ConversationHandler.END
    
async def pay_with_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pay with wallet and create panel client"""
    bot = context.bot
    query = update.callback_query

    user_id = query.from_user.id
    user = db.get_user(user_id)
    if not user:
        await query.answer("❌ کاربر یافت نشد.", show_alert=True)
        return

    balance = user['balance']
    selected_plan = context.user_data.get('selected_plan')
    if not selected_plan:
        await query.answer("❌ خطا! لطفا دوباره تلاش کنید.", show_alert=True)
        return

    price = selected_plan['price']

    if balance < price:
        needed = price - balance
        await query.answer(
            f"❌ موجودی کیف پول شما کافی نیست!\n\n"
            f"موجودی: {balance:,} تومان\n"
            f"مبلغ مورد نیاز: {price:,} تومان\n"
            f"کسری: {needed:,} تومان",
            show_alert=True
        )
        return

    # === کسر موجودی قبل از ساخت کلاینت ===
    db.update_balance(user_id, -price)
    db.add_transaction(user_id, -price, "purchase_attempt", 
                      f"تلاش خرید {selected_plan.get('name', 'پلن')}")

    await query.answer("⏳ در حال ایجاد اشتراک...")

    protocol = context.user_data.get('selected_protocol', 'v2ray')
    
    # ============ CREATE PANEL CLIENT ============
    success, msg, sub_data = await create_subscription_for_purchase(
        user_id=user_id,
        selected_plan=selected_plan,
        protocol=protocol
    )
    
    if not success:
        # === برگرداندن مبلغ در صورت خطا ===
        db.update_balance(user_id, price)
        db.add_transaction(user_id, price, "refund", f"بازگشت وجه - {msg}")

        # ============ لاگ خطای پنل ============
        await log_panel_error(
            bot, user_id, "ایجاد کلاینت (پرداخت با کیف پول)", msg,
            plan_name=selected_plan.get('name'),
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )

        if "email already in use" in msg.lower() or "already" in msg.lower():
            error_text = (
                "❌ این اشتراک قبلاً برای شما ایجاد شده است.\n\n"
                "لطفاً از بخش «مشاهده اشتراک‌ها» استفاده کنید یا با پشتیبانی تماس بگیرید."
            )
        else:
            error_text = (
                f"❌ خطا در ایجاد کلاینت در پنل!\n\n"
                f"پیام خطا: {msg}\n\n"
                f"💰 مبلغ {price:,} تومان به کیف پول شما بازگشت داده شد."
            )

        await query.edit_message_text(
            error_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📨 پشتیبانی", url="https://t.me/jadetunnel")],
                [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main")]
            ])
        )
        return
    
    # === موفقیت ===
    db.add_transaction(user_id, -price, "purchase", f"خرید {selected_plan.get('name', '')}")

    subscription_id = sub_data.get('subscription_id')
    new_balance = balance - price
    price_str = f"{price:,}"
    balance_str = f"{new_balance:,}"

    plan_display_name = selected_plan.get('name', 'پلن')
    if selected_plan.get('is_custom_charge', False):
        plan_display_name = "🔥 طرح شارژ دلخواه"

    # ============ دریافت نام پنل ============
    panel_name = "پنل پیش‌فرض"
    panel_id = sub_data.get('panel_id')
    if panel_id:
        panel_manager = get_panel_manager()
        panel_data = panel_manager.get_panel(panel_id)
        if panel_data:
            panel_name = panel_data.get('name', panel_id)

    # ============ لاگ پرداخت با کیف پول ============
    await log_wallet_payment(
        bot, user_id, plan_display_name, price, balance, new_balance, 'success',
        username=query.from_user.username,
        first_name=query.from_user.first_name,
        last_name=query.from_user.last_name
    )

    # ============ افزایش عمر چراغ جاده تونل ============
    await lifeline.add_day(bot)

    # ============ لینک این طرح خریداری‌شده ============
    single_link = get_single_sub_link(subscription_id)
    link_line = f"\nلینک اشتراک شما (سازگار با نت ملی)\n<code>{single_link}</code>\n" if single_link else ""

    keyboard = [
        [InlineKeyboardButton("🔧 دریافت کانفیگ", callback_data=f"get_config_{subscription_id}")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main")]
    ]

    await query.edit_message_text(
        f"✅ پرداخت با موفقیت انجام شد!\n\n"
        f"🖥 پنل: {panel_name}\n"
        f"📦 پلن: {plan_display_name}\n"
        f"💰 مبلغ: {price_str} تومان\n"
        f"💳 موجودی جدید: {balance_str} تومان\n"
        f"{link_line}\n"
        f"دریافت کانفیگ همینجا؛ دکمه زیر را بزنید 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

    # پاک کردن داده‌های موقتی
    context.user_data.pop('selected_plan', None)
    context.user_data.pop('selected_protocol', None)
    context.user_data.pop('plan_type', None)
    context.user_data.pop('plan_type_name', None)
        
async def pay_with_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pay with card - ask for last 4 digits (supports hybrid wallet+card payment)"""
    query = update.callback_query

    selected_plan = context.user_data.get('selected_plan')
    if not selected_plan:
        await query.answer("❌ خطا! لطفا دوباره تلاش کنید.", show_alert=True)
        return

    price = selected_plan['price']
    user_id = query.from_user.id
    user = db.get_user(user_id)
    balance = user['balance'] if user else 0

    wallet_used = 0
    card_amount = price

    if is_hybrid_payment_enabled() and balance > 0:
        wallet_used = min(balance, price)
        card_amount = price - wallet_used

        if card_amount <= 0:
            # موجودی کیف پول کل مبلغ را پوشش می‌دهد
            await query.answer(
                "💰 موجودی کیف پول شما کل مبلغ را پوشش می‌دهد؛ در حال پرداخت با کیف پول...",
                show_alert=True
            )
            return await pay_with_wallet(update, context)

        # کسر بخش کیف‌پولی همین الان (در صورت رد/انصراف/خطا، بازگردانده می‌شود)
        db.update_balance(user_id, -wallet_used)
        db.add_transaction(
            user_id, -wallet_used, "hybrid_wallet_use",
            f"کسر بخشی از کیف پول (پرداخت ترکیبی) - {selected_plan.get('name', 'پلن')}"
        )

    context.user_data['hybrid_wallet_used'] = wallet_used
    context.user_data['hybrid_card_amount'] = card_amount

    await query.answer(
        "۴ رقم آخر شماره کارتی که با آن قصد واریز دارید را وارد کنید",
        show_alert=True
    )

    price_str = f"{price:,}"
    card_amount_str = f"{card_amount:,}"
    wallet_note = f"\n💰 کسر شده از کیف پول: {wallet_used:,} تومان" if wallet_used else ""

    message_text = f"""💳 کارت به کارت خودکار
📦 پلن: {selected_plan['name']}
💰 مبلغ کل پلن: {price_str} تومان{wallet_note}
🏦 مبلغ قابل پرداخت با کارت: {card_amount_str} تومان

<blockquote>لطفاً ۴ رقم آخر شماره کارتی که می‌خواهید با آن واریز کنید را وارد کنید</blockquote>"""

    keyboard = [[KeyboardButton("❌ انصراف از پرداخت")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await query.edit_message_text(message_text, reply_markup=None, parse_mode='HTML')
    await query.message.reply_text("🍾", reply_markup=reply_markup)

    return PAYMENT_METHOD

async def handle_card_digits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle card last 4 digits input (supports hybrid wallet+card payment)"""
    bot = context.bot
    digits = update.message.text.strip()
    user_id = update.effective_user.id

    # انصراف
    if digits == "❌ انصراف از پرداخت":
        wallet_used = context.user_data.get('hybrid_wallet_used', 0)
        if wallet_used:
            db.update_balance(user_id, wallet_used)
            db.add_transaction(
                user_id, wallet_used, "refund",
                "بازگشت وجه کسر شده از کیف پول (انصراف از پرداخت ترکیبی)"
            )
        context.user_data.pop('hybrid_wallet_used', None)
        context.user_data.pop('hybrid_card_amount', None)
        await update.message.reply_text(
            "❌ پرداخت لغو شد.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END

    if not digits.isdigit() or len(digits) != 4:
        await update.message.reply_text(
            "❌ لطفاً دقیقاً ۴ رقم وارد کنید (فقط عدد):"
        )
        return PAYMENT_METHOD

    selected_plan = context.user_data.get('selected_plan')
    price = selected_plan['price']
    wallet_used = context.user_data.get('hybrid_wallet_used', 0)
    card_amount = context.user_data.get('hybrid_card_amount', price)

    user = update.effective_user
    protocol = context.user_data.get('selected_protocol', 'v2ray')

    context.user_data['card_digits'] = digits

    await log_invoice_issued(
        bot, user_id, selected_plan['name'], card_amount, digits,
        username=user.username, first_name=user.first_name, last_name=user.last_name
    )

    request_id = uuid.uuid4().hex[:8]
    PENDING_PAYMENTS[request_id] = {
        'type': 'purchase',
        'user_id': user_id,
        'selected_plan': selected_plan,
        'protocol': protocol,
        'card_digits': digits,
        'amount': card_amount,        # مبلغی که باید کارت‌به‌کارت شود
        'total_price': price,         # قیمت کامل پلن
        'wallet_used': wallet_used,   # مبلغ کسرشده از کیف پول (پرداخت ترکیبی)
        'plan_name': selected_plan.get('name'),
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
    }
    await send_payment_approval_request(bot, 'purchase', request_id, PENDING_PAYMENTS[request_id])

    wallet_note = f"\n💰 مبلغ کسر شده از کیف پول: {wallet_used:,} تومان" if wallet_used else ""
    card_amount_str = f"{card_amount:,}"

    invoice_text = f"""🧾 فاکتور پرداخت خودکار
📦 پلن انتخاب شده: {selected_plan['name']}{wallet_note}
💰 مبلغ قابل پرداخت با کارت: <code>{card_amount_str}</code> تومان
🏦 اطلاعات واریز:
- شماره کارت: <code>{get_card_number()}</code>
- بنام: {get_card_holder()}
- بانک: {get_card_bank()}
💰 مبلغ دقیق: <code>{card_amount_str}</code> تومان

<blockquote> حتماً از کارتی با ۴ رقم آخر {digits} استفاده کنید
- مبلغ را دقیقاً واریز کنید (رند نکنید)
- فقط کارت به کارت کنید(پل یا شبا نکنید)
- کانفیگ پس از تایید ادمین ارسال می‌شود </blockquote>"""
    
    await update.message.reply_text(invoice_text, parse_mode='HTML')

    await update.message.reply_text(
        "✅ فاکتور پرداخت صادر شد.\n"
        "📌 نیازی به ارسال عکس رسید نمیباشد\n"
        "⚠️ برای هربار واریز فاکتور جدید دریافت کنید ممکن است شماره کارت تغییر کند (زمان پرداخت این فاکتور ۲۰ دقیقه میباشد)\n\n"
        "پس از واریز و تایید ادمین، کانفیگ به صورت خودکار برای شما ارسال خواهد شد.",
        reply_markup=get_main_menu()
    )
    context.user_data.pop('hybrid_wallet_used', None)
    context.user_data.pop('hybrid_card_amount', None)
    return ConversationHandler.END

async def back_to_custom_charge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to custom charge plan page"""
    query = update.callback_query
    await query.answer()
    await custom_charge_from_plan(update, context)
    
async def payment_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    query = update.callback_query
    await query.answer()
   
    selected_plan = context.user_data.get('selected_plan')
    protocol = context.user_data.get('selected_protocol', 'v2ray')
    user_id = query.from_user.id
    card_digits = context.user_data.get('card_digits', '****')
   
    if not selected_plan:
        await query.answer("❌ خطا! لطفا دوباره تلاش کنید.", show_alert=True)
        return

    # ============ CREATE PANEL CLIENT ============
    success, msg, sub_data = await create_subscription_for_purchase(
        user_id=user_id,
        selected_plan=selected_plan,
        protocol=protocol
    )

    if not success:
        await log_panel_error(
            bot, user_id, "ایجاد کلاینت (پرداخت کارت به کارت)", msg,
            plan_name=selected_plan.get('name'),
            username=query.from_user.username,
            first_name=query.from_user.first_name,
            last_name=query.from_user.last_name
        )
        await query.edit_message_text(
            f"❌ خطا در ایجاد کلاینت در پنل!\n\n"
            f"پیام خطا: {msg}\n\n"
            f"لطفاً با پشتیبانی تماس بگیرید؛ پرداخت شما ثبت شده و پیگیری خواهد شد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📨 پشتیبانی", url="https://t.me/jadetunnel")],
                [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main")]
            ])
        )
        return

    subscription_id = sub_data.get('subscription_id')
    links = sub_data.get('links', [])

    db.add_transaction(user_id, selected_plan['price'], "card_payment", f"پرداخت کارت به کارت - {selected_plan['name']}")
    
    # ============ لاگ پرداخت کارت به کارت ============
    await log_payment_card(
        bot, user_id, selected_plan['name'], selected_plan['price'], card_digits, 'success',
        username=query.from_user.username,
        first_name=query.from_user.first_name,
        last_name=query.from_user.last_name
    )

    # ============ افزایش عمر چراغ جاده تونل ============
    await lifeline.add_day(bot)
    
    # اگر افزایش حجم اضافی از طریق کارت به کارت است
    extra_volume = context.user_data.get('extra_volume')
    subscription = None
    if extra_volume and subscription_id:
        # حجم اضافی را به اشتراک در دیتابیس داخلی اضافه کن
        db.add_volume_to_subscription(subscription_id, extra_volume)

        # بروزرسانی حجم واقعی روی کلاینت در پنل 3xUI - با مقدار کل از دیتابیس
        subscription = db.get_subscription(subscription_id)
        if subscription and subscription.get('email'):
            from client_manager import get_panel_client
            panel_client = get_panel_client()
            panel_success, panel_msg, new_total = panel_client.update_client_volume(
                subscription['email'], subscription['remaining_volume']
            )
            if not panel_success:
                logger.error(
                    f"Failed to update panel volume for {subscription['email']}: {panel_msg}"
                )
   
    price_str = f"{selected_plan['price']:,}".replace(",", ".")

    # ============ لینک این طرح خریداری‌شده ============
    single_link = get_single_sub_link(subscription_id)
    link_line = f"\nلینک اشتراک شما (سازگار با نت ملی)\n<code>{single_link}</code>\n" if single_link else ""

    keyboard = [
        [InlineKeyboardButton("🔧 دریافت کانفیگ", callback_data=f"get_config_{subscription_id}")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
   
    await query.edit_message_text(
        f"✅ پرداخت شما ثبت شد!\n\n"
        f"🏦 شماره کارت: ****{card_digits}\n"
        f"📦 پلن: {selected_plan['name']}\n"
        f"💰 مبلغ: {price_str} تومان\n"
        f"{link_line}\n"
        f"دریافت کانفیگ همینجا؛ دکمه زیر را بزنید 👇\n\n"
        f"📌 در صورت مشکل با پشتیبانی تماس بگیرید.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    # پاک کردن داده‌های موقت
    context.user_data.pop('selected_plan', None)
    context.user_data.pop('selected_protocol', None)
    context.user_data.pop('plan_type', None)
    context.user_data.pop('card_digits', None)
    context.user_data.pop('extra_volume', None)
    context.user_data.pop('target_subscription_id', None)
    
async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel payment - called from callback query"""
    query = update.callback_query
    await query.answer()
   
    await query.edit_message_text(
        "❌ پرداخت لغو شد.\n\n"
        "به منوی اصلی بازگشتید."
    )
    await query.message.reply_text(
        "به منوی اصلی خوش آمدید!",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

def get_single_sub_link(subscription_id: int):
    """لینک اشتراک اختصاصی (فقط همین یک طرح) برای این subscription"""
    if not subscription_id:
        return None
    token = db.get_or_create_subscription_link_token(subscription_id)
    if not token:
        return None
    base = get_combined_sub_base_url().rstrip('/')
    return f"{base}/sub/single/{token}"
        
# ============ View Subscriptions ============
@require_membership
async def view_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    subscriptions = db.get_active_subscriptions(user_id)

    if not subscriptions:
        keyboard = [[InlineKeyboardButton("🛒 خرید VPN", callback_data="buy_vpn")]]
        await update.message.reply_text(
            "📒 لیست اشتراک‌های شما:\n\n"
            "🔻 هنوز هیچ اشتراک فعالی ندارید.\n"
            "🔻 برای خرید از دکمه زیر استفاده کنید.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    combined_link = get_combined_sub_link(user_id)

    for idx, sub in enumerate(subscriptions, 1):
        protocol_names = {
            "wireguard": "WireGuard 🌐",
            "openvpn": "OpenVPN",
            "v2ray": "V2Ray | ویتوری"
        }

        if sub.get('plan_name'):
            plan_type_display = sub.get('plan_name')
        elif sub.get('plan_type') == 'custom_charge':
            plan_type_display = "🔥 طرح شارژ دلخواه"
        elif sub.get('plan_type') == 'new':
            plan_type_display = "🆕 طرح جدید (نامحدود)"
        elif sub.get('plan_type') == 'old':
            plan_type_display = "نامحدود تک کاربر"
        elif sub.get('plan_type') == 'manual':
            plan_type_display = "📦 اشتراک دستی"
        else:
            plan_type_display = "📦 طرح معمولی"

        # ============ نمایش حجم — جدا از تشخیص نام طرح ============
        # برای شارژ دلخواه و اشتراک‌های دستی که مقدار حجم دارند نشان بده
        volume_line = ""
        if sub.get('plan_type') in ('custom_charge', 'manual') and sub.get('remaining_volume', 0):
            volume_line = f"📊 حجم اشتراک: {sub.get('remaining_volume', 0)} گیگ\n"

        email = sub.get('email', f"{user_id}_{idx}")
        panel_id = sub.get('panel_id')

        panel_name = "پنل پیش‌فرض"
        if panel_id:
            panel_manager = get_panel_manager()
            panel_data = panel_manager.get_panel(panel_id)
            if panel_data:
                panel_name = panel_data.get('name', panel_id)

        start_date = str(sub.get('start_date', ''))[:10]
        end_date = str(sub.get('end_date', ''))[:10]

        link_line = f"\nلینک همه طرح‌ها (سازگار با نت ملی)\n<code>{combined_link}</code>\n" if combined_link else ""

        # ============ لینک اختصاصی همین طرح ============
        single_link = get_single_sub_link(sub['id'])
        single_link_line = f"\nلینک این طرح\n<code>{single_link}</code>\n" if single_link else ""

        sub_text = f"""
🔖 اشتراک: {email}

🖥 پنل: {panel_name}
📌 پروتکل: {protocol_names.get(sub['protocol'], sub['protocol'])}
📋 نوع طرح: {plan_type_display}
{volume_line}
⏰ مدت: {sub['duration_days']} روز

📅 شروع: {start_date}
📅 انقضا: {end_date}
✅ وضعیت: فعال
{link_line}{single_link_line}
دریافت کانفیگ همینجا؛ دکمه زیر را بزنید 👇
        """.strip()

        keyboard = [[InlineKeyboardButton("🔧 دریافت کانفیگ", callback_data=f"get_config_{sub['id']}")]]

        await update.message.reply_text(
            sub_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        
async def send_config_by_priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """با زدن دکمه «دریافت کانفیگ»، کانفیگ‌های پنل و کانفیگ‌های دستی ادمین را بر اساس اولویت می‌فرستد"""
    query = update.callback_query
    await query.answer("⏳ در حال دریافت کانفیگ...")

    try:
        subscription_id = int(query.data.replace("get_config_", ""))
    except ValueError:
        await query.message.reply_text("❌ خطا در شناسه اشتراک.")
        return

    subscription = db.get_subscription(subscription_id)
    if not subscription:
        await query.message.reply_text("⚠️ اطلاعات این اشتراک یافت نشد. با پشتیبانی تماس بگیرید.")
        return

    panel_id = subscription.get('panel_id')
    email = subscription.get('email')

    panel_links = []
    if panel_id and email:
        try:
            client = get_panel_client(panel_id)
            panel_links = client.get_client_links(email) or []
        except Exception as e:
            logger.error(f"Error fetching links for {email} (panel {panel_id}): {e}")
            panel_links = []

    manual_configs = db.get_manual_configs(subscription_id) or []

    if not panel_links and not manual_configs:
        await query.message.reply_text("⚠️ کانفیگی برای این اشتراک یافت نشد. با پشتیبانی تماس بگیرید.")
        return

    ordered_groups = group_combined_links(panel_links, manual_configs)

    priority_labels = [
        "الویت اول 👇🏻",
        "الویت دوم(برای زمانی که اختلال نت زیاده) 👇🏻",
    ]

    for i, (_, links_list) in enumerate(ordered_groups):
        label = priority_labels[i] if i < len(priority_labels) else f"الویت {i+1} 👇🏻"
        config_lines = "\n".join(f"<code>{l}</code>" for l in links_list)
        await query.message.reply_text(
            f"{label}\n\n{config_lines}",
            parse_mode='HTML',
            disable_web_page_preview=True
        )


def group_combined_links(panel_links: list, manual_configs: list) -> list:
    """
    لینک‌های گرفته‌شده از پنل (بر اساس type در query string) و کانفیگ‌های دستی
    (بر اساس priority ذخیره‌شده در دیتابیس) را با هم در یک ترتیب اولویت ترکیب می‌کند.
    خروجی: لیستی از (priority_num, [links]) به ترتیب صعودی اولویت
    """
    groups = {}

    for link in panel_links:
        t = get_link_type(link) or 'other'
        if t in PRIORITY_TYPE_ORDER:
            priority_num = PRIORITY_TYPE_ORDER.index(t) + 1
        else:
            priority_num = 99
        groups.setdefault(priority_num, []).append(link)

    for mc in manual_configs:
        priority_num = mc.get('priority', 1)
        groups.setdefault(priority_num, []).append(mc['link'])

    return [(k, groups[k]) for k in sorted(groups.keys())]
        
def get_link_type(link: str) -> str:
    """نوع کانفیگ (tcp, grpc, ws, ...) را از روی query string لینک استخراج می‌کند"""
    try:
        parsed = urlparse(link)
        qs = parse_qs(parsed.query)
        return (qs.get('type', [''])[0] or '').strip().lower()
    except Exception:
        return ''

def group_links_by_priority(links: list) -> list:
    """
    لینک‌ها را بر اساس type گروه‌بندی و بر اساس اولویت (tcp, grpc, سایر) مرتب می‌کند.
    خروجی: لیستی از (type_name, [links]) به ترتیب اولویت
    """
    groups = {}
    for link in links:
        t = get_link_type(link) or 'other'
        groups.setdefault(t, []).append(link)

    ordered = []
    for t in PRIORITY_TYPE_ORDER:
        if t in groups:
            ordered.append((t, groups.pop(t)))
    # بقیه‌ی تایپ‌هایی که در لیست اولویت نبودند، در آخر
    for t, l in groups.items():
        ordered.append((t, l))
    return ordered

# ============ Account Info ============
@require_membership
async def account_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Account info handler"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
   
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد. لطفا با /start شروع کنید.")
        return
   
    active_subs = db.get_active_subscriptions(user_id)
    inactive_subs = db.get_inactive_subscriptions_count(user_id)
   
    balance_str = f"{user['balance']:,}"
   
    info_text = f"""
🗂 اطلاعات حساب کاربری:

🔰 شناسه: `{user_id}`
👤 نام: {user['first_name'] or user['username'] or 'کاربر'}
💰 موجودی: {balance_str} تومان

📊 اشتراک‌های فعال: {len(active_subs)} عدد
📊 اشتراک‌های منقضی شده: {inactive_subs} عدد
"""
   
    keyboard = [[InlineKeyboardButton("🛒 خرید VPN", callback_data="buy_vpn")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(info_text, reply_markup=reply_markup, parse_mode='Markdown')
    
# ============ Help ============
@require_membership
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    keyboard = [
        [InlineKeyboardButton("🌐 WireGuard", callback_data="help_wireguard")],
        [InlineKeyboardButton("🔓 OpenVPN", callback_data="help_openvpn")],
        [InlineKeyboardButton("🚀 V2Ray", callback_data="help_v2ray")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(
            "📖 راهنمای اتصال به VPN\n\n"
            "لطفاً ابتدا پروتکل مورد نظر خود را انتخاب کنید:\n\n"
            "هر پروتکل شامل آموزش اختصاصی برای سیستم‌عامل‌های مختلف است.",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.edit_message_text(
            "📖 راهنمای اتصال به VPN\n\n"
            "لطفاً ابتدا پروتکل مورد نظر خود را انتخاب کنید:\n\n"
            "هر پروتکل شامل آموزش اختصاصی برای سیستم‌عامل‌های مختلف است.",
            reply_markup=reply_markup
        )
        
async def help_protocol_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help protocol selection callback"""
    query = update.callback_query
    await query.answer()
    protocol = query.data.replace("help_", "")
    if protocol == "v2ray":
        keyboard = [
            [
                InlineKeyboardButton("📱 اندروید", callback_data="v2ray_android"),
                InlineKeyboardButton("📱 آیفون", callback_data="v2ray_iphone"),
            ],
            [
                InlineKeyboardButton("💻 مک", callback_data="v2ray_mac"),
                InlineKeyboardButton("💻 ویندوز", callback_data="v2ray_windows"),
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📖 راهنمای اتصال - 🔱 V2Ray\n\n"
            "لطفاً سیستم‌عامل خود را انتخاب کنید:\n\n"
            "هر سیستم‌عامل آموزش مخصوص به خود را دارد.",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🔙 انتخاب راهنمای دیگر", callback_data="back_to_help")],
            [InlineKeyboardButton("🏠 صفحه اصلی", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"⚠️ راهنمای اتصال {protocol}\n\n"
            "❌ هشدار: آموزشی برای این پروتکل ارائه نشده است.\n\n"
            "لطفاً از گزینه‌های زیر استفاده کنید:",
            reply_markup=reply_markup
        )
        
async def v2ray_os_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """V2Ray OS selection callback - forwards post from channel"""
    query = update.callback_query
    await query.answer()
    os_type = query.data.replace("v2ray_", "")
    os_posts = {
        "android": {"chat_id": "@gadeeshterak", "message_id": 3},
        "iphone": {"chat_id": "@gadeeshterak", "message_id": 5},
        "mac": {"chat_id": "@gadeeshterak", "message_id": 5},
        "windows": {"chat_id": "@gadeeshterak", "message_id": 3},
    }
    os_names = {
        "android": "اندروید",
        "iphone": "آیفون",
        "mac": "مک",
        "windows": "ویندوز"
    }
    keyboard = [
        [InlineKeyboardButton("🔙 انتخاب راهنمای دیگر", callback_data="back_to_help")],
        [InlineKeyboardButton("🏠 صفحه اصلی", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    post_info = os_posts.get(os_type)
    if post_info:
        try:
            await query.message.reply_text(
                f"✅ راهنمای اتصال ارسال شد!\n\n"
                f"🔌 پروتکل: 🔱 V2Ray\n"
                f"📱 سیستم‌عامل: {os_names.get(os_type, os_type)}\n"
                f"📖 عنوان: آموزش اتصال در {os_names.get(os_type, os_type)}\n\n"
                f"👇 آموزش:"
            )
            await context.bot.forward_message(
                chat_id=update.effective_chat.id,
                from_chat_id=post_info["chat_id"],
                message_id=post_info["message_id"]
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ در صورت نیاز به راهنمایی بیشتر، از دکمه‌های زیر استفاده کنید.",
                reply_markup=reply_markup
            )
            await query.delete_message()
        except Exception as e:
            logger.error(f"Error forwarding message: {e}")
            await query.edit_message_text(
                f"✅ راهنمای اتصال ارسال شد!\n\n"
                f"🔌 پروتکل: 🔱 V2Ray\n"
                f"📱 سیستم‌عامل: {os_names.get(os_type, os_type)}\n"
                f"📖 عنوان: آموزش اتصال در {os_names.get(os_type, os_type)}\n\n"
                f"👇 لینک آموزش:\n"
                f"https://t.me/gadeeshterak/{post_info['message_id']}\n\n"
                f"⚠️ در صورت نیاز به راهنمایی بیشتر، از دکمه‌های زیر استفاده کنید.",
                reply_markup=reply_markup
            )
    else:
        await query.edit_message_text(
            f"❌ آموزشی برای {os_names.get(os_type, os_type)} یافت نشد.\n\n"
            f"لطفاً از گزینه‌های زیر استفاده کنید:",
            reply_markup=reply_markup
        )
        
async def back_to_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to help menu"""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🌐 WireGuard", callback_data="help_wireguard")],
        [InlineKeyboardButton("🔓 OpenVPN", callback_data="help_openvpn")],
        [InlineKeyboardButton("🚀 V2Ray", callback_data="help_v2ray")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📖 راهنمای اتصال به VPN\n\n"
        "لطفاً ابتدا پروتکل مورد نظر خود را انتخاب کنید:",
        reply_markup=reply_markup
    )
    
# ============ Charge Wallet ============
@require_membership
async def charge_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Charge wallet handler"""
    await update.message.reply_text(
        "💰 افزایش موجودی\n\n"
        "لطفاً مبلغ مورد نظر (به تومان) را وارد کنید:\n"
        "مثال: 10000\n\n"
        "<blockquote>⚠️ حداقل مبلغ: 10,000\n"
        "⚠️ حداکثر مبلغ: 100,000,000</blockquote>",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ انصراف از شارژ")]],
            resize_keyboard=True
        ),
        parse_mode='HTML'
    )
    return AMOUNT_SELECTION


async def charge_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle charge amount input"""
    amount_text = update.message.text.strip()

    if amount_text == "❌ انصراف از شارژ":
        await update.message.reply_text(
            "❌ درخواست شارژ لغو شد.\n\n"
            "برای شارژ مجدد از دکمه 💰 افزایش موجودی استفاده کنید.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END

    try:
        amount = int(amount_text)

        if amount < 10000:
            await update.message.reply_text(
                "❌ حداقل مبلغ قابل شارژ 10,000 تومان می‌باشد.\n\n"
                "لطفاً مجدداً مبلغ را وارد کنید:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("❌ انصراف از شارژ")]],
                    resize_keyboard=True
                )
            )
            return AMOUNT_SELECTION
        elif amount > 100000000:
            await update.message.reply_text(
                "❌ حداکثر مبلغ قابل شارژ 100,000,000 تومان می‌باشد.\n\n"
                "لطفاً مجدداً مبلغ را وارد کنید:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("❌ انصراف از شارژ")]],
                    resize_keyboard=True
                )
            )
            return AMOUNT_SELECTION

        context.user_data['charge_amount'] = amount

        amount_str = f"{amount:,}"

        # ==================== انتخاب روش پرداخت (دکمه شیشه‌ای) ====================
        keyboard = [
            [InlineKeyboardButton("💳 کارت به کارت خودکار", callback_data="charge_pay_card")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"💳 انتخاب روش پرداخت\n\n"
            f"💰 مبلغ شارژ: {amount_str} تومان\n\n"
            f"لطفاً روش پرداخت را از گزینه‌های زیر انتخاب کنید:",
            reply_markup=reply_markup
        )
        return PAYMENT_METHOD

    except ValueError:
        await update.message.reply_text(
            "❌ لطفا یک عدد معتبر وارد کنید:\n"
            "مثال: 10000",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("❌ انصراف از شارژ")]],
                resize_keyboard=True
            )
        )
        return AMOUNT_SELECTION


async def charge_pay_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Charge - pay with card selected, show alert & ask for last 4 digits"""
    query = update.callback_query
    await query.answer(
        "۴ رقم آخر شماره کارتی که با آن قصد واریز دارید را وارد کنید",
        show_alert=True
    )

    amount = context.user_data.get('charge_amount')
    if not amount:
        await query.answer("❌ خطا! لطفا دوباره تلاش کنید.", show_alert=True)
        return ConversationHandler.END

    amount_str = f"{amount:,}"

    message_text = f"""💳 کارت به کارت خودکار

💰 مبلغ: {amount_str} تومان

<blockquote>لطفاً 4رقم آخر شماره کارتی که می‌خواهید با آن واریز کنید را وارد کنید</blockquote>"""

    keyboard = [[KeyboardButton("❌ انصراف از شارژ")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await query.edit_message_text(message_text, reply_markup=None, parse_mode='HTML')
    await query.message.reply_text("🍾", reply_markup=reply_markup)

    return PAYMENT_METHOD


async def handle_charge_card_digits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle card last 4 digits input for charge"""
    bot = context.bot
    digits = update.message.text.strip()

    # انصراف
    if digits == "❌ انصراف از شارژ":
        await update.message.reply_text(
            "❌ درخواست شارژ لغو شد.\n\n"
            "برای شارژ مجدد از دکمه 💰 افزایش موجودی استفاده کنید.",
            reply_markup=get_main_menu()
        )
        return ConversationHandler.END

    if not digits.isdigit() or len(digits) != 4:
        await update.message.reply_text(
            "❌ خطا: 4رقم آخر کارت خود را به درستی وارد کنید. \n\n"
            "⚠️ مثال: 2366"
        )
        return PAYMENT_METHOD

    amount = context.user_data.get('charge_amount', 0)
    amount_str = f"{amount:,}"
    user = update.effective_user

    # ============ ثبت درخواست در انتظار تایید ادمین + ارسال فاکتور با دکمه تایید/رد ============
    request_id = uuid.uuid4().hex[:8]
    PENDING_PAYMENTS[request_id] = {
        'type': 'charge',
        'user_id': user.id,
        'amount': amount,
        'card_digits': digits,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
    }
    await send_payment_approval_request(bot, 'charge', request_id, PENDING_PAYMENTS[request_id])

    # ==================== فاکتور شارژ ====================
    invoice_text = f"""🧾 فاکتور شارژ خودکار

🏦 اطلاعات واریز:
- شماره کارت: `{get_card_number()}`
- بنام: {get_card_holder()}
- بانک: {get_card_bank()}

💰 مبلغ دقیق: {amount_str} تومان
🔢 ۴ رقم آخر کارت مبدأ: {digits}

⚠️ نکات مهم:
- فقط از کارتی با ۴ رقم آخر {digits} واریز کنید
- فقط کارت به کارت کنید (⚠️ پل یا شبا نکنید)
- مبلغ را دقیقاً {amount_str} تومان واریز کنید
- پس از واریز، پرداخت شما توسط ادمین بررسی می‌شود
- موجودی شما پس از تایید ادمین افزایش می‌یابد

⏰ زمان باقی مانده: ۲۰ دقیقه"""

    await update.message.reply_text(invoice_text, parse_mode='Markdown')

    # ==================== پیام پایان (ریپلای روی پیام ۴ رقمی) ====================
    await update.message.reply_text(
        "📌 نیازی به ارسال عکس رسید نمیباشد\n"
        "⚠️ برای هربار واریز فاکتور جدید دریافت کنید ممکن است شماره کارت تغییر کند (زمان پرداخت این فاکتور ۲۰ دقیقه میباشد)\n\n"
        "پس از واریز و تایید ادمین، موجودی شما افزایش خواهد یافت.",
        reply_markup=get_main_menu(),
        reply_to_message_id=update.message.message_id
    )

    context.user_data['charge_card_digits'] = digits
    return ConversationHandler.END


async def charge_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel charge - called from callback query"""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "❌ درخواست شارژ لغو شد.\n\n"
        "به منوی اصلی بازگشتید."
    )
    await query.message.reply_text(
        "به منوی اصلی خوش آمدید!",
        reply_markup=get_main_menu()
    )
    return ConversationHandler.END

# ============ Support ============
@require_membership
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Support handler"""
    support_username = get_support_username()
    support_url = f"https://t.me/{support_username.lstrip('@')}"

    keyboard = [
        [InlineKeyboardButton("چت با پشتیبانی 🧑‍💻", url=support_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "☎️ پشتیبانی:\n\n"
        "برای ارتباط با پشتیبانی می‌توانید از طریق زیر اقدام کنید:\n\n"
        f"📨 <a href=\"{support_url}\">تماس با پشتیبانی</a>",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
# ============ Invite Friends ============
@require_membership
async def invite_friends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invite friends handler"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد. لطفا با /start شروع کنید.")
        return

    referrals_count = db.get_referral_count(user_id)
    total_commission = db.get_total_commission(user_id)

    bot_username = context.bot.username
    invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    inviter_bonus_str = f"{get_referral_bonus_inviter():,}".replace(",", ".")
    invitee_bonus_str = f"{get_referral_bonus_invitee():,}".replace(",", ".")

    invite_text = f"""👥 <b>رفیقاتو بیار، جفتتون سود کنید!</b>

جاده تونل رو با دوستات به اشتراک بذار؛ به همین سادگی هم به اونا لطف کردی هم برای خودت اعتبار جمع کردی 🌿

🎁 به ازای هر دوستی که با لینک تو عضو ربات بشه:
💰 <b>{inviter_bonus_str} تومان</b> به کیف پول تو اضافه میشه
🎉 دوستت هم <b>{invitee_bonus_str} تومان</b> هدیه ورود می‌گیره

🔗 <b>لینک اختصاصی تو:</b>
<code>{invite_link}</code>

📊 <b>کارنامه‌ی دعوت‌هات:</b>
👥 دعوت‌های موفق: {referrals_count} نفر
💰 مجموع اعتباری که گرفتی: {total_commission:,} تومان

📋 کافیه لینک بالا رو برای دوستات بفرستی و منتظر هدیه‌ت بمونی 🚀"""

    share_text = (
        f"🚀 فیلترشکن پرسرعت و بدون قطعی می‌خوای؟\n"
        f"عضو جاده تونل شو و {invitee_bonus_str} تومان هدیه بگیر! 🎁"
    )

    keyboard = [
        [InlineKeyboardButton(
            "📤 اشتراک‌گذاری لینک",
            url=f"https://t.me/share/url?url={invite_link}&text={share_text}"
        )]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        invite_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

@require_membership
async def emergency_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی طرح اضطراری - نیازمند تایید ادمین"""
    user = update.effective_user
    access = db.get_emergency_access(user.id)

    if not access or access.get('status') == 'rejected':
        db.request_emergency_access(user.id)
        await send_emergency_access_request(context.bot, user)
        await update.message.reply_text(
            "🆘 درخواست شما برای طرح اضطراری برای ادمین ارسال شد.\n"
            "لطفاً منتظر تایید بمانید؛ پس از تایید به شما اطلاع داده می‌شود."
        )
        return

    if access.get('status') == 'pending':
        await update.message.reply_text(
            "⏳ درخواست شما در حال بررسی توسط ادمین است. لطفاً منتظر بمانید."
        )
        return

    access_type = access.get('access_type')
    keyboard = []
    if access_type in ('config', 'both'):
        keyboard.append([InlineKeyboardButton("🔧 ساخت کانفیگ", callback_data="emergency_build_config")])
    if access_type in ('proxy', 'both'):
        keyboard.append([InlineKeyboardButton("🌐 دریافت پروکسی", callback_data="emergency_get_proxy")])

    await update.message.reply_text(
        "🆘 طرح اضطراری\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_emergency_access_request(bot, user):
    """ارسال درخواست دسترسی طرح اضطراری به گروه لاگ همراه با دکمه‌های تصمیم‌گیری"""
    from logger_bot import LOG_GROUP_ID, get_thread_id, Topics, format_user_full

    if not LOG_GROUP_ID:
        logger.warning("LOG_GROUP_ID تنظیم نشده؛ درخواست طرح اضطراری ارسال نشد.")
        return

    user_info = format_user_full(user.id, user.username, user.first_name, getattr(user, 'last_name', None))
    text = (
        f"🆘 <b>درخواست جدید طرح اضطراری</b>\n\n"
        f"{user_info}\n\n"
        f"لطفاً نوع دسترسی را تعیین کنید یا درخواست را رد کنید:"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔧 کانفیگ", callback_data=f"admin_emergency_grant_config_{user.id}"),
            InlineKeyboardButton("🌐 پروکسی", callback_data=f"admin_emergency_grant_proxy_{user.id}"),
        ],
        [
            InlineKeyboardButton("✅ هردو", callback_data=f"admin_emergency_grant_both_{user.id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"admin_emergency_deny_{user.id}"),
        ]
    ])

    thread_id = get_thread_id(Topics.EMERGENCY_PLAN)
    try:
        await bot.send_message(
            chat_id=LOG_GROUP_ID, text=text, parse_mode='HTML',
            message_thread_id=thread_id, reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error sending emergency access request: {e}")
        
async def emergency_build_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    access = db.get_emergency_access(user_id)
    if not access or access.get('status') != 'approved' or access.get('access_type') not in ('config', 'both'):
        await query.edit_message_text("شما به بخش ساخت کانفیگ طرح اضطراری دسترسی ندارید.")
        return
    
    panel_manager = get_panel_manager()
    all_panels = panel_manager.get_all_panels()

    if not all_panels:
        await query.edit_message_text("در حال حاضر هیچ پنلی فعال نیست.")
        return

    existing_panel_ids = db.get_emergency_panel_ids(user_id)

    # لیست پنل‌های قابل انتخاب
    keyboard = []
    for panel_id, panel_data in all_panels.items():
        if not panel_data.get('enabled', True):
            continue
        if 'emergency' not in panel_data.get('plan_types', []):
            continue
        if panel_id in existing_panel_ids:
            continue
        keyboard.append([InlineKeyboardButton(
            f"{panel_data.get('name', panel_id)}",
            callback_data=f"emergency_panel_{panel_id}"
        )])

    if not keyboard:
        # بررسی اینکه آیا اصلاً پنل فعالی وجود دارد یا کاربر همه را ساخته
        all_panels_exist = any(
            panel_data.get('enabled', True) and 'emergency' in panel_data.get('plan_types', [])
            for panel_data in all_panels.values()
        )
        
        if not all_panels_exist:
            message = "در حال حاضر هیچ پنلی برای ساخت کانفیگ اضطراری تنظیم نشده است."
        else:
            message = "شما قبلاً از تمام پنل‌های موجود، کانفیگ اضطراری ساخته‌اید.\nهر کاربر فقط یک بار از هر پنل می‌تواند کانفیگ بسازد."
        
        await query.edit_message_text(message)
        return

    await query.edit_message_text(
        "ساخت کانفیگ اضطراری\n\n"
        "پنل مورد نظر خود را انتخاب کنید:\n"
        "توجه: هر کاربر فقط یک بار از هر پنل می‌تواند کانفیگ بسازد.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def emergency_get_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    access = db.get_emergency_access(user_id)
    if not access or access.get('status') != 'approved' or access.get('access_type') not in ('proxy', 'both'):
        await query.edit_message_text("شما به بخش دریافت پروکسی طرح اضطراری دسترسی ندارید.")
        return

    from bot_settings import get_emergency_proxy_links
    proxies = get_emergency_proxy_links()

    if not proxies:
        await query.edit_message_text(
            "در حال حاضر پروکسی دردسترس نیست.\n"
            "لطفاً بعداً مجدداً تلاش کنید."
        )
        return

    keyboard = []
    row = []
    for i, p in enumerate(proxies):
        row.append(InlineKeyboardButton(f"{i+1}.{p.get('name', 'Proxy')}", url=p.get('link')))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    message = (
        "<b>پروکسی‌های فعال</b>\n\n"
        "جهت استفاده، روی هرکدام کلیک کنید تا به کلاینت شما اضافه شود.\n"
        "در صورت بروز مشکل، از بخش پشتیبانی اقدام کنید."
    )

    await query.edit_message_text(
        message,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
async def emergency_panel_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """کاربر پنل مورد نظر برای دریافت کلاینت اضطراری (رایگان) را انتخاب کرد"""
    query = update.callback_query
    await query.answer()

    panel_id = query.data.replace("emergency_panel_", "")
    user_id = query.from_user.id

    panel_manager = get_panel_manager()
    panel_data = panel_manager.get_panel(panel_id)

    if not panel_data or not panel_data.get('enabled', True):
        await query.edit_message_text("این پنل در دسترس نیست.")
        return

    # جلوگیری از ساخت بیش از یک کلاینت اضطراری روی هر پنل
    if db.has_emergency_subscription(user_id, panel_id):
        await query.edit_message_text("شما قبلاً از این پنل کانفیگ اضطراری ساخته‌اید.\nهر کاربر فقط یک بار از هر پنل می‌تواند کانفیگ بسازد.")
        return

    await query.edit_message_text("در حال ساخت اشتراک اضطراری...")

    panel_client = PanelClient(panel_id)
    email = f"{user_id}_emg_{panel_id}"
    inbound_ids = panel_data.get('inbound_ids', [82, 80, 81])

    success, msg, client_data = panel_client.create_client(
        email=email,
        total_gb=EMERGENCY_PLAN_VOLUME_GB,
        expiry_days=EMERGENCY_PLAN_DURATION_DAYS,
        inbound_ids=inbound_ids
    )

    if not success or not client_data:
        await query.edit_message_text(
            f"خطا در ساخت اشتراک اضطراری در پنل: {msg}"
        )
        return

    links = panel_client.get_client_links(email)
    if not links:
        sub_id = client_data.get('subId')
        links = [f"{panel_client.panel_base}/sub/{sub_id}"] if sub_id else []

    db.add_subscription(
        user_id=user_id,
        protocol='v2ray',
        duration_days=EMERGENCY_PLAN_DURATION_DAYS,
        plan_type='emergency',
        initial_volume=EMERGENCY_PLAN_VOLUME_GB,
        plan_name="طرح اضطراری",
        email=email,
        panel_id=panel_id
    )

    if links:
        lines = "\n\n".join(f"کانفیگ {i+1}:\n<code>{l}</code>" for i, l in enumerate(links))
        config_text = f"لینک‌های اشتراک شما ({len(links)} عدد):\n\n{lines}"
    else:
        config_text = f"شناسه اشتراک: <code>{email}</code>"

    await query.edit_message_text(
        f"اشتراک اضطراری شما با موفقیت ساخته شد!\n\n"
        f"پنل: {panel_data.get('name', panel_id)}\n"
        f"حجم: {EMERGENCY_PLAN_VOLUME_GB} گیگ\n"
        f"مدت: {EMERGENCY_PLAN_DURATION_DAYS} روز\n\n"
        f"{config_text}",
        parse_mode='HTML'
    )
    await query.message.reply_text(
        "به منوی اصلی خوش آمدید!",
        reply_markup=get_main_menu()
    )
    
# ============ Navigation Handlers ============
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to main menu"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("🔙 بازگشت به منوی اصلی")
        await query.message.reply_text(
            "به منوی اصلی خوش آمدید!",
            reply_markup=get_main_menu()
        )
    else:
        await update.message.reply_text(
            "به منوی اصلی خوش آمدید!",
            reply_markup=get_main_menu()
        )
async def back_to_protocols(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to protocols selection"""
    query = update.callback_query
    await query.answer()
   
    keyboard = [
        [InlineKeyboardButton("🚀 V2Ray | ویتوری", callback_data="protocol_v2ray")],
        [InlineKeyboardButton("🌐 WireGuard", callback_data="protocol_wireguard")],
        [InlineKeyboardButton("🔓 OpenVPN", callback_data="protocol_openvpn")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
   
    await query.edit_message_text(
        "🔌 انتخاب پروتکل VPN\n\n"
        "✅ تمامی پروتکل‌های زیر برای دور زدن فیلترینگ و استفاده در سوشال مدیا و گیم کاملاً مناسب هستند.\n\n"
        "⭐️ پیشنهاد ویژه ما: V2Ray | ویتوری 🌐\n\n"
        "👇 لطفاً پروتکل مورد نظر خود را انتخاب کنید:",
        reply_markup=reply_markup
    )
    
async def back_to_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to plans selection"""
    query = update.callback_query
    await query.answer()
   
    protocol = context.user_data.get('selected_protocol', 'v2ray')
    user = db.get_user(query.from_user.id)
    balance = user['balance'] if user else 0
   
    protocol_names = {
        "wireguard": "WireGuard 🌐",
        "openvpn": "OpenVPN",
        "v2ray": "V2Ray | ویتوری"
    }
   
    # فقط پلن‌های V2Ray
    plans = {
        "v2ray": [
            {"name": "🟢 متعادل", "price": 259000, "days": 30, "volume": 105, "emoji": "🟢", "daily_volume": 3.5},
            {"name": "🔥 منصفانه", "price": 312000, "days": 30, "volume": 150, "emoji": "🔥", "daily_volume": 5},
            {"name": "💎 حرفه‌ای", "price": 492000, "days": 30, "volume": 300, "emoji": "💎", "daily_volume": 10}
        ]
    }
   
    # اگر پروتکل انتخاب شده V2Ray نیست، پیام خطا بده
    if protocol not in plans:
        await query.edit_message_text(
            "❌ این پروتکل در حال حاضر ارائه نمی‌شود.\n\n"
            "لطفاً پروتکل V2Ray | ویتوری را انتخاب کنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت به پروتکل‌ها", callback_data="back_to_protocols")]
            ])
        )
        return
   
    protocol_plans = plans[protocol]
   
    keyboard = []
    for i, plan in enumerate(protocol_plans):
        price_str = f"{plan['price']:,}".replace(",", ".")
        keyboard.append([
            InlineKeyboardButton(
                f"{plan['emoji']} {plan['name']} | {price_str} تومان",
                callback_data=f"plan_{i}"
            )
        ])
   
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پروتکل‌ها", callback_data="back_to_protocols")])
    reply_markup = InlineKeyboardMarkup(keyboard)
   
    await query.edit_message_text(
        f"🔌 پلن‌های {protocol_names.get(protocol, protocol)}\n\n"

        f"📊 اشتراک‌های فعال: {len(db.get_active_subscriptions(query.from_user.id))} عدد\n\n"
        "لطفاً پلن مورد نظر را جهت خرید از منو زیر انتخاب کنید:",
        reply_markup=reply_markup
    )


async def view_subscriptions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View subscriptions callback - fetch links from panel API"""
    query = update.callback_query
    await query.answer()
   
    user_id = query.from_user.id
    subscriptions = db.get_active_subscriptions(user_id)
   
    if not subscriptions:
        await query.edit_message_text(
            "📒 لیست اشتراک‌های شما:\n\n"
            "🔻 هنوز هیچ اشتراک فعالی ندارید.\n"
            "🔻 برای خرید از دکمه زیر استفاده کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 خرید VPN", callback_data="buy_vpn")]])
        )
        return
    
    text = "📒 لیست اشتراک‌های فعال شما:\n\n"
    for i, sub in enumerate(subscriptions, 1):
        protocol_names = {
            "wireguard": "WireGuard 🌐",
            "openvpn": "OpenVPN",
            "v2ray": "V2Ray | ویتوری"
        }
        
        # تشخیص نام نمایشی طرح
        if sub.get('plan_name'):
            plan_type_display = sub.get('plan_name')
        elif sub.get('plan_type') == 'custom_charge':
            plan_type_display = "🔥 شارژ دلخواه"
        elif sub.get('plan_type') == 'new':
            plan_type_display = "🆕 جدید"
        elif sub.get('plan_type') == 'old':
            plan_type_display = "📦 قدیمی"
        else:
            plan_type_display = "📦 معمولی"

        # ============ نمایش حجم — جدا از نام طرح ============
        # برای شارژ دلخواه، دستی، و هر طرحی که remaining_volume دارد نشان بده
        volume_suffix = ""
        if sub.get('plan_type') in ('custom_charge', 'manual') and sub.get('remaining_volume', 0):
            volume_suffix = f" - حجم اشتراک: {sub.get('remaining_volume', 0)} گیگ"
        
        text += f"{i}. {protocol_names.get(sub['protocol'], sub['protocol'])} - {plan_type_display} - {sub['duration_days']} روز - تا {sub['end_date']}{volume_suffix}\n"
   
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]])
    )
# ============ Create VPN Client in 3xUI Panel with Subscription Link ============

async def create_panel_client_and_get_link(email, total_gb, expiry_days, inbound_ids=None, plan_type='old'):
    """
    Create a client in 3xUI panel and get ALL subscription links (one per inbound)
    """
    try:
        from client_manager import get_panel_client
        
        client = get_panel_client()
        success, msg, client_data = client.create_client(email, total_gb, expiry_days, inbound_ids)
        
        if success and client_data:
            # همه لینک‌ها رو بگیر (یکی به ازای هر inbound)
            links = client.get_client_links(email)
            if links and len(links) > 0:
                return True, msg, links   # <-- لیست کامل، نه فقط links[0]
            
            sub_id = client_data.get('subId')
            if sub_id:
                panel_base = client.panel_base
                link = f"{panel_base}/sub/{sub_id}"
                return True, msg, [link]
            else:
                client_info = client.get_client_info(email)
                if client_info:
                    sub_id = client_info.get('subId')
                    if sub_id:
                        panel_base = client.panel_base
                        link = f"{panel_base}/sub/{sub_id}"
                        return True, msg, [link]
                return True, msg, None
        else:
            return False, msg, None
            
    except ImportError:
        logger.error("client_manager module not found")
        return False, "client_manager module not found", None
    except Exception as e:
        logger.error(f"Error creating panel client: {e}")
        return False, str(e), None


async def get_subscription_link(client, sub_id):
    """
    Get subscription link from panel using /panel/api/clients/subLinks/{subId}
    Returns the first URL from the response (usually vmess:// or vless://)
    """
    if not client._ensure_session():
        return None
    
    url = f"{client.panel_base}/panel/api/clients/subLinks/{sub_id}"
    try:
        response = client.session.get(
            url,
            headers=client._get_headers(),
            verify=False,
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        
        # The response is an array of URLs
        urls = result.get('obj', [])
        if urls and len(urls) > 0:
            return urls[0]
        return None
    except Exception as e:
        logger.error(f"Error getting subscription link: {e}")
        return None


async def get_client_subscription_link(email):
    """
    Get subscription link for an existing client by email
    Using /panel/api/clients/links/{email}
    """
    try:
        from client_manager import get_panel_client
        
        client = get_panel_client()
        
        # Try to get client links
        links = client.get_client_links(email)
        if links and len(links) > 0:
            return True, links[0]
        
        # Fallback: get subId and build link
        client_data = client.get_client_info(email)
        if client_data:
            sub_id = client_data.get('subId')
            if sub_id:
                panel_base = client.panel_base
                return True, f"{panel_base}/sub/{sub_id}"
        
        return False, None
    except Exception as e:
        logger.error(f"Error getting client link: {e}")
        return False, None

async def create_subscription_for_purchase(user_id, selected_plan, protocol='v2ray'):
    """
    Create subscription using the best available panel based on plan type
    """
    try:
        # تشخیص نوع طرح
        is_custom = selected_plan.get('is_custom_charge', False)
        plan_type = selected_plan.get('plan_type', 'old')
        
        if is_custom:
            plan_type = 'custom_charge'
        
        # Get available panel based on plan type
        panel_manager = get_panel_manager()
        panel_manager = get_panel_manager()

        # ============ بررسی واجد شرایط بودن کاربر برای پنل اختصاصی کمیسیون ============
        panel_data, panel_id = None, None
        special_panel_id = get_special_panel_id()

        if special_panel_id:
            threshold_percent = get_special_panel_commission_percent()
            total_commission = db.get_total_commission(user_id)
            required_commission = (selected_plan['price'] * threshold_percent) / 100

            if total_commission >= required_commission:
                special_panel = panel_manager.get_panel(special_panel_id)
                if special_panel and special_panel.get('enabled', True):
                    usage = panel_manager.panel_usage.get(special_panel_id, 0)
                    max_subs = special_panel.get('max_subscriptions', 100)
                    special_plan_types = special_panel.get('plan_types', ['new', 'old', 'custom_charge'])
                    if usage < max_subs and plan_type in special_plan_types:
                        panel_data, panel_id = special_panel, special_panel_id
                        logger.info(
                            f"User {user_id} qualified for commission panel {special_panel_id} "
                            f"(commission={total_commission}, required={required_commission})"
                        )

        # اگر واجد شرایط پنل اختصاصی نبود یا آن پنل ظرفیت/تنظیمات مناسب نداشت،
        # از روال معمول انتخاب پنل استفاده کن
        if not panel_data or not panel_id:
            panel_data, panel_id = panel_manager.get_panel_for_subscription(plan_type)

        if not panel_data or not panel_id:
            return False, "هیچ پنل فعالی با ظرفیت کافی برای این نوع طرح وجود ندارد. با پشتیبانی تماس بگیرید.", None
        
        # استفاده از PanelClient با panel_id
        panel_client = PanelClient(panel_id)
        
        # Get active subscriptions for user
        subscriptions = db.get_active_subscriptions(user_id)
        sub_number = len(subscriptions) + 1
        email = f"{user_id}_{sub_number}"
        
        if is_custom:
            plan_type = 'custom_charge'
            total_gb = 5
        elif plan_type == 'old':
            total_gb = 0
        else:
            daily_volume = selected_plan.get('daily_volume', 0)
            total_gb = 4 if daily_volume == 3.5 else int(daily_volume)

        expiry_days = selected_plan.get('days', 30)
        inbound_ids = panel_data.get('inbound_ids', [82, 80, 81])

        success, msg, client_data = panel_client.create_client(
            email=email,
            total_gb=total_gb,
            expiry_days=expiry_days,
            inbound_ids=inbound_ids
        )
        
        if success and client_data:
            # Get links after successful creation
            links = panel_client.get_client_links(email)
            if not links:
                sub_id = client_data.get('subId')
                if sub_id:
                    panel_base = panel_client.panel_base
                    links = [f"{panel_base}/sub/{sub_id}"]
                else:
                    links = []
            
            plan_name = selected_plan.get('name', '')
            initial_volume = 5 if is_custom else 0

            # ============ ذخیره با panel_id ============
            subscription_id = db.add_subscription(
                user_id=user_id,
                protocol=protocol,
                duration_days=expiry_days,
                plan_type=plan_type,
                initial_volume=initial_volume,
                plan_name=plan_name,
                email=email,
                panel_id=panel_id  # <-- مهم: ذخیره panel_id
            )
            
            return True, msg, {
                'subscription_id': subscription_id,
                'email': email,
                'links': links or [],
                'inbound_ids': inbound_ids,
                'panel_id': panel_id
            }
        else:
            return False, msg, None

    except Exception as e:
        logger.error(f"Error in create_subscription_for_purchase: {e}")
        import traceback
        traceback.print_exc()
        return False, f"خطای داخلی: {str(e)}", None
