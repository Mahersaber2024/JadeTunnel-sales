import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# چون این فایل داخل پوشه‌ی Autoscanner قرار دارد، فایل تنظیمات هم همین‌جا (کنار خودش) ساخته می‌شود
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "autoscanner_settings.json")

DEFAULT_SETTINGS = {
    "cf_api_token": "",
    "zones": [],           # [{"id": "<zone_id>", "label": "..."}]
    "records": [],         # [{"name": "goip44.bazargarni.ir", "port": 443, "zone_id": "..."}]
    "scan_interval_hours": 6,
    "enabled": False,
    "last_run_at": None,   # ISO timestamp (UTC)
}

_cache = None


def _load():
    global _cache
    if _cache is not None:
        return _cache
    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading autoscanner_settings.json: {e}")
            data = {}
    merged = {**DEFAULT_SETTINGS, **data}
    _cache = merged
    return merged


def _save(data):
    global _cache
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _cache = data


# ====================== Cloudflare API Token ======================

def get_cf_api_token() -> str:
    return _load().get("cf_api_token", "") or ""


def set_cf_api_token(token: str):
    data = _load()
    data["cf_api_token"] = token.strip()
    _save(data)


# ====================== Zones ======================

def get_zones() -> list:
    return _load().get("zones", [])


def get_zone(zone_id: str):
    for z in get_zones():
        if z["id"] == zone_id:
            return z
    return None


def add_zone(zone_id: str, label: str = None) -> bool:
    zone_id = zone_id.strip()
    data = _load()
    zones = data.get("zones", [])
    if any(z["id"] == zone_id for z in zones):
        return False
    zones.append({"id": zone_id, "label": (label or zone_id).strip()})
    data["zones"] = zones
    _save(data)
    return True


def remove_zone(zone_id: str) -> bool:
    data = _load()
    zones = data.get("zones", [])
    new_zones = [z for z in zones if z["id"] != zone_id]
    if len(new_zones) == len(zones):
        return False
    data["zones"] = new_zones
    # رکوردهایی که به این Zone وصل بودند هم حذف می‌شوند
    data["records"] = [r for r in data.get("records", []) if r.get("zone_id") != zone_id]
    _save(data)
    return True


# ====================== Records (record_name:port -> zone) ======================

def get_records() -> list:
    return _load().get("records", [])


def add_record(name: str, port: int, zone_id: str) -> bool:
    name = name.strip().lower()
    data = _load()
    records = data.get("records", [])
    if any(r["name"] == name and r["port"] == port for r in records):
        return False
    records.append({"name": name, "port": int(port), "zone_id": zone_id})
    data["records"] = records
    _save(data)
    return True


def remove_record(index: int) -> bool:
    data = _load()
    records = data.get("records", [])
    if index < 0 or index >= len(records):
        return False
    records.pop(index)
    data["records"] = records
    _save(data)
    return True


# ====================== Interval / Enabled / Last run ======================

def get_scan_interval_hours() -> int:
    try:
        return int(_load().get("scan_interval_hours", DEFAULT_SETTINGS["scan_interval_hours"]))
    except (TypeError, ValueError):
        return DEFAULT_SETTINGS["scan_interval_hours"]


def set_scan_interval_hours(hours: int):
    data = _load()
    data["scan_interval_hours"] = int(hours)
    _save(data)


def is_autoscanner_enabled() -> bool:
    return bool(_load().get("enabled", False))


def set_autoscanner_enabled(value: bool):
    data = _load()
    data["enabled"] = bool(value)
    _save(data)


def get_last_run_at():
    val = _load().get("last_run_at")
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


def set_last_run_at(dt: datetime = None):
    data = _load()
    dt = dt or datetime.now(timezone.utc)
    data["last_run_at"] = dt.isoformat()
    _save(data)


def is_due_for_run() -> bool:
    """آیا با توجه به فاصله زمانی تنظیم‌شده، الان وقت اجرای اسکن است؟"""
    if not is_autoscanner_enabled():
        return False
    last_run = get_last_run_at()
    if last_run is None:
        return True
    interval_hours = get_scan_interval_hours()
    elapsed = datetime.now(timezone.utc) - last_run
    return elapsed.total_seconds() >= interval_hours * 3600