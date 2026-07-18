#!/usr/bin/env python3
# sub_api.py - Web Service for Subscription Links

import os
import sys
import json
import base64
import logging
from datetime import datetime
from aiohttp import web
from pathlib import Path

# Add current directory to path
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

# ============================================================
# ========== Settings ==========
# ============================================================

API_KEY = os.environ.get("SUB_API_KEY", "")
HOST = os.environ.get("SUB_HOST", "0.0.0.0")
PORT = int(os.environ.get("SUB_PORT", 2053))

db: Database = None


def init_db():
    """Connect to the database"""
    global db
    if not config.load():
        raise RuntimeError("Bot configuration not found — please run/set up the main bot first.")
    db = Database(config.get_db_config())
    logger.info("✅ Database connection established for sub_api")


def check_api_key(request: web.Request) -> bool:
    """Check the API key (if configured)"""
    if not API_KEY:
        return True
    return request.headers.get("X-API-Key") == API_KEY


def collect_user_configs(user_id: int):
    """Collect all of the user's active configs from every panel"""
    subs = db.get_active_subscriptions(user_id)
    configs = []
    details = []

    for sub in subs:
        email = sub.get('email')
        panel_id = sub.get('panel_id')
        if not email:
            continue

        try:
            client = get_panel_client(panel_id) if panel_id else get_panel_client()
            links = client.get_client_links(email) or []
        except Exception as e:
            logger.error(f"Error fetching links for subscription {sub.get('id')} (panel {panel_id}): {e}")
            links = []

        # If no links, try to build one from subId
        if not links:
            try:
                client_info = client.get_client_info(email)
                if client_info and client_info.get('subId'):
                    panel_base = client.panel_base
                    links = [f"{panel_base}/sub/{client_info.get('subId')}"]
            except Exception:
                pass

        configs.extend(links)

        panel_name = "Default panel"
        if panel_id:
            panel_manager = get_panel_manager()
            panel_data = panel_manager.get_panel(panel_id)
            if panel_data:
                panel_name = panel_data.get('name', panel_id)

        details.append({
            "subscription_id": sub.get('id'),
            "plan_name": sub.get('plan_name') or sub.get('plan_type') or "Plan",
            "remaining_volume": sub.get('remaining_volume'),
            "end_date": str(sub.get('end_date'))[:10] if sub.get('end_date') else None,
            "start_date": str(sub.get('start_date'))[:10] if sub.get('start_date') else None,
            "panel_id": panel_id,
            "panel_name": panel_name,
            "email": email,
            "links": links,
        })

    return configs, details


# ============================================================
# ========== API Handlers ==========
# ============================================================

async def handle_sub(request: web.Request):
    """Get subscription link using the user's token"""
    if not check_api_key(request):
        return web.Response(status=403, text="forbidden")

    token = request.match_info.get('token')
    if not token:
        return web.Response(status=400, text="missing token")

    user_id = db.get_user_id_by_sub_token(token)
    if not user_id:
        return web.Response(status=404, text="subscription not found")

    configs, details = collect_user_configs(user_id)

    # Details mode → for HTML rendering by index.php
    if request.query.get('details') == '1':
        return web.json_response({
            "user_id": user_id,
            "count": len(configs),
            "subscriptions": details,
        })

    # Default mode → standard subscription format (base64) for direct Import
    if not configs:
        return web.Response(
            text="",
            content_type="text/plain",
            charset="utf-8"
        )

    raw = "\n".join(configs)
    encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
    return web.Response(text=encoded, content_type="text/plain", charset="utf-8")


async def handle_raw_configs(request: web.Request):
    """Get the raw list of configs (no base64) for use in index.php"""
    if not check_api_key(request):
        return web.Response(status=403, text="forbidden")

    token = request.match_info.get('token')
    if not token:
        return web.Response(status=400, text="missing token")

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


async def handle_info(request: web.Request):
    """Get user info based on the token"""
    if not check_api_key(request):
        return web.Response(status=403, text="forbidden")

    token = request.match_info.get('token')
    if not token:
        return web.Response(status=400, text="missing token")

    user_id = db.get_user_id_by_sub_token(token)
    if not user_id:
        return web.Response(status=404, text="user not found")

    user = db.get_user(user_id)
    subs = db.get_active_subscriptions(user_id)

    return web.json_response({
        "user_id": user_id,
        "username": user.get('username') if user else None,
        "balance": user.get('balance', 0) if user else 0,
        "subscriptions": [
            {
                "id": s.get('id'),
                "plan": s.get('plan_name') or s.get('plan_type'),
                "remaining_volume": s.get('remaining_volume'),
                "end_date": str(s.get('end_date'))[:10] if s.get('end_date') else None,
                "panel": s.get('panel_id'),
                "email": s.get('email'),
            }
            for s in subs
        ],
    })


async def handle_health(request: web.Request):
    """Health check for the service"""
    return web.Response(text="ok")


async def handle_index(request: web.Request):
    """Home page"""
    return web.Response(
        text="🚀 Subscription API is running. Use /sub/TOKEN to get subscription.",
        content_type="text/plain",
        charset="utf-8"
    )


# ============================================================
# ========== Build App ==========
# ============================================================

def create_app():
    init_db()
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/sub/{token}', handle_sub)
    app.router.add_get('/api/raw/{token}', handle_raw_configs)
    app.router.add_get('/api/info/{token}', handle_info)
    logger.info("✅ Subscription API routes registered")
    return app


if __name__ == "__main__":
    print(f"\n🚀 Subscription API starting on http://{HOST}:{PORT}")
    print(f"   - /sub/TOKEN   → get subscription link (base64)")
    print(f"   - /api/raw/TOKEN → get the raw list of configs")
    print(f"   - /api/info/TOKEN → get user info")
    print("=" * 50)
    
    web.run_app(create_app(), host=HOST, port=PORT)
