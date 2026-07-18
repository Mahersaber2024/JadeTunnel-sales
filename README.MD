# Jade Tunnel Sales Bot (JadeTunnel-sales)

ربات فروش VPN تلگرامی مبتنی بر `python-telegram-bot` که اشتراک‌های V2Ray را از طریق یک یا چند پنل **3x-UI** می‌سازد، پرداخت کیف‌پولی/کارت‌به‌کارت را مدیریت می‌کند، و از طریق یک وب‌سرویس جانبی (`sub-api`) لینک اشتراک یکپارچه (ترکیب همه‌ی پنل‌ها) در اختیار کاربر می‌گذارد.

با اضافه‌شدن `database.py`، `requirements.txt` و `LICENSE`، مجموعه‌ی فایل‌ها اکنون **کامل** است — با یک باگ وابستگی و یک باگ منطقی که در بخش [مشکلات شناسایی‌شده](#-مشکلات-شناسایی‌شده) توضیح داده شده.

## نصب سریع

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Mahersaber2024/JadeTunnel-sales/main/install.sh)
```

گزینه‌ی `1) Full installation` را انتخاب کنید. نصب‌گر به ترتیب:

1. وابستگی‌های سیستمی را نصب می‌کند
2. دیتابیس PostgreSQL و کاربر آن را می‌سازد (یا اطلاعات دیتابیس موجود را می‌گیرد)
3. توکن بات، آیدی ادمین‌ها و گروه لاگ را می‌پرسد
4. آدرس هاست ایران و IP سرور را برای پراکسی اشتراک می‌گیرد
5. پروژه را کلون و venv را می‌سازد و `pip install -r requirements.txt` را اجرا می‌کند
6. `setup_db.py --auto` را اجرا می‌کند (جدول‌ها را `database.py` هم در اولین اجرای واقعی خودش می‌سازد/migrate می‌کند)
7. دو سرویس systemd (`sell-bot`, `sub-api`) را می‌سازد و اجرا می‌کند
8. `index.php` را برای آپلود روی هاست ایران تولید می‌کند

> پیش از نصب، حتماً اصلاح شماره‌ی ۱ در بخش «مشکلات شناسایی‌شده» (اضافه‌کردن `aiohttp` به `requirements.txt`) را انجام دهید، وگرنه سرویس `sub-api` بعد از نصب بالا نمی‌آید.

بعد از نصب، `index.php` تولیدشده را روی هاست ایران در مسیری که مشخص کردید آپلود کنید تا لینک اشتراک یکپارچه کار کند.


## Uninstallation
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Mahersaber2024/JadeTunnel-sales/main/install.sh)
---
---

## سرویس‌های systemd

```bash
systemctl status sell-bot sub-api
journalctl -u sell-bot -f
journalctl -u sub-api -f
systemctl restart sell-bot sub-api
```

اندپوینت‌های `sub-api` (پورت `2053`):

| مسیر | خروجی |
|---|---|
| `GET /sub/{token}` | لینک‌های اشتراک به‌صورت base64 |
| `GET /sub/{token}?details=1` | JSON با جزئیات هر اشتراک (برای رندر HTML توسط `index.php`) |
| `GET /api/raw/{token}` | همان جزئیات بدون base64 |
| `GET /api/info/{token}` | اطلاعات کاربر و موجودی |
| `GET /health` | health check |

---

## مدیریت پنل‌های 3x-UI

از داخل پنل ادمین ربات (`/admin` → مدیریت پنل‌ها) می‌توان پنل افزود/حذف کرد، ظرفیت هر پنل را تغییر داد، پنل پیش‌فرض را عوض کرد، و مشخص کرد هر پنل کدام نوع طرح‌ها را پشتیبانی کند. `panel_manager.get_panel_for_subscription()` بر اساس این تنظیمات و ظرفیت فعلی، پنل مناسب هر **خرید جدید** را انتخاب می‌کند — بدون fallback خودکار به پنل‌های نامرتبط.

---

## جریان اشتراک یکپارچه

1. کاربر در بخش «📒 اشتراک‌ها» یک لینک واحد دریافت می‌کند: `https://<iran-host>/sub/<token>`
2. اگر با مرورگر باز شود → `index.php` صفحه‌ی HTML فارسی با دکمه‌ی کپی برای هر کانفیگ نمایش می‌دهد
3. اگر با کلاینت VPN باز شود → متن base64 مستقیم Import می‌شود
4. `index.php` این کار را با فراخوانی `sub_api.py` روی سرور اصلی (`http://<SERVER_IP>:2053`) انجام می‌دهد؛ `sub_api.py` برای هر اشتراک کاربر، پنل درست (`panel_id` ذخیره‌شده در آن رکورد) را صدا می‌زند تا لینک واقعی را بگیرد.

---

## ⚠️ مشکلات شناسایی‌شده

### 1. `requirements.txt` وابستگی `aiohttp` را کم دارد (بحرانی برای `sub-api`)
`sub_api.py` این خط را دارد:
```python
from aiohttp import web
```
ولی `requirements.txt` فقط شامل:
```
python-telegram-bot
psycopg2-binary
python-dotenv
requests
httpx
```
است. بدون `aiohttp`، بعد از `pip install -r requirements.txt`، سرویس `sub-api` با `ModuleNotFoundError: No module named 'aiohttp'` کرش می‌کند (سرویس `sell-bot` تحت تأثیر قرار نمی‌گیرد چون به `aiohttp` نیازی ندارد).

**رفع سریع:**
```bash
echo "aiohttp" >> requirements.txt
cd /opt/sell-bot && source venv/bin/activate && pip install aiohttp && deactivate
systemctl restart sub-api
```

### 2. آپدیت حجم اضافی همیشه روی پنل پیش‌فرض اعمال می‌شود، نه پنل واقعی اشتراک (باگ منطقی، غیر بحرانی)
در چهار نقطه از `handlers.py` (افزودن حجم با کیف‌پول، افزودن حجم با کارت‌به‌کارت، و تاییدهای متناظر ادمین) این الگو تکرار شده:
```python
subscription = db.get_subscription(subscription_id)
if subscription and subscription.get('email'):
    from client_manager import get_panel_client
    panel_client = get_panel_client()          # ← بدون panel_id، یعنی همیشه پنل پیش‌فرض
    panel_client.update_client_volume(subscription['email'], subscription['remaining_volume'])
```
مشکل از اینجا شروع می‌شود که خود `Database.get_subscription()` اصلاً ستون `panel_id` را در کوئری‌اش انتخاب نمی‌کند:
```python
SELECT id, user_id, protocol, duration_days, email,
       plan_type, remaining_volume, start_date, end_date
FROM subscriptions WHERE id = %s


## نکات امنیتی

- `config.json` حاوی توکن بات و پسورد دیتابیس است؛ نصب‌گر آن را با `chmod 600` می‌سازد.
- توکن‌های GitHub Personal Access Token هرگز نباید در ترمینال کلون/دستورات پیست یا لاگ شوند؛ در صورت افشا فوراً Revoke کنید.
- اطلاعات کارت بانکی و شماره‌ی گروه لاگ در `bot_settings.json`/`config.json` است — این فایل‌ها را commit نکنید.
- `API_KEY` در `sub_api.py` را با متغیر محیطی `SUB_API_KEY` فعال کنید تا اندپوینت‌ها بدون احراز هویت در دسترس نباشند (پیش‌فرض خالی = بدون محدودیت).
- ارتباط بین `index.php` (هاست ایران) و `sub_api.py` روی HTTP ساده و بدون احراز هویت انجام می‌شود؛ در تولید، پشت فایروال محدود به IP هاست ایران قرار دهید یا HTTPS/`SUB_API_KEY` اضافه کنید.



## لایسنس

MIT License — © 2026 Mahersaber2024. متن کامل در فایل `LICENSE`.
