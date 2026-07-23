#!/usr/bin/env python3
# sub_api.py - Web Service for Subscription Links (with SSL support)

import os
import sys
import json
import base64
import logging
import traceback
import ssl
from datetime import datetime
from aiohttp import web
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from database import Database
from client_manager import get_panel_client, PanelClient
from panel_manager import get_panel_manager

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("sub_api")

API_KEY = os.environ.get("SUB_API_KEY", "")
HOST = os.environ.get("SUB_HOST", "0.0.0.0")
PORT = int(os.environ.get("SUB_PORT", 2053))

SSL_CERT_FILE = os.environ.get("SSL_CERT_FILE")
SSL_KEY_FILE = os.environ.get("SSL_KEY_FILE")
ENABLE_SSL = SSL_CERT_FILE and SSL_KEY_FILE and os.path.exists(SSL_CERT_FILE) and os.path.exists(SSL_KEY_FILE)

db: Database = None

def init_db():
    global db
    if not config.load():
        raise RuntimeError("Bot configuration not found — please run/set up the main bot first.")
    db = Database(config.get_db_config())
    logger.info("✅ Database connection established for sub_api")

def check_api_key(request: web.Request) -> bool:
    if not API_KEY:
        return True
    return request.headers.get("X-API-Key") == API_KEY

def _to_number(value):
    if value is None:
        return None
    try:
        f = float(value)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None

def collect_user_configs(user_id: int):
    subs = db.get_active_subscriptions(user_id)
    configs = []
    details = []

    for sub in subs:
        email = sub.get('email')
        panel_id = sub.get('panel_id')
        sub_id = sub.get('id')
        plan_type = sub.get('plan_type')

        links = []

        # ============ کانفیگ‌های واقعی از پنل ============
        # فقط وقتی email داریم و panel_id معتبر است (یعنی واقعاً روی یک پنل 3xUI ساخته شده)
        # اشتراک‌های دستی (plan_type == 'manual') پنل واقعی ندارند، سراغشان نمی‌رویم
        if email and panel_id and plan_type != 'manual':
            try:
                client = get_panel_client(panel_id)
                links = client.get_client_links(email) or []
            except Exception as e:
                logger.error(f"Error fetching links for subscription {sub_id} (panel {panel_id}): {e}")
                links = []

            if not links:
                try:
                    client_info = client.get_client_info(email)
                    if client_info and client_info.get('subId'):
                        panel_base = client.panel_base
                        links = [f"{panel_base}/sub/{client_info.get('subId')}"]
                except Exception:
                    pass

        # ============ کانفیگ‌های دستی ثبت‌شده توسط ادمین ============
        try:
            manual_configs = db.get_manual_configs(sub_id) or []
            manual_links = [mc['link'] for mc in manual_configs]
        except Exception as e:
            logger.error(f"Error fetching manual configs for subscription {sub_id}: {e}")
            manual_links = []

        links = list(links) + manual_links

        configs.extend(links)

        panel_name = "Default panel"
        if panel_id:
            panel_manager = get_panel_manager()
            panel_data = panel_manager.get_panel(panel_id)
            if panel_data:
                panel_name = panel_data.get('name', panel_id)
        elif plan_type == 'manual':
            panel_name = "Manual"

        details.append({
            "subscription_id": sub_id,
            "plan_name": sub.get('plan_name') or sub.get('plan_type') or "Plan",
            "remaining_volume": _to_number(sub.get('remaining_volume')),
            "end_date": str(sub.get('end_date'))[:10] if sub.get('end_date') else None,
            "start_date": str(sub.get('start_date'))[:10] if sub.get('start_date') else None,
            "panel_id": panel_id,
            "panel_name": panel_name,
            "email": email,
            "links": links,
        })

    return configs, details

async def handle_sub(request: web.Request):
    if not check_api_key(request):
        return web.Response(status=403, text="forbidden")

    token = request.match_info.get('token')
    if not token:
        return web.Response(status=400, text="missing token")

    try:
        user_id = db.get_user_id_by_sub_token(token)
        if not user_id:
            return web.Response(status=404, text="subscription not found")

        configs, details = collect_user_configs(user_id)

        if request.query.get('details') == '1':
            return web.json_response({
                "user_id": user_id,
                "count": len(configs),
                "subscriptions": details,
            })

        if not configs:
            return web.Response(text="", content_type="text/plain", charset="utf-8")

        raw = "\n".join(configs)
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        return web.Response(text=encoded, content_type="text/plain", charset="utf-8")
    except Exception:
        logger.error("Error in handle_sub:\n" + traceback.format_exc())
        return web.json_response({"error": "internal_error"}, status=500)

async def handle_raw_configs(request: web.Request):
    if not check_api_key(request):
        return web.Response(status=403, text="forbidden")

    token = request.match_info.get('token')
    if not token:
        return web.Response(status=400, text="missing token")

    try:
        user_id = db.get_user_id_by_sub_token(token)
        if not user_id:
            return web.Response(status=404, text="subscription not found")

        configs, details = collect_user_configs(user_id)
        return web.json_response({
            "user_id": user_id,
            "count": len(configs),
            "configs": configs,
            "subscriptions": details,
        })
    except Exception:
        logger.error("Error in handle_raw_configs:\n" + traceback.format_exc())
        return web.json_response({"error": "internal_error"}, status=500)

async def handle_info(request: web.Request):
    if not check_api_key(request):
        return web.Response(status=403, text="forbidden")

    token = request.match_info.get('token')
    if not token:
        return web.Response(status=400, text="missing token")

    try:
        user_id = db.get_user_id_by_sub_token(token)
        if not user_id:
            return web.Response(status=404, text="user not found")

        user = db.get_user(user_id)
        subs = db.get_active_subscriptions(user_id)

        return web.json_response({
            "user_id": user_id,
            "username": user.get('username') if user else None,
            "balance": _to_number(user.get('balance', 0)) if user else 0,
            "subscriptions": [
                {
                    "id": s.get('id'),
                    "plan": s.get('plan_name') or s.get('plan_type'),
                    "remaining_volume": _to_number(s.get('remaining_volume')),
                    "end_date": str(s.get('end_date'))[:10] if s.get('end_date') else None,
                    "panel": s.get('panel_id'),
                    "email": s.get('email'),
                }
                for s in subs
            ],
        })
    except Exception:
        logger.error("Error in handle_info:\n" + traceback.format_exc())
        return web.json_response({"error": "internal_error"}, status=500)

async def handle_health(request: web.Request):
    return web.Response(text="ok")

async def handle_index(request: web.Request):
    return web.Response(
        text="🚀 Subscription API is running. Use /sub/TOKEN to get subscription.",
        content_type="text/plain",
        charset="utf-8"
    )

def collect_single_subscription(subscription_id: int):
    """کانفیگ‌ها و جزئیات فقط یک subscription خاص را برمی‌گرداند"""
    sub = db.get_subscription(subscription_id)
    if not sub:
        return None, None

    email = sub.get('email')
    panel_id = sub.get('panel_id')
    plan_type = sub.get('plan_type')

    links = []
    if email and panel_id and plan_type != 'manual':
        try:
            client = get_panel_client(panel_id)
            links = client.get_client_links(email) or []
        except Exception as e:
            logger.error(f"Error fetching links for subscription {subscription_id} (panel {panel_id}): {e}")
            links = []

        if not links:
            try:
                client_info = client.get_client_info(email)
                if client_info and client_info.get('subId'):
                    panel_base = client.panel_base
                    links = [f"{panel_base}/sub/{client_info.get('subId')}"]
            except Exception:
                pass

    try:
        manual_configs = db.get_manual_configs(subscription_id) or []
        manual_links = [mc['link'] for mc in manual_configs]
    except Exception as e:
        logger.error(f"Error fetching manual configs for subscription {subscription_id}: {e}")
        manual_links = []

    links = list(links) + manual_links

    panel_name = "Default panel"
    if panel_id:
        panel_manager = get_panel_manager()
        panel_data = panel_manager.get_panel(panel_id)
        if panel_data:
            panel_name = panel_data.get('name', panel_id)
    elif plan_type == 'manual':
        panel_name = "Manual"

    detail = {
        "subscription_id": subscription_id,
        "plan_name": sub.get('plan_name') or sub.get('plan_type') or "Plan",
        "remaining_volume": _to_number(sub.get('remaining_volume')),
        "end_date": str(sub.get('end_date'))[:10] if sub.get('end_date') else None,
        "start_date": str(sub.get('start_date'))[:10] if sub.get('start_date') else None,
        "panel_id": panel_id,
        "panel_name": panel_name,
        "email": email,
        "links": links,
    }
    return sub.get('user_id'), (links, detail)


async def handle_sub_single(request: web.Request):
    if not check_api_key(request):
        return web.Response(status=403, text="forbidden")

    token = request.match_info.get('token')
    if not token:
        return web.Response(status=400, text="missing token")

    try:
        subscription_id = db.get_subscription_id_by_link_token(token)
        if not subscription_id:
            return web.Response(status=404, text="subscription not found")

        user_id, result = collect_single_subscription(subscription_id)
        if not user_id:
            return web.Response(status=404, text="subscription not found")

        links, detail = result

        if request.query.get('details') == '1':
            return web.json_response({
                "user_id": user_id,
                "count": len(links),
                "subscription": detail,
            })

        if not links:
            return web.Response(text="", content_type="text/plain", charset="utf-8")

        raw = "\n".join(links)
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        return web.Response(text=encoded, content_type="text/plain", charset="utf-8")
    except Exception:
        logger.error("Error in handle_sub_single:\n" + traceback.format_exc())
        return web.json_response({"error": "internal_error"}, status=500)

def create_app():
    init_db()
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/sub/single/{token}', handle_sub_single)
    app.router.add_get('/sub/{token}', handle_sub)
    app.router.add_get('/api/raw/{token}', handle_raw_configs)
    app.router.add_get('/api/info/{token}', handle_info)
    logger.info("✅ Subscription API routes registered")
    return app

if __name__ == "__main__":
    protocol = "https" if ENABLE_SSL else "http"
    print(f"\n🚀 Subscription API starting on {protocol}://{HOST}:{PORT}")
    print(f"   - /sub/TOKEN   → get subscription link (base64)")
    print(f"   - /api/raw/TOKEN → get the raw list of configs")
    print(f"   - /api/info/TOKEN → get user info")
    if ENABLE_SSL:
        print(f"🔒 SSL enabled with cert: {SSL_CERT_FILE}")
    else:
        print("⚠️ SSL is disabled (no certificate files found)")
    print("=" * 50)

    if ENABLE_SSL:
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(SSL_CERT_FILE, SSL_KEY_FILE)
        web.run_app(create_app(), host=HOST, port=PORT, ssl_context=ssl_context)
    else:
        web.run_app(create_app(), host=HOST, port=PORT)
