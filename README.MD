# Jade Tunnel Sales Bot (JadeTunnel-sales)

ربات فروش VPN تلگرامی مبتنی بر `python-telegram-bot` که اشتراک‌های V2Ray را از طریق یک یا چند پنل **3x-UI** می‌سازد، پرداخت کیف‌پولی/کارت‌به‌کارت را مدیریت می‌کند، و از طریق یک وب‌سرویس جانبی (`sub-api`) لینک اشتراک یکپارچه (ترکیب همه‌ی پنل‌ها) در اختیار کاربر می‌گذارد.

با اضافه‌شدن `database.py`، `requirements.txt` و `LICENSE`، مجموعه‌ی فایل‌ها اکنون **کامل** است — با یک باگ وابستگی و یک باگ منطقی که در بخش [مشکلات شناسایی‌شده](#-مشکلات-شناسایی‌شده) توضیح داده شده.

---

## فهرست

- [معماری](#معماری)
- [ساختار فایل‌ها](#ساختار-فایل‌ها)
- [مدل داده (`database.py`)](#مدل-داده-databasepy)
- [پیش‌نیازها](#پیش‌نیازها)
- [نصب سریع](#نصب-سریع)
- [تنظیمات](#تنظیمات)
- [سرویس‌های systemd](#سرویس‌های-systemd)
- [مدیریت پنل‌های 3x-UI](#مدیریت-پنل‌های-3x-ui)
- [جریان اشتراک یکپارچه](#جریان-اشتراک-یکپارچه)
- [⚠️ مشکلات شناسایی‌شده](#-مشکلات-شناسایی‌شده)
- [نکات امنیتی](#نکات-امنیتی)
- [عملیات روزمره](#عملیات-روزمره)
- [لایسنس](#لایسنس)

---

## معماری

```
                        ┌──────────────────┐
   کاربر تلگرام ───────▶│   main.py (Bot)   │──▶ PostgreSQL (users, subscriptions, transactions, invite_codes, emergency_access)
                        └────────┬──────────┘
                                 │ create_client / get_client_links / update_client_volume
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

`index.php` روی هاست ایران (خارج از این ریپو، جدا آپلود می‌شود) درخواست کلاینت‌های VPN/مرورگر را به `sub_api.py` روی سرور اصلی پراکسی می‌کند تا از فیلترینگ داخل ایران عبور کند.

---

## ساختار فایل‌ها

| فایل | نقش |
|---|---|
| `main.py` | نقطه‌ی ورود ربات؛ ثبت تمام Handlerها و ConversationHandlerها |
| `handlers.py` | منطق اصلی کاربر: خرید VPN، شارژ کیف‌پول، افزایش حجم، مشاهده‌ی اشتراک‌ها، طرح اضطراری، تایید/رد پرداخت توسط ادمین |
| `admin.py` | پنل مدیریت: افزودن موجودی، مدیریت پنل‌ها، تنظیمات کانال/پشتیبانی/پاداش/کمیسیون/پرداخت ترکیبی، مدیریت طرح اضطراری |
| `send_gift.py` | فلوی ارسال هدیه‌ی موجودی بین کاربران (انتخاب مخاطب از طریق `KeyboardButtonRequestUsers`) |
| `logger_bot.py` | ارسال لاگ‌های عملیاتی به تاپیک‌های یک گروه تلگرامی |
| `database.py` | لایه‌ی دیتابیس PostgreSQL — ساخت جدول‌ها/مهاجرت ستون‌ها هنگام اجرا و تمام متدهای CRUD |
| `client_manager.py` | کلاینت HTTP برای API پنل 3x-UI (لاگین با CSRF، ساخت/حذف کلاینت، دریافت لینک، آپدیت حجم) |
| `panel_manager.py` | مدیریت چند پنل هم‌زمان؛ ذخیره در `config/panels.json`؛ انتخاب پنل بر اساس نوع طرح و ظرفیت |
| `proxy_manager.py` | لیست پروکسی‌های عمومی (`config/proxies.json`) — جدا از `emergency_proxies.json` در `bot_settings.py` |
| `bot_settings.py` | تنظیمات قابل‌تغییر از داخل ربات؛ در `bot_settings.json` ذخیره می‌شود |
| `config.py` | خواندن/نوشتن `config.json` (توکن بات، اطلاعات دیتابیس، آیدی ادمین‌ها، گروه لاگ) |
| `setup_db.py` | ساخت اولیه‌ی جدول‌های PostgreSQL از خط فرمان (مستقل از کلاس `Database`) |
| `sub_api.py` | وب‌سرویس aiohttp؛ اندپوینت‌های `/sub/{token}`، `/api/raw/{token}`، `/api/info/{token}`، `/health` |
| `install.sh` | نصب‌گر تعاملی کامل (وابستگی‌ها، دیتابیس، کلون، venv، ساخت جدول‌ها، دو سرویس systemd، تولید `index.php`) |
| `uninstall.sh` | حذف‌کننده‌ی مستقل — **قدیمی، فقط سرویس `sell-bot` را می‌شناسد** (نگاه کنید به بخش مشکلات) |
| `requirements.txt` | وابستگی‌های پایتون — **کامل نیست**، `aiohttp` کم دارد (نگاه کنید به بخش مشکلات) |
| `LICENSE` | MIT License، © 2026 Mahersaber2024 |

---

## مدل داده (`database.py`)

کلاس `Database` در سازنده‌ی خودش (`__init__` → `connect()` → `_create_tables()` → `_add_missing_columns()`) هم جدول‌ها را در صورت نبود می‌سازد و هم ستون‌های جدید را روی نصب‌های قدیمی‌تر Migrate می‌کند — یعنی نیازی نیست هر بار `setup_db.py` را جداگانه اجرا کنید؛ اولین بار که ربات یا `sub-api` بالا بیاید این کار خودکار انجام می‌شود.

جدول‌ها:

| جدول | نکات کلیدی |
|---|---|
| `users` | `balance`, `referred_by`, `referral_count`, `sub_token` (برای لینک اشتراک یکپارچه) |
| `subscriptions` | `email`, `panel_id`, `plan_type`, `plan_name`, `remaining_volume`, `status`, `end_date` |
| `transactions` | تاریخچه‌ی تراکنش‌های کیف‌پول |
| `invite_codes` | کدهای دعوت (ساختار پایه، در حال حاضر در جریان دعوت لینکی استفاده نمی‌شود) |
| `emergency_access` | وضعیت درخواست/تایید طرح اضطراری هر کاربر (`pending`/`approved`/`rejected`) |

تمام متدهایی که در `handlers.py`, `admin.py`, `send_gift.py`, `sub_api.py`, `main.py` صدا زده می‌شوند در `database.py` پیاده‌سازی شده‌اند (`add_subscription`, `add_transaction`, `add_user`, `add_volume_to_subscription`, `delete_subscription`, `delete_user`, `get_active_subscriptions`, `get_custom_charge_subscriptions`, `get_emergency_access`, `get_emergency_panel_ids`, `get_inactive_subscriptions_count`, `get_or_create_sub_token`, `get_referral_count`, `get_subscription`, `get_total_commission`, `get_user`, `get_user_id_by_sub_token`, `get_user_subscriptions`, `has_emergency_subscription`, `list_emergency_access`, `reject_emergency_access`, `remove_emergency_access`, `request_emergency_access`, `reset_balance`, `set_emergency_access`, `update_balance`) — از این نظر پروژه دیگر ناقص نیست.

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
کانال اسپانسر، متن پشتیبانی، مبلغ پاداش ثبت‌نام/دعوت، پنل کمیسیونی اختصاصی، وضعیت پرداخت ترکیبی، اطلاعات کارت بانکی، و `combined_sub_base_url`.

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
```
در نتیجه اگر اشتراکِ کاربر روی پنلی غیر از پنل پیش‌فرض ساخته شده باشد (مثلاً پنل کمیسیونی اختصاصی یا هر پنل دومی که در `panels.json` تعریف شده)، افزایش حجم روی پنل اشتباه اعمال می‌شود — یا کلاینتی با آن ایمیل روی پنل پیش‌فرض پیدا نمی‌شود و خطای `Client with email '...' not found in panel` برمی‌گردد، یا بدتر، اگر تصادفاً همان ایمیل روی پنل پیش‌فرض هم وجود داشته باشد، حجمِ یک اکانتِ نامرتبط تغییر می‌کند.

**رفع پیشنهادی:** به `SELECT` در `get_subscription()` ستون `panel_id` (و `plan_name` که آن هم جا افتاده) اضافه شود، و در هر چهار محل فراخوانی، `get_panel_client(subscription.get('panel_id'))` صدا زده شود به‌جای `get_panel_client()` بدون آرگومان.

### 3. `uninstall.sh` مستقل، قدیمی و ناقص است
این فایل فقط سرویس `sell-bot` را می‌شناسد و از `sub-api` بی‌خبر است (متغیرهای `SUB_SERVICE_NAME`/`SUB_SERVICE_FILE` در آن تعریف نشده). اگر مستقیم اجرا شود، سرویس `sub-api` روی سرور باقی می‌ماند. در مقابل، گزینه‌ی داخلی `7) Complete uninstall` در خود `install.sh` هر دو سرویس را درست پاک می‌کند و همان توصیه می‌شود.

---

## نکات امنیتی

- `config.json` حاوی توکن بات و پسورد دیتابیس است؛ نصب‌گر آن را با `chmod 600` می‌سازد.
- توکن‌های GitHub Personal Access Token هرگز نباید در ترمینال کلون/دستورات پیست یا لاگ شوند؛ در صورت افشا فوراً Revoke کنید.
- اطلاعات کارت بانکی و شماره‌ی گروه لاگ در `bot_settings.json`/`config.json` است — این فایل‌ها را commit نکنید.
- `API_KEY` در `sub_api.py` را با متغیر محیطی `SUB_API_KEY` فعال کنید تا اندپوینت‌ها بدون احراز هویت در دسترس نباشند (پیش‌فرض خالی = بدون محدودیت).
- ارتباط بین `index.php` (هاست ایران) و `sub_api.py` روی HTTP ساده و بدون احراز هویت انجام می‌شود؛ در تولید، پشت فایروال محدود به IP هاست ایران قرار دهید یا HTTPS/`SUB_API_KEY` اضافه کنید.

---

## عملیات روزمره

| کار | دستور |
|---|---|
| مشاهده‌ی لاگ ربات | `journalctl -u sell-bot -f` |
| مشاهده‌ی لاگ sub-api | `journalctl -u sub-api -f` |
| ری‌استارت هر دو سرویس | `systemctl restart sell-bot sub-api` |
| آپدیت به آخرین نسخه | از منوی `install.sh` گزینه‌ی `2) Update bot` |
| بکاپ دیتابیس | `pg_dump -U cbu_user jadetunnel_base > backup.sql` |
| اجرای دستی ساخت جدول‌ها | `python3 setup_db.py` (از داخل venv) — اختیاری، چون `database.py` هم خودش این کار را انجام می‌دهد |

---

## لایسنس

MIT License — © 2026 Mahersaber2024. متن کامل در فایل `LICENSE`.
