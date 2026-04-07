#!/usr/bin/env python3
"""
Automation Engine — executes action chains from the Automation Builder UI.

Called by the Flask route POST /automations/execute with a JSON payload:
{
    "automation_id": "uuid",
    "actions": [{"type": "discord_notify", "config": {"channel": "...", "message": "..."}}],
    "trigger_data": {"name": "John", "email": "john@example.com"},
    "dry_run": false
}

Each action type maps to an executor function that receives the action config
and trigger data, performs the action, and returns a result dict.

Variable interpolation: {{trigger.field_name}} in config values gets replaced
with the corresponding value from trigger_data.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("automation-engine")


# ─── Variable Interpolation ───

def interpolate(template: str, trigger_data: dict) -> str:
    """Replace {{trigger.field}} with values from trigger_data."""
    def replacer(match: re.Match) -> str:
        field = match.group(1)
        return str(trigger_data.get(field, match.group(0)))
    return re.sub(r"\{\{trigger\.(\w+)\}\}", replacer, str(template))


def interpolate_config(config: dict, trigger_data: dict) -> dict:
    """Deep-interpolate all string values in a config dict."""
    result = {}
    for key, value in config.items():
        if isinstance(value, str):
            result[key] = interpolate(value, trigger_data)
        elif isinstance(value, dict):
            result[key] = interpolate_config(value, trigger_data)
        elif isinstance(value, list):
            result[key] = [
                interpolate(v, trigger_data) if isinstance(v, str) else v
                for v in value
            ]
        else:
            result[key] = value
    return result


# ─── Action Executors ───

def execute_discord_notify(config: dict, trigger_data: dict, dry_run: bool = False) -> dict:
    """Send a Discord message to a channel."""
    from execution.ghl_automations import discord_send

    channel = config.get("channel", "")
    message = config.get("message", "")

    if not channel:
        return {"ok": False, "error": "No channel specified"}

    if dry_run:
        return {"ok": True, "dry_run": True, "channel": channel, "message": message[:100]}

    # Build embed from message template
    embed = {
        "title": "Automation Notification",
        "description": message,
        "color": 0x5865F2,
        "footer": {"text": "Automation Engine"},
    }

    try:
        result = discord_send(channel, embed=embed)
        return {"ok": True, "discord_message_id": result.get("id")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def execute_ghl_create_contact(config: dict, trigger_data: dict, dry_run: bool = False) -> dict:
    """Create or update a GHL contact."""
    from execution.ghl_client import create_or_update_contact

    email = config.get("email_field", "")
    name = config.get("name_field", "")
    phone = config.get("phone_field", "")
    tags_str = config.get("tags", "")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

    if not email:
        return {"ok": False, "error": "No email provided"}

    if dry_run:
        return {"ok": True, "dry_run": True, "email": email, "name": name}

    try:
        result = create_or_update_contact(
            email=email,
            first_name=name,
            phone=phone,
            tags=tags,
            source="automation-engine",
        )
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


def execute_http_request(config: dict, trigger_data: dict, dry_run: bool = False) -> dict:
    """Make an HTTP request."""
    method = config.get("method", "POST").upper()
    url = config.get("url", "")
    body = config.get("body", "")
    headers_raw = config.get("headers", {})

    if not url:
        return {"ok": False, "error": "No URL specified"}

    # SSRF prevention
    blocked = ["localhost", "127.", "0.0.0.", "10.", "192.168.", "169.254."]
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if any(parsed.hostname and parsed.hostname.startswith(b) for b in blocked):
            return {"ok": False, "error": "Blocked: internal/private URL"}
    except Exception:
        pass

    if dry_run:
        return {"ok": True, "dry_run": True, "method": method, "url": url}

    try:
        data = body.encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if isinstance(headers_raw, dict):
            for k, v in headers_raw.items():
                req.add_header(k, str(v))

        resp = urllib.request.urlopen(req, timeout=15)
        resp_body = resp.read().decode("utf-8", errors="replace")[:500]
        return {"ok": True, "status": resp.status, "body": resp_body}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": e.read().decode("utf-8", errors="replace")[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def execute_google_sheets_append(config: dict, trigger_data: dict, dry_run: bool = False) -> dict:
    """Append a row to a Google Sheet."""
    sheet_id = config.get("sheet_id", "")
    worksheet = config.get("worksheet", "Sheet1")
    values_raw = config.get("values", "")

    if not sheet_id:
        return {"ok": False, "error": "No sheet_id specified"}

    # Parse values (one per line)
    values = [v.strip() for v in values_raw.split("\n") if v.strip()]

    if dry_run:
        return {"ok": True, "dry_run": True, "sheet_id": sheet_id, "values": values}

    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds_path = PROJECT_ROOT / "service_account.json"
        creds = Credentials.from_service_account_file(
            str(creds_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        service = build("sheets", "v4", credentials=creds)

        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"'{worksheet}'!A:Z",
            valueInputOption="USER_ENTERED",
            body={"values": [values]},
        ).execute()

        return {"ok": True, "sheet_id": sheet_id, "row_count": len(values)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def execute_email_send(config: dict, trigger_data: dict, dry_run: bool = False) -> dict:
    """Send an email (placeholder — requires SMTP or Gmail API setup)."""
    to = config.get("to", "")
    subject = config.get("subject", "")
    body = config.get("body", "")

    if not to:
        return {"ok": False, "error": "No recipient specified"}

    if dry_run:
        return {"ok": True, "dry_run": True, "to": to, "subject": subject}

    # TODO: Wire up SMTP or Gmail API
    return {"ok": False, "error": "Email sending not yet configured — add SMTP credentials to .env"}


# ─── Action Registry ───

ACTION_REGISTRY: dict[str, Any] = {
    "discord_notify": execute_discord_notify,
    "ghl_create_contact": execute_ghl_create_contact,
    "http_request": execute_http_request,
    "google_sheets_append": execute_google_sheets_append,
    "email_send": execute_email_send,
}


# ─── Main Executor ───

def execute_automation(
    automation_id: str,
    actions: list[dict],
    trigger_data: dict,
    dry_run: bool = False,
) -> dict:
    """Execute an automation's action chain.

    Args:
        automation_id: UUID of the automation (for logging)
        actions: List of action dicts [{"type": "...", "config": {...}}]
        trigger_data: Data from the trigger (webhook payload, etc.)
        dry_run: If True, validate but don't execute

    Returns:
        {"ok": True/False, "results": [...], "duration_ms": int}
    """
    start = time.time()
    results = []
    all_ok = True

    for i, action in enumerate(actions):
        action_type = action.get("type", "")
        raw_config = action.get("config", {})

        executor = ACTION_REGISTRY.get(action_type)
        if not executor:
            results.append({"step": i + 1, "type": action_type, "ok": False,
                           "error": f"Unknown action type: {action_type}"})
            all_ok = False
            continue

        # Interpolate variables
        config = interpolate_config(raw_config, trigger_data)

        try:
            result = executor(config, trigger_data, dry_run=dry_run)
            result["step"] = i + 1
            result["type"] = action_type
            results.append(result)
            if not result.get("ok"):
                all_ok = False
        except Exception as e:
            results.append({"step": i + 1, "type": action_type, "ok": False,
                           "error": str(e)})
            all_ok = False

    duration_ms = int((time.time() - start) * 1000)

    return {
        "ok": all_ok,
        "automation_id": automation_id,
        "dry_run": dry_run,
        "results": results,
        "duration_ms": duration_ms,
        "status": "success" if all_ok else ("partial" if any(r.get("ok") for r in results) else "failed"),
    }
