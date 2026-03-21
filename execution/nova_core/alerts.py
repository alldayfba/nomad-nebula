"""Nova Alerts — posts operational alerts to Discord webhook."""

from __future__ import annotations

import os
import time
from typing import Optional

import requests

_last_alert: dict = {}
_MIN_INTERVAL = 300  # 5 min between same alert type


def send_alert(message: str, alert_type: str = "general", webhook_url: Optional[str] = None):
    """Post an alert to Discord ops webhook. Rate-limited per alert_type."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
    if not url:
        return False

    now = time.time()
    last = _last_alert.get(alert_type, 0)
    if now - last < _MIN_INTERVAL:
        return False

    try:
        resp = requests.post(url, json={"content": message}, timeout=5)
        _last_alert[alert_type] = now
        return resp.status_code in (200, 204)
    except Exception:
        return False


def alert_proxy_down(bot_name: str):
    send_alert(f"⚠️ **{bot_name} proxy DOWN** — auto-switching to API fallback", "proxy_down")


def alert_proxy_recovered(bot_name: str):
    send_alert(f"✅ **{bot_name} proxy RECOVERED** — back on Max plan", "proxy_recovered")


def alert_api_error(bot_name: str, error: str):
    send_alert(f"🔴 **{bot_name} API error:** {error[:200]}", "api_error")


def alert_rate_limit(bot_name: str, user_id: str):
    send_alert(f"⚡ **{bot_name}** rate limit hit by user {user_id}", "rate_limit")


def alert_injection(bot_name: str, user_id: str, severity: str):
    send_alert(f"🛡️ **{bot_name}** injection attempt (severity: {severity}) from user {user_id}", "injection")


def alert_backup_status(backed_up: int, errors: int):
    if errors:
        send_alert(f"🔴 **DB Backup:** {backed_up} OK, {errors} ERRORS", "backup")
    else:
        send_alert(f"✅ **DB Backup:** {backed_up} databases backed up successfully", "backup")
