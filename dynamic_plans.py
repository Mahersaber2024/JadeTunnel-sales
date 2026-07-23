import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple

CONFIG_DIR = Path(__file__).parent / 'config'
PLANS_FILE = str(CONFIG_DIR / 'custom_plans.json')

# plan_type ثابتی که همه‌ی طرح‌های داینامیک از آن استفاده می‌کنند
DYNAMIC_PLAN_TYPE = 'custom_plan'

DEFAULT_FOOTER_TEXT = (
    'لطفاً پلن مورد نظر را انتخاب کنید:\n\n'
    '<a href="https://t.me/jadetunnell/13">جزئیات بیشتر</a>'
)

DEFAULT_SCHEMES = {
    'new': {
        'id': 'new',
        'name': '🆕 طرح جدید',
        'description': 'نامحدود\nسرعت عالی + پایداری بالا + بدون اختلال در اپراتورها\n🔓 بدون محدودیت تعداد کاربر | 📅 ماهانه',
        'footer_text': DEFAULT_FOOTER_TEXT,
        'enabled': True,
        'order': 1,
    },
    'old': {
        'id': 'old',
        'name': '📦 طرح قدیمی',
        'description': '⚠️ توجه: این طرح‌ها محدودیت تعداد کاربر دارند (بعضی اپراتورها اختلال دارد)',
        'footer_text': DEFAULT_FOOTER_TEXT,
        'enabled': True,
        'order': 2,
    },
}

_cache = None
_mtime = None


def _load_raw() -> dict:
    """کل فایل شامل هر دو کلید plans و schemes را برمی‌گرداند"""
    global _cache, _mtime
    if os.path.exists(PLANS_FILE):
        try:
            mtime = os.path.getmtime(PLANS_FILE)
            if _cache is not None and _mtime == mtime:
                return _cache
            with open(PLANS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _cache = {
                'plans': data.get('plans', {}),
                'schemes': data.get('schemes', {}),
            }
            _mtime = mtime
            return _cache
        except Exception:
            _cache = {'plans': {}, 'schemes': {}}
            return _cache
    _cache = {'plans': {}, 'schemes': {}}
    return _cache


def _save_raw(plans: dict = None, schemes: dict = None):
    global _cache, _mtime
    raw = _load_raw()
    if plans is not None:
        raw = {**raw, 'plans': plans}
    if schemes is not None:
        raw = {**raw, 'schemes': schemes}
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(PLANS_FILE, 'w', encoding='utf-8') as f:
        json.dump(
            {'plans': raw['plans'], 'schemes': raw['schemes'], 'updated_at': datetime.now().isoformat()},
            f, ensure_ascii=False, indent=2
        )
    _cache = {'plans': raw['plans'], 'schemes': raw['schemes']}
    try:
        _mtime = os.path.getmtime(PLANS_FILE)
    except OSError:
        pass


def _load() -> dict:
    """فقط دیکشنری پلن‌ها (سازگار با نسخه‌ی قبلی این ماژول)"""
    return _load_raw()['plans']


def _save(plans: dict):
    _save_raw(plans=plans)


# ============ مدیریت «طرح‌ها» (schemes) ============

def get_all_schemes(enabled_only: bool = False) -> dict:
    """
    دیکشنری {scheme_id: scheme_dict} را بر اساس order مرتب‌شده برمی‌گرداند.
    اگر تا حالا هیچ طرحی ساخته نشده باشد، دو طرح پیش‌فرض «جدید»/«قدیمی»
    به‌صورت خودکار ساخته و ذخیره می‌شوند.
    """
    raw = _load_raw()
    schemes = raw.get('schemes', {})
    if not schemes:
        schemes = {k: dict(v) for k, v in DEFAULT_SCHEMES.items()}
        _save_raw(schemes=schemes)
    items = list(schemes.items())
    if enabled_only:
        items = [(k, v) for k, v in items if v.get('enabled', True)]
    items.sort(key=lambda kv: kv[1].get('order', 0))
    return dict(items)


def get_scheme(scheme_id: str):
    return get_all_schemes().get(scheme_id)


def get_scheme_footer_text(scheme_id: str) -> str:
    """متن پایین صفحه‌ی یک طرح؛ اگر تنظیم نشده باشد، متن پیش‌فرض برمی‌گردد"""
    scheme = get_scheme(scheme_id)
    if scheme and scheme.get('footer_text'):
        return scheme['footer_text']
    return DEFAULT_FOOTER_TEXT


def add_scheme(name: str, description: str = '', footer_text: str = '') -> str:
    """یک طرح جدید می‌سازد و شناسه‌ی آن را برمی‌گرداند"""
    schemes = get_all_schemes().copy()
    scheme_id = uuid.uuid4().hex[:8]
    order = max([s.get('order', 0) for s in schemes.values()], default=0) + 1
    schemes[scheme_id] = {
        'id': scheme_id,
        'name': name,
        'description': description or '',
        'footer_text': footer_text or '',
        'enabled': True,
        'order': order,
        'created_at': datetime.now().isoformat(),
    }
    _save_raw(schemes=schemes)
    return scheme_id


def update_scheme(scheme_id: str, **kwargs) -> bool:
    schemes = get_all_schemes().copy()
    if scheme_id not in schemes:
        return False
    for key in ('name', 'description', 'enabled', 'order', 'footer_text'):
        if key in kwargs:
            schemes[scheme_id][key] = kwargs[key]
    _save_raw(schemes=schemes)
    return True


def toggle_scheme(scheme_id: str) -> bool:
    schemes = get_all_schemes().copy()
    if scheme_id not in schemes:
        return False
    schemes[scheme_id]['enabled'] = not schemes[scheme_id].get('enabled', True)
    _save_raw(schemes=schemes)
    return True


def scheme_plan_count(scheme_id: str) -> int:
    """تعداد پلن‌هایی (فعال یا غیرفعال) که به این طرح وصل هستند"""
    plans = _load()
    return sum(1 for p in plans.values() if p.get('category', 'new') == scheme_id)


def delete_scheme(scheme_id: str) -> Tuple[bool, str]:
    """
    حذف یک طرح. اگر پلنی هنوز به این طرح وصل باشد حذف انجام نمی‌شود
    (باید اول پلن‌های آن حذف یا به طرح دیگری منتقل شوند) تا پلن‌های
    یتیم/گم‌شده در منوی خرید ایجاد نشود.
    """
    schemes = get_all_schemes().copy()
    if scheme_id not in schemes:
        return False, 'این طرح یافت نشد.'
    count = scheme_plan_count(scheme_id)
    if count > 0:
        return False, f'این طرح {count} پلن دارد؛ اول پلن‌های آن را حذف یا به طرح دیگری منتقل کنید.'
    del schemes[scheme_id]
    _save_raw(schemes=schemes)
    return True, 'طرح حذف شد.'


def get_all_plans(active_only: bool = True, category: str = None) -> dict:
    """
    دیکشنری {plan_id: plan_dict} را برمی‌گرداند، بر اساس فیلد order مرتب‌شده.
    اگر active_only=True باشد فقط طرح‌های enabled=True برگردانده می‌شوند
    (همان چیزی که باید به کاربر عادی نمایش داده شود).
    اگر category داده شود ('new' یا 'old')، فقط طرح‌های همان دسته برگردانده
    می‌شوند — این همان تفکیکی است که در منوی «🎯 انتخاب نوع طرح» استفاده
    می‌شود. طرح‌های قدیمی که category نداشتند، پیش‌فرض 'new' در نظر گرفته
    می‌شوند تا داده‌ای گم نشود.
    """
    plans = _load()
    items = list(plans.items())
    if active_only:
        items = [(k, v) for k, v in items if v.get('enabled', True)]
    if category is not None:
        items = [(k, v) for k, v in items if v.get('category', 'new') == category]
    items.sort(key=lambda kv: kv[1].get('order', 0))
    return dict(items)


def get_plan(plan_id: str):
    return _load().get(plan_id)


def add_plan(name: str, description: str, price: int, days: int,
             volume_gb: float = 0, daily_volume=None, category: str = None) -> str:
    """یک پلن جدید اضافه می‌کند و شناسه‌ی آن را برمی‌گرداند. category همان
    شناسه‌ی «طرحی» (scheme) است که این پلن زیر آن نمایش داده می‌شود."""
    plans = _load().copy()
    plan_id = uuid.uuid4().hex[:8]
    order = max([p.get('order', 0) for p in plans.values()], default=0) + 1
    if category is None or not get_scheme(category):
        # اگر طرحی داده نشده یا دیگر وجود ندارد، اولین طرح فعال را انتخاب کن
        fallback_schemes = get_all_schemes(enabled_only=True)
        category = next(iter(fallback_schemes), 'new')
    plans[plan_id] = {
        'id': plan_id,
        'name': name,
        'description': description or '',
        'price': int(price),
        'days': int(days),
        'volume': volume_gb,          # 0 یعنی نامحدود
        'daily_volume': daily_volume,  # فقط برای نمایش؛ می‌تواند None باشد
        'category': category,         # شناسه‌ی طرح (scheme_id) — برای منوی انتخاب نوع طرح
        'enabled': True,
        'order': order,
        'created_at': datetime.now().isoformat()
    }
    _save(plans)
    return plan_id


def update_plan(plan_id: str, **kwargs) -> bool:
    plans = _load().copy()
    if plan_id not in plans:
        return False
    for key in ('name', 'description', 'price', 'days', 'volume', 'daily_volume', 'enabled', 'order', 'category'):
        if key in kwargs:
            plans[plan_id][key] = kwargs[key]
    _save(plans)
    return True


def delete_plan(plan_id: str) -> bool:
    plans = _load().copy()
    if plan_id not in plans:
        return False
    del plans[plan_id]
    _save(plans)
    return True


def toggle_plan(plan_id: str) -> bool:
    """فعال/غیرفعال کردن یک طرح بدون حذف آن (طرح غیرفعال به کاربران نمایش داده نمی‌شود)"""
    plans = _load().copy()
    if plan_id not in plans:
        return False
    plans[plan_id]['enabled'] = not plans[plan_id].get('enabled', True)
    _save(plans)
    return True
