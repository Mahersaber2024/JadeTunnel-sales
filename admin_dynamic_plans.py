#!/usr/bin/env python3
# admin_dynamic_plans.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import dynamic_plans as dp

logger = logging.getLogger(__name__)

# States در بازه‌ی 200-207 تا با استیت‌های admin.py (که تا حدود 38 می‌روند) تداخل نداشته باشد
(
    ADMIN_DYNPLAN_CATEGORY,
    ADMIN_DYNPLAN_NAME,
    ADMIN_DYNPLAN_DESC,
    ADMIN_DYNPLAN_PRICE,
    ADMIN_DYNPLAN_DAYS,
    ADMIN_DYNPLAN_VOLUME,
    ADMIN_DYNPLAN_DAILY,
) = range(200, 207)

# استیت‌های مربوط به ساخت/تغییرنام/ویرایش متن پایین صفحه‌ی «طرح» (scheme)
# در بازه‌ی 210 تا با بازه‌ی بالا و استیت‌های admin.py تداخل نداشته باشد
(
    ADMIN_DYNSCHEME_NAME,
    ADMIN_DYNSCHEME_FOOTER,
) = range(210, 212)


def _scheme_label(scheme_id: str) -> str:
    """نام قابل‌نمایش یک طرح؛ اگر طرح حذف شده باشد، خود شناسه را برمی‌گرداند"""
    scheme = dp.get_scheme(scheme_id)
    return scheme.get('name') if scheme else (scheme_id or '-')

# تابع is_admin از admin.py در main.py تزریق می‌شود تا وابستگی دوطرفه نداشته باشیم
_is_admin_func = None


def set_is_admin(func):
    global _is_admin_func
    _is_admin_func = func


def _is_admin(user_id: int) -> bool:
    return _is_admin_func(user_id) if _is_admin_func else False


def _plan_line(plan: dict) -> str:
    status = "✅" if plan.get('enabled', True) else "❌"
    vol = "نامحدود" if not plan.get('volume') else f"{plan['volume']} گیگ"
    cat = _scheme_label(plan.get('category', 'new'))
    return f"{status} [{cat}] {plan.get('name')} | {plan.get('price'):,} ت | {plan.get('days')} روز | {vol}"


# ============ لیست/منوی اصلی ============
async def admin_plans_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    plans = dp.get_all_plans(active_only=False)
    keyboard = []
    for pid, plan in plans.items():
        keyboard.append([InlineKeyboardButton(_plan_line(plan), callback_data=f"dynplan_view_{pid}")])
    keyboard.append([InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="dynplan_add_start")])
    keyboard.append([InlineKeyboardButton("🗂 مدیریت طرح‌ها", callback_data="dynscheme_menu")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_to_main_menu")])

    text = "📋 مدیریت پلن‌های خرید\n\n"
    if plans:
        text += "پلن‌های زیر در بخش «🛒 خرید VPN» به کاربران نمایش داده می‌شوند.\nروی هر پلن بزنید تا ویرایش/حذف کنید:"
    else:
        text += (
            "هنوز هیچ پلنی ثبت نشده است.\n\n"
            "⚠️ برای اینکه پلن‌های داینامیک واقعاً قابل خرید باشند، حتماً باید حداقل یک پنل\n"
            "پشتیبانی از «🧩 طرح‌های داینامیک» را در بخش «مدیریت پنل‌ها ← ویرایش طرح‌ها» فعال کرده باشد."
        )

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ============ مدیریت «طرح‌ها» (schemes) ============
# «طرح» همان دسته‌بندی بالایی است که کاربر در منوی «🎯 انتخاب نوع طرح» می‌بیند
# (مثل «طرح جدید» / «طرح قدیمی»). برخلاف پلن‌ها که همیشه داینامیک بودند،
# قبلاً این دسته‌ها فقط دو مقدار ثابت 'new'/'old' در کد بودند؛ حالا خودشان هم
# یک لیست کاملاً قابل‌مدیریت (ساخت/تغییرنام/حذف/فعال‌غیرفعال/ویرایش متن پایین صفحه) هستند.

def _scheme_line(scheme_id: str, scheme: dict) -> str:
    status = "✅" if scheme.get('enabled', True) else "❌"
    count = dp.scheme_plan_count(scheme_id)
    return f"{status} {scheme.get('name')} ({count} پلن)"


async def admin_schemes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return

    schemes = dp.get_all_schemes(enabled_only=False)
    keyboard = []
    for sid, s in schemes.items():
        keyboard.append([InlineKeyboardButton(_scheme_line(sid, s), callback_data=f"dynscheme_view_{sid}")])
    keyboard.append([InlineKeyboardButton("➕ ساخت طرح جدید", callback_data="dynscheme_add_start")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_dynamic_plans_menu")])

    text = (
        "🗂 مدیریت طرح‌ها\n\n"
        "«طرح» همان دسته‌بندی بالایی است که کاربر توی منوی «🎯 انتخاب نوع طرح» می‌بیند "
        "(مثل «🆕 طرح جدید» / «📦 طرح قدیمی»). هر پلنی که می‌سازید باید زیر یکی از این طرح‌ها قرار بگیرد.\n\n"
        "روی هر طرح بزنید تا ویرایش/فعال‌غیرفعال/حذف کنید:"
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_scheme_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    scheme_id = query.data.replace("dynscheme_view_", "")
    scheme = dp.get_scheme(scheme_id)
    if not scheme:
        await query.edit_message_text(
            "❌ این طرح یافت نشد (شاید قبلاً حذف شده).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="dynscheme_menu")]])
        )
        return

    count = dp.scheme_plan_count(scheme_id)
    footer_display = scheme.get('footer_text') or '(خالی — متن پیش‌فرض نمایش داده می‌شود)'
    text = (
        f"🗂 {scheme.get('name')}\n\n"
        f"📝 توضیحات: {scheme.get('description') or '-'}\n\n"
        f"📄 متن پایین صفحه (بالای دکمه جزئیات بیشتر):\n{footer_display}\n\n"
        f"📦 تعداد پلن‌های این طرح: {count}\n"
        f"🔰 وضعیت: {'✅ فعال' if scheme.get('enabled', True) else '❌ غیرفعال'}\n\n"
        f"🆔 شناسه: {scheme_id}"
    )
    keyboard = [
        [InlineKeyboardButton("✏️ تغییر نام", callback_data=f"dynscheme_rename_{scheme_id}")],
        [InlineKeyboardButton("📝 ویرایش متن پایین صفحه", callback_data=f"dynscheme_editfooter_{scheme_id}")],
        [InlineKeyboardButton(
            "❌ غیرفعال کن (پنهان از منوی خرید)" if scheme.get('enabled', True) else "✅ فعال کن",
            callback_data=f"dynscheme_toggle_{scheme_id}"
        )],
        [InlineKeyboardButton("🗑 حذف طرح", callback_data=f"dynscheme_delete_{scheme_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="dynscheme_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_scheme_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔️ No access.", show_alert=True)
        return
    scheme_id = query.data.replace("dynscheme_toggle_", "")
    dp.toggle_scheme(scheme_id)
    await query.answer("✅ وضعیت طرح بروزرسانی شد.")
    await admin_schemes_menu(update, context)


async def admin_scheme_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔️ No access.", show_alert=True)
        return
    scheme_id = query.data.replace("dynscheme_delete_", "")
    ok, msg = dp.delete_scheme(scheme_id)
    await query.answer(("🗑 " if ok else "⚠️ ") + msg, show_alert=not ok)
    await admin_schemes_menu(update, context)


# ---------- افزودن/تغییرنام/ویرایش متن طرح (Conversation) ----------

async def admin_scheme_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ساخت یک طرح جدید — ابتدا اسم پرسیده می‌شود"""
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    context.user_data.pop('dynscheme_target_id', None)
    context.user_data.pop('dynscheme_new_name', None)
    context.user_data.pop('dynscheme_footer_target_id', None)

    await query.edit_message_text(
        "➕ ساخت طرح جدید\n\n"
        "📛 لطفاً نام این طرح را وارد کنید (همان چیزی که در منوی «🎯 انتخاب نوع طرح» به کاربر نمایش داده می‌شود):\n"
        "مثلاً: 💎 طرح ویژه\n\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNSCHEME_NAME


async def admin_scheme_rename_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع تغییر نام یک طرح موجود"""
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    scheme_id = query.data.replace("dynscheme_rename_", "")
    scheme = dp.get_scheme(scheme_id)
    if not scheme:
        await query.edit_message_text("❌ این طرح یافت نشد (شاید قبلاً حذف شده).")
        return ConversationHandler.END

    context.user_data.pop('dynscheme_new_name', None)
    context.user_data.pop('dynscheme_footer_target_id', None)
    context.user_data['dynscheme_target_id'] = scheme_id

    await query.edit_message_text(
        f"✏️ تغییر نام طرح «{scheme.get('name')}»\n\n"
        "📛 لطفاً نام جدید را وارد کنید:\n\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNSCHEME_NAME


async def admin_scheme_editfooter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش متن پایین صفحه‌ی یک طرح موجود"""
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    scheme_id = query.data.replace("dynscheme_editfooter_", "")
    scheme = dp.get_scheme(scheme_id)
    if not scheme:
        await query.edit_message_text("❌ این طرح یافت نشد (شاید قبلاً حذف شده).")
        return ConversationHandler.END

    context.user_data.pop('dynscheme_target_id', None)
    context.user_data.pop('dynscheme_new_name', None)
    context.user_data['dynscheme_footer_target_id'] = scheme_id

    current = scheme.get('footer_text') or '(خالی — متن پیش‌فرض نمایش داده می‌شود)'
    await query.edit_message_text(
        f"📝 ویرایش متن پایین صفحه‌ی «{scheme.get('name')}»\n\n"
        f"متن فعلی:\n{current}\n\n"
        "لطفاً متن جدید را وارد کنید (می‌توانید لینک HTML هم بگذارید)، مثال:\n"
        'لطفاً پلن مورد نظر را انتخاب کنید:\n\n<a href="https://t.me/yourchannel/1">جزئیات بیشتر</a>\n\n'
        "برای پاک کردن و برگشت به پیش‌فرض، فقط - بفرستید.\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNSCHEME_FOOTER


async def admin_scheme_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دریافت نام طرح.
    - اگر در حال «تغییرنام» یک طرح موجود بودیم (dynscheme_target_id ست شده)،
      فقط نام را آپدیت کرده و تمام می‌شود.
    - اگر در حال «ساخت» طرح جدید بودیم، نام را نگه می‌داریم و مرحله بعد
      متن پایین صفحه را می‌پرسیم.
    """
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.")
        context.user_data.pop('dynscheme_target_id', None)
        context.user_data.pop('dynscheme_new_name', None)
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("❌ نام نمی‌تواند خالی باشد. دوباره وارد کنید:")
        return ADMIN_DYNSCHEME_NAME

    target_id = context.user_data.get('dynscheme_target_id')
    if target_id:
        dp.update_scheme(target_id, name=text)
        await update.message.reply_text(f"✅ نام طرح به «{text}» تغییر کرد.")
        context.user_data.pop('dynscheme_target_id', None)
        return ConversationHandler.END

    # ساخت طرح جدید - حالا متن پایین صفحه را می‌پرسیم
    context.user_data['dynscheme_new_name'] = text
    await update.message.reply_text(
        "📝 حالا متنی که پایین لیست پلن‌ها (بالای دکمه «جزئیات بیشتر») نمایش داده می‌شود را وارد کنید.\n"
        "می‌توانید لینک HTML هم بگذارید، مثال:\n"
        'لطفاً پلن مورد نظر را انتخاب کنید:\n\n<a href="https://t.me/yourchannel/1">جزئیات بیشتر</a>\n\n'
        "برای رد کردن و استفاده از متن پیش‌فرض، فقط - بفرستید.\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNSCHEME_FOOTER


async def admin_scheme_footer_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دریافت متن پایین صفحه.
    - اگر در حال «ویرایش» متن یک طرح موجود بودیم (dynscheme_footer_target_id ست شده)،
      فقط متن را آپدیت می‌کند.
    - در غیر این صورت، این آخرین مرحله‌ی «ساخت طرح جدید» است؛ طرح را با نام
      ذخیره‌شده در dynscheme_new_name و این متن می‌سازد.
    """
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.")
        for k in ('dynscheme_target_id', 'dynscheme_new_name', 'dynscheme_footer_target_id'):
            context.user_data.pop(k, None)
        return ConversationHandler.END

    footer_text = '' if text == '-' else text

    # حالت ویرایش متن یک طرح موجود
    edit_target = context.user_data.pop('dynscheme_footer_target_id', None)
    if edit_target:
        dp.update_scheme(edit_target, footer_text=footer_text)
        await update.message.reply_text("✅ متن پایین صفحه با موفقیت بروزرسانی شد.")
        return ConversationHandler.END

    # حالت ساخت طرح جدید
    name = context.user_data.pop('dynscheme_new_name', None)
    if not name:
        await update.message.reply_text("❌ خطا! لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    dp.add_scheme(name, footer_text=footer_text)
    await update.message.reply_text(
        f"✅ طرح «{name}» ساخته شد و همین الان در منوی «🎯 انتخاب نوع طرح» کاربران قابل مشاهده است!\n\n"
        "حالا می‌تونید از «➕ افزودن پلن جدید» یک پلن زیر این طرح اضافه کنید."
    )
    return ConversationHandler.END


async def admin_scheme_name_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فال‌بک برای /cancel در حین conversation ساخت/تغییرنام/ویرایش متن طرح"""
    await update.message.reply_text("❌ عملیات لغو شد.")
    for k in ('dynscheme_target_id', 'dynscheme_new_name', 'dynscheme_footer_target_id'):
        context.user_data.pop(k, None)
    return ConversationHandler.END


async def admin_plan_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    plan_id = query.data.replace("dynplan_view_", "")
    plan = dp.get_plan(plan_id)
    if not plan:
        await query.edit_message_text(
            "❌ این طرح یافت نشد (شاید قبلاً حذف شده).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_dynamic_plans_menu")]])
        )
        return

    vol = "نامحدود" if not plan.get('volume') else f"{plan['volume']} گیگ"
    cat = _scheme_label(plan.get('category', 'new'))
    text = (
        f"📦 {plan.get('name')}\n\n"
        f"🎯 دسته: {cat}\n"
        f"📝 توضیحات: {plan.get('description') or '-'}\n"
        f"💰 قیمت: {plan.get('price'):,} تومان\n"
        f"⏰ مدت: {plan.get('days')} روز\n"
        f"📊 حجم: {vol}\n"
        f"🔰 وضعیت: {'✅ فعال' if plan.get('enabled', True) else '❌ غیرفعال'}\n\n"
        f"🆔 شناسه: {plan_id}"
    )
    keyboard = [
        [InlineKeyboardButton(
            "❌ غیرفعال کن (پنهان از کاربران)" if plan.get('enabled', True) else "✅ فعال کن",
            callback_data=f"dynplan_toggle_{plan_id}"
        )],
        [InlineKeyboardButton("🗑 حذف کامل طرح", callback_data=f"dynplan_delete_{plan_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_dynamic_plans_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_plan_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔️ No access.", show_alert=True)
        return
    plan_id = query.data.replace("dynplan_toggle_", "")
    dp.toggle_plan(plan_id)
    await query.answer("✅ وضعیت طرح بروزرسانی شد.")
    await admin_plans_menu(update, context)


async def admin_plan_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_admin(query.from_user.id):
        await query.answer("⛔️ No access.", show_alert=True)
        return
    plan_id = query.data.replace("dynplan_delete_", "")
    dp.delete_plan(plan_id)
    await query.answer("🗑 طرح حذف شد.")
    await admin_plans_menu(update, context)


# ============ افزودن طرح جدید (Conversation) ============
async def admin_plan_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    schemes = dp.get_all_schemes(enabled_only=True)
    if not schemes:
        await query.edit_message_text(
            "⚠️ هنوز هیچ «طرحی» ساخته نشده که پلن را زیر آن اضافه کنید.\n"
            "اول از «🗂 مدیریت طرح‌ها» یک طرح بسازید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗂 مدیریت طرح‌ها", callback_data="dynscheme_menu")]
            ])
        )
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(s.get('name', sid), callback_data=f"dynplan_scheme_{sid}")]
        for sid, s in schemes.items()
    ]
    keyboard.append([InlineKeyboardButton("🔙 انصراف", callback_data="admin_dynamic_plans_menu")])
    await query.edit_message_text(
        "➕ افزودن پلن جدید\n\n"
        "📛 این پلن را به کدام طرح اضافه می‌کنید؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_DYNPLAN_CATEGORY


async def admin_plan_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    scheme_id = query.data.replace("dynplan_scheme_", "")
    scheme = dp.get_scheme(scheme_id)
    if not scheme:
        await query.edit_message_text("❌ این طرح یافت نشد (شاید حذف شده). دوباره از منو تلاش کنید.")
        return ConversationHandler.END

    context.user_data['dynplan_category'] = scheme_id

    await query.edit_message_text(
        f"➕ افزودن پلن جدید — طرح: {scheme.get('name')}\n\n"
        "📛 لطفاً نام دلخواه پلن را وارد کنید (همراه با ایموجی اگر می‌خواهید):\n"
        "مثلاً: 🟢 وصل باش\n\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNPLAN_NAME


async def admin_plan_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END
    if not text:
        await update.message.reply_text("❌ نام نمی‌تواند خالی باشد. دوباره وارد کنید:")
        return ADMIN_DYNPLAN_NAME

    context.user_data['dynplan_name'] = text
    await update.message.reply_text(
        "📝 لطفاً متن/توضیحاتی که زیر نام طرح به کاربر نمایش داده می‌شود را وارد کنید.\n"
        "(مثال: سرعت بالا + پایداری کامل + بدون قطعی)\n\n"
        "برای رد کردن این مرحله فقط - بفرستید.\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNPLAN_DESC


async def admin_plan_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END

    context.user_data['dynplan_desc'] = '' if text == '-' else text
    await update.message.reply_text(
        "💰 لطفاً قیمت طرح را به تومان وارد کنید (فقط عدد):\nمثال: 199000\n\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNPLAN_PRICE


async def admin_plan_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END
    try:
        price = int(text)
        if price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ لطفاً فقط عدد صحیح مثبت وارد کنید:")
        return ADMIN_DYNPLAN_PRICE

    context.user_data['dynplan_price'] = price
    await update.message.reply_text(
        "⏰ لطفاً مدت اعتبار طرح را به روز وارد کنید:\nمثال: 30\n\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNPLAN_DAYS


async def admin_plan_add_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END
    try:
        days = int(text)
        if days < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ لطفاً عدد صحیح حداقل 1 وارد کنید:")
        return ADMIN_DYNPLAN_DAYS

    context.user_data['dynplan_days'] = days
    await update.message.reply_text(
        "📊 لطفاً حجم کل طرح را به گیگابایت وارد کنید (0 برای نامحدود):\nمثال: 100\n\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNPLAN_VOLUME


async def admin_plan_add_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END
    try:
        volume = float(text)
        if volume < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ لطفاً عدد معتبر وارد کنید (0 برای نامحدود):")
        return ADMIN_DYNPLAN_VOLUME

    context.user_data['dynplan_volume'] = volume
    await update.message.reply_text(
        "📅 حجم روزانه (اختیاری - فقط برای نمایش به کاربر) را به گیگ وارد کنید.\n"
        "اگر نمی‌خواهید نمایش داده شود، فقط - بفرستید.\n\n"
        "⚠️ برای لغو /cancel را ارسال کنید."
    )
    return ADMIN_DYNPLAN_DAILY


async def admin_plan_add_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END

    daily_volume = None
    if text != '-':
        try:
            daily_volume = float(text)
        except ValueError:
            await update.message.reply_text("❌ عدد نامعتبر است. یا عدد بفرستید یا - :")
            return ADMIN_DYNPLAN_DAILY

    name = context.user_data.get('dynplan_name')
    desc = context.user_data.get('dynplan_desc', '')
    price = context.user_data.get('dynplan_price')
    days = context.user_data.get('dynplan_days')
    volume = context.user_data.get('dynplan_volume')
    category = context.user_data.get('dynplan_category', 'new')

    dp.add_plan(name, desc, price, days, volume, daily_volume, category=category)

    vol_text = "نامحدود" if not volume else f"{volume} گیگ"
    await update.message.reply_text(
        f"✅ پلن جدید با موفقیت اضافه شد و همین الان در «🛒 خرید VPN ← {_scheme_label(category)}» قابل مشاهده است!\n\n"
        f"📦 نام: {name}\n"
        f"💰 قیمت: {price:,} تومان\n"
        f"⏰ مدت: {days} روز\n"
        f"📊 حجم: {vol_text}\n\n"
        f"⚠️ یادآوری: اگر تا حالا هیچ پنلی از «🧩 طرح‌های داینامیک» پشتیبانی نکرده،\n"
        f"از بخش «مدیریت پنل‌ها ← [نام پنل] ← ✏️ ویرایش طرح‌ها» آن را برای حداقل یک پنل فعال کنید."
    )

    for key in ('dynplan_name', 'dynplan_desc', 'dynplan_price', 'dynplan_days', 'dynplan_volume', 'dynplan_category'):
        context.user_data.pop(key, None)

    return ConversationHandler.END


async def admin_plan_add_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فال‌بک برای /cancel در حین conversation"""
    await update.message.reply_text("❌ عملیات لغو شد.")
    for key in ('dynplan_name', 'dynplan_desc', 'dynplan_price', 'dynplan_days', 'dynplan_volume', 'dynplan_category'):
        context.user_data.pop(key, None)
    return ConversationHandler.END
