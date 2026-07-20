#!/usr/bin/env python3
# lifeline.py - "چراغ جاده تونل" / ماژول شمارنده‌ی معکوس عمر ربات
#
# منطق:
#  - یک شمارنده‌ی «روز باقیمانده» در دیتابیس نگه‌داری می‌شود (پیش‌فرض 30 روز، سقف max_days)
#  - با هر خرید موفق اشتراک، یک روز به عمر اضافه می‌شود (تا سقف max_days)
#  - با خروج هر کاربر از کانال اسپانسر، یک روز از عمر کم می‌شود
#  - یک پست (عکس + کپشن) در کانال «ادیت» می‌شود، نه اینکه هر بار پیام جدید بفرستد
#  - اگر ادیت پیام قبلی شکست بخورد (مثلاً پیام حذف شده)، پیام جدید ساخته و آیدی‌اش ذخیره می‌شود
#
# نکته: این ماژول فقط یک نمایش انگیزشی/گرافیکی است و به‌خودی‌خود چیزی را قطع نمی‌کند.
# اگر خواستید به رسیدن به صفر، رفتار واقعی (مثلاً غیرفعال کردن خرید) هم وصل شود، باید جداگانه اضافه شود.

import io
import math
import logging
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from telegram import InputMediaPhoto, Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

db = None
LIFELINE_CHANNEL_ID = None

def set_db(database):
    global db
    db = database

def set_channel(channel_id: str):
    global LIFELINE_CHANNEL_ID
    LIFELINE_CHANNEL_ID = channel_id


FONT_PATH_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _load_font(size):
    try:
        return ImageFont.truetype(FONT_PATH_BOLD, size)
    except Exception:
        return ImageFont.load_default()


def generate_lifeline_image(days_remaining: int, max_days: int, pulse_phase: float = 0.0) -> io.BytesIO:
    """گیج دایره‌ای با افکت نور نفس‌کشیدن (breathing glow) متناسب با روز باقیمانده"""
    W, H = 1000, 1000
    bg_top, bg_bottom = (10, 14, 25), (20, 28, 45)
    img = Image.new("RGB", (W, H), bg_top)
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y / H
        r = int(bg_top[0] + (bg_bottom[0] - bg_top[0]) * t)
        g = int(bg_top[1] + (bg_bottom[1] - bg_top[1]) * t)
        b = int(bg_top[2] + (bg_bottom[2] - bg_top[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    ratio = max(0.0, min(1.0, days_remaining / max(1, max_days)))
    if ratio > 0.5:
        color = (60, 220, 140)   # سبز = سالم
    elif ratio > 0.2:
        color = (250, 180, 60)   # کهربایی = هشدار
    else:
        color = (235, 70, 70)    # قرمز = بحرانی

    cx, cy, r_outer = W // 2, H // 2 - 40, 340
    pulse = (math.sin(pulse_phase) + 1) / 2  # 0..1 برای افکت نفس‌کشیدن

    base_rgba = img.convert("RGBA")
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(6, 0, -1):
        glow_r = r_outer + i * 14 + int(pulse * 18)
        alpha = max(0, 40 - i * 6)
        gd.ellipse([cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r],
                   outline=color + (alpha,), width=6)
    img = Image.alpha_composite(base_rgba, glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    track_w = 34
    draw.arc([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], 0, 360,
              fill=(45, 55, 75), width=track_w)
    start_angle = -90
    end_angle = start_angle + 360 * ratio
    draw.arc([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], start_angle, end_angle,
              fill=color, width=track_w)

    font_big = _load_font(210)
    font_small = _load_font(46)

    num_text = str(max(0, days_remaining))
    bbox = draw.textbbox((0, 0), num_text, font=font_big)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw / 2, cy - th / 2 - 30), num_text, font=font_big, fill=(245, 245, 250))

    label = "DAYS LEFT"
    bbox2 = draw.textbbox((0, 0), label, font=font_small)
    lw = bbox2[2] - bbox2[0]
    draw.text((cx - lw / 2, cy + 150), label, font=font_small, fill=(170, 180, 200))

    buf = io.BytesIO()
    buf.name = "lifeline.png"
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def build_caption(days_remaining: int, max_days: int) -> str:
    if days_remaining <= 0:
        return (
            "🕯 <b>چراغ جاده تونل خاموش شد...</b>\n\n"
            "بدون حمایت شما، جاده تونل نمی‌تونه ادامه بده.\n"
            "با دعوت یک دوست، دوباره روشنش کن 🌿"
        )

    urgency = ""
    if days_remaining <= 5:
        urgency = "🔴 <b>وضعیت بحرانی!</b>\n"
    elif days_remaining <= 15:
        urgency = "🟡 <b>نیاز به حمایت داری!</b>\n"

    return (
        f"{urgency}"
        f"🕯 <b>چراغ جاده تونل</b>\n\n"
        f"⏳ <b>{days_remaining} روز</b> تا خاموشی چراغ باقی مونده...\n\n"
        f"هر عضو جدیدی که با لینک دعوت شما بیاد و اشتراک بگیره، یک روز به عمر جاده تونل اضافه می‌کنه 🌱\n"
        f"هر کاربری که مارو ترک کنه، از این عمر کم می‌شه 💔\n\n"
        f"با دعوت از دوستات، چراغ جاده تونل رو روشن نگه دار!\n"
        f"از بخش «👥 دعوت از دوستان» لینک اختصاصی خودت رو بردار 🚀"
    )


async def post_or_update_lifeline(bot: Bot):
    """پست گیج را در کانال ادیت می‌کند؛ اگر پیامی وجود نداشت یا ادیت شکست خورد، پیام جدید می‌فرستد"""
    if not db or not LIFELINE_CHANNEL_ID:
        logger.warning("Lifeline: db یا channel تنظیم نشده")
        return

    row = db.get_lifeline()
    if not row:
        return

    days_remaining = row['days_remaining']
    max_days = row['max_days']
    message_id = row.get('message_id')

    pulse_phase = (datetime.now().timestamp() % 60) / 60 * 2 * math.pi
    photo = generate_lifeline_image(days_remaining, max_days, pulse_phase)
    caption = build_caption(days_remaining, max_days)

    if message_id:
        try:
            await bot.edit_message_media(
                chat_id=LIFELINE_CHANNEL_ID,
                message_id=message_id,
                media=InputMediaPhoto(media=photo, caption=caption, parse_mode='HTML')
            )
            return
        except TelegramError as e:
            logger.warning(f"Lifeline: ادیت پیام قبلی شکست خورد ({e})؛ پیام جدید ارسال می‌شود...")

    try:
        if message_id:
            try:
                await bot.delete_message(chat_id=LIFELINE_CHANNEL_ID, message_id=message_id)
            except Exception:
                pass

        photo.seek(0)
        sent = await bot.send_photo(
            chat_id=LIFELINE_CHANNEL_ID,
            photo=photo,
            caption=caption,
            parse_mode='HTML'
        )
        db.set_lifeline_message(LIFELINE_CHANNEL_ID, sent.message_id)
    except Exception as e:
        logger.error(f"Lifeline: خطا در ارسال پست جدید: {e}")


async def add_day(bot: Bot, amount: int = 1):
    row = db.get_lifeline()
    max_days = row['max_days'] if row else 30
    db.adjust_lifeline_days(amount, max_days=max_days)
    await post_or_update_lifeline(bot)


async def subtract_day(bot: Bot, amount: int = 1):
    db.adjust_lifeline_days(-amount)
    await post_or_update_lifeline(bot)


async def refresh_pulse(context):
    """جاب دوره‌ای فقط برای افکت نفس‌کشیدن تصویر (بدون تغییر روز باقیمانده)"""
    await post_or_update_lifeline(context.bot)
