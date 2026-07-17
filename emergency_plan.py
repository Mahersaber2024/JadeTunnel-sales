"""
============================================================
ماژول «طرح اضطراری» (Emergency Plan)
============================================================
این ماژول کاملاً مستقل است و خودش جدول‌های موردنیاز را در همان
دیتابیس اصلی (همان کانکشن psycopg2 که در database.py ساخته شده)
می‌سازد. کافی است در main.py متد set_db(db) را صدا بزنید.

قابلیت‌ها:
- دکمه «🚨 طرح اضطراری» در منوی اصلی
- اگر کاربر عضو فعال نیست: می‌تواند درخواست عضویت بفرستد
- درخواست به ادمین‌ها (از طریق تاپیک ADMIN_ACTION در گروه لاگ، یا
  در صورت نبود گروه لاگ، مستقیم به تک‌تک ادمین‌ها) با دو دکمه
  «✅ تایید» / «❌ رد» ارسال می‌شود
- هنگام تایید، ادمین باید تعداد روز عضویت را مشخص کند (دکمه‌های
  آماده 7/15/30/60/90 روز یا دکمه «روز دلخواه» برای تایپ عدد دلخواه)
- به کاربر بعد از تایید/رد پیام اطلاع‌رسانی ارسال می‌شود
- اگر کاربر عضو فعال باشد: دو دکمه «📡 دریافت پروکسی» و
  «⚙️ دریافت کانفیگ» نمایش داده می‌شود (متن این دو از طریق پنل
  ادمین قابل ویرایش است)
- ادمین می‌تواند از پنل مدیریت، لیست اعضای فعال را ببیند و هرکدام
  را حذف (لغو عضویت) کند
============================================================
"""

import logging
import uuid
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes, ConversationHandler

logger = logging.getLogger(__name__)

# ============ Conversation States (باید با state‌های سایر ماژول‌ها تداخل نداشته باشد) ============
EMERGENCY_PROXY_EDIT_INPUT = 501
EMERGENCY_CONFIG_EDIT_INPUT = 502

# ============ Presets ============
DURATION_PRESETS = [7, 15, 30, 60, 90]

# ============ Global refs ============
db = None
ADMIN_IDS = []
get_main_menu_func = None

# request_id -> dict
PENDING_REQUESTS = {}
# admin_id -> request_id  (منتظر دریافت عدد روز دلخواه از این ادمین هستیم)
AWAITING_CUSTOM_DAYS = {}


# ============ Setup ============
def set_db(database):
    global db
    db = database
    _ensure_tables()


def set_admin_ids(admin_ids):
    global ADMIN_IDS
    ADMIN_IDS = admin_ids or []


def set_get_main_menu(func):
    global get_main_menu_func
    get_main_menu_func = func


def _is_admin(user_id: int) -> bool:
    return (not ADMIN_IDS) or (user_id in ADMIN_IDS)


def get_main_menu():
    if get_main_menu_func:
        return get_main_menu_func()
    return None


def _ensure_tables():
    """ساخت جدول‌های موردنیاز در صورت نبودن"""
    cursor = None
    try:
        cursor = db.get_cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emergency_members (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_date TIMESTAMP NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                approved_by BIGINT,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emergency_settings (
                key VARCHAR(50) PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emergency_user_id ON emergency_members(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emergency_status ON emergency_members(status)")
        db.conn.commit()
        logger.info("✅ جدول‌های طرح اضطراری بررسی/ساخته شد")
    except Exception as e:
        logger.error(f"Error creating emergency plan tables: {e}")
        if db.conn:
            db.conn.rollback()
    finally:
        if cursor:
            cursor.close()


# ============ Settings (متن پروکسی/کانفیگ) ============
def _get_setting(key, default=""):
    cursor = None
    try:
        cursor = db.get_cursor()
        cursor.execute("SELECT value FROM emergency_settings WHERE key = %s", (key,))
        row = cursor.fetchone()
        return row['value'] if row and row['value'] is not None else default
    except Exception as e:
        logger.error(f"Error reading emergency setting {key}: {e}")
        return default
    finally:
        if cursor:
            cursor.close()


def _set_setting(key, value):
    cursor = None
    try:
        cursor = db.get_cursor()
        cursor.execute("""
            INSERT INTO emergency_settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (key, value))
        db.conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving emergency setting {key}: {e}")
        if db.conn:
            db.conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()


def get_emergency_proxy_text():
    return _get_setting("proxy_text", "⚠️ هنوز اطلاعات پروکسی توسط ادمین ثبت نشده است.")


def set_emergency_proxy_text(text):
    return _set_setting("proxy_text", text)


def get_emergency_config_text():
    return _get_setting("config_text", "⚠️ هنوز اطلاعات کانفیگ توسط ادمین ثبت نشده است.")


def set_emergency_config_text(text):
    return _set_setting("config_text", text)


# ============ DB helpers - عضویت ============
def get_active_membership(user_id: int):
    cursor = None
    try:
        cursor = db.get_cursor()
        cursor.execute("""
            SELECT * FROM emergency_members
            WHERE user_id = %s AND status = 'active' AND end_date > NOW()
            ORDER BY id DESC LIMIT 1
        """, (user_id,))
        return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting emergency membership: {e}")
        return None
    finally:
        if cursor:
            cursor.close()


def add_membership(user_id: int, days: int, approved_by: int = None):
    cursor = None
    try:
        cursor = db.get_cursor()
        end_date = datetime.now() + timedelta(days=days)
        cursor.execute(
            "UPDATE emergency_members SET status = 'expired' WHERE user_id = %s AND status = 'active'",
            (user_id,)
        )
        cursor.execute("""
            INSERT INTO emergency_members (user_id, end_date, status, approved_by)
            VALUES (%s, %s, 'active', %s) RETURNING id
        """, (user_id, end_date, approved_by))
        new_id = cursor.fetchone()['id']
        db.conn.commit()
        return new_id
    except Exception as e:
        logger.error(f"Error adding emergency membership: {e}")
        if db.conn:
            db.conn.rollback()
        return None
    finally:
        if cursor:
            cursor.close()


def remove_membership(user_id: int) -> bool:
    cursor = None
    try:
        cursor = db.get_cursor()
        cursor.execute(
            "UPDATE emergency_members SET status = 'removed' WHERE user_id = %s AND status = 'active'",
            (user_id,)
        )
        removed = cursor.rowcount > 0
        db.conn.commit()
        return removed
    except Exception as e:
        logger.error(f"Error removing emergency membership: {e}")
        if db.conn:
            db.conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()


def get_all_active_members():
    cursor = None
    try:
        cursor = db.get_cursor()
        cursor.execute("""
            SELECT em.*, u.username, u.first_name FROM emergency_members em
            LEFT JOIN users u ON u.user_id = em.user_id
            WHERE em.status = 'active' AND em.end_date > NOW()
            ORDER BY em.end_date ASC
        """)
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error listing emergency members: {e}")
        return []
    finally:
        if cursor:
            cursor.close()


# ============================================================
# ============ User-facing handlers ============
# ============================================================
async def emergency_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورودی از دکمه منوی اصلی «🚨 طرح اضطراری»"""
    user_id = update.effective_user.id
    membership = get_active_membership(user_id)

    if membership:
        end_date_str = str(membership['end_date'])[:16]
        keyboard = [
            [InlineKeyboardButton("📡 دریافت پروکسی", callback_data="emergency_get_proxy")],
            [InlineKeyboardButton("⚙️ دریافت کانفیگ", callback_data="emergency_get_config")],
        ]
        await update.message.reply_text(
            f"🚨 طرح اضطراری\n\n"
            f"✅ شما عضو فعال طرح اضطراری هستید.\n"
            f"⏰ تاریخ انقضا: {end_date_str}\n\n"
            f"لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        keyboard = [
            [InlineKeyboardButton("📨 ارسال درخواست عضویت", callback_data="emergency_request")]
        ]
        await update.message.reply_text(
            "🚨 طرح اضطراری\n\n"
            "شما در حال حاضر عضو طرح اضطراری نیستید.\n"
            "برای درخواست عضویت روی دکمه زیر بزنید؛ پس از بررسی و تایید ادمین "
            "به شما اطلاع داده خواهد شد.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def emergency_get_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    membership = get_active_membership(query.from_user.id)
    if not membership:
        await query.answer("❌ عضویت شما یافت نشد یا منقضی شده است.", show_alert=True)
        return
    await query.message.reply_text(
        f"📡 اطلاعات پروکسی طرح اضطراری:\n\n{get_emergency_proxy_text()}"
    )


async def emergency_get_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    membership = get_active_membership(query.from_user.id)
    if not membership:
        await query.answer("❌ عضویت شما یافت نشد یا منقضی شده است.", show_alert=True)
        return
    await query.message.reply_text(
        f"⚙️ اطلاعات کانفیگ طرح اضطراری:\n\n{get_emergency_config_text()}"
    )


async def emergency_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """کاربر درخواست عضویت می‌فرستد"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id

    if get_active_membership(user_id):
        await query.answer("✅ شما همین الان هم عضو فعال طرح اضطراری هستید.", show_alert=True)
        return

    for req in PENDING_REQUESTS.values():
        if req['user_id'] == user_id and req['status'] == 'pending':
            await query.answer("⏳ یک درخواست قبلی شما هنوز در حال بررسی است.", show_alert=True)
            return

    request_id = uuid.uuid4().hex[:8]
    PENDING_REQUESTS[request_id] = {
        'user_id': user_id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'status': 'pending',
        'requested_at': datetime.now(),
    }

    await query.edit_message_text(
        "📨 درخواست شما ثبت شد.\n\n"
        "پس از بررسی و تایید ادمین، به شما اطلاع داده خواهد شد."
    )

    await _send_request_to_admins(context.bot, request_id, PENDING_REQUESTS[request_id])


async def _send_request_to_admins(bot, request_id, req_data):
    import html as html_lib

    name = req_data.get('first_name') or 'کاربر'
    username = f"@{req_data['username']}" if req_data.get('username') else 'ندارد'

    text = (
        f"🚨 <b>درخواست عضویت طرح اضطراری</b>\n\n"
        f"📛 نام: {html_lib.escape(name)}\n"
        f"🔰 یوزرنیم: {username}\n"
        f"🆔 آیدی: <code>{req_data['user_id']}</code>\n\n"
        f"🆔 شناسه درخواست: <code>{request_id}</code>"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تایید", callback_data=f"emg_approve_{request_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"emg_reject_{request_id}")
    ]])

    sent_to_group = False
    try:
        from logger_bot import LOG_GROUP_ID, get_thread_id, Topics
        if LOG_GROUP_ID:
            thread_id = get_thread_id(Topics.ADMIN_ACTION)
            await bot.send_message(
                chat_id=LOG_GROUP_ID,
                text=text,
                parse_mode='HTML',
                message_thread_id=thread_id,
                reply_markup=keyboard
            )
            sent_to_group = True
    except Exception as e:
        logger.error(f"Error sending emergency request to log group: {e}")

    if not sent_to_group:
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(chat_id=admin_id, text=text, parse_mode='HTML', reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Error notifying admin {admin_id} of emergency request: {e}")


# ============================================================
# ============ Admin: تایید / رد / تعیین مدت ============
# ============================================================
async def emergency_admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ادمین دکمه «✅ تایید» را زده — نمایش گزینه‌های تعداد روز"""
    query = update.callback_query
    admin = query.from_user

    request_id = query.data.replace("emg_approve_", "")
    req = PENDING_REQUESTS.get(request_id)

    if not req or req['status'] != 'pending':
        await query.answer("❌ این درخواست دیگر معتبر نیست (شاید قبلاً بررسی شده).", show_alert=True)
        return

    if not _is_admin(admin.id):
        await query.answer("⛔️ شما اجازه تایید این درخواست را ندارید.", show_alert=True)
        return

    await query.answer()

    keyboard, row = [], []
    for d in DURATION_PRESETS:
        row.append(InlineKeyboardButton(f"{d} روز", callback_data=f"emg_days_{d}_{request_id}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✏️ روز دلخواه", callback_data=f"emg_customdays_{request_id}")])
    keyboard.append([InlineKeyboardButton("🔙 انصراف", callback_data=f"emg_cancelapprove_{request_id}")])

    try:
        base_text = query.message.text_html
    except Exception:
        base_text = query.message.text or ""

    await query.edit_message_text(
        base_text + "\n\n⏳ <b>لطفاً تعداد روز عضویت را انتخاب کنید:</b>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def emergency_admin_cancel_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت از صفحه انتخاب روز به دکمه‌های تایید/رد اصلی"""
    query = update.callback_query
    await query.answer()
    request_id = query.data.replace("emg_cancelapprove_", "")
    req = PENDING_REQUESTS.get(request_id)
    if not req:
        await query.edit_message_text("❌ این درخواست دیگر معتبر نیست.")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تایید", callback_data=f"emg_approve_{request_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"emg_reject_{request_id}")
    ]])
    try:
        base_text = query.message.text_html.split("\n\n⏳")[0]
    except Exception:
        base_text = query.message.text or ""

    await query.edit_message_text(base_text, parse_mode='HTML', reply_markup=keyboard)


async def emergency_admin_set_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ادمین یکی از گزینه‌های آماده روز را انتخاب کرد"""
    query = update.callback_query
    admin = query.from_user

    data = query.data.replace("emg_days_", "")
    days_str, request_id = data.split("_", 1)
    days = int(days_str)

    await _finalize_approval(query, context, request_id, days, admin)


async def emergency_admin_custom_days_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ادمین می‌خواهد عدد دلخواه تایپ کند"""
    query = update.callback_query
    admin = query.from_user
    request_id = query.data.replace("emg_customdays_", "")

    req = PENDING_REQUESTS.get(request_id)
    if not req or req['status'] != 'pending':
        await query.answer("❌ این درخواست دیگر معتبر نیست.", show_alert=True)
        return

    if not _is_admin(admin.id):
        await query.answer("⛔️ دسترسی ندارید.", show_alert=True)
        return

    await query.answer()
    AWAITING_CUSTOM_DAYS[admin.id] = request_id

    await query.message.reply_text(
        f"✏️ لطفاً تعداد روز عضویت را به‌صورت عدد صحیح ارسال کنید:\n"
        f"(برای درخواست <code>{request_id}</code>)\n\n"
        f"⚠️ برای انصراف /cancel را ارسال کنید.",
        parse_mode='HTML'
    )


async def emergency_admin_custom_days_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    این هندلر باید به‌صورت سراسری (روی همه پیام‌های متنی) با group=-1 ثبت شود.
    فقط وقتی کاری انجام می‌دهد که فرستنده، ادمینی باشد که منتظر ورودی «روز دلخواه» است؛
    در غیر این صورت بی‌سروصدا خارج می‌شود و مزاحم بقیه‌ی هندلرها نمی‌شود.
    """
    if not update.message or not update.message.text:
        return

    admin_id = update.effective_user.id
    if admin_id not in AWAITING_CUSTOM_DAYS:
        return

    text = update.message.text.strip()
    request_id = AWAITING_CUSTOM_DAYS[admin_id]

    if text == "/cancel":
        AWAITING_CUSTOM_DAYS.pop(admin_id, None)
        await update.message.reply_text("❌ عملیات لغو شد.")
        return

    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح مثبت ارسال کنید (یا /cancel برای انصراف):")
        return

    days = int(text)
    AWAITING_CUSTOM_DAYS.pop(admin_id, None)

    req = PENDING_REQUESTS.get(request_id)
    if not req or req['status'] != 'pending':
        await update.message.reply_text("❌ این درخواست دیگر معتبر نیست (شاید قبلاً بررسی شده).")
        return

    await _finalize_approval_from_message(update, context, request_id, days, update.effective_user)


async def _finalize_approval_from_message(update, context, request_id, days, admin):
    """نسخه‌ی مخصوص وقتی تایید از طریق پیام متنی (روز دلخواه) انجام می‌شود"""
    req = PENDING_REQUESTS.get(request_id)
    if not req or req['status'] != 'pending':
        await update.message.reply_text("❌ این درخواست دیگر معتبر نیست.")
        return

    if not _is_admin(admin.id):
        await update.message.reply_text("⛔️ شما اجازه تایید این درخواست را ندارید.")
        return

    user_id = req['user_id']
    add_membership(user_id, days, approved_by=admin.id)
    req['status'] = 'approved'

    end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M')

    await update.message.reply_text(
        f"✅ عضویت طرح اضطراری برای کاربر <code>{user_id}</code> با {days} روز مهلت ثبت شد.\n"
        f"⏰ تاریخ انقضا: {end_date}",
        parse_mode='HTML'
    )

    await _notify_user_approved(context.bot, user_id, end_date)
    PENDING_REQUESTS.pop(request_id, None)


async def _finalize_approval(query, context, request_id, days, admin):
    """نسخه‌ی مخصوص وقتی تایید از طریق یکی از دکمه‌های آماده روز انجام می‌شود"""
    req = PENDING_REQUESTS.get(request_id)
    if not req or req['status'] != 'pending':
        await query.answer("❌ این درخواست دیگر معتبر نیست.", show_alert=True)
        return

    if not _is_admin(admin.id):
        await query.answer("⛔️ شما اجازه تایید این درخواست را ندارید.", show_alert=True)
        return

    user_id = req['user_id']
    add_membership(user_id, days, approved_by=admin.id)
    req['status'] = 'approved'

    await query.answer(f"✅ عضویت {days} روزه ثبت شد.")
    end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M')

    try:
        base_text = query.message.text_html.split("\n\n⏳")[0]
        await query.edit_message_text(
            base_text +
            f"\n\n✅ <b>تایید شد توسط:</b> {admin.first_name or admin.id}\n"
            f"⏰ مدت عضویت: {days} روز (تا {end_date})",
            parse_mode='HTML'
        )
    except Exception:
        pass

    await _notify_user_approved(context.bot, user_id, end_date)
    PENDING_REQUESTS.pop(request_id, None)


async def _notify_user_approved(bot, user_id, end_date_str):
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 درخواست شما برای عضویت در طرح اضطراری تایید شد!\n\n"
                f"✅ شما اکنون عضو طرح اضطراری هستید.\n"
                f"⏰ تاریخ انقضا: {end_date_str}\n\n"
                f"برای دریافت پروکسی و کانفیگ، از منوی «🚨 طرح اضطراری» استفاده کنید."
            )
        )
    except Exception as e:
        logger.error(f"Could not notify user {user_id} of emergency approval: {e}")


async def emergency_admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = query.from_user

    request_id = query.data.replace("emg_reject_", "")
    req = PENDING_REQUESTS.get(request_id)

    if not req or req['status'] != 'pending':
        await query.answer("❌ این درخواست دیگر معتبر نیست.", show_alert=True)
        return

    if not _is_admin(admin.id):
        await query.answer("⛔️ شما اجازه رد این درخواست را ندارید.", show_alert=True)
        return

    await query.answer("رد شد")
    req['status'] = 'rejected'
    user_id = req['user_id']

    try:
        base_text = query.message.text_html
        await query.edit_message_text(
            base_text + f"\n\n❌ <b>رد شد توسط:</b> {admin.first_name or admin.id}",
            parse_mode='HTML'
        )
    except Exception:
        pass

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ متاسفانه درخواست عضویت شما در طرح اضطراری تایید نشد.\nدر صورت نیاز با پشتیبانی تماس بگیرید."
        )
    except Exception as e:
        logger.error(f"Could not notify user {user_id} of emergency rejection: {e}")

    PENDING_REQUESTS.pop(request_id, None)


# ============================================================
# ============ Admin: مدیریت اعضا و متن پروکسی/کانفیگ ============
# ============================================================
async def emergency_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ورودی از دکمه «🚨 مدیریت طرح اضطراری» در پنل ادمین"""
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ شما دسترسی ادمین ندارید.")
        return

    keyboard = [
        [InlineKeyboardButton("📋 لیست اعضای فعال", callback_data="emg_list_members")],
        [InlineKeyboardButton("✏️ ویرایش متن پروکسی", callback_data="emg_edit_proxy")],
        [InlineKeyboardButton("✏️ ویرایش متن کانفیگ", callback_data="emg_edit_config")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_to_main_menu")],
    ]
    await query.edit_message_text(
        "🚨 مدیریت طرح اضطراری\n\nلطفاً یک گزینه را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def emergency_list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return

    members = get_all_active_members()
    if not members:
        await query.edit_message_text(
            "📋 هیچ عضو فعالی در طرح اضطراری وجود ندارد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="emg_admin_menu")]])
        )
        return

    keyboard = []
    for m in members:
        name = m.get('first_name') or m.get('username') or str(m['user_id'])
        end_date = str(m['end_date'])[:16]
        keyboard.append([
            InlineKeyboardButton(f"🗑 {name} - تا {end_date}", callback_data=f"emg_remove_{m['user_id']}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="emg_admin_menu")])

    await query.edit_message_text(
        "📋 اعضای فعال طرح اضطراری:\n\n(برای حذف عضویت روی نام کاربر بزنید)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def emergency_remove_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = query.from_user
    if not _is_admin(admin.id):
        await query.answer("⛔️ دسترسی ندارید.", show_alert=True)
        return

    user_id = int(query.data.replace("emg_remove_", ""))
    success = remove_membership(user_id)

    if success:
        await query.answer("✅ عضویت حذف شد.")
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="⚠️ عضویت شما در طرح اضطراری توسط ادمین حذف شد."
            )
        except Exception as e:
            logger.error(f"Could not notify user {user_id} of emergency removal: {e}")
    else:
        await query.answer("❌ خطا در حذف عضویت (شاید قبلاً حذف شده).", show_alert=True)

    await emergency_list_members(update, context)


async def emergency_edit_proxy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        f"✏️ ویرایش متن پروکسی طرح اضطراری\n\n"
        f"متن فعلی:\n{get_emergency_proxy_text()}\n\n"
        f"لطفاً متن جدید را ارسال کنید:\n\n⚠️ /cancel برای انصراف",
        parse_mode=None
    )
    return EMERGENCY_PROXY_EDIT_INPUT


async def emergency_edit_proxy_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_menu())
        return ConversationHandler.END
    set_emergency_proxy_text(text)
    await update.message.reply_text("✅ متن پروکسی با موفقیت بروزرسانی شد.", reply_markup=get_main_menu())
    return ConversationHandler.END


async def emergency_edit_config_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(query.from_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        f"✏️ ویرایش متن کانفیگ طرح اضطراری\n\n"
        f"متن فعلی:\n{get_emergency_config_text()}\n\n"
        f"لطفاً متن جدید را ارسال کنید:\n\n⚠️ /cancel برای انصراف",
        parse_mode=None
    )
    return EMERGENCY_CONFIG_EDIT_INPUT


async def emergency_edit_config_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "/cancel":
        await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_menu())
        return ConversationHandler.END
    set_emergency_config_text(text)
    await update.message.reply_text("✅ متن کانفیگ با موفقیت بروزرسانی شد.", reply_markup=get_main_menu())
    return ConversationHandler.END
