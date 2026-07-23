#!/usr/bin/env python3
# admin_send_plan.py
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import dynamic_plans as dp
from logger_bot import log_panel_error

logger = logging.getLogger(__name__)

# استیت‌ها در بازه‌ی 300-307 تا با استیت‌های admin.py (تا ~38) و
# admin_dynamic_plans.py (200-211) تداخل نداشته باشد
(
    ADMSP_TARGET,
    ADMSP_USER_ID,
    ADMSP_SCHEME,
    ADMSP_PLAN,
    ADMSP_REPLACE,
    ADMSP_DELAY,
    ADMSP_CONFIRM,
) = range(300, 307)

# فاصله‌ی زمانی پیش‌فرض/قابل انتخاب بین ساخت کلاینت هر کاربر (ثانیه)
DELAY_PRESETS = [2, 3, 5, 10]
DEFAULT_DELAY_SECONDS = 3

# ============ سیاست‌های جایگزینی طرح تکراری ============
# none        -> طرح قبلی دست‌نخورده می‌ماند، طرح جدید هم اضافه می‌شود
# db_only     -> طرح قبلی فقط از دیتابیس حذف می‌شود (روی پنل باقی می‌ماند)
# db_and_api  -> طرح قبلی هم از دیتابیس و هم از پنل (API) حذف می‌شود
REPLACE_NONE = 'none'
REPLACE_DB_ONLY = 'db_only'
REPLACE_DB_AND_API = 'db_and_api'

# ============ وابستگی‌ها (تزریق‌شونده از main.py، برای جلوگیری از import حلقوی) ============
db = None
_is_admin_func = None
get_main_menu_func = None
_create_subscription_for_purchase = None  # تابع handlers.create_subscription_for_purchase
_get_single_sub_link = None                # تابع handlers.get_single_sub_link


def set_db(database):
    global db
    db = database


def set_is_admin(func):
    global _is_admin_func
    _is_admin_func = func


def _is_admin(user_id: int) -> bool:
    return _is_admin_func(user_id) if _is_admin_func else False


def set_get_main_menu(func):
    global get_main_menu_func
    get_main_menu_func = func


def get_main_menu():
    if get_main_menu_func:
        return get_main_menu_func()
    from telegram import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup([[KeyboardButton("🏠 منو")]], resize_keyboard=True)


def set_purchase_deps(create_subscription_for_purchase_func, get_single_sub_link_func):
    """
    تزریق توابع خرید از handlers.py:
    - create_subscription_for_purchase(user_id, selected_plan, protocol) -> همان تابعی
      که هنگام خرید عادی کاربر صدا زده می‌شود (ساخت کلاینت روی پنل + ثبت در دیتابیس)
    - get_single_sub_link(subscription_id) -> ساخت لینک اشتراک اختصاصی همان طرح
    """
    global _create_subscription_for_purchase, _get_single_sub_link
    _create_subscription_for_purchase = create_subscription_for_purchase_func
    _get_single_sub_link = get_single_sub_link_func


def _custom_charge_plan() -> dict:
    """همان selected_plan طرح «شارژ دلخواه» که در خرید عادی استفاده می‌شود"""
    return {
        "name": "🔥 طرح شارژ دلخواه",
        "price": 112000,
        "days": 30,
        "volume": 5,
        "is_custom_charge": True,
        "plan_type": "custom_charge",
    }


def _plan_type_of(selected_plan: dict) -> str:
    """plan_type ای که هنگام ثبت در دیتابیس برای این طرح استفاده می‌شود"""
    if selected_plan.get('is_custom_charge'):
        return 'custom_charge'
    return selected_plan.get('plan_type', dp.DYNAMIC_PLAN_TYPE)


def _find_matching_subscriptions(user_id: int, selected_plan: dict) -> list:
    """
    اشتراک‌های فعال کاربر که دقیقاً همین «طرح» (بر اساس plan_type + plan_name) را
    دارند برمی‌گرداند. تشخیص «همان طرح» بر اساس نام و نوع طرح است، چون plan_id
    داینامیک در جدول subscriptions ذخیره نمی‌شود.
    """
    if not db:
        return []
    plan_type = _plan_type_of(selected_plan)
    plan_name = selected_plan.get('name')
    try:
        subs = db.get_active_subscriptions(user_id) or []
    except Exception as e:
        logger.error(f"Error checking existing subscriptions for {user_id}: {e}")
        return []
    return [
        s for s in subs
        if s.get('plan_type') == plan_type and s.get('plan_name') == plan_name
    ]


def _delete_matching_subscriptions(matches: list, replace_mode: str):
    """
    طرح(های) تکراری را طبق سیاست انتخاب‌شده‌ی ادمین حذف می‌کند.
    Returns: تعداد رکوردهایی که از دیتابیس حذف شدند
    """
    deleted = 0
    for sub in matches:
        try:
            db.delete_subscription(sub['id'])
            deleted += 1
        except Exception as e:
            logger.error(f"Error deleting old subscription {sub.get('id')}: {e}")
            continue

        if replace_mode == REPLACE_DB_AND_API and sub.get('email'):
            try:
                from client_manager import get_panel_client
                panel_client = get_panel_client(sub.get('panel_id'))
                panel_client.delete_client(sub['email'])
            except Exception as e:
                logger.error(
                    f"Error deleting old client '{sub.get('email')}' from panel: {e}"
                )
    return deleted


# ============ Entry point ============
async def admin_send_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    context.user_data.pop('admsp_targets', None)
    context.user_data.pop('admsp_target_label', None)
    context.user_data.pop('admsp_selected_plan', None)
    context.user_data.pop('admsp_delay', None)
    context.user_data.pop('admsp_replace_mode', None)

    keyboard = [
        [InlineKeyboardButton("👤 کاربر خاص", callback_data="admsp_target_single")],
        [InlineKeyboardButton("👥 همه کاربران", callback_data="admsp_target_all")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_to_main_menu")],
    ]
    await query.edit_message_text(
        "🎁 ارسال طرح توسط ادمین\n\n"
        "این طرح دقیقاً به همان روشی که کاربر خودش می‌خرد ساخته و برای او ارسال می‌شود "
        "(بدون کسر از کیف پول کاربر).\n\n"
        "👇 گیرنده را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMSP_TARGET


async def admin_send_plan_target_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    await query.edit_message_text(
        "👤 لطفاً آیدی عددی (user_id) کاربر مورد نظر را ارسال کنید:\n\n"
        "⚠️ برای انصراف /cancel را بفرستید."
    )
    return ADMSP_USER_ID


async def admin_send_plan_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or '').strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not text.isdigit():
        await update.message.reply_text(
            "❌ آیدی باید فقط عدد باشد. دوباره ارسال کنید:\n\n⚠️ برای انصراف /cancel را بفرستید."
        )
        return ADMSP_USER_ID

    target_user_id = int(text)
    target_user = db.get_user(target_user_id)
    if not target_user:
        await update.message.reply_text(
            "❌ کاربری با این آیدی پیدا نشد.\n\n"
            "لطفاً آیدی دیگری ارسال کنید یا /cancel را بزنید."
        )
        return ADMSP_USER_ID

    context.user_data['admsp_targets'] = [target_user_id]
    context.user_data['admsp_target_label'] = f"کاربر {target_user_id}"

    await update.message.reply_text(
        "📦 لطفاً طرح مورد نظر را انتخاب کنید:",
        reply_markup=_scheme_keyboard()
    )
    return ADMSP_SCHEME


async def admin_send_plan_target_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    all_ids = db.get_all_user_ids() or []
    if not all_ids:
        await query.edit_message_text(
            "❌ هیچ کاربری در دیتابیس ثبت نشده است.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_to_main_menu")]
            ])
        )
        return ConversationHandler.END

    context.user_data['admsp_targets'] = all_ids
    context.user_data['admsp_target_label'] = f"همه کاربران ({len(all_ids)} نفر)"

    await query.edit_message_text(
        f"👥 گیرنده‌ها: {len(all_ids)} کاربر\n\n"
        "📦 لطفاً طرح مورد نظر را انتخاب کنید:",
        reply_markup=_scheme_keyboard()
    )
    return ADMSP_SCHEME


def _scheme_keyboard() -> InlineKeyboardMarkup:
    schemes = dp.get_all_schemes(enabled_only=True)
    keyboard = [
        [InlineKeyboardButton(scheme.get('name', scheme_id), callback_data=f"admsp_scheme_{scheme_id}")]
        for scheme_id, scheme in schemes.items()
    ]
    keyboard.append([InlineKeyboardButton("🔥 طرح شارژ دلخواه", callback_data="admsp_scheme_custom")])
    keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data="admsp_cancel")])
    return InlineKeyboardMarkup(keyboard)


async def admin_send_plan_scheme_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    scheme_id = query.data.replace("admsp_scheme_", "")

    if scheme_id == "custom":
        context.user_data['admsp_selected_plan'] = _custom_charge_plan()
        return await _show_replace_policy(update, context)

    plans = dp.get_all_plans(active_only=True)
    plans = {pid: p for pid, p in plans.items() if p.get('category', 'new') == scheme_id}

    if not plans:
        await query.edit_message_text(
            "❌ در حال حاضر هیچ پلنی در این طرح ثبت نشده است.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_send_plan_start")]
            ])
        )
        return ADMSP_SCHEME

    keyboard = []
    for plan_id, plan in plans.items():
        price_str = f"{plan['price']:,}"
        keyboard.append([InlineKeyboardButton(
            f"{plan['name']} | {price_str} تومان", callback_data=f"admsp_plan_{plan_id}"
        )])
    keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data="admsp_cancel")])

    await query.edit_message_text(
        "🎯 لطفاً پلن مورد نظر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMSP_PLAN


async def admin_send_plan_plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    plan_id = query.data.replace("admsp_plan_", "")
    plan = dp.get_plan(plan_id)
    if not plan or not plan.get('enabled', True):
        await query.answer("❌ این پلن دیگر در دسترس نیست.", show_alert=True)
        return ADMSP_PLAN

    selected_plan = {
        'name': plan['name'],
        'price': plan['price'],
        'days': plan['days'],
        'volume': plan.get('volume', 0),
        'daily_volume': plan.get('daily_volume'),
        'plan_type': dp.DYNAMIC_PLAN_TYPE,
        'plan_id': plan_id,
    }
    context.user_data['admsp_selected_plan'] = selected_plan
    return await _show_replace_policy(update, context)


# ============ سیاست جایگزینی طرح تکراری ============
async def _show_replace_policy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    از ادمین می‌پرسد در صورتی که کاربر (یا هر کدام از کاربران، در ارسال گروهی)
    از قبل دقیقاً همین طرح را داشته باشد، چه کاری انجام شود.
    این تصمیم پیش از شروع ارسال گرفته می‌شود چون در ارسال گروهی امکان پرسیدن
    برای تک‌تک کاربران وجود ندارد؛ سیاست انتخابی برای همه‌ی گیرنده‌ها یکسان اعمال می‌شود.
    """
    query = update.callback_query
    plan = context.user_data.get('admsp_selected_plan', {})

    keyboard = [
        [InlineKeyboardButton("🗑 حذف طرح قبلی (فقط دیتابیس)", callback_data="admsp_replace_db")],
        [InlineKeyboardButton("🗑🌐 حذف طرح قبلی (دیتابیس + پنل)", callback_data="admsp_replace_full")],
        [InlineKeyboardButton("➕ نگه‌داشتن قبلی و افزودن جدید", callback_data="admsp_replace_none")],
        [InlineKeyboardButton("❌ انصراف", callback_data="admsp_cancel")],
    ]
    await query.edit_message_text(
        f"📦 طرح انتخابی: {plan.get('name', '-')}\n\n"
        "❓ اگر گیرنده(ها) از قبل دقیقاً همین طرح را داشته باشند، چه کار شود؟\n\n"
        "🗑 «فقط دیتابیس» → رکورد اشتراک قبلی از دیتابیس ربات حذف می‌شود اما "
        "کلاینت روی پنل (3xUI) دست‌نخورده باقی می‌ماند.\n"
        "🗑🌐 «دیتابیس + پنل» → رکورد از دیتابیس حذف و کلاینت متناظر هم از روی "
        "پنل (از طریق API) حذف می‌شود.\n"
        "➕ «نگه‌داشتن قبلی» → طرح قدیمی دست‌نخورده می‌ماند و طرح جدید هم به‌صورت "
        "جداگانه اضافه/ارسال می‌شود.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMSP_REPLACE


async def admin_send_plan_replace_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    mapping = {
        "admsp_replace_db": REPLACE_DB_ONLY,
        "admsp_replace_full": REPLACE_DB_AND_API,
        "admsp_replace_none": REPLACE_NONE,
    }
    replace_mode = mapping.get(query.data, REPLACE_NONE)
    context.user_data['admsp_replace_mode'] = replace_mode

    return await _show_delay_selection(update, context)


async def _show_delay_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    targets = context.user_data.get('admsp_targets', [])

    # برای یک گیرنده‌ی تنها، فاصله‌ی زمانی بین کاربران معنا ندارد (اصلاً
    # حلقه‌ای در کار نیست که نیاز به تاخیر داشته باشد) — مستقیم برو تایید نهایی
    if len(targets) <= 1:
        context.user_data['admsp_delay'] = 0
        return await _show_confirmation(update, context)

    keyboard = [
        [InlineKeyboardButton(f"{d} ثانیه", callback_data=f"admsp_delay_{d}") for d in DELAY_PRESETS],
        [InlineKeyboardButton("❌ انصراف", callback_data="admsp_cancel")],
    ]
    await query.edit_message_text(
        f"👥 تعداد گیرنده: {len(targets)}\n\n"
        "⏱ برای جلوگیری از فشار به API پنل، بین ساخت کلاینت هر کاربر یک فاصله‌ی "
        "زمانی رعایت می‌شود.\n\n"
        "لطفاً فاصله‌ی زمانی بین هر کاربر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMSP_DELAY


async def admin_send_plan_delay_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    try:
        delay = int(query.data.replace("admsp_delay_", ""))
    except ValueError:
        delay = DEFAULT_DELAY_SECONDS
    context.user_data['admsp_delay'] = delay

    return await _show_confirmation(update, context)


_REPLACE_LABELS = {
    REPLACE_NONE: "➕ نگه‌داشتن طرح قبلی (در صورت وجود) و افزودن طرح جدید",
    REPLACE_DB_ONLY: "🗑 حذف طرح قبلی از دیتابیس (پنل دست‌نخورده می‌ماند)",
    REPLACE_DB_AND_API: "🗑🌐 حذف طرح قبلی از دیتابیس و پنل",
}


async def _show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    plan = context.user_data.get('admsp_selected_plan', {})
    targets = context.user_data.get('admsp_targets', [])
    delay = context.user_data.get('admsp_delay', 0)
    replace_mode = context.user_data.get('admsp_replace_mode', REPLACE_NONE)
    label = context.user_data.get('admsp_target_label', f"{len(targets)} کاربر")

    price_str = f"{plan.get('price', 0):,}"
    vol = plan.get('volume', 0)
    if plan.get('daily_volume'):
        volume_text = f"{plan['daily_volume']} گیگ روزانه"
    else:
        volume_text = "نامحدود" if not vol else f"{vol} گیگابایت"

    est_seconds = max(0, len(targets) - 1) * delay
    est_minutes = est_seconds / 60
    delay_line = (
        f"⏱ فاصله بین هر کاربر: {delay} ثانیه (~{est_minutes:.1f} دقیقه کل)\n\n"
        if len(targets) > 1 else ""
    )

    keyboard = [
        [InlineKeyboardButton("✅ تایید و ارسال", callback_data="admsp_confirm_yes")],
        [InlineKeyboardButton("❌ انصراف", callback_data="admsp_cancel")],
    ]
    await query.edit_message_text(
        "📋 خلاصه‌ی عملیات:\n\n"
        f"🎯 گیرنده: {label}\n"
        f"📦 طرح: {plan.get('name', '-')}\n"
        f"💰 ارزش طرح: {price_str} تومان (رایگان برای کاربر)\n"
        f"⏰ مدت: {plan.get('days', 0)} روز\n"
        f"📊 حجم: {volume_text}\n"
        f"{delay_line}"
        f"♻️ در صورت وجود طرح تکراری: {_REPLACE_LABELS.get(replace_mode, replace_mode)}\n\n"
        "آیا تایید می‌کنید؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMSP_CONFIRM


async def admin_send_plan_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        for key in ('admsp_targets', 'admsp_target_label', 'admsp_selected_plan',
                    'admsp_delay', 'admsp_replace_mode'):
            context.user_data.pop(key, None)
        await query.edit_message_text("❌ عملیات لغو شد.")
    return ConversationHandler.END


async def admin_send_plan_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ عملیات در پس‌زمینه شروع شد...")
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return ConversationHandler.END

    targets = list(context.user_data.get('admsp_targets', []))
    selected_plan = dict(context.user_data.get('admsp_selected_plan', {}))
    delay = context.user_data.get('admsp_delay', DEFAULT_DELAY_SECONDS)
    replace_mode = context.user_data.get('admsp_replace_mode', REPLACE_NONE)
    admin_id = query.from_user.id

    for key in ('admsp_targets', 'admsp_target_label', 'admsp_selected_plan',
                'admsp_delay', 'admsp_replace_mode'):
        context.user_data.pop(key, None)

    if not targets or not selected_plan:
        await query.edit_message_text("❌ اطلاعات ناقص است، دوباره تلاش کنید.")
        return ConversationHandler.END

    await query.edit_message_text(
        f"⏳ در حال ارسال طرح «{selected_plan.get('name', '')}» برای {len(targets)} کاربر...\n"
        f"این کار در پس‌زمینه انجام می‌شود و در پایان گزارش برایتان ارسال می‌شود."
    )

    # اجرا در پس‌زمینه تا ربات برای بقیه کاربران/ادمین قفل نشود
    asyncio.create_task(
        _run_bulk_send(context.bot, admin_id, targets, selected_plan, delay, replace_mode)
    )
    return ConversationHandler.END


async def _notify_user_gifted(bot, user_id: int, subscription_id, plan_name: str, days: int,
                               volume_text: str, replaced_count: int = 0):
    link = _get_single_sub_link(subscription_id) if _get_single_sub_link else None
    link_line = f"\nلینک اشتراک شما:\n<code>{link}</code>\n" if link else ""
    replaced_line = (
        "\nℹ️ اشتراک قبلی مشابه شما در همین راستا حذف شد.\n" if replaced_count else ""
    )
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎁 یک اشتراک توسط ادمین برای شما فعال شد!\n\n"
                f"📦 طرح: {plan_name}\n"
                f"⏰ مدت: {days} روز\n"
                f"📊 حجم: {volume_text}\n"
                f"{replaced_line}"
                f"{link_line}\n"
                f"اکنون می‌توانید از بخش «📒 اشتراک ها» آن را ببینید و کانفیگ را دریافت کنید."
            ),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.warning(f"Could not notify user {user_id} about gifted plan: {e}")


async def _run_bulk_send(bot, admin_id: int, targets: list, selected_plan: dict, delay: int,
                          replace_mode: str = REPLACE_NONE):
    """
    برای هر کاربر، دقیقاً همان مسیر خرید عادی (create_subscription_for_purchase)
    را صدا می‌زند تا کلاینت روی پنل ساخته و در دیتابیس ثبت شود — بدون کسر
    وجه از کیف پول کاربر. بین هر کاربر یک تاخیر کوتاه اعمال می‌شود تا به
    API پنل فشار ناگهانی وارد نشود.

    اگر replace_mode != REPLACE_NONE باشد، پیش از ساخت طرح جدید، اشتراک(های)
    فعال کاربر که دقیقاً همین plan_type + plan_name را دارند طبق سیاست انتخابی
    (فقط دیتابیس یا دیتابیس+پنل) حذف می‌شوند.
    """
    plan_name = selected_plan.get('name', 'پلن')
    days = selected_plan.get('days', 0)
    vol = selected_plan.get('volume', 0)
    if selected_plan.get('daily_volume'):
        volume_text = f"{selected_plan['daily_volume']} گیگ روزانه"
    else:
        volume_text = "نامحدود" if not vol else f"{vol} گیگابایت"

    success_count = 0
    replaced_total = 0
    failed = []  # list of (user_id, msg)

    for idx, user_id in enumerate(targets):
        replaced_count = 0
        if replace_mode != REPLACE_NONE:
            matches = _find_matching_subscriptions(user_id, selected_plan)
            if matches:
                replaced_count = _delete_matching_subscriptions(matches, replace_mode)
                replaced_total += replaced_count

        try:
            success, msg, sub_data = await _create_subscription_for_purchase(
                user_id=user_id,
                selected_plan=selected_plan,
                protocol='v2ray'
            )
        except Exception as e:
            success, msg, sub_data = False, str(e), None

        if success and sub_data:
            subscription_id = sub_data.get('subscription_id')
            try:
                db.add_transaction(
                    user_id, 0, "admin_gift",
                    f"هدیه ادمین ({admin_id}) - {plan_name}"
                )
            except Exception as e:
                logger.warning(f"Could not log admin_gift transaction for {user_id}: {e}")

            await _notify_user_gifted(
                bot, user_id, subscription_id, plan_name, days, volume_text, replaced_count
            )
            success_count += 1
        else:
            admin_detail = (sub_data or {}).get('admin_error', msg)
            failed.append((user_id, msg))
            try:
                await log_panel_error(
                    bot, user_id, "Admin gift plan (bulk send)", admin_detail,
                    plan_name=plan_name
                )
            except Exception:
                pass

        # فاصله‌ی زمانی بین هر کاربر، به جز بعد از آخرین نفر
        if idx < len(targets) - 1 and delay > 0:
            await asyncio.sleep(delay)

    # گزارش نهایی به ادمین
    report_lines = [
        f"✅ گزارش ارسال طرح «{plan_name}»",
        f"👥 کل گیرنده‌ها: {len(targets)}",
        f"✅ موفق: {success_count}",
        f"❌ ناموفق: {len(failed)}",
    ]
    if replace_mode != REPLACE_NONE:
        report_lines.append(f"♻️ طرح‌های تکراری حذف‌شده: {replaced_total}")
    if failed:
        report_lines.append("\nکاربران ناموفق:")
        for uid, err in failed[:20]:
            report_lines.append(f"- {uid}: {err}")
        if len(failed) > 20:
            report_lines.append(f"... و {len(failed) - 20} مورد دیگر")

    try:
        await bot.send_message(chat_id=admin_id, text="\n".join(report_lines))
    except Exception as e:
        logger.error(f"Could not send bulk-send report to admin {admin_id}: {e}")
