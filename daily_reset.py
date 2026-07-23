import logging
from client_manager import get_panel_client

logger = logging.getLogger(__name__)

db = None


def set_db(database):
    global db
    db = database


async def run_daily_traffic_reset(context):
    """
    Job که هر شب توسط JobQueue خودِ ربات اجرا می‌شود (بدون نیاز به cron جدا).
    ترافیک مصرفیِ پلن‌های سقف‌دار روزانه (متعادل / منصفانه / حرفه‌ای) را
    روی هر پنل ریست می‌کند — سقف کلی (totalGB) دست‌نخورده می‌ماند.
    """
    if db is None:
        logger.error("❌ daily_reset: دیتابیس ست نشده (daily_reset.set_db صدا زده نشده)")
        return

    logger.info("🔄 شروع ریست روزانه ترافیک (job داخلی ربات)...")

    emails_by_panel = db.get_daily_cap_subscriptions()
    if not emails_by_panel:
        logger.info("ℹ️ اشتراک فعالی برای ریست روزانه پیدا نشد.")
        return

    total_success = 0
    total_fail = 0
    fail_details = []

    for panel_id, emails in emails_by_panel.items():
        try:
            client = get_panel_client(panel_id)
        except Exception as e:
            logger.error(f"❌ خطا در ساخت کلاینت برای پنل {panel_id}: {e}")
            total_fail += len(emails)
            fail_details.append(f"پنل {panel_id}: خطا در اتصال ({e})")
            continue

        panel_fail = 0
        for email in emails:
            success, msg = client.reset_client_traffic(email)
            if success:
                total_success += 1
            else:
                total_fail += 1
                panel_fail += 1
                logger.error(f"❌ ریست ناموفق برای {email} (پنل {panel_id}): {msg}")

        if panel_fail:
            fail_details.append(f"پنل {panel_id}: {panel_fail} کاربر ناموفق")

    logger.info(f"📊 ریست روزانه پایان یافت: {total_success} موفق / {total_fail} ناموفق.")

    # ============ اطلاع‌رسانی به گروه لاگ (اختیاری، اگر LOG_GROUP_ID ست شده باشد) ============
    try:
        from logger_bot import LOG_GROUP_ID
        if LOG_GROUP_ID:
            text = f"🔄 ریست روزانه ترافیک انجام شد.\n✅ موفق: {total_success}\n❌ ناموفق: {total_fail}"
            if fail_details:
                text += "\n\n" + "\n".join(fail_details)
            await context.bot.send_message(chat_id=LOG_GROUP_ID, text=text)
    except Exception as e:
        logger.error(f"خطا در ارسال گزارش ریست روزانه به گروه لاگ: {e}")

async def run_emergency_plan_cleanup(context):
    """
    حذف خودکار اشتراک‌های طرح اضطراری منقضی‌شده — هم از دیتابیس هم از پنل 3xUI.
    """
    if db is None:
        logger.error("❌ emergency_cleanup: دیتابیس ست نشده")
        return

    expired = db.get_expired_subscriptions_by_type('emergency')
    if not expired:
        return

    logger.info(f"🆘 {len(expired)} اشتراک اضطراری منقضی شده — در حال حذف...")
    removed = 0
    fail_details = []

    for sub in expired:
        email = sub.get('email')
        panel_id = sub.get('panel_id')
        user_id = sub.get('user_id')
        sub_id = sub.get('id')

        if email and panel_id:
            try:
                client = get_panel_client(panel_id)
                success, msg = client.delete_client(email)
                if not success:
                    logger.error(f"❌ حذف کلاینت اضطراری {email} از پنل {panel_id} ناموفق: {msg}")
                    fail_details.append(f"{email} (پنل {panel_id}): {msg}")
            except Exception as e:
                logger.error(f"❌ خطا در حذف کلاینت اضطراری {email} از پنل {panel_id}: {e}")
                fail_details.append(f"{email} (پنل {panel_id}): {e}")

        if db.delete_subscription(sub_id):
            removed += 1
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "⏰ اشتراک طرح اضطراری شما منقضی و حذف شد.\n"
                        "در صورت نیاز مجدد، از دکمه 🆘 طرح اضطراری استفاده کنید."
                    )
                )
            except Exception as e:
                logger.error(f"Could not notify user {user_id} about emergency expiry: {e}")

    logger.info(f"🆘 پاکسازی اشتراک‌های اضطراری پایان یافت: {removed}/{len(expired)} حذف شد.")

    try:
        from logger_bot import LOG_GROUP_ID
        if LOG_GROUP_ID and (removed or fail_details):
            text = f"🆘 پاکسازی خودکار طرح اضطراری انجام شد.\n✅ حذف شده: {removed}/{len(expired)}"
            if fail_details:
                text += "\n\n⚠️ خطاهای حذف از پنل:\n" + "\n".join(fail_details)
            await context.bot.send_message(chat_id=LOG_GROUP_ID, text=text)
    except Exception as e:
        logger.error(f"خطا در ارسال گزارش پاکسازی اضطراری به گروه لاگ: {e}")
