#!/usr/bin/env python3
"""
Script: ghl_automations.py
Purpose: Replace Zapier — receive GHL workflow webhooks and route to Discord/sheets/etc.

Usage (standalone test):
  python execution/ghl_automations.py test-call-booked

Routes (added to app.py):
  POST  /webhooks/call-booked       — New sales call booked → Discord #call-booked
  POST  /webhooks/call-cancelled    — Call cancelled → Discord #call-cancelled
  POST  /webhooks/payment-success   — Payment received → Discord #payment-successful
  POST  /webhooks/payment-failed    — Payment failed → Discord #payment-failed
  POST  /webhooks/opt-in            — Funnel opt-in → Discord #free-training-opt-in
  POST  /webhooks/webby-opt-in      — Webinar opt-in → Discord #webby-opt-in
  POST  /webhooks/eoc-report        — EOC report submitted → Discord #eoc-report

GHL Setup:
  1. In GHL workflow, replace the Zapier webhook URL with:
     https://<your-domain>/webhooks/call-booked
  2. Keep the same custom data fields (Name, Email, Phone, etc.)
  3. Save & publish the workflow

Architecture:
  GHL Workflow → POST webhook → Flask route → Discord bot API → channel message
  No Zapier. No middleman. Zero monthly cost.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path for sibling imports
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger("ghl-automations")

# ─── Discord channel IDs (Sales Team Discord: 1247237585252909088) ───
CHANNELS = {
    # Existing (GHL workflow handlers)
    "call-booked": "1326007621211127859",
    "call-cancelled": "1459633032054046794",
    "payment-successful": "1248405410600452207",
    "payment-failed": "1439382067589677177",
    "free-training-opt-in": "1317256857483743232",
    "webby-opt-in": "1406887388264796231",
    "eoc-report": "1426377199170097152",
    # New (Zapier migration)
    "ic-applications": "1317256857483743232",       # TODO: Sabbo — replace with correct channel ID
    "student-onboarding": "1248405410600452207",     # TODO: Sabbo — replace with correct channel ID
    "sdr-eod-report": "1426377199170097152",         # TODO: Sabbo — replace with correct channel ID
    "sdr-applications": "1317256857483743232",       # TODO: Sabbo — replace with correct channel ID
    "raw-footage": "1326007621211127859",            # TODO: Sabbo — replace with correct channel ID
    "ic-product-leads": "1352031282799837237",       # 🔎┃new-product-lead (already exists in app.py)
    "fanbasis-payments": "1248405410600452207",      # TODO: Sabbo — replace with correct channel ID
}


def _get_bot_token() -> str:
    """Get Discord sales bot token from env."""
    token = os.environ.get("DISCORD_SALES_BOT_TOKEN", "")
    if not token:
        raise ValueError("DISCORD_SALES_BOT_TOKEN not set in .env")
    return token


def discord_send(channel_key: str, content: str = "", embed: dict | None = None) -> dict:
    """Send a message to a Discord channel using the bot API."""
    bot_token = _get_bot_token()
    channel_id = CHANNELS.get(channel_key)
    if not channel_id:
        raise ValueError(f"Unknown channel key: {channel_key}")

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    payload: dict = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bot {bot_token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "DiscordBot (https://nomad-nebula, 1.0)")

    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode("utf-8"))


def _get(data: dict, *keys: str, default: str = "No data") -> str:
    """Try multiple key variations (Title Case, lowercase, snake_case)."""
    for key in keys:
        val = data.get(key)
        if val:
            return str(val)
    return default


# ─── Call Booked ───

def handle_call_booked(data: dict) -> dict:
    """GHL call booked → Discord #call-booked."""
    name = _get(data, "Name", "name", "contact_name", default="Unknown")
    email = _get(data, "Email", "email")
    phone = _get(data, "Phone", "phone")
    call_dt = _get(data, "Call Date Time", "call_date_time", "Call_Date_Time")
    seller = _get(data, "Amazon Seller", "amazon_seller")
    capital = _get(data, "Capital", "capital")
    credit = _get(data, "Credit", "credit")
    struggle = _get(data, "Struggle", "struggle")
    show_up = _get(data, "Will Show Up", "will_show_up")
    closer = _get(data, "Closer", "closer")
    setter = _get(data, "Setter", "setter")
    source = _get(data, "Source", "source")
    calendar = _get(data, "Calendar Title", "calendar_title", default="")

    embed = {
        "title": "\U0001f4de\U0001f3e0 24/7 Profits Sales Call Booked!",
        "description": "\n".join([
            f"\U0001f464 **Prospect & Closer:**  {calendar}",
            "",
            f"\U0001f3d7 **Setter Who Booked Call:**  {setter}",
            "",
            f"\U0001f4e7 **Email:**  {email}",
            f"\U0001f4de **Phone:**  {phone}",
            f"\U0001f4c5 **Call Date:**  {call_dt}",
            "",
            f"\U0001f911 **Sells On Amazon Already?:**  {seller}",
            f"\U0001f4b0 **Capital To Invest:**  {capital}",
            f"\U0001f4b3 **Credit Score:**  {credit}",
            f"\u2049\ufe0f **Struggle:**  {struggle}",
            f"\u2705 **Show Up Commitment:**  {show_up}",
            "",
            f"\U0001f4cd **Source:**  {source}",
            f"\U0001f3af **Closer:**  {closer}",
        ]),
        "color": 0x00FF88,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    }

    result = discord_send("call-booked", embed=embed)
    logger.info(f"[call-booked] Sent for {name} → msg {result.get('id')}")
    return {"ok": True, "discord_message_id": result.get("id"), "prospect": name}


# ─── Call Cancelled ───

def handle_call_cancelled(data: dict) -> dict:
    """GHL call cancelled → Discord #call-cancelled."""
    name = _get(data, "Name", "name", "contact_name", default="Unknown")
    email = _get(data, "Email", "email")
    phone = _get(data, "Phone", "phone")
    call_dt = _get(data, "Call Date Time", "call_date_time", "Call_Date_Time")
    reason = _get(data, "Reason", "reason", "cancellation_reason")
    closer = _get(data, "Closer", "closer")
    setter = _get(data, "Setter", "setter")

    embed = {
        "title": "\u274c Call Cancelled",
        "description": "\n".join([
            f"\U0001f464 **Prospect:**  {name}",
            f"\U0001f4e7 **Email:**  {email}",
            f"\U0001f4de **Phone:**  {phone}",
            f"\U0001f4c5 **Original Date:**  {call_dt}",
            f"\U0001f6ab **Reason:**  {reason}",
            "",
            f"\U0001f3af **Closer:**  {closer}",
            f"\U0001f3d7 **Setter:**  {setter}",
        ]),
        "color": 0xFF4444,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    }

    result = discord_send("call-cancelled", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "prospect": name}


# ─── Payment Success ───

def handle_payment_success(data: dict) -> dict:
    """GHL payment received → Discord #payment-successful."""
    name = _get(data, "Name", "name", "contact_name", default="Unknown")
    email = _get(data, "Email", "email")
    amount = _get(data, "Amount", "amount", "payment_amount")
    product = _get(data, "Product", "product", "product_name")
    plan = _get(data, "Plan", "plan", "payment_plan")

    embed = {
        "title": "\U0001f3c6 Payment Successful!",
        "description": "\n".join([
            f"\U0001f464 **Name:**  {name}",
            f"\U0001f4e7 **Email:**  {email}",
            f"\U0001f4b5 **Amount:**  {amount}",
            f"\U0001f4e6 **Product:**  {product}",
            f"\U0001f4cb **Plan:**  {plan}",
        ]),
        "color": 0x00FF00,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    }

    result = discord_send("payment-successful", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": name}


# ─── Payment Failed ───

def handle_payment_failed(data: dict) -> dict:
    """GHL payment failed → Discord #payment-failed."""
    name = _get(data, "Name", "name", "contact_name", default="Unknown")
    email = _get(data, "Email", "email")
    amount = _get(data, "Amount", "amount", "payment_amount")
    reason = _get(data, "Reason", "reason", "failure_reason")

    embed = {
        "title": "\u274c Payment Failed",
        "description": "\n".join([
            f"\U0001f464 **Name:**  {name}",
            f"\U0001f4e7 **Email:**  {email}",
            f"\U0001f4b5 **Amount:**  {amount}",
            f"\U0001f6ab **Reason:**  {reason}",
        ]),
        "color": 0xFF0000,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    }

    result = discord_send("payment-failed", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": name}


# ─── Opt-In (Free Training) ───

def handle_opt_in(data: dict) -> dict:
    """GHL funnel opt-in → Discord #free-training-opt-in."""
    name = _get(data, "Name", "name", "contact_name", default="Unknown")
    email = _get(data, "Email", "email")
    phone = _get(data, "Phone", "phone")
    source = _get(data, "Source", "source")

    embed = {
        "title": "\U0001f6a8 New Free Training Opt-In!",
        "description": "\n".join([
            f"\U0001f464 **Name:**  {name}",
            f"\U0001f4e7 **Email:**  {email}",
            f"\U0001f4de **Phone:**  {phone}",
            f"\U0001f4cd **Source:**  {source}",
        ]),
        "color": 0xFFAA00,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    }

    result = discord_send("free-training-opt-in", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": name}


# ─── Webinar Opt-In ───

def handle_webby_opt_in(data: dict) -> dict:
    """GHL webinar opt-in → Discord #webby-opt-in + ConvertKit subscriber."""
    name = _get(data, "Name", "name", "contact_name", default="Unknown")
    email = _get(data, "Email", "email")
    phone = _get(data, "Phone", "phone")
    source = _get(data, "Source", "source")

    embed = {
        "title": "\U0001f4c5 Webinar Opt-In!",
        "description": "\n".join([
            f"\U0001f464 **Name:**  {name}",
            f"\U0001f4e7 **Email:**  {email}",
            f"\U0001f4de **Phone:**  {phone}",
            f"\U0001f4cd **Source:**  {source}",
        ]),
        "color": 0x5865F2,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    }

    result = discord_send("webby-opt-in", embed=embed)

    # Add to ConvertKit (replaces Zapier ConvertKit step in Webby OPT-IN zap)
    ck_result = {"skipped": True}
    try:
        from execution.convertkit_client import add_subscriber  # noqa: E402
        ck_result = add_subscriber(
            email=email,
            first_name=name,
            form_id=os.environ.get("CONVERTKIT_WEBBY_FORM_ID", ""),
        )
    except Exception as e:
        logger.warning(f"[webby-opt-in] ConvertKit error (non-fatal): {e}")

    return {"ok": True, "discord_message_id": result.get("id"), "name": name,
            "convertkit": ck_result}


# ─── EOC Report ───

def handle_eoc_report(data: dict) -> dict:
    """GHL EOC report submitted → Discord #eoc-report."""
    name = _get(data, "Name", "name", "closer_name", default="Unknown")
    calls = _get(data, "Calls", "calls", "total_calls")
    shows = _get(data, "Shows", "shows", "total_shows")
    closes = _get(data, "Closes", "closes", "total_closes")
    revenue = _get(data, "Revenue", "revenue", "total_revenue")
    notes = _get(data, "Notes", "notes", "eoc_notes")

    embed = {
        "title": "\U0001f4ca EOC Report Submitted",
        "description": "\n".join([
            f"\U0001f464 **Closer:**  {name}",
            f"\U0001f4de **Calls:**  {calls}",
            f"\U0001f440 **Shows:**  {shows}",
            f"\U0001f91d **Closes:**  {closes}",
            f"\U0001f4b0 **Revenue:**  {revenue}",
            f"\U0001f4dd **Notes:**  {notes}",
        ]),
        "color": 0x00BFFF,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "GHL \u2192 Direct (no Zapier)"},
    }

    result = discord_send("eoc-report", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": name}


# ─── Typeform Answer Parser ───

def parse_typeform_answers(data: dict) -> dict:
    """Extract field:value pairs from Typeform webhook payload.

    Typeform sends: {"form_response": {"answers": [{"field": {"ref": "..."}, "type": "...", "text": "..."}]}}
    Also handles Zapier-style flat payloads for backwards compatibility.
    """
    # Handle raw Typeform webhook format
    form_response = data.get("form_response", {})
    if form_response:
        answers = form_response.get("answers", [])
        hidden = form_response.get("hidden", {})
        result = {}
        for ans in answers:
            ref = ans.get("field", {}).get("ref", "")
            field_id = ans.get("field", {}).get("id", "")
            key = ref or field_id
            # Extract value based on answer type
            ans_type = ans.get("type", "")
            if ans_type == "choice":
                val = ans.get("choice", {}).get("label", "")
            elif ans_type == "choices":
                labels = [c.get("label", "") for c in ans.get("choices", {}).get("labels", [])]
                val = ", ".join(labels)
            elif ans_type in ("number", "rating"):
                val = str(ans.get(ans_type, ""))
            elif ans_type == "boolean":
                val = "Yes" if ans.get("boolean") else "No"
            elif ans_type == "email":
                val = ans.get("email", "")
            elif ans_type == "phone_number":
                val = ans.get("phone_number", "")
            elif ans_type == "date":
                val = ans.get("date", "")
            else:
                val = ans.get("text", ans.get(ans_type, ""))
            result[key] = str(val) if val else ""
        # Merge hidden fields (UTM params etc.)
        result.update(hidden)
        return result

    # Flat payload (Zapier-style or direct POST)
    return data


# ─── Typeform: IC Application (ZAP-001) ───

def handle_typeform_ic(data: dict) -> dict:
    """Typeform IC Application → GHL Contact + Discord #ic-applications."""
    fields = parse_typeform_answers(data)

    first_name = _get(fields, "first_name", "firstName", "name", default="Unknown")
    email = _get(fields, "email", "Email", default="")
    phone = _get(fields, "phone", "phone_number", "Phone", default="")
    age = _get(fields, "age", "Age", default="")
    selling = _get(fields, "currently_selling", "are_you_currently_selling_on_amazon",
                   "Amazon Seller", default="")
    capital = _get(fields, "capital", "how_much_do_you_have_to_invest",
                   "amount_of_capital", default="")
    struggle = _get(fields, "struggle", "biggest_struggle",
                    "what_is_your_biggest_problem", default="")
    credit = _get(fields, "credit", "credit_score",
                  "what_is_your_credit_score", default="")
    utm_source = _get(fields, "utm_source", default="")
    utm_campaign = _get(fields, "utm_campaign", default="")
    utm_medium = _get(fields, "utm_medium", default="")
    utm_content = _get(fields, "utm_content", default="")

    # Create/update GHL contact
    try:
        from execution.ghl_client import create_or_update_contact  # noqa: E402
        ghl_result = create_or_update_contact(
            email=email,
            first_name=first_name,
            phone=phone,
            tags=["ic-application"],
            custom_fields={
                "are_you_currently_selling_on_amazon": selling,
                "how_much_do_you_have_to_invest_into_your_amazon_business_and_education_right_now": capital,
                "what_is_your_biggest_problem_when_it_comes_to_selling_on_amazon_or_making_money_online_in_general": struggle,
                "what_is_your_credit_score_roughly": credit,
            },
            pipeline_id="sFxWPIwC0fTGZBNRO0Lf",
            stage_id="8a87671c-caa6-4669-a47d-69040cac6195",
            source=utm_source or "typeform-ic",
        )
    except Exception as e:
        logger.error(f"[typeform-ic] GHL error: {e}")
        ghl_result = {"ok": False, "error": str(e)}

    # Discord notification
    utm_block = ""
    if any([utm_source, utm_campaign, utm_medium, utm_content]):
        utm_block = "\n".join([
            "",
            "\U0001f4cd **UTMs Tracked:**",
            f"  Source: {utm_source}",
            f"  Campaign: {utm_campaign}",
            f"  Medium: {utm_medium}",
            f"  Content: {utm_content}",
        ])

    embed = {
        "title": "\U0001f6a8 New IC Application!",
        "description": "\n".join([
            f"\U0001f464 **First Name:** {first_name}",
            f"\U0001f382 **Age:** {age}",
            f"\U0001f4de **Phone:** {phone}",
            f"\U0001f4e7 **Email:** {email}",
            f"\U0001f4e6 **Currently Selling:** {selling}",
            f"\U0001f4b0 **Capital:** {capital}",
            f"\u2753 **Biggest Struggle:** {struggle}",
            f"\U0001f4b3 **Credit Score:** {credit}",
            utm_block,
        ]),
        "color": 0xFF6600,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Typeform \u2192 Direct (no Zapier)"},
    }

    result = discord_send("ic-applications", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": first_name,
            "ghl": ghl_result}


# ─── Typeform: New Student Onboarding (ZAP-008) ───

def handle_typeform_onboarding(data: dict) -> dict:
    """Typeform Student Onboarding → Discord #student-onboarding."""
    fields = parse_typeform_answers(data)

    first_name = _get(fields, "first_name", "firstName", "name", default="Unknown")
    email = _get(fields, "email", "Email", default="")
    phone = _get(fields, "phone", "phone_number", "Phone", default="")
    age = _get(fields, "age", "Age", default="")
    ig_handle = _get(fields, "ig_handle", "instagram", "IG Handle", default="")
    location = _get(fields, "location", "Location", default="")
    works = _get(fields, "works", "Works", default="")
    selling = _get(fields, "selling_on_amazon", "Selling On AMZN", default="")
    capital = _get(fields, "capital", "has_money_to_invest", "Has $$$ To Invest", default="")
    credit = _get(fields, "credit", "credit_score", default="")

    embed = {
        "title": "\U0001f6a8 New Student Onboarding!",
        "description": "\n".join([
            f"\U0001f464 **First Name:** {first_name}",
            f"\U0001f4de **Phone:** {phone}",
            f"\U0001f4e7 **Email:** {email}",
            f"\U0001f382 **Age:** {age}",
            f"\U0001f4f8 **IG Handle:** {ig_handle}",
            f"\U0001f4cd **Location:** {location}",
            f"\U0001f4bc **Works:** {works}",
            "",
            f"\U0001f4e6 **Selling On Amazon?:** {selling}",
            f"\U0001f4b0 **Has $$$ To Invest:** {capital}",
            f"\U0001f4b3 **Credit Score:** {credit}",
        ]),
        "color": 0x00FF88,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Typeform \u2192 Direct (no Zapier)"},
    }

    result = discord_send("student-onboarding", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": first_name}


# ─── Typeform: Agency SDR Application (ZAP-014) ───

def handle_typeform_sdr_app(data: dict) -> dict:
    """Typeform SDR Application → Discord #sdr-applications."""
    fields = parse_typeform_answers(data)

    name = _get(fields, "name", "first_name", "firstName", default="Unknown")
    last_name = _get(fields, "last_name", "lastName", default="")
    full_name = f"{name} {last_name}".strip()
    email = _get(fields, "email", "Email", default="")
    phone = _get(fields, "phone", "phone_number", "Phone", default="")
    location = _get(fields, "location", "Location", default="")
    start_date = _get(fields, "when_can_they_start", "start_date",
                      "When can they start", default="")
    experience = _get(fields, "experience", "Experience", default="")
    hours = _get(fields, "hours_per_day", "Hours Per Day To Work", default="")

    embed = {
        "title": "\U0001f4cb New SDR Sales Rep Application",
        "description": "\n".join([
            f"\U0001f464 **Name:** {full_name}",
            f"\U0001f4e7 **Email:** {email}",
            f"\U0001f4de **Phone:** {phone}",
            f"\U0001f4cd **Location:** {location}",
            f"\U0001f4c5 **Can Start:** {start_date}",
            f"\U0001f4bc **Experience:** {experience}",
            f"\u23f0 **Hours/Day:** {hours}",
        ]),
        "color": 0x5865F2,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Typeform \u2192 Direct (no Zapier)"},
    }

    result = discord_send("sdr-applications", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": full_name}


# ─── Google Forms: SDR End Of Day Report (ZAP-010) ───

def handle_sdr_eod(data: dict) -> dict:
    """Google Forms SDR EOD → Discord #sdr-eod-report.

    Expects JSON payload from Google Apps Script attached to the form.
    """
    date = _get(data, "date", "Date", default="Today")
    setter_name = _get(data, "setter_name", "Setter Name", "name", default="Unknown")
    dials = _get(data, "dials", "Dials (Phone)", default="0")
    quality_convos = _get(data, "quality_conversations", "Quality Conversations", default="0")
    calls_booked = _get(data, "calls_booked", "Calls Booked (Phone)", default="0")
    calls_on_cal = _get(data, "calls_on_calendar", "Calls On Calendar (Phone)", default="0")
    deals_closed = _get(data, "deals_closed", "Deals Closed (Phone)", default="0")
    new_dms = _get(data, "new_convos_dm", "New Convos (DM)", default="0")
    followup_dms = _get(data, "followup_convos_dm", "Follow Up Convos (DM)", default="0")
    dm_booked = _get(data, "dm_calls_booked", "Calls Booked (DM)", default="0")
    notes = _get(data, "notes", "Notes", "Additional Notes", default="None")

    embed = {
        "title": "\U0001f4dd SDR End Of Day Report",
        "description": "\n".join([
            f"\U0001f4c5 **Date:** {date}",
            f"\U0001f464 **Setter:** {setter_name}",
            f"\U0001f3af **Offer:** 24/7 Profits - AllDayFBA LLC",
            "",
            "**\U0001f4de Phone:**",
            f"  Dials: {dials}",
            f"  Quality Convos (2-5 min): {quality_convos}",
            f"  Calls Booked: {calls_booked}",
            f"  Calls On Calendar: {calls_on_cal}",
            f"  Deals Closed: {deals_closed}",
            "",
            "**\U0001f4ac DMs:**",
            f"  New Convos: {new_dms}",
            f"  Follow-Up Convos: {followup_dms}",
            f"  Calls Booked: {dm_booked}",
            "",
            f"\U0001f4cb **Notes:** {notes}",
        ]),
        "color": 0x00BFFF,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Google Forms \u2192 Direct (no Zapier)"},
    }

    result = discord_send("sdr-eod-report", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": setter_name}


# ─── FanBasis: Payment (ZAP-004) ───

def handle_fanbasis_payment(data: dict) -> dict:
    """FanBasis payment event → filter for Circle product → GHL Contact + Discord.

    FanBasis sends payment webhooks with product info. We only process
    payments that contain 'Circle' in the product title (matching the
    original Zapier filter).
    """
    product_title = _get(data, "product_title", "product", "Product", default="")

    # Filter: only process Circle products (matching Zapier filter)
    if "circle" not in product_title.lower():
        logger.info(f"[fanbasis] Skipping non-Circle product: {product_title}")
        return {"ok": True, "skipped": True, "reason": f"Product '{product_title}' is not Circle"}

    full_name = _get(data, "full_name", "name", "Name", default="Unknown")
    first_name = _get(data, "first_name", "firstName", default=full_name.split()[0] if full_name != "Unknown" else "Unknown")
    email = _get(data, "email", "Email", default="")
    phone = _get(data, "phone", "Phone", default="")
    amount = _get(data, "amount", "payment_amount", "Amount", default="0")
    payment_mode = _get(data, "payment_mode", default="")
    payment_method = _get(data, "payment_method", default="")

    # Create/update GHL contact
    try:
        from execution.ghl_client import create_or_update_contact  # noqa: E402
        ghl_result = create_or_update_contact(
            email=email,
            first_name=first_name,
            phone=phone,
            tags=["fanbasis-payment"],
            pipeline_id="fNtUwkQHwbYFjs6jIIDR",
            stage_id="7ca04e84-d4e1-4a60-9949-66472b66b94a",
            source="fanbasis",
        )
    except Exception as e:
        logger.error(f"[fanbasis] GHL error: {e}")
        ghl_result = {"ok": False, "error": str(e)}

    # Discord notification
    embed = {
        "title": "\U0001f7e3 FanBasis — New Payment!",
        "description": "\n".join([
            f"\U0001f3c6 **NEW PAYMENT LET'S GO!**",
            "",
            f"\U0001f464 **Name:** {full_name}",
            f"\U0001f4e6 **Product:** {product_title}",
            f"\U0001f4b3 **Method:** {payment_mode}|{payment_method}",
            f"\U0001f4b5 **Amount:** ${amount}",
            "",
            "\U0001f4b0 **AMEN TO WI-FI MONEY**",
        ]),
        "color": 0x9B59B6,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "FanBasis \u2192 Direct (no Zapier)"},
    }

    result = discord_send("fanbasis-payments", embed=embed)
    return {"ok": True, "discord_message_id": result.get("id"), "name": full_name,
            "ghl": ghl_result}


# ─── Route registry (used by app.py) ───

WEBHOOK_HANDLERS = {
    # Existing GHL handlers
    "call-booked": handle_call_booked,
    "call-cancelled": handle_call_cancelled,
    "payment-success": handle_payment_success,
    "payment-failed": handle_payment_failed,
    "opt-in": handle_opt_in,
    "webby-opt-in": handle_webby_opt_in,
    "eoc-report": handle_eoc_report,
    # New Zapier replacement handlers
    "typeform-ic": handle_typeform_ic,
    "typeform-onboarding": handle_typeform_onboarding,
    "typeform-sdr-app": handle_typeform_sdr_app,
    "sdr-eod": handle_sdr_eod,
    "fanbasis-payment": handle_fanbasis_payment,
}


# ─── CLI test ───

if __name__ == "__main__":
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    if len(sys.argv) < 2:
        print("Usage: python ghl_automations.py <handler> [json-file]")
        print(f"Handlers: {', '.join(WEBHOOK_HANDLERS.keys())}")
        sys.exit(1)

    handler_name = sys.argv[1]
    if handler_name.startswith("test-"):
        handler_name = handler_name[5:]

    handler = WEBHOOK_HANDLERS.get(handler_name)
    if not handler:
        print(f"Unknown handler: {handler_name}")
        sys.exit(1)

    # Load test data from file or use sample
    if len(sys.argv) > 2:
        test_data = json.loads(Path(sys.argv[2]).read_text())
    else:
        test_data = {
            "Name": "Test Prospect",
            "Email": "test@example.com",
            "Phone": "(555) 123-4567",
            "Call Date Time": "March 29, 2026, 2:30 PM",
            "Amazon Seller": "No",
            "Capital": "$5k-10k",
            "Credit": "700+",
            "Struggle": "Finding profitable products",
            "Will Show Up": "Yes I do",
            "Closer": "Rocky",
            "Setter": "Peter",
            "Source": "booking_widget",
            "Calendar Title": "ONBOARDING CALL - Test & Rocky",
        }

    print(f"Sending test {handler_name}...")
    result = handler(test_data)
    print(json.dumps(result, indent=2))
