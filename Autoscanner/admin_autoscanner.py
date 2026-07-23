# ====================== Admin: AutoScanner (Cloudflare IP Scanner) ======================
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import ContextTypes, ConversationHandler

from . import autoscanner_settings as settings
from . import cf_autoscanner

logger = logging.getLogger(__name__)

# ====================== Conversation States ======================
# We use the range starting from 100 so it doesn't conflict with the states in admin.py
AUTOSCANNER_TOKEN_INPUT = 100
AUTOSCANNER_ZONE_INPUT = 101
AUTOSCANNER_RECORD_INPUT = 102
AUTOSCANNER_RECORD_ZONE_SELECT = 103
AUTOSCANNER_INTERVAL_INPUT = 104
AUTOSCANNER_RECORD_BULK_ADD_INPUT = 105
AUTOSCANNER_RECORD_BULK_ADD_ZONE_SELECT = 106
AUTOSCANNER_RECORD_BULK_DELETE_INPUT = 107

# ====================== External deps (set from main.py) ======================
_is_admin_func = None
_get_main_menu_func = None


def set_is_admin(func):
    global _is_admin_func
    _is_admin_func = func


def set_get_main_menu(func):
    global _get_main_menu_func
    _get_main_menu_func = func


def is_admin(user_id: int) -> bool:
    if _is_admin_func:
        return _is_admin_func(user_id)
    return False


def get_main_menu():
    if _get_main_menu_func:
        return _get_main_menu_func()
    return None


# Text of the temporary "Cancel" reply-keyboard button shown while a text-input
# step of a conversation is in progress, replacing the main menu buttons.
CANCEL_BUTTON_TEXT = "❌ Cancel"


def _cancel_keyboard() -> ReplyKeyboardMarkup:
    """Reply keyboard with a single Cancel button, shown in place of the main menu
    buttons while the admin is expected to type something (instead of relying on
    the /cancel text command, which is easy to miss)."""
    return ReplyKeyboardMarkup([[KeyboardButton(CANCEL_BUTTON_TEXT)]], resize_keyboard=True)


# ====================== Helpers ======================
def _mask_token(token: str) -> str:
    if not token:
        return "❌ Not set"
    if len(token) <= 8:
        return "•" * len(token)
    return f"{token[:4]}{'•' * 8}{token[-4:]}"


def _progress_bar(percent: float, length: int = 12) -> str:
    percent = max(0, min(100, percent))
    filled = int(round(length * percent / 100))
    return "█" * filled + "░" * (length - filled)


def _fmt_node(nd: dict) -> str:
    status = nd.get("status")
    city = nd.get("city", "?")
    if status == "ok":
        ms = f"{nd['avg_ms']:.0f}ms" if nd.get("avg_ms") is not None else "-"
        result = f"{nd['ok_count']}/{nd['total_count']}" if nd.get("total_count") is not None else "-"
        return f"{city:<9}{ms:<7}{result}"
    elif status == "blocked":
        result = f"{nd['ok_count']}/{nd['total_count']}" if nd.get("total_count") is not None else "0/0"
        return f"{city:<9}{result}"
    elif status == "unresolved":
        return f"{city:<9}unresolved"
    else:
        return f"{city:<9}-"


def _fmt_node_grid(node_details: list, per_row: int = 2) -> List[str]:
    rows = []
    for i in range(0, len(node_details), per_row):
        pair = node_details[i:i + per_row]
        rows.append("  ".join(_fmt_node(n) for n in pair))
    return rows


class _ScanProgressState:
    """Live state of a scan run, rendered as a step checklist (➖ → ✅/❌) and
    edited in place on a single Telegram message — never sent as a new message."""

    def __init__(self, total_ports: int):
        self.total_ports = max(total_ports, 1)
        self.port_order: List[int] = []
        self.ports: Dict[int, dict] = {}
        # Keyed by "name:port" so a record only ever shows once, even though
        # it may receive multiple record_updated events (DNS update, then
        # again after the domain-health recheck for the champion record).
        self.records: Dict[str, dict] = {}
        # Keyed by domain name -> latest "checkhost_result" event with phase == "domain"
        self.domain_checks: Dict[str, dict] = {}
        self.started_at = time.monotonic()

    def _port_state(self, port: int) -> dict:
        if port not in self.ports:
            self.port_order.append(port)
            self.ports[port] = {
                "status": "pending",       # pending -> scanning -> done
                "round": (0, 1),
                "found_ip": None,
                "checkhost_node_details": None,
                "checkhost_passed": None,
                "checkhost_loss": None,
            }
        return self.ports[port]

    def percent(self) -> float:
        done = 0.0
        for port, p in self.ports.items():
            if p["status"] == "done":
                done += 1.0
            else:
                round_num, max_rounds = p["round"]
                done += min(round_num / max_rounds, 0.95) if max_rounds else 0
        return (done / self.total_ports) * 100

    def apply(self, event: dict):
        event_type = event.get("type")

        if event_type == "round":
            p = self._port_state(event["port"])
            p["round"] = (event["round"], event["max_rounds"])
            p["status"] = "scanning"

        elif event_type == "checkhost_result" and event.get("phase") == "candidate":
            p = self._port_state(event["port"])
            p["found_ip"] = event["ip"]
            p["checkhost_node_details"] = event["node_details"]
            p["checkhost_passed"] = event["passed"]
            p["checkhost_loss"] = event["loss_percent"]

        elif event_type == "checkhost_result" and event.get("phase") == "domain":
            # Full per-datacenter grid for the domain-level recheck (the
            # "champion" record). Stored separately so it can be rendered
            # under the matching record instead of collapsed into one line.
            self.domain_checks[event["name"]] = event

        elif event_type == "port_done":
            p = self._port_state(event["port"])
            p["status"] = "done"
            if event.get("ip"):
                p["found_ip"] = event["ip"]

        elif event_type == "record_updated":
            # Store keyed by name:port so a later event for the same record
            # (e.g. after the domain recheck finishes) replaces the earlier
            # one instead of appending a duplicate line.
            key = f"{event['name']}:{event['port']}"
            self.records[key] = event

    def render(self) -> str:
        percent = self.percent()
        elapsed = int(time.monotonic() - self.started_at)
        lines = [
            "*Scanning Cloudflare…*",
            "",
            f"`{_progress_bar(percent)}` {percent:.0f}%  ·  {elapsed}s",
        ]

        for port in self.port_order:
            p = self.ports[port]
            lines.append("")
            lines.append(f"*Port {port}*")

            if p["status"] == "done" or p["found_ip"]:
                step1 = f"✓ IP & latency scan → `{p['found_ip']}`" if p["found_ip"] else "✗ IP & latency scan → not found"
            elif p["status"] == "scanning":
                r, m = p["round"]
                step1 = f"… IP & latency scan (round {r}/{m})"
            else:
                step1 = "· IP & latency scan"
            lines.append(f"  {step1}")

            if p["checkhost_node_details"]:
                mark = "✓" if p["checkhost_passed"] else "✗"
                lines.append(f"  {mark} Iran datacenter test (loss {p['checkhost_loss']:.0f}%)")
                lines.append("```")
                lines.extend(_fmt_node_grid(p["checkhost_node_details"]))
                lines.append("```")
            else:
                lines.append("  · Iran datacenter test")

        if self.records:
            lines.append("")
            lines.append("*Records*")
            for key, event in self.records.items():
                lines.append("")
                mark = "✓" if event["updated"] else "·"
                ip_part = f" → `{event['new_ip']}`" if event.get("new_ip") else ""
                lines.append(f"{mark} `{key}`{ip_part}")
                lines.append(f"  {event['message']}")

                domain_check = self.domain_checks.get(event["name"])
                if domain_check:
                    dmark = "✓" if domain_check["passed"] else "✗"
                    lines.append("")
                    lines.append(f"  {dmark} Domain datacenter test (loss {domain_check['loss_percent']:.0f}%)")
                    if not domain_check["passed"] and domain_check.get("message"):
                        lines.append(f"  {domain_check['message']}")
                    lines.append("")
                    lines.append("```")
                    lines.extend(_fmt_node_grid(domain_check["node_details"]))
                    lines.append("```")

        return "\n".join(lines)


# Cloudflare-supported ports, grouped by protocol
HTTP_PORTS = {80, 8080, 8880, 2052, 2082, 2086, 2095}
HTTPS_PORTS = {443, 2053, 2083, 2087, 2096, 8443}


def _fmt_last_run() -> str:
    last_run = settings.get_last_run_at()
    if not last_run:
        return "Never run"
    delta = datetime.now(timezone.utc) - last_run
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    if hours > 0:
        return f"{hours} hours and {minutes} minutes ago"
    return f"{minutes} minutes ago"


def _format_records_by_protocol(records: list) -> str:
    """Groups records into HTTP / HTTPS / Other sections based on their port,
    instead of showing them all mixed together in one flat list."""
    if not records:
        return "  ❌ No records registered"

    def _line(r):
        zone = settings.get_zone(r["zone_id"])
        zone_label = zone["label"] if zone else "⚠️ Invalid Zone"
        return f"  • `{r['name']}:{r['port']}` ← {zone_label}"

    https_records = [r for r in records if r["port"] in HTTPS_PORTS]
    http_records = [r for r in records if r["port"] in HTTP_PORTS]
    other_records = [r for r in records if r["port"] not in HTTPS_PORTS and r["port"] not in HTTP_PORTS]

    sections = []
    if https_records:
        sections.append("🔒 HTTPS:\n" + "\n".join(_line(r) for r in https_records))
    if http_records:
        sections.append("🌐 HTTP:\n" + "\n".join(_line(r) for r in http_records))
    if other_records:
        sections.append("⚙️ Other:\n" + "\n".join(_line(r) for r in other_records))

    return "\n\n".join(sections)


def _main_text_and_keyboard():
    token_display = _mask_token(settings.get_cf_api_token())
    zones = settings.get_zones()
    records = settings.get_records()
    interval = settings.get_scan_interval_hours()
    enabled = settings.is_autoscanner_enabled()
    status = "✅ Enabled" if enabled else "❌ Disabled"

    records_display = _format_records_by_protocol(records)

    text = (
        f"🛰 AutoScanner Management (Cloudflare IP Scanner)\n\n"
        f"🔑 Cloudflare Token: {token_display}\n"
        f"🌐 Number of registered Zones: {len(zones)}\n"
        f"📋 Records:\n{records_display}\n\n"
        f"⏱ Auto-run interval: every {interval} hours\n"
        f"🔰 Status: {status}\n"
        f"🕓 Last run: {_fmt_last_run()}"
    )

    keyboard = [
        [InlineKeyboardButton("🔑 Set Cloudflare Token", callback_data="autoscanner_token_edit")],
        [InlineKeyboardButton("🌐 Manage Zones", callback_data="autoscanner_zones_menu")],
        [InlineKeyboardButton("📋 Manage Records", callback_data="autoscanner_records_menu")],
        [InlineKeyboardButton("⏱ Set Scan Interval", callback_data="autoscanner_interval_edit")],
        [InlineKeyboardButton(
            "🔴 Disable" if enabled else "🟢 Enable",
            callback_data="autoscanner_toggle"
        )],
        [InlineKeyboardButton("▶️ Run Scan Now", callback_data="autoscanner_run_menu")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back_to_main_menu")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def _safe_edit_markdown(query, text: str, reply_markup=None):
    """Edits the message with Markdown (so IP/domain can be copied with one tap); if a free-form
    label (e.g. a Zone name) has special Markdown characters that fail to parse, falls back to plain text."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.debug(f"Markdown edit failed, falling back to plain text: {e}")
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def _reply_with_autoscanner_menu(update: Update, message: str):
    """After a conversation ends (text input), restores the persistent main menu keyboard
    (replacing the temporary Cancel button) and shows both the result message and the
    AutoScanner menu (with buttons) so the user doesn't have to start over from the main menu."""
    text, reply_markup = _main_text_and_keyboard()
    await update.message.reply_text(message, reply_markup=get_main_menu())
    try:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.debug(f"Markdown reply failed, falling back to plain text: {e}")
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)


async def admin_autoscanner_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔️ You do not have admin access.")
        return
    text, reply_markup = _main_text_and_keyboard()
    await _safe_edit_markdown(query, text, reply_markup)


# ====================== Cloudflare Token ======================
async def autoscanner_token_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "🔑 Set Cloudflare API Token\n\n"
        f"Current value: {_mask_token(settings.get_cf_api_token())}",
        parse_mode=None
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Please send the new Cloudflare API token:",
        reply_markup=_cancel_keyboard()
    )
    return AUTOSCANNER_TOKEN_INPUT


async def autoscanner_token_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ("/cancel", CANCEL_BUTTON_TEXT):
        await _reply_with_autoscanner_menu(update, "❌ Operation cancelled.")
        return ConversationHandler.END

    if not text:
        await update.message.reply_text("❌ The token cannot be empty. Please send it again:")
        return AUTOSCANNER_TOKEN_INPUT

    settings.set_cf_api_token(text)
    await _reply_with_autoscanner_menu(update, "✅ Cloudflare token saved successfully.")
    return ConversationHandler.END


# ====================== Zones Management ======================
def _zones_text_and_keyboard():
    zones = settings.get_zones()
    if zones:
        lines = [f"{i+1}. {z['label']} — `{z['id']}`" for i, z in enumerate(zones)]
        current = "\n".join(lines)
    else:
        current = "❌ No zones registered."

    text = f"🌐 Cloudflare Zones Management\n\n{current}"

    keyboard = []
    for z in zones:
        keyboard.append([InlineKeyboardButton(f"🗑 Delete {z['label']}", callback_data=f"autoscanner_zone_del_{z['id']}")])
    keyboard.append([InlineKeyboardButton("➕ Add New Zone", callback_data="autoscanner_zone_add")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_autoscanner_menu")])
    return text, InlineKeyboardMarkup(keyboard)


async def autoscanner_zones_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    text, reply_markup = _zones_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def autoscanner_zone_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    await query.edit_message_text(
        "➕ Add New Zone\n\n"
        "Please send the Zone ID. To set a custom display name, "
        "write it after the Zone ID separated by a space:\n\n"
        "Example:\n"
        "`a1b2c3d4e5f6...` \n"
        "or\n"
        "`a1b2c3d4e5f6... bazargarni.ir`",
        parse_mode='Markdown'
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⌨️ Waiting for the Zone ID.",
        reply_markup=_cancel_keyboard()
    )
    return AUTOSCANNER_ZONE_INPUT


async def autoscanner_zone_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ("/cancel", CANCEL_BUTTON_TEXT):
        await _reply_with_autoscanner_menu(update, "❌ Operation cancelled.")
        return ConversationHandler.END

    parts = text.split(None, 1)
    zone_id = parts[0].strip()
    label = parts[1].strip() if len(parts) > 1 else zone_id

    if not zone_id:
        await update.message.reply_text("❌ Invalid Zone ID. Please send it again:")
        return AUTOSCANNER_ZONE_INPUT

    success = settings.add_zone(zone_id, label)
    if success:
        await _reply_with_autoscanner_menu(update, f"✅ Zone «{label}» added successfully.")
    else:
        await _reply_with_autoscanner_menu(update, "❌ This Zone ID is already registered.")
    return ConversationHandler.END


async def autoscanner_zone_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    zone_id = query.data.replace("autoscanner_zone_del_", "")
    success = settings.remove_zone(zone_id)
    if success:
        await query.answer("✅ Zone deleted (records linked to it were also deleted).")
    else:
        await query.answer("❌ Zone not found.", show_alert=True)

    text, reply_markup = _zones_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ====================== Records Management ======================
def _records_text_and_keyboard():
    records = settings.get_records()
    if records:
        lines = []
        for i, r in enumerate(records):
            zone = settings.get_zone(r["zone_id"])
            zone_label = zone["label"] if zone else "⚠️ Invalid Zone"
            lines.append(f"{i+1}. `{r['name']}:{r['port']}` ← {zone_label}")
        current = "\n".join(lines)
    else:
        current = "❌ No records registered."

    text = (
        f"📋 Records Management\n\n{current}\n\n"
        f"Each record is registered in the following format:\n"
        f"`domain.example.com:443`"
    )

    keyboard = []
    for i, r in enumerate(records):
        keyboard.append([InlineKeyboardButton(
            f"🗑 Delete {r['name']}:{r['port']}", callback_data=f"autoscanner_record_del_{i}"
        )])
    keyboard.append([InlineKeyboardButton("➕ Add New Record", callback_data="autoscanner_record_add")])
    keyboard.append([
        InlineKeyboardButton("📥 Bulk Add", callback_data="autoscanner_record_bulk_add"),
        InlineKeyboardButton("🗑 Bulk Delete", callback_data="autoscanner_record_bulk_delete"),
    ])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_autoscanner_menu")])
    return text, InlineKeyboardMarkup(keyboard)


async def autoscanner_records_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    text, reply_markup = _records_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def autoscanner_record_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    if not settings.get_zones():
        await query.edit_message_text(
            "❌ You must register at least one Zone first.\n\n"
            "Add a Zone from the «Manage Zones» menu.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="autoscanner_records_menu")]
            ])
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "➕ Add New Record\n\n"
        "Please send it in this format:\n"
        "`domain.example.com:443`\n\n"
        "Example:\n"
        "`goip44.bazargarni.ir:443`",
        parse_mode='Markdown'
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⌨️ Waiting for the record.",
        reply_markup=_cancel_keyboard()
    )
    return AUTOSCANNER_RECORD_INPUT


async def autoscanner_record_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ("/cancel", CANCEL_BUTTON_TEXT):
        await _reply_with_autoscanner_menu(update, "❌ Operation cancelled.")
        return ConversationHandler.END

    if ":" not in text:
        await update.message.reply_text(
            "❌ Invalid format. It must be in the form `domain:port`.\n"
            "Example: `goip44.bazargarni.ir:443`\n\n"
            "Please send it again:",
            parse_mode='Markdown'
        )
        return AUTOSCANNER_RECORD_INPUT

    name, _, port_str = text.rpartition(":")
    name = name.strip().lower()
    port_str = port_str.strip()

    if not name or not port_str.isdigit():
        await update.message.reply_text(
            "❌ Invalid format. It must be in the form `domain:port` (port must be numeric only).\n"
            "Please send it again:",
            parse_mode='Markdown'
        )
        return AUTOSCANNER_RECORD_INPUT

    port = int(port_str)
    if port < 1 or port > 65535:
        await update.message.reply_text("❌ Invalid port number. Please send it again:")
        return AUTOSCANNER_RECORD_INPUT

    context.user_data['autoscanner_new_record'] = {"name": name, "port": port}

    zones = settings.get_zones()
    keyboard = [
        [InlineKeyboardButton(z['label'], callback_data=f"autoscanner_recordzone_{z['id']}")]
        for z in zones
    ]
    await update.message.reply_text(f"✅ Record: `{name}:{port}`", parse_mode='Markdown', reply_markup=get_main_menu())
    await update.message.reply_text(
        "Now specify which Zone this record belongs to:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AUTOSCANNER_RECORD_ZONE_SELECT


async def autoscanner_record_zone_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    zone_id = query.data.replace("autoscanner_recordzone_", "")
    zone = settings.get_zone(zone_id)
    new_record = context.user_data.get('autoscanner_new_record')

    if not zone or not new_record:
        await query.edit_message_text("❌ Error! Please try again.")
        return ConversationHandler.END

    success = settings.add_record(new_record["name"], new_record["port"], zone_id)
    context.user_data.pop('autoscanner_new_record', None)

    if success:
        result_msg = f"✅ Record «{new_record['name']}:{new_record['port']}» linked and saved to Zone «{zone['label']}»."
    else:
        result_msg = "❌ This record is already registered."

    text, reply_markup = _main_text_and_keyboard()
    await _safe_edit_markdown(query, f"{result_msg}\n\n{text}", reply_markup)
    return ConversationHandler.END


async def autoscanner_record_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    idx = int(query.data.replace("autoscanner_record_del_", ""))
    success = settings.remove_record(idx)
    if success:
        await query.answer("✅ Record deleted.")
    else:
        await query.answer("❌ This item is no longer valid.", show_alert=True)

    text, reply_markup = _records_text_and_keyboard()
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ====================== Bulk Add Records ======================
def _parse_bulk_lines(text: str):
    """Parses multi-line `domain:port` input.
    Returns (parsed, errors) where parsed is a list of {"name","port"} dicts
    and errors is a list of human-readable messages for bad lines."""
    parsed = []
    errors = []
    seen = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            errors.append(f"`{line}` — missing `:port`")
            continue
        name, _, port_str = line.rpartition(":")
        name = name.strip().lower()
        port_str = port_str.strip()
        if not name or not port_str.isdigit():
            errors.append(f"`{line}` — invalid format")
            continue
        port = int(port_str)
        if port < 1 or port > 65535:
            errors.append(f"`{line}` — invalid port")
            continue
        key = f"{name}:{port}"
        if key in seen:
            errors.append(f"`{line}` — duplicate in list")
            continue
        seen.add(key)
        parsed.append({"name": name, "port": port})
    return parsed, errors


async def autoscanner_record_bulk_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    if not settings.get_zones():
        await query.edit_message_text(
            "❌ You must register at least one Zone first.\n\n"
            "Add a Zone from the «Manage Zones» menu.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="autoscanner_records_menu")]
            ])
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "📥 Bulk Add Records\n\n"
        "Send one record per line, in the format `domain:port`:\n\n"
        "Example:\n"
        "`goip43.example.ir:443`\n"
        "`goip53.example.ir:2053`\n"
        "`goip83.example.ir:2083`\n\n"
        "All records you send will be linked to the same Zone, which you'll pick next.",
        parse_mode='Markdown'
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⌨️ Waiting for the list of records.",
        reply_markup=_cancel_keyboard()
    )
    return AUTOSCANNER_RECORD_BULK_ADD_INPUT


async def autoscanner_record_bulk_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ("/cancel", CANCEL_BUTTON_TEXT):
        await _reply_with_autoscanner_menu(update, "❌ Operation cancelled.")
        return ConversationHandler.END

    parsed, errors = _parse_bulk_lines(text)

    if not parsed:
        msg = "❌ No valid records found."
        if errors:
            msg += "\n\n" + "\n".join(errors[:20])
        msg += "\n\nPlease send the list again:"
        await update.message.reply_text(msg, parse_mode='Markdown')
        return AUTOSCANNER_RECORD_BULK_ADD_INPUT

    context.user_data['autoscanner_bulk_records'] = parsed

    zones = settings.get_zones()
    keyboard = [
        [InlineKeyboardButton(z['label'], callback_data=f"autoscanner_bulkzone_{z['id']}")]
        for z in zones
    ]
    lines_preview = "\n".join(f"`{r['name']}:{r['port']}`" for r in parsed)
    warn = ""
    if errors:
        warn = "\n\n⚠️ Skipped lines:\n" + "\n".join(errors[:20])

    await update.message.reply_text(
        f"✅ Parsed {len(parsed)} record(s):\n{lines_preview}{warn}",
        parse_mode='Markdown',
        reply_markup=get_main_menu()
    )
    await update.message.reply_text(
        "Now specify which Zone these records belong to:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AUTOSCANNER_RECORD_BULK_ADD_ZONE_SELECT


async def autoscanner_record_bulk_zone_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    zone_id = query.data.replace("autoscanner_bulkzone_", "")
    zone = settings.get_zone(zone_id)
    records = context.user_data.get('autoscanner_bulk_records')

    if not zone or not records:
        await query.edit_message_text("❌ Error! Please try again.")
        return ConversationHandler.END

    added, skipped = [], []
    for r in records:
        if settings.add_record(r["name"], r["port"], zone_id):
            added.append(r)
        else:
            skipped.append(r)
    context.user_data.pop('autoscanner_bulk_records', None)

    lines = [f"📥 Bulk add finished for Zone «{zone['label']}»:", ""]
    lines.append(f"✅ Added: {len(added)}")
    if added:
        lines.extend(f"  • `{r['name']}:{r['port']}`" for r in added)
    if skipped:
        lines.append(f"⚠️ Already existed / skipped: {len(skipped)}")
        lines.extend(f"  • `{r['name']}:{r['port']}`" for r in skipped)
    result_msg = "\n".join(lines)

    text, reply_markup = _main_text_and_keyboard()
    await _safe_edit_markdown(query, f"{result_msg}\n\n{text}", reply_markup)
    return ConversationHandler.END


# ====================== Bulk Delete Records ======================
async def autoscanner_record_bulk_delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    records = settings.get_records()
    if not records:
        await query.edit_message_text(
            "❌ No records registered.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back", callback_data="autoscanner_records_menu")]
            ])
        )
        return ConversationHandler.END

    records_list = "\n".join(f"`{r['name']}:{r['port']}`" for r in records)

    await query.edit_message_text(
        "🗑 Bulk Delete Records\n\n"
        "Send one record per line, in the format `domain:port`, matching existing records exactly:\n\n"
        "Current records:\n"
        f"{records_list}",
        parse_mode='Markdown'
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="⌨️ Waiting for the list of records.",
        reply_markup=_cancel_keyboard()
    )
    return AUTOSCANNER_RECORD_BULK_DELETE_INPUT


async def autoscanner_record_bulk_delete_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ("/cancel", CANCEL_BUTTON_TEXT):
        await _reply_with_autoscanner_menu(update, "❌ Operation cancelled.")
        return ConversationHandler.END

    parsed, errors = _parse_bulk_lines(text)

    if not parsed:
        msg = "❌ No valid records found."
        if errors:
            msg += "\n\n" + "\n".join(errors[:20])
        msg += "\n\nPlease send the list again:"
        await update.message.reply_text(msg, parse_mode='Markdown')
        return AUTOSCANNER_RECORD_BULK_DELETE_INPUT

    all_records = settings.get_records()
    key_to_idx = {_record_key(r): i for i, r in enumerate(all_records)}

    to_delete_idx = []
    not_found = []
    for r in parsed:
        key = f"{r['name']}:{r['port']}"
        idx = key_to_idx.get(key)
        if idx is None:
            not_found.append(key)
        else:
            to_delete_idx.append((idx, key))

    # Remove from highest index to lowest so earlier indices stay valid
    deleted = []
    for idx, key in sorted(to_delete_idx, key=lambda x: x[0], reverse=True):
        if settings.remove_record(idx):
            deleted.append(key)
        else:
            not_found.append(key)

    lines = ["🗑 Bulk delete finished:", "", f"✅ Deleted: {len(deleted)}"]
    if deleted:
        lines.extend(f"  • `{k}`" for k in sorted(deleted))
    if not_found:
        lines.append(f"⚠️ Not found: {len(not_found)}")
        lines.extend(f"  • `{k}`" for k in not_found)
    if errors:
        lines.append(f"⚠️ Skipped lines: {len(errors)}")
        lines.extend(errors[:20])

    text, reply_markup = _main_text_and_keyboard()
    await update.message.reply_text("\n".join(lines), parse_mode='Markdown', reply_markup=get_main_menu())
    try:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.debug(f"Markdown reply failed, falling back to plain text: {e}")
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=None)
    return ConversationHandler.END


# ====================== Interval Setting ======================
async def autoscanner_interval_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return ConversationHandler.END

    current = settings.get_scan_interval_hours()
    await query.edit_message_text(
        f"⏱ Set Auto-Run Interval for Scanner\n\n"
        f"Current value: every {current} hours",
        parse_mode=None
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Please enter the new value in hours (e.g. 6):",
        reply_markup=_cancel_keyboard()
    )
    return AUTOSCANNER_INTERVAL_INPUT


async def autoscanner_interval_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ("/cancel", CANCEL_BUTTON_TEXT):
        await _reply_with_autoscanner_menu(update, "❌ Operation cancelled.")
        return ConversationHandler.END

    try:
        hours = int(text)
        if hours < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter an integer greater than or equal to 1:")
        return AUTOSCANNER_INTERVAL_INPUT

    settings.set_scan_interval_hours(hours)
    await _reply_with_autoscanner_menu(update, f"✅ Scanner interval changed to {hours} hours.")
    return ConversationHandler.END


# ====================== Enable / Disable Toggle ======================
async def autoscanner_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔️ No access.", show_alert=True)
        return

    new_value = not settings.is_autoscanner_enabled()

    if new_value and (not settings.get_cf_api_token() or not settings.get_records()):
        await query.answer(
            "⚠️ To enable, you must first set a Cloudflare token and register at least one record.",
            show_alert=True
        )
        return

    settings.set_autoscanner_enabled(new_value)
    await query.answer("✅ Status updated.")

    text, reply_markup = _main_text_and_keyboard()
    await _safe_edit_markdown(query, text, reply_markup)
# ====================== Manual Run ======================
_MIN_EDIT_INTERVAL = 2.0  # Minimum interval between consecutive edits to the same message (seconds)


# ====================== Manual Run (with record selection) ======================
_MIN_EDIT_INTERVAL = 2.0  # Minimum interval between consecutive edits to the same message (seconds)


def _record_key(r: dict) -> str:
    return f"{r['name']}:{r['port']}"


def _run_selection_text_and_keyboard(user_data: dict):
    records = settings.get_records()
    selection = user_data.setdefault('autoscanner_run_selection', {_record_key(r) for r in records})

    if records:
        text = "▶️ Run Immediate Scan\n\nSelect the records you want to scan right now:"
    else:
        text = "▶️ Run Immediate Scan\n\n❌ No records registered."

    keyboard = []
    for i, r in enumerate(records):
        key = _record_key(r)
        check = "☑️" if key in selection else "⬜️"
        keyboard.append([InlineKeyboardButton(f"{check} {key}", callback_data=f"autoscanner_runsel_toggle_{i}")])

    if records:
        keyboard.append([
            InlineKeyboardButton("✅ Select All", callback_data="autoscanner_runsel_all"),
            InlineKeyboardButton("🚫 None", callback_data="autoscanner_runsel_none"),
        ])
        keyboard.append([InlineKeyboardButton("▶️ Start Scan", callback_data="autoscanner_runsel_start")])

    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_autoscanner_menu")])
    return text, InlineKeyboardMarkup(keyboard)


async def autoscanner_run_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    # Every time this menu is opened, reset the selection to "all"
    context.user_data['autoscanner_run_selection'] = {_record_key(r) for r in settings.get_records()}
    text, reply_markup = _run_selection_text_and_keyboard(context.user_data)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def autoscanner_runsel_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    idx = int(query.data.replace("autoscanner_runsel_toggle_", ""))
    records = settings.get_records()
    if idx < 0 or idx >= len(records):
        await query.answer("❌ This item is no longer valid.", show_alert=True)
        return

    key = _record_key(records[idx])
    selection = context.user_data.setdefault('autoscanner_run_selection', {_record_key(r) for r in records})
    if key in selection:
        selection.discard(key)
    else:
        selection.add(key)

    text, reply_markup = _run_selection_text_and_keyboard(context.user_data)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def autoscanner_runsel_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ All selected.")
    if not is_admin(query.from_user.id):
        return
    context.user_data['autoscanner_run_selection'] = {_record_key(r) for r in settings.get_records()}
    text, reply_markup = _run_selection_text_and_keyboard(context.user_data)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def autoscanner_runsel_none(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🚫 Selection cleared.")
    if not is_admin(query.from_user.id):
        return
    context.user_data['autoscanner_run_selection'] = set()
    text, reply_markup = _run_selection_text_and_keyboard(context.user_data)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)


async def autoscanner_runsel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer()
        return

    all_records = settings.get_records()
    selection = context.user_data.get('autoscanner_run_selection', {_record_key(r) for r in all_records})
    selected_records = [r for r in all_records if _record_key(r) in selection]

    if not selected_records:
        await query.answer("⚠️ At least one record must be selected.", show_alert=True)
        return

    await query.answer("⏳ Running scan; this may take a few minutes...")

    total_ports = len({r["port"] for r in selected_records}) or 1
    state = _ScanProgressState(total_ports)

    await query.edit_message_text(state.render(), parse_mode='Markdown')

    loop = asyncio.get_running_loop()
    last_edit_ts = 0.0
    edit_lock = asyncio.Lock()

    async def _apply_edit(force: bool = False):
        nonlocal last_edit_ts
        async with edit_lock:
            now = time.monotonic()
            if not force and (now - last_edit_ts) < _MIN_EDIT_INTERVAL:
                return
            last_edit_ts = now
            try:
                # Always rewrite the same previous message, never send a new one
                await query.edit_message_text(state.render(), parse_mode='Markdown')
            except Exception as e:
                # e.g. when the message text hasn't changed (BadRequest: Message is not modified)
                logger.debug(f"progress edit skipped: {e}")

    def progress_callback(event: dict):
        # This function is called from a separate thread (asyncio.to_thread)
        state.apply(event)
        force = event.get("type") in ("port_done", "checkhost_result", "record_updated")
        asyncio.run_coroutine_threadsafe(_apply_edit(force=force), loop)

    try:
        summary = await asyncio.to_thread(cf_autoscanner.run_scan_cycle, progress_callback, selected_records)
    except Exception as e:
        logger.error(f"Error running manual autoscanner cycle: {e}")
        await query.edit_message_text(f"❌ Error running scanner: {e}")
        return

    settings.set_last_run_at()
    text = _format_summary(summary)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="admin_autoscanner_menu")]
    ])

    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown')
    except Exception as e:
        # If the Cloudflare error text has special Markdown characters that fail to parse, send it without formatting
        logger.warning(f"Markdown parse failed for summary, sending as plain text: {e}")
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=None)


def _format_summary(summary: dict) -> str:
    if not summary.get("ok", True) and summary.get("error"):
        return f"*Scan stopped*\n{summary['error']}"

    lines = ["*Scan Result*", ""]
    for p in summary.get("ports_scanned", []):
        if p["found"]:
            lines.append(f"✓ Port {p['port']}: best IP → `{p['ip']}`")
        else:
            lines.append(f"✗ Port {p['port']}: no verified IP found")

    if summary.get("records"):
        lines.append("")
        lines.append("*Records*")
        for r in summary["records"]:
            lines.append("")
            mark = "✓" if r["updated"] else "·"
            ip_part = f" → `{r['new_ip']}`" if r.get("new_ip") else ""
            lines.append(f"{mark} `{r['name']}:{r['port']}`{ip_part}")
            lines.append(f"  {r['message']}")

            if r.get("domain_node_details"):
                dmark = "✓" if r.get("domain_passed") else "✗"
                loss = r.get("domain_loss_percent")
                loss_str = f"{loss:.0f}%" if loss is not None else "-"
                lines.append("")
                lines.append(f"  {dmark} Domain datacenter test (loss {loss_str})")
                if not r.get("domain_passed") and r.get("domain_message"):
                    lines.append(f"  {r['domain_message']}")
                lines.append("")
                lines.append("```")
                lines.extend(_fmt_node_grid(r["domain_node_details"]))
                lines.append("```")

    lines.append("")
    lines.append("*Scan complete*")

    return "\n".join(lines)


# ====================== Scheduled Job (called by job_queue in main.py) ======================
async def autoscanner_scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    """
    This function should be called every 30 minutes (or some short interval) by job_queue.
    It figures out on its own whether it's actually time to run based on scan_interval_hours.
    """
    if not settings.is_due_for_run():
        return

    logger.info("AutoScanner: periodic run time reached, starting scan...")
    try:
        summary = await asyncio.to_thread(cf_autoscanner.run_scan_cycle)
    except Exception as e:
        logger.error(f"Error in scheduled autoscanner job: {e}")
        return
    finally:
        settings.set_last_run_at()

    updated = [r for r in summary.get("records", []) if r.get("updated")]
    needs_attention = [r for r in summary.get("records", []) if r.get("domain_needs_attention")]
    logger.info(f"AutoScanner: periodic scan finished. {len(updated)} record(s) updated, "
                f"{len(needs_attention)} needing attention.")

    # If you want the result to also be sent to the log group (optional):
    try:
        from logger_bot import log_system_error
        if updated:
            detail = "\n".join(f"{r['name']}:{r['port']} → {r.get('new_ip')}" for r in updated)
            await log_system_error(
                context.bot,
                "🛰 AutoScanner: periodic scan performed",
                context=f"Updated records:\n{detail}"
            )
        if needs_attention:
            detail = "\n".join(f"{r['name']}:{r['port']} — {r['domain_message']}" for r in needs_attention)
            await log_system_error(
                context.bot,
                "⚠️ AutoScanner: domain needs attention",
                context=detail
            )
    except Exception as e:
        logger.error(f"Error logging autoscanner result: {e}")
