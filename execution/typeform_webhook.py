"""
Typeform → Discord webhook relay for webinar opt-ins.

Deploy:  modal deploy execution/typeform_webhook.py
URL:     https://nick-90891--typeform-webby-webhook-relay.modal.run

Typeform Setup:
  1. Go to your form → Connect → Webhooks
  2. Paste the Modal URL above
  3. Every submission sends a Discord notification

Discord webhook sends directly — no bot token needed.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

import modal

app = modal.App("typeform-webby-webhook")

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1490603389120286722/bhoW16Tt-DIU-4s_GphJYwWUNJDPiiKWJkHhLR-wHda1TIhyStbd35Vccv8d-zqznum-"

# File-based counter (persisted in Modal volume)
vol = modal.Volume.from_name("typeform-counter", create_if_missing=True)


def _extract_typeform(data: dict) -> dict:
    """Extract answers from Typeform webhook payload."""
    answers = {}
    form_response = data.get("form_response", {})

    # Extract answers by field type
    for answer in form_response.get("answers", []):
        field = answer.get("field", {})
        field_ref = field.get("ref", "")
        field_title = field.get("title", "").lower()
        answer_type = answer.get("type", "")

        # Get the value based on answer type
        if answer_type == "text":
            value = answer.get("text", "")
        elif answer_type == "email":
            value = answer.get("email", "")
        elif answer_type == "phone_number":
            value = answer.get("phone_number", "")
        elif answer_type == "choice":
            value = answer.get("choice", {}).get("label", "")
        elif answer_type == "boolean":
            value = "Yes" if answer.get("boolean") else "No"
        elif answer_type == "number":
            value = str(answer.get("number", ""))
        else:
            value = str(answer.get(answer_type, ""))

        # Map to our fields by checking field title keywords
        if "first" in field_title and "name" in field_title:
            answers["first_name"] = value
        elif "name" in field_title:
            answers["first_name"] = answers.get("first_name", value)
        elif "email" in field_title:
            answers["email"] = value
        elif "phone" in field_title:
            answers["phone"] = value
        elif "amazon" in field_title or "sell" in field_title:
            answers["sells_amazon"] = value
        elif "struggle" in field_title or "challenge" in field_title or "help" in field_title:
            answers["struggles"] = value
        elif "capital" in field_title or "invest" in field_title or "budget" in field_title:
            answers["capital"] = value
        elif "source" in field_title or "hear" in field_title or "find" in field_title:
            answers["source"] = value

        # Also map by ref if title matching fails
        if field_ref:
            ref_lower = field_ref.lower()
            if "name" in ref_lower and "first_name" not in answers:
                answers["first_name"] = value
            elif "email" in ref_lower and "email" not in answers:
                answers["email"] = value
            elif "phone" in ref_lower and "phone" not in answers:
                answers["phone"] = value

    # Calculate time to finish
    submitted_at = form_response.get("submitted_at", "")
    landed_at = form_response.get("landed_at", "")
    time_to_finish = ""
    if submitted_at and landed_at:
        try:
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            start = datetime.strptime(landed_at, fmt)
            end = datetime.strptime(submitted_at, fmt)
            delta = int((end - start).total_seconds())
            mins, secs = divmod(abs(delta), 60)
            hrs, mins = divmod(mins, 60)
            time_to_finish = f"{hrs:02d}:{mins:02d}:{secs:02d}"
        except Exception:
            pass

    answers["time_to_finish"] = time_to_finish
    return answers


def _get_count() -> int:
    """Read and increment the registrant counter."""
    count_file = "/data/registrant_count.txt"
    try:
        with open(count_file, "r") as f:
            count = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        count = 0
    count += 1
    with open(count_file, "w") as f:
        f.write(str(count))
    return count


@app.function(
    volumes={"/data": vol},
)
@modal.concurrent(max_inputs=10)
@modal.fastapi_endpoint(method="POST", label="typeform-webby-webhook-relay")
def relay(data: dict = {}):
    """Receive Typeform webhook → format → send to Discord."""
    answers = _extract_typeform(data)

    # Increment counter
    count = _get_count()
    vol.commit()

    first_name = answers.get("first_name", "Unknown")
    phone = answers.get("phone", "N/A")
    email = answers.get("email", "N/A")
    sells_amazon = answers.get("sells_amazon", "N/A")
    struggles = answers.get("struggles", "N/A")
    capital = answers.get("capital", "N/A")
    source = answers.get("source", "")
    time_to_finish = answers.get("time_to_finish", "N/A")

    # Build Discord message (plain text, matching the exact format requested)
    message = "\n".join([
        "**NEW WEBBY OPT-IN** \U0001f6a8",
        "-",
        f"Registrant Count: **{count}** / 1,000",
        f"\U0001f465First Name: {first_name}",
        f"\U0001f4f2Phone Number: {phone}",
        f"\U0001f4e7Email: {email}",
        f"\U0001f4e6Sells On Amazon: {sells_amazon}",
        f"\u2753Struggles With: {struggles}",
        f"\U0001f4b0Capital To Invest: {capital}",
        f"Source: {source}",
        "-",
        f"\u23f0Time To Finish Form: {time_to_finish}",
    ])

    # Send to Discord webhook
    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=payload,
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "TypeformRelay/1.0")

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.getcode()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "status": status, "count": count}
