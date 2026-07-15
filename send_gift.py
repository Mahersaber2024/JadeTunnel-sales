import logging
import html as html_lib
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, KeyboardButtonRequestUsers
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

# ====================== Constants ======================
GIFT_RECIPIENT_INPUT, GIFT_AMOUNT_INPUT, GIFT_MESSAGE_INPUT, GIFT_CONFIRM = range(4)

MIN_GIFT_AMOUNT = 5000
CANCEL_TEXT = "❌ انصراف از ارسال هدیه"
SKIP_MESSAGE_TEXT = "⏭ رد کردن پیام"

# request_id دلخواه برای شناسایی درخواست انتخاب کاربر (باید همیشه همین مقدار باشد)
PICK_FRIEND_REQUEST_ID = 1001

db = None
get_main_menu_func = None


def set_db(database):
    global db
    db = database


def set_get_main_menu(func):
    global get_main_menu_func
    get_main_menu_func = func


def get_main_menu():
    if get_main_menu_func:
        return get_main_menu_func()
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup([[KeyboardButton("🏠 منو")]], resize_keyboard=True)


def _cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton(CANCEL_TEXT)]], resize_keyboard=True)


def _skip_or_cancel_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(SKIP_MESSAGE_TEXT)], [KeyboardButton(CANCEL_TEXT)]],
        resize_keyboard=True
    )


def _pick_friend_keyboard():
    """کیبورد شامل دکمه‌ی انتخاب مخاطب از لیست تلگرام کاربر + انصراف"""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(
                "👤 انتخاب از مخاطبین تلگرام",
                request_users=KeyboardButtonRequestUsers(
                    request_id=PICK_FRIEND_REQUEST_ID,
                    max_quantity=1,
                )
            )],
            [KeyboardButton(CANCEL_TEXT)]
        ],
        resize_keyboard=True
    )


def _display_name(user, fallback_id):
    if not user:
        return str(fallback_id)
    name = user.get('first_name') if isinstance(user, dict) else getattr(user, 'first_name', None)
    username = user.get('username') if isinstance(user, dict) else getattr(user, 'username', None)
    if name:
        return name
    if username:
        return f"@{username}"
    return str(fallback_id)


# ====================== Utility ======================
async def _update_or_create_user(bot, user_id, user_obj=None):
    if not user_obj:
        try:
            user_obj = await bot.get_chat(user_id)
        except:
            return None
    db.add_user(user_id, getattr(user_obj, 'username', None), getattr(user_obj, 'first_name', None), None)
    return db.get_user(user_id)


async def _try_resolve_username(bot, raw_text: str):
    username = raw_text.strip().lstrip('@')
    if not username or username.isdigit():
        return None
    try:
        chat = await bot.get_chat(f"@{username}")
        if chat.type == "private":
            return chat
    except Exception as e:
        logger.warning(f"Username resolve failed @{username}: {e}")
    return None


async def _proceed_with_recipient(source, context, target_id: int, target_user, is_callback=False):
    sender_id = source.from_user.id if hasattr(source, 'from_user') else source.message.from_user.id

    if target_id == sender_id:
        text = "😅 نمی‌تونی به خودت هدیه بفرستی!"
        if is_callback:
            await source.answer(text, show_alert=True)
        else:
            await source.reply_text(text, reply_markup=_pick_friend_keyboard())
        return GIFT_RECIPIENT_INPUT

    if not target_user:
        if is_callback:
            await source.answer("❌ این کاربر هنوز عضو ربات نشده.", show_alert=True)
        else:
            await source.reply_text(
                "❌ این کاربر هنوز با /start عضو نشده.\nاز دوستت بخواه اول عضو بشه.",
                reply_markup=_pick_friend_keyboard()
            )
        return GIFT_RECIPIENT_INPUT

    name = _display_name(target_user, target_id)
    context.user_data['gift_target_id'] = target_id
    context.user_data['gift_target_name'] = name

    reply_text = (
        f"🎯 گیرنده: <b>{html_lib.escape(name)}</b>\n\n"
        f"حالا مبلغ هدیه را وارد کن (تومان):\nمثال: 20000\n\n"
        f"⚠️ حداقل: {MIN_GIFT_AMOUNT:,} تومان"
    )

    if is_callback:
        await source.message.reply_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=_cancel_keyboard())
    else:
        await source.reply_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=_cancel_keyboard())

    return GIFT_AMOUNT_INPUT


# ====================== Handlers ======================
async def gift_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد.")
        return ConversationHandler.END

    balance_str = f"{user.get('balance', 0):,}"

    text = (
        f"🎁 <b>ارسال هدیه به دوستت</b>\n\n"
        f"💳 موجودی فعلی: <b>{balance_str} تومان</b>\n\n"
        f"👇 روی دکمه زیر بزن و دوستت رو از لیست مخاطبین تلگرامت انتخاب کن:"
    )

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=_pick_friend_keyboard()
    )

    return GIFT_RECIPIENT_INPUT


async def gift_users_shared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی کاربر از طریق دکمه‌ی انتخاب مخاطب تلگرام، یک نفر را انتخاب می‌کند"""
    message = update.message
    shared = message.users_shared

    if not shared or not shared.users:
        await message.reply_text(
            "❌ مخاطبی انتخاب نشد. دوباره تلاش کن:",
            reply_markup=_pick_friend_keyboard()
        )
        return GIFT_RECIPIENT_INPUT

    picked_user = shared.users[0]
    target_id = picked_user.user_id

    # تلگرام معمولاً فقط user_id را برمی‌گرداند؛ برای گرفتن نام/یوزرنیم باید از دیتابیس یا get_chat استفاده کنیم
    target_user = db.get_user(target_id)
    if not target_user:
        target_user = await _update_or_create_user(context.bot, target_id)

    return await _proceed_with_recipient(message, context, target_id, target_user)


async def gift_recipient_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = (message.text or '').strip()

    if text == CANCEL_TEXT:
        await message.reply_text("❌ ارسال هدیه لغو شد.", reply_markup=get_main_menu())
        return ConversationHandler.END

    # فوروارد
    forwarded_user = None
    if message.forward_origin and hasattr(message.forward_origin, 'sender_user') and message.forward_origin.sender_user:
        forwarded_user = message.forward_origin.sender_user
    elif message.forward_from:
        forwarded_user = message.forward_from

    if forwarded_user:
        target_id = forwarded_user.id
        target_user = db.get_user(target_id) or await _update_or_create_user(context.bot, target_id, forwarded_user)
        return await _proceed_with_recipient(message, context, target_id, target_user)

    # آیدی عددی
    if text.isdigit():
        target_id = int(text)
        target_user = db.get_user(target_id) or await _update_or_create_user(context.bot, target_id)
        return await _proceed_with_recipient(message, context, target_id, target_user)

    # یوزرنیم
    if '@' in text:
        resolved = await _try_resolve_username(context.bot, text)
        if resolved:
            target_id = resolved.id
            target_user = db.get_user(target_id) or await _update_or_create_user(context.bot, target_id, resolved)
            return await _proceed_with_recipient(message, context, target_id, target_user)

    await message.reply_text(
        "❌ متوجه نشدم 🙈\n\nاز دکمه‌ی «👤 انتخاب از مخاطبین تلگرام» استفاده کن.",
        reply_markup=_pick_friend_keyboard()
    )
    return GIFT_RECIPIENT_INPUT


async def gift_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = (message.text or '').strip()

    if text == CANCEL_TEXT:
        await message.reply_text("❌ ارسال هدیه لغو شد.", reply_markup=get_main_menu())
        return ConversationHandler.END

    try:
        amount = int(text)
    except ValueError:
        await message.reply_text("❌ لطفاً فقط عدد وارد کنید (مثال: 20000)", reply_markup=_cancel_keyboard())
        return GIFT_AMOUNT_INPUT

    if amount < MIN_GIFT_AMOUNT:
        await message.reply_text(f"❌ حداقل مبلغ هدیه {MIN_GIFT_AMOUNT:,} تومان است.", reply_markup=_cancel_keyboard())
        return GIFT_AMOUNT_INPUT

    sender = db.get_user(update.effective_user.id)
    if amount > sender.get('balance', 0):
        await message.reply_text("❌ موجودی کافی نیست!", reply_markup=_cancel_keyboard())
        return GIFT_AMOUNT_INPUT

    context.user_data['gift_amount'] = amount

    await message.reply_text(
        f"💌 اگر می‌خواهید پیام همراه هدیه بفرستید بنویسید، وگرنه دکمه «{SKIP_MESSAGE_TEXT}» را بزنید:",
        reply_markup=_skip_or_cancel_keyboard()
    )
    return GIFT_MESSAGE_INPUT


async def gift_message_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = (message.text or '').strip()

    if text == CANCEL_TEXT:
        await message.reply_text("❌ لغو شد.", reply_markup=get_main_menu())
        return ConversationHandler.END

    context.user_data['gift_message'] = None if text == SKIP_MESSAGE_TEXT else text[:300]

    target_name = context.user_data.get('gift_target_name', '')
    amount = context.user_data.get('gift_amount')

    summary = (
        f"📋 <b>خلاصه هدیه</b>\n\n"
        f"🎯 گیرنده: {html_lib.escape(target_name)}\n"
        f"🎁 مبلغ: {amount:,} تومان\n"
    )
    if context.user_data.get('gift_message'):
        summary += f"💌 پیام: <blockquote>{html_lib.escape(context.user_data['gift_message'])}</blockquote>\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ارسال کن", callback_data="gift_confirm_yes")],
        [InlineKeyboardButton("❌ انصراف", callback_data="gift_confirm_no")]
    ])

    await message.reply_text(summary, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return GIFT_CONFIRM


async def gift_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "gift_confirm_no":
        await query.edit_message_text("❌ ارسال هدیه لغو شد.")
        await query.message.reply_text("به منوی اصلی خوش آمدید!", reply_markup=get_main_menu())
        context.user_data.clear()
        return ConversationHandler.END

    sender_id = query.from_user.id
    target_id = context.user_data.get('gift_target_id')
    amount = context.user_data.get('gift_amount')
    gift_message = context.user_data.get('gift_message')

    sender = db.get_user(sender_id)
    if sender.get('balance', 0) < amount:
        await query.edit_message_text("❌ موجودی کافی نیست!")
        return ConversationHandler.END

    db.update_balance(sender_id, -amount)
    db.add_transaction(sender_id, -amount, "gift_sent", f"ارسال هدیه به {target_id}")

    db.update_balance(target_id, amount)
    db.add_transaction(target_id, amount, "gift_received", f"دریافت هدیه از {sender_id}")

    await query.edit_message_text(f"✅ هدیه به {context.user_data.get('gift_target_name')} ارسال شد!")

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎁 هدیه‌ای به مبلغ {amount:,} تومان از طرف {sender.get('first_name')} دریافت کردید!",
            parse_mode=ParseMode.HTML
        )
    except:
        pass

    context.user_data.clear()
    await query.message.reply_text("به منوی اصلی خوش آمدید!", reply_markup=get_main_menu())
    return ConversationHandler.END


async def gift_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("❌ ارسال هدیه لغو شد.", reply_markup=get_main_menu())
    return ConversationHandler.END
