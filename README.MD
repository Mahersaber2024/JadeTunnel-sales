# Jade Tunnel Sales Bot (JadeTunnel-sales)

ربات فروش VPN تلگرامی مبتنی بر `python-telegram-bot` که اشتراک‌های V2Ray را از طریق یک یا چند پنل **3x-UI** می‌سازد، پرداخت کیف‌پولی/کارت‌به‌کارت را مدیریت می‌کند، و از طریق یک وب‌سرویس جانبی (`sub-api`) لینک اشتراک یکپارچه (ترکیب همه‌ی پنل‌ها) در اختیار کاربر می‌گذارد.

> ⚠️ **قبل از هر کاری بخوانید:** بخش [مشکلات شناسایی‌شده](#-مشکلات-شناسایی‌شده-در-وضعیت-فعلی-ریپازیتوری) — پروژه در وضعیت فعلی کامل نیست و بدون رفع آن اجرا نمی‌شود.

---

## فهرست

- [معماری](#معماری)
- [ساختار فایل‌ها](#ساختار-فایل‌ها)
- [پیش‌نیازها](#پیش‌نیازها)
- [نصب سریع](#نصب-سریع)
- [تنظیمات (`config.json` و `bot_settings.json`)](#تنظیمات)
- [سرویس‌های systemd](#سرویس‌های-systemd)
- [مدیریت پنل‌های 3x-UI](#مدیریت-پنل‌های-3x-ui)
- [جریان اشتراک یکپارچه (Iran Host Proxy)](#جریان-اشتراک-یکپارچه)
- [مشکلات شناسایی‌شده](#-مشکلات-شناسایی‌شده-در-وضعیت-فعلی-ریپازیتوری)
- [نکات امنیتی](#نکات-امنیتی)
- [عملیات روزمره](#عملیات-روزمره)

---

## معماری

```
                        ┌──────────────────┐
   کاربر تلگرام ───────▶│   main.py (Bot)   │──▶ PostgreSQL (users, subscriptions, transactions, invite_codes)
                        └────────┬──────────┘
                                 │ create_client / get_client_links
                                 ▼
                        ┌──────────────────┐
                        │  client_manager   │──▶ یک یا چند پنل 3x-UI (panel_manager.py → config/panels.json)
                        └──────────────────┘

   کلاینت VPN کاربر ───▶ index.php (هاست ایران) ──HTTP──▶ sub_api.py (aiohttp, پورت 2053) ──▶ PostgreSQL + پنل‌ها
```

دو پروسه‌ی مستقل روی سرور اجرا می‌شوند:

| سرویس | فایل ورودی | وظیفه |
|---|---|---|
| `sell-bot` | `main.py` | خود ربات تلگرام (polling) |
| `sub-api` | `sub_api.py` | وب‌سرویس aiohttp که لینک اشتراک را (بر اساس توکن کاربر) از همه‌ی پنل‌ها جمع‌آوری و برمی‌گرداند |

`index.php` روی هاست ایران (خارج از این ریپو، جدا آپلود می‌شود) درخواست کلاینت‌های VPN / مرورگر را به `sub_api.py` روی سرور اصلی پراکسی می‌کند تا از فیلترینگ داخل ایران عبور کند.

---

## ساختار فایل‌ها

| فایل | نقش |
|---|---|
| `main.py` | نقطه‌ی ورود ربات؛ ثبت تمام Handlerها و ConversationHandlerها |
| `handlers.py` | منطق اصلی کاربر: خرید VPN، شارژ کیف‌پول، افزایش حجم، مشاهده‌ی اشتراک‌ها، طرح اضطراری، تایید/رد پرداخت توسط ادمین |
| `admin.py` | پنل مدیریت (کیبورد ادمین): افزودن موجودی، مدیریت پنل‌ها، تنظیمات کانال/پشتیبانی/پاداش/کمیسیون/پرداخت ترکیبی، مدیریت طرح اضطراری |
| `send_gift.py` | فلوی ارسال هدیه‌ی موجودی بین کاربران (با انتخاب مخاطب از طریق `KeyboardButtonRequestUsers`) |
| `logger_bot.py` | ارسال لاگ‌های عملیاتی (خرید، پرداخت، خطای پنل و…) به تاپیک‌های یک گروه تلگرامی |
| `client_manager.py` | کلاینت HTTP برای API پنل 3x-UI (لاگین با CSRF، ساخت/حذف کلاینت، دریافت لینک، آپدیت حجم) |
| `panel_manager.py` | مدیریت چند پنل هم‌زمان؛ ذخیره در `config/panels.json`؛ الگوریتم انتخاب پنل بر اساس نوع طرح و ظرفیت |
| `proxy_manager.py` | لیست پروکسی‌های عمومی (`config/proxies.json`) — جدا از `emergency_proxies.json` که در `bot_settings.py` است |
| `bot_settings.py` | تنظیمات قابل‌تغییر از داخل ربات (کانال اسپانسر، پاداش‌ها، کارت پرداخت، آدرس پایه‌ی اشتراک یکپارچه) — در `bot_settings.json` ذخیره می‌شود |
| `config.py` | خواندن/نوشتن `config.json` (توکن بات، اطلاعات دیتابیس، آیدی ادمین‌ها، گروه لاگ) |
| `setup_db.py` | ساخت جدول‌های PostgreSQL (`users`, `subscriptions`, `transactions`, `invite_codes`) + کلیدهای خارجی و ایندکس‌ها |
| `sub_api.py` | وب‌سرویس aiohttp؛ اندپوینت‌های `/sub/{token}`، `/api/raw/{token}`، `/api/info/{token}`، `/health` |
| `install.sh` | نصب‌گر تعاملی کامل (وابستگی‌ها، دیتابیس، کلون، venv، ساخت جدول‌ها، دو سرویس systemd، تولید `index.php`) |
| `uninstall.sh` | حذف‌کننده‌ی مستقل — **قدیمی، فقط سرویس `sell-bot` را می‌شناسد** (نگاه کنید به بخش مشکلات) |
| `database.py` | ❌ **در ریپو موجود نیست** — نگاه کنید به بخش مشکلات |
| `requirements.txt` | ❌ **در ریپو موجود نیست** — نگاه کنید به بخش مشکلات |

---

## پیش‌نیازها

- Ubuntu 22.04/24.04 (یا معادل)، دسترسی root
- Python 3.10+
- PostgreSQL (نصب‌گر می‌تواند خودش نصب کند)
- یک یا چند پنل 3x-UI با API فعال
- توکن بات از `@BotFather`
- (اختیاری ولی توصیه‌شده) یک گروه تلگرامی با تاپیک‌های فعال برای لاگ عملیات
- یک هاست ایران با PHP برای میزبانی `index.php` (برای لینک اشتراک یکپارچه)

---

## نصب سریع

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Mahersaber2024/JadeTunnel-sales/main/install.sh)
```

گزینه‌ی `1) Full installation` را انتخاب کنید. نصب‌گر به ترتیب:

1. وابستگی‌های سیستمی (`python3-venv`, `libpq-dev`, ...) را نصب می‌کند
2. دیتابیس PostgreSQL و کاربر آن را می‌سازد (یا اطلاعات دیتابیس موجود را می‌گیرد)
3. توکن بات، آیدی ادمین‌ها و گروه لاگ را می‌پرسد
4. آدرس هاست ایران و IP سرور را برای پراکسی اشتراک می‌گیرد
5. پروژه را کلون و venv را می‌سازد
6. `setup_db.py --auto` را اجرا می‌کند
7. دو سرویس systemd (`sell-bot`, `sub-api`) را می‌سازد و اجرا می‌کند
8. `index.php` را برای آپلود روی هاست ایران تولید می‌کند

بعد از نصب، حتماً `index.php` تولیدشده را روی هاست ایران در مسیری که مشخص کردید آپلود کنید تا لینک اشتراک یکپارچه کار کند.

---

## تنظیمات

### `config.json` (حساس — دسترسی 600)
```json
{
  "bot_token": "...",
  "db_host": "localhost",
  "db_port": 5432,
  "db_name": "jadetunnel_base",
  "db_user": "cbu_user",
  "db_password": "...",
  "admin_ids": [123456789],
  "LOG_GROUP_ID": -1001234567890
}
```

### `bot_settings.json` (قابل‌تغییر از داخل پنل ادمین)
شامل: کانال اسپانسر، متن پشتیبانی، مبلغ پاداش ثبت‌نام/دعوت، پنل کمیسیونی اختصاصی، وضعیت پرداخت ترکیبی، اطلاعات کارت بانکی، و `combined_sub_base_url` (آدرس هاست ایران برای لینک اشتراک یکپارچه).

### `config/panels.json` (توسط `panel_manager.py` مدیریت می‌شود)
هر پنل شامل: `panel_base`, `username`, `password`, `inbound_ids`, `max_subscriptions`, `plan_types` (`new`/`old`/`custom_charge`/`emergency`), `enabled`, `is_default`.

---

## سرویس‌های systemd

```bash
systemctl status sell-bot sub-api
journalctl -u sell-bot -f
journalctl -u sub-api -f
systemctl restart sell-bot sub-api
```

`sub-api` روی پورت `2053` بالا می‌آید و اندپوینت‌های زیر را دارد:

| مسیر | خروجی |
|---|---|
| `GET /sub/{token}` | لینک‌های اشتراک به‌صورت base64 (فرمت استاندارد Import کلاینت) |
| `GET /sub/{token}?details=1` | JSON با جزئیات هر اشتراک (برای رندر HTML توسط `index.php`) |
| `GET /api/raw/{token}` | همان جزئیات بدون base64 |
| `GET /api/info/{token}` | اطلاعات کاربر و موجودی |
| `GET /health` | health check |

---

## مدیریت پنل‌های 3x-UI

از داخل پنل ادمین ربات (`/admin` → مدیریت پنل‌ها) می‌توان پنل افزود/حذف کرد، محدودیت ظرفیت هر پنل را تغییر داد، پنل پیش‌فرض را عوض کرد، و مشخص کرد هر پنل کدام نوع طرح‌ها (`new`, `old`, `custom_charge`, `emergency`) را پشتیبانی کند. `panel_manager.get_panel_for_subscription()` بر اساس این تنظیمات و ظرفیت فعلی، پنل مناسب هر خرید را انتخاب می‌کند — **بدون fallback خودکار به پنل‌های نامرتبط** (مثلاً یک خرید معمولی هرگز روی پنل اختصاصیِ کمیسیونی ساخته نمی‌شود).

---

## جریان اشتراک یکپارچه

1. کاربر در بخش «📒 اشتراک‌ها» یک لینک واحد دریافت می‌کند: `https://<iran-host>/sub/<token>`
2. اگر با مرورگر باز شود → `index.php` صفحه‌ی HTML فارسی با دکمه‌ی کپی برای هر کانفیگ نمایش می‌دهد
3. اگر با کلاینت VPN باز شود (بر اساس User-Agent) → متن base64 مستقیم Import می‌شود
4. `index.php` این کار را با فراخوانی `sub_api.py` روی سرور اصلی (`http://<SERVER_IP>:2053`) انجام می‌دهد

---

## ⚠️ مشکلات شناسایی‌شده در وضعیت فعلی ریپازیتوری

بررسی فایل‌های آپلودشده نشان داد:

### 1. `database.py` وجود ندارد (بحرانی)
`main.py` و `sub_api.py` هر دو خط زیر را دارند:
```python
from database import Database
```
ولی این فایل در ریپازیتوری/آپلود موجود نیست. **بدون آن، هیچ‌کدام از دو سرویس بالا نمی‌آید.** بر اساس تمام فراخوانی‌های `db.<method>(...)` در `handlers.py`, `admin.py`, `send_gift.py`, `sub_api.py`, `main.py`، کلاس `Database` باید حداقل این متدها را داشته باشد:

```
add_subscription, add_transaction, add_user, add_volume_to_subscription,
delete_subscription, delete_user, get_active_subscriptions,
get_custom_charge_subscriptions, get_emergency_access, get_emergency_panel_ids,
get_inactive_subscriptions_count, get_or_create_sub_token, get_referral_count,
get_subscription, get_total_commission, get_user, get_user_id_by_sub_token,
get_user_subscriptions, has_emergency_subscription, list_emergency_access,
reject_emergency_access, remove_emergency_access, request_emergency_access,
reset_balance, set_emergency_access, update_balance
```
**اقدام لازم:** فایل `database.py` را از سرور یا نسخه‌ی قبلی ریپو پیدا و اضافه کنید، یا از این لیست به‌عنوان مشخصات برای بازنویسی آن استفاده کنید.

### 2. `requirements.txt` وجود ندارد
`install.sh` در `setup_venv()` این دستور را اجرا می‌کند:
```bash
pip install -r requirements.txt
```
بدون این فایل، نصب venv با خطا متوقف می‌شود. حداقل باید شامل باشد: `python-telegram-bot`, `psycopg2-binary`, `aiohttp`, `requests`.

### 3. `uninstall.sh` مستقل، قدیمی و ناقص است
این فایل جدا از `install.sh` فقط سرویس `sell-bot` را می‌شناسد و از `sub-api` کاملاً بی‌خبر است (متغیرهای `SUB_SERVICE_NAME`/`SUB_SERVICE_FILE` در آن تعریف نشده‌اند). اگر کسی مستقیماً این فایل را اجرا کند، سرویس `sub-api` روی سرور باقی می‌ماند. در مقابل، تابع داخلی `uninstall_bot()` در خود `install.sh` (گزینه‌ی ۷ در منو) هر دو سرویس را درست پاک می‌کند.
**اقدام لازم:** یا `uninstall.sh` را با منطق `create_systemd_services` در `install.sh` هم‌گام کنید، یا آن را کلاً حذف و کاربران را به گزینه‌ی داخلی `install.sh` ارجاع دهید.

---

## نکات امنیتی

- `config.json` حاوی توکن بات و پسورد دیتابیس است؛ نصب‌گر آن را با `chmod 600` می‌سازد — دست‌کاری نکنید.
- **توکن‌های GitHub Personal Access Token هرگز نباید در ترمینال کلون/دستورات پیست یا لاگ شوند.** اگر چنین اتفاقی افتاده، توکن را از `GitHub → Settings → Developer settings → Personal access tokens` فوراً Revoke و جایگزین کنید.
- اطلاعات کارت بانکی و شماره‌ی گروه لاگ در `bot_settings.json`/`config.json` است — این فایل‌ها را در کنترل نسخه (git) commit نکنید.
- `API_KEY` در `sub_api.py` را با متغیر محیطی `SUB_API_KEY` فعال کنید تا اندپوینت‌های عمومی بدون احراز هویت در دسترس نباشند (در حال حاضر پیش‌فرض خالی = بدون محدودیت).
- ارتباط بین `index.php` (هاست ایران) و `sub_api.py` (سرور اصلی) روی HTTP ساده و بدون احراز هویت انجام می‌شود؛ برای محیط تولید، پشت فایروال محدود به IP هاست ایران قرار دهید یا HTTPS/`SUB_API_KEY` اضافه کنید.

---

## عملیات روزمره

| کار | دستور |
|---|---|
| مشاهده‌ی لاگ ربات | `journalctl -u sell-bot -f` |
| مشاهده‌ی لاگ sub-api | `journalctl -u sub-api -f` |
| ری‌استارت هر دو سرویس | `systemctl restart sell-bot sub-api` |
| آپدیت به آخرین نسخه | از منوی `install.sh` گزینه‌ی `2) Update bot` |
| بکاپ دیتابیس | `pg_dump -U cbu_user jadetunnel_base > backup.sql` |
| اجرای دستی ساخت جدول‌ها | `python3 setup_db.py` (از داخل venv) |
