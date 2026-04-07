"""
Modal webhook: GHL → Discord (instant, permanent URL, replaces Zapier).

Deploy:  modal deploy execution/modal_ghl_webhook.py
Test:    curl -X POST https://nick-90891--ghl-discord-webhook.modal.run/call-booked -H 'Content-Type: application/json' -d '{"Name":"Test"}'

GHL Setup:
  1. In GHL workflow, set webhook URL to: https://nick-90891--ghl-discord-webhook.modal.run/call-booked
  2. Set method to POST
  3. Add custom data fields: Name, Email, Phone, Call Date Time, Capital, Credit, etc.
  4. Remove the old Discord webhook action (we handle it now)
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

import modal

app = modal.App("ghl-discord-webhook")

# Discord channel IDs (Sales Team Discord)
CHANNELS = {
    "call-booked": "1326007621211127859",
    "call-cancelled": "1459633032054046794",
    "payment-successful": "1248405410600452207",
    "payment-failed": "1439382067589677177",
    "free-training-opt-in": "1317256857483743232",
    "webby-opt-in": "1406887388264796231",
    "eoc-report": "1426377199170097152",
}


def discord_send(channel_id: str, embed: dict) -> dict:
    """Send embed to Discord channel via bot API."""
    bot_token = os.environ["DISCORD_SALES_BOT_TOKEN"]
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bot {bot_token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "DiscordBot (nomad-nebula, 1.0)")
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode("utf-8"))


def _get(data: dict, *keys: str, default: str = "N/A") -> str:
    for key in keys:
        val = data.get(key)
        if val:
            return str(val)
    return default


HANDLERS = {
    "call-booked": lambda data: {
        "title": "\U0001f4de\U0001f3e0 24/7 Profits Sales Call Booked!",
        "description": "\n".join([
            f"\U0001f464 **Prospect & Closer:**  {_get(data, 'Calendar Title', 'calendar_title', 'Name', 'name')}",
            "",
            f"\U0001f3d7 **Setter Who Booked Call:**  {_get(data, 'Setter', 'setter')}",
            "",
            f"\U0001f4e7 **Email:**  {_get(data, 'Email', 'email')}",
            f"\U0001f4de **Phone:**  {_get(data, 'Phone', 'phone')}",
            f"\U0001f4c5 **Call Date:**  {_get(data, 'Call Date Time', 'call_date_time', 'Call_Date_Time', 'start_time', 'startTime')}",
            "",
            f"\U0001f911 **Sells On Amazon Already?:**  {_get(data, 'Amazon Seller', 'amazon_seller')}",
            f"\U0001f4b0 **Capital To Invest:**  {_get(data, 'Capital', 'capital')}",
            f"\U0001f4b3 **Credit Score:**  {_get(data, 'Credit', 'credit')}",
            f"\u2049\ufe0f **Struggle:**  {_get(data, 'Struggle', 'struggle')}",
            f"\u2705 **Show Up Commitment:**  {_get(data, 'Will Show Up', 'will_show_up')}",
            "",
            f"\U0001f4cd **Source:**  {_get(data, 'Source', 'source')}",
            f"\U0001f3af **Closer:**  {_get(data, 'Closer', 'closer')}",
        ]),
        "color": 0x00FF88,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    },
    "call-cancelled": lambda data: {
        "title": "\u274c Call Cancelled",
        "description": "\n".join([
            f"\U0001f464 **Prospect:**  {_get(data, 'Name', 'name')}",
            f"\U0001f4e7 **Email:**  {_get(data, 'Email', 'email')}",
            f"\U0001f4de **Phone:**  {_get(data, 'Phone', 'phone')}",
            f"\U0001f4c5 **Original Date:**  {_get(data, 'Call Date Time', 'call_date_time')}",
            f"\U0001f6ab **Reason:**  {_get(data, 'Reason', 'reason')}",
        ]),
        "color": 0xFF4444,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    },
    "payment-successful": lambda data: {
        "title": "\U0001f3c6 Payment Successful!",
        "description": "\n".join([
            f"\U0001f464 **Name:**  {_get(data, 'Name', 'name')}",
            f"\U0001f4e7 **Email:**  {_get(data, 'Email', 'email')}",
            f"\U0001f4b5 **Amount:**  {_get(data, 'Amount', 'amount')}",
            f"\U0001f4e6 **Product:**  {_get(data, 'Product', 'product')}",
        ]),
        "color": 0x00FF00,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    },
    "payment-failed": lambda data: {
        "title": "\u274c Payment Failed",
        "description": "\n".join([
            f"\U0001f464 **Name:**  {_get(data, 'Name', 'name')}",
            f"\U0001f4e7 **Email:**  {_get(data, 'Email', 'email')}",
            f"\U0001f4b5 **Amount:**  {_get(data, 'Amount', 'amount')}",
            f"\U0001f6ab **Reason:**  {_get(data, 'Reason', 'reason')}",
        ]),
        "color": 0xFF0000,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    },
    "free-training-opt-in": lambda data: {
        "title": "\U0001f6a8 New Free Training Opt-In!",
        "description": "\n".join([
            f"\U0001f464 **Name:**  {_get(data, 'Name', 'name')}",
            f"\U0001f4e7 **Email:**  {_get(data, 'Email', 'email')}",
            f"\U0001f4de **Phone:**  {_get(data, 'Phone', 'phone')}",
            f"\U0001f4cd **Source:**  {_get(data, 'Source', 'source')}",
        ]),
        "color": 0xFFAA00,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    },
    "webby-opt-in": lambda data: {
        "title": "\U0001f4c5 Webinar Opt-In!",
        "description": "\n".join([
            f"\U0001f464 **Name:**  {_get(data, 'Name', 'name')}",
            f"\U0001f4e7 **Email:**  {_get(data, 'Email', 'email')}",
            f"\U0001f4de **Phone:**  {_get(data, 'Phone', 'phone')}",
            f"\U0001f4cd **Source:**  {_get(data, 'Source', 'source')}",
        ]),
        "color": 0x5865F2,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    },
    "eoc-report": lambda data: {
        "title": "\U0001f4ca EOC Report Submitted",
        "description": "\n".join([
            f"\U0001f464 **Closer:**  {_get(data, 'Name', 'name')}",
            f"\U0001f4de **Calls:**  {_get(data, 'Calls', 'calls')}",
            f"\U0001f440 **Shows:**  {_get(data, 'Shows', 'shows')}",
            f"\U0001f91d **Closes:**  {_get(data, 'Closes', 'closes')}",
            f"\U0001f4b0 **Revenue:**  {_get(data, 'Revenue', 'revenue')}",
        ]),
        "color": 0x00BFFF,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    },
}


@app.function(
    secrets=[modal.Secret.from_name("discord-sales-bot")],
)
@modal.web_endpoint(method="POST", label="ghl-discord-webhook")
def webhook(slug: str = "call-booked"):
    """Receive GHL webhook POST → send rich Discord embed instantly."""
    from modal import web  # noqa
    import fastapi

    # This won't work with the simple decorator — need to use the ASGI approach
    pass


# Use the ASGI/web server approach for path-based routing
@app.function(
    secrets=[modal.Secret.from_name("discord-sales-bot")],
)
@modal.asgi_app(label="ghl-discord")
def fastapi_app():
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    api = FastAPI()

    @api.post("/{slug}")
    async def handle(slug: str, request: Request):
        try:
            data = await request.json()
        except Exception:
            data = {}

        handler = HANDLERS.get(slug)
        if not handler:
            return JSONResponse(
                {"error": f"Unknown slug: {slug}", "available": list(HANDLERS.keys())},
                status_code=404,
            )

        embed = handler(data)
        channel_id = CHANNELS.get(slug)
        if not channel_id:
            return JSONResponse({"error": f"No channel for: {slug}"}, status_code=404)

        try:
            result = discord_send(channel_id, embed)
            return {"ok": True, "discord_message_id": result.get("id")}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @api.get("/")
    async def list_slugs():
        return {"available_webhooks": list(HANDLERS.keys())}

    return api
